"""
chm_builder.py
--------------
Generates a Microsoft Compiled HTML Help (.chm) file from extracted Jira data.

How CHM works:
  1. A folder of individual HTML files (one per issue) + a CSS/image folder
  2. A Table of Contents file (.hhc) — XML describing the TOC tree
  3. An Index file (.hhk) — XML listing all keywords
  4. A Project file (.hhp) — master config listing all files
  5. HTML Help Compiler (hhc.exe) compiles everything into one .chm file

Requirements:
  - HTML Help Workshop must be installed (free from Microsoft)
  - Default path: C:\\Program Files (x86)\\HTML Help Workshop\\hhc.exe
  - Only generates CHM on Windows (hhc.exe is Windows-only)
"""

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "template")

# Default paths to HTML Help Compiler on Windows
HHC_SEARCH_PATHS = [
    r"C:\Program Files (x86)\HTML Help Workshop\hhc.exe",
    r"C:\Program Files\HTML Help Workshop\hhc.exe",
    r"C:\Windows\hhc.exe",
]


def find_hhc() -> Optional[str]:
    """Find hhc.exe on this machine. Returns path or None."""
    for path in HHC_SEARCH_PATHS:
        if os.path.exists(path):
            return path
    # Also try PATH
    hhc = shutil.which("hhc")
    if hhc:
        return hhc
    return None


def hhc_available() -> bool:
    """Return True if HTML Help Compiler is available."""
    return find_hhc() is not None


def _safe_filename(key: str) -> str:
    """Convert issue key to safe filename (e.g. PROJ-123 -> PROJ-123.html)."""
    return re.sub(r"[^\w\-]", "_", key) + ".html"


def _escape_xml(s: str) -> str:
    """Escape a string for embedding in XML/HTML attributes."""
    if not s:
        return ""
    # Use explicit character sequences to avoid formatter issues
    amp = chr(38) + "amp;"
    lt  = chr(38) + "lt;"
    gt  = chr(38) + "gt;"
    quot = chr(38) + "quot;"
    return s.replace("&", amp).replace("<", lt).replace(">", gt).replace('"', quot)


def build_hhc(project_data: Dict[str, Any]) -> str:
    """
    Build the Table of Contents (.hhc) XML content.
    Structure: Project Overview → Epics → Stories/Tasks → Sub-tasks
                                → By Status
                                → By Component
                                → By Version
    """
    issues = project_data.get("issues", {})
    hierarchy = project_data.get("hierarchy", {})
    project = project_data["project"]

    def item(name: str, filename: str, indent: int = 0) -> str:
        pad = "    " * indent
        return (
            f'{pad}<LI><OBJECT type="text/sitemap">\n'
            f'{pad}  <param name="Name" value="{_escape_xml(name)}">\n'
            f'{pad}  <param name="Local" value="{_escape_xml(filename)}">\n'
            f'{pad}</OBJECT>\n'
        )

    lines = [
        '<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML//EN">',
        '<HTML><HEAD></HEAD><BODY>',
        '<UL>',
        item(f"{project['key']} — {project['name']}", "index.html"),
        '<UL>',
    ]

    # Epics section
    epics = hierarchy.get("epics", {})
    non_epics = hierarchy.get("non_epics", {})
    orphans = hierarchy.get("orphans", [])
    subtasks = hierarchy.get("subtasks", {})

    if epics:
        lines.append('  <LI><OBJECT type="text/sitemap">')
        lines.append('    <param name="Name" value="Epics">')
        lines.append('  </OBJECT>')
        lines.append('  <UL>')
        for epic_key, epic_node in epics.items():
            epic = issues.get(epic_key, {})
            name = f"{epic_key}: {epic.get('summary', '')[:50]}"
            lines.append(item(name, _safe_filename(epic_key), indent=2))
            children = epic_node.get("children", [])
            if children:
                lines.append('    <UL>')
                for child_key in children:
                    child = issues.get(child_key, {})
                    cname = f"{child_key}: {child.get('summary', '')[:50]}"
                    lines.append(item(cname, _safe_filename(child_key), indent=3))
                    child_subtasks = non_epics.get(child_key, {}).get("subtasks", [])
                    if child_subtasks:
                        lines.append('      <UL>')
                        for sk in child_subtasks:
                            sub = issues.get(sk, {})
                            sname = f"{sk}: {sub.get('summary', '')[:40]}"
                            lines.append(item(sname, _safe_filename(sk), indent=4))
                        lines.append('      </UL>')
                lines.append('    </UL>')
        lines.append('  </UL>')

    # Orphans (issues not in any epic)
    if orphans:
        lines.append('  <LI><OBJECT type="text/sitemap">')
        lines.append('    <param name="Name" value="Unassigned to Epic">')
        lines.append('  </OBJECT>')
        lines.append('  <UL>')
        for key in sorted(orphans):
            issue = issues.get(key, {})
            name = f"{key}: {issue.get('summary', '')[:50]}"
            lines.append(item(name, _safe_filename(key), indent=2))
        lines.append('  </UL>')

    # All issues (flat alphabetical)
    lines.append('  <LI><OBJECT type="text/sitemap">')
    lines.append('    <param name="Name" value="All Issues">')
    lines.append('  </OBJECT>')
    lines.append('  <UL>')
    for key in sorted(issues.keys()):
        issue = issues[key]
        name = f"{key}: {issue.get('summary', '')[:50]}"
        lines.append(item(name, _safe_filename(key), indent=2))
    lines.append('  </UL>')

    lines.append('</UL>')
    lines.append('</UL>')
    lines.append('</BODY></HTML>')
    return "\n".join(lines)


def build_hhk(issues: Dict[str, Any]) -> str:
    """Build the Index (.hhk) XML with issue keys and summaries as keywords."""
    lines = [
        '<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML//EN">',
        '<HTML><HEAD></HEAD><BODY>',
        '<UL>',
    ]
    for key in sorted(issues.keys()):
        issue = issues[key]
        summary = issue.get("summary", "")
        lines.append(f'  <LI><OBJECT type="text/sitemap">')
        lines.append(f'    <param name="Name" value="{_escape_xml(key)}: {_escape_xml(summary[:60])}">')
        lines.append(f'    <param name="Local" value="{_escape_xml(_safe_filename(key))}">')
        lines.append(f'  </OBJECT>')
    lines.append('</UL>')
    lines.append('</BODY></HTML>')
    return "\n".join(lines)


def build_hhp(project_key: str, project_name: str, issue_files: List[str]) -> str:
    """Build the HHP project file."""
    files_section = "\n".join(issue_files + ["index.html"])
    return f"""[OPTIONS]
Compiled file={project_key}_jiradump.chm
Contents file=toc.hhc
Index file=index.hhk
Default topic=index.html
Title={project_name} JiraDump
Language=0x409 English (United States)
Full-text search=Yes
Default Window=main

[WINDOWS]
main="{project_name} JiraDump","toc.hhc","index.hhk","index.html","index.html",,,,,0x2520,,0x387e,,,,,,,,0

[FILES]
{files_section}
"""


def build_index_page(project_data: Dict[str, Any], generated_at: str) -> str:
    """Build the CHM home/index page."""
    project = project_data["project"]
    stats = project_data.get("stats", {})
    issues = project_data.get("issues", {})

    # Build issue type counts
    type_counts: Dict[str, int] = {}
    status_counts: Dict[str, int] = {}
    for issue in issues.values():
        t = issue.get("issuetype_name", "Unknown")
        s = issue.get("status_name", "Unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
        status_counts[s] = status_counts.get(s, 0) + 1

    type_rows = "".join(
        f"<tr><td>{t}</td><td>{c}</td></tr>"
        for t, c in sorted(type_counts.items(), key=lambda x: -x[1])
    )
    status_rows = "".join(
        f"<tr><td>{s}</td><td>{c}</td></tr>"
        for s, c in sorted(status_counts.items(), key=lambda x: -x[1])
    )

    lead_name = (project.get("lead") or {}).get("name", "—")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{_escape_xml(project['name'])} — JiraDump</title>
<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; color: #172b4d; margin: 0; padding: 20px; background: #fff; }}
h1 {{ font-size: 1.3rem; color: #0052cc; margin: 0 0 4px; }}
.subtitle {{ color: #6b778c; font-size: 0.85rem; margin-bottom: 20px; }}
.stats-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; }}
.stat-box {{ background: #f4f5f7; border: 1px solid #dfe1e6; border-radius: 4px; padding: 12px; text-align: center; }}
.stat-num {{ font-size: 1.6rem; font-weight: 800; color: #0052cc; }}
.stat-lbl {{ font-size: 0.75rem; color: #6b778c; margin-top: 2px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; margin-bottom: 16px; }}
th {{ background: #f4f5f7; text-align: left; padding: 6px 10px; border-bottom: 2px solid #dfe1e6; }}
td {{ padding: 5px 10px; border-bottom: 1px solid #dfe1e6; }}
h2 {{ font-size: 0.9rem; text-transform: uppercase; letter-spacing: 0.06em; color: #6b778c; margin: 16px 0 8px; }}
</style>
</head>
<body>
<h1>📚 {_escape_xml(project['name'])}</h1>
<div class="subtitle">Project Key: <strong>{_escape_xml(project['key'])}</strong> &nbsp;·&nbsp; Generated: {_escape_xml(generated_at)}</div>
{"<p style='margin-bottom:16px;font-size:0.875rem;'>" + _escape_xml(project.get('description','')) + "</p>" if project.get('description') else ''}

<div class="stats-grid">
  <div class="stat-box"><div class="stat-num">{stats.get('total_issues',0)}</div><div class="stat-lbl">Issues</div></div>
  <div class="stat-box"><div class="stat-num">{stats.get('total_comments',0)}</div><div class="stat-lbl">Comments</div></div>
  <div class="stat-box"><div class="stat-num">{stats.get('total_attachments',0)}</div><div class="stat-lbl">Attachments</div></div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
<div>
<h2>Issues by Type</h2>
<table><tr><th>Type</th><th>Count</th></tr>{type_rows}</table>
</div>
<div>
<h2>Issues by Status</h2>
<table><tr><th>Status</th><th>Count</th></tr>{status_rows}</table>
</div>
</div>

<h2>Project Details</h2>
<table>
<tr><td><strong>Lead</strong></td><td>{_escape_xml(lead_name)}</td></tr>
<tr><td><strong>Generated</strong></td><td>{_escape_xml(generated_at)}</td></tr>
</table>

<p style="font-size:0.8rem;color:#97a0af;margin-top:20px;">
Use the Table of Contents panel on the left to browse issues, or use the Search tab to find specific issues.
</p>
</body>
</html>"""


class CHMBuilder:
    """
    Builds a CHM (Compiled HTML Help) file from extracted Jira project data.
    Requires HTML Help Workshop (hhc.exe) to be installed on Windows.
    """

    def __init__(self, config: dict):
        self.config = config
        opts = config.get("options", {})
        self.output_dir = opts.get("output_dir", "./output")
        os.makedirs(self.output_dir, exist_ok=True)

        # Set up Jinja2 for issue pages
        self.env = Environment(
            loader=FileSystemLoader(TEMPLATE_DIR),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        # Import date filter from html_builder
        from .html_builder import format_date, format_date_short
        self.env.filters["format_date"] = format_date
        self.env.filters["format_date_short"] = format_date_short

    def build(self, project_data: Dict[str, Any]) -> str:
        """
        Build a .chm file for the given project data.
        Returns path to the generated .chm file (or .zip fallback if hhc not available).
        """
        project_key = project_data["project"]["key"]
        project_name = project_data["project"]["name"]
        issues = project_data.get("issues", {})
        generated_at = datetime.now().strftime("%d %b %Y %H:%M:%S")

        logger.info(f"Building CHM for project: {project_key} ({len(issues)} issues)")

        # Work in a temp directory
        with tempfile.TemporaryDirectory(prefix="jira2chm_") as work_dir:
            issue_template = self.env.get_template("chm_issue.html")
            issue_files: List[str] = []

            # Write index page
            index_html = build_index_page(project_data, generated_at)
            with open(os.path.join(work_dir, "index.html"), "w", encoding="utf-8") as f:
                f.write(index_html)

            # Write one HTML file per issue
            logger.info(f"  Writing {len(issues)} issue pages…")
            for issue_key, issue in issues.items():
                filename = _safe_filename(issue_key)
                html_content = issue_template.render(issue=issue)
                filepath = os.path.join(work_dir, filename)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(html_content)
                issue_files.append(filename)

            # Write TOC, Index, Project files
            toc_content = build_hhc(project_data)
            with open(os.path.join(work_dir, "toc.hhc"), "w", encoding="utf-8") as f:
                f.write(toc_content)

            hhk_content = build_hhk(issues)
            with open(os.path.join(work_dir, "index.hhk"), "w", encoding="utf-8") as f:
                f.write(hhk_content)

            safe_key = re.sub(r"[^\w\-]", "_", project_key)
            hhp_content = build_hhp(project_key, project_name, sorted(issue_files))
            hhp_path = os.path.join(work_dir, f"{safe_key}.hhp")
            with open(hhp_path, "w", encoding="utf-8") as f:
                f.write(hhp_content)

            chm_filename = f"{safe_key}_jiradump.chm"
            chm_output_path = os.path.join(self.output_dir, chm_filename)

            # Try to compile with hhc.exe
            hhc_path = find_hhc()
            if hhc_path:
                logger.info(f"  Compiling CHM with: {hhc_path}")
                try:
                    result = subprocess.run(
                        [hhc_path, hhp_path],
                        capture_output=True,
                        text=True,
                        timeout=300,
                        cwd=work_dir,
                    )
                    # hhc.exe returns 1 on success (non-standard)
                    compiled_chm = os.path.join(work_dir, chm_filename)
                    if os.path.exists(compiled_chm):
                        shutil.copy2(compiled_chm, chm_output_path)
                        size_mb = os.path.getsize(chm_output_path) / 1024 / 1024
                        logger.info(f"  CHM compiled: {chm_output_path} ({size_mb:.2f} MB)")
                        return chm_output_path
                    else:
                        logger.warning(f"  hhc.exe ran but no .chm produced. Falling back to ZIP.")
                        logger.debug(f"  hhc stdout: {result.stdout}")
                        logger.debug(f"  hhc stderr: {result.stderr}")
                except Exception as e:
                    logger.warning(f"  CHM compilation failed ({e}). Falling back to ZIP.")
            else:
                logger.warning(
                    "  HTML Help Workshop (hhc.exe) not found. "
                    "Generating ZIP of HTML files instead.\n"
                    "  Install HTML Help Workshop from: "
                    "https://learn.microsoft.com/en-us/previous-versions/windows/desktop/htmlhelp/microsoft-html-help-downloads"
                )

            # Fallback: ZIP the work directory (hhc not available or failed)
            zip_filename = f"{safe_key}_jiradump_chm_source.zip"
            zip_base = os.path.join(self.output_dir, zip_filename.replace(".zip", ""))
            shutil.make_archive(zip_base, "zip", work_dir)
            zip_path = zip_base + ".zip"
            size_mb = os.path.getsize(zip_path) / 1024 / 1024
            logger.info(
                f"  ZIP created: {zip_path} ({size_mb:.2f} MB)\n"
                f"  To compile to CHM: install HTML Help Workshop and run:\n"
                f"  hhc.exe \"{safe_key}.hhp\""
            )
            return zip_path
