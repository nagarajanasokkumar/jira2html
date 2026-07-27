# Jira Knowledge Base — End User Guide

## Table of Contents

1. [Getting Started](#getting-started)
2. [Opening the Knowledge Base](#opening-the-knowledge-base)
3. [Navigating the Interface](#navigating-the-interface)
4. [Using Search](#using-search)
5. [Filtering Issues](#filtering-issues)
6. [Reading Issue Details](#reading-issue-details)
7. [Working with Attachments](#working-with-attachments)
8. [Views: Sprints, Components, Versions](#views-sprints-components-versions)
9. [Dark Mode & Accessibility](#dark-mode--accessibility)
10. [Printing & Saving](#printing--saving)
11. [Keyboard Shortcuts](#keyboard-shortcuts)
12. [FAQ](#faq)

---

## 1. Getting Started

The Jira Knowledge Base is a **single HTML file** that contains all the issues, comments, attachments, and relationships from your Jira project. It works completely offline — no internet connection or Jira access needed.

**What you need:**
- The HTML file (e.g., `MYPROJECT_knowledge_base.html`)
- Any modern web browser: **Chrome**, **Firefox**, **Microsoft Edge**, or **Safari**

**What you do NOT need:**
- Internet access
- Jira login or account
- Any software installation
- A web server

---

## 2. Opening the Knowledge Base

### Method 1 — Double-click (Easiest)

Simply **double-click** the `.html` file. It will open in your default web browser.

### Method 2 — Drag and Drop

Drag the HTML file into an open browser window.

### Method 3 — File Menu

In your browser, go to **File → Open File** (or press `Ctrl+O` / `Cmd+O`) and browse to the HTML file.

### First Load Time

Large files (with many embedded images) may take **5–15 seconds** to fully load. You will see the page appear progressively. This is normal — everything is self-contained in one file.

> 💡 **Tip:** Once opened, you can bookmark the file in your browser for quick access later.

---

## 3. Navigating the Interface

The knowledge base has three main areas:

```
┌─────────────────────────────────────────────────────────┐
│  📚 Knowledge Base    [PROJ]  🔍 Search…      🌙         │  ← Header
├──────────────┬──────────────────────────────────────────┤
│              │                                          │
│   Sidebar    │           Main Content                   │
│              │                                          │
│ 📊 Overview  │   Issues / Issue Detail / Overview       │
│ 🏷️ By Type   │                                          │
│ 🔄 By Status │                                          │
│ ⚡ Epics     │                                          │
│ 🏃 Sprints   │                                          │
│ 🧩 Components│                                          │
│ 🏷️ Versions  │                                          │
│              │                                          │
└──────────────┴──────────────────────────────────────────┘
```

### The Header Bar

- **📚 Knowledge Base** — your project name/logo; click to go to overview
- **[PROJ]** — the project key badge
- **Search box** — type here to search all issues
- **🌙 button** — toggle dark/light mode

### The Sidebar

The sidebar organises all issues into different navigation views. Click any item to switch views:

| Section | What It Shows |
|---|---|
| 🏠 **Project Overview** | Summary statistics and charts |
| 📋 **All Issues** | Every issue in the project |
| 🏷️ **By Type** | Issues grouped by type (Epic, Story, Bug, Task…) |
| 🔄 **By Status** | Issues grouped by workflow status |
| ⚡ **Epics** | Individual epics with their child issues |
| 🏃 **Sprints** | Issues organised by sprint |
| 🧩 **Components** | Issues organised by component |
| 🏷️ **Versions** | Issues organised by fix version/release |

**Collapsing sidebar sections:** Click the section header to collapse or expand it.

**Mobile / narrow screens:** Tap the ☰ hamburger button in the top-left to show/hide the sidebar.

---

## 4. Using Search

Search is the fastest way to find issues. It searches across:
- Issue keys (e.g., `PROJ-123`)
- Summaries / titles
- Descriptions
- Comments
- Labels
- Components
- Assignee / reporter names
- Sprint names

### How to Search

1. Click the search box in the header (or press **Ctrl+K** / **Cmd+K**)
2. Start typing your query
3. Results appear instantly as you type
4. Click any result to open that issue

### Search Tips

| Query | What It Finds |
|---|---|
| `PROJ-42` | Issue with that exact key |
| `login error` | Issues mentioning "login" and "error" |
| `john.doe` | Issues assigned to or commented by John Doe |
| `sprint 5` | Issues in Sprint 5 |
| `authentication bug` | Issues about authentication bugs |

### Clearing Search

- Click the **✕** button in the search box
- Press **Escape**
- Delete the text and press Enter

---

## 5. Filtering Issues

The **filter bar** appears above the issue list when you're in any list view (All Issues, By Type, By Status, etc.).

### Available Filters

| Filter | What It Does |
|---|---|
| **Type** | Show only Bugs, Stories, Tasks, Epics, etc. |
| **Status** | Show only issues with a specific status (e.g., "In Progress") |
| **Priority** | Show only High, Medium, Low priority issues |
| **Sprint** | Show only issues from a specific sprint |
| **Component** | Show only issues belonging to a component |

### Using Filters

1. Click a filter dropdown and select a value
2. The issue list updates immediately — showing only matching issues
3. The issue count at the right of the filter bar updates (e.g., "23 issues")
4. Combine multiple filters — they work together (AND logic)
5. Click **Reset** to clear all filters

> 💡 **Example:** Select Type = "Bug" and Status = "Open" to see all open bugs.

---

## 6. Reading Issue Details

Click any issue card to open the **issue detail view**.

### Issue Detail Layout

```
┌─────────────────────────────────────────────────────────┐
│  🐛  PROJ-42                               [← Back]     │
│     Login page crashes on mobile                        │
├──────────────────────────────────────┬──────────────────┤
│  Description                         │ Status: In Prog  │
│  ─────────────                       │ Type:   🐛 Bug   │
│  When opening the login page on...   │ Priority: High   │
│                                      │ Assignee: J. Doe │
│  Attachments (2)                     │ Reporter: M. Lee │
│  ─────────────                       │ Created: 12 Jan  │
│  [screenshot.png] [log.txt ⬇]       │ Updated: 15 Jan  │
│                                      │ Sprint: Sprint 3 │
│  Linked Issues                       │                  │
│  ─────────────                       │ Labels           │
│  blocks → PROJ-50                    │ [mobile] [login] │
│                                      │                  │
│  Comments (3)                        │ Components       │
│  ─────────────                       │ [Frontend]       │
│  👤 John: "Fixed in build 2.3"       │                  │
│  👤 Mary: "Verified on iOS"          │ Custom Fields    │
│                                      │ Story Points: 3  │
└──────────────────────────────────────┴──────────────────┘
```

### What You Can See

**Left column (main content):**
- **Description** — the full issue description with formatting, tables, and code blocks
- **Attachments** — images shown as thumbnails; other files as download buttons
- **Linked Issues** — issues this one blocks, is blocked by, relates to, duplicates, etc.
- **Sub-tasks** — child issues (click any to open them)
- **Comments** — full comment thread with authors and timestamps
- **Work Log** — time tracking entries (if recorded in Jira)
- **History** — changelog showing when fields were changed and by whom

**Right column (metadata):**
- Status, type, priority, assignee, reporter
- Dates (created, updated, due date)
- Resolution and resolution date
- Story points
- Sprint, parent issue
- Time tracking (estimated, remaining, spent)
- Labels
- Components
- Fix versions
- Custom fields

### Navigating Between Issues

- **Click linked issues** — opens the linked issue directly
- **Click sub-tasks** — opens the sub-task
- **Click parent key** — opens the parent issue
- **← Back button** — returns to the previous list view
- **Browser Back button** — also works

---

## 7. Working with Attachments

### Images

Images are embedded directly in the HTML and displayed as thumbnails in the Attachments section.

- **Click any image thumbnail** to open it in a full-screen lightbox viewer
- **Click outside the image** or the **✕ button** to close the lightbox
- Images in descriptions are also zoomable — click them to enlarge

### Other Files (PDFs, Word docs, Excel, etc.)

Non-image files appear as download buttons with a file icon:
```
📄 ⬇ quarterly-report.pdf     (2.3 MB)
📄 ⬇ test-results.xlsx        (450 KB)
```

- **Click the filename** to download the file
- Files are saved to your browser's default download folder
- Files are embedded in the HTML as Base64 data — no external server needed

### Skipped Attachments

If an attachment shows with reduced opacity and a note like "(File size 25.1 MB exceeds limit)", it was not embedded because it exceeded the size limit set during export. Contact your administrator to re-export with a higher size limit if needed.

---

## 8. Views: Sprints, Components, Versions

### Sprint View

Click a sprint name in the sidebar to see all issues in that sprint.

Each sprint shows:
- Sprint name, state (Active 🟢 / Closed ⬜ / Future 🔵)
- Sprint goal (if set)
- Start and end dates
- All issues in that sprint

### Component View

Click a component name to see all issues assigned to that component.

### Version/Release View

Click a version name to see all issues with that fix version.

Each version shows:
- Version name and description
- Whether it has been released (✅ Released / 🔖 Unreleased)
- Release date (if set)

### Epic View

Click an epic in the **⚡ Epics** sidebar section to open the epic issue detail directly.

The epic detail shows all its child issues in the "Sub-tasks" / linked issues section.

### Unassigned to Epic

Issues that don't belong to any epic are listed under **📭 Unassigned to Epic** in the Epics section.

---

## 9. Dark Mode & Accessibility

### Switching Dark/Light Mode

Click the **🌙** button in the top-right of the header to switch between light and dark themes.

- **🌙** = currently in Light mode (click to switch to Dark)
- **☀️** = currently in Dark mode (click to switch to Light)

Your preference is **saved in your browser** and remembered next time you open the file.

### Accessibility Features

- All images have descriptive alt text
- Buttons have aria labels for screen readers
- Colour contrast meets WCAG AA standards in both light and dark modes
- Keyboard navigation is fully supported
- Font sizes are relative and scale with browser zoom

### Adjusting Text Size

Use your browser's built-in zoom:
- **Zoom in:** `Ctrl+` (Windows/Linux) or `Cmd+` (Mac)
- **Zoom out:** `Ctrl-` (Windows/Linux) or `Cmd-` (Mac)
- **Reset zoom:** `Ctrl+0` (Windows/Linux) or `Cmd+0` (Mac)

---

## 10. Printing & Saving

### Printing an Issue

1. Open the issue detail view
2. Press **Ctrl+P** (Windows/Linux) or **Cmd+P** (Mac)
3. The sidebar and filter bar are automatically hidden in print view
4. Choose your printer or "Save as PDF"

### Saving a Copy

The HTML file is already self-contained. To save/share:
- **Copy the file** to another location, USB drive, or email it
- **Save from browser:** File → Save As → choose a location (saves the same self-contained file)

### Exporting to PDF

For a permanent PDF record of the entire knowledge base:
1. In your browser, go to **File → Print** (or `Ctrl+P`)
2. Set destination to "Save as PDF"
3. Set layout to **Portrait** or **Landscape** depending on content
4. Click Save

> 💡 For best results when printing issues, open the specific issue first, then print.

---

## 11. Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+K` / `Cmd+K` | Open search |
| `Escape` | Close search / close lightbox |
| `Enter` (in search) | Open first search result |
| `Ctrl+P` / `Cmd+P` | Print current view |
| `Ctrl++` / `Cmd++` | Zoom in |
| `Ctrl+-` / `Cmd+-` | Zoom out |
| `Ctrl+0` / `Cmd+0` | Reset zoom |
| `Backspace` / `Alt+←` | Browser back |
| `F5` | Reload page (resets to overview) |

---

## 12. FAQ

**Q: Do I need an internet connection to use the knowledge base?**
A: No. The HTML file is entirely self-contained. Everything — CSS, JavaScript, images, and data — is embedded. It works completely offline.

---

**Q: Do I need a Jira account or login?**
A: No. The knowledge base is a static HTML file. There is no connection to Jira. Your Jira account is only needed during the initial export by the administrator.

---

**Q: How do I find a specific issue by its key (e.g., PROJ-123)?**
A: Type `PROJ-123` in the search box at the top. It will appear instantly as the top result.

---

**Q: The search doesn't find something I know is in Jira. Why?**
A: The search index is built from the exported data. Check whether:
1. The issue was in Jira at the time of export
2. The word appears in the summary, description, or comments (not in a field that wasn't extracted)
3. There are no typos in your search query

---

**Q: An attachment won't download or shows as "skipped". Why?**
A: Large attachments may have been excluded during export to keep the file size manageable. Contact your administrator to re-export with a higher `max_attachment_size_mb` setting.

---

**Q: The page is slow or unresponsive when I open the file. Why?**
A: Very large files (50+ MB, usually with many embedded images) can take 10–30 seconds to fully load. Once loaded, navigation is instant. Try using a more recent browser version for better performance.

---

**Q: I see "No description provided." for some issues. Why?**
A: Those issues had no description text entered in Jira.

---

**Q: Issue links show a key but clicking doesn't open anything. Why?**
A: The linked issue may belong to a different project that was not included in this export. Each HTML file covers one project.

---

**Q: How current is the data?**
A: The data reflects Jira's state at the time the export was run. The export timestamp is shown in the footer of the sidebar. Contact your administrator if you need a more recent export.

---

**Q: Can I edit issues in the knowledge base?**
A: No. The HTML knowledge base is a read-only archive. It is a snapshot of your Jira data at the time of export. To make changes to issues, you would have needed to do so in Jira before the decommission.

---

**Q: Can I search across multiple projects at once?**
A: Each HTML file covers one Jira project. To search across projects, open each project's HTML file in a separate browser tab and search individually.

---

**Q: The sidebar is missing (Sprints / Components / Versions sections not showing). Why?**
A: Those sections only appear if the project had sprints, components, or versions respectively. If a project had no sprints configured in Jira, the Sprints section will not be shown.

---

**Q: Images in descriptions don't display. Why?**
A: This can happen if the images in Jira descriptions were externally hosted (not attached to the issue). Only Jira-attached images are embedded. Externally hosted images require internet access to load.

---

*For administrator/deployment questions, see [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md).*
