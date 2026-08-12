#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
APP="$ROOT/Note Bridge.app"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

/usr/bin/swiftc "$ROOT/macapp/NoteBridgeApp.swift" \
  -framework Cocoa \
  -framework WebKit \
  -o "$APP/Contents/MacOS/NoteBridge"

cp "$ROOT/plauddb_web.py" "$APP/Contents/Resources/plauddb_web.py"
cp "$ROOT/sync_plaud_to_notion.py" "$APP/Contents/Resources/sync_plaud_to_notion.py"
cp "$ROOT/install_launchd.sh" "$APP/Contents/Resources/install_launchd.sh"
cp "$ROOT/com.note-bridge.sync.plist" "$APP/Contents/Resources/com.note-bridge.sync.plist"
cp "$ROOT/category_rules.json" "$APP/Contents/Resources/category_rules.json"
chmod +x "$APP/Contents/Resources/install_launchd.sh"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>NoteBridge</string>
  <key>CFBundleIdentifier</key>
  <string>com.note-bridge.app</string>
  <key>CFBundleName</key>
  <string>Note Bridge</string>
  <key>CFBundleDisplayName</key>
  <string>Note Bridge</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

chmod +x "$APP/Contents/MacOS/NoteBridge"
echo "Built $APP"
