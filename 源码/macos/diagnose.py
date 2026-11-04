#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mac 端体检：给「切回 HDMI 黑屏」定位是哪一类原因

跑法：  python3 diagnose.py
输出：  一堆 KEY = VALUE，最后一段是结论和该装什么。

只读，不改任何设置。
"""

import os
import re
import shutil
import subprocess
import sys

def sh(cmd, timeout=25):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip()
    except Exception as e:
        return "ERR(%r)" % (e,)


def head(title):
    print("\n===== %s =====" % title)


def kv(k, v):
    print("%-26s = %s" % (k, v if v != "" else "(空)"))


def display_names():
    """当前在线显示器名字列表（JSON 优先，老系统退回文本解析）"""
    try:
        r = subprocess.run(["system_profiler", "SPDisplaysDataType", "-json"],
                           capture_output=True, text=True, timeout=25)
        data = __import__("json").loads(r.stdout or "{}")
        root = data.get("SPDisplaysDataType") or []
        if root:
            nv = root[0].get("spdisplays_ndrvs") or []
            out = []
            for d in nv:
                nm = d.get("_name") or d.get("_spdisplays_display-product-name") or "?"
                res = ""
                for k in ("_spdisplays_resolution", "_spdisplays_pixels", "spdisplays_resolution"):
                    if d.get(k):
                        res = d[k]
                        break
                out.append("%s%s" % (nm, (" (%s)" % res) if res else ""))
            return out
    except Exception:
        pass
    out = []
    for line in sh("system_profiler SPDisplaysDataType 2>/dev/null").splitlines():
        s = line.strip()
        if s.endswith(":") and ":" in s and not s.lower().startswith(("resolution", "ui looks", "display type")):
            nm = s.rstrip(":")
            if nm and nm not in ("Displays", "Graphics/Displays"):
                out.append(nm)
    return out


def watch(interval=2):
    """--watch：盯显示配置变化。
    用户在切信号源时跑着它，就能看到'切回那一瞬间外接屏有没有掉出去'——
    B 类（坞/链路）和 C 类（锁存）的分水岭就在这。"""
    import time
    print("盯着显示配置，Ctrl+C 结束。去 Windows 点一次「切到 Mac」，回来 Ctrl+C。")
    last = None
    start = time.time()
    while True:
        cur = display_names()
        sig = " + ".join(cur) if cur else "(没有显示器)"
        if sig != last:
            print("%s  [%d 块] %s" % (time.strftime("%H:%M:%S"), len(cur), sig))
            last = sig
        if time.time() - start > 1800:
            print("跑了 30 分钟，先停。")
            return 0
        time.sleep(interval)


def main():
    if "--watch" in sys.argv:
        try:
            return watch()
        except KeyboardInterrupt:
            print("\n结束。")
            return 0

    result = {}

    head("系统")
    kv("macos", sh("sw_vers -productVersion"))
    kv("model", sh("sysctl -n hw.model"))
    kv("chip", sh("sysctl -n machdep.cpu.brand_string") or sh("uname -m"))

    head("睡眠设置（A 类判定）")
    custom = sh("pmset -g custom")
    ac_block = ""
    bat_block = ""
    section = None
    for line in custom.splitlines():
        low = line.strip().lower()
        if low.startswith("ac power"):
            section = "ac"
            continue
        if low.startswith("battery power"):
            section = "bat"
            continue
        m = re.match(r"^\s*(displaysleep|sleep|standby|standbydelaylow|standbydelayhigh|powernap)\s+(\d+)", line)
        if m:
            key, val = m.group(1), m.group(2)
            if section == "ac":
                ac_block += "%s=%s " % (key, val)
            elif section == "bat":
                bat_block += "%s=%s " % (key, val)
    kv("pmset_ac", ac_block.strip())
    kv("pmset_battery", bat_block.strip())

    ds = re.search(r"displaysleep=(\d+)", ac_block)
    result["displaysleep_ac"] = int(ds.group(1)) if ds else -1
    kv("displaysleep_ac_min", str(result["displaysleep_ac"]) if ds else "未读到")

    assertions = sh("pmset -g assertions")
    keep_disp = len(re.findall(r"PreventUserIdleDisplaySleep\s+1", assertions))
    keep_sys = len(re.findall(r"PreventUserIdleSystemSleep\s+1", assertions))
    kv("assert_display_awake", keep_disp)
    kv("assert_system_awake", keep_sys)
    result["has_display_assertion"] = keep_disp > 0

    head("防睡眠组件（方案 A）")
    caf = sh("pgrep -fl caffeinate")
    kv("caffeinate_proc", caf or "未运行")
    plist_a = os.path.expanduser("~/Library/LaunchAgents/com.monswitch.awake.plist")
    kv("awake_plist", "存在" if os.path.exists(plist_a) else "不存在")
    result["scheme_a"] = bool(caf) and os.path.exists(plist_a)

    head("唤醒监听组件（方案 C）")
    lst = sh("pgrep -fl mac_wake_listener.py")
    kv("listener_proc", lst or "未运行")
    port = sh("lsof -nP -iUDP:9998 | tail -n +2")
    kv("udp_9998", port or "没有进程监听")
    plist_c = os.path.expanduser("~/Library/LaunchAgents/com.monswitch.wakelistener.plist")
    kv("listener_plist", "存在" if os.path.exists(plist_c) else "不存在")
    dp = ""
    for p in ("/opt/homebrew/bin/displayplacer", "/usr/local/bin/displayplacer", "/usr/bin/displayplacer"):
        if os.access(p, os.X_OK):
            dp = p
            break
    kv("displayplacer", dp or "未安装")
    modef = os.path.expanduser("~/.monswitch/mode.txt")
    kv("mode_cache", "存在" if os.path.exists(modef) else "不存在")
    logf = os.path.expanduser("~/.monswitch/listener.log")
    if os.path.exists(logf):
        tail = sh("tail -6 '%s'" % logf)
        print("--- listener.log 末尾 ---")
        print(tail)
    result["scheme_c"] = bool(lst) and bool(dp)

    head("显示器与链路（B 类判定）")
    disp = sh("system_profiler SPDisplaysDataType 2>/dev/null")
    ext = []
    cur = {}
    for line in disp.splitlines():
        s = line.strip()
        if s.startswith("Display Type:") or s.endswith(":") and ":" in s and line.startswith("        "):
            pass
        if re.match(r"^[A-Za-z0-9].*:$", s) and not s.startswith("Displays:"):
            if cur:
                ext.append(cur)
            cur = {"name": s.rstrip(":")}
        m = re.match(r"^(Resolution|UI Looks like|Main Display|Mirror|Online|Connection Type|Automatically Adjust Brightness)\s*:\s*(.+)$", s)
        if m and cur is not None:
            cur[m.group(1)] = m.group(2)
    if cur:
        ext.append(cur)

    for i, d in enumerate(ext):
        name = d.get("name", "?")
        if name in ("Displays", "Graphics/Displays"):
            continue
        kv("display_%d" % i, "%s | res=%s | conn=%s | main=%s" % (
            name, d.get("Resolution", "?"), d.get("Connection Type", "?"), d.get("Main Display", "?")))

    kv("display_count", len(ext))
    result["display_count"] = len(ext)

    dongle = sh("system_profiler SPUSBDataType 2>/dev/null | grep -iE 'dock|hub|DS-7A15|Acasis|阿卡西斯' | head -5")
    kv("dock_hint", dongle or "未识别到坞（可能是 Thunderbolt/USB4 设备，走 SPThunderboltDataType）")
    tb = sh("system_profiler SPThunderboltDataType 2>/dev/null | grep -iE 'Device Name|Vendor Name' | head -6")
    kv("thunderbolt_devices", tb or "无")

    head("最近睡眠/唤醒记录")
    log = sh("pmset -g log 2>/dev/null | grep -E 'Entering Sleep|Wake from|DarkWake' | tail -8")
    print(log or "（没有记录）")

    head("网络")
    kv("lan_ip", sh("ipconfig getifaddr en0") or sh("ipconfig getifaddr en1") or "未联网/无线未连")
    kv("firewall", sh("/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate 2>/dev/null"))

    head("结论")
    verdicts = []
    a_ok = result["scheme_a"]
    c_ok = result["scheme_c"]
    ds_min = result["displaysleep_ac"]

    if ds_min > 0 and not a_ok:
        verdicts.append("A 未做：接电源仍会在 %d 分钟后关闭显示器 → 装「4-保持Mac唤醒.command」" % ds_min)
    elif ds_min == 0:
        verdicts.append("A 已具备：系统层面不自动关屏")
    else:
        verdicts.append("A 已具备：caffeinate 在跑，不会空闲睡眠")

    if not c_ok:
        miss = []
        if not dp:
            miss.append("displayplacer 未装")
        if not lst:
            miss.append("监听未运行")
        verdicts.append("C 未做：%s → 装「6-安装唤醒监听.command」" % "、".join(miss))
    else:
        verdicts.append("C 已具备：监听在 9998 上跑，displayplacer 就位")

    if result["display_count"] <= 1:
        verdicts.append("B 待查：当前只识别到 %d 块屏，外接屏可能没在输出（切到 Mac 时应为 2 块）" % result["display_count"])

    for v in verdicts:
        print(" - " + v)

    print("""
下一步（照做，别猜）：
  1. 上面 A 未做 → 双击 4-保持Mac唤醒.command
  2. 上面 C 未做 → 双击 6-安装唤醒监听.command，防火墙点「允许」
  3. 两者都做完 → 本地打枪验证：
     python3 -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(b'WAKE',('127.0.0.1',9998))"
     sleep 1 && tail -3 ~/.monswitch/listener.log
     必须看到 "WAKE from" 和 "reapply -> True"
  4. 再去 Windows 上点「切到 Mac」，2 秒内出画面才算通过
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
