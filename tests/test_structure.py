"""구조·크기·메타데이터 검사 — ZIP/OPF/NCX/spine 과 dc: 항목."""
from __future__ import annotations

import os
import unittest

from builders import Asset, Book, Doc, colophon_doc, cover_doc, image_bytes, write_epub
from helpers import REGRESSION_EPUB, BookTest, check_path, codes
from upaper_check.epub import EpubLoadError, EpubPackage
from upaper_check.findings import Level

KB = 1024


class MimetypeTest(BookTest):
    def test_correct_book_has_no_mimetype_finding(self):
        self.assertNoCode(self.check(), "STRUCT-MIMETYPE")

    def test_missing(self):
        path = write_epub(self.path(), Book().files(), mimetype_text=None)
        self.assertIn("없습니다", self.assertCode(check_path(path), "STRUCT-MIMETYPE", Level.ERROR).message)

    def test_not_first_entry(self):
        path = Book(mimetype_first=False).build(self.path())
        self.assertIn("첫 번째", self.assertCode(check_path(path), "STRUCT-MIMETYPE", Level.ERROR).message)

    def test_compressed(self):
        path = Book(mimetype_stored=False).build(self.path())
        self.assertIn("압축", self.assertCode(check_path(path), "STRUCT-MIMETYPE", Level.ERROR).message)

    def test_wrong_content(self):
        path = Book(mimetype_text="application/zip").build(self.path())
        self.assertIn("내용", self.assertCode(check_path(path), "STRUCT-MIMETYPE", Level.ERROR).message)


class LoadErrorTest(BookTest):
    """열 수 없는 파일은 검사 이전에 EpubLoadError 로 끊어야 한다(CLI 종료 코드 2)."""

    def test_not_a_zip(self):
        path = self.path("broken.epub")
        with open(path, "wb") as fh:
            fh.write(b"not a zip at all")
        with self.assertRaises(EpubLoadError):
            EpubPackage(path)

    def test_container_missing(self):
        path = Book(include_container=False).build(self.path())
        with self.assertRaises(EpubLoadError):
            EpubPackage(path)

    def test_container_points_at_missing_opf(self):
        files = Book().files()
        files["META-INF/container.xml"] = files["META-INF/container.xml"].replace(b"content.opf", b"gone.opf")
        with self.assertRaises(EpubLoadError):
            EpubPackage(write_epub(self.path(), files))

    def test_opf_unparsable(self):
        files = Book().files()
        files["OEBPS/content.opf"] = b"\x00\x01\x02 not xml"
        with self.assertRaises(EpubLoadError):
            EpubPackage(write_epub(self.path(), files))


class VersionTest(BookTest):
    def test_epub2_is_info(self):
        self.assertEqual(self.assertCode(self.check(), "STRUCT-VERSION").level, Level.INFO)

    def test_epub201_is_info(self):
        self.assertEqual(self.assertCode(self.check(Book(version="2.0.1")), "STRUCT-VERSION").level, Level.INFO)

    def test_epub3_is_error(self):
        finding = self.assertCode(self.check(Book(version="3.0")), "STRUCT-VERSION", Level.ERROR)
        self.assertIn("EPUB 2", finding.hint + finding.message)

    def test_missing_version_attribute(self):
        self.assertCode(self.check(Book(version="")), "STRUCT-VERSION", Level.ERROR)


class NcxAndSpineTest(BookTest):
    def test_ncx_not_in_manifest(self):
        self.assertCode(self.check(Book(ncx_in_manifest=False)), "STRUCT-NCX", Level.ERROR)

    def test_ncx_file_missing(self):
        book = Book()
        files = book.files()
        del files["OEBPS/toc.ncx"]
        self.assertCode(check_path(write_epub(self.path(), files)), "STRUCT-NCX", Level.ERROR)

    def test_spine_without_toc_attribute_is_warning(self):
        self.assertCode(self.check(Book(spine_toc=False)), "STRUCT-NCX", Level.WARN)

    def test_spine_idref_not_in_manifest(self):
        found = self.check(Book(spine_extra_idrefs=["ghost"]))
        self.assertIn("ghost", self.assertCode(found, "STRUCT-SPINE", Level.ERROR).message)

    def test_manifest_item_without_file(self):
        book = Book(assets=[Asset("ghost-img", "ghost.jpg", "image/jpeg", b"", write_file=False)])
        self.assertCode(self.check(book), "STRUCT-MANIFEST", Level.ERROR)

    def test_empty_spine(self):
        book = Book()
        files = book.files()
        opf = files["OEBPS/content.opf"].decode()
        start, end = opf.index("<spine"), opf.index("</spine>") + len("</spine>")
        files["OEBPS/content.opf"] = (opf[:start] + '<spine toc="ncx"></spine>' + opf[end:]).encode()
        self.assertCode(check_path(write_epub(self.path(), files)), "STRUCT-SPINE", Level.ERROR)


class SizeLimitTest(BookTest):
    def test_html_over_limit(self):
        big = Doc("ch1", body="<p>" + "가" * 5000 + "</p>")
        found = self.check(Book(docs=[cover_doc(), big, colophon_doc()]), limits={"max_html_bytes": 2 * KB})
        self.assertCode(found, "SIZE-HTML", Level.ERROR)

    def test_html_under_limit_is_clean(self):
        self.assertNoCode(self.check(limits={"max_html_bytes": 100 * KB}), "SIZE-HTML")

    def test_too_many_documents(self):
        docs = [cover_doc()] + [Doc(f"ch{i}") for i in range(4)] + [colophon_doc()]
        self.assertCode(self.check(Book(docs=docs), limits={"max_spine_docs": 3}), "TOC-COUNT", Level.ERROR)

    def test_epub_file_over_limit(self):
        self.assertCode(self.check(limits={"max_epub_bytes": 1000}), "SIZE-EPUB", Level.ERROR)


class MetadataTest(BookTest):
    def test_complete_metadata_is_clean(self):
        found = self.check()
        for code in ("META-TITLE", "META-CREATOR", "META-LANGUAGE", "META-PUBLISHER", "META-IDENTIFIER"):
            self.assertNoCode(found, code)

    def test_missing_title_author_language(self):
        found = self.check(Book(title="", creator="", language=""))
        for code in ("META-TITLE", "META-CREATOR", "META-LANGUAGE"):
            self.assertCode(found, code, Level.ERROR)

    def test_missing_identifier_is_warning(self):
        self.assertCode(self.check(Book(identifier="")), "META-IDENTIFIER", Level.WARN)

    def test_missing_date_is_info(self):
        self.assertCode(self.check(Book(date="")), "META-DATE", Level.INFO)

    def test_non_korean_language_is_info(self):
        self.assertCode(self.check(Book(language="en")), "META-LANGUAGE", Level.INFO)

    def test_publisher_missing_and_mismatched(self):
        self.assertCode(self.check(Book(publisher="")), "META-PUBLISHER", Level.ERROR)
        self.assertCode(self.check(Book(publisher="홍길동출판")), "META-PUBLISHER-NAME", Level.ERROR)

    def test_publisher_rule_can_be_overridden(self):
        book = Book(publisher="내출판사", docs=[cover_doc(), Doc("ch1"),
                                            colophon_doc(body="<h1>판권</h1><p>테스트 도서</p><p>지은이 홍길동</p>"
                                                              "<p>발행일 2026년 9월 1일</p><p>발행처 내출판사</p>"
                                                              "<p>정가 5,900원</p>")])
        self.assertNoCode(self.check(book, publisher_expected="내출판사"), "META-PUBLISHER-NAME")
        self.assertNoCode(self.check(book, name="any.epub", publisher_expected=""), "META-PUBLISHER-NAME")


class PathResolutionTest(BookTest):
    """OPF 위치·퍼센트 인코딩 경로에서도 파일을 찾아야 한다."""

    def test_opf_at_zip_root(self):
        self.assertClean(self.check(Book(opf_dir="")))

    def test_opf_in_nested_folder(self):
        self.assertClean(self.check(Book(opf_dir="EPUB/pkg")))

    def test_percent_encoded_href(self):
        cover = Asset("cover-img", "images/cover%20art.jpg", "image/jpeg", image_bytes())
        book = Book(cover_image=None, assets=[cover],
                    docs=[Doc("cover", body='<div><img src="images/cover%20art.jpg" alt="표지"/></div>', title="표지"),
                          Doc("ch1"), colophon_doc()])
        files = book.files()
        files["OEBPS/images/cover art.jpg"] = files.pop("OEBPS/images/cover%20art.jpg")
        found = check_path(write_epub(self.path(), files))
        self.assertNoCode(found, "IMG-MISSING")
        self.assertNoCode(found, "STRUCT-MANIFEST")


class RegressionBookTest(unittest.TestCase):
    """유페이퍼 승인본은 언제나 오류 0 이어야 한다."""

    @unittest.skipUnless(os.path.isfile(REGRESSION_EPUB), "승인본이 이 PC 에 없음")
    def test_approved_book_has_no_errors(self):
        self.assertEqual(codes(check_path(REGRESSION_EPUB), Level.ERROR), set())


if __name__ == "__main__":
    unittest.main()
