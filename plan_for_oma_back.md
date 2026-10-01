# Omarchy Config Backup & Restore — Implementation Plan

## 1. Project goal

Build a production-quality Python 3 CLI called `omarchy-backup` for Omarchy 4.x and current Hyprland.

The application must:

1. Discover the user's Omarchy + Hyprland configuration.
2. Back up all relevant user configuration safely.
3. Back up Hyprland keybindings and configuration.
4. Back up Omarchy configuration.
5. Detect installed Omarchy shell plugins and Hyprland `hyprpm` plugins.
6. Store plugin GitHub repository URLs and metadata rather than blindly copying managed plugin repositories.
7. Back up relevant custom scripts and package information when explicitly supported.
8. Create checksums and a manifest.
9. Initialize/manage a separate Git repository.
10. Commit the backup.
11. Push the backup to GitHub.
12. Restore the backup safely to the current machine.
13. Reinstall missing plugins from their recorded GitHub URLs.
14. Validate the restored configuration.
15. Automatically create a pre-restore snapshot and support rollback.
16. Provide dry-run and compatibility checks.

---

# 2. Important Omarchy architecture

Do not treat `/usr/share/omarchy` as the user's configuration.

Omarchy's defaults are maintained separately, while user overrides live primarily under:

```text
~/.config/
```

Never modify `/usr/share/omarchy` as part of normal backup/restore.

The backup application should preserve the user's configuration and record the installed Omarchy version so the restore process can detect compatibility problems.

---

# 3. Backup repository architecture

Use a repository outside `~/.config`, for example:

```text
~/omarchy-config-backup/
```

Suggested structure:

```text
omarchy-config-backup/
├── README.md
├── manifest.json
├── versions.json
├── system.json
│
├── hypr/
│   ├── hyprland.lua
│   ├── bindings.lua
│   ├── monitors.lua
│   ├── input.lua
│   ├── looknfeel.lua
│   ├── autostart.lua
│   ├── hyprsunset.conf
│   ├── xdph.conf
│   └── ...
│
├── omarchy/
│   ├── shell.json
│   ├── shell.toml
│   ├── extensions/
│   └── hooks/
│
├── plugins/
│   ├── omarchy-shell.json
│   └── hyprpm.json
│
├── packages/
│   ├── native.txt
│   ├── aur.txt
│   └── explicit.txt
│
├── local/
│   ├── bin/
│   └── applications/
│
├── dotfiles/
│   └── ...
│
└── metadata/
    ├── checksums.json
    ├── backup-info.json
    └── hardware.json
```

The exact file list must be generated from a controlled manifest rather than blindly copying the entire home directory or entire `~/.config`.

---

# 4. Manifest-driven backup

Never implement the backup as:

```python
copytree("~/.config", backup)
```

and never use:

```bash
git add .
```

The application must maintain an audited manifest.

Example:

```json
{
  "version": 1,
  "entries": [
    {
      "source": "~/.config/hypr",
      "destination": "hypr",
      "type": "directory",
      "scope": "portable"
    }
  ]
}
```

The manifest should contain:

- source path
- backup destination
- file/directory type
- scope (`portable` or `local`)
- SHA-256 checksum
- permissions
- symlink information where relevant
- optional restore rules

The manifest should be generated/updated during discovery and backup.

---

# 5. Hyprland backup

Discover the user's complete:

```text
~/.config/hypr/
```

configuration.

Recognize the standard Omarchy files:

```text
hyprland.lua
bindings.lua
monitors.lua
input.lua
looknfeel.lua
autostart.lua
hyprsunset.conf
xdph.conf
```

Also discover additional supported user configuration files rather than assuming the list will never change.

Preserve:

- relative paths
- permissions
- symlinks
- file type
- checksums

Keybindings must be restored from their actual configuration source, especially:

```text
~/.config/hypr/bindings.lua
```

Do not create a separate keybinding database that becomes the source of truth.

Optional diagnostic metadata may contain a rendered/effective keybinding list.

---

# 6. Omarchy configuration

Discover and back up relevant user configuration under:

```text
~/.config/omarchy/
```

Important supported files/directories include:

```text
shell.json
shell.toml
extensions/
hooks/
plugins/
```

Do not blindly copy unrelated state.

The application should have a configurable allowlist/discovery mechanism.

---

# 7. Omarchy shell plugins

Treat Omarchy's built-in plugins and user-installed plugins differently.

Do not copy Omarchy's built-in plugin source into the backup.

For user-installed plugins, record:

```json
{
  "id": "example.plugin",
  "type": "omarchy-shell",
  "repository": "https://github.com/example/plugin.git",
  "enabled": true,
  "version": "...",
  "revision": "..."
}
```

The plugin repository URL is the important part for reproduction.

During restore:

1. Detect whether the plugin is already installed.
2. If missing, use the official Omarchy plugin installation mechanism.
3. Enable it if the backup says it was enabled.
4. Do not reinstall existing plugins unnecessarily.

Because plugins execute with user permissions, plugin installation must require confirmation by default.

Provide:

```bash
omarchy-backup restore --yes
```

for explicitly unattended operation.

---

# 8. Hyprland plugins

Use the current `hyprpm` mechanism.

Discover installed plugins through supported `hyprpm` commands.

Store:

```text
plugin name
repository URL
enabled state
version/revision when available
```

Example:

```json
{
  "plugins": [
    {
      "name": "example",
      "repository": "https://github.com/example/hypr-plugin",
      "enabled": true,
      "revision": "..."
    }
  ]
}
```

Restore missing plugins through `hyprpm`.

Do not copy arbitrary plugin binaries or plugin directories as the primary restoration mechanism.

---

# 9. Plugin reproducibility

A GitHub URL alone may not reproduce the exact version.

Store, where discoverable:

```text
repository
branch
tag
commit/revision
version
enabled state
```

Support two conceptual restore modes:

### Latest-compatible

Install the current version from the recorded repository.

### Reproducible

Attempt to restore the recorded revision/commit.

The default should favor safe compatibility rather than blindly checking out an old revision if the current Omarchy/Hyprland version is incompatible.

---

# 10. System/version metadata

Create:

```text
versions.json
```

containing information such as:

```json
{
  "omarchy": "...",
  "hyprland": "...",
  "linux": "...",
  "hyprpm": "...",
  "quickshell": "...",
  "python": "...",
  "architecture": "x86_64"
}
```

Discover versions dynamically using supported commands.

Do not assume command output formats will remain unchanged.

Also record:

```text
system.json
```

for diagnostic information such as:

- architecture
- CPU
- GPU
- RAM
- display/monitor information
- hostname if desired

Do not use hardware metadata as the configuration source.

---

# 11. Portable vs local configuration

Classify backed-up configuration as:

```text
portable
local
```

Examples:

### Portable

```text
bindings.lua
input.lua
looknfeel.lua
many Omarchy shell settings
```

### Local

```text
monitors.lua
hardware-specific configuration
machine-specific scripts
```

Normal restore should not overwrite local configuration without explicit permission.

Support:

```bash
omarchy-backup restore --include-local
```

---

# 12. Package backup

Optionally record installed packages.

Separate:

```text
packages/native.txt
packages/aur.txt
packages/explicit.txt
```

Do not automatically reinstall packages during a normal restore.

Provide an explicit option such as:

```bash
omarchy-backup restore --packages
```

Package availability may differ between machines, so package restoration must be best-effort with clear reporting.

---

# 13. Custom scripts

Optionally support:

```text
~/.local/bin/
```

and relevant application files.

The tool should discover scripts referenced by:

- Hyprland keybindings
- autostart
- Omarchy hooks
- other backed-up configuration

Avoid blindly copying every executable.

Provide:

```bash
omarchy-backup backup --include-scripts
```

when appropriate.

---

# 14. Secret protection

This is mandatory.

Never back up:

```text
~/.ssh/
.env
*.pem
*.key
credentials
tokens
API keys
private keys
browser credential stores
unrelated application secrets
```

Implement:

1. Explicit exclusion patterns.
2. Secret-pattern scanning.
3. Pre-Git-stage validation.

The tool must never automatically stage unreviewed files.

If a possible secret is found:

```text
Potential secret detected:
path: ...
reason: ...
Action: excluded from backup
```

Allow users to configure additional exclusions/patterns.

---

# 15. Git architecture

The Git repository must be separate from the live configuration.

Good:

```text
~/omarchy-config-backup/.git/
```

Bad:

```text
~/.config/.git/
```

The backup repository should contain only audited configuration and metadata.

---

# 16. Git workflow

Backup flow:

```text
discover
   ↓
validate
   ↓
secret scan
   ↓
generate/update manifest
   ↓
copy files
   ↓
calculate checksums
   ↓
inspect Git diff
   ↓
commit
   ↓
optional push
```

Never use:

```bash
git add .
```

Stage only files listed in the audited manifest.

Suggested commit message:

```text
backup: update Omarchy configuration
```

Include useful metadata such as Omarchy and Hyprland versions when appropriate.

---

# 17. GitHub setup

Support:

```bash
omarchy-backup init
```

Interactive configuration:

```text
Backup directory
GitHub repository
Branch
Remote
```

Example configuration:

```toml
repository = "git@github.com:user/omarchy-config.git"
branch = "main"
```

Do not store GitHub tokens/passwords in the backup repository.

Prefer the user's existing Git/SSH credential mechanism.

---

# 18. CLI

Implement:

```bash
omarchy-backup init
omarchy-backup scan
omarchy-backup backup
omarchy-backup backup --push
omarchy-backup status
omarchy-backup diff
omarchy-backup history
omarchy-backup restore
omarchy-backup restore --dry-run
omarchy-backup restore --include-local
omarchy-backup restore --exact
omarchy-backup restore --from <commit>
omarchy-backup rollback
omarchy-backup push
omarchy-backup pull
```

---

# 19. Restore architecture

Never restore by blindly doing:

```python
shutil.copytree(...)
```

Use:

```text
backup
  ↓
validate
  ↓
compatibility check
  ↓
create emergency snapshot
  ↓
generate restore plan
  ↓
dry-run/confirmation
  ↓
stage changes
  ↓
validate staged configuration
  ↓
apply changes
  ↓
reload/restart required components
  ↓
validate live system
  ↓
success
```

If validation fails:

```text
rollback emergency snapshot
```

---

# 20. Pre-restore snapshot

Every restore must automatically create:

```text
snapshots/
└── pre-restore-YYYY-MM-DDTHH-MM-SS/
```

containing the currently managed configuration.

This makes every restore reversible.

Provide:

```bash
omarchy-backup rollback
```

to restore the latest emergency snapshot.

---

# 21. Atomic file restoration

For files:

1. Write to a temporary file.
2. Validate the temporary file.
3. Flush/sync it.
4. Atomically rename it into place where possible.

Do not directly truncate the live configuration before validation.

For directories, stage the restore in a temporary location and apply managed files individually.

---

# 22. Never delete unknown files by default

Normal restore should only:

- create files from the backup
- modify files managed by the backup
- restore supported configuration

It must not delete unrelated files.

Do not do:

```bash
rm -rf ~/.config
```

or equivalent.

Provide:

```bash
omarchy-backup restore --exact
```

only for an explicitly requested exact restore.

Even `--exact` must restrict deletion to files/directories defined by the application's managed manifest.

---

# 23. Restore planner

Create a restore planner before executing anything.

It should produce actions such as:

```text
CREATE
MODIFY
DELETE
INSTALL_PLUGIN
ENABLE_PLUGIN
DISABLE_PLUGIN
RELOAD_SERVICE
RESTART_SERVICE
PACKAGE_INSTALL
```

Example dry-run:

```text
RESTORE PLAN

Files:
  MODIFY ~/.config/hypr/bindings.lua
  MODIFY ~/.config/hypr/looknfeel.lua
  CREATE ~/.config/omarchy/shell.toml

Plugins:
  INSTALL example.weather
  ENABLE example.clock

Services:
  RELOAD Hyprland
  RESTART Omarchy Shell

Local configuration:
  monitors.lua
  NOT INCLUDED

No changes have been made.
```

The planner must run before the executor.

---

# 24. Hyprland validation

After restoring Hyprland Lua configuration:

```bash
hyprctl reload
```

Then validate using the current supported Hyprland configuration-error mechanism, including:

```bash
hyprctl configerrors
```

Do not report a successful restore while configuration errors remain.

Handle `hyprsunset.conf` and `xdph.conf` separately because they do not follow the same validation/reload path as the main Hyprland Lua configuration.

---

# 25. Omarchy shell reload

Use official Omarchy mechanisms for reloading/restarting the shell.

Do not manipulate Quickshell internals directly if an official Omarchy command is available.

The restore engine should have a post-restore action registry, rather than assuming every configuration change is solved with:

```bash
hyprctl reload
```

---

# 26. Plugin restoration order

Use:

```text
1. Restore base configuration.
2. Restore Omarchy shell configuration.
3. Restore Hyprland configuration.
4. Install missing Omarchy plugins.
5. Install missing Hyprland plugins.
6. Enable required plugins.
7. Reload Hyprland.
8. Reload/restart Omarchy shell.
9. Validate the running system.
```

---

# 27. Compatibility checks

Before restore compare:

```text
backup Omarchy version
current Omarchy version

backup Hyprland version
current Hyprland version
```

Use severity levels:

```text
INFO
WARNING
BLOCKING
```

Example:

```text
WARNING:
Backup created on Omarchy 4.x.
Current system is Omarchy 5.x.
Configuration may require migration.
```

Do not automatically block every version mismatch.

---

# 28. Backup format migrations

Use:

```text
migrations/
├── __init__.py
├── v1.py
├── v2.py
└── ...
```

Every backup must contain:

```json
{
  "format_version": 1,
  "created_at": "...",
  "application_version": "...",
  "omarchy_version": "...",
  "hyprland_version": "..."
}
```

This allows future versions of the application to restore old backups.

---

# 29. Checksums and integrity

Every managed file should have metadata like:

```json
{
  "path": "hypr/bindings.lua",
  "sha256": "...",
  "size": 1234,
  "mode": "0644",
  "scope": "portable"
}
```

During restore:

1. Verify backup checksum.
2. Verify the file has not changed since the manifest was generated.
3. Restore.
4. Verify the destination checksum.

---

# 30. Status and diff

`status` should compare:

```text
current filesystem
       VS
backup repository
```

Example:

```text
Modified:
  hypr/bindings.lua

Added:
  hypr/windowrules.lua

Deleted:
  omarchy/hooks/example

Plugin changed:
  example.weather
```

Use SHA-256 checksums instead of relying only on timestamps.

---

# 31. Recovery state

Create a state file outside the backup repository, for example:

```text
~/.local/state/omarchy-backup/.restore-state.json
```

Example:

```json
{
  "operation": "restore",
  "status": "in_progress",
  "snapshot": "..."
}
```

If the program crashes during restore, the next invocation should detect the unfinished operation and offer:

```text
1. Roll back
2. Continue
3. Inspect
```

---

# 32. Python architecture

Suggested source tree:

```text
src/
└── omarchy_backup/
    ├── __init__.py
    ├── cli.py
    ├── config.py
    ├── paths.py
    ├── manifest.py
    │
    ├── discovery/
    │   ├── hyprland.py
    │   ├── omarchy.py
    │   ├── plugins.py
    │   ├── packages.py
    │   └── scripts.py
    │
    ├── backup/
    │   ├── collector.py
    │   ├── copier.py
    │   ├── checksum.py
    │   └── snapshot.py
    │
    ├── restore/
    │   ├── planner.py
    │   ├── executor.py
    │   ├── validator.py
    │   └── rollback.py
    │
    ├── plugins/
    │   ├── omarchy.py
    │   └── hyprpm.py
    │
    ├── git/
    │   ├── repository.py
    │   ├── commit.py
    │   └── remote.py
    │
    ├── security/
    │   ├── secrets.py
    │   └── exclusions.py
    │
    └── migrations/
```

---

# 33. Dependencies

Target:

```text
Python 3.11+
```

Prefer the standard library:

```python
pathlib
subprocess
shutil
json
hashlib
tempfile
datetime
platform
os
stat
tarfile
logging
```

Optional:

```text
typer
rich
```

Do not add dependencies without a clear reason.

---

# 34. Command runner

Do not scatter raw `subprocess.run()` throughout the project.

Create a `CommandRunner` abstraction with methods such as:

```python
run()
check()
capture()
interactive()
```

It should handle:

```text
omarchy
hyprctl
hyprpm
git
systemctl
```

This makes testing and error handling easier.

---

# 35. Testing

## Unit tests

Test:

```text
manifest generation
path handling
checksums
secret detection
version parsing
plugin parsing
Git command construction
restore planning
rollback planning
```

## Integration tests

Use a temporary fake HOME:

```text
/tmp/omarchy-backup-test/
```

Simulate:

```text
~/.config/hypr
~/.config/omarchy
~/.local/bin
```

Test:

```text
backup
modify configuration
restore
verify
```

Create fake command runners for:

```text
omarchy
hyprctl
hyprpm
git
```

Do not let automated tests modify the real user's desktop.

---

# 36. Logging

Store logs outside the Git backup repository:

```text
~/.local/state/omarchy-backup/
```

Example:

```text
backup-2026-10-01.log
restore-2026-10-01.log
```

Avoid writing secrets or sensitive configuration content into logs.

---

# 37. Implementation phases

Do not implement everything simultaneously.

## Phase 1 — Discovery

Implement:

```text
CLI
configuration
path discovery
Hyprland discovery
Omarchy discovery
manifest
read-only scan
```

The first milestone must not modify the system.

## Phase 2 — Backup

Add:

```text
file collection
checksums
permissions
symlink handling
snapshots
secret scanning
```

## Phase 3 — Plugins

Add:

```text
Omarchy plugin discovery
Hyprland plugin discovery
GitHub URL extraction
plugin metadata
```

## Phase 4 — Git

Add:

```text
Git initialization
audited staging
commit
remote configuration
push
pull
history
```

## Phase 5 — Restore

Add:

```text
restore planner
dry-run
transactional restore
atomic writes
pre-restore snapshots
rollback
```

## Phase 6 — Runtime validation

Add:

```text
Hyprland reload
config error validation
Omarchy shell reload
plugin restoration
compatibility checks
```

## Phase 7 — Advanced features

Add:

```text
package backup
script discovery
format migrations
exact restore
enhanced secret scanning
```

## Phase 8 — Quality

Add:

```text
unit tests
integration tests
documentation
CI
packaging
release process
```

---

# 38. Critical design principles

The implementation must follow these principles:

### Never modify Omarchy-owned defaults

```text
/usr/share/omarchy
```

is not the primary backup target.

### Never blindly copy all configuration

Use an audited manifest.

### Never blindly install arbitrary plugins

Plugins execute with user permissions.

### Never store secrets

Scan before Git staging.

### Never use `git add .`

Only stage manifest-approved files.

### Never overwrite live configuration before validation

Use staging and atomic replacement.

### Never delete unknown files during normal restore

Use explicit `--exact`.

### Always make restore reversible

Create a pre-restore snapshot first.

### Always validate Hyprland after restoration

Do not report success while configuration errors remain.

### Prefer official Omarchy/Hyprland mechanisms

Use `omarchy`, `hyprctl`, and `hyprpm` rather than manipulating internal implementation details.

### Discover before assuming

Omarchy and Hyprland are actively evolving. Detect supported commands, files, plugins, and configuration formats dynamically wherever possible.

---

# 39. Initial implementation order for the AI agent

Start with:

```text
1. Research the installed Omarchy version and current Hyprland version.
2. Inspect the current Omarchy source/documentation.
3. Inspect the actual user's configuration paths.
4. Implement read-only discovery.
5. Implement `omarchy-backup scan`.
6. Show the discovered files/plugins/configuration.
7. Add manifest generation.
8. Add backup.
9. Add checksums and secret scanning.
10. Add Git commit/push.
11. Add dry-run restore planner.
12. Add transactional restore.
13. Add plugin restoration.
14. Add Hyprland/Omarchy validation.
15. Add rollback.
16. Add tests.
17. Document the complete workflow.
```

Do not skip the discovery phase.

The agent must inspect the actual installed environment before deciding that a file, command, plugin mechanism, or configuration path exists.
