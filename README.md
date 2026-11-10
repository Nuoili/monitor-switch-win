# Monitor Switch · Windows 端

**v2.4.0** — 与 Mac 端 [monitor-switch-mac](https://github.com/Nuoili/monitor-switch-mac) 同号发布，两端版本号必须保持一致。
本版是**改名版**：程序、exe、目录、注册表项统一成 `Monitor Switch`（原名「显示器切换」），
并修掉标题栏取不到应用图标、退化成系统通用图标的问题。老版本会自动迁移开机自启项，不用重装。

一台显示器接两台机器（Windows 主机 + MacBook），点一下就能换信号源，不用去按显示器背面的按钮。

- 纯 ctypes 调 DDC/CI：`dxva2.dll` → `SetVCPFeature`，VCP `0x60` 写输入源，无第三方依赖。
- PyInstaller 打包单文件 exe，常驻托盘，**单实例**（重复双击只唤起已有窗口）。
- **全局热键** `Ctrl+Alt+Shift+D`：不看屏幕也能来回切，切走之后还能摸黑按回来。
- 显示器实测型号：AOC Q24G2（DP = Windows，HDMI-1 = Mac）。换屏只要 DDC 通路正常，改一下输入源编号即可。
- Mac 端在另一个仓库：[monitor-switch-mac](https://github.com/Nuoili/monitor-switch-mac)。

## 用法

从 [Releases](../../releases) 下载 `Monitor Switch.exe`，双击即用，图标在托盘。

| 操作 | 结果 |
|---|---|
| 托盘左键 / 双击图标 | 打开主窗口 |
| 托盘右键 | 菜单：切到 Mac、切回 Windows、显示主窗口、开机自启、退出 |
| 窗口右上角 × | 只收进托盘，**不是退出** |
| 再双击一次 exe | 唤起已有窗口（单实例，不会开出第二个） |
| `Ctrl+Alt+Shift+D` | 全局热键：两端来回切，不弹窗口 |

命令行（供快捷方式 / 开机自启使用）：

```
Monitor Switch.exe                      打开窗口
Monitor Switch.exe --tray               静默进托盘（开机自启用这条）
Monitor Switch.exe --auto --tray        先切回 Windows 再进托盘
Monitor Switch.exe --dp / --win         静默切到 DP（Windows）
Monitor Switch.exe --hdmi / --mac       静默切到 HDMI-1（Mac）
Monitor Switch.exe --state              打印当前信号源，排查用
Monitor Switch.exe --version            打印版本号
Monitor Switch.exe --hotkey             看当前热键与候选顺序
Monitor Switch.exe --set-hotkey X       改热键，X 形如 Ctrl+Alt+Shift+F9
Monitor Switch.exe --no-hotkey          本次不注册热键（排查冲突用）
```

版本号从哪来：`源码/monitor_switch_gui.py` 的 `APP_VERSION` 是唯一源头，
`源码/build_win.py` 读它生成 exe 的版本资源。改版本只改那一处。

## 全局热键

默认 **`Ctrl+Alt+Shift+D`**：按一下切走，再按一下切回来（toggle）。

做成 toggle 而不是单向"切到 Mac"：切走之后这台 Windows 就黑屏了，鼠标键盘够不到
任何按钮 —— 此时唯一还能用的入口就是热键本身。"摸黑按一下切回 Windows"能成立，
这才是热键的价值。

### 选键原则：避开所有已知全局热键

`RegisterHotKey` 被占时只返回 FALSE，不会告诉你是谁占了。所以不能假设某个组合一定可用 ——
程序内置 5 个候选，启动时按顺序试，第一个注册成功的才生效：

| 顺序 | 组合 |
|---|---|
| 1 | `Ctrl+Alt+Shift+D` |
| 2 | `Ctrl+Alt+Shift+M` |
| 3 | `Ctrl+Alt+Shift+F9` |
| 4 | `Ctrl+Alt+Shift+F10` |
| 5 | `Ctrl+Shift+F9` |

（实测：先占住第 1 个，程序会自动顺延到第 2 个并把它显示在托盘菜单里。）

为什么一律用**三修饰键**——两修饰的组合在 Windows 上已被占满：

| 组合 | 被谁占用 |
|---|---|
| `Ctrl+Alt+F1`~`F12` | Intel 核显图形热键 |
| `Ctrl+Alt+A` | QQ 截图 |
| `Ctrl+Alt+Insert` | NVIDIA |
| `Ctrl+Alt+方向键` | 旧显卡屏幕旋转 |
| `Alt+Z` / `Alt+R` | NVIDIA GeForce Experience / 录制 |
| `Alt+A` | 微信截图 |
| `Ctrl+Shift+*` | 输入法切换、钉钉 `Ctrl+Shift+A`、各类 IDE 默认键 |
| `Alt+Shift` | 键盘布局 / 语言切换（系统级） |
| `Win+*` | 全归系统：`L D E R I X P S V A K G H M U B C F`、数字键、方向键 |
| `Ctrl+Space` / `Shift+Space` / `Ctrl+.` / `Ctrl+,` | 微软拼音 |
| `Ctrl+Alt+Del`、`Ctrl+Shift+Esc`、`Alt+Tab`、`Alt+F4`、`PrintScreen`、`Win+Shift+S` | 安全键与截图键，系统直接吞掉，`RegisterHotKey` 根本注册不上，不必浪费候选位 |

### 改键 / 临时关闭

```bash
Monitor Switch.exe --hotkey                        # 看当前生效的组合与候选顺序
Monitor Switch.exe --set-hotkey Ctrl+Alt+Shift+F9  # 改（≥1 修饰键 + 1 主键，不能有空格）
Monitor Switch.exe --no-hotkey                     # 本次不注册（排查冲突）
```

`--set-hotkey` 写 `HKCU\Software\Monitor Switch\Hotkey`，并 `PostMessage` 通知正在运行的
实例即刻换绑，不用重启；卸载器会把这条注册表项一起清掉。

### 已知限制

- 以管理员身份运行的前台程序（任务管理器、全屏游戏）会挡住普通权限程序的热键 ——
  这是 UIPI，不是 bug。切到桌面再按即可。
- 加了 `MOD_NOREPEAT`，按住不放只会触发一次，不会按键盘重复率连发。

## 卸载

双击 `卸载器.bat`，它会：

1. 结束正在运行的 `Monitor Switch.exe`
2. 删除开机自启项 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\Monitor Switch`（旧名 `MonitorSwitch` 一并清）
3. 删除配置 `HKCU\Software\Monitor Switch`（旧键 `Software\MonitorSwitch` 一并清）
4. 清理 `%TEMP%\Monitor Switch`（含旧目录 `MonitorSwitch`）下的错误日志
5. 删除开始菜单与桌面快捷方式
6. 打开本文件夹并选中，由你把整个文件夹拖进回收站

最后一步故意留给人工：脚本删不掉"自己所在的文件夹"，硬删还会被杀软误判成木马
（实测火绒会把带隐藏窗口 + 递归删除的卸载脚本直接当 `Trojan/Veil` 删掉）。
拖进回收站既干净又能还原。源码不会丢，GitHub 上有完整仓库。

## 目录

```
源码/               全部程序代码
   monitor_switch_gui.py   主程序（窗口 + 托盘 + DDC 切换），APP_VERSION 在这里
   build_win.py            一键打包（自动生成版本资源，调 PyInstaller）
   version_info.txt        exe 版本资源，由 build_win.py 生成，不入库
   app.manifest            PerMonitorV2 DPI 感知 + comctl32 v6
   icon.ico / tray_*.ico   程序图标与托盘图标
   gen_icon.py             重新生成图标
   gen_tray_icon.py        托盘图标（明暗两套）
   tray_selftest.py        托盘图标自检
   _busy_test.py           切换状态机回归测试
   _single_instance_test.py 单实例 / 唤起窗口回归测试
使用说明.txt         给使用者看的操作手册
卸载器.bat           卸载（见上一节）
CHANGELOG.md         版本变更记录
```

## 实现要点（踩过的坑）

- **DDC 句柄会失效**：切换信号源后显示器对 Windows 而言是"重新接入"，旧的 `hPhysicalMonitor` 立刻作废。所以每次用完就丢缓存，下次重新枚举并 `_probe()` 验证，不能沿用。
- **切换要重试**：显示器接收器重新上电后只有 1–3 秒的检测窗口。切信号源时带 4 次重试 + 0.4 秒预热，失败要给出明确提示，不能静默。
- **状态标志必须复位**：`busy` 只在失败分支复位过一次，导致成功切出一次之后所有点击被静默吞掉——表现为"点了没反应"。现在用 `try/finally`。
- **单实例**：命名互斥体判重 + `RegisterWindowMessage("MonitorSwitch-ShowMe")` 让第二个进程通知第一个把窗口亮出来；`AttachThreadInput` 换前台权限，否则只闪任务栏。
- **切 Mac 前先捅一下 Mac**：广播 UDP `WAKE`（端口 9998）给 Mac 端的监听脚本，0.4 秒后再发 DDC。多网段环境会同时向全局广播和各网段定向广播各发一份（有 VPN 时全局广播可能从虚拟网卡溜走）。
- **`--noconsole` 下 `sys.stderr` 是 None**：原来的异常日志会二次抛异常吞掉真错误，现在写 `%TEMP%\MonitorSwitch\error.log`。
- **热键注册失败不报原因**：`RegisterHotKey` 只回一个 FALSE，查不到是被谁占了。所以必须准备候选列表 + 顺延，并且失败要弹托盘气泡告知，不能静默。
- **热键要绑窗口而不是线程**：`WM_HOTKEY` 走正常窗口消息，`WM_DESTROY` 里 `UnregisterHotKey`，避免窗口没了而组合还被占着。

## 自己编译

版本号写在 `源码/monitor_switch_gui.py` 的 `APP_VERSION`，打包脚本会读它：

```bash
pip install pyinstaller
python 源码/build_win.py          # 产物：源码/dist/Monitor Switch.exe
```

脚本内部等价于：

```bash
python -m PyInstaller --noconfirm --clean --onefile --noconsole \
  --name "Monitor Switch" --manifest 源码/app.manifest --icon 源码/icon.ico \
  --version-file 源码/version_info.txt 源码/monitor_switch_gui.py
```

回归测试（真机会弹出程序窗口）：

```bash
python 源码/_single_instance_test.py 源码/dist/Monitor Switch.exe
python 源码/_busy_test.py
```

## 与 Mac 端的协议

切到 Mac 之前，先向 UDP 端口 **9998** 广播 ASCII 字符串 `WAKE`；Mac 端收到后重放一次显示配置（modeset），给显示器一个新鲜的信号边沿，破解 HPD 假在线导致的切回去黑屏。协议细节见 [Mac 仓库](https://github.com/Nuoili/monitor-switch-mac)。

## License

MIT
