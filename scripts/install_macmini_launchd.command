#!/bin/zsh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="kr.ningning.thread2-uploader"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$PROJECT_DIR/logs"

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"
chmod +x "$PROJECT_DIR/scripts/thread2_uploader_launchd.zsh"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>$PROJECT_DIR/scripts/thread2_uploader_launchd.zsh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$PROJECT_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/thread2-uploader.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/thread2-uploader.err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

echo
echo "Installed $LABEL"
echo "Dashboard: http://127.0.0.1:8782/web/index.html"
echo "Same Wi-Fi: http://$(/bin/hostname -s).local:8782/web/index.html"
echo "Logs:"
echo "  $LOG_DIR/thread2-uploader.out.log"
echo "  $LOG_DIR/thread2-uploader.err.log"
echo
