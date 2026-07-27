"""
app.py
------
Flask web UI for the Jira → HTML Knowledge Base tool.

Run with:
    python app.py

Then open: http://localhost:5000
"""

import json
import logging
import os
import sys
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import yaml
from flask import (
    Flask, flash, jsonify, redirect, render_template,
    request, send_file, session, url_for,
)

# ── App setup ────────────────────────────────────────────────
app = Flask(
    __name__,
    template_folder="web/templates",
    static_folder="web/static",
)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "jira2html-dev-secret-change-in-prod")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

CONFIG_PATH = "config.yaml"

# ── In-memory job store ──────────────────────────────────────
# Holds running / completed export jobs keyed by job_id
_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()


# ── Helpers ──────────────────────────────────────────────────
def load_config() -> dict:
    """Load config.yaml, returning defaults if not found."""
    defaults: dict = {
        "jira": {
            "base_url": "https://your-jira.company.com",
            "auth_method": "token",
            "username": "your-username",
            "token": "your-personal-access-token",
            "password": "",
            "verify_ssl": True,
            "projects": [],
        },
        "options": {
            "embed_attachments": True,
            "max_attachment_size_mb": 10,
            "output_dir": "./output",
            "page_size": 100,
            "attachment_workers": 3,
            "include_watchers": False,
            "include_worklogs": True,
        },
        "extraction": {
            "mode": "full",
            "fields": {"standard": [], "custom": []},
        },
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            # Deep merge loaded over defaults
            for section in ("jira", "options", "extraction"):
                if section in loaded:
                    defaults[section].update(loaded[section])
            return defaults
        except Exception as e:
            logger.warning(f"Could not load config.yaml: {e}")
    return defaults


def save_config(cfg: dict) -> None:
    """Save config dict to config.yaml."""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)
    except Exception as e:
        logger.error(f"Could not save config.yaml: {e}")


def build_jira_client(cfg: dict):
    """Build a JiraClient from config dict."""
    from src.jira_client import JiraClient
    return JiraClient(cfg)


def human_file_size(path: str) -> str:
    """Return human-readable file size."""
    try:
        size = os.path.getsize(path)
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / 1024 / 1024:.2f} MB"
    except Exception:
        return ""


# ── Routes ────────────────────────────────────────────────────

@app.route("/")
def index():
    """Step 1 — Connection setup."""
    config = load_config()
    return render_template("index.html", active_step=1, config=config)


@app.route("/connect", methods=["POST"])
def connect():
    """Handle Step 1 form submission — save credentials and redirect to Step 2."""
    config = load_config()

    base_url = request.form.get("base_url", "").rstrip("/")
    auth_method = request.form.get("auth_method", "token")
    username = request.form.get("username", "")
    token = request.form.get("token", "")
    password = request.form.get("password", "")
    verify_ssl = "verify_ssl" in request.form

    if not base_url:
        flash("Jira base URL is required.", "danger")
        return redirect(url_for("index"))
    if not username:
        flash("Username is required.", "danger")
        return redirect(url_for("index"))

    # Update config
    config["jira"]["base_url"] = base_url
    config["jira"]["auth_method"] = auth_method
    config["jira"]["username"] = username
    config["jira"]["verify_ssl"] = verify_ssl
    if auth_method == "token" and token:
        config["jira"]["token"] = token
    elif auth_method == "basic" and password:
        config["jira"]["password"] = password

    # Test connection
    try:
        client = build_jira_client(config)
        user = client.test_connection()
        session["connected"] = True
        session["jira_url"] = base_url
        session["display_name"] = user.get("displayName", username)
        save_config(config)
        flash(f"✅ Connected as {user.get('displayName', username)}", "success")
        return redirect(url_for("projects"))
    except Exception as e:
        flash(f"Connection failed: {str(e)}", "danger")
        return redirect(url_for("index"))


@app.route("/projects")
def projects():
    """Step 2 — Project and field selection (projects loaded via AJAX)."""
    if not session.get("connected"):
        flash("Please connect to Jira first.", "warning")
        return redirect(url_for("index"))
    # Projects and fields are loaded client-side via /api/projects and /api/fields
    return render_template("projects.html", active_step=2)


@app.route("/save-projects", methods=["POST"])
def save_projects():
    """Handle Step 2 form submission."""
    selected = request.form.getlist("projects")
    if not selected:
        flash("Please select at least one project.", "warning")
        return redirect(url_for("projects"))

    extraction_mode = request.form.get("extraction_mode", "full")
    std_fields = request.form.getlist("std_fields")
    custom_fields_sel = request.form.getlist("custom_fields")

    session["selected_projects"] = selected
    session["extraction_mode"] = extraction_mode
    session["selected_std_fields"] = std_fields
    session["selected_custom_fields"] = custom_fields_sel

    # Persist to config
    config = load_config()
    config["extraction"]["mode"] = extraction_mode
    config["extraction"]["fields"]["standard"] = std_fields
    config["extraction"]["fields"]["custom"] = custom_fields_sel
    save_config(config)

    return redirect(url_for("options"))


@app.route("/options")
def options():
    """Step 3 — Export options."""
    if not session.get("connected"):
        flash("Please connect to Jira first.", "warning")
        return redirect(url_for("index"))
    if not session.get("selected_projects"):
        flash("Please select at least one project.", "warning")
        return redirect(url_for("projects"))

    config = load_config()
    return render_template(
        "options.html",
        active_step=3,
        selected_projects=session["selected_projects"],
        extraction_mode=session.get("extraction_mode", "full"),
        options=config["options"],
    )


@app.route("/save-options", methods=["POST"])
def save_options():
    """Handle Step 3 form submission and redirect to export."""
    config = load_config()

    config["options"]["embed_attachments"] = "embed_attachments" in request.form
    config["options"]["max_attachment_size_mb"] = int(request.form.get("max_attachment_size_mb") or 10)
    config["options"]["attachment_workers"] = int(request.form.get("attachment_workers") or 3)
    config["options"]["include_worklogs"] = "include_worklogs" in request.form
    config["options"]["include_watchers"] = "include_watchers" in request.form
    config["options"]["page_size"] = int(request.form.get("page_size", 100))
    output_dir = request.form.get("output_dir", "./output").strip() or "./output"
    config["options"]["output_dir"] = output_dir
    session["output_dir"] = output_dir

    save_config(config)
    return redirect(url_for("export"))


@app.route("/export")
def export():
    """Step 4 — Export progress page."""
    if not session.get("connected"):
        flash("Please connect to Jira first.", "warning")
        return redirect(url_for("index"))
    if not session.get("selected_projects"):
        flash("Please select at least one project.", "warning")
        return redirect(url_for("projects"))

    config = load_config()
    return render_template(
        "export.html",
        active_step=4,
        selected_projects=session["selected_projects"],
        extraction_mode=session.get("extraction_mode", "full"),
        output_dir=config["options"].get("output_dir", "./output"),
    )


# ── API Endpoints ─────────────────────────────────────────────

@app.route("/api/projects")
def api_get_projects():
    """Fetch project list from Jira. Called via AJAX from projects page."""
    if not session.get("connected"):
        return jsonify({"error": "Not connected"}), 401
    config = load_config()
    try:
        client = build_jira_client(config)
        projects = client.get_projects()
        # Normalize to safe minimal structure
        result = []
        for p in projects:
            result.append({
                "key": p.get("key", ""),
                "name": p.get("name", ""),
                "projectTypeKey": p.get("projectTypeKey", "software"),
                "description": (p.get("description") or "")[:120],
            })
        return jsonify({"success": True, "projects": result, "count": len(result)})
    except Exception as e:
        logger.exception("Failed to fetch projects")
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/fields")
def api_get_fields():
    """Fetch all Jira fields. Called via AJAX only when Selective mode is chosen."""
    if not session.get("connected"):
        return jsonify({"error": "Not connected"}), 401
    config = load_config()
    try:
        client = build_jira_client(config)
        all_fields = client.get_all_fields()
        standard = sorted(
            [{"id": f.get("id",""), "name": f.get("name",""),
              "schema": f.get("schema",{}), "custom": False}
             for f in all_fields if not f.get("custom", False)],
            key=lambda x: x["name"]
        )
        custom = sorted(
            [{"id": f.get("id",""), "name": f.get("name",""),
              "schema": f.get("schema",{}), "custom": True}
             for f in all_fields if f.get("custom", False)],
            key=lambda x: x["name"]
        )
        return jsonify({"success": True, "standard_fields": standard, "custom_fields": custom})
    except Exception as e:
        logger.exception("Failed to fetch fields")
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/test-connection", methods=["POST"])
def api_test_connection():
    """Test Jira credentials without saving. Returns JSON."""
    data = request.get_json() or {}
    config = load_config()

    cfg = {
        "jira": {
            "base_url": data.get("base_url", "").rstrip("/"),
            "auth_method": data.get("auth_method", "token"),
            "username": data.get("username", ""),
            "token": data.get("token", ""),
            "password": data.get("password", ""),
            "verify_ssl": data.get("verify_ssl", True),
        },
        "options": config.get("options", {}),
    }

    try:
        from src.jira_client import JiraClient, JiraAuthError
        client = JiraClient(cfg)
        user = client.test_connection()
        return jsonify({
            "success": True,
            "display_name": user.get("displayName", user.get("name", "Unknown")),
            "email": user.get("emailAddress", ""),
            "key": user.get("key", user.get("accountId", "")),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/export", methods=["POST"])
def api_start_export():
    """Start an async export job. Returns job_id."""
    data = request.get_json() or {}
    project_keys = data.get("projects", session.get("selected_projects", []))

    if not project_keys:
        return jsonify({"error": "No projects specified"}), 400

    config = load_config()
    job_id = str(uuid.uuid4())[:8]

    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "started_at": datetime.now().isoformat(),
            "finished": False,
            "logs": [],
            "log_cursor": 0,
            "project_updates": [],
            "output_files": [],
        }

    # Launch background thread
    thread = threading.Thread(
        target=_run_export_job,
        args=(job_id, project_keys, config),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/export/status/<job_id>")
def api_export_status(job_id: str):
    """Poll export job status. Returns new logs and project updates since last poll."""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    cursor = int(request.args.get("cursor", job.get("log_cursor", 0)))
    all_logs = job.get("logs", [])
    new_logs = all_logs[cursor:]

    response = {
        "finished": job.get("finished", False),
        "new_logs": new_logs,
        "log_cursor": len(all_logs),
        "project_updates": job.get("project_updates", []),
        "output_files": job.get("output_files", []),
    }
    # Clear consumed project_updates
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["project_updates"] = []
            _jobs[job_id]["log_cursor"] = len(all_logs)

    return jsonify(response)


@app.route("/download/<path:filename>")
def download_file(filename: str):
    """Serve a generated HTML file for download."""
    config = load_config()
    output_dir = os.path.abspath(config["options"].get("output_dir", "./output"))
    safe_name = os.path.basename(filename)
    full_path = os.path.join(output_dir, safe_name)
    if not os.path.exists(full_path):
        return "File not found", 404
    return send_file(full_path, as_attachment=True, download_name=safe_name)


# ── Background export worker ─────────────────────────────────

def _job_log(job_id: str, message: str) -> None:
    """Append a log line to a job."""
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {message}"
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["logs"].append(line)


def _job_update(job_id: str, update: dict) -> None:
    """Append a project status update to a job."""
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["project_updates"].append(update)


def _run_export_job(job_id: str, project_keys: List[str], config: dict) -> None:
    """
    Background thread: runs extraction + HTML build for all project keys.
    Posts progress updates to the job store for polling by the UI.
    """
    try:
        from src.jira_client import JiraClient
        from src.attachment_handler import AttachmentHandler
        from src.extractor import Extractor
        from src.html_builder import HTMLBuilder

        _job_log(job_id, f"Connecting to Jira: {config['jira']['base_url']}")
        client = JiraClient(config)

        try:
            user = client.test_connection()
            _job_log(job_id, f"Authenticated as: {user.get('displayName', '?')}")
        except Exception as e:
            _job_log(job_id, f"ERROR: Authentication failed: {e}")
            with _jobs_lock:
                _jobs[job_id]["finished"] = True
            return

        attachment_handler = AttachmentHandler(client, config)
        builder = HTMLBuilder(config)

        total = len(project_keys)
        for idx, project_key in enumerate(project_keys, 1):
            project_key = project_key.strip().upper()
            _job_log(job_id, f"[{idx}/{total}] Starting export: {project_key}")
            _job_update(job_id, {
                "key": project_key,
                "status": "running",
                "progress": 10,
                "label": "Connecting and loading field metadata…",
            })

            try:
                # Create a new extractor for each project (resets field cache)
                extractor = Extractor(client, attachment_handler, config)

                _job_update(job_id, {"key": project_key, "status": "running", "progress": 20,
                                     "label": "Fetching project metadata, sprints, components…"})

                # Extract project
                _job_log(job_id, f"  Fetching issues for {project_key}…")
                project_data = extractor.extract_project(project_key)
                stats = project_data.get("stats", {})
                project_name = project_data["project"]["name"]

                _job_update(job_id, {"key": project_key, "status": "running", "progress": 80,
                                     "label": f"Building HTML ({stats.get('total_issues', 0)} issues)…",
                                     "name": project_name})

                _job_log(job_id, f"  Retrieved {stats.get('total_issues', 0)} issues, "
                                 f"{stats.get('total_comments', 0)} comments, "
                                 f"{stats.get('total_attachments', 0)} attachments")

                # Build HTML
                _job_log(job_id, f"  Building self-contained HTML…")
                output_path = builder.build(project_data)
                file_size = human_file_size(output_path)
                output_filename = os.path.basename(output_path)

                _job_log(job_id, f"  ✓ Generated: {output_path} ({file_size})")

                with _jobs_lock:
                    if job_id in _jobs:
                        _jobs[job_id]["output_files"].append(output_path)

                _job_update(job_id, {
                    "key": project_key,
                    "status": "done",
                    "progress": 100,
                    "label": f"Complete — {stats.get('total_issues', 0)} issues exported",
                    "name": project_name,
                    "file": output_filename,
                    "size": file_size,
                })

            except Exception as e:
                _job_log(job_id, f"  ✗ ERROR exporting {project_key}: {e}")
                _job_update(job_id, {
                    "key": project_key,
                    "status": "error",
                    "progress": 100,
                    "label": f"Failed: {str(e)[:80]}",
                })
                logger.exception(f"Export failed for {project_key}")

        _job_log(job_id, f"Export complete. {total} project(s) processed.")

    except Exception as e:
        _job_log(job_id, f"FATAL ERROR: {e}")
        logger.exception("Fatal error in export job")
    finally:
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["finished"] = True


# ── Error handlers ────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template("base.html",
                           active_step=1,
                           config=load_config(),
                           error="Page not found."), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("base.html",
                           active_step=1,
                           config=load_config(),
                           error=f"Server error: {e}"), 500


# ── Entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("=" * 55)
    print("  📚 Jira2HTML — Web UI")
    print("  Open in your browser: http://localhost:5000")
    print("=" * 55)
    print()
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        threaded=True,
    )
