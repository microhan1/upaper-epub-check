"""시작 그림(assets/splash.png)을 만든다 — exe 를 켜자마자 압축을 푸는 동안 보이는 작은 그림.

    python assets/make_splash.py [저장 경로]

창과 같은 색(종이·갈색·금색)으로 책 한 권과 「유페이퍼 EPUB 검수」「켜는 중…」 을 그린다. 크게 그린 뒤 줄여
가장자리를 매끈하게 하고, 색을 64색으로 줄여 파일을 작게 둔다(PyInstaller 가 exe 안에 그대로 싣는다).
자홍색(#FF00FF)은 Windows 시작 그림에서 투명을 뜻하므로 쓰지 않는다.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding="utf-8")
SCALE = 4
W, H = 320, 110
PAPER, INK, BROWN, GOLD, MUTED, ZONE = "#FAF6EF", "#2C2822", "#6B4F3B", "#C9A66B", "#6B6257", "#F5F1E8"
FONT_BOLD, FONT_REGULAR = r"C:\Windows\Fonts\malgunbd.ttf", r"C:\Windows\Fonts\malgun.ttf"
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "splash.png")


def draw_book(d, s):
    """왼쪽에 펼친 책 — 두 쪽과 가운데 접힌 선, 쪽마다 글줄 세 개."""
    x0, y0, x1, y1 = 26 * s, 28 * s, 86 * s, 80 * s
    mid = (x0 + x1) // 2
    d.rounded_rectangle((x0, y0, x1, y1), radius=3 * s, fill="white", outline=BROWN, width=s)
    d.line((mid, y0, mid, y1), fill=BROWN, width=s)
    for px0, px1 in ((x0 + 7 * s, mid - 6 * s), (mid + 6 * s, x1 - 7 * s)):
        for k in range(3):
            yy = y0 + (13 + k * 12) * s
            d.rectangle((px0, yy, px1 - (k == 2) * 8 * s, yy + 3 * s), fill=GOLD)
    d.rectangle((x0 + 2 * s, y1 + 2 * s, x1 - 2 * s, y1 + 4 * s), fill=ZONE)   # 책 아래 그림자


def main(path):
    s = SCALE
    img = Image.new("RGB", (W * s, H * s), PAPER)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W * s - 1, H * s - 1), outline=GOLD, width=s)
    draw_book(d, s)
    title = ImageFont.truetype(FONT_BOLD, 20 * s)
    sub = ImageFont.truetype(FONT_REGULAR, 12 * s)
    d.text((104 * s, 44 * s), "유페이퍼 EPUB 검수", font=title, fill=BROWN, anchor="lm")
    d.text((105 * s, 70 * s), "켜는 중…", font=sub, fill=MUTED, anchor="lm")
    small = img.resize((W, H), Image.LANCZOS).convert("P", palette=Image.ADAPTIVE, colors=64)
    small.save(path, optimize=True)
    print(path, os.path.getsize(path), "bytes")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT)
