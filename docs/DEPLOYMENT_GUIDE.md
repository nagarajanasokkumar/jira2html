# Jira → HTML Knowledge Base — Deployment & Migration Guide

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Web UI (Recommended)](#web-ui-recommended)
6. [Running via CLI](#running-via-cli)
7. [Selective Field Extraction](#selective-field-extraction)
8. [Output Files](#output-files)
9. [Migration Checklist](#migration-checklist)
10. [Troubleshooting](#troubleshooting)
11. [Advanced Options](#advanced-options)

---

## 1. Overview

`jira2html` is a Python CLI tool that connects to your Jira Server/Data Center instance via REST API and exports entire projects into **single, self-contained HTML files**. Each HTML file:

- Requires **no web server** — open it directly in any modern browser
- Has **no external dependencies** — CSS, JavaScript, and data are all embedded
- Contains **full-text search** across all issues, comments, descriptions, and metadata
- Preserves **all data relationships** — Epic → Story → Sub-task hierarchy, issue links, sprints, components, versions
- Embeds **images as Base64** inline; provides download links for other file types
- Works **offline** permanently as a knowledge base archive

---

## 2. Prerequisites

| Requirement | Minimum Version | Check Command |
|---|---|---|
| Python | 3.8+ | `python --version` |
| pip | 20+ | `pip --version` |
| Network access | — | Must reach your Jira instance |
| Jira account | — | Must have read access to target projects |

### Jira Account Permissions Required

Your Jira account needs the following project-level permissions:
- **Browse Projects** — to read issue data
- **View Read-Only Workflow** — to read statuses
- **View Voters and Watchers** *(optional)* — only if `include_watchers: true`

---

## 3. Installation

### Step 1 — Clone or Download the Project

```bash
# If you have the zip file, extract it to a folder
# Or if using git:
git clone <repository-url> jira2html
cd jira2html
```

### Step 2 — Create a Python Virtual Environment (Recommended)

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 3 — Install Dependencies

```bash
pip install -r requirements.txt
```

Expected output: pip installs `requests`, `pyyaml`, `jinja2`, `tqdm`, `Pillow`, `markdownify`.

### Step 4 — Verify Installation

```bash
python jira2html.py --help
```

You should see the usage/help output.

---

## 4. Configuration

All settings live in `config.yaml`. Copy the provided file and edit it:

```bash
# The file is already present — just edit it:
notepad config.yaml        # Windows
nano config.yaml           # Linux/macOS
```

### Minimum Required Settings

```yaml
jira:
  base_url: "https://jira.yourcompany.com"   # No trailing slash
  auth_method: "token"                        # "token" or "basic"
  username: "john.doe"
  token: "your-personal-access-token"
```

### Generating a Personal Access Token (PAT)

1. Log in to Jira
2. Click your avatar → **Profile**
3. In the left panel, click **Personal Access Tokens**
4. Click **Create token**
5. Give it a name (e.g., "jira2html export"), set expiry if required
6. Copy the token and paste it into `config.yaml`

> **Note:** PAT authentication is available in Jira Server 8.14+ and Jira Data Center 8.14+. For older versions, use `auth_method: "basic"` with your username and password.

### Specifying Projects

Option A — In `config.yaml`:
```yaml
jira:
  projects: ["PROJ1", "PROJ2", "MYAPP"]
```

Option B — On the command line (overrides config):
```bash
python jira2html.py --project PROJ1 --project PROJ2
```

Option C — Export everything:
```bash
python jira2html.py --all-projects
```

### SSL Certificate Issues

If your Jira uses a self-signed certificate:
```yaml
jira:
  verify_ssl: false
```

> ⚠️ Only disable SSL verification on trusted internal networks.

---

## 5. Web UI (Recommended)

The web UI provides a user-friendly 4-step wizard interface — no command-line knowledge needed.

### Starting the Web UI

```bash
# Install dependencies (includes Flask)
pip install -r requirements.txt

# Start the web server
python app.py
```

Then open **http://localhost:5000** in your browser.

### Step 1 — Connect to Jira

![Step 1](https://placeholder)

- Enter your **Jira base URL** (e.g., `https://jira.yourcompany.com`)
- Choose authentication: **Personal Access Token** (recommended) or **Basic** (username + password)
- Click **🔍 Test Connection** to verify credentials live — a green confirmation appears without leaving the page
- Click **Connect & Continue →** to save settings and proceed

### Step 2 — Select Projects

- All accessible Jira projects are displayed as a **clickable card grid**
- Check one or more projects to export
- Use **Select All** for bulk selection
- Choose extraction mode:
  - **Full Extract** — all fields, comments, attachments, sprints (recommended for migration)
  - **Selective** — a table of every standard and custom field appears; tick only what you need
- Use the **filter box** to search through hundreds of custom fields by name or ID

### Step 3 — Export Options

Configure per-export settings without editing any YAML file:

| Setting | Description |
|---|---|
| Embed attachments | Toggle on/off. Enabled = images inline, files as download links |
| Max attachment size | Slider + number input (1–100 MB). Files above limit are skipped |
| Attachment workers | 1–5 concurrent downloads. More = faster, but may hit rate limits |
| Include work logs | Toggle time-tracking entries |
| Include watchers | Toggle watcher lists (adds API calls per issue) |
| API page size | 25/50/100 issues per request |
| Output directory | Where to save the HTML files |

### Step 4 — Export & Download

- Export starts automatically when you arrive at Step 4
- **Live progress bars** for each project update every 1.5 seconds
- **Dark log console** shows real-time extraction messages
- On completion, **⬇ Download** buttons appear for each generated HTML file
- Files are downloaded directly through the browser — no file manager needed

### Accessing the Web UI Remotely

By default the web server binds to `0.0.0.0:5000`, so it is accessible from other machines on the same network at `http://YOUR-PC-IP:5000`. To restrict to localhost only:

```python
# In app.py, change:
app.run(host="127.0.0.1", port=5000, ...)
```

### Changing the Port

```bash
# Set environment variable before running
set FLASK_RUN_PORT=8080     # Windows
export FLASK_RUN_PORT=8080  # macOS/Linux
python app.py
```

Or edit the `app.run(port=5000)` line at the bottom of `app.py`.

---

## 6. Running via CLI

### Basic Commands

```bash
# Export a single project (full extraction — all fields)
python jira2html.py --project MYPROJECT

# Export multiple projects
python jira2html.py --project PROJ1 --project PROJ2

# Export all accessible projects
python jira2html.py --all-projects

# Export with verbose logging (shows API calls, debug info)
python jira2html.py --project MYPROJECT --verbose

# Save output to a specific directory
python jira2html.py --project MYPROJECT --output C:\exports

# Use a different config file
python jira2html.py --project MYPROJECT --config prod_config.yaml
```

### What Happens During Export

1. **Connect** — Authenticates against your Jira instance
2. **Load fields** — Discovers all field definitions (standard + custom)
3. **Fetch project metadata** — Versions, components, issue types, boards, sprints
4. **Fetch all issues** — Uses JQL with pagination to retrieve every issue
5. **Process issues** — Normalizes fields, extracts hierarchy, links, comments
6. **Download attachments** — Images embedded as Base64, other files as download URIs
7. **Build HTML** — Renders Jinja2 template with all embedded data
8. **Write output** — Saves `PROJECTKEY_knowledge_base.html` to output directory

### Typical Timings

| Project Size | Approx. Time |
|---|---|
| 50 issues, no attachments | ~15 seconds |
| 200 issues, small attachments | ~1–2 minutes |
| 500 issues, many attachments | ~5–10 minutes |

---

## 7. Selective Field Extraction

By default, the tool extracts **all fields** (`mode: full`). For selective extraction:

### Step 1 — Discover Available Fields

```bash
python jira2html.py --list-fields --project MYPROJECT
```

Output example:
```
═══════════════════════════════════════════════════════════════
  Available fields for project: MYPROJECT
═══════════════════════════════════════════════════════════════

STANDARD FIELDS ─────────────────────────────────────────────
  summary                        → Summary                        [string]
  description                    → Description                    [string]
  status                         → Status                         [status]
  ...

CUSTOM FIELDS ────────────────────────────────────────────────
  customfield_10001              → Story Points                   [number]
  customfield_10014              → Epic Link                      [any]
  customfield_10020              → Sprint                         [array]
  ...
```

### Step 2a — Configure in config.yaml

```yaml
extraction:
  mode: "selective"
  fields:
    standard:
      - summary
      - description
      - status
      - issuetype
      - priority
      - assignee
      - reporter
      - created
      - updated
      - labels
      - components
      - fixVersions
      - issuelinks
      - comment
      - attachment
      - parent
      - subtasks
    custom:
      - customfield_10001   # Story Points
      - customfield_10014   # Epic Link
      - customfield_10020   # Sprint
```

Then run:
```bash
python jira2html.py --project MYPROJECT --mode selective
```

### Step 2b — Interactive Selection

```bash
python jira2html.py --project MYPROJECT --interactive
```

The tool will prompt for each field:
```
── Standard Fields ──────────────────────────────────────
  Include 'summary'? [Y/n]:       ← press Enter to include
  Include 'description'? [Y/n]:   ← type 'n' to skip
  ...
── Custom Fields ────────────────────────────────────────
  Include 'Story Points' (customfield_10001)? [y/N]:  ← type 'y' to include
```

---

## 8. Output Files

Generated HTML files are saved to the `output_dir` specified in `config.yaml` (default: `./output`).

**File naming:** `PROJECTKEY_knowledge_base.html`

**Examples:**
```
output/
├── MYAPP_knowledge_base.html       (e.g., 45 MB for 500 issues with attachments)
├── PROJ1_knowledge_base.html
└── PROJ2_knowledge_base.html
```

### File Size Guidance

| Scenario | Approx. File Size |
|---|---|
| 100 issues, no attachments | 1–3 MB |
| 100 issues, images embedded | 5–20 MB |
| 500 issues, full attachments | 20–100 MB |

> Large files (>50 MB) may take a few seconds to open in a browser. This is normal — the browser is parsing the embedded data.

### Distributing the Files

The HTML files are fully self-contained. You can:
- Email them
- Upload to SharePoint/OneDrive
- Store on a shared network drive
- Copy to a USB drive
- Host on any HTTP server

No installation required to view them — just a modern browser (Chrome, Firefox, Edge, Safari).

---

## 9. Migration Checklist

Use this checklist to ensure a complete Jira decommission migration:

### Pre-Migration

- [ ] Identify all Jira projects to be migrated (run `python jira2html.py --all-projects` to list them)
- [ ] Verify your account has **Browse Projects** access to all target projects
- [ ] Test connectivity: `python jira2html.py --list-fields --project TESTPROJECT`
- [ ] Check disk space: estimate ~20 MB per 100 issues with attachments
- [ ] Decide on `max_attachment_size_mb` limit in config.yaml

### During Migration

- [ ] Run a test export on one small project first
- [ ] Open the HTML file and verify it loads correctly
- [ ] Test search functionality (type an issue key or keyword)
- [ ] Click several issues and verify detail view renders correctly
- [ ] Verify attachments open/download correctly
- [ ] Run full export for all projects
- [ ] Record the export date and store it with each HTML file

### Post-Migration

- [ ] Distribute HTML files to all stakeholders
- [ ] Communicate the new file locations to end users (see USER_GUIDE.md)
- [ ] Archive the original HTML files to at least two separate storage locations
- [ ] Verify at least one person from each team can open and search the knowledge base
- [ ] Document where the HTML files are stored (SharePoint, network drive, etc.)
- [ ] Set a reminder to check file accessibility after 6 months

---

## 10. Troubleshooting

### Error: "Authentication failed (401)"

**Cause:** Wrong username, token, or password.

**Fix:**
1. Verify `username` in config.yaml matches your Jira login name (not display name)
2. Re-generate your Personal Access Token — they can expire
3. Try Basic auth: set `auth_method: "basic"` and provide your password

### Error: "Connection failed" / SSL errors

**Cause:** SSL certificate not trusted, or Jira URL is wrong.

**Fix:**
1. Check `base_url` — no trailing slash, correct protocol (`https://`)
2. If using self-signed cert: set `verify_ssl: false`
3. Test connectivity: `curl -k https://your-jira.company.com/rest/api/2/myself`

### Error: "Resource not found (404)" for a project

**Cause:** Project key is wrong or your account lacks Browse access.

**Fix:**
1. Verify project key (case-insensitive but must match exactly, e.g., `MYAPP` not `My App`)
2. Ask a Jira admin to grant your account Browse Projects permission
3. Use `--all-projects` to see which projects you have access to

### Attachments Not Embedded

**Cause:** Files exceed `max_attachment_size_mb` limit.

**Fix:** Increase the limit in config.yaml:
```yaml
options:
  max_attachment_size_mb: 25
```

### HTML File Is Very Slow to Open

**Cause:** Very large Base64-embedded attachments inflating file size.

**Fix:** Reduce attachment size limit or disable attachments:
```yaml
options:
  embed_attachments: false
```

### Python ImportError or ModuleNotFoundError

**Cause:** Dependencies not installed, or wrong virtual environment active.

**Fix:**
```bash
pip install -r requirements.txt
```

### Jira Rate Limiting (429 errors)

**Cause:** Too many API requests in a short time.

**Fix:** The tool automatically retries with exponential backoff. If persistent:
```yaml
options:
  page_size: 50         # Reduce from 100
  attachment_workers: 1  # Sequential downloads
```

---

## 11. Advanced Options

### Running Multiple Configs

Maintain separate config files for different environments:
```bash
python jira2html.py --project MYAPP --config config_prod.yaml
python jira2html.py --project MYAPP --config config_staging.yaml
```

### Automating Periodic Exports

On Windows (Task Scheduler):
```batch
cd C:\path\to\jira2html
venv\Scripts\python.exe jira2html.py --all-projects --output C:\exports
```

On Linux/macOS (cron):
```bash
# Run every Sunday at 2 AM
0 2 * * 0 /path/to/jira2html/venv/bin/python /path/to/jira2html/jira2html.py --all-projects
```

### Excluding Watchers and Worklogs

```yaml
options:
  include_watchers: false
  include_worklogs: false
```

This speeds up extraction significantly for large projects.

### Re-running Exports

Simply run the tool again — it overwrites existing HTML files. There is no incremental/delta mode; each run produces a complete fresh export.

---

*For end-user instructions on using the generated HTML files, see [USER_GUIDE.md](USER_GUIDE.md).*
