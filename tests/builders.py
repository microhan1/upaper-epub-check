"""테스트용 EPUB 조립기.

검사 규칙 하나를 시험하려면 '그 규칙만 어긋난 책'이 필요하다. 그래서 기본값이 규정을 지키는
책(`Book()`)을 만들고, 시험할 부분만 바꿔 `build()` 하는 방식으로 쓴다.

    Book(publisher="홍길동").build(path)          # 출판사명만 어긋난 책
    Book(docs=[Doc("ch1", body="<p>본문</p>")]).build(path)

ZIP 은 EPUB 규격대로 mimetype 을 첫 항목·무압축으로 쓴다. 그 규격 자체를 시험할 때만
mimetype_first·mimetype_stored·mimetype_text 를 건드린다.
"""
from __future__ import annotations

import io
import os
import zipfile
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont

CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="{opf}" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""
XHTML_HEAD = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">"""
DEFAULT_CSS = "body { line-height: 1.7; } h1 { font-size: 1.4em; color: #2C2822; }"
COLOPHON_BODY = ("<h1>판권</h1><p>테스트 도서</p><p>지은이 홍길동</p><p>발행일 2026년 9월 1일</p>"
                 "<p>발행처 유페이퍼</p><p>정가 5,900원</p><p>ISBN 979-11-6811-999-4</p>")
FONT_PATH = r"C:\Windows\Fonts\malgun.ttf"
COVER_TEXT_COLOR = (60, 45, 35)
COVER_BG = (245, 238, 225)


def xhtml(title: str, body: str, lang: str = ' xml:lang="ko" lang="ko"', css: str | None = "style.css") -> str:
    link = f'<link rel="stylesheet" type="text/css" href="{css}"/>' if css else ""
    return (f"{XHTML_HEAD}\n<html xmlns=\"http://www.w3.org/1999/xhtml\"{lang}>\n"
            f"<head><title>{title}</title>{link}</head>\n<body>{body}</body></html>")


def image_bytes(width: int = 700, height: int = 1000, mode: str = "RGB", fmt: str = "JPEG",
                lines: tuple[tuple[str, int], ...] = ()) -> bytes:
    """표지·삽화용 이미지. lines 를 주면 그 글자를 그려 넣는다(표지 문구 확인 시험용)."""
    img = Image.new(mode, (width, height), COVER_BG if mode == "RGB" else (0, 60, 90, 10))
    if lines and mode == "RGB":
        draw = ImageDraw.Draw(img)
        y = height // 3
        for text, size in lines:
            font = ImageFont.truetype(FONT_PATH, size)
            draw.text(((width - draw.textlength(text, font=font)) / 2, y), text, font=font, fill=COVER_TEXT_COLOR)
            y += size + 40
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()


@dataclass
class Doc:
    """spine 에 들어가는 본문 문서."""
    doc_id: str
    body: str = "<h1>장</h1><p>본문입니다. 충분히 긴 문장을 넣어 표지로 오인되지 않게 합니다.</p>"
    title: str = "장"
    lang: str = ' xml:lang="ko" lang="ko"'
    css: str | None = "style.css"
    raw: str | None = None          # 문법이 깨진 XHTML 을 그대로 넣을 때
    nav_label: str | None = None    # None 이면 title 을 목차명으로

    @property
    def href(self) -> str:
        return f"{self.doc_id}.xhtml"

    def content(self) -> str:
        return self.raw if self.raw is not None else xhtml(self.title, self.body, self.lang, self.css)


@dataclass
class Asset:
    """manifest 에 들어가는 비문서 파일(이미지·폰트·CSS)."""
    asset_id: str
    href: str
    media_type: str
    data: bytes
    in_manifest: bool = True
    write_file: bool = True
    properties: str = ""


def cover_doc(doc_id: str = "cover", href: str = "cover.jpg") -> Doc:
    return Doc(doc_id, body=f'<div><img src="{href}" alt="표지"/></div>', title="표지")


def colophon_doc(doc_id: str = "colophon", body: str = COLOPHON_BODY) -> Doc:
    return Doc(doc_id, body=body, title="판권")


@dataclass
class Book:
    """기본값이 규정을 지키는 EPUB. 시험할 항목만 바꿔 쓴다."""
    title: str = "테스트 도서"
    creator: str = "홍길동"
    publisher: str = "유페이퍼"
    language: str = "ko"
    date: str = "2026-09-01"
    identifier: str = "urn:uuid:11111111-2222-3333-4444-555555555555"
    version: str = "2.0"
    opf_dir: str = "OEBPS"
    docs: list[Doc] | None = None
    assets: list[Asset] | None = None
    cover_image: bytes | str | None = "auto"   # "auto"=기본 표지 생성, bytes=그 이미지, None=표지 없음
    cover_in_meta: bool = True
    cover_properties: bool = False
    guide: list[tuple[str, str]] = field(default_factory=list)   # (type, href)
    css: str | None = DEFAULT_CSS
    ncx_points: list[tuple[str, str]] | None = None              # (목차명, src) — None 이면 docs 에서 생성
    ncx_depth_chain: int = 0
    include_ncx: bool = True
    ncx_in_manifest: bool = True
    spine_toc: bool = True
    spine_extra_idrefs: list[str] = field(default_factory=list)
    mimetype_first: bool = True
    mimetype_stored: bool = True
    mimetype_text: str = "application/epub+zip"
    include_container: bool = True
    opf_raw: str | None = None

    def __post_init__(self):
        if self.docs is None:
            self.docs = [cover_doc(), Doc("ch1"), colophon_doc()]
        if self.assets is None:
            self.assets = []
        if self.cover_image == "auto":
            self.cover_image = image_bytes(lines=(("테스트 도서", 60), ("홍길동 지음", 34), ("유페이퍼", 28)))

    # ---------- 조각 ----------
    def _cover_asset(self) -> Asset | None:
        if not self.cover_image:
            return None
        props = "cover-image" if self.cover_properties else ""
        return Asset("cover-img", "cover.jpg", "image/jpeg", self.cover_image, properties=props)

    def _all_assets(self) -> list[Asset]:
        assets = list(self.assets)
        cover = self._cover_asset()
        if cover and not any(a.href == cover.href for a in assets):
            assets.append(cover)
        if self.css is not None and not any(a.href == "style.css" for a in assets):
            assets.append(Asset("css", "style.css", "text/css", self.css.encode("utf-8")))
        return assets

    def _manifest(self, assets: list[Asset]) -> str:
        rows = []
        if self.include_ncx and self.ncx_in_manifest:
            rows.append('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
        for a in assets:
            if not a.in_manifest:
                continue
            props = f' properties="{a.properties}"' if a.properties else ""
            rows.append(f'<item id="{a.asset_id}" href="{a.href}" media-type="{a.media_type}"{props}/>')
        for d in self.docs:
            rows.append(f'<item id="{d.doc_id}" href="{d.href}" media-type="application/xhtml+xml"/>')
        return "\n    ".join(rows)

    def _spine(self) -> str:
        refs = [f'<itemref idref="{d.doc_id}"/>' for d in self.docs]
        refs += [f'<itemref idref="{i}"/>' for i in self.spine_extra_idrefs]
        toc = ' toc="ncx"' if (self.include_ncx and self.spine_toc) else ""
        return f"<spine{toc}>\n    " + "\n    ".join(refs) + "\n  </spine>"

    def _opf(self, assets: list[Asset]) -> str:
        if self.opf_raw is not None:
            return self.opf_raw
        meta_cover = '<meta name="cover" content="cover-img"/>' if (self.cover_image and self.cover_in_meta) else ""
        guide = ""
        if self.guide:
            rows = "".join(f'<reference type="{t}" href="{h}" title="{t}"/>' for t, h in self.guide)
            guide = f"\n  <guide>{rows}</guide>"
        fields = [f"<dc:identifier id=\"uid\">{self.identifier}</dc:identifier>" if self.identifier else "",
                  f"<dc:title>{self.title}</dc:title>" if self.title else "",
                  f"<dc:creator>{self.creator}</dc:creator>" if self.creator else "",
                  f"<dc:publisher>{self.publisher}</dc:publisher>" if self.publisher else "",
                  f"<dc:language>{self.language}</dc:language>" if self.language else "",
                  f"<dc:date>{self.date}</dc:date>" if self.date else "", meta_cover]
        version = f' version="{self.version}"' if self.version else ""
        return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<package{version} xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid">\n'
                f'  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n    '
                + "\n    ".join(f for f in fields if f)
                + f'\n  </metadata>\n  <manifest>\n    {self._manifest(assets)}\n  </manifest>\n  '
                + self._spine() + guide + "\n</package>")

    def _ncx(self) -> str:
        points = self.ncx_points
        if points is None:
            points = [(d.nav_label if d.nav_label is not None else d.title, d.href) for d in self.docs]
        nav = "\n".join(
            f'<navPoint id="n{i}" playOrder="{i + 1}"><navLabel><text>{label}</text></navLabel>'
            f'<content src="{src}"/></navPoint>' for i, (label, src) in enumerate(points))
        deep = ""
        if self.ncx_depth_chain:
            deep = "".join(f'<navPoint id="d{i}"><navLabel><text>깊이{i}</text></navLabel>'
                           f'<content src="{self.docs[0].href}"/>' for i in range(self.ncx_depth_chain))
            deep += "</navPoint>" * self.ncx_depth_chain
        return ('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
                f'  <head><meta name="dtb:uid" content="{self.identifier}"/></head>\n'
                f'  <docTitle><text>{self.title}</text></docTitle>\n  <navMap>{nav}{deep}</navMap>\n</ncx>')

    # ---------- 쓰기 ----------
    def files(self) -> dict[str, bytes]:
        assets = self._all_assets()
        prefix = f"{self.opf_dir}/" if self.opf_dir else ""
        out: dict[str, bytes] = {}
        if self.include_container:
            out["META-INF/container.xml"] = CONTAINER.format(opf=f"{prefix}content.opf").encode("utf-8")
        out[f"{prefix}content.opf"] = self._opf(assets).encode("utf-8")
        if self.include_ncx:
            out[f"{prefix}toc.ncx"] = self._ncx().encode("utf-8")
        for a in assets:
            if a.write_file:
                out[f"{prefix}{a.href}"] = a.data
        for d in self.docs:
            out[f"{prefix}{d.href}"] = d.content().encode("utf-8")
        return out

    def build(self, path: str) -> str:
        write_epub(path, self.files(), self.mimetype_first, self.mimetype_stored, self.mimetype_text)
        return path


def write_epub(path: str, files: dict[str, bytes], mimetype_first: bool = True,
               mimetype_stored: bool = True, mimetype_text: str | None = "application/epub+zip") -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    mime_kind = zipfile.ZIP_STORED if mimetype_stored else zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(path, "w") as zf:
        if mimetype_text is not None and mimetype_first:
            zf.writestr(zipfile.ZipInfo("mimetype"), mimetype_text.encode("ascii"), compress_type=mime_kind)
        for name, data in files.items():
            zf.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
        if mimetype_text is not None and not mimetype_first:
            zf.writestr(zipfile.ZipInfo("mimetype"), mimetype_text.encode("ascii"), compress_type=mime_kind)
    return path
