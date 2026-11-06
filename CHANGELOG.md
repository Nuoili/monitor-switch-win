# 变更记录

双端统一版本号：**Windows（本仓库）与 Mac（monitor-switch-mac）同号同发**。
发版时两边打同名 tag，仓库间版本号不一致视为发版未完成。

## v2.3.0 — 2026-11-06

双端对齐版本，Windows 端首次对外标注版本号。

**新增**
- 程序内版本可见：窗口标题、托盘悬浮提示都带 `v2.3.0`；新增命令行 `--version`（打包版会弹窗显示，因为 exe 无控制台）。
- exe 文件属性写入版本资源（`FileVersion 2.3.0.0` / `ProductVersion 2.3.0`），此前资源管理器里看不到版本。
- `源码/build_win.py`：一键打包，版本号唯一源头是 `monitor_switch_gui.py` 的 `APP_VERSION`，不再手写两份。
- `卸载器.bat` 入库：停进程 → 删开机自启项 → 清临时日志 → 引导把目录拖进回收站。
- `CHANGELOG.md`（本文件）。

**变更**
- 卸载器重写为纯 cmd。旧版用「隐藏窗口 PowerShell + 递归删除目录」，被杀软判为 `Trojan/Veil.a`（火绒实测直接删除脚本），现在不含 PowerShell、不隐藏窗口、不自删目录。

**修复**
- 承接 2.2 的「切到 Mac → 切回 Windows → 再切 Mac 无反应」：`busy` 状态标志改为 `try/finally` 复位，DDC 句柄每次重新枚举。

## v2.2 — 2026-11-04

- 修复连续切换后按钮静默失效。
- 切 Mac 前广播 UDP `WAKE` 给 Mac 端监听，缓解切回黑屏。

## v2.1 — 2026-11-03

- 单实例：命名互斥体 + `RegisterWindowMessage` 唤起已有窗口。
- 错误日志落 `%TEMP%\MonitorSwitch\error.log`（`--noconsole` 下 `sys.stderr` 为 None）。

## v2.0 — 2026-11-03

- 首个正式版：托盘常驻、开机自启、一键切 DP / HDMI-1。
