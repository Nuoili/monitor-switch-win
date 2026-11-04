#!/bin/bash
# 把显示器信号源切到 DisplayPort（Windows 那台机器）
# 依赖 m1ddc，见「0-安装m1ddc.command」

find_m1ddc() {
  for p in /opt/homebrew/bin/m1ddc /usr/local/bin/m1ddc \
           "$HOME/bin/m1ddc" "$HOME/m1ddc/m1ddc" "$HOME/m1ddc-src/m1ddc"; do
    if [ -x "$p" ]; then echo "$p"; return; fi
  done
  command -v m1ddc 2>/dev/null
}

M1DDC="$(find_m1ddc)"

if [ -z "$M1DDC" ]; then
  osascript -e 'display dialog "没有找到 m1ddc。请先双击运行「0-安装m1ddc.command」。" buttons {"好"} default button 1 with icon caution'
  exit 1
fi

"$M1DDC" set input 15
