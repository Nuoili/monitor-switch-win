#!/bin/bash
# 保持 Mac 唤醒（只运行一次，之后永久生效）
#
# 作用：显示器切到 Windows 后，Mac 不要因为"太久没动"而关掉显示输出。
#       macOS 默认接电源 10 分钟、用电池 2 分钟就"关闭显示器"，
#       一旦关屏，GPU 就不再往 HDMI 口送信号，切回来自然是"HDMI 无信号"。
#
# 原理：caffeinate 常驻，阻止「显示器睡眠」和「系统空闲睡眠」。
# 不影响合盖行为 —— 合盖要用外接屏还需要接电源 + 外接键鼠（macOS clamshell 条件）。

PLIST="$HOME/Library/LaunchAgents/com.monswitch.awake.plist"

mkdir -p "$HOME/Library/LaunchAgents"

if [ -f "$PLIST" ] && launchctl list 2>/dev/null | grep -q com.monswitch.awake; then
  osascript -e 'display dialog "保持唤醒已经开着了，不用重复设置。" buttons {"好"} default button 1'
  exit 0
fi

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.monswitch.awake</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/caffeinate</string>
        <string>-d</string>
        <string>-i</string>
        <string>-s</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null
if launchctl load "$PLIST"; then
  osascript -e 'display dialog "已开启保持唤醒。\n\n从现在起 Mac 接电源时不会关屏、不会空闲睡眠，显示器切到 Windows 多久都还能切回来看到画面。\n\n取消方法：双击「5-取消保持唤醒.command」" buttons {"好"} default button 1'
else
  osascript -e 'display dialog "设置失败。请把本文件拖进「终端」手动运行一次。" buttons {"好"} default button 1 with icon caution'
fi
