"""표지 검사 — 탐지 경로, 첫 장 배치, 중복, 규격."""
from __future__ import annotations

import unittest

from builders import Asset, Book, Doc, colophon_doc, cover_doc, image_bytes
from helpers import BookTest
from upaper_check.checks.cover import find_cover_image
from upaper_check.context import Context, load_rules
from upaper_check.epub import EpubPackage
from upaper_check.findings import Level


def cover_of(path: str) -> str:
    ctx = Context(EpubPackage(path), load_rules())
    item = find_cover_image(ctx)
    return item.href if item else ""


class CoverDetectionTest(BookTest):
    """표지를 찾는 경로는 다섯 가지다. 하나씩 끊어 확인한다."""

    def test_meta_name_cover(self):
        self.assertEqual(cover_of(self.build()), "cover.jpg")

    def test_properties_cover_image(self):
        path = self.build(Book(cover_in_meta=False, cover_properties=True))
        self.assertEqual(cover_of(path), "cover.jpg")

    def test_guide_reference(self):
        path = self.build(Book(cover_in_meta=False, guide=[("cover", "cover.xhtml")]))
        self.assertEqual(cover_of(path), "cover.jpg")

    def test_first_document_with_single_image(self):
        art = Asset("art", "front.jpg", "image/jpeg", image_bytes())
        book = Book(cover_image=None, assets=[art],
                    docs=[cover_doc(href="front.jpg"), Doc("ch1"), colophon_doc()])
        self.assertEqual(cover_of(self.build(book)), "front.jpg")

    def test_filename_containing_cover(self):
        art = Asset("art", "the-cover-art.jpg", "image/jpeg", image_bytes())
        book = Book(cover_image=None, assets=[art],
                    docs=[Doc("ch1"), Doc("ch2"), colophon_doc()])
        self.assertEqual(cover_of(self.build(book)), "the-cover-art.jpg")

    def test_no_cover_at_all(self):
        book = Book(cover_image=None, docs=[Doc("ch1"), colophon_doc()])
        found = self.check(book)
        self.assertCode(found, "COVER-MISSING", Level.ERROR)


class CoverPlacementTest(BookTest):
    def test_correct_book_is_clean(self):
        found = self.check()
        for code in ("COVER-FIRST", "COVER-DUP", "COVER-MISSING"):
            self.assertNoCode(found, code)

    def test_first_document_is_not_cover(self):
        book = Book(docs=[Doc("ch1"), cover_doc(), colophon_doc()])
        self.assertCode(self.check(book), "COVER-FIRST", Level.ERROR)

    def test_first_document_is_a_different_cover_image_is_info(self):
        """첫 장이 이미지 한 장짜리 표지인데 OPF 표지와 다른 파일이면 오류가 아니라 정보(v0.2.2)."""
        other = Asset("other", "front.jpg", "image/jpeg", image_bytes())
        book = Book(assets=[other], docs=[cover_doc(href="front.jpg"), Doc("ch1"), colophon_doc()])
        self.assertEqual(self.assertCode(self.check(book), "COVER-FIRST").level, Level.INFO)

    def test_page_whose_only_image_is_missing_is_not_a_cover(self):
        """깨진 그림 한 장짜리 첫 장을 표지로 쳐 주면 반려 사유가 정보로 약해진다."""
        book = Book(docs=[Doc("ch1", body='<p>본문</p><img src="gone.jpg" alt=""/>'), cover_doc(), colophon_doc()])
        self.assertEqual(self.assertCode(self.check(book), "COVER-FIRST").level, Level.ERROR)

    def test_same_cover_image_in_two_documents(self):
        book = Book(docs=[cover_doc(), cover_doc("cover2"), Doc("ch1"), colophon_doc()])
        self.assertCode(self.check(book), "COVER-DUP", Level.ERROR)

    def test_title_page_after_cover_is_not_duplicate(self):
        """속표지·로고 페이지를 표지 중복으로 잡으면 안 된다(상용본 107권 오탐 회귀)."""
        logo = Asset("logo", "logo.jpg", "image/jpeg", image_bytes(300, 300))
        book = Book(assets=[logo],
                    docs=[cover_doc(), Doc("title", body='<div><img src="logo.jpg" alt=""/></div>', title="속표지"),
                          Doc("ch1"), colophon_doc()])
        self.assertNoCode(self.check(book), "COVER-DUP")


class CoverSpecTest(BookTest):
    def test_recommended_size_says_nothing(self):
        """700x1000 은 권장 크기라 알릴 것이 없다."""
        self.assertNoCode(self.check(), "COVER-SIZE")

    def test_in_range_but_not_recommended_is_info(self):
        book = Book(cover_image=image_bytes(625, 1000))
        self.assertEqual(self.assertCode(self.check(book), "COVER-SIZE").level, Level.INFO)

    def test_width_bounds(self):
        for width, level in ((600, Level.INFO), (1000, Level.INFO), (599, Level.WARN), (1001, Level.WARN)):
            with self.subTest(width=width):
                book = Book(cover_image=image_bytes(width, 1000))
                found = self.check(book, name=f"w{width}.epub")
                self.assertEqual(self.assertCode(found, "COVER-SIZE").level, level)

    def test_cmyk_cover(self):
        self.assertCode(self.check(Book(cover_image=image_bytes(mode="CMYK"))), "COVER-CMYK", Level.ERROR)

    def test_png_cover_is_info_only(self):
        png = Asset("cover-img", "cover.png", "image/png", image_bytes(fmt="PNG"))
        book = Book(cover_image=None, assets=[png], cover_in_meta=False, cover_properties=False,
                    docs=[cover_doc(href="cover.png"), Doc("ch1"), colophon_doc()])
        found = self.check(book)
        self.assertEqual(self.assertCode(found, "COVER-FORMAT").level, Level.INFO)
        self.assertClean(found)

    def test_unreadable_cover(self):
        broken = Asset("cover-img", "cover.jpg", "image/jpeg", b"not an image")
        book = Book(cover_image=None, assets=[broken],
                    docs=[cover_doc(), Doc("ch1"), colophon_doc()])
        self.assertCode(self.check(book), "COVER-UNREADABLE", Level.ERROR)

    def test_cover_text_is_always_manual(self):
        """표지 그림 속 글자는 프로그램이 못 읽으니 항상 사람이 볼 항목으로 남는다."""
        self.assertCode(self.check(), "COVER-TEXT", Level.MANUAL)


if __name__ == "__main__":
    unittest.main()
