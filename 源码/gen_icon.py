# -*- coding: utf-8 -*-
"""生成应用图标：icon.ico（Windows）+ icon.icns（macOS）"""
import os, io, struct
from PIL import Image, ImageDraw

OUT = os.path.dirname(os.path.abspath(__file__))
S = 1024

def rr(d, box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=int(r), fill=fill, outline=outline, width=int(width))

def make(size=S):
    k = size / 1024.0
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # 背景：圆角深蓝渐变
    bg = Image.new("RGB", (size, size), (0, 0, 0))
    bd = ImageDraw.Draw(bg)
    for y in range(size):
        t = y / size
        bd.line([(0, y), (size, y)],
                fill=(int(26 + 20 * t), int(44 + 38 * t), int(80 + 56 * t)))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1],
                                           radius=int(229 * k), fill=255)
    im.paste(bg, (0, 0), mask)
    d = ImageDraw.Draw(im)

    top, h, w = 292 * k, 228 * k, 296 * k
    lx, rx = 128 * k, 600 * k

    # 左显示器：实心
    rr(d, [lx, top, lx + w, top + h], 24 * k, fill=(255, 255, 255, 255))
    rr(d, [lx + 100 * k, top + h, lx + w - 100 * k, top + h + 40 * k], 6 * k,
       fill=(255, 255, 255, 255))
    rr(d, [lx + 56 * k, top + h + 40 * k, lx + w - 56 * k, top + h + 56 * k], 8 * k,
       fill=(255, 255, 255, 255))

    # 右显示器：描边
    o = (255, 255, 255, 205)
    rr(d, [rx, top, rx + w, top + h], 24 * k, outline=o, width=26 * k)
    rr(d, [rx + 100 * k, top + h, rx + w - 100 * k, top + h + 40 * k], 6 * k, fill=o)
    rr(d, [rx + 56 * k, top + h + 40 * k, rx + w - 56 * k, top + h + 56 * k], 8 * k, fill=o)

    # 中间双向箭头
    acc = (118, 226, 170, 255)
    ay = 706 * k
    cx1, cx2 = 358 * k, 666 * k
    th = 34 * k
    d.rounded_rectangle([cx1, ay - th / 2, cx2, ay + th / 2], radius=th / 2, fill=acc)
    d.polygon([(cx1 - 26 * k, ay), (cx1 + 36 * k, ay - 56 * k), (cx1 + 36 * k, ay + 56 * k)],
              fill=acc)
    d.polygon([(cx2 + 26 * k, ay), (cx2 - 36 * k, ay - 56 * k), (cx2 - 36 * k, ay + 56 * k)],
              fill=acc)
    return im

master = make()
master.save(os.path.join(OUT, "icon_1024.png"))

# ---- Windows .ico ----
master.save(os.path.join(OUT, "icon.ico"),
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

# ---- macOS .icns（PNG 数据块）----
entries = [(b"ic07", 128), (b"ic08", 256), (b"ic09", 512), (b"ic10", 1024),
           (b"ic11", 32), (b"ic12", 64), (b"ic13", 256), (b"ic14", 512)]
chunks = b""
for typ, sz in entries:
    buf = io.BytesIO()
    master.resize((sz, sz), Image.LANCZOS).save(buf, format="PNG")
    data = buf.getvalue()
    chunks += typ + struct.pack(">I", len(data) + 8) + data
icns = b"icns" + struct.pack(">I", len(chunks) + 8) + chunks
with open(os.path.join(OUT, "icon.icns"), "wb") as f:
    f.write(icns)

print("icon.ico", os.path.getsize(os.path.join(OUT, "icon.ico")))
print("icon.icns", os.path.getsize(os.path.join(OUT, "icon.icns")))
