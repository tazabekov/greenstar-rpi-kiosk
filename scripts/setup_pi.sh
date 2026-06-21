#!/usr/bin/env bash
# setup_pi.sh — run once on a fresh Pi after cloning the repo.
# Sets up Python deps, .env, autostart on boot, and a desktop shortcut.
#
# Usage:
#   cd /home/<user>/greenstar-rpi-kiosk
#   bash scripts/setup_pi.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON=/usr/bin/python3
ICON="$REPO_DIR/assets/icon.svg"
EXEC="$PYTHON $REPO_DIR/main.py"

echo "=== GreenStar Kiosk — Pi Setup ==="
echo "Repo: $REPO_DIR"
echo ""

# 1. Python dependencies
echo "[1/4] Installing Python dependencies..."
pip3 install -r "$REPO_DIR/requirements.txt" --break-system-packages --quiet
echo "      Done."

# 2. .env
echo "[2/4] Setting up .env..."
if [ ! -f "$REPO_DIR/.env" ]; then
    cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
    echo "      Created .env from .env.example."
    echo "      >>> Fill in FIREBASE_SERVICE_ACCOUNT_JSON and GKM_KIOSK_ID before starting. <<<"
else
    echo "      .env already exists — skipping."
fi

# 3. Autostart on boot (XDG autostart — works with labwc + any Wayland/X session manager)
echo "[3/4] Installing autostart entry..."
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/mygreenstar-kiosk.desktop <<DESKTOP
[Desktop Entry]
Name=MyGreenStar Kiosk
Exec=$EXEC
Type=Application
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=3
DESKTOP
echo "      Installed: ~/.config/autostart/mygreenstar-kiosk.desktop"

# 4. Make desktop .desktop files execute on double-click without prompting
echo "[4/5] Configuring PCManFM to execute .desktop files on double-click..."
LIBFM_CONF=~/.config/libfm/libfm.conf
if [ -f "$LIBFM_CONF" ]; then
    sed -i 's/^quick_exec=0/quick_exec=1/' "$LIBFM_CONF"
else
    mkdir -p ~/.config/libfm
    printf '[config]\nquick_exec=1\n' > "$LIBFM_CONF"
fi
echo "      Done."

# 5. Desktop shortcut (pcmanfm shows files in ~/Desktop as icons on the labwc desktop)
echo "[5/5] Creating desktop shortcut..."
mkdir -p ~/Desktop
cat > ~/Desktop/mygreenstar-kiosk.desktop <<DESKTOP
[Desktop Entry]
Name=MyGreenStar Kiosk
Comment=Coffee kiosk payment terminal
Exec=$EXEC
Icon=$ICON
Type=Application
Terminal=false
StartupNotify=false
DESKTOP
chmod +x ~/Desktop/mygreenstar-kiosk.desktop
# Mark as trusted so PCManFM launches it directly without "Execute or Open?" prompt
gio set ~/Desktop/mygreenstar-kiosk.desktop metadata::trusted yes
echo "      Installed: ~/Desktop/mygreenstar-kiosk.desktop (double-click to launch)"

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit $REPO_DIR/.env — fill in FIREBASE_SERVICE_ACCOUNT_JSON, GKM_KIOSK_ID,"
echo "     GKM_KIOSK_NAME, and GKM_KIOSK_LOCATION."
echo "  2. Reboot — the kiosk will start automatically."
echo "  3. Or start now: DISPLAY=:0 $EXEC"
