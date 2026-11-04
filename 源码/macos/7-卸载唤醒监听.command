#!/bin/bash
# 卸载「唤醒监听」，恢复干净状态

PLIST="$HOME/Library/LaunchAgents/com.monswitch.wakelistener.plist"
CONF="$HOME/.monswitch"

launchctl bootout "gui/$UID/com.monswitch.wakelistener" 2>/dev/null
launchctl unload "$PLIST" 2>/dev/null
pkill -f mac_wake_listener.py 2>/dev/null
rm -f "$PLIST"

if [ -f "$PLIST" ]; then
  osascript -e 'display dialog "卸载失败，请把本文件拖进「终端」手动运行一次。" buttons {"好"} default button 1 with icon caution'
else
  osascript -e "display dialog \"已卸载唤醒监听。\n\n日志和配置还留在 $CONF，不用了可以整个删掉。\" buttons {\"好\"} default button 1"
fi
