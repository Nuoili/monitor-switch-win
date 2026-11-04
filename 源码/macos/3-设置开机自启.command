#!/bin/bash
# 设置开机（登录）自启动：开机后自动把显示器切到 HDMI（Mac）
# 只运行一次就退出，不会常驻后台。

DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.monswitch.autostart.plist"

mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.monswitch.autostart</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$DIR/2-切到Mac.command</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null
if launchctl load "$PLIST"; then
  osascript -e 'display dialog "已设置开机自启：登录后自动把显示器切到 HDMI（Mac）。\n\n卸载方法：删除 ~/Library/LaunchAgents/com.monswitch.autostart.plist" buttons {"好"} default button 1'
else
  osascript -e 'display dialog "设置失败，请把本文件拖进「终端」手动运行一次。" buttons {"好"} default button 1 with icon caution'
fi
