#!/bin/bash
# 取消「保持 Mac 唤醒」，恢复 macOS 原本的自动关屏 / 睡眠行为

PLIST="$HOME/Library/LaunchAgents/com.monswitch.awake.plist"

launchctl unload "$PLIST" 2>/dev/null
rm -f "$PLIST"

if [ -f "$PLIST" ]; then
  osascript -e 'display dialog "取消失败，请把本文件拖进「终端」手动运行一次。" buttons {"好"} default button 1 with icon caution'
else
  osascript -e 'display dialog "已取消保持唤醒，Mac 恢复正常的自动关屏/睡眠。" buttons {"好"} default button 1'
fi
