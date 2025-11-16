#!/usr/bin/env python3
"""
EasySSHTunnel - A simple GUI for managing SSH tunnels on Ubuntu/Gnome
Now with system tray indicator support!
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
from gi.repository import Gtk, Gdk, GLib, Pango, AppIndicator3
import subprocess
import json
import os
import signal
import re
from pathlib import Path

class SSHTunnelManager:
    """Manages SSH tunnel processes"""

    def __init__(self):
        self.tunnels = {}  # tunnel_id -> process

    def start_tunnel(self, tunnel_id, config):
        """Start an SSH tunnel with the given configuration"""
        if tunnel_id in self.tunnels and self.tunnels[tunnel_id].poll() is None:
            return False, "Tunnel already running"

        tunnel_type = config.get('type', 'local')
        ssh_host = config.get('ssh_host', '')
        ssh_user = config.get('ssh_user', '')
        ssh_port = config.get('ssh_port', '22')

        # Build SSH command
        cmd = ['ssh', '-N']

        if tunnel_type == 'local':
            # Local port forwarding: -L local_port:remote_host:remote_port
            # Support both single port forward and multiple port forwards
            forwards = config.get('forwards', [])
            if forwards:
                # Multiple port forwards
                for forward in forwards:
                    local_port = forward.get('local_port', '')
                    remote_host = forward.get('remote_host', '')
                    remote_port = forward.get('remote_port', '')
                    tunnel_spec = f"{local_port}:{remote_host}:{remote_port}"
                    cmd.extend(['-L', tunnel_spec])
            else:
                # Legacy single port forward (backward compatibility)
                local_port = config.get('local_port', '')
                remote_host = config.get('remote_host', '')
                remote_port = config.get('remote_port', '')
                tunnel_spec = f"{local_port}:{remote_host}:{remote_port}"
                cmd.extend(['-L', tunnel_spec])
        elif tunnel_type == 'remote':
            # Remote port forwarding: -R remote_port:remote_host:local_port
            # Support both single and multiple port forwards
            forwards = config.get('forwards', [])
            if forwards:
                # Multiple port forwards
                for forward in forwards:
                    remote_port = forward.get('remote_port', '')
                    remote_host = forward.get('remote_host', '')
                    local_port = forward.get('local_port', '')
                    tunnel_spec = f"{remote_port}:{remote_host}:{local_port}"
                    cmd.extend(['-R', tunnel_spec])
            else:
                # Legacy single port forward (backward compatibility)
                local_port = config.get('local_port', '')
                remote_host = config.get('remote_host', '')
                remote_port = config.get('remote_port', '')
                tunnel_spec = f"{remote_port}:{remote_host}:{local_port}"
                cmd.extend(['-R', tunnel_spec])
        else:  # dynamic
            # Dynamic port forwarding (SOCKS proxy): -D local_port
            local_port = config.get('local_port', '')
            cmd.extend(['-D', local_port])

        # Add SSH connection details
        cmd.extend(['-p', ssh_port, f"{ssh_user}@{ssh_host}"])

        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.tunnels[tunnel_id] = process
            return True, "Tunnel started successfully"
        except Exception as e:
            return False, str(e)

    def stop_tunnel(self, tunnel_id):
        """Stop a running SSH tunnel"""
        if tunnel_id in self.tunnels:
            process = self.tunnels[tunnel_id]
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            del self.tunnels[tunnel_id]
            return True, "Tunnel stopped"
        return False, "Tunnel not found"

    def is_running(self, tunnel_id):
        """Check if a tunnel is currently running"""
        if tunnel_id in self.tunnels:
            return self.tunnels[tunnel_id].poll() is None
        return False

    def cleanup(self):
        """Stop all running tunnels"""
        for tunnel_id in list(self.tunnels.keys()):
            self.stop_tunnel(tunnel_id)


class ConfigManager:
    """Manages tunnel configuration persistence"""

    def __init__(self):
        self.config_dir = Path.home() / '.config' / 'easy-ssh-tunnel'
        self.config_file = self.config_dir / 'tunnels.json'
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load_tunnels(self):
        """Load saved tunnel configurations"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading config: {e}")
                return []
        return []

    def save_tunnels(self, tunnels):
        """Save tunnel configurations"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(tunnels, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False


class SSHCommandParser:
    """Parses SSH commands and converts them to tunnel configurations"""

    @staticmethod
    def parse_ssh_command(command):
        """
        Parse an SSH command and extract tunnel configuration.
        Supports formats like:
        - ssh -L 8080:localhost:80 user@host
        - ssh -L 27017:mongodb-0:27017 -L 27018:mongodb-1:27017 user@host
        - ssh -R 9090:localhost:8080 -p 2222 user@host
        - ssh -D 1080 user@host
        """
        # Remove leading/trailing whitespace and normalize whitespace
        command = ' '.join(command.split())

        # Basic validation - must start with ssh
        if not command.startswith('ssh'):
            raise ValueError("Command must start with 'ssh'")

        # Initialize config with defaults
        config = {
            'type': 'local',
            'ssh_port': '22',
            'local_port': '',
            'remote_host': 'localhost',
            'remote_port': '',
            'ssh_user': '',
            'ssh_host': '',
            'name': '',
            'forwards': []
        }

        # Parse all -L (local forwarding) flags
        local_matches = re.findall(r'-L\s+(\d+):([^:\s]+):(\d+)', command)
        if local_matches:
            config['type'] = 'local'
            if len(local_matches) == 1:
                # Single forward - use legacy format for backward compatibility
                config['local_port'] = local_matches[0][0]
                config['remote_host'] = local_matches[0][1]
                config['remote_port'] = local_matches[0][2]
            else:
                # Multiple forwards - use new format
                config['forwards'] = []
                for match in local_matches:
                    config['forwards'].append({
                        'local_port': match[0],
                        'remote_host': match[1],
                        'remote_port': match[2]
                    })
                # Set first forward's local_port for display purposes
                config['local_port'] = local_matches[0][0]

        # Parse all -R (remote forwarding) flags
        remote_matches = re.findall(r'-R\s+(\d+):([^:\s]+):(\d+)', command)
        if remote_matches:
            config['type'] = 'remote'
            if len(remote_matches) == 1:
                # Single forward - use legacy format for backward compatibility
                config['remote_port'] = remote_matches[0][0]
                config['remote_host'] = remote_matches[0][1]
                config['local_port'] = remote_matches[0][2]
            else:
                # Multiple forwards - use new format
                config['forwards'] = []
                for match in remote_matches:
                    config['forwards'].append({
                        'remote_port': match[0],
                        'remote_host': match[1],
                        'local_port': match[2]
                    })
                # Set first forward's remote_port for display purposes
                config['remote_port'] = remote_matches[0][0]

        # Parse -D (dynamic forwarding)
        dynamic_match = re.search(r'-D\s+(\d+)', command)
        if dynamic_match:
            config['type'] = 'dynamic'
            config['local_port'] = dynamic_match.group(1)

        # Parse -p (SSH port)
        port_match = re.search(r'-p\s+(\d+)', command)
        if port_match:
            config['ssh_port'] = port_match.group(1)

        # Parse user@host (required)
        # This should be the last non-option argument
        user_host_match = re.search(r'(?:^|\s)([^\s@]+)@([^\s]+?)(?:\s|$)', command)
        if user_host_match:
            config['ssh_user'] = user_host_match.group(1)
            config['ssh_host'] = user_host_match.group(2)
        else:
            raise ValueError("Could not find user@host in command")

        # Generate a default name
        if config['type'] == 'local':
            if config.get('forwards'):
                # Multiple forwards - show count in name
                config['name'] = f"{config['ssh_host']}_L{len(config['forwards'])}x"
            else:
                config['name'] = f"{config['ssh_host']}_L{config['local_port']}"
        elif config['type'] == 'remote':
            if config.get('forwards'):
                # Multiple forwards - show count in name
                config['name'] = f"{config['ssh_host']}_R{len(config['forwards'])}x"
            else:
                config['name'] = f"{config['ssh_host']}_R{config['remote_port']}"
        else:  # dynamic
            config['name'] = f"{config['ssh_host']}_D{config['local_port']}"

        return config

    @staticmethod
    def export_to_command(config):
        """
        Convert a tunnel configuration to an SSH command line.
        """
        tunnel_type = config.get('type', 'local')
        ssh_host = config.get('ssh_host', '')
        ssh_user = config.get('ssh_user', '')
        ssh_port = config.get('ssh_port', '22')

        # Build SSH command
        cmd = "ssh -N"

        if tunnel_type == 'local':
            forwards = config.get('forwards', [])
            if forwards:
                # Multiple port forwards
                for forward in forwards:
                    local_port = forward.get('local_port', '')
                    remote_host = forward.get('remote_host', 'localhost')
                    remote_port = forward.get('remote_port', '')
                    tunnel_spec = f"{local_port}:{remote_host}:{remote_port}"
                    cmd += f" -L {tunnel_spec}"
            else:
                # Legacy single port forward
                local_port = config.get('local_port', '')
                remote_host = config.get('remote_host', 'localhost')
                remote_port = config.get('remote_port', '')
                tunnel_spec = f"{local_port}:{remote_host}:{remote_port}"
                cmd += f" -L {tunnel_spec}"
        elif tunnel_type == 'remote':
            forwards = config.get('forwards', [])
            if forwards:
                # Multiple port forwards
                for forward in forwards:
                    remote_port = forward.get('remote_port', '')
                    remote_host = forward.get('remote_host', 'localhost')
                    local_port = forward.get('local_port', '')
                    tunnel_spec = f"{remote_port}:{remote_host}:{local_port}"
                    cmd += f" -R {tunnel_spec}"
            else:
                # Legacy single port forward
                local_port = config.get('local_port', '')
                remote_host = config.get('remote_host', 'localhost')
                remote_port = config.get('remote_port', '')
                tunnel_spec = f"{remote_port}:{remote_host}:{local_port}"
                cmd += f" -R {tunnel_spec}"
        else:  # dynamic
            local_port = config.get('local_port', '')
            cmd += f" -D {local_port}"

        # Add SSH connection details
        if ssh_port != '22':
            cmd += f" -p {ssh_port}"
        cmd += f" {ssh_user}@{ssh_host}"

        return cmd


class TunnelDialog(Gtk.Dialog):
    """Dialog for adding/editing SSH tunnel configurations"""

    def __init__(self, parent, tunnel_data=None):
        super().__init__(title="SSH Tunnel Configuration", parent=parent)
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK
        )

        self.set_default_size(400, 400)
        box = self.get_content_area()
        box.set_spacing(6)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)

        # Tunnel name
        box.pack_start(Gtk.Label(label="Tunnel Name:", xalign=0), False, False, 0)
        self.name_entry = Gtk.Entry()
        box.pack_start(self.name_entry, False, False, 0)

        # Tunnel type
        box.pack_start(Gtk.Label(label="Tunnel Type:", xalign=0), False, False, 6)
        self.type_combo = Gtk.ComboBoxText()
        self.type_combo.append("local", "Local (-L) - Forward local port to remote")
        self.type_combo.append("remote", "Remote (-R) - Forward remote port to local")
        self.type_combo.append("dynamic", "Dynamic (-D) - SOCKS proxy")
        self.type_combo.set_active(0)
        self.type_combo.connect("changed", self.on_type_changed)
        box.pack_start(self.type_combo, False, False, 0)

        # SSH connection details
        box.pack_start(Gtk.Label(label="SSH Connection:", xalign=0), False, False, 6)

        ssh_grid = Gtk.Grid()
        ssh_grid.set_column_spacing(6)
        ssh_grid.set_row_spacing(6)

        ssh_grid.attach(Gtk.Label(label="User:", xalign=0), 0, 0, 1, 1)
        self.ssh_user_entry = Gtk.Entry()
        self.ssh_user_entry.set_placeholder_text("username")
        ssh_grid.attach(self.ssh_user_entry, 1, 0, 1, 1)

        ssh_grid.attach(Gtk.Label(label="Host:", xalign=0), 0, 1, 1, 1)
        self.ssh_host_entry = Gtk.Entry()
        self.ssh_host_entry.set_placeholder_text("example.com")
        ssh_grid.attach(self.ssh_host_entry, 1, 1, 1, 1)

        ssh_grid.attach(Gtk.Label(label="Port:", xalign=0), 0, 2, 1, 1)
        self.ssh_port_entry = Gtk.Entry()
        self.ssh_port_entry.set_text("22")
        self.ssh_port_entry.set_placeholder_text("22")
        ssh_grid.attach(self.ssh_port_entry, 1, 2, 1, 1)

        box.pack_start(ssh_grid, False, False, 0)

        # Tunnel details
        box.pack_start(Gtk.Label(label="Tunnel Details:", xalign=0), False, False, 6)

        self.tunnel_grid = Gtk.Grid()
        self.tunnel_grid.set_column_spacing(6)
        self.tunnel_grid.set_row_spacing(6)

        self.local_port_label = Gtk.Label(label="Local Port:", xalign=0)
        self.tunnel_grid.attach(self.local_port_label, 0, 0, 1, 1)
        self.local_port_entry = Gtk.Entry()
        self.local_port_entry.set_placeholder_text("8080")
        self.tunnel_grid.attach(self.local_port_entry, 1, 0, 1, 1)

        self.remote_host_label = Gtk.Label(label="Remote Host:", xalign=0)
        self.tunnel_grid.attach(self.remote_host_label, 0, 1, 1, 1)
        self.remote_host_entry = Gtk.Entry()
        self.remote_host_entry.set_placeholder_text("localhost")
        self.tunnel_grid.attach(self.remote_host_entry, 1, 1, 1, 1)

        self.remote_port_label = Gtk.Label(label="Remote Port:", xalign=0)
        self.tunnel_grid.attach(self.remote_port_label, 0, 2, 1, 1)
        self.remote_port_entry = Gtk.Entry()
        self.remote_port_entry.set_placeholder_text("80")
        self.tunnel_grid.attach(self.remote_port_entry, 1, 2, 1, 1)

        box.pack_start(self.tunnel_grid, False, False, 0)

        # Multi-forward info label (shown when editing tunnels with multiple forwards)
        self.multi_forward_label = Gtk.Label()
        self.multi_forward_label.set_markup("<b>Note:</b> This tunnel has multiple port forwards.\nTo edit them, delete this tunnel and re-import the SSH command.")
        self.multi_forward_label.set_xalign(0)
        self.multi_forward_label.set_line_wrap(True)
        self.multi_forward_label.set_no_show_all(True)
        box.pack_start(self.multi_forward_label, False, False, 6)

        # Load existing data if editing
        self.tunnel_data = tunnel_data
        if tunnel_data:
            self.load_data(tunnel_data)

        self.on_type_changed(self.type_combo)
        self.show_all()

    def on_type_changed(self, combo):
        """Update UI based on selected tunnel type"""
        tunnel_type = combo.get_active_id()

        if tunnel_type == "local":
            self.local_port_label.set_text("Local Port:")
            self.local_port_entry.set_placeholder_text("8080")
            self.remote_host_label.show()
            self.remote_host_entry.show()
            self.remote_port_label.set_text("Remote Port:")
            self.remote_port_entry.set_placeholder_text("80")
            self.remote_port_label.show()
            self.remote_port_entry.show()
        elif tunnel_type == "remote":
            self.local_port_label.set_text("Local Port:")
            self.local_port_entry.set_placeholder_text("8080")
            self.remote_host_label.show()
            self.remote_host_entry.show()
            self.remote_port_label.set_text("Remote Port:")
            self.remote_port_entry.set_placeholder_text("9090")
            self.remote_port_label.show()
            self.remote_port_entry.show()
        else:  # dynamic
            self.local_port_label.set_text("SOCKS Port:")
            self.local_port_entry.set_placeholder_text("1080")
            self.remote_host_label.hide()
            self.remote_host_entry.hide()
            self.remote_port_label.hide()
            self.remote_port_entry.hide()

    def load_data(self, data):
        """Load tunnel data into the form"""
        self.name_entry.set_text(data.get('name', ''))
        self.type_combo.set_active_id(data.get('type', 'local'))
        self.ssh_user_entry.set_text(data.get('ssh_user', ''))
        self.ssh_host_entry.set_text(data.get('ssh_host', ''))
        self.ssh_port_entry.set_text(data.get('ssh_port', '22'))
        self.local_port_entry.set_text(data.get('local_port', ''))
        self.remote_host_entry.set_text(data.get('remote_host', ''))
        self.remote_port_entry.set_text(data.get('remote_port', ''))

        # Check if this has multiple forwards
        forwards = data.get('forwards', [])
        if forwards and len(forwards) > 0:
            # Show the multi-forward info label
            self.multi_forward_label.show()
            # Make fields read-only to prevent confusion
            self.local_port_entry.set_editable(False)
            self.remote_host_entry.set_editable(False)
            self.remote_port_entry.set_editable(False)

    def get_data(self):
        """Get tunnel data from the form"""
        data = {
            'name': self.name_entry.get_text(),
            'type': self.type_combo.get_active_id(),
            'ssh_user': self.ssh_user_entry.get_text(),
            'ssh_host': self.ssh_host_entry.get_text(),
            'ssh_port': self.ssh_port_entry.get_text(),
            'local_port': self.local_port_entry.get_text(),
            'remote_host': self.remote_host_entry.get_text(),
            'remote_port': self.remote_port_entry.get_text(),
        }

        # Preserve forwards if they exist in the original data
        if self.tunnel_data and 'forwards' in self.tunnel_data:
            data['forwards'] = self.tunnel_data['forwards']

        return data


class EasySSHTunnelApp(Gtk.Window):
    """Main application window"""

    def __init__(self, app_indicator=None, tunnel_manager=None, config_manager=None):
        super().__init__(title="Easy SSH Tunnel Manager")
        self.set_default_size(700, 400)
        self.set_border_width(10)

        # Set window properties for taskbar appearance
        # Note: set_wmclass is deprecated in GTK3 but may still be useful for some window managers
        # It helps window managers group windows correctly
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            try:
                self.set_wmclass("easy-ssh-tunnel", "Easy SSH Tunnel Manager")
            except:
                pass

        # Set window type hint to NORMAL to ensure taskbar visibility
        self.set_type_hint(Gdk.WindowTypeHint.NORMAL)

        # Set role for window manager identification
        self.set_role("easy-ssh-tunnel-main")

        # Ensure the window can be focused and appears in taskbar
        self.set_skip_taskbar_hint(False)
        self.set_skip_pager_hint(False)

        # Try to set icon if available
        try:
            # Try local directory first, then system installation directory
            script_dir = os.path.dirname(os.path.abspath(__file__))
            local_logo = os.path.join(script_dir, "icons", "logo.png")
            local_icon = os.path.join(script_dir, "icons", "easy-ssh-tunnel-white.png")
            system_logo = "/usr/local/share/easy-ssh-tunnel/icons/logo.png"
            system_icon = "/usr/local/share/easy-ssh-tunnel/icons/easy-ssh-tunnel-white.png"

            # Try logo.png first, then fallback to other icons
            if os.path.exists(local_logo):
                self.set_icon_from_file(local_logo)
            elif os.path.exists(system_logo):
                self.set_icon_from_file(system_logo)
            elif os.path.exists(local_icon):
                self.set_icon_from_file(local_icon)
            elif os.path.exists(system_icon):
                self.set_icon_from_file(system_icon)
            else:
                # Set icon name for fallback to theme
                self.set_icon_name("network-workgroup")
        except Exception as e:
            print(f"Could not set window icon: {e}")
            # Fallback to theme icon
            self.set_icon_name("network-workgroup")

        self.app_indicator = app_indicator
        self.tunnel_manager = tunnel_manager or SSHTunnelManager()
        self.config_manager = config_manager or ConfigManager()
        self.tunnels_config = self.config_manager.load_tunnels()

        # Main layout
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(vbox)

        # Toolbar
        toolbar = Gtk.Toolbar()
        toolbar.get_style_context().add_class(Gtk.STYLE_CLASS_PRIMARY_TOOLBAR)

        add_button = Gtk.ToolButton(stock_id=Gtk.STOCK_ADD)
        add_button.connect("clicked", self.on_add_tunnel)
        toolbar.insert(add_button, 0)

        edit_button = Gtk.ToolButton(stock_id=Gtk.STOCK_EDIT)
        edit_button.connect("clicked", self.on_edit_tunnel)
        toolbar.insert(edit_button, 1)

        remove_button = Gtk.ToolButton(stock_id=Gtk.STOCK_REMOVE)
        remove_button.connect("clicked", self.on_remove_tunnel)
        toolbar.insert(remove_button, 2)

        toolbar.insert(Gtk.SeparatorToolItem(), 3)

        start_button = Gtk.ToolButton(stock_id=Gtk.STOCK_MEDIA_PLAY)
        start_button.set_label("Start")
        start_button.connect("clicked", self.on_start_tunnel)
        toolbar.insert(start_button, 4)

        stop_button = Gtk.ToolButton(stock_id=Gtk.STOCK_MEDIA_STOP)
        stop_button.set_label("Stop")
        stop_button.connect("clicked", self.on_stop_tunnel)
        toolbar.insert(stop_button, 5)

        toolbar.insert(Gtk.SeparatorToolItem(), 6)

        import_button = Gtk.ToolButton(stock_id=Gtk.STOCK_OPEN)
        import_button.set_label("Import")
        import_button.set_tooltip_text("Import SSH command")
        import_button.connect("clicked", self.on_import_command)
        toolbar.insert(import_button, 7)

        export_button = Gtk.ToolButton(stock_id=Gtk.STOCK_SAVE_AS)
        export_button.set_label("Export")
        export_button.set_tooltip_text("Export all tunnels as SSH commands")
        export_button.connect("clicked", self.on_export_commands)
        toolbar.insert(export_button, 8)

        vbox.pack_start(toolbar, False, False, 0)

        # Tunnel list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # ListStore: name, type, ssh_host, local_port, status, config_dict
        self.tunnel_store = Gtk.ListStore(str, str, str, str, str, object)

        self.tunnel_view = Gtk.TreeView(model=self.tunnel_store)
        # Note: set_rules_hint is deprecated in GTK3 and ignored
        # Alternating row colors are now controlled by the theme

        # Columns
        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn("Name", renderer, text=0)
        column.set_min_width(120)
        self.tunnel_view.append_column(column)

        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn("Type", renderer, text=1)
        column.set_min_width(80)
        self.tunnel_view.append_column(column)

        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn("SSH Host", renderer, text=2)
        column.set_min_width(150)
        self.tunnel_view.append_column(column)

        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn("Local Port", renderer, text=3)
        column.set_min_width(80)
        self.tunnel_view.append_column(column)

        renderer = Gtk.CellRendererText()
        renderer.set_property("weight", Pango.Weight.BOLD)
        column = Gtk.TreeViewColumn("Status", renderer, text=4)
        column.set_min_width(80)
        self.tunnel_view.append_column(column)

        scrolled.add(self.tunnel_view)
        vbox.pack_start(scrolled, True, True, 0)

        # Status bar
        self.statusbar = Gtk.Statusbar()
        vbox.pack_start(self.statusbar, False, False, 0)

        # Load saved tunnels
        self.refresh_tunnel_list()

        # Update status periodically
        GLib.timeout_add_seconds(2, self.update_status)

        # Handle window close to hide instead of quit (when running with indicator)
        self.connect("delete-event", self.on_window_delete)

    def on_window_delete(self, widget, event):
        """Handle window close - hide instead of quit when using indicator"""
        if self.app_indicator:
            self.hide()
            return True  # Prevent window destruction
        else:
            self.on_quit(widget)
            return False

    def refresh_tunnel_list(self):
        """Refresh the tunnel list view"""
        self.tunnel_store.clear()
        for config in self.tunnels_config:
            tunnel_type = config.get('type', 'local').capitalize()
            ssh_host = f"{config.get('ssh_user')}@{config.get('ssh_host')}"

            # Handle multiple forwards
            forwards = config.get('forwards', [])
            if forwards and len(forwards) > 0:
                # Show first local port + count
                local_port = f"{forwards[0].get('local_port', '-')} (+{len(forwards)-1})"
            else:
                local_port = config.get('local_port', '-')

            status = "Running" if self.tunnel_manager.is_running(config.get('name')) else "Stopped"

            self.tunnel_store.append([
                config.get('name'),
                tunnel_type,
                ssh_host,
                local_port,
                status,
                config
            ])

    def update_status(self):
        """Update tunnel status in the list"""
        for row in self.tunnel_store:
            tunnel_name = row[0]
            is_running = self.tunnel_manager.is_running(tunnel_name)
            row[4] = "Running" if is_running else "Stopped"
        return True

    def on_add_tunnel(self, widget):
        """Add a new tunnel configuration"""
        dialog = TunnelDialog(self)
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            data = dialog.get_data()
            if data['name'] and data['ssh_host'] and data['ssh_user']:
                self.tunnels_config.append(data)
                self.config_manager.save_tunnels(self.tunnels_config)
                self.refresh_tunnel_list()
                self.show_message("Tunnel configuration added")
                # Update indicator menu if present
                if self.app_indicator:
                    self.app_indicator.update_menu()
            else:
                self.show_error("Please fill in all required fields")

        dialog.destroy()

    def on_edit_tunnel(self, widget):
        """Edit selected tunnel configuration"""
        selection = self.tunnel_view.get_selection()
        model, treeiter = selection.get_selected()

        if treeiter:
            config = model[treeiter][5]
            dialog = TunnelDialog(self, config)
            response = dialog.run()

            if response == Gtk.ResponseType.OK:
                new_data = dialog.get_data()
                if new_data['name'] and new_data['ssh_host'] and new_data['ssh_user']:
                    # Find and update the config
                    for i, c in enumerate(self.tunnels_config):
                        if c.get('name') == config.get('name'):
                            self.tunnels_config[i] = new_data
                            break
                    self.config_manager.save_tunnels(self.tunnels_config)
                    self.refresh_tunnel_list()
                    self.show_message("Tunnel configuration updated")
                    # Update indicator menu if present
                    if self.app_indicator:
                        self.app_indicator.update_menu()
                else:
                    self.show_error("Please fill in all required fields")

            dialog.destroy()
        else:
            self.show_error("Please select a tunnel to edit")

    def on_remove_tunnel(self, widget):
        """Remove selected tunnel configuration"""
        selection = self.tunnel_view.get_selection()
        model, treeiter = selection.get_selected()

        if treeiter:
            config = model[treeiter][5]
            tunnel_name = config.get('name')

            # Stop tunnel if running
            if self.tunnel_manager.is_running(tunnel_name):
                self.tunnel_manager.stop_tunnel(tunnel_name)

            # Remove from config
            self.tunnels_config = [c for c in self.tunnels_config if c.get('name') != tunnel_name]
            self.config_manager.save_tunnels(self.tunnels_config)
            self.refresh_tunnel_list()
            self.show_message(f"Tunnel '{tunnel_name}' removed")
            # Update indicator menu if present
            if self.app_indicator:
                self.app_indicator.update_menu()
        else:
            self.show_error("Please select a tunnel to remove")

    def on_start_tunnel(self, widget):
        """Start selected tunnel"""
        selection = self.tunnel_view.get_selection()
        model, treeiter = selection.get_selected()

        if treeiter:
            config = model[treeiter][5]
            tunnel_name = config.get('name')

            success, message = self.tunnel_manager.start_tunnel(tunnel_name, config)
            if success:
                self.show_message(f"Tunnel '{tunnel_name}' started")
                self.update_status()
                # Update indicator menu if present
                if self.app_indicator:
                    self.app_indicator.update_menu()
            else:
                self.show_error(f"Failed to start tunnel: {message}")
        else:
            self.show_error("Please select a tunnel to start")

    def on_stop_tunnel(self, widget):
        """Stop selected tunnel"""
        selection = self.tunnel_view.get_selection()
        model, treeiter = selection.get_selected()

        if treeiter:
            config = model[treeiter][5]
            tunnel_name = config.get('name')

            success, message = self.tunnel_manager.stop_tunnel(tunnel_name)
            if success:
                self.show_message(f"Tunnel '{tunnel_name}' stopped")
                self.update_status()
                # Update indicator menu if present
                if self.app_indicator:
                    self.app_indicator.update_menu()
            else:
                self.show_error(message)
        else:
            self.show_error("Please select a tunnel to stop")

    def on_import_command(self, widget):
        """Import SSH commands (supports multiple commands, one per line)"""
        dialog = Gtk.Dialog(
            title="Import SSH Commands",
            parent=self,
            flags=0
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK
        )
        dialog.set_default_size(600, 400)

        box = dialog.get_content_area()
        box.set_spacing(6)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)

        label = Gtk.Label(label="Paste SSH commands (supports multiline with \\ or indentation):")
        label.set_xalign(0)
        box.pack_start(label, False, False, 0)

        # Text view for multi-line input
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        text_view = Gtk.TextView()
        text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scrolled.add(text_view)
        box.pack_start(scrolled, True, True, 0)

        # Example text
        example_label = Gtk.Label()
        example_label.set_markup("<small><i>Examples:\n# Single tunnel\nssh -L 8080:localhost:80 user@host\n# Multiple forwards\nssh -L 27017:mongo-0:27017 \\\n    -L 27018:mongo-1:27017 -p 4022 user@host</i></small>")
        example_label.set_xalign(0)
        box.pack_start(example_label, False, False, 0)

        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            text_buffer = text_view.get_buffer()
            start_iter = text_buffer.get_start_iter()
            end_iter = text_buffer.get_end_iter()
            input_text = text_buffer.get_text(start_iter, end_iter, False).strip()

            if input_text:
                # Pre-process to handle multiline commands with backslash continuation
                # Replace backslash-newline with space
                processed_text = input_text.replace('\\\n', ' ')

                # Split by lines and process each command
                lines = processed_text.split('\n')
                imported_count = 0
                failed_count = 0
                error_messages = []
                existing_names = [t.get('name') for t in self.tunnels_config]

                # Track the last comment to use as tunnel name
                pending_name = None

                # Track lines that are part of a multiline command (without backslash)
                current_command = []
                command_start_line = 0

                for line_num, line in enumerate(lines, 1):
                    line = line.strip()

                    # Skip empty lines
                    if not line:
                        continue

                    # Check if this is a comment line
                    if line.startswith('#'):
                        # If we have a pending multiline command, process it first
                        if current_command:
                            full_command = ' '.join(current_command)
                            try:
                                config = SSHCommandParser.parse_ssh_command(full_command)
                                if pending_name:
                                    config['name'] = pending_name
                                if config['name'] in existing_names:
                                    counter = 1
                                    base_name = config['name']
                                    while f"{base_name}_{counter}" in existing_names:
                                        counter += 1
                                    config['name'] = f"{base_name}_{counter}"
                                existing_names.append(config['name'])
                                self.tunnels_config.append(config)
                                imported_count += 1
                            except Exception as e:
                                failed_count += 1
                                error_messages.append(f"Line {command_start_line}: {str(e)}")
                            current_command = []
                            pending_name = None

                        # Extract the name from the comment (remove # and whitespace)
                        comment_text = line[1:].strip()
                        if comment_text:
                            pending_name = comment_text
                        continue

                    # Check if this is the start of a new SSH command
                    if line.startswith('ssh'):
                        # If we have a pending multiline command, process it first
                        if current_command:
                            full_command = ' '.join(current_command)
                            try:
                                config = SSHCommandParser.parse_ssh_command(full_command)
                                if pending_name:
                                    config['name'] = pending_name
                                if config['name'] in existing_names:
                                    counter = 1
                                    base_name = config['name']
                                    while f"{base_name}_{counter}" in existing_names:
                                        counter += 1
                                    config['name'] = f"{base_name}_{counter}"
                                existing_names.append(config['name'])
                                self.tunnels_config.append(config)
                                imported_count += 1
                            except Exception as e:
                                failed_count += 1
                                error_messages.append(f"Line {command_start_line}: {str(e)}")
                            pending_name = None

                        # Start new command
                        current_command = [line]
                        command_start_line = line_num
                    elif current_command:
                        # This is a continuation line (doesn't start with ssh)
                        current_command.append(line)
                    else:
                        # Orphaned line that doesn't start with ssh and no current command
                        failed_count += 1
                        error_messages.append(f"Line {line_num}: Command must start with 'ssh'")

                # Process the last command if any
                if current_command:
                    full_command = ' '.join(current_command)
                    try:
                        # Parse the SSH command
                        config = SSHCommandParser.parse_ssh_command(full_command)

                        # Use the pending name from comment if available
                        if pending_name:
                            config['name'] = pending_name
                            pending_name = None  # Reset for next command

                        # Check if tunnel with this name already exists
                        if config['name'] in existing_names:
                            # Make the name unique
                            counter = 1
                            base_name = config['name']
                            while f"{base_name}_{counter}" in existing_names:
                                counter += 1
                            config['name'] = f"{base_name}_{counter}"

                        # Add to existing names to avoid duplicates in the same import
                        existing_names.append(config['name'])

                        # Add the tunnel
                        self.tunnels_config.append(config)
                        imported_count += 1

                    except ValueError as e:
                        failed_count += 1
                        error_messages.append(f"Line {line_num}: {str(e)}")
                        pending_name = None  # Reset on error
                    except Exception as e:
                        failed_count += 1
                        error_messages.append(f"Line {line_num}: {str(e)}")
                        pending_name = None  # Reset on error

                # Save if any tunnels were imported
                if imported_count > 0:
                    self.config_manager.save_tunnels(self.tunnels_config)
                    self.refresh_tunnel_list()

                    # Update indicator menu if present
                    if self.app_indicator:
                        self.app_indicator.update_menu()

                # Show results
                if imported_count > 0 and failed_count == 0:
                    self.show_message(f"Successfully imported {imported_count} tunnel(s)")
                elif imported_count > 0 and failed_count > 0:
                    result_msg = f"Imported {imported_count} tunnel(s), {failed_count} failed:\n\n" + "\n".join(error_messages[:5])
                    if len(error_messages) > 5:
                        result_msg += f"\n... and {len(error_messages) - 5} more errors"
                    dialog_result = Gtk.MessageDialog(
                        parent=self,
                        flags=0,
                        message_type=Gtk.MessageType.WARNING,
                        buttons=Gtk.ButtonsType.OK,
                        text="Partial Import"
                    )
                    dialog_result.format_secondary_text(result_msg)
                    dialog_result.run()
                    dialog_result.destroy()
                elif failed_count > 0:
                    error_msg = "Failed to import commands:\n\n" + "\n".join(error_messages[:5])
                    if len(error_messages) > 5:
                        error_msg += f"\n... and {len(error_messages) - 5} more errors"
                    self.show_error(error_msg)
                else:
                    self.show_error("No valid SSH commands found (empty lines and comments are ignored)")
            else:
                self.show_error("Please enter at least one SSH command")

        dialog.destroy()

    def on_export_commands(self, widget):
        """Export all tunnel configurations as SSH commands"""
        if not self.tunnels_config:
            self.show_error("No tunnels to export")
            return

        # Generate SSH commands
        commands = []
        for config in self.tunnels_config:
            try:
                cmd = SSHCommandParser.export_to_command(config)
                commands.append(f"# {config.get('name')}\n{cmd}\n")
            except Exception as e:
                print(f"Error exporting {config.get('name')}: {e}")

        if not commands:
            self.show_error("No valid tunnels to export")
            return

        export_text = "\n".join(commands)

        # Show export dialog
        dialog = Gtk.Dialog(
            title="Export SSH Commands",
            parent=self,
            flags=0
        )
        dialog.add_buttons(
            Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE
        )
        dialog.set_default_size(600, 400)

        box = dialog.get_content_area()
        box.set_spacing(6)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)

        label = Gtk.Label(label="SSH commands for all tunnels:")
        label.set_xalign(0)
        box.pack_start(label, False, False, 0)

        # Text view to display commands
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        text_view = Gtk.TextView()
        text_view.set_editable(False)
        text_view.set_cursor_visible(False)
        text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        text_buffer = text_view.get_buffer()
        text_buffer.set_text(export_text)
        scrolled.add(text_view)
        box.pack_start(scrolled, True, True, 0)

        # Copy to clipboard button
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        copy_button = Gtk.Button.new_with_label("Copy to Clipboard")
        copy_button.connect("clicked", self.on_copy_to_clipboard, text_buffer)
        button_box.pack_start(copy_button, False, False, 0)
        box.pack_start(button_box, False, False, 0)

        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def on_copy_to_clipboard(self, widget, text_buffer):
        """Copy text buffer contents to clipboard"""
        start_iter = text_buffer.get_start_iter()
        end_iter = text_buffer.get_end_iter()
        text = text_buffer.get_text(start_iter, end_iter, False)

        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)
        self.show_message("Copied to clipboard")

    def show_message(self, message):
        """Show a message in the statusbar"""
        context_id = self.statusbar.get_context_id("main")
        self.statusbar.pop(context_id)
        self.statusbar.push(context_id, message)

    def show_error(self, message):
        """Show an error dialog"""
        dialog = Gtk.MessageDialog(
            parent=self,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=message
        )
        dialog.run()
        dialog.destroy()

    def on_quit(self, widget):
        """Cleanup and quit"""
        self.tunnel_manager.cleanup()
        Gtk.main_quit()


class SSHTunnelIndicator:
    """System tray indicator for SSH tunnels"""

    def __init__(self):
        self.tunnel_manager = SSHTunnelManager()
        self.config_manager = ConfigManager()
        self.tunnels_config = self.config_manager.load_tunnels()

        # Setup custom icon theme path
        # Try local directory first, then system installation directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        local_icons = os.path.join(script_dir, "icons")
        system_icons = "/usr/local/share/easy-ssh-tunnel/icons"

        if os.path.exists(local_icons):
            self.icon_theme_path = local_icons
        elif os.path.exists(system_icons):
            self.icon_theme_path = system_icons
        else:
            self.icon_theme_path = local_icons  # Fallback to local

        # Icon names (without extension)
        self.icon_name_white = "easy-ssh-tunnel-white"
        self.icon_name_green = "easy-ssh-tunnel-green"

        # Create the indicator with icon theme path
        self.indicator = AppIndicator3.Indicator.new(
            "easy-ssh-tunnel",
            self.icon_name_white,
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_icon_theme_path(self.icon_theme_path)
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title("SSH Tunnel Manager")

        # Set attention icon for when tunnels are active (green)
        self.indicator.set_attention_icon(self.icon_name_green)

        # Store current state
        self.currently_active = False

        # Create main window (hidden initially) and pass shared managers
        self.window = EasySSHTunnelApp(
            app_indicator=self,
            tunnel_manager=self.tunnel_manager,
            config_manager=self.config_manager
        )

        # Build the menu
        self.menu = Gtk.Menu()
        self.build_menu()
        self.indicator.set_menu(self.menu)

        # Update menu and icon periodically to refresh status
        GLib.timeout_add_seconds(2, self.update_menu_status)

    def build_menu(self):
        """Build the indicator menu"""
        # Clear existing menu items
        for item in self.menu.get_children():
            self.menu.remove(item)

        # Store references to tunnel menu items for status updates
        self.tunnel_menu_items = {}

        # Add tunnels section
        if self.tunnels_config:
            for config in self.tunnels_config:
                tunnel_name = config.get('name', 'Unknown')
                is_running = self.tunnel_manager.is_running(tunnel_name)

                # Create menu item with status indicator and name
                # Using Unicode colored circles that work better with system themes
                if is_running:
                    # Green dot for connected
                    label_text = f"🟢 {tunnel_name}"
                else:
                    # Red dot for disconnected
                    label_text = f"🔴 {tunnel_name}"

                menu_item = Gtk.MenuItem(label=label_text)

                # Toggle tunnel on/off when clicked
                menu_item.connect("activate", self.toggle_tunnel, config)
                menu_item.show_all()
                self.menu.append(menu_item)

                # Store reference for status updates
                self.tunnel_menu_items[tunnel_name] = menu_item

            # Separator
            separator = Gtk.SeparatorMenuItem()
            separator.show()
            self.menu.append(separator)
        else:
            # No tunnels configured
            item = Gtk.MenuItem(label="No tunnels configured")
            item.set_sensitive(False)
            item.show()
            self.menu.append(item)

            separator = Gtk.SeparatorMenuItem()
            separator.show()
            self.menu.append(separator)

        # Open settings (right-click behavior on left-click item)
        settings_item = Gtk.MenuItem(label="Manage Tunnels...")
        settings_item.connect("activate", self.show_main_window)
        settings_item.show()
        self.menu.append(settings_item)

        # Quit
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self.quit_app)
        quit_item.show()
        self.menu.append(quit_item)

    def update_menu(self):
        """Rebuild the menu (called when tunnels are added/removed/edited)"""
        self.tunnels_config = self.config_manager.load_tunnels()
        self.window.tunnels_config = self.tunnels_config
        self.window.refresh_tunnel_list()
        self.build_menu()

    def update_menu_status(self):
        """Update menu status indicators periodically without rebuilding menu"""
        # Check if any tunnel is running
        any_running = False
        if hasattr(self, 'tunnel_menu_items'):
            for tunnel_name, menu_item in self.tunnel_menu_items.items():
                is_running = self.tunnel_manager.is_running(tunnel_name)
                if is_running:
                    any_running = True
                    # Green dot for connected
                    menu_item.set_label(f"🟢 {tunnel_name}")
                else:
                    # Red dot for disconnected
                    menu_item.set_label(f"🔴 {tunnel_name}")

        # Update tray icon status based on connection status
        # Switch between ACTIVE (normal icon) and ATTENTION (active icon)
        if any_running and not self.currently_active:
            self.indicator.set_status(AppIndicator3.IndicatorStatus.ATTENTION)
            self.currently_active = True
        elif not any_running and self.currently_active:
            self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            self.currently_active = False

        return True

    def toggle_tunnel(self, widget, config):
        """Toggle tunnel on/off"""
        tunnel_name = config.get('name')

        if self.tunnel_manager.is_running(tunnel_name):
            # Stop the tunnel
            self.tunnel_manager.stop_tunnel(tunnel_name)
        else:
            # Start the tunnel
            self.tunnel_manager.start_tunnel(tunnel_name, config)

        # Update menu and window
        self.update_menu()

    def show_main_window(self, widget=None):
        """Show the main configuration window"""
        self.window.show_all()
        self.window.present()
        # Request focus and move to current workspace
        self.window.present_with_time(Gdk.CURRENT_TIME)
        self.window.set_keep_above(False)  # Ensure it's a normal window

    def quit_app(self, widget):
        """Quit the application"""
        self.tunnel_manager.cleanup()
        Gtk.main_quit()


def main():
    # Check if we should run with indicator (default)
    import sys

    use_indicator = True
    if '--no-indicator' in sys.argv:
        use_indicator = False

    if use_indicator:
        try:
            # Run with system tray indicator
            indicator = SSHTunnelIndicator()
            signal.signal(signal.SIGINT, signal.SIG_DFL)  # Allow Ctrl+C to quit
            Gtk.main()
        except Exception as e:
            print(f"Failed to start with indicator: {e}")
            print("Falling back to window mode...")
            app = EasySSHTunnelApp()
            app.show_all()
            Gtk.main()
    else:
        # Run without indicator (just the window)
        app = EasySSHTunnelApp()
        app.show_all()
        Gtk.main()


if __name__ == '__main__':
    main()
