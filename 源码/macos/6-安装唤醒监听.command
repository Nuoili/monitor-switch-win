#!/bin/bash
# 安装「唤醒监听」：让 Windows 端切回 HDMI 时能踢开显示器的"无信号"僵局
#
# 做了什么：
#   1. 检查 python3 / 安装 displayplacer（缺什么装什么）
#   2. 把 mac_wake_listener.py 复制到 ~/.monswitch/
#   3. 装一个 LaunchAgent，登录常驻监听 UDP 9998
#
# 卸载：双击「7-卸载唤醒监听.command」

set -u

DIR="$(cd "$(dirname "$0")" && pwd)"
HOME_DIR="$HOME"
CONF="$HOME_DIR/.monswitch"
PLIST="$HOME_DIR/Library/LaunchAgents/com.monswitch.wakelistener.plist"
SRC="$DIR/mac_wake_listener.py"

say() {
  osascript -e "display dialog \"$1\" buttons {\"好\"} default button 1 ${2:-}" >/dev/null 2>&1
  echo "$1"
}

fail() {
  osascript -e "display dialog \"$1\" buttons {\"好\"} default button 1 with icon caution" >/dev/null 2>&1
  echo "失败：$1" >&2
  exit 1
}

echo "=== 1/4 检查 python3 ==="
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  say "缺少 python3。请先装 Xcode 命令行工具（终端执行 xcode-select --install），装完再运行本文件。"
  fail "没有 python3"
fi
echo "python3 -> $PY"

echo "=== 2/4 检查 displayplacer ==="
DP=""
for p in /opt/homebrew/bin/displayplacer /usr/local/bin/displayplacer /usr/bin/displayplacer; do
  [ -x "$p" ] && DP="$p" && break
done

if [ -z "$DP" ]; then
  if command -v brew >/dev/null 2>&1; then
    echo "没装 displayplacer，正在用 Homebrew 安装（需要联网，1-2 分钟）……"
    brew install jakehilborn/jakehilborn/displayplacer
    for p in /opt/homebrew/bin/displayplacer /usr/local/bin/displayplacer; do
      [ -x "$p" ] && DP="$p" && break
    done
  fi
  if [ -z "$DP" ]; then
    fail "没找到 displayplacer 且没有 Homebrew。\n\n请先装 Homebrew（https://brew.sh），再运行本文件。\n或者手动装好 displayplacer 后重跑。"
  fi
fi
echo "displayplacer -> $DP"

echo "=== 3/4 安装监听脚本 ==="
mkdir -p "$CONF" "$HOME_DIR/Library/LaunchAgents"
cp "$SRC" "$CONF/mac_wake_listener.py" || fail "复制脚本失败"
chmod +x "$CONF/mac_wake_listener.py"

if [ ! -d "/Library/Developer/CommandLineTools" ] && [ ! -d "/Applications/Xcode.app" ]; then
  echo "提示：python3 可能要求先装命令行工具，若监听起不来请执行 xcode-select --install"
fi

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.monswitch.wakelistener</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PY</string>
        <string>$CONF/mac_wake_listener.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$CONF/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$CONF/stderr.log</string>
</dict>
</plist>
EOF

echo "=== 4/4 启动 ==="
launchctl bootout "gui/$UID/com.monswitch.wakelistener" 2>/dev/null
if ! launchctl bootstrap "gui/$UID" "$PLIST" 2>/dev/null; then
  launchctl unload "$PLIST" 2>/dev/null
  launchctl load "$PLIST" || fail "LaunchAgent 加载失败"
fi
launchctl enable "gui/$UID/com.monswitch.wakelistener" 2>/dev/null

sleep 2
if pgrep -f mac_wake_listener.py >/dev/null; then
  echo "监听进程已在运行："
  pgrep -fl mac_wake_listener.py
  say "安装完成，监听已启动。\\n\\n首次启动 macOS 可能会弹窗问「是否允许 Python 接受传入网络连接」——必须点「允许」，否则收不到 Windows 的唤醒包。\\n\\n日志：~/.monswitch/listener.log"
else
  echo "进程没起来，看日志："
  tail -20 "$CONF/stderr.log" 2>/dev/null
  tail -20 "$CONF/listener.log" 2>/dev/null
  fail "监听进程未启动，请把终端里的报错截图发出来。"
fi
