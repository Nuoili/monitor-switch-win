#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mac 端唤醒监听

Windows 的「显示器切换」在切到 HDMI 之前，会往局域网广播一个 UDP WAKE 包。
本脚本收到后做两件事：

  1. caffeinate -u -t 2   声明一次"用户活动"，把睡下去的显示输出叫醒
  2. 用 displayplacer 重放一次当前显示配置（modeset），人为制造一次信号重新协商

为什么需要它：显示器长时间停在 DP 输入时，会把 HDMI 口判成"无信号"并锁存待机；
而 Mac 这边 HPD 一直是高电平，认为外接屏好得很，绝不会主动重新协商。
两边谁也不动，切回去就是黑的，必须手动按 OSD 才出画面。这个包就是踢僵局的那一脚。

零依赖（除 displayplacer），常驻内存约 12MB。
"""

import os
import socket
import subprocess
import time

PORT = 9998
HOME = os.path.expanduser("~")
CONF_DIR = os.path.join(HOME, ".monswitch")
MODE_FILE = os.path.join(CONF_DIR, "mode.txt")
LOG_FILE = os.path.join(CONF_DIR, "listener.log")

CANDIDATES = (
    "/opt/homebrew/bin/displayplacer",
    "/usr/local/bin/displayplacer",
    "/usr/bin/displayplacer",
)


def log(msg):
    try:
        os.makedirs(CONF_DIR, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write("%s %s\n" % (time.strftime("%m-%d %H:%M:%S"), msg))
        if os.path.getsize(LOG_FILE) > 200 * 1024:
            os.remove(LOG_FILE)
    except Exception:
        pass


def run(cmd, timeout=15):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True,
                              text=True, timeout=timeout)
    except Exception as e:
        log("run fail %r | %s" % (e, cmd))
        return None


def find_displayplacer():
    for p in CANDIDATES:
        if os.access(p, os.X_OK):
            return p
    return None


def capture(dp):
    """把当前显示配置记进 mode.txt，唤醒时原样重放。
    displayplacer list 末尾会给出可直接执行的配置命令，形如
        displayplacer "id:697D... res:2560x1440 hz:60 color_depth:8 ..."
    """
    r = run("%s list" % dp)
    if not r or r.returncode != 0:
        log("capture failed rc=%s" % (getattr(r, "returncode", "?"),))
        return []
    cmds = [l.strip() for l in r.stdout.splitlines()
            if l.strip().startswith("displayplacer ") and " list" not in l]
    if cmds:
        os.makedirs(CONF_DIR, exist_ok=True)
        with open(MODE_FILE, "w") as f:
            f.write("\n".join(cmds))
        log("captured %d mode cmd(s)" % len(cmds))
    else:
        log("capture: no mode line found")
    return cmds


def reapply(dp):
    cmds = []
    if os.path.exists(MODE_FILE):
        try:
            cmds = [l.strip() for l in open(MODE_FILE) if l.strip()]
        except Exception:
            cmds = []
    if not cmds:
        cmds = capture(dp)
    if not cmds:
        return False
    for c in cmds:
        run(c)
    return True


def main():
    os.makedirs(CONF_DIR, exist_ok=True)
    dp = find_displayplacer()
    log("start pid=%d displayplacer=%s" % (os.getpid(), dp))
    if dp:
        capture(dp)

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", PORT))
    log("listening udp/%d" % PORT)

    while True:
        try:
            data, addr = s.recvfrom(64)
        except KeyboardInterrupt:
            log("bye")
            return
        except Exception as e:
            log("recv err %r" % (e,))
            time.sleep(1)
            continue

        if data.strip() != b"WAKE":
            continue

        log("WAKE from %s" % (addr[0],))
        run("caffeinate -u -t 2")
        if dp:
            log("reapply -> %s" % reapply(dp))
        else:
            log("displayplacer missing, display woken only")


if __name__ == "__main__":
    main()
