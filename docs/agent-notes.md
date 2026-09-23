# Agent Notes

Repo notes for coding agents. The entry files CLAUDE.md, AGENTS.md and GEMINI.md are generated routers from workspace-wiki and link here.

## Project Overview

Easy SSH Tunnel Manager is a GTK3-based GUI application for managing SSH tunnels on Ubuntu/Gnome with system tray integration. It's a single-file Python application that provides a user-friendly interface for creating, managing, and monitoring multiple SSH tunnel configurations.

## Architecture

### Core Components

The application consists of four main classes in `easy_ssh_tunnel.py`:

1. **SSHTunnelManager** (lines 17-82): Manages SSH tunnel processes
   - Maintains a dictionary of tunnel processes (`tunnel_id -> subprocess.Popen`)
   - Handles starting/stopping tunnels via subprocess calls to `ssh` command
   - Supports three tunnel types: local (`-L`), remote (`-R`), and dynamic (`-D`)

2. **ConfigManager** (lines 85-112): Handles configuration persistence
   - Stores tunnel configurations in `~/.config/easy-ssh-tunnel/tunnels.json`
   - Loads/saves tunnel configurations as JSON

3. **EasySSHTunnelApp** (lines 262-535): Main GTK3 window
   - Provides full GUI with TreeView list of tunnels
   - Toolbar buttons for Add/Edit/Remove/Start/Stop operations
   - Can run standalone or integrated with SSHTunnelIndicator
   - Updates tunnel status every 2 seconds via GLib.timeout_add_seconds()

4. **SSHTunnelIndicator** (lines 538-666): System tray integration
   - Uses AppIndicator3 for top bar icon
   - Provides quick menu with all tunnels and status indicators
   - Shares SSHTunnelManager instance with main window
   - Green dot (●) = running, gray circle (○) = stopped

### Key Relationships

- SSHTunnelIndicator creates and manages an instance of EasySSHTunnelApp
- Both share the same SSHTunnelManager and ConfigManager instances
- Window can be hidden and reopened without destroying tunnel processes
- Menu rebuilds periodically (every 2 seconds) to update status indicators

## Development Commands

### Run the application

```bash
# With system tray (default)
./easy_ssh_tunnel.py

# Window mode only (no system tray)
./easy_ssh_tunnel.py --no-indicator
```

### Install system dependencies

```bash
sudo apt-get update
sudo apt-get install python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-appindicator3-0.1
```

### Install system-wide

```bash
sudo ./install.sh
```

This installs the script to `/usr/local/bin/` and creates a desktop entry.

### Configuration location

Tunnel configurations are stored at: `~/.config/easy-ssh-tunnel/tunnels.json`

## Important Implementation Details

### SSH Command Construction

The application builds SSH commands in `SSHTunnelManager.start_tunnel()`:
- **Local**: `ssh -N -L local_port:remote_host:remote_port -p ssh_port user@ssh_host`
- **Remote**: `ssh -N -R remote_port:remote_host:local_port -p ssh_port user@ssh_host`
- **Dynamic**: `ssh -N -D local_port -p ssh_port user@ssh_host`

All tunnels use `-N` flag (no remote command execution).

### Tunnel Configuration Schema

Each tunnel config dictionary contains:
- `name`: Unique identifier and display name
- `type`: "local", "remote", or "dynamic"
- `ssh_user`, `ssh_host`, `ssh_port`: SSH connection details
- `local_port`: Local port for forwarding or SOCKS proxy
- `remote_host`, `remote_port`: Remote destination (not used for dynamic type)

### Process Management

- Tunnels are stored as subprocess.Popen objects keyed by tunnel name
- Status checked via `process.poll()` (None = running)
- Cleanup uses terminate() with 5-second timeout, then kill() if needed
- All tunnels cleaned up on application exit

### UI Update Pattern

Status updates happen in two ways:
1. Main window: GLib.timeout_add_seconds(2, self.update_status) updates TreeView
2. Indicator menu: GLib.timeout_add_seconds(2, self.update_menu_status) rebuilds menu

Both share the same SSHTunnelManager, so status is always synchronized.

### Window Management with Indicator

When running with indicator (default):
- Window close (delete-event) hides window instead of quitting
- "Manage Tunnels..." menu item shows the window via `window.present()`
- Actual quit only happens via "Quit" menu item in indicator

## Testing SSH Tunnels

To manually verify tunnel functionality:

```bash
# Check if SSH tunnel process is running
ps aux | grep "ssh -N"

# Test local tunnel (example: forwarding to port 80)
curl localhost:8080

# Test dynamic tunnel (SOCKS proxy on 1080)
curl --socks5 localhost:1080 http://example.com
```

## Dependencies

- Python 3.6+
- PyGObject >= 3.30.0 (from requirements.txt)
- GTK3 and GObject Introspection bindings
- AppIndicator3 (for system tray)
- OpenSSH client (ssh command must be available)

## Git Commits & Pull Requests

**CRITICAL: No AI attribution in commits or pull requests.**

- NEVER add `Co-Authored-By` lines mentioning Claude, Anthropic, or any AI
- NEVER include "Claude", "Claude Code", "AI-generated", "AI-assisted", or similar in commit messages
- NEVER reference AI tools in pull request titles or descriptions
- Commit messages must be clean, professional, and written as if authored by a human developer
