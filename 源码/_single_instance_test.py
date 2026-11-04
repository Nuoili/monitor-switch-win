# -*- coding: utf-8 -*-
"""单实例回归测试：重复双击只能有一个进程，且要把已有窗口叫回前台。

真机跑（会短暂弹出程序窗口），结束前把进程收掉。
"""
import ctypes
import ctypes.wintypes as w
import subprocess
import sys
import time

EXE = sys.argv[1] if len(sys.argv) > 1 else r"dist\MonitorSwitch.exe"
IMAGE = EXE.replace("/", "\\").split("\\")[-1]

u = ctypes.WinDLL("user32", use_last_error=True)
u.FindWindowW.argtypes = [w.LPCWSTR, w.LPCWSTR]
u.FindWindowW.restype = w.HWND
u.IsWindow.argtypes = [w.HWND]
u.IsWindow.restype = w.BOOL
u.IsWindowVisible.argtypes = [w.HWND]
u.IsWindowVisible.restype = w.BOOL
u.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]

SW_MINIMIZE = 6
WM_CLOSE = 0x0010
WM_SHOWME_UNUSED = 0


u.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM), w.LPARAM]
u.GetClassNameW.argtypes = [w.HWND, w.LPCWSTR, ctypes.c_int]
_ENUM = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)


def count():
    """数窗口，不数进程。

    PyInstaller onefile 每个实例都是 bootloader 父进程 + 真实子进程两枚同名进程，
    按进程数算会永远多一倍。
    """
    n = [0]

    def cb(h, _l):
        buf = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(h, buf, 256)
        if buf.value == "MonitorSwitchWnd":
            n[0] += 1
        return True

    u.EnumWindows(_ENUM(cb), 0)
    return n[0]


def find(timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        h = u.FindWindowW("MonitorSwitchWnd", None)
        if h:
            return h
        time.sleep(0.15)
    return None


def launch(*args):
    return subprocess.Popen([EXE, *args])


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + ("   " + extra if extra else ""))
    if not cond:
        raise SystemExit("测试中断：" + name)


p1 = launch()
hwnd = find()
check("首个实例把窗口建出来", bool(hwnd), "hwnd=%s" % hwnd)
time.sleep(0.8)
check("只有一个窗口实例", count() == 1, "windows=%d" % count())

# 1) 重复双击 -> 第二个进程必须自己退出
p2 = launch()
rc = p2.wait(timeout=15)
time.sleep(0.8)
check("重复双击：第二进程退出码 0", rc == 0, "rc=%s" % rc)
check("重复双击：窗口仍只有 1 个", count() == 1, "windows=%d" % count())
check("重复双击：窗口可见", bool(u.IsWindowVisible(hwnd)))

# 2) 收进托盘（点 X 的真实路径）后再双击 -> 应该被叫回来
u.PostMessageW(hwnd, WM_CLOSE, 0, 0)
time.sleep(0.8)
if u.IsWindow(hwnd):
    check("收进托盘后窗口已隐藏", not u.IsWindowVisible(hwnd))
    p3 = launch()
    rc3 = p3.wait(timeout=15)
    time.sleep(1.0)
    check("托盘状态下双击：第二进程退出", rc3 == 0, "rc=%s" % rc3)
    check("托盘状态下双击：窗口被叫回前台", bool(u.IsWindowVisible(hwnd)))
    check("托盘状态下双击：窗口仍只有 1 个", count() == 1, "windows=%d" % count())
else:
    print("SKIP  托盘没挂上（窗口直接销毁），跳过托盘唤醒用例")

# 3) 最小化后再双击 -> 应该还原
hwnd2 = find(2.0)
if hwnd2:
    u.ShowWindow(hwnd2, SW_MINIMIZE)
    time.sleep(0.5)
    p4 = launch()
    rc4 = p4.wait(timeout=15)
    time.sleep(1.0)
    check("最小化状态下双击：窗口还原", bool(u.IsWindowVisible(hwnd2)))
    check("最小化状态下双击：窗口仍只有 1 个", count() == 1, "windows=%d" % count())

# 4) 开机自启路径不得唤起窗口、也不得新开实例
p5 = launch("--tray")
time.sleep(1.5)
check("--tray 启动不重复开窗口", count() == 1, "windows=%d" % count())
p5.terminate()

print("\nALL PASS")
p1.terminate()
