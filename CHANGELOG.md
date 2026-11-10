# 变更记录

双端统一版本号：**Windows（本仓库）与 Mac（monitor-switch-mac）同号同发**。
发版时两边打同名 tag，仓库间版本号不一致视为发版未完成。

## v2.4.0 — 2026-11-11

**改名版**：产品名从「显示器切换」统一为 **Monitor Switch**，同时修掉标题栏图标不生效。

**改名范围（Windows）**
| 位置 | 旧 | 新 |
|---|---|---|
| 窗口标题 / 托盘提示 | 显示器切换 v2.3.1 | Monitor Switch v2.4.0 |
| 程序文件 | `显示器切换.exe` | `Monitor Switch.exe` |
| 安装目录 | `D:\显示器切换` | `D:\Monitor Switch` |
| 开机自启值名 | `Run\MonitorSwitch` | `Run\Monitor Switch` |
| 配置键 | `HKCU\Software\MonitorSwitch` | `HKCU\Software\Monitor Switch` |
| 临时目录 | `%TEMP%\MonitorSwitch` | `%TEMP%\Monitor Switch` |
| exe 属性 | ProductName=显示器切换 | ProductName=Monitor Switch |

**修 Bug**
- 标题栏图标退化成系统通用图标：原来用 `LoadIconW(hInstance, MAKEINTRESOURCE(1))`，
  PyInstaller onefile 里图标组 ID 不保证是 1，取不到就回落到 `IDI_APPLICATION`。
  改用 `ExtractIconExW(当前 exe, 0)` 取第 0 组，大/小图标分别取（小图标不再拿 32px 硬缩）。
  另外补一次 `WM_SETICON`，防止部分系统版本忽略窗口类里的 `hIcon`。
- `SendMessageW` 第 4 参声明为 LPARAM（整数），HICON 对象必须 `.value` 后传，
  否则打包运行直接抛 `TypeError: 'c_void_p' object cannot be interpreted as an integer`。

**升级兼容**
- 老版本的开机自启项（值名 `MonitorSwitch`、指向旧 exe）在首次启动时自动改写成新名字 + 新路径，
  旧值删除；装过 2.3.x 的用户不用手动重设自启。
- 自定义热键从旧配置键读到后自动搬到新键，不会丢。
- 卸载器同时清理新旧两套注册表项和临时目录，老机器升级后也能删干净。

## v2.3.1 — 2026-11-06

Windows 端新增全局热键。Mac 端无对应功能改动，仅版本号跟进，保持双端同号。

**新增**
- **全局热键 `Ctrl+Alt+Shift+D`**：按一下切走，再按一下切回来（toggle）。
  做成 toggle 是因为切到 Mac 之后 Windows 黑屏，唯一还能用的入口就是热键本身。
- **候选顺延**：内置 5 个组合（`Ctrl+Alt+Shift+D` → `M` → `F9` → `F10` → `Ctrl+Shift+F9`），
  启动时按顺序注册，被占用自动跳过。`RegisterHotKey` 失败不回原因，靠顺延兜底。
- 托盘菜单新增一行灰字显示当前实际生效的热键；主窗口底部说明文字同步。
- 命令行 `--hotkey`（查当前组合与候选顺序）、`--set-hotkey X`（改键，`PostMessage`
  通知运行中的实例即刻换绑）、`--no-hotkey`（本次不注册，排查冲突用）。
- 热键配置持久化在 `HKCU\Software\MonitorSwitch\Hotkey`。

**变更**
- 卸载器新增第 3 步：删除 `HKCU\Software\MonitorSwitch`（热键配置随之清掉）。
- 热键触发走静默路径：不把主窗口叫到前台，避免打游戏/共享屏幕时突然蹦窗口；
  结果用托盘气泡反馈。失败仍弹错误提示（此时屏幕还在本机，看得见）。

**选键说明**
一律用三修饰键。两修饰组合已被占满：`Ctrl+Alt+F1~F12`（Intel 核显）、
`Ctrl+Alt+A`（QQ 截图）、`Alt+Z`/`Alt+R`（NVIDIA）、`Ctrl+Shift`（输入法）、
`Alt+Shift`（键盘布局）、`Win+*`（全归系统）。安全键与截图键
（`Ctrl+Alt+Del`、`Ctrl+Shift+Esc`、`Alt+Tab`、`PrintScreen`、`Win+Shift+S`）
系统直接吞掉，根本注册不上，未纳入候选。

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
