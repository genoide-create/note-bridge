#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DATA_ROOT="${NOTE_BRIDGE_HOME:-$ROOT}"
RUNTIME="$HOME/.plauddb"
AGENT="$HOME/Library/LaunchAgents/com.note-bridge.sync.plist"
LABEL="com.note-bridge.sync"
UID_VALUE="$(id -u)"

mkdir -p "$RUNTIME/logs" "$HOME/Library/LaunchAgents"
cp "$ROOT/sync_plaud_to_notion.py" "$RUNTIME/sync_plaud_to_notion.py"
if [ -f "$DATA_ROOT/.env" ]; then
  cp "$DATA_ROOT/.env" "$RUNTIME/.env"
elif [ -f "$ROOT/.env" ]; then
  cp "$ROOT/.env" "$RUNTIME/.env"
else
  : > "$RUNTIME/.env"
fi
if [ -f "$DATA_ROOT/category_rules.json" ]; then
  cp "$DATA_ROOT/category_rules.json" "$RUNTIME/category_rules.json"
elif [ -f "$ROOT/category_rules.json" ]; then
  cp "$ROOT/category_rules.json" "$RUNTIME/category_rules.json"
fi
cat > "$AGENT" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>

  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>$RUNTIME/sync_plaud_to_notion.py</string>
    <string>--today</string>
    <string>--limit</string>
    <string>20</string>
  </array>

  <key>WorkingDirectory</key>
  <string>$RUNTIME</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>22</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
</dict>
</plist>
PLIST

chmod 700 "$RUNTIME"
chmod 600 "$RUNTIME/.env"
[ ! -f "$RUNTIME/category_rules.json" ] || chmod 600 "$RUNTIME/category_rules.json"
chmod +x "$RUNTIME/sync_plaud_to_notion.py"

launchctl bootout "gui/$UID_VALUE/$LABEL" >/dev/null 2>&1 || true
launchctl bootout "gui/$UID_VALUE" "$AGENT" >/dev/null 2>&1 || true
launchctl enable "gui/$UID_VALUE/$LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID_VALUE" "$AGENT"
if grep -q '^PLAUDDB_AUTORUN_ENABLED=false$' "$RUNTIME/.env" 2>/dev/null; then
  launchctl disable "gui/$UID_VALUE/$LABEL"
else
  launchctl enable "gui/$UID_VALUE/$LABEL"
fi
launchctl print "gui/$UID_VALUE/$LABEL" | sed -n '1,90p'
