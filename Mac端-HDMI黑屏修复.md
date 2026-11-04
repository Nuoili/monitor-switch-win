# Mac 端交接：切回 HDMI 黑屏 —— 三套方案全量落地

> 给 **Mac 上的 AI 助手** 读。也可人自己照着做。
> 全部自包含，不需要 Windows 那边解释。

---

## 一、把这段贴给 Mac 上的 AI

```
这个文件夹里有：
  Mac端-HDMI黑屏修复.md    ← 本文件，先完整读一遍
  diagnose.py              ← 体检脚本
  mac_wake_listener.py     ← 唤醒监听（方案 C 用）
  4-保持Mac唤醒.command     ← 方案 A
  5-取消保持唤醒.command
  6-安装唤醒监听.command     ← 方案 C
  7-卸载唤醒监听.command

任务：这台 Mac 接在 AOC Q24G2 显示器的 HDMI 口上，Windows 台式机接 DP 口。
问题是「切到 Windows 久了，再切回 Mac 就黑屏报无信号，Mac 的显示器设置里外接屏却一切正常」。

请按本文件的「四、诊断流程」一步步做：
 1. 先跑 python3 diagnose.py，把输出完整贴给我；
 2. 按诊断结论判定属于 A / B / C 哪一类（判据见第三、四节）；
 3. 装对应的方案，三套方案不一定只装一套，该装几个装几个；
 4. 用「六、验收」里的复现测试真的复现一次、再真的修好一次。
    复现用加速法（把 displaysleep 改成 1 分钟），不需要真的等半小时。

硬性要求：
 · 不许用「应该好了 / 理论上没问题」当结论，必须贴 listener.log 和实测结果；
 · 每一步失败就停下来分析，不要跳过继续往下走；
 · 需要 sudo 或者需要我动手（拔插线、按显示器按钮）的地方，明确告诉我；
 · 收尾时把 pmset 改回原值；
 · 全程中文。
```

---

## 二、根因：同一个症状，三种不同的断法

```
MacBook ──USB-C──> DS-7A15 坞 ──HDMI──> AOC Q24G2 (HDMI 口, 输入值 17)
Windows ────────────DP────────────────> AOC Q24G2 (DP 口, 输入值 15)
```

切到 Windows 后，"Mac 那一路"会以三种方式失效，症状都是黑屏，但修法完全不同：

| 类 | 谁断了 | 现场特征 | 方案 |
|---|---|---|---|
| **A** | Mac 自己睡了 / 关屏了 | Mac 唤醒后 1–3 秒必出画面；`pmset` 里 displaysleep 不是 0 | 让 Mac 别睡（caffeinate） |
| **B** | 坞在主机睡眠后没把 HDMI 拉起来 | 唤醒 Mac 无效；拔插坞的 USB-C 线才恢复；`--watch` 里那一刻**外接屏从列表消失** | 换直连 / 换坞 / 换线 |
| **C** | 显示器判"无信号"并锁存 | 唤醒 Mac 无效；拔插线也未必用；但 **OSD 重新扫描**或 `--watch` 里外接屏**一直在列表里** | OSD 关待机 + UDP 唤醒踢一脚 |

**C 的机制**（最常见，也最反直觉）：

- 显示器切到 DP 后关掉 HDMI 接收端省电，但 **HPD 一直是高电平**（线还插着、屏还在）；
- Mac 看 HPD 一直高、EDID 也读得到 → 判定外接屏好得很，**永不重新协商链路**；
- 切回瞬间，显示器 HDMI 口重新上电，检测窗口只有 1–3 秒。Mac 没重新发 modeset，
  输出还沉在低功耗状态 → 窗口错过 → 判"无信号" → 进待机并**锁存**，不再主动重试。

两边都觉得自己没问题，于是僵住。必须有人踢一脚。

---

## 四、诊断流程（先定位，再动手）

### STEP 0 环境

```bash
cd ~/Desktop/macOS
chmod +x *.command
python3 diagnose.py
```

把输出贴出来。重点看四行：

- `displaysleep_ac_min` —— 不是 0 就说明会自己关屏 → 至少要做 A
- `caffeinate_proc` / `awake_plist` —— A 装了没
- `listener_proc` / `displayplacer` —— C 装了没
- `display_count` —— 切到 Mac 时正常应该是 2（笔记本屏 + 外接屏）

### STEP 1 加速复现（关键，别真等半小时）

```bash
# 记录原值，测完要还原
pmset -g custom | grep -E "displaysleep|^\s*sleep"

# 临时改成 1 分钟关屏（需要密码）
sudo pmset -a displaysleep 1
```

然后把监听盯起来：

```bash
python3 diagnose.py --watch
```

### STEP 2 制造故障

1. 在 Windows 上点「切到 Mac」→ 确认此刻正常出画面；
2. 切回 Windows；
3. **等 3 分钟**（足够让 displaysleep=1 生效）；
4. 切回 Mac，观察。

### STEP 3 读现象，定类型

| 现象 | 类型 | 下一步 |
|---|---|---|
| 黑屏，但**动一下 Mac 键盘/触控板 1–3 秒出画面** | **A** | 做方案 A，测完再复测 |
| 黑屏，动键盘无效，**拔插坞的 USB-C 线**才恢复 | **B** | 走方案 B 的三步物理测试 |
| 黑屏，动键盘无效，`--watch` 里外接屏**始终在列表**，按 OSD 重新扫描才出来 | **C** | 走方案 C |
| 黑屏，`--watch` 里外接屏**从列表消失了** | **B 或 A** | 先看 Mac 是不是睡了；没睡就是坞 |

复现不出来？说明 3 分钟还不够，把 `displaysleep` 保持 1 分钟，等 10 分钟再试一次。

---

## 五、三套方案

### 方案 A：让 Mac 别睡

**治**：Mac 侧关屏 → GPU 停止往 HDMI 送信号。

**装**：双击 `4-保持Mac唤醒.command`。它会写一个 LaunchAgent，
常驻 `caffeinate -d -i -s`，禁止关屏 + 禁止空闲睡眠。

**验证**：

```bash
pmset -g assertions | grep -i "PreventUserIdleDisplaySleep"   # 应为 1
pgrep -fl caffeinate                                          # 应有进程
```

**复测**：保持 `displaysleep=1`，重复 STEP 2。装了 A 之后即使过了 3 分钟，
`pmset -g assertions` 里显示断言仍在，应能直接出画面。

**回滚**：双击 `5-取消保持唤醒.command`。

**代价**：接电源时屏幕不会自动熄灭。合盖场景下还要满足 clamshell 条件
（接电源 + 有外接键鼠），键鼠被 USB 切换器切到 Windows 时 Mac 侧算"没有键鼠"，
所以**合盖用的话 A 不一定保得住，建议开盖**。

---

### 方案 B：坞与链路

**治**：坞在主机睡眠/唤醒后没把 HDMI 输出拉起来（HPD 没恢复），或线材/接口本身不稳。

这一类**没有纯软件解**，必须动手测。按顺序做，每步记录结果：

| 步骤 | 操作 | 结果说明 |
|---|---|---|
| B1 | 把 Mac 的 HDMI 线从坞上拔下来，**直连**显示器 HDMI 口（用 USB-C 转 HDMI 线或转接头），重复 STEP 2 | 直连不犯 → 问题在坞 |
| B2 | 仍走坞，但把坞的**电源适配器单独插一个 100W 头**（不要和多口氮化镓共用），重复 STEP 2 | 不犯 → 是 PD 供电瞬断导致坞重启 |
| B3 | 换一根 HDMI 线（2.0 认证、1.5 米内），重复 STEP 2 | 不犯 → 线材问题 |
| B4 | `--watch` 里刻意观察切回瞬间：外接屏是否从列表消失 | 消失 = HPD 真的掉了，坐实 B |

**B 的临时缓解**：写一个拔插替代动作 —— 在 Mac 上执行

```bash
# 让显示器端口重新枚举（不需要物理拔插）
sudo pmset displaysleepnow && sleep 2 && caffeinate -u -t 2
```

如果这条能救回来（不用拔线），说明是 HPD 状态问题而不是硬件坏，
把这条加到方案 C 的兜底里一起用。

---

### 方案 C：打破"无信号"锁存

**两层，都要做。**

#### C1 显示器 OSD（人工，30 秒）

按显示器背面摇杆进 OSD，找到并改：

| 项目 | 改成 | 在哪 |
|---|---|---|
| DPMS | 关 | 其他 / Other |
| 无信号自动关机（Auto Standby / Off Timer） | 关 | 其他 / 设置 |
| 自动输入检测（Auto Source） | 开 | 其他 / 设置 |
| Quick Start / 快速启动（有就开） | 开 | 设置 |

#### C2 UDP 唤醒监听（AI 装）

**原理**：Windows 端点「切到 Mac」时，先广播一个 UDP `WAKE` 包；Mac 收到后
`caffeinate -u` 叫醒显示输出 + 用 `displayplacer` 重放一次显示配置（modeset），
人为制造一次信号重新协商。0.4 秒后 Windows 再切信号源，显示器上电时正好抓到新鲜信号。

**装**：双击 `6-安装唤醒监听.command`（自动查 python3 / 装 displayplacer / 写
LaunchAgent / 启动）。

**防火墙**：首次会弹「是否允许 Python 接受传入网络连接」→ **必须点允许**。
点错了去 `系统设置 → 网络 → 防火墙 → 选项` 里改。

**验证（必做）**：

```bash
# 1. 进程与端口
pgrep -fl mac_wake_listener.py
lsof -nP -iUDP:9998

# 2. 本地打一枪（会闪一下屏，正常）
python3 -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(b'WAKE',('127.0.0.1',9998))"
sleep 1 && tail -5 ~/.monswitch/listener.log
```

日志必须出现这两行，缺一不可：

```
WAKE from 127.0.0.1
reapply -> True
```

如果是 `reapply -> False`：`displayplacer list` 手动跑一次，确认末尾有
`displayplacer "id:... res:... hz:..."` 这样的行；然后
`rm ~/.monswitch/mode.txt`，重启监听重抓。

**回滚**：双击 `7-卸载唤醒监听.command`。

---

### 组合建议

| 你的情况 | 装什么 |
|---|---|
| 只有 C 的症状 | C1 + C2 |
| 只有 A 的症状 | A |
| A + C 都有（最常见） | A + C1 + C2 |
| 判到 B | 先 B1/B2/B3 找到物理原因，同时把 A + C2 装上兜底 |

Windows 端不需要你做任何事，UDP 包默认广播。若广播被挡（多网卡/跨网段），
在 Windows 的 `D:\显示器切换\` 下建 `mac_ip.txt` 写本机 IP，一行一个：

```
192.168.1.23
```

---

## 六、验收：AI 必须交付这些证据

不许口头结论。逐条打勾，缺一条都算没做完。

1. `python3 diagnose.py` 的完整输出
2. 复现成功的那一次：切回黑屏 + `--watch` 当时的输出（决定性证据）
3. 判定成 A / B / C 的理由（对着第三节的判据表说）
4. 装完之后 `pgrep` / `lsof` / `pmset -g assertions` 的结果
5. 本地打枪的 `listener.log` 末尾 5 行，含 `reapply -> True`
6. **端到端**：Windows 上点一次「切到 Mac」，2 秒内出画面；`listener.log` 里
   出现 `WAKE from 192.168.x.x`（不是 127.0.0.1）
7. 把 `sudo pmset -a displaysleep <原值>` 改回去，并贴 `pmset -g custom` 确认

---

## 七、排错

| 现象 | 原因 | 处理 |
|---|---|---|
| `pgrep` 无输出 | LaunchAgent 没起来 | `cat ~/.monswitch/stderr.log`；多为 python3 路径错或缺 Xcode CLT（`xcode-select --install`） |
| 本地打枪有记录，Windows 切过去没记录 | 防火墙拦了 / 不在同一网段 / 广播被挡 | 先允许 python3 入站；再试 `mac_ip.txt` 单播 |
| `reapply -> False` | displayplacer 没装好或抓不到配置 | 手动 `displayplacer list`；删 `~/.monswitch/mode.txt` 重抓 |
| 日志里 `WAKE from` 有，`reapply` 也 True，但还是黑 | 锁存发生在显示器侧，软件踢不动 | 确认 C1 三项已关；再试强刷 `sudo pmset displaysleepnow && sleep 2 && caffeinate -u -t 2` |
| 一切正常但偶尔还黑 | 坞供电瞬断 | 走 B2，坞独占 100W 头 |

---

## 八、给 AI 的硬约束

- 端口 **9998** 不许改，Windows 端写死了。
- 不要 `sudo killall WindowServer` —— 会直接注销会话。
- 不要用 `osascript` 模拟点「检测显示器」按钮，UI 脚本换版本必崩。
- 不要在没复现过的情况下宣布修复。
- 改 `pmset` 前先记原值，结束必须还原。
- 中文回复，结论先行。
