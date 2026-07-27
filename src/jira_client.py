"""
jira_client.py
--------------
Authenticated Jira Server/Data Center REST API client.
Handles Basic Auth and Personal Access Token (PAT) auth,
pagination, rate limiting, and all API calls needed for extraction.
"""

import requests
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import List, Dict, Any, Optional, Generator

logger = logging.getLogger(__name__)


class JiraAuthError(Exception):
    pass


class JiraAPIError(Exception):
    pass


class JiraClient:
    """
    Thread-safe Jira REST API v2 client for Server/Data Center.
    Supports Personal Access Token (Bearer) and Basic authentication.
    """

    def __init__(self, config: dict):
        jira_cfg = config.get("jira", {})
        self.base_url = jira_cfg.get("base_url", "").rstrip("/")
        self.auth_method = jira_cfg.get("auth_method", "token").lower()
        self.username = jira_cfg.get("username", "")
        self.token = jira_cfg.get("token", "")
        self.password = jira_cfg.get("password", "")
        self.verify_ssl = jira_cfg.get("verify_ssl", True)

        opts = config.get("options", {})
        self.page_size = opts.get("page_size", 100)

        self.session = self._build_session()
        self.api_base = f"{self.base_url}/rest/api/2"

    def _build_session(self) -> requests.Session:
        session = requests.Session()

        # Configure auth
        if self.auth_method == "token":
            session.headers.update({
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Atlassian-Token": "no-check",
            })
        elif self.auth_method == "basic":
            session.auth = (self.username, self.password)
            session.headers.update({
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Atlassian-Token": "no-check",
            })
        else:
            raise JiraAuthError(f"Unknown auth_method: '{self.auth_method}'. Use 'token' or 'basic'.")

        session.verify = self.verify_ssl

        # Retry strategy for transient failures
        retry = Retry(
            total=5,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        return session

    def test_connection(self) -> Dict[str, Any]:
        """Verify credentials and connectivity. Returns current user info."""
        resp = self.session.get(f"{self.api_base}/myself")
        if resp.status_code == 401:
            raise JiraAuthError(
                "Authentication failed. Check your username/token/password in config.yaml."
            )
        if resp.status_code == 403:
            raise JiraAuthError(
                "Access forbidden. Your account may lack API access permissions."
            )
        self._check_response(resp)
        return resp.json()

    def get_all_fields(self) -> List[Dict[str, Any]]:
        """Fetch all available fields (standard + custom) from Jira."""
        resp = self.session.get(f"{self.api_base}/field")
        self._check_response(resp)
        return resp.json()

    def get_projects(self) -> List[Dict[str, Any]]:
        """Fetch all projects accessible to the authenticated user."""
        projects = []
        start = 0
        while True:
            resp = self.session.get(
                f"{self.api_base}/project",
                params={"startAt": start, "maxResults": self.page_size, "expand": "description,lead"},
            )
            self._check_response(resp)
            data = resp.json()
            # Project list endpoint returns an array directly (not paginated in older Jira)
            if isinstance(data, list):
                projects.extend(data)
                break
            else:
                batch = data.get("values", data.get("projects", []))
                projects.extend(batch)
                if len(batch) < self.page_size:
                    break
                start += self.page_size
        return projects

    def get_project(self, project_key: str) -> Dict[str, Any]:
        """Fetch metadata for a single project."""
        resp = self.session.get(
            f"{self.api_base}/project/{project_key}",
            params={"expand": "description,lead,versions,components,issueTypes"},
        )
        self._check_response(resp)
        return resp.json()

    def get_project_versions(self, project_key: str) -> List[Dict[str, Any]]:
        """Fetch all versions (releases) for a project."""
        resp = self.session.get(f"{self.api_base}/project/{project_key}/versions")
        self._check_response(resp)
        return resp.json()

    def get_project_components(self, project_key: str) -> List[Dict[str, Any]]:
        """Fetch all components for a project."""
        resp = self.session.get(f"{self.api_base}/project/{project_key}/components")
        self._check_response(resp)
        return resp.json()

    def search_issues(
        self,
        jql: str,
        fields: Optional[List[str]] = None,
        expand: Optional[List[str]] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Paginated JQL search. Yields individual issue dicts.
        fields=None fetches all fields (*all).
        """
        fields_param = ",".join(fields) if fields else "*all"
        expand_param = ",".join(expand) if expand else "renderedFields,changelog,names"
        start = 0

        while True:
            params = {
                "jql": jql,
                "startAt": start,
                "maxResults": self.page_size,
                "fields": fields_param,
                "expand": expand_param,
            }
            resp = self.session.get(f"{self.api_base}/search", params=params)
            self._check_response(resp)
            data = resp.json()

            issues = data.get("issues", [])
            total = data.get("total", 0)
            logger.debug(f"Fetched issues {start}–{start + len(issues)} of {total}")

            for issue in issues:
                yield issue

            start += len(issues)
            if start >= total or not issues:
                break

    def get_issue(self, issue_key: str, fields: Optional[List[str]] = None) -> Dict[str, Any]:
        """Fetch a single issue with all details."""
        params = {
            "expand": "renderedFields,changelog,names,transitions",
        }
        if fields:
            params["fields"] = ",".join(fields)
        resp = self.session.get(f"{self.api_base}/issue/{issue_key}", params=params)
        self._check_response(resp)
        return resp.json()

    def get_issue_comments(self, issue_key: str) -> List[Dict[str, Any]]:
        """Fetch all comments for an issue (handles pagination)."""
        comments = []
        start = 0
        while True:
            resp = self.session.get(
                f"{self.api_base}/issue/{issue_key}/comment",
                params={"startAt": start, "maxResults": 100, "expand": "renderedBody"},
            )
            self._check_response(resp)
            data = resp.json()
            batch = data.get("comments", [])
            comments.extend(batch)
            total = data.get("total", 0)
            start += len(batch)
            if start >= total or not batch:
                break
        return comments

    def get_issue_worklogs(self, issue_key: str) -> List[Dict[str, Any]]:
        """Fetch all work log entries for an issue."""
        worklogs = []
        start = 0
        while True:
            resp = self.session.get(
                f"{self.api_base}/issue/{issue_key}/worklog",
                params={"startAt": start, "maxResults": 100},
            )
            self._check_response(resp)
            data = resp.json()
            batch = data.get("worklogs", [])
            worklogs.extend(batch)
            total = data.get("total", 0)
            start += len(batch)
            if start >= total or not batch:
                break
        return worklogs

    def get_issue_watchers(self, issue_key: str) -> List[Dict[str, Any]]:
        """Fetch watchers for an issue."""
        resp = self.session.get(f"{self.api_base}/issue/{issue_key}/watchers")
        self._check_response(resp)
        return resp.json().get("watchers", [])

    def get_attachment_content(self, attachment_url: str) -> bytes:
        """Download raw attachment content bytes."""
        resp = self.session.get(attachment_url, stream=True)
        self._check_response(resp)
        return resp.content

    def get_sprints_for_board(self, board_id: int) -> List[Dict[str, Any]]:
        """Fetch all sprints for an Agile board (requires Jira Software Scrum board)."""
        sprints = []
        start = 0
        while True:
            resp = self.session.get(
                f"{self.base_url}/rest/agile/1.0/board/{board_id}/sprint",
                params={"startAt": start, "maxResults": 50},
            )
            if resp.status_code in (404, 403):
                logger.warning(f"Board {board_id} not accessible or not found — skipping sprints.")
                break
            if resp.status_code == 400:
                # Kanban boards don't support sprints — silently skip
                logger.debug(f"Board {board_id} does not support sprints (likely Kanban) — skipping.")
                break
            self._check_response(resp)
            data = resp.json()
            batch = data.get("values", [])
            sprints.extend(batch)
            if data.get("isLast", True):
                break
            start += len(batch)
        return sprints

    def get_boards_for_project(self, project_key: str) -> List[Dict[str, Any]]:
        """Fetch Agile boards associated with a project."""
        resp = self.session.get(
            f"{self.base_url}/rest/agile/1.0/board",
            params={"projectKeyOrId": project_key, "maxResults": 50},
        )
        if resp.status_code in (404, 403):
            logger.warning(f"No boards accessible for project {project_key}.")
            return []
        self._check_response(resp)
        return resp.json().get("values", [])

    def get_issue_transitions(self, issue_key: str) -> List[Dict[str, Any]]:
        """Fetch available workflow transitions for an issue."""
        resp = self.session.get(f"{self.api_base}/issue/{issue_key}/transitions")
        self._check_response(resp)
        return resp.json().get("transitions", [])

    def _check_response(self, resp: requests.Response) -> None:
        """Raise a descriptive error for non-2xx responses."""
        if resp.status_code == 401:
            raise JiraAuthError(
                "Authentication failed (401). Verify credentials in config.yaml."
            )
        if resp.status_code == 403:
            raise JiraAPIError(
                f"Access forbidden (403) for URL: {resp.url}"
            )
        if resp.status_code == 404:
            raise JiraAPIError(
                f"Resource not found (404): {resp.url}"
            )
        if not resp.ok:
            try:
                err = resp.json()
                messages = err.get("errorMessages", []) or [str(err.get("errors", resp.text))]
                detail = "; ".join(messages)
            except Exception:
                detail = resp.text[:300]
            raise JiraAPIError(
                f"Jira API error {resp.status_code} for {resp.url}: {detail}"
            )
