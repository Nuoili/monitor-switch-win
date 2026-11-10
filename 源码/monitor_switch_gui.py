# -*- coding: utf-8 -*-
"""
Monitor Switch —— Windows 端正式程序

只有三个功能：
  1. 一键切换显示器信号源（DDC/CI · VCP 0x60）
  2. 全局热键：不看屏幕也能来回切（默认 Ctrl+Alt+Shift+D）
  3. 可选开机自动切回 Windows

常驻系统托盘：关闭窗口只是收进托盘，右键图标可切信号源、显示窗口、退出。

热键说明见 HOTKEY_DEFAULTS 上方的注释：候选列表按优先级注册，第一个成功的
才生效，所以被占用的组合会被自动跳过。

命令行（供快捷方式 / 开机自启）：
  --dp / --auto   静默切到 DP（Windows）
  --hdmi / --mac  静默切到 HDMI-1（Mac）
  --tray          直接以托盘方式启动（不弹窗口）
  --version       打印版本号（与 Mac 端共用同一套版本号）
  --hotkey        打印当前生效的热键与候选顺序
  --set-hotkey X  把热键改成一个自定义组合（如 Ctrl+Alt+Shift+F9）
  --no-hotkey     本次不注册热键（排查占位用）
  不带参数        打开窗口

单实例：程序已在运行时再双击图标，不会开出第二个窗口，而是把已有窗口
（哪怕已收进托盘或最小化）叫到前台。开机自启那条路径完全静默，不受影响。
"""

import base64
import ctypes
import os
import socket
import sys
import tempfile
import time
import winreg
from ctypes import wintypes

APP_TITLE = "Monitor Switch"
# 版本号双端统一：Windows / Mac 两个仓库同号同发，改这里必须同步改 Mac 仓的 VERSION 文件。
# 2.3.0 = 首次双端对齐版本（Win 2.2 的「来回切失效」修复 + 卸载器 + 版本可见化）
# 2.3.1 = 全局热键（Windows 端独有，Mac 端用自身脚本/快捷键）
# 2.4.0 = 改名 Monitor Switch（原「显示器切换」）+ 修窗口标题栏图标
APP_VERSION = "2.4.0"
APP_TITLE_FULL = "%s v%s" % (APP_TITLE, APP_VERSION)
VCP_INPUT = 0x60
INPUT_DP = 0x0F
INPUT_HDMI1 = 0x11

# 自启项名 / 配置键 / 临时目录都用带空格的产品名，任务管理器和 regedit 里一眼能认。
# 2.4.0 改名后带 OLD_ 前缀的三个常量只用于「迁移 + 清理旧版残留」。
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "Monitor Switch"
RUN_NAME_OLD = "MonitorSwitch"
CFG_KEY = r"Software\Monitor Switch"        # 本程序自己的配置（目前只存自定义热键）
CFG_KEY_OLD = r"Software\MonitorSwitch"     # 2.3.x 的旧位置，读到就搬到新位置
CFG_HOTKEY = "Hotkey"
TEMP_DIR = "Monitor Switch"

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
dxva2 = ctypes.WinDLL("dxva2", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
comctl32 = ctypes.WinDLL("comctl32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)


class INITCOMMONCONTROLSEX(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("dwICC", wintypes.DWORD)]


# ----------------------------------------------------------- DDC/CI

class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class PHYSICAL_MONITOR(ctypes.Structure):
    _fields_ = [("hPhysicalMonitor", wintypes.HANDLE),
                ("szPhysicalMonitorDescription", ctypes.c_wchar * 128)]


EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                              ctypes.POINTER(RECT), wintypes.LPARAM)

user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.c_void_p, EnumProc, wintypes.LPARAM]
user32.EnumDisplayMonitors.restype = wintypes.BOOL
dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, ctypes.POINTER(wintypes.DWORD)]
dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, wintypes.DWORD,
                                                  ctypes.POINTER(PHYSICAL_MONITOR)]
dxva2.GetPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
dxva2.SetVCPFeature.argtypes = [wintypes.HANDLE, ctypes.c_ubyte, wintypes.DWORD]
dxva2.SetVCPFeature.restype = wintypes.BOOL
dxva2.GetVCPFeatureAndVCPFeatureReply.argtypes = [wintypes.HANDLE, ctypes.c_ubyte,
                                                  ctypes.c_void_p,
                                                  ctypes.POINTER(wintypes.DWORD),
                                                  ctypes.POINTER(wintypes.DWORD)]
dxva2.GetVCPFeatureAndVCPFeatureReply.restype = wintypes.BOOL

_monitors = []
_keep = []          # 持有底层数组，防止结构体视图悬空
_hmons = []
_cached = [None, 0]  # [句柄, 取得时刻]


def _cb(hMon, hdc, lprc, dw):
    _hmons.append(hMon)
    return True


_proc = EnumProc(_cb)


def _enumerate():
    del _monitors[:]
    del _keep[:]
    del _hmons[:]
    user32.EnumDisplayMonitors(None, None, _proc, 0)
    for hmon in _hmons:
        n = wintypes.DWORD()
        if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmon, ctypes.byref(n)) or n.value <= 0:
            continue
        arr = (PHYSICAL_MONITOR * n.value)()
        if not dxva2.GetPhysicalMonitorsFromHMONITOR(hmon, n.value, arr):
            continue
        _keep.append(arr)
        for i in range(n.value):
            _monitors.append(arr[i])
    return _monitors


def _probe(h):
    """句柄是否真的能通 DDC"""
    if not h:
        return False
    cur, mx = wintypes.DWORD(), wintypes.DWORD()
    return bool(dxva2.GetVCPFeatureAndVCPFeatureReply(h, VCP_INPUT, None,
                                                      ctypes.byref(cur), ctypes.byref(mx)))


def _handle(force=False):
    """取一个能真正通 DDC 的物理显示器句柄。
    枚举结果不稳定（有时返回空句柄），所以逐个探测并重试。

    缓存句柄不能无条件复用：切换信号源后显示器对 Windows 而言是"重新接入"，
    旧的 hPhysicalMonitor 已失效，拿它 SetVCPFeature 会白跑（甚至假报成功），
    表现为"第一次能切，之后点了没反应"。所以缓存也要 probe 一次。
    """
    h = _cached[0]
    if h and not force:
        if _probe(h):
            return h
        _cached[0] = None          # 句柄死了，重新枚举
    for attempt in range(4):
        for pm in _enumerate():
            h = pm.hPhysicalMonitor
            if _probe(h):
                _cached[0] = h
                return h
        time.sleep(0.4)
    return None


def set_input(value):
    for _ in range(2):
        h = _handle()
        if h and dxva2.SetVCPFeature(h, VCP_INPUT, value):
            # 信号源变了，链路会重建，句柄别再留着
            _cached[0] = None
            return True
        _cached[0] = None
        time.sleep(0.3)
    return False


def get_input():
    h = _handle()
    if not h:
        return None
    cur, mx = wintypes.DWORD(), wintypes.DWORD()
    if not dxva2.GetVCPFeatureAndVCPFeatureReply(h, VCP_INPUT, None,
                                                 ctypes.byref(cur), ctypes.byref(mx)):
        _cached[0] = None
        return None
    return cur.value


def source_name(v):
    if v == INPUT_DP:
        return "DisplayPort", "Windows 这台"
    if v == INPUT_HDMI1:
        return "HDMI-1", "MacBook"
    if v is None:
        return "未知", "显示器未响应"
    return "0x%02X" % v, ""


# ----------------------------------------------------------- 唤醒 Mac

UDP_PORT = 9998


def _mac_targets():
    """优先用 exe 同目录的 mac_ip.txt 单播，没有就发广播。
    广播在多网卡/跨网段时会漏，能填 IP 就填（一行一个，# 开头是注释）。"""
    out = []
    try:
        p = os.path.join(os.path.dirname(exe_path()), "mac_ip.txt")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.split("#")[0].strip()
                    if line:
                        out.append(line)
    except OSError:
        pass
    return out or ["255.255.255.255"]


def _local_broadcasts():
    """本机各网段的定向广播地址（x.y.z.255）。

    只发 255.255.255.255 会走默认路由 —— 开着 VPN 时广播可能从虚拟网卡出去，
    Mac 根本收不到。所以把物理网段的 C 类广播也各发一份，用不依赖路由表的方式。
    """
    ips = set()
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            ips.add(ip)
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    out = set()
    for ip in ips:
        if ip.startswith(("127.", "0.")):
            continue
        parts = ip.split(".")
        if len(parts) == 4:
            out.add(".".join(parts[:3] + ["255"]))
    return sorted(out)


def wake_mac():
    """切到 HDMI 之前先捅 Mac 一下。

    显示器长时间停在 DP 时，会把 HDMI 口判成"无信号"并锁存待机；而 Mac 那边
    HPD 一直是高电平，认为外接屏好得很，绝不重新协商 —— 两边谁也不动，切回去
    就是黑的，得手动按 OSD 才出画面。

    Mac 上跑着一个监听脚本，收到这个包就重放一次显示配置（modeset），
    相当于给链路打一针，让显示器上电的检测窗口里能抓到新鲜信号。
    """
    targets = _mac_targets()          # mac_ip.txt 有内容就只单播
    if targets == ["255.255.255.255"]:
        targets = ["255.255.255.255"] + _local_broadcasts()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for addr in targets:
            try:
                s.sendto(b"WAKE", (addr, UDP_PORT))
            except OSError:
                pass
        s.close()
        return True
    except OSError:
        return False


# ----------------------------------------------------------- 日志

def log_error(e):
    """--noconsole 打包后 sys.stderr 是 None，直接 write 会二次抛异常、
    把真正的错误吞掉。改成写 %TEMP%\\Monitor Switch\\error.log。"""
    line = "%s %r\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), e)
    try:
        if sys.stderr:
            sys.stderr.write(line)
    except Exception:
        pass
    try:
        d = os.path.join(tempfile.gettempdir(), TEMP_DIR)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "error.log")
        if os.path.exists(p) and os.path.getsize(p) > 256 * 1024:
            os.remove(p)
        with open(p, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


# ----------------------------------------------------------- 全局热键

# 修饰键位标志（定义在这里而不是「常量」段，因为下面的候选表在模块导入时就要用）
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x0001, 0x0002, 0x0004, 0x0008
# 按住不放只触发一次；不加这个，系统会按键盘重复率狂发 WM_HOTKEY
MOD_NOREPEAT = 0x4000
HOTKEY_ID = 0xA001

# 候选热键：从第一个开始试，第一个注册成功的才生效；被占用会自动跳到下一个。
#
# 为什么一律用「三修饰键 + 字母/功能键」：
#   两修饰的组合在 Windows 上基本被占满了 ——
#     Ctrl+Alt+*   Intel 核显图形热键占 F1~F12；NVIDIA 用 Alt+Z、Alt+R、
#                  Ctrl+Alt+Insert；QQ 截图 Ctrl+Alt+A；旧显卡旋转屏 Ctrl+Alt+方向键
#     Ctrl+Shift+* 输入法切换、钉钉 Ctrl+Shift+A、IDE / 浏览器一堆默认键
#     Alt+Shift    语言与键盘布局切换（系统级，抢不到）
#     Alt+*        微信截图 Alt+A、各软件菜单栏 Alt+F / Alt+E
#     Win+*        全部归系统：Win+L/D/E/R/I/X/P/S/V/A/K/G/H/M/U/B/C/F/数字/方向键…
#   多加一个修饰键后几乎不撞车，代价是要三根手指 —— 对「一天切几次」的操作够用，
#   换来的是「按了必响，绝不被别的软件截胡」。
#
# 另外刻意避开的：
#   Ctrl+Alt+Del、Ctrl+Shift+Esc、Ctrl+Esc、Alt+Tab、Alt+Esc、Alt+F4、
#   PrintScreen、Alt+PrintScreen、Win+Shift+S —— 安全键与截图键，系统直接吞掉，
#   RegisterHotKey 本来就注册不上，别浪费候选位。
#   Ctrl+Space、Ctrl+Shift、Shift+Space、Ctrl+.、Ctrl+, —— 微软拼音热键。
#   F1 / F11 / F12 —— 帮助、全屏、开发者工具。
#   Win+Space —— 输入法切换。
HOTKEY_DEFAULTS = [
    ("Ctrl+Alt+Shift+D", MOD_CONTROL | MOD_ALT | MOD_SHIFT, ord("D")),
    ("Ctrl+Alt+Shift+M", MOD_CONTROL | MOD_ALT | MOD_SHIFT, ord("M")),
    ("Ctrl+Alt+Shift+F9", MOD_CONTROL | MOD_ALT | MOD_SHIFT, 0x78),   # VK_F9
    ("Ctrl+Alt+Shift+F10", MOD_CONTROL | MOD_ALT | MOD_SHIFT, 0x79),  # VK_F10
    ("Ctrl+Shift+F9", MOD_CONTROL | MOD_SHIFT, 0x78),
]

_VK_NAMED = {
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD,
    "\\": 0xDC, ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
}


def _vk_of(name):
    """键名 -> 虚拟键码，认不出来返回 None。"""
    low = name.lower()
    if low in _VK_NAMED:
        return _VK_NAMED[low]
    if len(name) == 1:
        c = name.upper()
        if ("A" <= c <= "Z") or ("0" <= c <= "9"):
            return ord(c)
    if low.startswith("f") and low[1:].isdigit():
        n = int(low[1:])
        if 1 <= n <= 24:
            return 0x6F + n                  # VK_F1 = 0x70
    return None


def parse_hotkey(text):
    """"Ctrl+Alt+Shift+D" -> (mods, vk)；写错一个字就返回 None。

    强制要求「至少一个修饰键 + 一个主键」：否则 --set-hotkey D 会把裸字母 D
    注册成全局热键，全系统打字都打不出来。
    """
    if not text:
        return None
    mods, vk = 0, None
    for part in [p.strip() for p in text.split("+") if p.strip()]:
        low = part.lower()
        if low in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif low == "alt":
            mods |= MOD_ALT
        elif low == "shift":
            mods |= MOD_SHIFT
        elif low in ("win", "super"):
            mods |= MOD_WIN
        else:
            k = _vk_of(part)
            if k is None:
                return None
            vk = k
    if not mods or vk is None:
        return None
    return mods, vk


def _cfg_read(key, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            v, _ = winreg.QueryValueEx(k, name)
            return v
    except OSError:
        return None


def cfg_get(name):
    """读配置；新位置没有就回落到 2.3.x 的旧键，读到后顺手搬过来。

    2.4.0 把配置键从 Software\\MonitorSwitch 改成了 Software\\Monitor Switch，
    不迁移的话老用户自定义的热键会凭空失效。
    """
    v = _cfg_read(CFG_KEY, name)
    if v is not None:
        return v
    v = _cfg_read(CFG_KEY_OLD, name)
    if v is not None:
        cfg_set(name, v)
    return v


def cfg_set(name, value):
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, CFG_KEY, 0,
                                winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        return True
    except OSError:
        return False


def hotkey_candidates():
    """自定义的排第一，其余按内置顺序去重。"""
    out, seen = [], set()
    custom = cfg_get(CFG_HOTKEY)
    if custom:
        parsed = parse_hotkey(custom)
        if parsed:
            desc = custom.strip()
            out.append((desc, parsed[0], parsed[1]))
            seen.add(desc.lower())
    for desc, mods, vk in HOTKEY_DEFAULTS:
        if desc.lower() in seen:
            continue
        out.append((desc, mods, vk))
        seen.add(desc.lower())
    return out


_hotkey = [None]        # 实际生效的热键字符串；None = 一个都没注册上


def hotkey_register(hwnd):
    """按候选顺序注册，返回生效的组合名；全被占用返回 None。

    注册到窗口上（而不是线程）是为了让 WM_HOTKEY 走正常的窗口消息。
    """
    for desc, mods, vk in hotkey_candidates():
        # MOD_NOREPEAT：按住不放只触发一次，否则会按键盘重复率连发
        if user32.RegisterHotKey(hwnd, HOTKEY_ID, mods | MOD_NOREPEAT, vk):
            _hotkey[0] = desc
            return desc
    _hotkey[0] = None
    return None


def hotkey_unregister(hwnd):
    """必须注销：热键是进程级注册，进程崩了才自动释放，正常退出不会。"""
    if _hotkey[0]:
        try:
            user32.UnregisterHotKey(hwnd, HOTKEY_ID)
        except Exception:
            pass
    _hotkey[0] = None


def hotkey_label():
    return _hotkey[0] or "未启用"


# ----------------------------------------------------------- 自启动

def exe_path():
    return os.path.abspath(sys.executable if getattr(sys, "frozen", False) else sys.argv[0])


def autostart_on():
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(k, RUN_NAME)
            return True
        finally:
            winreg.CloseKey(k)
    except OSError:
        return False


def set_autostart(enable):
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
        try:
            if enable:
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, '"%s" --auto --tray' % exe_path())
            else:
                winreg.DeleteValue(k, RUN_NAME)
        finally:
            winreg.CloseKey(k)
        return True
    except OSError:
        return False


def _run_value(name):
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ)
        try:
            val, _ = winreg.QueryValueEx(k, name)
            return val
        finally:
            winreg.CloseKey(k)
    except OSError:
        return None


def _del_run_value(name):
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(k, name)
        finally:
            winreg.CloseKey(k)
    except OSError:
        pass


def migrate_autostart():
    """把旧版的开机项迁到 2.4.0 的新名字 / 新路径上。

    2.4.0 把程序从「显示器切换.exe」改名成「Monitor Switch.exe」，旧的开机项
    值名是 MonitorSwitch、路径指向旧 exe。留着它会开机弹「找不到文件」，所以：
      · 旧值在 → 说明用户原来就勾了自启，按新名字 + 当前 exe 路径重写，再删旧值
      · 新值在但戳的不是当前 exe → 重写（换过目录、或改名前后路径不一致）

    只在打包后的 exe 里做：源码直跑时 exe_path() 是 .py，写进注册表等于给
    开机留一条错的命令。
    """
    if not getattr(sys, "frozen", False):
        return

    old = _run_value(RUN_NAME_OLD)
    cur = _run_value(RUN_NAME)

    if old:
        _del_run_value(RUN_NAME_OLD)
        set_autostart(True)
        return

    if cur and exe_path().lower() not in cur.lower():
        set_autostart(True)


# ----------------------------------------------------------- 常量

WM_CREATE, WM_DESTROY, WM_CLOSE = 0x0001, 0x0002, 0x0010
WM_COMMAND, WM_TIMER, WM_SETFONT = 0x0111, 0x0113, 0x0030
WM_CTLCOLORSTATIC = 0x0138
WM_NULL = 0x0000
WM_LBUTTONUP, WM_RBUTTONUP, WM_LBUTTONDBLCLK = 0x0202, 0x0205, 0x0203
WM_HOTKEY = 0x0312
WM_SETICON = 0x0080
ICON_SMALL, ICON_BIG = 0, 1       # WM_SETICON 的 wParam

# ---- 托盘
WM_APP = 0x8000
WM_TRAY = WM_APP + 1          # 托盘图标的回调消息
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x01, 0x02, 0x04, 0x10
NIIF_INFO = 0x01
MF_STRING, MF_CHECKED, MF_SEPARATOR, MF_GRAYED = 0x0000, 0x0008, 0x0800, 0x0001
TPM_RIGHTBUTTON, TPM_RETURNCMD = 0x0002, 0x0100
ID_TRAY = 1
MENU_MAC, MENU_WIN, MENU_SHOW, MENU_AUTO, MENU_QUIT = 201, 202, 203, 204, 205
SW_HIDE = 0
SM_CXSMICON, SM_CYSMICON = 49, 50
SM_CXICON, SM_CYCICON = 11, 12
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
CLR_INVALID = 0xFFFFFFFF

WS_OVERLAPPED, WS_CAPTION, WS_SYSMENU = 0x00000000, 0x00C00000, 0x00080000
WS_MINIMIZEBOX, WS_CHILD, WS_VISIBLE = 0x00020000, 0x40000000, 0x10000000
WS_TABSTOP = 0x00010000
BS_PUSHBUTTON, BS_AUTOCHECKBOX = 0x00000000, 0x00000003
SS_LEFT, SS_NOPREFIX = 0x00000000, 0x00000080
BM_SETCHECK, BM_GETCHECK = 0x00F1, 0x00F0
SW_SHOW = 5
SW_RESTORE = 9
ERROR_ALREADY_EXISTS = 183

# 单实例：窗口类名同时用作跨进程“叫醒”已有窗口的锚点
WND_CLASS = "MonitorSwitchWnd"
MUTEX_NAME = "Local\\MonitorSwitch.SingleInstance"

BN_CLICKED = 0
ID_MAC, ID_WIN, ID_CHK = 101, 102, 103
TIMER_CLOSE, TIMER_TEST, TIMER_REFRESH = 1, 9, 2

BG = 0x00FBF9F7
FG_TITLE = 0x00807060
FG_VALUE = 0x00201810
FG_TIP = 0x007E7870

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD), ("pt", wintypes.POINT)]


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    """托盘图标描述。cbSize 必须精确，Windows 按它判断结构版本。"""
    _fields_ = [("cbSize", wintypes.DWORD),
                ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HICON),
                ("szTip", ctypes.c_wchar * 128),
                ("dwState", wintypes.DWORD),
                ("dwStateMask", wintypes.DWORD),
                ("szInfo", ctypes.c_wchar * 256),
                ("uVersion", wintypes.UINT),
                ("szInfoTitle", ctypes.c_wchar * 64),
                ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", GUID),
                ("hBalloonIcon", wintypes.HICON)]


# ---- 函数签名（不设好会在 64 位下截断句柄 / 无法传字符串）
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t

user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
user32.CreateWindowExW.restype = wintypes.HWND

user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t

user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
user32.SetWindowTextW.restype = wintypes.BOOL

# 取 exe 里的图标资源。LoadIconW(hinst, 1) 在 PyInstaller onefile 里经常拿不到
# 真正编进去的那组图标（组 ID 不保证是 1），结果标题栏退化成系统的通用图标 ——
# 这就是 v2.3.x 截图里那个"不像自己 logo"的方框。ExtractIconExW 按 exe 路径取
# 第 0 组图标，大/小两个尺寸分别要。
# 注意在 shell32 里，不在 user32
shell32.ExtractIconExW.argtypes = [wintypes.LPCWSTR, ctypes.c_int,
                                   ctypes.POINTER(wintypes.HICON),
                                   ctypes.POINTER(wintypes.HICON), wintypes.UINT]
shell32.ExtractIconExW.restype = wintypes.UINT

user32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
user32.MessageBoxW.restype = ctypes.c_int

user32.SetTimer.argtypes = [wintypes.HWND, wintypes.WPARAM, wintypes.UINT, ctypes.c_void_p]
user32.SetTimer.restype = wintypes.WPARAM
user32.KillTimer.argtypes = [wintypes.HWND, wintypes.WPARAM]
user32.KillTimer.restype = wintypes.BOOL

user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wintypes.ATOM
user32.AdjustWindowRectEx.argtypes = [ctypes.POINTER(RECT), wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
user32.AdjustWindowRectEx.restype = wintypes.BOOL
user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
user32.SystemParametersInfoW.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.restype = ctypes.c_ssize_t
user32.LoadIconW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
user32.LoadIconW.restype = wintypes.HICON
user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
user32.LoadCursorW.restype = wintypes.HANDLE
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = [wintypes.HWND]
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = ctypes.c_void_p
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
user32.UpdateWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.GetDpiForWindow.argtypes = [wintypes.HWND]
user32.GetDpiForWindow.restype = wintypes.UINT
gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
gdi32.SetBkMode.restype = ctypes.c_int
gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.DWORD]
gdi32.SetTextColor.restype = wintypes.DWORD

gdi32.CreateSolidBrush.argtypes = [wintypes.DWORD]
gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
gdi32.CreateFontW.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                              wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                              wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR]
gdi32.CreateFontW.restype = wintypes.HFONT

# ---- 托盘 / 菜单签名
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL

user32.CreatePopupMenu.argtypes = []
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.AppendMenuW.restype = wintypes.BOOL
user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, wintypes.HWND, ctypes.c_void_p]
user32.TrackPopupMenu.restype = ctypes.c_int
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.DestroyMenu.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p, wintypes.UINT,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.LoadImageW.restype = wintypes.HANDLE
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
gdi32.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.GetPixel.restype = wintypes.DWORD
user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
user32.RegisterWindowMessageW.restype = wintypes.UINT

hinst = kernel32.GetModuleHandleW(None)


# ----------------------------------------------------------- 托盘

# explorer.exe 重启（或用户重启桌面）后广播这条消息，收到就得重新加图标，
# 否则托盘里那块会凭空消失。
WM_TASKBARCREATED = user32.RegisterWindowMessageW("TaskbarCreated")

# 第二个进程双击启动时，靠这条注册消息通知已有实例“把窗口亮出来”。
# RegisterWindowMessage 对同名消息在所有进程里返回同一个值，不需要别的 IPC。
WM_SHOWME = user32.RegisterWindowMessageW("MonitorSwitch-ShowMe")
# --set-hotkey 改完注册表后用它戳已运行的实例，让它当场换绑，不用重启程序
WM_RELOAD_HOTKEY = user32.RegisterWindowMessageW("MonitorSwitch-ReloadHotkey")

_nid = [None]        # 当前登记中的 NOTIFYICONDATAW
_tray_on = [False]   # 托盘是否真的挂上了（挂不上就不能靠隐藏窗口，否则窗口找不回来）
_hicon_app = [None]

# 托盘图标 = 程序图标的单色版（透明底，只剩两个屏幕和双向箭头）。
# 深色任务栏用白图案，浅色任务栏用深灰图案，运行时按任务栏实际颜色挑。
_TRAY_ICO = {
    "dark": "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",
    "light": "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",
}
_tray_hicon = [None]
_ico_cache = {}


def _tray_ico_file(kind):
    """内嵌的 ico 落到临时目录，再交给 LoadImageW 按尺寸挑图，比缩放锐利。"""
    path = _ico_cache.get(kind)
    if path and os.path.exists(path):
        return path
    try:
        d = os.path.join(tempfile.gettempdir(), TEMP_DIR)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "tray_%s.ico" % kind)
        data = base64.b64decode(_TRAY_ICO[kind])
        if (not os.path.exists(path)) or os.path.getsize(path) != len(data):
            with open(path, "wb") as f:
                f.write(data)
        _ico_cache[kind] = path
        return path
    except OSError:
        return None


def _taskbar_is_light():
    """采样任务栏真实像素判断明暗。

    注册表里的 SystemUsesLightTheme 不可靠——单独设置任务栏颜色、或用第三方
    任务栏工具时它仍是浅色值，照它挑图标会挑成"白图案压白底"。
    """
    try:
        hwnd = user32.FindWindowW("Shell_TrayWnd", None)
        if not hwnd:
            return False
        r = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return False
        w = r.right - r.left
        h = r.bottom - r.top
        if w <= 0 or h <= 0:
            return False
        hdc = user32.GetDC(None)
        if not hdc:
            return False
        tot, n = 0.0, 0
        try:
            # 两侧边缘通常没图标；纵向取中下部，避开按钮高光
            for fx in (0.06, 0.10, 0.88, 0.92, 0.96):
                for fy in (0.55, 0.80):
                    c = gdi32.GetPixel(hdc, r.left + int(w * fx), r.top + int(h * fy))
                    if c == CLR_INVALID:
                        continue
                    tot += ((c & 0xFF) + ((c >> 8) & 0xFF) + ((c >> 16) & 0xFF)) / 3.0
                    n += 1
        finally:
            user32.ReleaseDC(None, hdc)
        return n > 0 and (tot / n) > 140
    except Exception:
        return False


def app_icons():
    """返回 (大图标, 小图标)，用于窗口类 + 标题栏。

    三条回落路径，按可靠性从高到低：
      1. 从当前 exe 里取图标资源 —— 打包后走这条，是真正编进 exe 的 logo
      2. 源码目录下的 icon.ico —— 用 python 直接跑时走这条
      3. 系统默认应用图标 —— 兜底，总比没有强
    小图标必须单独取：直接把 32px 的图塞进 ICON_SMALL，标题栏会糊成一团。
    """
    big = wintypes.HICON()
    sml = wintypes.HICON()

    exe = sys.executable or ""
    # frozen 才从 exe 取；源码直跑时 sys.executable 是 python.exe，取出来是 Python 的图标
    if getattr(sys, "frozen", False) and exe.lower().endswith(".exe"):
        try:
            n = shell32.ExtractIconExW(exe, 0, ctypes.byref(big), ctypes.byref(sml), 1)
            if n and (big.value or sml.value):
                return big.value and big, sml.value and sml
        except Exception:
            pass

    ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    if os.path.exists(ico):
        cb = user32.GetSystemMetrics(SM_CXICON) or 32
        cs = user32.GetSystemMetrics(SM_CXSMICON) or 16
        b = user32.LoadImageW(None, ico, IMAGE_ICON, cb, cb, LR_LOADFROMFILE)
        s = user32.LoadImageW(None, ico, IMAGE_ICON, cs, cs, LR_LOADFROMFILE)
        if b or s:
            return b, s

    h = user32.LoadIconW(None, ctypes.c_void_p(32512))   # IDI_APPLICATION
    return h, h


def tray_icon():
    """按系统小图标尺寸取单色图标；取不到再退回 exe 里的彩色图标。"""
    cx = user32.GetSystemMetrics(SM_CXSMICON) or 16
    cy = user32.GetSystemMetrics(SM_CYSMICON) or 16
    kind = "light" if _taskbar_is_light() else "dark"
    path = _tray_ico_file(kind)
    h = user32.LoadImageW(None, path, IMAGE_ICON, cx, cy, LR_LOADFROMFILE) if path else 0
    if not h:
        h = user32.LoadImageW(hinst, ctypes.c_void_p(1), IMAGE_ICON, cx, cy, 0)
    if h:
        _tray_hicon[0] = h
    return h or _hicon_app[0]


def _blank_nid(hwnd):
    n = NOTIFYICONDATAW()
    n.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
    n.hWnd = hwnd
    n.uID = ID_TRAY
    return n


def tray_add(hwnd, tip):
    n = _blank_nid(hwnd)
    n.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
    n.uCallbackMessage = WM_TRAY
    n.hIcon = tray_icon()
    n.szTip = (tip or APP_TITLE)[:120]
    if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(n)):
        # 上一次没清理干净时会失败，先删再试一次
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(n))
        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(n)):
            _tray_on[0] = False
            return False
    _nid[0] = n
    _tray_on[0] = True
    return True


def tray_tip(text):
    """返回 False 说明图标其实不在托盘里（NIM_MODIFY 对不存在的图标会失败）。"""
    cur = _nid[0]
    if cur is None:
        return False
    cur.szTip = (text or APP_TITLE)[:120]
    cur.uFlags = NIF_TIP
    return bool(shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(cur)))


def tray_balloon(title, text):
    """首次收进托盘时提示一次，免得用户以为程序被关掉了。"""
    cur = _nid[0]
    if cur is None:
        return False
    n = _blank_nid(cur.hWnd)
    n.uFlags = NIF_INFO
    n.szInfoTitle = title[:60]
    n.szInfo = text[:250]
    n.dwInfoFlags = NIIF_INFO
    return bool(shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(n)))


def tray_remove():
    cur = _nid[0]
    if cur is not None:
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(cur))
    _nid[0] = None
    _tray_on[0] = False


def tray_menu(hwnd):
    hm = user32.CreatePopupMenu()
    if not hm:
        return 0
    user32.AppendMenuW(hm, MF_STRING, MENU_MAC, "切到 Mac（HDMI-1）")
    user32.AppendMenuW(hm, MF_STRING, MENU_WIN, "切回 Windows（DisplayPort）")
    # 灰显一行把热键摆在眼前，省得用户去翻说明；点不动也不占菜单位
    user32.AppendMenuW(hm, MF_STRING | MF_GRAYED, 0,
                       "热键 %s · 来回切" % hotkey_label())
    user32.AppendMenuW(hm, MF_SEPARATOR, 0, None)
    user32.AppendMenuW(hm, MF_STRING, MENU_SHOW, "显示主窗口")
    user32.AppendMenuW(hm, MF_STRING | (MF_CHECKED if autostart_on() else 0),
                       MENU_AUTO, "开机时自动切回 Windows")
    user32.AppendMenuW(hm, MF_SEPARATOR, 0, None)
    user32.AppendMenuW(hm, MF_STRING, MENU_QUIT, "退出")

    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    # 不先抢焦点的话，点菜单外面菜单不会消失
    user32.SetForegroundWindow(hwnd)
    cmd = user32.TrackPopupMenu(hm, TPM_RETURNCMD | TPM_RIGHTBUTTON,
                                pt.x, pt.y, 0, hwnd, None)
    user32.PostMessageW(hwnd, WM_NULL, 0, 0)
    user32.DestroyMenu(hm)
    return cmd


# ----------------------------------------------------------- 界面

class App:
    def __init__(self):
        self.hwnd = None
        self.ctrls = {}
        self.fonts = {}
        self.dpi = 96
        self.busy = False
        self.brush = None
        self.quitting = False      # True 时关闭窗口才真退出，否则只是收进托盘
        self.tip_shown = False     # 托盘提示只弹一次
        self._tip = APP_TITLE_FULL  # 托盘悬浮文字缓存，避免频繁读 DDC
        self.no_hotkey = False     # --no-hotkey：本次不注册热键（排查占位用）

    def tray_text(self):
        return self._tip

    def tip_text(self):
        """窗口底部那行说明，把当前实际生效的热键摆出来。"""
        if self.no_hotkey:
            return "本次未启用热键 · 关闭窗口后常驻托盘"
        if _hotkey[0]:
            return "热键 %s 来回切 · 关闭窗口后常驻托盘" % _hotkey[0]
        return "热键未启用（候选组合被占用）· 右键托盘图标可切换"

    def S(self, v):
        return int(round(v * self.dpi / 96.0))

    def font(self, pt, bold=False):
        key = (pt, bold)
        if key not in self.fonts:
            self.fonts[key] = gdi32.CreateFontW(
                -self.S(pt * 96 / 72.0), 0, 0, 0, 700 if bold else 400,
                0, 0, 0, 1, 0, 0, 5, 0, "Microsoft YaHei UI")
        return self.fonts[key]

    def static(self, text, x, y, w, h, pt, bold, color, ident):
        hw = user32.CreateWindowExW(0, "STATIC", text,
                                    WS_CHILD | WS_VISIBLE | SS_LEFT | SS_NOPREFIX,
                                    self.S(x), self.S(y), self.S(w), self.S(h),
                                    self.hwnd, None, hinst, None)
        user32.SendMessageW(hw, WM_SETFONT, self.font(pt, bold), 1)
        self.ctrls[ident] = (hw, color)
        return hw

    def button(self, text, x, y, w, h, ident):
        hw = user32.CreateWindowExW(0, "BUTTON", text,
                                    WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
                                    self.S(x), self.S(y), self.S(w), self.S(h),
                                    self.hwnd, wintypes.HMENU(ident), hinst, None)
        user32.SendMessageW(hw, WM_SETFONT, self.font(11, True), 1)
        return hw

    def checkbox(self, text, x, y, w, h, checked, ident):
        hw = user32.CreateWindowExW(0, "BUTTON", text,
                                    WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_AUTOCHECKBOX,
                                    self.S(x), self.S(y), self.S(w), self.S(h),
                                    self.hwnd, wintypes.HMENU(ident), hinst, None)
        user32.SendMessageW(hw, WM_SETFONT, self.font(10), 1)
        user32.SendMessageW(hw, BM_SETCHECK, 1 if checked else 0, 0)
        self.ctrls["chk"] = (hw, FG_VALUE)
        return hw

    def build(self):
        self.static("当前信号源", 26, 20, 200, 22, 9, False, FG_TITLE, "cap")
        self.sub = self.static("读取中…", 26, 42, 370, 38, 16, True, FG_VALUE, "val")
        self.button("切到 Mac", 26, 100, 174, 54, ID_MAC)
        self.button("切回 Windows", 220, 100, 174, 54, ID_WIN)
        self.checkbox("开机时自动切回 Windows", 26, 172, 368, 26, autostart_on(), ID_CHK)
        self.static(self.tip_text(), 26, 214, 368, 22, 8.5, False, FG_TIP, "tip")
        # DDC 探测偶尔要重试一两秒，同步做会卡住窗口创建；交给定时器异步读
        user32.SetTimer(self.hwnd, TIMER_REFRESH, 60, None)

    def refresh(self):
        try:
            name, who = source_name(get_input())
            user32.SetWindowTextW(self.sub, name + ("（%s）" % who if who else ""))
            self._tip = "%s · 当前 %s" % (APP_TITLE_FULL, name)
            tray_tip(self._tip)
        except Exception:
            pass

    def do_switch(self, value, label, quiet=False):
        """执行切换。

        quiet=True 是热键用的静默路径：不把主窗口叫到前台 —— 正在打游戏、
        看视频、开会共享屏幕时按一下热键，屏幕上不该突然蹦出一个窗口。

        注意 busy 必须走 finally 复位：以前只在失败分支清，成功一次之后
        busy 永远是 True，后面每次点击都被 `if self.busy: return` 静默吞掉
        —— 这正是"切到 Mac、切回来、再点切 Mac 就没反应"的原因。
        """
        if self.busy:
            if not quiet:
                self.say("上一次切换还没结束…")
            return
        self.busy = True
        try:
            # 从托盘菜单点进来时窗口是隐藏的，先亮出来，否则看不到任何过程
            if self.hwnd and not quiet:
                user32.ShowWindow(self.hwnd, SW_SHOW)
                user32.SetForegroundWindow(self.hwnd)
            if not quiet:
                self.say("正在切到 %s …" % label)
            if value == INPUT_HDMI1:
                # 先让 Mac 重新协商一次，再切信号源，否则撞上显示器的"无信号"锁存
                wake_mac()
                time.sleep(0.4)
            ok = False
            for i in range(3):
                if set_input(value):
                    ok = True
                    break
                self.say("第 %d 次没成功，重试中…" % (i + 1))
                time.sleep(0.8)
            if ok:
                self.say("已切换到 " + label)
                if quiet:
                    # 热键路径没有可见窗口，用托盘气泡给个确认。
                    # 切走那一下看不到，切回来时能看到，等于留了条"上次干了什么"。
                    tray_balloon(APP_TITLE_FULL, "已切到 %s" % label)
                else:
                    user32.SetTimer(self.hwnd, TIMER_CLOSE, 1200, None)
            else:
                self.say("切换失败")
                user32.MessageBoxW(self.hwnd,
                                   "显示器没有响应 DDC 命令。\n\n"
                                   "请确认：\n"
                                   "· 显示器 OSD 菜单里的 DDC/CI 已开启\n"
                                   "· 视频线连接正常\n"
                                   "· 目标那台机器已开机并输出信号",
                                   APP_TITLE, 0x40000 | 0x10)
        finally:
            self.busy = False

    def hotkey_switch(self):
        """热键：在两端之间来回切（toggle）。

        为什么不做成「切到 Mac」单向：切走之后这台 Windows 就黑屏了，鼠标键盘
        够不到任何按钮 —— 这时唯一还能用的入口就是热键自己。做成 toggle，
        「摸黑按一下切回 Windows」才成立，这也是热键最大的价值所在。
        """
        if self.busy:
            return
        cur = get_input()
        if cur == INPUT_HDMI1:
            target, label = INPUT_DP, "DisplayPort（Windows）"
        else:
            # 读不到当前值（显示器休眠 / DDC 没回话）时按最常见场景走：
            # 人在 Windows 上，下一步是想去 Mac。
            target, label = INPUT_HDMI1, "HDMI-1（Mac）"
        self.do_switch(target, label, quiet=True)

    def say(self, text):
        """改状态文字并立刻重绘 —— 同步 sleep 期间消息循环不转，
        不 UpdateWindow 的话界面会像卡死一样没有任何变化。"""
        try:
            user32.SetWindowTextW(self.sub, text)
            user32.UpdateWindow(self.hwnd)
        except Exception:
            pass


app = App()


def force_foreground(hwnd):
    """把窗口提到最前。

    Windows 只允许“前台进程”抢焦点，托盘图标或第二个进程去 SetForegroundWindow
    往往只闪一下任务栏。临时把本线程附到当前前台线程上，拿到权限再换回来。
    """
    fg = user32.GetForegroundWindow()
    tid_fg = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    tid_self = kernel32.GetCurrentThreadId()
    attached = False
    if tid_fg and tid_fg != tid_self:
        attached = bool(user32.AttachThreadInput(tid_self, tid_fg, True))
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    if attached:
        user32.AttachThreadInput(tid_self, tid_fg, False)


def show_main(hwnd):
    if user32.IsIconic(hwnd):        # 最小化状态下 SW_SHOW 不管用
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.ShowWindow(hwnd, SW_SHOW)
    force_foreground(hwnd)
    # 窗口隐藏期间信号源可能被 Mac 端改过，重新读一次再显示
    user32.SetTimer(hwnd, TIMER_REFRESH, 60, None)


def close_main(hwnd):
    """真退出：先摘掉托盘图标，否则任务栏会留一个点不掉的残影。"""
    app.quitting = True
    tray_remove()
    user32.DestroyWindow(hwnd)


def retire(hwnd):
    """收起窗口。托盘没挂上就直接退出 —— 否则窗口既看不见也叫不回来。"""
    if app.quitting or not _tray_on[0]:
        close_main(hwnd)
        return
    user32.ShowWindow(hwnd, SW_HIDE)
    if not app.tip_shown:
        app.tip_shown = True
        tray_balloon(APP_TITLE, "已收进托盘。右键图标可切换信号源或退出。")


def run_menu_cmd(hwnd, cmd):
    if cmd == MENU_MAC:
        app.do_switch(INPUT_HDMI1, "HDMI-1（Mac）")
    elif cmd == MENU_WIN:
        app.do_switch(INPUT_DP, "DisplayPort（Windows）")
    elif cmd == MENU_SHOW:
        show_main(hwnd)
    elif cmd == MENU_AUTO:
        set_autostart(not autostart_on())
        if "chk" in app.ctrls:
            user32.SendMessageW(app.ctrls["chk"][0], BM_SETCHECK,
                                1 if autostart_on() else 0, 0)
    elif cmd == MENU_QUIT:
        close_main(hwnd)


def wndproc(hwnd, msg, wparam, lparam):
    try:
        if msg == WM_CREATE:
            app.hwnd = hwnd
            try:
                app.dpi = user32.GetDpiForWindow(hwnd) or 96
            except Exception:
                app.dpi = 96
            if app.dpi < 96:
                app.dpi = 96
            # 先注册热键再 build：build 里那行说明文字要读到实际生效的组合
            if not app.no_hotkey:
                try:
                    hotkey_register(hwnd)
                except Exception as e:
                    log_error(e)
            app.build()
            return 0

        if msg == WM_HOTKEY:
            if wparam == HOTKEY_ID:
                app.hotkey_switch()
            return 0

        if msg == WM_RELOAD_HOTKEY and msg:
            # 另一个进程用 --set-hotkey 改完注册表后戳我一下，免得重启程序
            hotkey_unregister(hwnd)
            hotkey_register(hwnd)
            if "tip" in app.ctrls:
                user32.SetWindowTextW(app.ctrls["tip"][0], app.tip_text())
            return 0

        if msg == WM_SHOWME and msg:
            # 另一个进程被双击启动：把已有窗口叫回前台，绝不再开一个
            show_main(hwnd)
            return 0

        if msg == WM_TASKBARCREATED and msg:
            # 资源管理器重启过，托盘被清空，重新挂回去
            tray_add(hwnd, app.tray_text())
            return 0

        if msg == WM_TRAY:
            btn = lparam & 0xFFFF
            if btn in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                show_main(hwnd)
            elif btn == WM_RBUTTONUP:
                run_menu_cmd(hwnd, tray_menu(hwnd))
            return 0

        if msg == WM_COMMAND:
            ident = wparam & 0xFFFF
            code = (wparam >> 16) & 0xFFFF
            if code == BN_CLICKED:
                if ident == ID_MAC:
                    app.do_switch(INPUT_HDMI1, "HDMI-1（Mac）")
                elif ident == ID_WIN:
                    app.do_switch(INPUT_DP, "DisplayPort（Windows）")
                elif ident == ID_CHK:
                    hw = app.ctrls["chk"][0]
                    state = user32.SendMessageW(hw, BM_GETCHECK, 0, 0)
                    if not set_autostart(state == 1):
                        user32.SendMessageW(hw, BM_SETCHECK, 0 if state == 1 else 1, 0)
                        user32.MessageBoxW(hwnd, "写入开机启动项失败。", APP_TITLE, 0x40000 | 0x30)
            return 0

        if msg == WM_TIMER:
            if wparam == TIMER_CLOSE:
                user32.KillTimer(hwnd, TIMER_CLOSE)
                retire(hwnd)          # 切完自动收进托盘，不退出
            elif wparam == TIMER_REFRESH:
                user32.KillTimer(hwnd, TIMER_REFRESH)
                app.refresh()
            elif wparam == TIMER_TEST:
                user32.KillTimer(hwnd, TIMER_TEST)
                close_main(hwnd)
            return 0

        if msg == WM_CTLCOLORSTATIC:
            hdc = wparam
            ctrl = lparam
            gdi32.SetBkMode(hdc, 1)
            color = FG_VALUE
            for h, c in app.ctrls.values():
                if h == ctrl:
                    color = c
                    break
            gdi32.SetTextColor(hdc, color)
            return ctypes.cast(app.brush, ctypes.c_void_p).value or 0

        if msg == WM_CLOSE:
            retire(hwnd)
            return 0

        if msg == WM_DESTROY:
            hotkey_unregister(hwnd)
            tray_remove()
            user32.PostQuitMessage(0)
            return 0
    except Exception as e:
        log_error(e)

    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


wndproc_cb = WNDPROC(wndproc)


def run_gui(selftest=False, start_hidden=False):
    # 启用 comctl32 v6 主题（配合 manifest，按钮才是现代外观）
    try:
        icc = INITCOMMONCONTROLSEX()
        icc.dwSize = ctypes.sizeof(INITCOMMONCONTROLSEX)
        icc.dwICC = 0x00FF
        comctl32.InitCommonControlsEx(ctypes.byref(icc))
    except Exception:
        pass

    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
        except Exception:
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass

    if not selftest:
        try:
            migrate_autostart()
        except Exception:
            pass

    app.brush = gdi32.CreateSolidBrush(BG)

    try:
        hicon, hicon_sm = app_icons()
    except Exception:
        hicon, hicon_sm = None, None
    if not hicon:
        hicon = user32.LoadIconW(None, ctypes.c_void_p(32512))
    if not hicon_sm:
        hicon_sm = hicon
    _hicon_app[0] = hicon

    cls = WND_CLASS
    wc = WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
    wc.style = 0x0003
    wc.lpfnWndProc = wndproc_cb
    wc.hInstance = hinst
    wc.hIcon = hicon
    wc.hIconSm = hicon_sm
    wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32512))
    wc.hbrBackground = app.brush
    wc.lpszClassName = cls
    user32.RegisterClassExW(ctypes.byref(wc))

    style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX
    rc = RECT(0, 0, 420, 252)
    user32.AdjustWindowRectEx(ctypes.byref(rc), style, False, 0)
    w, h = rc.right - rc.left, rc.bottom - rc.top

    wa = RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(wa), 0)
    x = wa.left + (wa.right - wa.left - w) // 2
    y = wa.top + (wa.bottom - wa.top - h) // 2

    hwnd = user32.CreateWindowExW(0, cls, APP_TITLE_FULL, style, x, y, w, h, None, None, hinst, None)
    if not hwnd:
        return 2
    # 再显式设一次：某些系统版本对窗口类里的 hIcon 不生效（尤其 onefile 解包后）。
    # 注意 SendMessageW 的第 4 个参数声明成 LPARAM（整数），ctypes 的 HICON 对象
    # 不能直传，必须先取 .value，否则打包后会抛
    # "argument 4: TypeError: 'c_void_p' object cannot be interpreted as an integer"。
    def _hv(h):
        return h.value if isinstance(h, ctypes.c_void_p) else int(h or 0)
    user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, _hv(hicon))
    user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, _hv(hicon_sm))
    if not start_hidden:
        user32.ShowWindow(hwnd, SW_SHOW)
        user32.UpdateWindow(hwnd)
        user32.SetForegroundWindow(hwnd)
    tray_add(hwnd, app.tray_text())

    if not app.no_hotkey and _hotkey[0] is None:
        # 候选全被占用：不静默失败，告诉用户一声，并指出还能怎么用
        tray_balloon(APP_TITLE,
                     "热键没注册上：候选组合都被别的程序占了。\n"
                     "右键托盘图标照样能切；换组合见 使用说明.txt。")

    if selftest:
        user32.SetTimer(hwnd, TIMER_TEST, 1200, None)

    msg = MSG()
    while True:
        r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
        if r == 0 or r == -1:
            break
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    return 0


def silent(value):
    if value == INPUT_HDMI1:
        wake_mac()
        time.sleep(0.4)
    for _ in range(4):
        if set_input(value):
            return 0
        time.sleep(1.5)
    return 1


_mutex = [None]


def claim_single_instance():
    """建单实例锁。True = 本进程是唯一实例。

    句柄存全局变量，进程活着就一直持有；进程退出系统自动释放，不会留死锁。
    """
    h = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not h:
        return True                      # 锁都建不出来就别拦着用户
    _mutex[0] = h
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS


def wake_existing():
    """已有实例在跑就把它的窗口叫到前台，返回 True（本进程随即退出）。

    用 FindWindow 而不是只靠锁：老版本没有锁，也能被新版本这一下唤起。
    """
    hwnd = user32.FindWindowW(WND_CLASS, None)
    if not hwnd:
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.PostMessageW(hwnd, WM_SHOWME, 0, 0)
    return True


def main():
    raw = sys.argv[1:]
    args = [a.lower() for a in raw]
    if "--version" in args or "-v" in args or "--ver" in args:
        text = "%s %s" % (APP_TITLE, APP_VERSION)
        print(text)
        if getattr(sys, "frozen", False):
            # 打包后是 noconsole，print 没地方去 —— 弹个窗口才看得见
            user32.MessageBoxW(None, text, APP_TITLE, 0x40)
        return 0
    if "--selftest-gui" in args:
        return run_gui(selftest=True)
    if "--state" in args:
        n, who = source_name(get_input())
        print("%s (%s)" % (n, who))
        return 0

    if "--hotkey" in args:
        cands = hotkey_candidates()
        custom = cfg_get(CFG_HOTKEY)
        text = "%s %s\n\n" % (APP_TITLE, APP_VERSION)
        if custom:
            text += "自定义热键：%s\n" % custom
        text += "默认热键：%s\n" % cands[0][0]
        text += "候选顺序（前面的被占用就自动顺延）：\n  " + \
                "\n  ".join(d for d, _, _ in cands)
        print(text)
        if getattr(sys, "frozen", False):
            user32.MessageBoxW(None, text, APP_TITLE, 0x40)
        return 0

    if "--set-hotkey" in args:
        i = args.index("--set-hotkey")
        val = (raw[i + 1] if i + 1 < len(raw) else "").strip()
        parsed = parse_hotkey(val)
        if not parsed:
            text = ("热键写法不对：%r\n\n"
                    "要求「至少一个修饰键 + 一个主键」，且中间不能有空格，例如：\n"
                    "  Ctrl+Alt+Shift+D\n"
                    "  Ctrl+Alt+Shift+F9\n"
                    "  Ctrl+Win+M\n\n"
                    "修饰键可用：Ctrl / Alt / Shift / Win" % val)
            print(text)
            if getattr(sys, "frozen", False):
                user32.MessageBoxW(None, text, APP_TITLE, 0x40 | 0x10)
            return 2
        if not cfg_set(CFG_HOTKEY, val):
            text = "写注册表失败，热键没改。"
            print(text)
            if getattr(sys, "frozen", False):
                user32.MessageBoxW(None, text, APP_TITLE, 0x40 | 0x10)
            return 2
        # 已经有实例在跑就戳它当场换绑，否则新组合要等下次启动才生效
        hwnd = user32.FindWindowW(WND_CLASS, None)
        if hwnd:
            user32.PostMessageW(hwnd, WM_RELOAD_HOTKEY, 0, 0)
            text = "热键已改为 %s，正在运行的程序已即时换绑。" % val
        else:
            text = "热键已改为 %s，下次启动生效。" % val
        print(text)
        if getattr(sys, "frozen", False):
            user32.MessageBoxW(None, text, APP_TITLE, 0x40)
        return 0

    # --tray = 开机自启（静默，不弹窗）；其余无参数启动 = 用户双击图标
    silent_start = "--tray" in args

    # 纯命令行动作不涉及界面，也就不进单实例逻辑
    if not silent_start:
        if any(a in ("--auto", "--dp", "--win", "--windows") for a in args):
            return silent(INPUT_DP)
        if any(a in ("--hdmi", "--hdmi1", "--mac") for a in args):
            return silent(INPUT_HDMI1)

    app.no_hotkey = "--no-hotkey" in args

    if not silent_start and wake_existing():
        return 0                         # 已有实例，唤起它，本进程立即退出

    if not claim_single_instance():
        if not silent_start:
            wake_existing()              # 抢锁失败但窗口还没建好，补一枪
        return 0

    if silent_start:
        # 开机自启走这条：先静默切好信号源，再常驻托盘
        if any(a in ("--auto", "--dp", "--win", "--windows") for a in args):
            silent(INPUT_DP)
        elif any(a in ("--hdmi", "--hdmi1", "--mac") for a in args):
            silent(INPUT_HDMI1)
        return run_gui(start_hidden=True)

    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
