"""테스트용 EPUB 픽스처 생성 — good.epub(규정 준수) / bad.epub(규정 위반 모음).

python tests/make_fixtures.py [출력폴더]
"""
from __future__ import annotations

import io
import os
import sys
import zipfile

from PIL import Image

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "fixtures")

CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""


def xhtml(title: str, body: str, lang: str = ' xml:lang="ko" lang="ko"') -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml"{lang}>
<head><title>{title}</title><link rel="stylesheet" type="text/css" href="style.css"/></head>
<body>{body}</body></html>"""


def opf(version: str, publisher: str, spine: list[str], extra_items: str = "", meta_cover: bool = True,
        toc_attr: str = ' toc="ncx"') -> str:
    items = "\n".join(f'<item id="{i}" href="{i}.xhtml" media-type="application/xhtml+xml"/>' for i in spine)
    refs = "\n".join(f'<itemref idref="{i}"/>' for i in spine)
    cover_meta = '<meta name="cover" content="cover-img"/>' if meta_cover else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<package version="{version}" xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">urn:uuid:11111111-2222-3333-4444-555555555555</dc:identifier>
    <dc:title>테스트 도서</dc:title>
    <dc:creator>홍길동</dc:creator>
    <dc:publisher>{publisher}</dc:publisher>
    <dc:language>ko</dc:language>
    <dc:date>2026-09-01</dc:date>
    {cover_meta}
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="css" href="style.css" media-type="text/css"/>
    <item id="cover-img" href="cover.jpg" media-type="image/jpeg"/>
    {items}
    {extra_items}
  </manifest>
  <spine{toc_attr}>
    {refs}
  </spine>
</package>"""


def ncx(points: list[tuple[str, str]], depth_chain: int = 0) -> str:
    nav = "\n".join(f'<navPoint id="n{i}"><navLabel><text>{label}</text></navLabel><content src="{src}"/></navPoint>'
                    for i, (label, src) in enumerate(points))
    deep = ""
    if depth_chain:
        deep = "".join(f'<navPoint id="d{i}"><navLabel><text>깊이{i}</text></navLabel><content src="ch1.xhtml"/>'
                       for i in range(depth_chain)) + "</navPoint>" * depth_chain
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="urn:uuid:11111111-2222-3333-4444-555555555555"/></head>
  <docTitle><text>테스트 도서</text></docTitle>
  <navMap>{nav}{deep}</navMap>
</ncx>"""


def jpeg(width: int, height: int, mode: str = "RGB") -> bytes:
    buf = io.BytesIO()
    Image.new(mode, (width, height), (200, 120, 60) if mode == "RGB" else (0, 60, 90, 10)).save(buf, "JPEG")
    return buf.getvalue()


def write_epub(path: str, files: dict[str, bytes | str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for name, data in files.items():
            payload = data.encode("utf-8") if isinstance(data, str) else data
            zf.writestr(name, payload, compress_type=zipfile.ZIP_DEFLATED)


def good_epub(path: str) -> None:
    spine = ["cover", "ch1", "ch2", "copyright"]
    files = {
        "META-INF/container.xml": CONTAINER,
        "OEBPS/content.opf": opf("2.0", "유페이퍼", spine),
        "OEBPS/toc.ncx": ncx([("표지", "cover.xhtml"), ("1장", "ch1.xhtml"), ("2장", "ch2.xhtml"), ("판권", "copyright.xhtml")]),
        "OEBPS/style.css": "body { line-height: 1.7; } h1 { font-size: 1.4em; color: #2C2822; }",
        "OEBPS/cover.jpg": jpeg(700, 1000),
        "OEBPS/cover.xhtml": xhtml("표지", '<div><img src="cover.jpg" alt="표지"/></div>'),
        "OEBPS/ch1.xhtml": xhtml("1장", "<h1>1장</h1><p>본문입니다. 하늘은 왜 파랄까요.</p>"),
        "OEBPS/ch2.xhtml": xhtml("2장", "<h1>2장</h1><p>두 번째 장입니다.</p>"),
        "OEBPS/copyright.xhtml": xhtml("판권", "<h1>판권</h1><p>테스트 도서</p><p>지은이 홍길동</p>"
                                       "<p>발행일 2026년 9월 1일</p><p>발행처 유페이퍼</p><p>정가 5,900원</p>"
                                       "<p>ISBN 979-11-6811-999-4</p>"),
    }
    write_epub(path, files)


def bad_epub(path: str) -> None:
    spine = ["ch1", "cover", "cover2", "empty", "copyright", "copyright2", "last"]
    extra = '<item id="unused" href="unused.jpg" media-type="image/jpeg"/>' \
            '<item id="font" href="font.ttf" media-type="application/x-font-ttf"/>'
    files = {
        "META-INF/container.xml": CONTAINER,
        "OEBPS/content.opf": opf("3.0", "홍길동출판", spine, extra_items=extra),
        "OEBPS/toc.ncx": ncx([("", "ch1.xhtml"), ("표지", "cover.xhtml"), ("없는파일", "nope.xhtml")], depth_chain=4),
        "OEBPS/style.css": "p { color: #000000; font-size: 12pt; } body { background-color: #000; }",
        "OEBPS/cover.jpg": jpeg(1600, 2560, "CMYK"),
        "OEBPS/unused.jpg": jpeg(10, 10),
        "OEBPS/font.ttf": b"\x00\x01\x00\x00",
        "OEBPS/cover.xhtml": xhtml("표지", '<div><img src="cover.jpg" alt="표지"/></div>'),
        "OEBPS/cover2.xhtml": xhtml("표지2", '<div><img src="cover.jpg" alt="표지"/></div>'),
        "OEBPS/ch1.xhtml": xhtml("1장", '<h1>1장</h1><p style="color:black">본문입니다. 표지 페이지로 오인되지 않도록 '
                                 '글이 충분히 길어야 합니다. 하늘은 왜 파랄까요.</p><script>alert(1)</script>'
                                 '<iframe src="x"></iframe><ul><li>항목</li></ul><a href="javascript:void(0)" onclick="x()">x</a>'
                                 '<img src="missing.jpg" alt=""/><font color="#000000">검정</font>', lang=""),
        "OEBPS/empty.xhtml": xhtml("빈", "<div></div>"),
        "OEBPS/copyright.xhtml": xhtml("판권", "<h1>판권</h1><p>지은이 홍길동</p><p>발행처 홍길동출판</p>"
                                       "<p>출판등록 제2026-000001호</p><p>ISBN 978-0-00-000000-1</p>"),
        "OEBPS/copyright2.xhtml": xhtml("판권", "<h1>판권</h1><p>발행일 2026.9.1</p><p>펴낸곳 어딘가</p>"),
        "OEBPS/last.xhtml": xhtml("끝", "<p>마지막 <b>장</p>"),
    }
    write_epub(path, files)


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    good_epub(os.path.join(OUT_DIR, "good.epub"))
    bad_epub(os.path.join(OUT_DIR, "bad.epub"))
    print("fixtures written to", OUT_DIR)
