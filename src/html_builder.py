"""
html_builder.py
---------------
Renders extracted Jira project data into a single self-contained HTML file
using Jinja2 templating. All CSS, JavaScript, and data are embedded inline.
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "template")


def format_date(iso_string: str) -> str:
    """Convert Jira ISO timestamp to a human-readable date."""
    if not iso_string:
        return ""
    try:
        # Jira format: 2023-04-15T10:30:00.000+0530
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y, %H:%M")
    except Exception:
        return iso_string[:10] if len(iso_string) >= 10 else iso_string


def format_date_short(iso_string: str) -> str:
    """Short date format."""
    if not iso_string:
        return ""
    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y")
    except Exception:
        return iso_string[:10] if len(iso_string) >= 10 else iso_string


def user_initials(user: Optional[Dict[str, str]]) -> str:
    """Get initials from a user display name."""
    if not user:
        return "?"
    name = user.get("name", "?")
    parts = name.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[:2].upper() if name else "?"


def status_badge_class(status_color: str, status_name: str) -> str:
    """Map Jira status color to CSS class."""
    color = (status_color or "").lower()
    name = (status_name or "").lower()
    if color in ("green", "medium-gray") or "done" in name or "closed" in name or "resolved" in name:
        return "badge-done"
    if color in ("blue-gray",) or "progress" in name or "review" in name or "testing" in name:
        return "badge-inprogress"
    if color in ("yellow",) or "blocked" in name:
        return "badge-blocked"
    return "badge-todo"


def priority_class(priority: str) -> str:
    """Map priority name to CSS class."""
    p = (priority or "").lower()
    if p in ("highest", "blocker", "critical"):
        return "priority-critical"
    if p in ("high", "major"):
        return "priority-high"
    if p in ("medium", "normal"):
        return "priority-medium"
    if p in ("low", "minor"):
        return "priority-low"
    if p in ("lowest", "trivial"):
        return "priority-lowest"
    return "priority-medium"


def issuetype_icon_char(issuetype: str) -> str:
    """Map issue type name to a Unicode icon character."""
    t = (issuetype or "").lower()
    if "epic" in t:
        return "⚡"
    if "story" in t:
        return "📖"
    if "bug" in t:
        return "🐛"
    if "task" in t:
        return "✅"
    if "sub-task" in t or "subtask" in t:
        return "↳"
    if "improvement" in t or "enhancement" in t:
        return "✨"
    if "new feature" in t or "feature" in t:
        return "🚀"
    return "📋"


def sanitize_anchor(key: str) -> str:
    """Make a safe HTML anchor ID from an issue key."""
    return re.sub(r"[^a-zA-Z0-9_-]", "-", key)


def value_to_str(value: Any) -> str:
    """Convert any custom field value to a display string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(item.get("name", item.get("value", str(item))))
            else:
                parts.append(str(item))
        return ", ".join(parts)
    if isinstance(value, dict):
        return value.get("name", value.get("value", value.get("displayName", str(value))))
    return str(value)


def build_lunr_index(issues: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build a search index as a list of dicts (serialized via tojson in template)."""
    docs = []
    for key, issue in issues.items():
        # Strip HTML tags from rendered fields to get searchable plain text
        comments_text = " ".join(
            re.sub(r"<[^>]+>", " ", c.get("body_html", "") or "")
            for c in issue.get("comments", [])
        )
        description_text = re.sub(
            r"<[^>]+>", " ", issue.get("description_html", "") or ""
        )
        docs.append({
            "id": key,
            "key": key,
            "summary": issue.get("summary", ""),
            "description": description_text[:2000],
            "issuetype": issue.get("issuetype_name", ""),
            "status": issue.get("status_name", ""),
            "priority": issue.get("priority_name", ""),
            "assignee": (issue.get("assignee") or {}).get("name", ""),
            "reporter": (issue.get("reporter") or {}).get("name", ""),
            "labels": " ".join(issue.get("labels", [])),
            "components": " ".join(issue.get("component_names", [])),
            "sprint": issue.get("sprint_name", ""),
            "comments": comments_text[:1000],
        })
    return docs


class HTMLBuilder:
    """
    Renders a project data dict into a single self-contained HTML file.
    """

    def __init__(self, config: dict):
        self.config = config
        opts = config.get("options", {})
        self.output_dir = opts.get("output_dir", "./output")
        os.makedirs(self.output_dir, exist_ok=True)

        # Set up Jinja2 environment
        # NOTE: autoescape is intentionally disabled for the knowledge base template
        # because we embed pre-rendered HTML content (Jira descriptions, comment bodies)
        # directly into JavaScript data blocks. Autoescape would double-encode HTML
        # entities inside JSON strings (e.g. <p> → \u003cp\u003e → <p> in browser).
        self.env = Environment(
            loader=FileSystemLoader(TEMPLATE_DIR),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

        # Register custom filters
        self.env.filters["format_date"] = format_date
        self.env.filters["format_date_short"] = format_date_short
        self.env.filters["user_initials"] = user_initials
        self.env.filters["status_badge_class"] = status_badge_class
        self.env.filters["priority_class"] = priority_class
        self.env.filters["issuetype_icon"] = issuetype_icon_char
        self.env.filters["sanitize_anchor"] = sanitize_anchor
        self.env.filters["value_to_str"] = value_to_str

    def build(self, project_data: Dict[str, Any]) -> str:
        """
        Render a project data dict to HTML and write it to the output directory.
        Returns the path to the generated HTML file.
        """
        project_key = project_data["project"]["key"]
        project_name = project_data["project"]["name"]
        logger.info(f"Building HTML for project: {project_key}")

        # Build Lunr search index
        lunr_docs_json = build_lunr_index(project_data.get("issues", {}))

        # Prepare template context
        context = {
            "project": project_data["project"],
            "versions": project_data.get("versions", []),
            "components": project_data.get("components", []),
            "sprints": project_data.get("sprints", []),
            "issues": project_data.get("issues", {}),
            "hierarchy": project_data.get("hierarchy", {}),
            "issues_by_type": project_data.get("issues_by_type", {}),
            "issues_by_status": project_data.get("issues_by_status", {}),
            "issues_by_component": project_data.get("issues_by_component", {}),
            "issues_by_version": project_data.get("issues_by_version", {}),
            "issues_by_sprint": project_data.get("issues_by_sprint", {}),
            "stats": project_data.get("stats", {}),
            "lunr_docs_json": lunr_docs_json,
            "generated_at": datetime.now().strftime("%d %b %Y %H:%M:%S"),
            "generated_at_iso": datetime.now().isoformat(),
        }

        template = self.env.get_template("base_template.html")
        html_content = template.render(**context)

        # Write output file
        safe_key = re.sub(r"[^\w\-]", "_", project_key)
        output_filename = f"{safe_key}_knowledge_base.html"
        output_path = os.path.join(self.output_dir, output_filename)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        file_size_mb = os.path.getsize(output_path) / 1024 / 1024
        logger.info(f"  Generated: {output_path} ({file_size_mb:.2f} MB)")
        return output_path
