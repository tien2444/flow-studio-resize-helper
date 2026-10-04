#!/bin/zsh
set -euo pipefail

PACKAGE_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_ROOT="$HOME/Library/Application Support/FlowStudioWebHelper"
PROCESSOR_DIR="$INSTALL_ROOT/processor-v12"
DATA_DIR="$INSTALL_ROOT/data"
LOG_DIR="$INSTALL_ROOT/logs"
PLIST="$HOME/Library/LaunchAgents/com.ikame.flowstudio.processor.plist"
LABEL="com.ikame.flowstudio.processor"

if [[ ! -x "$PACKAGE_DIR/processor/flow-local-processor" ]]; then
  echo "Khong tim thay Flow Studio Helper trong goi cai dat."
  read -r "?Nhan Enter de dong..."
  exit 1
fi

mkdir -p "$INSTALL_ROOT" "$DATA_DIR" "$LOG_DIR" "$HOME/Library/LaunchAgents"
ditto "$PACKAGE_DIR/processor" "$PROCESSOR_DIR"
chmod +x "$PROCESSOR_DIR/flow-local-processor"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PROCESSOR_DIR/flow-local-processor</string>
    <string>--port</string><string>43127</string>
    <string>--data-dir</string><string>$DATA_DIR</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict><key>FLOW_PROCESSOR_ORIGINS</key><string>https://flow-studio-web-one.vercel.app</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOG_DIR/stdout.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/stderr.log</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$UID/$LABEL" >/dev/null 2>&1 || true
sleep 1
if ! launchctl bootstrap "gui/$UID" "$PLIST"; then
  sleep 2
  launchctl bootstrap "gui/$UID" "$PLIST"
fi
launchctl kickstart -k "gui/$UID/$LABEL"

READY=0
for _ in {1..30}; do
  VERSION="$(curl -fsS -H 'Origin: https://flow-studio-web-one.vercel.app' http://127.0.0.1:43127/session 2>/dev/null | sed -n 's/.*"version": *\([0-9][0-9]*\).*/\1/p')"
  if [[ "$VERSION" -eq 12 ]]; then
    READY=1
    break
  fi
  sleep 1
done
if [[ "$READY" -eq 1 ]]; then
  echo ""
  echo "Flow Studio Helper da cai xong va dang chay."
  echo "Quay lai Flow Studio va bam Kiem tra lai."
else
  echo ""
  echo "Da cai Helper nhung chua ket noi duoc. Hay mo lai install.command hoac khoi dong lai may."
fi
read -r "?Nhan Enter de dong..."
