"""
extractor.py
------------
Full data extraction pipeline for Jira Server/Data Center.
Supports both 'full' extraction (all fields) and 'selective' extraction
(only user-specified fields from config.yaml).

Extracts:
  - Project metadata (versions, components, issue types)
  - All issue types: Epics, Stories, Tasks, Bugs, Sub-tasks, custom types
  - Issue hierarchy (parent/child/epic relationships)
  - Comments (with rendered HTML body)
  - Attachments (metadata; actual download handled by AttachmentHandler)
  - Issue links (all link types)
  - Sprints (via Agile API)
  - Work logs
  - Watchers
  - Custom fields (dynamically discovered)
  - Changelog / history
"""

import logging
import re
from typing import Dict, Any, List, Optional, Set
from tqdm import tqdm

from .jira_client import JiraClient
from .attachment_handler import AttachmentHandler

logger = logging.getLogger(__name__)

# Standard fields that are always fetched regardless of selective mode
# (needed for hierarchy and linking)
MANDATORY_FIELDS = {
    "summary", "issuetype", "status", "parent", "subtasks",
    "issuelinks", "project", "created", "updated",
}


def safe_get(obj: Any, *keys: str, default: Any = None) -> Any:
    """Safely navigate nested dicts."""
    for key in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(key, default)
        if obj is None:
            return default
    return obj


def extract_user(user_obj: Optional[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    """Normalize a Jira user object to a simple dict."""
    if not user_obj:
        return None
    return {
        "key": user_obj.get("key", user_obj.get("accountId", "")),
        "name": user_obj.get("displayName", user_obj.get("name", "Unknown")),
        "email": user_obj.get("emailAddress", ""),
        "avatar": (user_obj.get("avatarUrls") or {}).get("48x48", ""),
    }


def extract_version(v: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": v.get("id", ""),
        "name": v.get("name", ""),
        "description": v.get("description", ""),
        "released": v.get("released", False),
        "releaseDate": v.get("releaseDate", ""),
        "archived": v.get("archived", False),
    }


def extract_component(c: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": c.get("id", ""),
        "name": c.get("name", ""),
        "description": c.get("description", ""),
        "lead": extract_user(c.get("lead")),
    }


def extract_sprint_from_field(sprint_field: Any) -> Optional[Dict[str, Any]]:
    """
    Extract sprint info from a customfield value.
    Jira Server returns sprints as a list of objects or a string representation.
    """
    if not sprint_field:
        return None

    # If it's a list, take the last (most recent active) sprint
    if isinstance(sprint_field, list) and sprint_field:
        sprint_field = sprint_field[-1]

    if isinstance(sprint_field, dict):
        return {
            "id": str(sprint_field.get("id", "")),
            "name": sprint_field.get("name", ""),
            "state": sprint_field.get("state", ""),
            "startDate": sprint_field.get("startDate", ""),
            "endDate": sprint_field.get("endDate", ""),
            "completeDate": sprint_field.get("completeDate", ""),
            "boardId": str(sprint_field.get("boardId", "")),
            "goal": sprint_field.get("goal", ""),
        }

    # Some Jira Server versions return a string like:
    # "com.atlassian.greenhopper...Sprint@abc[id=1,name=Sprint 1,...]"
    if isinstance(sprint_field, str):
        name_match = re.search(r"name=([^,\]]+)", sprint_field)
        state_match = re.search(r"state=([^,\]]+)", sprint_field)
        id_match = re.search(r"id=([^,\]]+)", sprint_field)
        return {
            "id": id_match.group(1) if id_match else "",
            "name": name_match.group(1) if name_match else sprint_field,
            "state": state_match.group(1) if state_match else "",
            "startDate": "",
            "endDate": "",
            "completeDate": "",
            "boardId": "",
            "goal": "",
        }

    return None


def find_sprint_custom_field(fields_meta: Dict[str, Any]) -> Optional[str]:
    """Find the custom field ID used for Sprint in this Jira instance."""
    for field_id, meta in fields_meta.items():
        name = meta.get("name", "").lower() if isinstance(meta, dict) else ""
        if name == "sprint" and field_id.startswith("customfield_"):
            return field_id
    return None


def find_epic_link_field(fields_meta: Dict[str, Any]) -> Optional[str]:
    """Find the custom field ID used for Epic Link."""
    for field_id, meta in fields_meta.items():
        name = meta.get("name", "").lower() if isinstance(meta, dict) else ""
        if name in ("epic link", "epic") and field_id.startswith("customfield_"):
            return field_id
    return None


def find_story_points_field(fields_meta: Dict[str, Any]) -> Optional[str]:
    """Find the custom field ID used for Story Points."""
    for field_id, meta in fields_meta.items():
        name = meta.get("name", "").lower() if isinstance(meta, dict) else ""
        if name in ("story points", "story point estimate", "points") and field_id.startswith("customfield_"):
            return field_id
    return None


class Extractor:
    """
    Orchestrates the full extraction of a Jira project into a structured dict.
    """

    def __init__(self, client: JiraClient, attachment_handler: AttachmentHandler, config: dict):
        self.client = client
        self.attachment_handler = attachment_handler
        self.config = config

        extraction_cfg = config.get("extraction", {})
        self.mode = extraction_cfg.get("mode", "full").lower()
        self.selective_fields: Dict[str, Any] = extraction_cfg.get("fields", {})

        opts = config.get("options", {})
        self.include_watchers: bool = opts.get("include_watchers", False)
        self.include_worklogs: bool = opts.get("include_worklogs", True)

        # Populated during extraction
        self._sprint_field_id: Optional[str] = None
        self._epic_link_field_id: Optional[str] = None
        self._story_points_field_id: Optional[str] = None
        self._all_fields_meta: Dict[str, Any] = {}

    def get_fields_for_query(self) -> Optional[List[str]]:
        """
        Return list of field IDs to pass to JQL search.
        Returns None for full extraction (fetches *all fields).
        """
        if self.mode == "full":
            return None  # *all

        standard: Set[str] = set(self.selective_fields.get("standard", []))
        custom: Set[str] = set(self.selective_fields.get("custom", []))
        all_fields: Set[str] = standard | custom | MANDATORY_FIELDS

        if self._sprint_field_id:
            all_fields.add(self._sprint_field_id)
        if self._epic_link_field_id:
            all_fields.add(self._epic_link_field_id)
        if self._story_points_field_id:
            all_fields.add(self._story_points_field_id)

        return list(all_fields)

    def _load_fields_meta(self) -> None:
        """Load all field metadata and identify sprint/epic/story-points field IDs."""
        try:
            fields_list = self.client.get_all_fields()
            self._all_fields_meta = {
                f["id"]: {
                    "name": f.get("name", ""),
                    "schema": f.get("schema", {}),
                    "custom": f.get("custom", False),
                }
                for f in fields_list
            }
            self._sprint_field_id = find_sprint_custom_field(self._all_fields_meta)
            self._epic_link_field_id = find_epic_link_field(self._all_fields_meta)
            self._story_points_field_id = find_story_points_field(self._all_fields_meta)
            logger.debug(f"Sprint field: {self._sprint_field_id}")
            logger.debug(f"Epic Link field: {self._epic_link_field_id}")
            logger.debug(f"Story Points field: {self._story_points_field_id}")
        except Exception as e:
            logger.warning(f"Could not load field metadata: {e}")

    def extract_project(self, project_key: str) -> Dict[str, Any]:
        """
        Full extraction pipeline for one project.
        Returns a structured dict ready for HTML generation.
        """
        logger.info(f"Starting extraction for project: {project_key}")

        self._load_fields_meta()

        project_meta = self.client.get_project(project_key)
        versions = self.client.get_project_versions(project_key)
        components = self.client.get_project_components(project_key)

        # Boards and sprints
        sprints_by_id: Dict[str, Dict[str, Any]] = {}
        boards = self.client.get_boards_for_project(project_key)
        for board in boards:
            board_sprints = self.client.get_sprints_for_board(board["id"])
            for s in board_sprints:
                sprints_by_id[str(s["id"])] = {
                    "id": str(s.get("id", "")),
                    "name": s.get("name", ""),
                    "state": s.get("state", ""),
                    "startDate": s.get("startDate", ""),
                    "endDate": s.get("endDate", ""),
                    "completeDate": s.get("completeDate", ""),
                    "goal": s.get("goal", ""),
                }

        # Fetch all issues via JQL
        jql = f'project = "{project_key}" ORDER BY issuetype ASC, created ASC'
        fields_to_fetch = self.get_fields_for_query()

        raw_issues = list(tqdm(
            self.client.search_issues(jql, fields=fields_to_fetch),
            desc=f"  Fetching issues [{project_key}]",
            unit="issue",
        ))
        logger.info(f"  Retrieved {len(raw_issues)} issues for {project_key}")

        # Process each issue
        processed_issues: Dict[str, Dict[str, Any]] = {}
        for raw in tqdm(raw_issues, desc=f"  Processing issues [{project_key}]", unit="issue"):
            issue = self._process_issue(raw, sprints_by_id)
            processed_issues[issue["key"]] = issue

        # Build hierarchy and indexes
        hierarchy = self._build_hierarchy(processed_issues)
        issues_by_type = self._group_by(processed_issues, "issuetype_name")
        issues_by_status = self._group_by(processed_issues, "status_name")
        issues_by_component = self._group_by_multi(processed_issues, "component_names")
        issues_by_version = self._group_by_multi(processed_issues, "fix_version_names")
        issues_by_sprint = self._group_by(processed_issues, "sprint_name")

        return {
            "project": {
                "key": project_key,
                "id": project_meta.get("id", ""),
                "name": project_meta.get("name", ""),
                "description": project_meta.get("description", ""),
                "lead": extract_user(project_meta.get("lead")),
                "url": project_meta.get("self", ""),
                "avatar_url": safe_get(project_meta, "avatarUrls", "48x48", default=""),
                "issue_types": [
                    {
                        "id": it.get("id"),
                        "name": it.get("name"),
                        "description": it.get("description", ""),
                        "subtask": it.get("subtask", False),
                    }
                    for it in project_meta.get("issueTypes", [])
                ],
            },
            "versions": [extract_version(v) for v in versions],
            "components": [extract_component(c) for c in components],
            "sprints": list(sprints_by_id.values()),
            "issues": processed_issues,
            "hierarchy": hierarchy,
            "issues_by_type": issues_by_type,
            "issues_by_status": issues_by_status,
            "issues_by_component": issues_by_component,
            "issues_by_version": issues_by_version,
            "issues_by_sprint": issues_by_sprint,
            "stats": {
                "total_issues": len(processed_issues),
                "total_comments": sum(len(i.get("comments", [])) for i in processed_issues.values()),
                "total_attachments": sum(len(i.get("attachments", [])) for i in processed_issues.values()),
                "issue_type_counts": {k: len(v) for k, v in issues_by_type.items()},
                "status_counts": {k: len(v) for k, v in issues_by_status.items()},
            },
        }

    def _process_issue(self, raw: Dict[str, Any], sprints_by_id: Dict[str, Any]) -> Dict[str, Any]:
        """Transform a raw Jira API issue into a normalized dict."""
        fields: Dict[str, Any] = raw.get("fields", {})
        rendered: Dict[str, Any] = raw.get("renderedFields", {})
        key: str = raw.get("key", "")

        # Sprint detection
        sprint_info = None
        if self._sprint_field_id:
            sprint_raw = fields.get(self._sprint_field_id)
            sprint_info = extract_sprint_from_field(sprint_raw)
        sprint_name = sprint_info.get("name", "") if sprint_info else ""

        # Story points
        story_points = None
        if self._story_points_field_id:
            story_points = fields.get(self._story_points_field_id)

        # Epic link
        epic_link = None
        if self._epic_link_field_id:
            epic_link = fields.get(self._epic_link_field_id)

        # Components
        component_names = [c.get("name", "") for c in (fields.get("components") or [])]

        # Fix versions
        fix_version_names = [v.get("name", "") for v in (fields.get("fixVersions") or [])]

        # Affects versions
        affects_version_names = [v.get("name", "") for v in (fields.get("versions") or [])]

        # Labels
        labels = fields.get("labels", []) or []

        # Parent
        parent_key = None
        parent_summary = None
        parent_raw = fields.get("parent")
        if parent_raw:
            parent_key = parent_raw.get("key", "")
            parent_summary = safe_get(parent_raw, "fields", "summary", default="")

        # Sub-tasks
        subtask_keys = [s.get("key", "") for s in (fields.get("subtasks") or [])]

        # Issue links
        issue_links = []
        for link in (fields.get("issuelinks") or []):
            link_type = safe_get(link, "type", "name", default="")
            inward = safe_get(link, "type", "inward", default="")
            outward = safe_get(link, "type", "outward", default="")
            if link.get("inwardIssue"):
                linked_issue = link["inwardIssue"]
                issue_links.append({
                    "type": link_type,
                    "direction": "inward",
                    "label": inward,
                    "key": linked_issue.get("key", ""),
                    "summary": safe_get(linked_issue, "fields", "summary", default=""),
                    "status": safe_get(linked_issue, "fields", "status", "name", default=""),
                    "issuetype": safe_get(linked_issue, "fields", "issuetype", "name", default=""),
                })
            if link.get("outwardIssue"):
                linked_issue = link["outwardIssue"]
                issue_links.append({
                    "type": link_type,
                    "direction": "outward",
                    "label": outward,
                    "key": linked_issue.get("key", ""),
                    "summary": safe_get(linked_issue, "fields", "summary", default=""),
                    "status": safe_get(linked_issue, "fields", "status", "name", default=""),
                    "issuetype": safe_get(linked_issue, "fields", "issuetype", "name", default=""),
                })

        # Attachments
        raw_attachments = fields.get("attachment") or []
        attachments = self.attachment_handler.process_attachments(raw_attachments)

        # Comments — prefer renderedFields for HTML, fallback to raw body
        raw_comments = (fields.get("comment") or {}).get("comments", [])
        comments = []
        for c in raw_comments:
            comments.append({
                "id": c.get("id", ""),
                "author": extract_user(c.get("author")),
                "body_html": c.get("renderedBody", "") or c.get("body", ""),
                "body_raw": c.get("body", ""),
                "created": c.get("created", ""),
                "updated": c.get("updated", ""),
            })

        # Work logs
        worklogs: List[Dict[str, Any]] = []
        if self.include_worklogs:
            try:
                raw_worklogs = self.client.get_issue_worklogs(key)
                for wl in raw_worklogs:
                    worklogs.append({
                        "author": extract_user(wl.get("author")),
                        "comment": wl.get("comment", ""),
                        "started": wl.get("started", ""),
                        "timeSpent": wl.get("timeSpent", ""),
                        "timeSpentSeconds": wl.get("timeSpentSeconds", 0),
                    })
            except Exception as e:
                logger.debug(f"Could not fetch worklogs for {key}: {e}")

        # Watchers
        watchers: List[Dict[str, Any]] = []
        if self.include_watchers:
            try:
                watchers = [extract_user(w) for w in self.client.get_issue_watchers(key) if w]  # type: ignore[misc]
            except Exception as e:
                logger.debug(f"Could not fetch watchers for {key}: {e}")

        # Time tracking
        time_tracking = fields.get("timetracking") or {}

        # Changelog / history
        changelog_entries = []
        changelog = raw.get("changelog", {})
        for history in (changelog.get("histories") or []):
            entry = {
                "author": extract_user(history.get("author")),
                "created": history.get("created", ""),
                "items": [],
            }
            for item in (history.get("items") or []):
                entry["items"].append({
                    "field": item.get("field", ""),
                    "fieldtype": item.get("fieldtype", ""),
                    "from": item.get("fromString", ""),
                    "to": item.get("toString", ""),
                })
            if entry["items"]:
                changelog_entries.append(entry)

        # Collect all remaining custom fields (full mode)
        custom_fields: Dict[str, Any] = {}
        for field_id, value in fields.items():
            if not field_id.startswith("customfield_"):
                continue
            # Skip already-handled custom fields
            if field_id in (self._sprint_field_id, self._epic_link_field_id, self._story_points_field_id):
                continue
            if value is None:
                continue
            field_meta = self._all_fields_meta.get(field_id, {})
            field_name = field_meta.get("name", field_id) if isinstance(field_meta, dict) else field_id
            custom_fields[field_id] = {
                "id": field_id,
                "name": field_name,
                "value": value,
            }

        return {
            "id": raw.get("id", ""),
            "key": key,
            "url": raw.get("self", ""),
            "summary": fields.get("summary", ""),
            "description_raw": fields.get("description", "") or "",
            "description_html": rendered.get("description", "") or fields.get("description", "") or "",
            "issuetype_name": safe_get(fields, "issuetype", "name", default=""),
            "issuetype_icon": safe_get(fields, "issuetype", "iconUrl", default=""),
            "issuetype_subtask": safe_get(fields, "issuetype", "subtask", default=False),
            "status_name": safe_get(fields, "status", "name", default=""),
            "status_category": safe_get(fields, "status", "statusCategory", "name", default=""),
            "status_color": safe_get(fields, "status", "statusCategory", "colorName", default=""),
            "priority_name": safe_get(fields, "priority", "name", default=""),
            "priority_icon": safe_get(fields, "priority", "iconUrl", default=""),
            "assignee": extract_user(fields.get("assignee")),
            "reporter": extract_user(fields.get("reporter")),
            "created": fields.get("created", ""),
            "updated": fields.get("updated", ""),
            "duedate": fields.get("duedate", ""),
            "resolutiondate": fields.get("resolutiondate", ""),
            "resolution": safe_get(fields, "resolution", "name", default=""),
            "environment": fields.get("environment", ""),
            "labels": labels,
            "component_names": component_names,
            "fix_version_names": fix_version_names,
            "affects_version_names": affects_version_names,
            "parent_key": parent_key,
            "parent_summary": parent_summary,
            "subtask_keys": subtask_keys,
            "epic_link": epic_link,
            "sprint": sprint_info,
            "sprint_name": sprint_name,
            "story_points": story_points,
            "time_tracking": {
                "original": time_tracking.get("originalEstimate", ""),
                "remaining": time_tracking.get("remainingEstimate", ""),
                "spent": time_tracking.get("timeSpent", ""),
            },
            "issue_links": issue_links,
            "attachments": attachments,
            "comments": comments,
            "worklogs": worklogs,
            "watchers": watchers,
            "changelog": changelog_entries,
            "custom_fields": custom_fields,
        }

    def _build_hierarchy(self, issues: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Build a hierarchical tree structure:
        Epics → Stories/Tasks/Bugs → Sub-tasks
        Also handles Epic Link relationships.
        """
        epics: Dict[str, Dict[str, Any]] = {}
        non_epics: Dict[str, Dict[str, Any]] = {}
        subtasks: Dict[str, Dict[str, Any]] = {}

        for key, issue in issues.items():
            itype = issue.get("issuetype_name", "").lower()
            if itype == "epic":
                epics[key] = {"issue": issue, "children": []}
            elif issue.get("issuetype_subtask"):
                subtasks[key] = {"issue": issue}
            else:
                non_epics[key] = {"issue": issue, "subtasks": []}

        # Attach sub-tasks to their parents
        for key, node in subtasks.items():
            issue = node["issue"]
            parent_key = issue.get("parent_key")
            if parent_key and parent_key in non_epics:
                non_epics[parent_key]["subtasks"].append(key)
            elif parent_key and parent_key in epics:
                # Sub-task directly under an epic (uncommon but possible)
                epics[parent_key]["children"].append(key)

        # Attach non-epics to their epics via epic_link or parent_key
        orphans: List[str] = []
        for key, node in non_epics.items():
            issue = node["issue"]
            epic_key = issue.get("epic_link") or issue.get("parent_key")
            if epic_key and epic_key in epics:
                epics[epic_key]["children"].append(key)
            else:
                orphans.append(key)

        return {
            "epics": epics,
            "non_epics": non_epics,
            "subtasks": subtasks,
            "orphans": orphans,
        }

    def _group_by(
        self,
        issues: Dict[str, Dict[str, Any]],
        field: str,
    ) -> Dict[str, List[str]]:
        """Group issue keys by the value of a single-value field."""
        groups: Dict[str, List[str]] = {}
        for key, issue in issues.items():
            value = str(issue.get(field, "") or "")
            if not value:
                value = "None"
            groups.setdefault(value, []).append(key)
        return groups

    def _group_by_multi(
        self,
        issues: Dict[str, Dict[str, Any]],
        field: str,
    ) -> Dict[str, List[str]]:
        """Group issue keys by the values of a list field (multi-value)."""
        groups: Dict[str, List[str]] = {}
        for key, issue in issues.items():
            values: List[str] = issue.get(field, []) or []
            if not values:
                groups.setdefault("None", []).append(key)
            else:
                for value in values:
                    groups.setdefault(str(value), []).append(key)
        return groups
