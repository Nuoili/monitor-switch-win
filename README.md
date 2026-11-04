# 显示器切换 · Windows 端

一台显示器接两台机器（Windows 主机 + MacBook），点一下就能换信号源，不用去按显示器背面的按钮。

- 纯 ctypes 调 DDC/CI：`dxva2.dll` → `SetVCPFeature`，VCP `0x60` 写输入源，无第三方依赖。
- PyInstaller 打包单文件 exe，常驻托盘，**单实例**（重复双击只唤起已有窗口）。
- 显示器实测型号：AOC Q24G2（DP = Windows，HDMI-1 = Mac）。换屏只要 DDC 通路正常，改一下输入源编号即可。
- Mac 端在另一个仓库：[monitor-switch-mac](https://github.com/Nuoili/monitor-switch-mac)。

## 用法

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

## 目录

```
源码/               全部程序代码
   monitor_switch_gui.py   主程序（窗口 + 托盘 + DDC 切换）
   app.manifest            PerMonitorV2 DPI 感知 + comctl32 v6
   icon.ico / tray_*.ico   程序图标与托盘图标
   gen_icon.py             重新生成图标
   gen_tray_icon.py        托盘图标（明暗两套）
   tray_selftest.py        托盘图标自检
   _busy_test.py           切换状态机回归测试
   _single_instance_test.py 单实例 / 唤起窗口回归测试
使用说明.txt         给使用者看的操作手册
```

## 实现要点（踩过的坑）

- **DDC 句柄会失效**：切换信号源后显示器对 Windows 而言是"重新接入"，旧的 `hPhysicalMonitor` 立刻作废。所以每次用完就丢缓存，下次重新枚举并 `_probe()` 验证，不能沿用。
- **切换要重试**：显示器接收器重新上电后只有 1–3 秒的检测窗口。切信号源时带 4 次重试 + 0.4 秒预热，失败要给出明确提示，不能静默。
- **状态标志必须复位**：`busy` 只在失败分支复位过一次，导致成功切出一次之后所有点击被静默吞掉——表现为"点了没反应"。现在用 `try/finally`。
- **单实例**：命名互斥体判重 + `RegisterWindowMessage("MonitorSwitch-ShowMe")` 让第二个进程通知第一个把窗口亮出来；`AttachThreadInput` 换前台权限，否则只闪任务栏。
- **切 Mac 前先捅一下 Mac**：广播 UDP `WAKE`（端口 9998）给 Mac 端的监听脚本，0.4 秒后再发 DDC。多网段环境会同时向全局广播和各网段定向广播各发一份（有 VPN 时全局广播可能从虚拟网卡溜走）。
- **`--noconsole` 下 `sys.stderr` 是 None**：原来的异常日志会二次抛异常吞掉真错误，现在写 `%TEMP%\MonitorSwitch\error.log`。

## 自己编译

```bash
pip install pyinstaller
cd 源码
python -m PyInstaller --noconfirm --clean --onefile --noconsole \
  --name MonitorSwitch --manifest app.manifest --icon icon.ico \
  monitor_switch_gui.py
```

回归测试（真机会弹出程序窗口）：

```bash
python _single_instance_test.py dist/MonitorSwitch.exe
python _busy_test.py
```

## 与 Mac 端的协议

切到 Mac 之前，先向 UDP 端口 **9998** 广播 ASCII 字符串 `WAKE`；Mac 端收到后重放一次显示配置（modeset），给显示器一个新鲜的信号边沿，破解 HPD 假在线导致的切回去黑屏。协议细节见 [Mac 仓库](https://github.com/Nuoili/monitor-switch-mac)。

## License

MIT
