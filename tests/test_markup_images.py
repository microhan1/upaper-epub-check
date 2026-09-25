"""본문 마크업·스타일·이미지·폰트 검사."""
from __future__ import annotations

import unittest

from builders import Asset, Book, Doc, colophon_doc, cover_doc, image_bytes
from helpers import BookTest
from upaper_check.findings import Level

TTF = b"\x00\x01\x00\x00" + b"\x00" * 100


def with_chapter(body: str, **kwargs) -> Book:
    return Book(docs=[cover_doc(), Doc("ch1", body=body), colophon_doc()], **kwargs)


class ForbiddenMarkupTest(BookTest):
    def test_clean_chapter_has_no_markup_findings(self):
        found = self.check()
        for code in ("TAG-FORBIDDEN", "ATTR-EVENT", "ATTR-JAVASCRIPT", "DOC-XML", "DOC-LANG"):
            self.assertNoCode(found, code)

    def test_each_forbidden_tag(self):
        for tag, markup in (("script", "<script>alert(1)</script>"),
                            ("iframe", '<iframe src="x"></iframe>'),
                            ("form", '<form action="x"><input/></form>'),
                            ("video", '<video src="v.mp4"></video>'),
                            ("audio", '<audio src="a.mp3"></audio>'),
                            ("object", '<object data="x"></object>')):
            with self.subTest(tag=tag):
                found = self.check(with_chapter(f"<p>본문</p>{markup}"), name=f"{tag}.epub")
                message = self.assertCode(found, "TAG-FORBIDDEN", Level.ERROR).message
                self.assertIn(tag, message)

    def test_event_attribute_and_javascript_link(self):
        found = self.check(with_chapter('<p onclick="x()">본문</p><a href="javascript:void(0)">링크</a>'))
        self.assertCode(found, "ATTR-EVENT", Level.ERROR)
        self.assertCode(found, "ATTR-JAVASCRIPT", Level.ERROR)

    def test_discouraged_tags_are_one_finding_per_tag(self):
        """ul/li/table 은 파일마다가 아니라 태그마다 한 건으로 묶어 보고한다."""
        body = "<ul><li>하나</li><li>둘</li></ul><table><tr><td>표</td></tr></table>"
        book = Book(docs=[cover_doc(), Doc("ch1", body=body), Doc("ch2", body=body), colophon_doc()])
        found = self.check(book)
        li = [f for f in found if f.code == "TAG-DISCOURAGED" and "<li>" in f.message]
        self.assertEqual(len(li), 1, [f.message for f in found if f.code == "TAG-DISCOURAGED"])
        self.assertIn("2개 파일", li[0].message)
        self.assertEqual(li[0].level, Level.WARN)

    def test_html5_tags_are_epub2_warnings(self):
        found = self.check(with_chapter('<section><p>본문</p></section><svg width="10"></svg>'))
        self.assertCode(found, "TAG-EPUB2", Level.WARN)

    def test_malformed_xhtml(self):
        book = Book(docs=[cover_doc(), Doc("ch1", raw="<html><body><p>닫지 않음<b></body></html>"), colophon_doc()])
        self.assertCode(self.check(book), "DOC-XML", Level.ERROR)

    def test_missing_language_attribute(self):
        self.assertCode(self.check(with_chapter("<p>본문</p>", docs=None) if False else
                                   Book(docs=[cover_doc(), Doc("ch1", lang=""), colophon_doc()])),
                        "DOC-LANG", Level.WARN)


class StyleTest(BookTest):
    def test_black_text_colour_in_css(self):
        self.assertCode(self.check(Book(css="p { color: #000000; }")), "STYLE-BLACK", Level.ERROR)

    def test_black_text_colour_inline_and_font_tag(self):
        found = self.check(with_chapter('<p style="color:black">본문</p><font color="#000000">검정</font>'))
        self.assertEqual(len([f for f in found if f.code == "STYLE-BLACK"]), 2)

    def test_black_background_is_not_a_text_colour(self):
        """background-color:#000 을 글자색으로 잡으면 안 된다(회귀)."""
        self.assertNoCode(self.check(Book(css="body { background-color: #000; }")), "STYLE-BLACK")

    def test_fixed_font_size_is_warning(self):
        for css in ("p { font-size: 12pt; }", "p { font-size: 16px; }"):
            with self.subTest(css=css):
                self.assertCode(self.check(Book(css=css), name="f.epub"), "STYLE-FONT-SIZE", Level.WARN)

    def test_relative_font_size_is_fine(self):
        self.assertNoCode(self.check(Book(css="p { font-size: 1.1em; }")), "STYLE-FONT-SIZE")

    def test_remote_stylesheet_is_not_missing(self):
        book = Book(docs=[cover_doc(), Doc("ch1", css="https://example.com/book.css"), colophon_doc()])
        self.assertNoCode(self.check(book), "CSS-MISSING")

    def test_missing_stylesheet_link(self):
        book = Book(css=None, docs=[cover_doc(), Doc("ch1", css="style.css"), colophon_doc()])
        self.assertCode(self.check(book), "CSS-MISSING", Level.ERROR)


class ImageAndFontTest(BookTest):
    def test_missing_image_reference(self):
        found = self.check(with_chapter('<p>본문</p><img src="gone.jpg" alt=""/>'))
        self.assertCode(found, "IMG-MISSING", Level.ERROR)

    def test_image_not_registered_in_manifest(self):
        art = Asset("art", "art.jpg", "image/jpeg", image_bytes(200, 200), in_manifest=False)
        book = Book(assets=[art], docs=[cover_doc(), Doc("ch1", body='<p>본문</p><img src="art.jpg" alt=""/>'),
                                        colophon_doc()])
        self.assertCode(self.check(book), "IMG-MANIFEST", Level.ERROR)

    def test_cmyk_body_image(self):
        art = Asset("art", "art.jpg", "image/jpeg", image_bytes(200, 200, mode="CMYK"))
        book = Book(assets=[art], docs=[cover_doc(), Doc("ch1", body='<p>본문</p><img src="art.jpg" alt=""/>'),
                                        colophon_doc()])
        self.assertCode(self.check(book), "IMG-CMYK", Level.ERROR)

    def test_unused_image_is_warning(self):
        art = Asset("art", "art.jpg", "image/jpeg", image_bytes(200, 200))
        self.assertCode(self.check(Book(assets=[art])), "IMG-UNUSED", Level.WARN)

    def test_font_used_by_css_is_not_flagged(self):
        font = Asset("font", "fonts/book.ttf", "application/x-font-ttf", TTF)
        css = "@font-face { font-family: book; src: url('fonts/book.ttf'); }"
        self.assertNoCode(self.check(Book(assets=[font], css=css)), "FONT-UNUSED")

    def test_unused_font_is_warning(self):
        font = Asset("font", "fonts/book.ttf", "application/x-font-ttf", TTF)
        self.assertCode(self.check(Book(assets=[font])), "FONT-UNUSED", Level.WARN)

    def test_css_pointing_at_missing_font(self):
        css = "@font-face { font-family: book; src: url('fonts/gone.ttf'); }"
        found = self.check(Book(css=css))
        self.assertCode(found, "CSS-RES-MISSING", Level.ERROR)
        self.assertNoCode(found, "IMG-MISSING")

    def test_remote_and_data_uris_are_ignored(self):
        body = ('<p>본문</p><img src="https://example.com/a.jpg" alt=""/>'
                '<img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" alt=""/>')
        self.assertNoCode(self.check(with_chapter(body)), "IMG-MISSING")


class TocTest(BookTest):
    def test_empty_navigation_label(self):
        book = Book(docs=[cover_doc(), Doc("ch1", nav_label=""), colophon_doc()])
        self.assertCode(self.check(book), "TOC-LABEL", Level.ERROR)

    def test_navigation_target_missing(self):
        book = Book(ncx_points=[("표지", "cover.xhtml"), ("없는 장", "nope.xhtml")])
        self.assertCode(self.check(book), "TOC-TARGET", Level.ERROR)

    def test_document_without_text_or_image(self):
        book = Book(docs=[cover_doc(), Doc("empty", body="<div></div>"), colophon_doc()])
        self.assertCode(self.check(book), "TOC-EMPTY-DOC", Level.ERROR)

    def test_depth_over_three_is_warning(self):
        self.assertCode(self.check(Book(ncx_depth_chain=4)), "TOC-DEPTH", Level.WARN)

    def test_depth_three_is_fine(self):
        self.assertNoCode(self.check(Book(ncx_depth_chain=2)), "TOC-DEPTH")


if __name__ == "__main__":
    unittest.main()
