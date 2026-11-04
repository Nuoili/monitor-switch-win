#!/bin/bash
# 一次性安装 m1ddc（显示器 DDC 控制命令行工具）

clear
echo "======================================"
echo "  安装 m1ddc"
echo "======================================"
echo ""

if [ -x "$HOME/bin/m1ddc" ] || [ -x /opt/homebrew/bin/m1ddc ] || [ -x /usr/local/bin/m1ddc ]; then
  echo "已经装过了，不用重复安装。"
  osascript -e 'display dialog "m1ddc 已经安装过了。" buttons {"好"} default button 1'
  exit 0
fi

if ! xcode-select -p >/dev/null 2>&1; then
  echo "需要先安装 Xcode 命令行工具，正在唤起安装窗口……"
  xcode-select --install
  echo ""
  echo "请在弹出的窗口里点「安装」，等它下载完成（约 5-10 分钟）。"
  echo "装完后再双击运行一次本文件。"
  osascript -e 'display dialog "需要先装 Xcode 命令行工具。请在弹出的窗口点「安装」，完成后重新运行本文件。" buttons {"好"} default button 1'
  exit 1
fi

echo "第 1 步：下载 m1ddc 源码……"
rm -rf "$HOME/m1ddc-src"
if ! git clone --depth 1 https://github.com/waydabber/m1ddc.git "$HOME/m1ddc-src"; then
  echo "下载失败，请检查网络。"
  osascript -e 'display dialog "下载失败，请检查网络后重试。" buttons {"好"} default button 1 with icon caution'
  exit 1
fi

echo "第 2 步：编译……"
cd "$HOME/m1ddc-src" || exit 1
if ! make; then
  echo "编译失败。"
  osascript -e 'display dialog "编译失败。" buttons {"好"} default button 1 with icon caution'
  exit 1
fi

echo "第 3 步：安装到 ~/bin ……"
mkdir -p "$HOME/bin"
cp "$HOME/m1ddc-src/m1ddc" "$HOME/bin/m1ddc"
chmod +x "$HOME/bin/m1ddc"

echo ""
echo "完成。检测结果："
"$HOME/bin/m1ddc" display list
echo ""
osascript -e 'display dialog "m1ddc 安装完成。\n\n现在可以双击「1-切到Windows.command」测试切换。" buttons {"好"} default button 1'
