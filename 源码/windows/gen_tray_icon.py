"""生成托盘用的单色（黑白）图标。

托盘图标只有 16×16，直接缩放 1024 原图会糊成一团；这里按 16 单位网格重绘：
两个屏幕轮廓 + 双向箭头，透明背景，前景色可指定（深色任务栏用白，浅色用深灰）。

用法：python gen_tray_icon.py
产出：
  tray_light.ico  白色图案，给【深色任务栏】用（源码 _TRAY_ICO["dark"]）
  tray_dark.ico   深灰图案，给【浅色任务栏】用（源码 _TRAY_ICO["light"]）
  _tray_preview.png  两套图标在深/浅背景下的各尺寸预览

重新生成后，需要把两个 ico 重新 base64 注入 monitor_switch_gui.py 的 _TRAY_ICO。
"""

from PIL import Image, ImageDraw

SIZES = (16, 20, 24, 32, 48, 256)
SS = 16            # 超采样倍数


def _draw(fg, style="base"):
    """按 16 单位网格画一张大图，返回分尺寸的列表。

    小尺寸（<=24px）走简版：不画显示器底座，屏幕更大、箭头更粗，
    否则 16px 上底座横线会和箭头挤成一条，认不出来。
    """
    out = []
    for size in SIZES:
        small = size <= 24
        S = size * SS
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        def u(v):
            return v / 16.0 * S

        lw = max(1, round(u(1.05)))
        top, bot = (1.80, 8.20) if small else (1.70, 7.60)

        # 左屏：实心，代表 Windows 那头
        d.rounded_rectangle((u(1.15), u(top), u(7.10), u(bot)),
                            radius=u(0.80), fill=fg)
        # 右屏：空心，代表 Mac 那头
        d.rounded_rectangle((u(8.90), u(top), u(14.85), u(bot)),
                            radius=u(0.80), outline=fg, width=lw)

        if not small:
            # 底座：竖颈 + 底横
            d.rectangle((u(3.55), u(7.60), u(4.70), u(9.05)), fill=fg)
            d.rounded_rectangle((u(2.45), u(9.05), u(5.80), u(9.80)),
                                radius=u(0.35), fill=fg)
            d.rectangle((u(11.30), u(7.60), u(12.45), u(9.05)), fill=fg)
            d.rounded_rectangle((u(10.20), u(9.05), u(13.55), u(9.80)),
                                radius=u(0.35), fill=fg)
            cy = 12.0
        else:
            cy = 11.6

        # 双向箭头
        bar = 1.40
        d.rectangle((u(3.6), u(cy - bar / 2), u(12.4), u(cy + bar / 2)), fill=fg)
        hh = 1.75                  # 箭头半高
        d.polygon([(u(1.65), u(cy)), (u(3.75), u(cy - hh)), (u(3.75), u(cy + hh))], fill=fg)
        d.polygon([(u(14.35), u(cy)), (u(12.25), u(cy - hh)), (u(12.25), u(cy + hh))], fill=fg)

        out.append(img.resize((size, size), Image.LANCZOS))
    return out


def build(fg, path):
    frames = _draw(fg)
    frames[-1].save(path, format="ICO",
                    sizes=[(s, s) for s in SIZES], append_images=frames[:-1])
    return frames


def main():
    WHITE = (255, 255, 255, 255)
    DARK = (26, 28, 34, 255)
    light = build(WHITE, "tray_light.ico")
    dark = build(DARK, "tray_dark.ico")

    # 预览：深色底摆白图标，浅色底摆深图标
    zoom = 12
    pad = 10
    cols = [16, 20, 24, 32, 48]
    W = pad
    for s in cols:
        W += s * zoom + pad * 2
    H = (48 * zoom + pad * 2) * 2
    canvas = Image.new("RGBA", (W, H), (32, 32, 32, 255))
    canvas.paste(Image.new("RGBA", (W, 48 * zoom + pad * 2), (250, 250, 252, 255)),
                 (0, 48 * zoom + pad * 2))
    for row, frames in enumerate((light, dark)):
        y0 = row * (48 * zoom + pad * 2) + pad
        x = pad
        for i, s in enumerate(cols):
            t = frames[i].resize((s * zoom, s * zoom), Image.NEAREST)
            canvas.alpha_composite(t, (x, y0))
            x += s * zoom + pad * 2
    canvas.convert("RGB").save("_tray_preview.png")
    print("ok", canvas.size)


if __name__ == "__main__":
    main()
