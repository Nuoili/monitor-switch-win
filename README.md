# 显示器切换 · monitor-switch

一台显示器接两台机器（Windows 主机 + MacBook），用鼠标点一下就能换信号源，不用去按显示器背面的按钮。

- **Windows 端**：纯 ctypes 调 DDC/CI（`dxva2.dll` → VCP `0x60`），无第三方依赖，打包成单文件 exe，常驻托盘。
- **Mac 端**：脚本驱动 [`m1ddc`](https://github.com/waydabber/m1ddc) 发同样的 DDC 指令，附一键安装 / 卸载 / 开机自启。
- 显示器实测型号：AOC Q24G2（DP = Windows，HDMI-1 = Mac）。换显示器只要 DDC 通路正常，改一下输入源编号即可。

## 目录结构

```
源码/windows/      Windows 端（Python + ctypes，PyInstaller 单文件打包）
源码/macos/        Mac 端（.command 脚本 + 诊断 / 唤醒监听 Python）
使用说明.txt        给使用者看的操作手册（Windows 端）
```

## Windows 端

从 [Releases](../../releases) 下载 `显示器切换.exe`，双击即用，图标在托盘。

| 操作 | 结果 |
|---|---|
| 托盘左键 / 双击图标 | 打开主窗口 |
| 托盘右键 | 菜单：切到 Mac、切回 Windows、显示主窗口、开机自启、退出 |
| 窗口右上角 × | 只收进托盘，**不是退出** |
| 再双击一次 exe | 唤起已有窗口（单实例，不会开出第二个） |

命令行（供快捷方式 / 开机自启使用）：

```
显示器切换.exe                      打开窗口
显示器切换.exe --tray               静默进托盘（开机自启用这条）
显示器切换.exe --auto --tray        先切回 Windows 再进托盘
显示器切换.exe --dp / --win         静默切到 DP（Windows）
显示器切换.exe --hdmi / --mac       静默切到 HDMI-1（Mac）
显示器切换.exe --state              打印当前信号源，排查用
```

### 实现要点

- **DDC 句柄会失效**：切换信号源后，显示器对 Windows 而言是"重新接入"，旧的 `hPhysicalMonitor` 立刻作废。所以每次用完就丢缓存，下次重新枚举并 `_probe()` 验证。
- **切换要重试**：显示器接收器重新上电后只有 1–3 秒的检测窗口，错过就判"无信号"。所以切信号源时带 4 次重试 + 0.4 秒预热。
- **单实例**：命名互斥体 + `RegisterWindowMessage` 唤起已有窗口，重复双击不会多开。开机自启那条路径完全静默。

### 自己编译

```bash
pip install pyinstaller
cd 源码/windows
python -m PyInstaller --noconfirm --clean --onefile --noconsole \
  --name MonitorSwitch --manifest app.manifest --icon icon.ico \
  monitor_switch_gui.py
```

回归测试（真机会弹出程序窗口）：

```bash
python _single_instance_test.py dist/MonitorSwitch.exe   # 单实例 / 唤起窗口
python _busy_test.py                                     # 切换后 busy 复位、句柄自愈
```

## Mac 端

拷 `源码/macos/` 到 Mac，首次 `chmod +x *.command`，然后按序号双击：

| 文件 | 作用 |
|---|---|
| `0-安装m1ddc.command` | 装 m1ddc 并验证能读到显示器 |
| `1-切到Windows.command` / `2-切到Mac.command` | 切信号源 |
| `3-设置开机自启.command` | 登录后自动切回 Mac |
| `4-保持Mac唤醒.command` / `5-取消保持唤醒.command` | `caffeinate` 常驻，避免 Mac 关屏后 HDMI 断流 |
| `6-安装唤醒监听.command` / `7-卸载唤醒监听.command` | 监听 UDP 9998，收到 Windows 的唤醒包就重放一次显示配置 |
| `diagnose.py` | 体检：读显示器、查 DDC、看 pmset；`--watch` 持续盯显示配置变化 |
| `mac_wake_listener.py` | 唤醒监听本体（LaunchAgent 常驻） |

Windows 端点「切到 Mac」时会先广播一个 UDP `WAKE` 包（端口 9998），0.4 秒后再发 DDC 命令——给 Mac 腾出重新协商链路的时间。多网段环境会同时向全局广播和本机各网段的定向广播各发一份。

## 已知问题

**Mac 久不切回来，切回去 HDMI 黑屏**：这是 HPD 假在线导致的僵局（显示器认为没信号，Mac 认为屏还在），不是线材问题。排查与三套修复方案见 [`源码/macos/Mac端-HDMI黑屏修复.md`](源码/macos/Mac端-HDMI黑屏修复.md)。

## License

MIT
