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
echo "[1/5] Installing Python dependencies..."
pip3 install -r "$REPO_DIR/requirements.txt" --break-system-packages --quiet
echo "      Done."

# 2. .env
echo "[2/5] Setting up .env..."
if [ ! -f "$REPO_DIR/.env" ]; then
    cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
    echo "      Created .env from .env.example."
    echo "      >>> Fill in FIREBASE_SERVICE_ACCOUNT_JSON and GKM_KIOSK_ID before starting. <<<"
else
    echo "      .env already exists — skipping."
fi

# 3. Autostart on boot (XDG autostart — picked up by lxsession / labwc)
echo "[3/5] Installing autostart entry..."
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

# 4. Configure PCManFM to execute .desktop files on double-click without prompting.
#    quick_exec=1  — skip "Execute or Open?" for executables
#    metadata::trusted yes — marks this specific .desktop file as trusted (libfm requires "yes")
#    PCManFM must be restarted for libfm.conf to take effect.
echo "[4/5] Configuring PCManFM (quick_exec) and restarting desktop..."
LIBFM_CONF=~/.config/libfm/libfm.conf
if [ -f "$LIBFM_CONF" ]; then
    sed -i 's/^quick_exec=0/quick_exec=1/' "$LIBFM_CONF"
else
    mkdir -p ~/.config/libfm
    printf '[config]\nquick_exec=1\n' > "$LIBFM_CONF"
fi

# Restart PCManFM so it picks up the new libfm.conf immediately.
# lxsession uses '@' prefix to auto-respawn it; if that doesn't happen within
# 3 s we start it ourselves.
pkill -f "pcmanfm --desktop" 2>/dev/null || true
sleep 3
if ! pgrep -f "pcmanfm --desktop" > /dev/null 2>&1; then
    /usr/bin/pcmanfm --desktop --profile LXDE-pi &
    sleep 1
fi
echo "      Done."

# 5. Desktop shortcut
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
# Mark as trusted — libfm checks for the string "yes" (not "true")
gio set ~/Desktop/mygreenstar-kiosk.desktop metadata::trusted yes
echo "      Installed: ~/Desktop/mygreenstar-kiosk.desktop"

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit $REPO_DIR/.env — fill in FIREBASE_SERVICE_ACCOUNT_JSON, GKM_KIOSK_ID,"
echo "     GKM_KIOSK_NAME, and GKM_KIOSK_LOCATION."
echo "  2. Reboot — the kiosk will start automatically on login."
echo "  3. Or start now: DISPLAY=:0 $EXEC"
