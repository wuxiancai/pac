#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../../.." && pwd)
PACKAGE_DIR="$REPO_ROOT/poc/macos-audio"
APP_DIR="$REPO_ROOT/.poc-data/backend-lifecycle-poc.app"

swift build --package-path "$PACKAGE_DIR" --product backend-lifecycle-poc
mkdir -p "$APP_DIR/Contents/MacOS"
cp "$PACKAGE_DIR/.build/debug/backend-lifecycle-poc" "$APP_DIR/Contents/MacOS/backend-lifecycle-poc"
cat > "$APP_DIR/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>backend-lifecycle-poc</string>
<key>CFBundleIdentifier</key><string>com.example.pac.backend-lifecycle-poc</string>
<key>CFBundleName</key><string>Backend Lifecycle POC</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$APP_DIR/Contents/Info.plist" >/dev/null
printf 'Built %s\n' "$APP_DIR"
