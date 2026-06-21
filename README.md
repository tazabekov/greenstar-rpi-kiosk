# MyGreenStar Kiosk

Real-time CPU usage and temperature dashboard for Raspberry Pi 5.

## Requirements

- Python 3.11+
- PyQt5 (`sudo apt install python3-pyqt5`)
- psutil (`sudo apt install python3-psutil`)

Both are already installed on this Pi.

## Run

```bash
python3 main.py
```

Press **Esc** to quit during development.

## Autostart on boot

The file `~/.config/autostart/mygreenstar-kiosk.desktop` configures the app
to launch automatically when the LXDE desktop session starts.

To disable autostart:
```bash
rm ~/.config/autostart/mygreenstar-kiosk.desktop
```
