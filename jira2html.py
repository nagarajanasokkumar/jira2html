#!/usr/bin/env python3
"""
jira2html.py
------------
Main CLI entry point for the Jira → Compiled HTML JiraDump tool.

Usage examples:
  python jira2html.py --list-fields --project PROJ1
  python jira2html.py --project PROJ1
  python jira2html.py --project PROJ1 --project PROJ2
  python jira2html.py --all-projects
  python jira2html.py --project PROJ1 --mode selective
  python jira2html.py --project PROJ1 --interactive
  python jira2html.py --project PROJ1 --output ./my-output
  python jira2html.py --project PROJ1 --config custom_config.yaml
"""

import argparse
import logging
import os
import sys
import time
from typing import List, Optional

import yaml

# ── Logging setup ────────────────────────────────────────────────────────────
def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s  %(levelname)-8s  %(message)s"
    datefmt = "%H:%M:%S"
    logging.basicConfig(level=level, format=fmt, datefmt=datefmt)
    # Quieten noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


# ── Config loading ───────────────────────────────────────────────────────────
def load_config(config_path: str) -> dict:
    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        logger.error("Copy config.yaml.example to config.yaml and fill in your Jira credentials.")
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        try:
            cfg = yaml.safe_load(f)
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse config file: {e}")
            sys.exit(1)
    return cfg or {}


def apply_cli_overrides(config: dict, args: argparse.Namespace) -> dict:
    """Apply CLI argument overrides to config."""
    if args.output:
        config.setdefault("options", {})["output_dir"] = args.output
    if args.mode:
        config.setdefault("extraction", {})["mode"] = args.mode
    return config


# ── Field listing ────────────────────────────────────────────────────────────
def cmd_list_fields(client, project_key: str) -> None:
    """Print all available fields for a project."""
    print(f"\n{'═' * 64}")
    print(f"  Available fields for project: {project_key}")
    print(f"{'═' * 64}")

    try:
        fields = client.get_all_fields()
    except Exception as e:
        logger.error(f"Could not fetch fields: {e}")
        sys.exit(1)

    standard_fields = [f for f in fields if not f.get("custom", False)]
    custom_fields = [f for f in fields if f.get("custom", False)]

    print(f"\n{'STANDARD FIELDS':─<60}")
    for f in sorted(standard_fields, key=lambda x: x.get("name", "")):
        fid = f.get("id", "")
        name = f.get("name", "")
        schema = f.get("schema", {})
        ftype = schema.get("type", "") if schema else ""
        print(f"  {fid:<30} → {name:<30} [{ftype}]")

    print(f"\n{'CUSTOM FIELDS':─<60}")
    for f in sorted(custom_fields, key=lambda x: x.get("name", "")):
        fid = f.get("id", "")
        name = f.get("name", "")
        schema = f.get("schema", {})
        ftype = schema.get("type", "") if schema else ""
        print(f"  {fid:<30} → {name:<30} [{ftype}]")

    print(f"\n{'═' * 64}")
    print("Use these IDs in config.yaml under extraction.fields.custom")
    print(f"{'═' * 64}\n")


# ── Interactive field selection ──────────────────────────────────────────────
def cmd_interactive_fields(client, config: dict) -> dict:
    """Interactively ask user which fields to include."""
    print("\n" + "═" * 64)
    print("  Interactive Field Selection")
    print("  Press ENTER to accept a field, type 'n' to skip it.")
    print("═" * 64 + "\n")

    try:
        all_fields = client.get_all_fields()
    except Exception as e:
        logger.error(f"Could not fetch fields: {e}")
        return config

    selected_standard = []
    selected_custom = []

    standard_names = [
        "summary", "description", "status", "issuetype", "priority",
        "assignee", "reporter", "created", "updated", "duedate",
        "resolutiondate", "resolution", "labels", "components",
        "fixVersions", "versions", "environment", "timetracking",
        "issuelinks", "comment", "attachment", "parent", "subtasks",
    ]

    print("── Standard Fields ──────────────────────────────────────────")
    for fname in standard_names:
        resp = input(f"  Include '{fname}'? [Y/n]: ").strip().lower()
        if resp != "n":
            selected_standard.append(fname)

    custom_fields = [f for f in all_fields if f.get("custom", False)]
    if custom_fields:
        print("\n── Custom Fields ────────────────────────────────────────────")
        for f in sorted(custom_fields, key=lambda x: x.get("name", "")):
            fid = f.get("id", "")
            name = f.get("name", "")
            resp = input(f"  Include '{name}' ({fid})? [y/N]: ").strip().lower()
            if resp == "y":
                selected_custom.append(fid)

    config.setdefault("extraction", {})["mode"] = "selective"
    config["extraction"]["fields"] = {
        "standard": selected_standard,
        "custom": selected_custom,
    }

    print(f"\n  Selected {len(selected_standard)} standard + {len(selected_custom)} custom fields.")
    print("  Extraction mode set to 'selective'.\n")
    return config


# ── Project discovery ────────────────────────────────────────────────────────
def resolve_project_keys(client, config: dict, cli_projects: List[str], all_projects: bool) -> List[str]:
    """Determine which project keys to process."""
    if all_projects:
        logger.info("Fetching all accessible projects from Jira…")
        projects = client.get_projects()
        keys = [p["key"] for p in projects]
        logger.info(f"Found {len(keys)} projects: {', '.join(keys)}")
        return keys

    if cli_projects:
        return cli_projects

    cfg_projects = config.get("jira", {}).get("projects", [])
    if cfg_projects:
        return cfg_projects

    # If nothing specified, ask user
    logger.warning("No projects specified. Fetching all accessible projects…")
    projects = client.get_projects()
    keys = [p["key"] for p in projects]
    logger.info(f"Available projects: {', '.join(keys)}")
    return keys


# ── Main pipeline ────────────────────────────────────────────────────────────
def run_extraction(config: dict, project_keys: List[str]) -> List[str]:
    """Run the full extraction and HTML generation pipeline. Returns list of output file paths."""
    from src.jira_client import JiraClient
    from src.attachment_handler import AttachmentHandler
    from src.extractor import Extractor
    from src.html_builder import HTMLBuilder

    client = JiraClient(config)
    attachment_handler = AttachmentHandler(client, config)
    extractor = Extractor(client, attachment_handler, config)
    builder = HTMLBuilder(config)

    output_files = []
    total = len(project_keys)

    for idx, project_key in enumerate(project_keys, 1):
        project_key = project_key.strip().upper()
        logger.info(f"\n[{idx}/{total}] Processing project: {project_key}")
        start_time = time.time()

        try:
            project_data = extractor.extract_project(project_key)
            output_path = builder.build(project_data)
            elapsed = time.time() - start_time
            stats = project_data.get("stats", {})
            logger.info(
                f"  ✓ Completed {project_key} in {elapsed:.1f}s — "
                f"{stats.get('total_issues', 0)} issues, "
                f"{stats.get('total_comments', 0)} comments, "
                f"{stats.get('total_attachments', 0)} attachments"
            )
            logger.info(f"  → Output: {output_path}")
            output_files.append(output_path)
        except Exception as e:
            logger.error(f"  ✗ Failed to process {project_key}: {e}")
            if logging.getLogger().level == logging.DEBUG:
                import traceback
                traceback.print_exc()
            continue

    return output_files


# ── CLI argument parser ──────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jira2html",
        description="Convert Jira Server/Data Center projects to self-contained HTML knowledge bases.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all available fields for a project (run before selective mode)
  python jira2html.py --list-fields --project MYPROJECT

  # Full extract for a single project (default: all fields)
  python jira2html.py --project MYPROJECT

  # Full extract for multiple projects
  python jira2html.py --project PROJ1 --project PROJ2

  # Extract all projects accessible to your account
  python jira2html.py --all-projects

  # Selective mode — uses fields defined in config.yaml
  python jira2html.py --project MYPROJECT --mode selective

  # Interactive field selection (prompts in terminal)
  python jira2html.py --project MYPROJECT --interactive

  # Custom output directory
  python jira2html.py --project MYPROJECT --output ./exports

  # Use a different config file
  python jira2html.py --project MYPROJECT --config prod_config.yaml
        """,
    )

    parser.add_argument(
        "--project", "-p",
        action="append",
        dest="projects",
        metavar="PROJECT_KEY",
        help="Jira project key to export (can be specified multiple times). Overrides config.yaml projects list.",
    )
    parser.add_argument(
        "--all-projects",
        action="store_true",
        help="Export ALL projects accessible to your account.",
    )
    parser.add_argument(
        "--list-fields",
        action="store_true",
        help="List all available fields for the specified project and exit (useful before selective mode).",
    )
    parser.add_argument(
        "--mode",
        choices=["full", "selective"],
        default=None,
        help="Extraction mode: 'full' (all fields) or 'selective' (fields from config.yaml). Overrides config.yaml.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactively choose which fields to extract (sets mode to selective).",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        metavar="DIRECTORY",
        help="Output directory for generated HTML files. Overrides config.yaml output_dir.",
    )
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        metavar="FILE",
        help="Path to configuration YAML file (default: config.yaml).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging.",
    )

    return parser


# ── Entry point ──────────────────────────────────────────────────────────────
def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(args.verbose)

    # Load and apply config
    config = load_config(args.config)
    config = apply_cli_overrides(config, args)

    # Validate Jira URL
    jira_url = config.get("jira", {}).get("base_url", "")
    if not jira_url or "your-jira" in jira_url:
        logger.error("Jira base_url is not configured. Please edit config.yaml.")
        sys.exit(1)

    # Import and connect
    from src.jira_client import JiraClient, JiraAuthError, JiraAPIError

    logger.info(f"Connecting to Jira: {jira_url}")
    client = JiraClient(config)

    try:
        user = client.test_connection()
        logger.info(f"  Authenticated as: {user.get('displayName', user.get('name', '?'))} ({user.get('emailAddress', '')})")
    except JiraAuthError as e:
        logger.error(f"Authentication failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        sys.exit(1)

    # ── --list-fields mode ──────────────────────────────────────
    if args.list_fields:
        project_key = (args.projects or [None])[0]
        if not project_key:
            # Just list fields globally without a specific project
            project_key = "N/A"
        cmd_list_fields(client, project_key)
        sys.exit(0)

    # ── --interactive mode ──────────────────────────────────────
    if args.interactive:
        config = cmd_interactive_fields(client, config)

    # ── Resolve projects ────────────────────────────────────────
    project_keys = resolve_project_keys(
        client,
        config,
        args.projects or [],
        args.all_projects,
    )

    if not project_keys:
        logger.error("No project keys specified or found. Use --project KEY or --all-projects.")
        sys.exit(1)

    logger.info(f"Projects to export: {', '.join(project_keys)}")
    extraction_mode = config.get("extraction", {}).get("mode", "full")
    logger.info(f"Extraction mode: {extraction_mode}")
    output_dir = config.get("options", {}).get("output_dir", "./output")
    logger.info(f"Output directory: {output_dir}")

    # ── Run extraction ──────────────────────────────────────────
    print()
    total_start = time.time()
    output_files = run_extraction(config, project_keys)
    total_elapsed = time.time() - total_start

    # ── Summary ─────────────────────────────────────────────────
    print()
    logger.info("=" * 60)
    logger.info(f"  Export complete in {total_elapsed:.1f}s")
    logger.info(f"  Generated {len(output_files)} HTML file(s):")
    for f in output_files:
        logger.info(f"    • {f}")
    logger.info("=" * 60)

    if not output_files:
        logger.error("No HTML files were generated. Check errors above.")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
