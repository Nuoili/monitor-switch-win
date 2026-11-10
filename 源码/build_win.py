# -*- coding: utf-8 -*-
"""Windows 端一键打包：生成 version_info.txt 并调用 PyInstaller 出单文件 exe。

版本号只有一个源头 —— monitor_switch_gui.py 里的 APP_VERSION，
本脚本读它来渲染 exe 的版本资源，避免"程序里写一个数、属性里写另一个数"。

用法（仓库根目录）：
    python 源码/build_win.py
产物：
    源码/dist/Monitor Switch.exe   （再手动覆盖到仓库根的 Monitor Switch.exe）
"""

import os
import re
import subprocess
import sys

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SRC_DIR)
MAIN_PY = os.path.join(SRC_DIR, "monitor_switch_gui.py")

VERSION_INFO_TMPL = u"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({v0}, {v1}, {v2}, 0),
    prodvers=({v0}, {v1}, {v2}, 0),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([StringTable(u'080404B0', [
      StringStruct(u'CompanyName', u'Nuoili'),
      StringStruct(u'FileDescription', u'{title} · Windows 端（DDC/CI 一键切信号源）'),
      StringStruct(u'FileVersion', u'{ver}.0'),
      StringStruct(u'InternalName', u'MonitorSwitch'),
      StringStruct(u'OriginalFilename', u'{title}.exe'),
      StringStruct(u'LegalCopyright', u'MIT License'),
      StringStruct(u'ProductName', u'{title}'),
      StringStruct(u'ProductVersion', u'{ver}')
    ])]),
    VarFileInfo([VarStruct(u'Translation', [2052, 1200])])
  ]
)
"""


def read_version():
    with open(MAIN_PY, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r'^APP_VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"', src, re.M)
    if not m:
        raise SystemExit("monitor_switch_gui.py 里找不到 APP_VERSION")
    return m.group(1)


def read_title():
    with open(MAIN_PY, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r'^APP_TITLE\s*=\s*"([^"]+)"', src, re.M)
    return m.group(1) if m else "MonitorSwitch"


def main():
    ver = read_version()
    title = read_title()
    v0, v1, v2 = (int(x) for x in ver.split("."))

    vi_path = os.path.join(SRC_DIR, "version_info.txt")
    with open(vi_path, "w", encoding="utf-8") as f:
        f.write(VERSION_INFO_TMPL.format(v0=v0, v1=v1, v2=v2, ver=ver, title=title))
    print("version_info.txt -> %s" % ver)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile", "--noconsole",
        "--name", title,
        "--icon", os.path.join(SRC_DIR, "icon.ico"),
        "--manifest", os.path.join(SRC_DIR, "app.manifest"),
        "--version-file", vi_path,
        "--distpath", os.path.join(SRC_DIR, "dist"),
        "--workpath", os.path.join(SRC_DIR, "build"),
        "--specpath", SRC_DIR,
        MAIN_PY,
    ]
    print(" ".join(cmd))
    rc = subprocess.call(cmd)
    out = os.path.join(SRC_DIR, "dist", title + ".exe")
    if rc != 0:
        raise SystemExit("PyInstaller 失败，退出码 %d" % rc)
    if not os.path.exists(out):
        raise SystemExit("没找到产物：%s" % out)
    print("OK %s  %.1f MB" % (out, os.path.getsize(out) / 1048576.0))
    print("下一步：把这个 exe 覆盖到 %s" % os.path.join(REPO_DIR, title + ".exe"))


if __name__ == "__main__":
    main()
