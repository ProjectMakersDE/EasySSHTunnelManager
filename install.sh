#!/bin/bash
# Installation script for Easy SSH Tunnel Manager

echo "Easy SSH Tunnel Manager - Installation Script"
echo "=============================================="
echo

# Check if running with sudo
if [ "$EUID" -ne 0 ]; then
    echo "This script needs to be run with sudo to install system-wide."
    echo "Usage: sudo ./install.sh"
    exit 1
fi

# Check for required packages
echo "Checking dependencies..."
if ! dpkg -l | grep -q python3-gi; then
    echo "Installing required packages..."
    apt-get update
    apt-get install -y python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-appindicator3-0.1
else
    echo "GTK dependencies are installed."
fi

# Check for AppIndicator3
if ! dpkg -l | grep -q gir1.2-appindicator3; then
    echo "Installing AppIndicator3..."
    apt-get install -y gir1.2-appindicator3-0.1
else
    echo "AppIndicator3 is installed."
fi

# Generate icons
echo "Generating tray icons..."
python3 create_icons.py

# Copy script to /usr/local/bin
echo "Installing application..."
cp easy_ssh_tunnel.py /usr/local/bin/
chmod +x /usr/local/bin/easy_ssh_tunnel.py

# Copy icons
echo "Installing icons..."
mkdir -p /usr/local/share/easy-ssh-tunnel/icons
cp icons/*.png /usr/local/share/easy-ssh-tunnel/icons/

# Copy desktop entry
echo "Installing desktop entry..."
cp easy-ssh-tunnel.desktop /usr/share/applications/

# Update desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database /usr/share/applications/
fi

echo
echo "Installation complete!"
echo "You can now launch 'Easy SSH Tunnel Manager' from your applications menu,"
echo "or run it from the terminal with: easy_ssh_tunnel.py"
echo
echo "The application will run in system tray mode by default."
echo "To run without the system tray indicator, use: easy_ssh_tunnel.py --no-indicator"
