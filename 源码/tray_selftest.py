# -*- coding: utf-8 -*-
"""托盘功能自检：不依赖人工点击，走一遍 建窗口 -> 加图标 -> 读回 -> 退出清理。"""
import ctypes
import sys
import threading
import time

import monitor_switch_gui as m

ok = True


def check(name, cond, extra=""):
    global ok
    if not cond:
        ok = False
    print("%-28s %s %s" % (name, "PASS" if cond else "FAIL", extra))


def mkmenu():
    hm = m.user32.CreatePopupMenu()
    check("CreatePopupMenu", bool(hm))
    r1 = m.user32.AppendMenuW(hm, m.MF_STRING, m.MENU_MAC, "切到 Mac（HDMI-1）")
    r2 = m.user32.AppendMenuW(hm, m.MF_SEPARATOR, 0, None)
    r3 = m.user32.AppendMenuW(hm, m.MF_STRING | m.MF_CHECKED, m.MENU_AUTO, "开机自启")
    check("AppendMenuW x3", bool(r1 and r2 and r3))
    m.user32.DestroyMenu(hm)


print("---- 结构体 ----")
check("sizeof(NOTIFYICONDATAW)", ctypes.sizeof(m.NOTIFYICONDATAW) > 500,
      "= %d" % ctypes.sizeof(m.NOTIFYICONDATAW))
check("TaskbarCreated 消息", bool(m.WM_TASKBARCREATED), "= 0x%04X" % m.WM_TASKBARCREATED)

print("---- 菜单 ----")
mkmenu()

print("---- 窗口 + 托盘 ----")
t = threading.Thread(target=lambda: m.run_gui(selftest=True), daemon=True)
t.start()
time.sleep(1.0)

check("窗口已创建", bool(m.app.hwnd))
check("托盘已注册", m._tray_on[0] is True)
nid = m._nid[0]
check("NOTIFYICONDATA 有效", nid is not None)
if nid is not None:
    check("hIcon 非空", bool(nid.hIcon), "= %s" % nid.hIcon)
    check("回调消息", nid.uCallbackMessage == m.WM_TRAY)
    check("悬浮提示非空", bool(nid.szTip), "szTip=%r" % nid.szTip)
check("托盘图标句柄可获取", bool(m.tray_icon()))

print("---- 等自检定时器退出 ----")
t.join(timeout=10)
check("消息循环已退出", not t.is_alive())
check("退出后图标已摘除", m._tray_on[0] is False)
check("退出后 hwnd 记录", m._nid[0] is None)
check("信号源已异步读取", "当前" in m.app._tip, "tip=%r" % m.app._tip)

print("---- 自动启动项 ----")
check("migrate_autostart 可调用", callable(m.migrate_autostart))
try:
    import winreg
    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, m.RUN_KEY, 0, winreg.KEY_READ)
    try:
        v, _ = winreg.QueryValueEx(k, m.RUN_NAME)
        print("  当前注册值: %s" % v)
    except OSError:
        print("  当前无开机自启项（未开启）")
    finally:
        winreg.CloseKey(k)
except OSError:
    pass

print()
print("RESULT:", "ALL PASS" if ok else "HAS FAILURE")
sys.exit(0 if ok else 1)
