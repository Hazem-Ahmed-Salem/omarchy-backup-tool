# omarchy-backup

A production-quality Python 3 CLI for safe, audited, reversible backup and restoration of **Omarchy 4.x** and **Hyprland** configurations.

---

## Key Features

1. **Manifest-Driven & Audited**: Never copies blind directories (`copytree("~/.config")`) or runs unreviewed Git staging (`git add .`). Every file is individually audited, hashed with SHA-256, and recorded in `manifest.json`.
2. **Secret Protection**: Strict pattern exclusions (`.env`, `*.pem`, `*.key`, `id_rsa*`, credentials, browser stores) combined with pre-stage content scanning for private keys and API tokens.
3. **Omarchy & Hyprland Architecture Aware**:
   - Preserves user configurations (`~/.config/hypr/`, `~/.config/omarchy/`).
   - Never alters Omarchy-owned package defaults (`/usr/share/omarchy`).
   - Categorizes configurations into **portable** (`bindings.lua`, `input.lua`, `shell.json`) and **local** (`monitors.lua`, `display-settings.json`).
4. **Reproducible Plugins**: Records Git repository URLs and commit revisions for user-installed Omarchy shell plugins and Hyprland plugins rather than copying managed Git trees.
5. **Reversible Restoration & Rollback**: Every restore automatically creates an emergency snapshot (`~/.local/state/omarchy-backup/snapshots/pre-restore-YYYY-MM-DDTHH-MM-SS/`). One-command recovery is available via `omarchy-backup rollback`.
6. **Atomic File Operations**: Restoration writes to temporary files, verifies checksums, flushes to disk, and atomically replaces live files.
7. **Post-Restore Validation & Self-Healing**: Validates Hyprland Lua syntax using official `hyprctl reload` and `hyprctl configerrors`. If errors are detected, the system automatically rolls back the pre-restore snapshot.
8. **Zero Third-Party Dependencies**: Built exclusively with Python 3.11+ standard library tools for maximum reliability across Arch Linux updates.

---

## Directory Architecture

The backup repository maintains an audited, clean structure outside `~/.config`:

```text
~/omarchy-config-backup/
├── README.md
├── manifest.json
├── versions.json
├── system.json
│
├── hypr/
│   ├── hyprland.lua
│   ├── bindings.lua
│   ├── input.lua
│   ├── looknfeel.lua
│   ├── autostart.lua
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
└── metadata/
    ├── checksums.json
    ├── backup-info.json
    └── hardware.json
```

---

## Usage

`omarchy-backup` requires zero external dependencies and runs directly out of the box using Python's standard library. No installation or `pip` setup is needed.

From the repository root, run commands using the `./omarchy-backup` script runner:

### 1. Initialize Configuration & Git Remote
```bash
./omarchy-backup init

# Or non-interactive:
./omarchy-backup init --dir ~/omarchy-config-backup --remote git@github.com:user/omarchy-config.git --branch main
```

### 2. Read-Only Scan
Inspect discovered Hyprland configs, Omarchy settings, shell plugins, packages, and hardware without modifying anything:
```bash
./omarchy-backup scan
```

### 3. Back Up Configuration
Collect configuration files, calculate checksums, verify secrets, and commit to the Git repository:
```bash
./omarchy-backup backup

# Optional: commit and push immediately to GitHub:
./omarchy-backup backup --push -m "backup: updated custom bindings"
```

### 4. Check Status & Diff
Compare your live system configuration against the backup repository:
```bash
# View summary of modified, missing, or untracked files
./omarchy-backup status

# View unified diff for modified files
./omarchy-backup diff
```

### 5. Inspect History
```bash
./omarchy-backup history
```

### 6. Restore Configuration
```bash
# Preview what would change without modifying files:
./omarchy-backup restore --dry-run

# Interactive restore:
./omarchy-backup restore

# Unattended restore (e.g. fresh machine setup):
./omarchy-backup restore --yes

# Restore including machine-specific hardware (monitors):
./omarchy-backup restore --include-local
```

### 7. Emergency Rollback
If you ever want to revert your configurations to the state prior to the last restore:
```bash
./omarchy-backup rollback
```

### 8. Push / Pull
```bash
./omarchy-backup push
./omarchy-backup pull
```

---

## Running Tests

Execute the unit and integration test suite:

```bash
PYTHONPATH=src python3 -m unittest discover tests
```

---

## License

MIT License.
