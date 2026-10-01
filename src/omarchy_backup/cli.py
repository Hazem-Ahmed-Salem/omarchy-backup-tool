"""Command-line interface for omarchy-backup."""

from __future__ import annotations

import argparse
import difflib
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from omarchy_backup import __version__
from omarchy_backup.backup.checksum import calculate_sha256
from omarchy_backup.backup.collector import BackupCollector
from omarchy_backup.backup.snapshot import get_latest_snapshot, list_snapshots
from omarchy_backup.config import BackupConfig
from omarchy_backup.discovery.hyprland import discover_hyprland_files
from omarchy_backup.discovery.omarchy import discover_omarchy_files
from omarchy_backup.discovery.packages import discover_packages
from omarchy_backup.discovery.plugins import discover_all_plugins
from omarchy_backup.discovery.scripts import discover_custom_scripts
from omarchy_backup.discovery.system import discover_system_info, discover_versions
from omarchy_backup.git.commit import commit_manifest_backup
from omarchy_backup.git.remote import configure_remote, pull_backup, push_backup
from omarchy_backup.git.repository import GitRepo
from omarchy_backup.manifest import Manifest
from omarchy_backup.paths import AppPaths, default_paths
from omarchy_backup.restore.executor import RestoreEngine
from omarchy_backup.restore.planner import plan_restore
from omarchy_backup.restore.rollback import rollback_latest_snapshot
from omarchy_backup.runner import CommandRunner, default_runner

# ANSI terminal formatting
USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text

def bold(text: str) -> str: return _c(text, "1")
def green(text: str) -> str: return _c(text, "32")
def red(text: str) -> str: return _c(text, "31")
def yellow(text: str) -> str: return _c(text, "33")
def cyan(text: str) -> str: return _c(text, "36")
def dim(text: str) -> str: return _c(text, "2")


def setup_logging(paths: AppPaths, op_name: str = "cli") -> None:
    """Configure file logging in ~/.local/state/omarchy-backup/logs."""
    logs_dir = paths.logs_dir
    logs_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = logs_dir / f"{op_name}-{today}.log"

    logging.basicConfig(
        filename=str(log_file),
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


# --- Commands ---

def cmd_init(args: argparse.Namespace, paths: AppPaths, config: BackupConfig) -> int:
    """Initialize omarchy-backup configuration and git repository."""
    print(bold(cyan("\n=== omarchy-backup Initialization ===\n")))

    backup_dir = args.dir or config.backup_dir
    if not backup_dir:
        default_dir = str(paths.default_backup_dir)
        if sys.stdin.isatty():
            ans = input(f"Backup repository directory [{default_dir}]: ").strip()
            backup_dir = ans if ans else default_dir
        else:
            backup_dir = default_dir

    remote_url = args.remote or config.remote_url
    if not remote_url and sys.stdin.isatty():
        ans = input("GitHub / Remote git URL (optional, e.g. git@github.com:...): ").strip()
        remote_url = ans

    branch = args.branch or config.branch or "main"

    # Save configuration
    config.backup_dir = backup_dir
    config.remote_url = remote_url
    config.branch = branch
    cfg_file = config.save(paths)
    print(f"{green('✓')} Saved configuration to: {cfg_file}")

    # Initialize Git repository
    repo_path = Path(backup_dir).expanduser().resolve()
    repo = GitRepo(repo_path)
    if repo.init(branch=branch):
        print(f"{green('✓')} Initialized Git repository at: {repo_path} (branch: {branch})")
    else:
        print(f"{red('✗')} Failed to initialize Git repository at: {repo_path}")
        return 1

    # Remote setup
    if remote_url:
        if configure_remote(repo, remote_url):
            print(f"{green('✓')} Configured remote 'origin' -> {remote_url}")
        else:
            print(f"{yellow('!')} Could not configure remote URL.")

    print(bold(green("\nInitialization complete! You can now run `omarchy-backup scan` or `omarchy-backup backup`.\n")))
    return 0


def cmd_scan(args: argparse.Namespace, paths: AppPaths, config: BackupConfig) -> int:
    """Read-only discovery of current system configuration, plugins, and secrets."""
    print(bold(cyan("\n=== Omarchy Configuration Scan (Read-Only) ===\n")))

    # 1. Versions
    versions = discover_versions()
    print(bold("Discovered Versions:"))
    for comp, ver in versions.items():
        print(f"  • {comp:<14}: {cyan(ver)}")

    # 2. Hyprland configuration
    hypr_files = discover_hyprland_files(paths, config.custom_exclusions)
    print(bold(f"\nHyprland Configurations ({len(hypr_files)} files found):"))
    for hf in hypr_files:
        scope_str = yellow("[local]") if hf.scope == "local" else green("[portable]")
        print(f"  {scope_str} {hf.source} -> {dim(hf.destination)}")

    # 3. Omarchy configuration
    omarchy_files = discover_omarchy_files(paths, config.custom_exclusions)
    print(bold(f"\nOmarchy Configurations ({len(omarchy_files)} files found):"))
    for of in omarchy_files:
        scope_str = yellow("[local]") if of.scope == "local" else green("[portable]")
        print(f"  {scope_str} {of.source} -> {dim(of.destination)}")

    # 4. Plugins
    all_plugins = discover_all_plugins(paths)
    om_plugins = all_plugins.get("omarchy-shell", [])
    print(bold(f"\nOmarchy Shell Plugins ({len(om_plugins)} discovered):"))
    for p in om_plugins:
        status = green("enabled") if p.enabled else dim("disabled")
        repo_disp = cyan(p.repository) if p.repository else dim("(local / no git repo)")
        rev_disp = f"@{p.revision[:8]}" if p.revision else ""
        first_party_str = dim(" [first-party]") if p.first_party else ""
        print(f"  • {bold(p.id)} ({status}){first_party_str}: {repo_disp} {rev_disp}")

    hypr_plugins = all_plugins.get("hyprpm", [])
    if hypr_plugins:
        print(bold(f"\nHyprland Plugins ({len(hypr_plugins)} discovered):"))
        for hp in hypr_plugins:
            print(f"  • {bold(hp.name)}: {cyan(hp.repository)}")

    # 5. Packages
    pkg_lists = discover_packages()
    print(bold("\nExplicit Packages:"))
    print(f"  • Native packages: {len(pkg_lists.native)}")
    print(f"  • AUR packages:    {len(pkg_lists.aur)}")
    print(f"  • Total explicit:  {len(pkg_lists.explicit)}")

    # 6. Scripts
    scripts = discover_custom_scripts(hypr_files + omarchy_files, include_all=False, paths=paths)
    print(bold(f"\nReferenced Custom Scripts ({len(scripts)} found in ~/.local/bin):"))
    for sc in scripts:
        print(f"  • {sc.source} ({sc.mode})")

    # 7. System Diagnostics
    sys_info = discover_system_info()
    displays = sys_info.get("displays", [])
    print(bold(f"\nHardware & Displays:"))
    print(f"  • CPU: {sys_info.get('cpu', 'unknown')}")
    print(f"  • RAM: {sys_info.get('memory_total_mb', 0)} MB")
    print(f"  • Connected Monitors ({len(displays)}):")
    for d in displays:
        name = d.get("name", "Display")
        w, h, r = d.get("width"), d.get("height"), d.get("refreshRate")
        print(f"    - {name}: {w}x{h} @ {r:.2f}Hz")

    print(bold(green("\n✓ Read-only scan complete. No changes were made to your system or backup repository.\n")))
    return 0


def cmd_backup(args: argparse.Namespace, paths: AppPaths, config: BackupConfig) -> int:
    """Perform configuration backup and commit to Git repository."""
    setup_logging(paths, "backup")
    print(bold(cyan("\n=== Running Omarchy Configuration Backup ===\n")))

    target_dir = Path(args.dir).expanduser().resolve() if args.dir else config.get_backup_path(paths)
    include_scripts = args.include_scripts or config.include_scripts

    collector = BackupCollector(config=config, paths=paths)
    res = collector.collect(
        target_dir=target_dir,
        include_scripts=include_scripts,
        include_packages=not args.no_packages,
    )

    if not res.success:
        print(red(f"\n✗ Backup encountered errors: {len(res.failed_files)} files failed to copy."))
        for f, err in res.failed_files:
            print(f"  - {f}: {err}")
        return 1

    print(f"{green('✓')} Copied {bold(str(len(res.copied_files)))} configuration files to {target_dir}")
    print(f"{green('✓')} Recorded {res.plugin_counts.get('omarchy-shell', 0)} Omarchy plugins and {res.plugin_counts.get('hyprpm', 0)} Hyprpm plugins")
    print(f"{green('✓')} Generated checksums, manifest.json, versions.json, and system.json")

    # Git commit
    repo = GitRepo(target_dir)
    ok, msg = commit_manifest_backup(repo, res.manifest, custom_message=args.message)
    if ok:
        print(f"{green('✓')} Git commit: {cyan(msg)}")
    else:
        print(f"{yellow('!')} Git commit notice: {msg}")

    # Push if requested
    if args.push:
        print(dim("\nPushing backup to remote..."))
        push_ok, push_msg = push_backup(repo, branch=config.branch)
        if push_ok:
            print(f"{green('✓')} {push_msg}")
        else:
            print(f"{red('✗')} {push_msg}")
            return 1

    print(bold(green("\n✓ Backup completed successfully!\n")))
    return 0


def cmd_status(args: argparse.Namespace, paths: AppPaths, config: BackupConfig) -> int:
    """Compare live system configuration against the backup repository."""
    backup_dir = Path(args.dir).expanduser().resolve() if args.dir else config.get_backup_path(paths)
    manifest_file = backup_dir / "manifest.json"

    if not manifest_file.is_file():
        print(red(f"Error: Manifest not found at {manifest_file}. Run 'omarchy-backup backup' first."))
        return 1

    manifest = Manifest.load(manifest_file)
    print(bold(cyan(f"\n=== Configuration Status ({backup_dir.name}) ===\n")))

    modified: list[str] = []
    missing_live: list[str] = []
    identical: list[str] = []

    for entry in manifest.entries:
        live_file = Path(entry.source.replace("~", str(paths.home)))
        if not live_file.exists() and not live_file.is_symlink():
            missing_live.append(entry.source)
            continue

        if entry.entry_type == "file":
            try:
                live_sha = calculate_sha256(live_file)
                if live_sha.lower() != entry.sha256.lower():
                    modified.append(entry.source)
                else:
                    identical.append(entry.source)
            except Exception:
                modified.append(entry.source)

    if modified:
        print(bold(yellow(f"Modified files ({len(modified)}):")))
        for m in modified:
            print(f"  {yellow('~')} {m}")

    if missing_live:
        print(bold(red(f"\nFiles present in backup but missing on system ({len(missing_live)}):")))
        for ml in missing_live:
            print(f"  {red('-')} {ml}")

    # Check for new unbacked-up files in ~/.config/hypr and ~/.config/omarchy
    live_hypr = discover_hyprland_files(paths)
    live_om = discover_omarchy_files(paths)
    manifest_sources = {e.source for e in manifest.entries}
    new_files = [f.source for f in live_hypr + live_om if f.source not in manifest_sources]

    if new_files:
        print(bold(green(f"\nNew unbacked files ({len(new_files)}):")))
        for nf in new_files:
            print(f"  {green('+')} {nf}")

    if not modified and not missing_live and not new_files:
        print(green("All managed files match the backup repository exactly."))

    print()
    return 0


def cmd_diff(args: argparse.Namespace, paths: AppPaths, config: BackupConfig) -> int:
    """Show differences between live configuration and backup repository."""
    backup_dir = Path(args.dir).expanduser().resolve() if args.dir else config.get_backup_path(paths)
    manifest_file = backup_dir / "manifest.json"

    if not manifest_file.is_file():
        print(red(f"Manifest not found at {manifest_file}"))
        return 1

    manifest = Manifest.load(manifest_file)
    diff_found = False

    for entry in manifest.entries:
        if entry.entry_type != "file":
            continue

        if args.file and args.file not in entry.destination and args.file not in entry.source:
            continue

        backup_file = backup_dir / entry.destination
        live_file = Path(entry.source.replace("~", str(paths.home)))

        if not backup_file.is_file() or not live_file.is_file():
            continue

        try:
            with open(backup_file, "r", encoding="utf-8", errors="replace") as bf:
                b_lines = bf.readlines()
            with open(live_file, "r", encoding="utf-8", errors="replace") as lf:
                l_lines = lf.readlines()

            diff = list(difflib.unified_diff(
                b_lines,
                l_lines,
                fromfile=f"backup/{entry.destination}",
                tofile=f"live/{entry.source}",
            ))

            if diff:
                diff_found = True
                print(bold(f"\n--- diff: {entry.destination} ---"))
                for line in diff:
                    line_s = line.rstrip("\n")
                    if line_s.startswith("+"):
                        print(green(line_s))
                    elif line_s.startswith("-"):
                        print(red(line_s))
                    elif line_s.startswith("@"):
                        print(cyan(line_s))
                    else:
                        print(line_s)
        except Exception as exc:
            print(yellow(f"Could not diff {entry.destination}: {exc}"))

    if not diff_found:
        print("No differences found between live system and backup.")
    return 0


def cmd_history(args: argparse.Namespace, paths: AppPaths, config: BackupConfig) -> int:
    """Display git commit history for backup repository."""
    backup_dir = Path(args.dir).expanduser().resolve() if args.dir else config.get_backup_path(paths)
    repo = GitRepo(backup_dir)

    history = repo.get_history(limit=args.limit)
    if not history:
        print("No backup history found.")
        return 0

    print(bold(cyan(f"\n=== Backup History ({backup_dir.name}) ===\n")))
    for commit in history:
        print(f"  {yellow(commit['short_hash'])}  {cyan(commit['date'])}  {commit['message']}")
    print()
    return 0


def cmd_restore(args: argparse.Namespace, paths: AppPaths, config: BackupConfig) -> int:
    """Safely restore configuration with pre-restore snapshot and verification."""
    setup_logging(paths, "restore")
    backup_dir = Path(args.dir).expanduser().resolve() if args.dir else config.get_backup_path(paths)
    manifest_file = backup_dir / "manifest.json"

    if not manifest_file.is_file():
        print(red(f"Backup manifest not found: {manifest_file}"))
        return 1

    manifest = Manifest.load(manifest_file)
    engine = RestoreEngine(paths=paths)

    # Check crash recovery
    pending = engine.check_pending_recovery()
    if pending:
        print(bold(red("\n[!] A previous restore operation was interrupted or crashed!")))
        print(f"    Snapshot available at: {pending.get('snapshot')}")
        print("    Run 'omarchy-backup rollback' to return to safe state before proceeding.\n")
        if not args.yes:
            ans = input("Continue anyway? (y/N): ").strip().lower()
            if ans != "y":
                return 1

    # Plan
    plan = plan_restore(
        manifest=manifest,
        backup_dir=backup_dir,
        paths=paths,
        include_local=args.include_local,
        exact=args.exact,
    )

    print(plan.render_text())

    # Dry-run check
    if args.dry_run:
        print(bold(cyan("\nDry-run complete. No changes have been made to your system.\n")))
        return 0

    # User confirmation
    if not args.yes:
        ans = input(bold("\nProceed with restore? (y/N): ")).strip().lower()
        if ans != "y":
            print("Restore cancelled by user.")
            return 0

    print(dim("\nExecuting restore pipeline..."))
    res = engine.execute(
        backup_dir=backup_dir,
        include_local=args.include_local,
        exact=args.exact,
        auto_confirm=args.yes,
        skip_service_reload=args.no_reload,
    )

    if res.rolled_back:
        print(bold(red(f"\n✗ Restore failed and was automatically rolled back: {res.error}")))
        if res.warnings:
            for w in res.warnings:
                print(f"  {yellow('!')} {w}")
        return 1

    if not res.success:
        print(bold(red(f"\n✗ Restore failed: {res.error}")))
        return 1

    print(f"{green('✓')} Pre-restore snapshot created: {res.snapshot_path}")
    print(f"{green('✓')} Restored {bold(str(len(res.files_applied)))} configuration files.")
    for sa in res.service_actions:
        print(f"{green('✓')} {sa}")
    for pa in res.plugin_actions:
        print(f"{green('✓')} {pa}")

    print(bold(green("\n✓ Restore completed successfully!\n")))
    return 0


def cmd_rollback(args: argparse.Namespace, paths: AppPaths) -> int:
    """Restore the latest emergency pre-restore snapshot."""
    print(bold(cyan("\n=== Emergency Snapshot Rollback ===\n")))
    latest = get_latest_snapshot(paths)
    if not latest:
        print(yellow("No emergency snapshots found to rollback."))
        return 1

    print(f"Found latest snapshot: {bold(latest.name)}")
    if not args.yes:
        ans = input("Rollback system to this snapshot? (y/N): ").strip().lower()
        if ans != "y":
            print("Rollback cancelled.")
            return 0

    ok, name, files = rollback_latest_snapshot(paths)
    if ok:
        print(f"{green('✓')} Rolled back {bold(str(len(files)))} files from snapshot {name}")
        print(bold(green("\n✓ Rollback successful! Restart your shell or reload Hyprland if needed.\n")))
        return 0
    else:
        print(red(f"\n✗ Rollback failed for snapshot {name}."))
        return 1


def cmd_push(args: argparse.Namespace, paths: AppPaths, config: BackupConfig) -> int:
    """Push configuration backup to remote Git repository."""
    backup_dir = Path(args.dir).expanduser().resolve() if args.dir else config.get_backup_path(paths)
    repo = GitRepo(backup_dir)
    ok, msg = push_backup(repo, branch=config.branch)
    if ok:
        print(f"{green('✓')} {msg}")
        return 0
    else:
        print(f"{red('✗')} {msg}")
        return 1


def cmd_pull(args: argparse.Namespace, paths: AppPaths, config: BackupConfig) -> int:
    """Pull configuration backup updates from remote Git repository."""
    backup_dir = Path(args.dir).expanduser().resolve() if args.dir else config.get_backup_path(paths)
    repo = GitRepo(backup_dir)
    ok, msg = pull_backup(repo, branch=config.branch)
    if ok:
        print(f"{green('✓')} {msg}")
        return 0
    else:
        print(f"{red('✗')} {msg}")
        return 1


# --- CLI Parser Setup ---

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="omarchy-backup",
        description="Audited, reversible configuration backup and restore for Omarchy and Hyprland",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser("init", help="Initialize backup directory and Git remote")
    p_init.add_argument("--dir", help="Backup repository path")
    p_init.add_argument("--remote", help="GitHub repository URL")
    p_init.add_argument("--branch", default="main", help="Git branch name")

    # scan
    subparsers.add_parser("scan", help="Read-only scan of Omarchy & Hyprland configurations")

    # backup
    p_backup = subparsers.add_parser("backup", help="Back up configurations to repository")
    p_backup.add_argument("--push", action="store_true", help="Push to remote after commit")
    p_backup.add_argument("--dir", help="Target backup repository path")
    p_backup.add_argument("--include-scripts", action="store_true", help="Include custom scripts from ~/.local/bin")
    p_backup.add_argument("--no-packages", action="store_true", help="Skip capturing pacman package lists")
    p_backup.add_argument("-m", "--message", help="Custom Git commit message")

    # status
    p_status = subparsers.add_parser("status", help="Compare live configurations against backup")
    p_status.add_argument("--dir", help="Backup repository path")

    # diff
    p_diff = subparsers.add_parser("diff", help="Show differences between live files and backup")
    p_diff.add_argument("--dir", help="Backup repository path")
    p_diff.add_argument("--file", help="Specific file relative path to diff")

    # history
    p_hist = subparsers.add_parser("history", help="Show commit history of the backup repository")
    p_hist.add_argument("--dir", help="Backup repository path")
    p_hist.add_argument("--limit", type=int, default=15, help="Number of commits to display")

    # restore
    p_restore = subparsers.add_parser("restore", help="Restore configurations safely")
    p_restore.add_argument("--dry-run", action="store_true", help="Preview restore plan without making changes")
    p_restore.add_argument("--yes", "-y", action="store_true", help="Proceed without interactive prompts")
    p_restore.add_argument("--include-local", action="store_true", help="Include machine-local configs like monitors.lua")
    p_restore.add_argument("--exact", action="store_true", help="Remove untracked files in managed directories")
    p_restore.add_argument("--dir", help="Backup repository path")
    p_restore.add_argument("--no-reload", action="store_true", help="Skip Hyprland/shell reload")

    # rollback
    p_rb = subparsers.add_parser("rollback", help="Restore latest pre-restore snapshot")
    p_rb.add_argument("--yes", "-y", action="store_true", help="Proceed without confirmation")

    # push / pull
    p_push = subparsers.add_parser("push", help="Push backup repository to remote")
    p_push.add_argument("--dir", help="Backup repository path")

    p_pull = subparsers.add_parser("pull", help="Pull backup repository from remote")
    p_pull.add_argument("--dir", help="Backup repository path")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    paths = default_paths
    config = BackupConfig.load(paths)

    cmd_map = {
        "init": lambda: cmd_init(args, paths, config),
        "scan": lambda: cmd_scan(args, paths, config),
        "backup": lambda: cmd_backup(args, paths, config),
        "status": lambda: cmd_status(args, paths, config),
        "diff": lambda: cmd_diff(args, paths, config),
        "history": lambda: cmd_history(args, paths, config),
        "restore": lambda: cmd_restore(args, paths, config),
        "rollback": lambda: cmd_rollback(args, paths),
        "push": lambda: cmd_push(args, paths, config),
        "pull": lambda: cmd_pull(args, paths, config),
    }

    handler = cmd_map.get(args.command)
    if not handler:
        parser.print_help()
        return 1

    try:
        return handler()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        return 130
    except Exception as exc:
        print(red(f"\nUnexpected error: {exc}"))
        logging.exception("Unhandled error in CLI execution")
        return 1


if __name__ == "__main__":
    sys.exit(main())
