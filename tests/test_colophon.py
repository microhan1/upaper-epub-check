"""판권 검사 — 탐지, 5요소, 중복, ISBN, 위치. 상용본에서 오탐이 잦았던 부분이라 촘촘히 나눈다."""
from __future__ import annotations

import unittest

from builders import Asset, Book, Doc, colophon_doc, cover_doc, image_bytes
from helpers import BookTest
from upaper_check.checks.colophon import _isbn_text_valid, _title_present, is_valid_isbn
from upaper_check.findings import Level
from upaper_check.xhtml import normalize

FULL = ("<h1>판권</h1><p>테스트 도서</p><p>지은이 홍길동</p><p>발행일 2026년 9월 1일</p>"
        "<p>발행처 유페이퍼</p><p>정가 5,900원</p>")
LONG_BODY = "<p>" + "본문이 이어집니다. " * 400 + "</p>"


def book_with_colophon(body: str, **kwargs) -> Book:
    return Book(docs=[cover_doc(), Doc("ch1"), colophon_doc(body=body)], **kwargs)


class ColophonRequiredFieldsTest(BookTest):
    def test_complete_colophon_is_clean(self):
        found = self.check(book_with_colophon(FULL))
        for code in ("COLOPHON-MISSING", "COLOPHON-TITLE", "COLOPHON-AUTHOR",
                     "COLOPHON-PUBLISHER", "COLOPHON-DATE", "COLOPHON-PRICE"):
            self.assertNoCode(found, code)

    def test_each_missing_field_is_reported(self):
        cases = {
            "COLOPHON-TITLE": FULL.replace("<p>테스트 도서</p>", ""),
            "COLOPHON-AUTHOR": FULL.replace("<p>지은이 홍길동</p>", ""),
            "COLOPHON-PUBLISHER": FULL.replace("<p>발행처 유페이퍼</p>", "<p>ISBN 979-11-6811-999-4</p>"),
            "COLOPHON-DATE": FULL.replace("<p>발행일 2026년 9월 1일</p>", ""),
            "COLOPHON-PRICE": FULL.replace("<p>정가 5,900원</p>", ""),
        }
        for code, body in cases.items():
            with self.subTest(code=code):
                found = self.check(book_with_colophon(body), name=f"{code}.epub")
                self.assertCode(found, code, Level.ERROR)

    def test_publisher_name_must_match_rule(self):
        body = FULL.replace("유페이퍼", "홍길동출판")
        found = self.check(book_with_colophon(body, publisher="홍길동출판"))
        self.assertCode(found, "COLOPHON-PUBLISHER-NAME", Level.ERROR)

    def test_date_without_label_is_warning(self):
        body = "<h1>판권</h1><p>테스트 도서</p><p>지은이 홍길동</p><p>2026.9.1</p><p>펴낸곳 유페이퍼</p><p>정가 5,900원</p>"
        self.assertEqual(self.assertCode(self.check(book_with_colophon(body)), "COLOPHON-DATE").level, Level.WARN)

    def test_spaced_labels_are_recognised(self):
        """판권은 '펴 낸 날'처럼 자간을 벌려 적는 일이 잦다(v0.2.3)."""
        body = ("<p>테스트 도서</p><p>지 은 이 홍길동</p><p>펴 낸 날 2026년 9월 1일</p>"
                "<p>펴 낸 곳 유페이퍼</p><p>정 가 5,900원</p>")
        found = self.check(Book(docs=[cover_doc(), Doc("ch1"), Doc("colophon", body=body, title="간기")]))
        self.assertNoCode(found, "COLOPHON-MISSING")
        self.assertNoCode(found, "COLOPHON-DATE")
        self.assertClean(found)


class ColophonDetectionTest(BookTest):
    def test_no_colophon_at_all(self):
        book = Book(docs=[cover_doc(), Doc("ch1"), Doc("ch2")])
        self.assertCode(self.check(book), "COLOPHON-MISSING", Level.ERROR)

    def test_image_only_tail_page_is_manual_not_error(self):
        art = Asset("colophon-img", "colophon.jpg", "image/jpeg", image_bytes(700, 400))
        book = Book(assets=[art],
                    docs=[cover_doc(), Doc("ch1"),
                          Doc("colophon", body='<div><img src="colophon.jpg" alt=""/></div>', title="판권")])
        found = self.check(book)
        self.assertCode(found, "COLOPHON-IMAGE", Level.MANUAL)
        self.assertNoCode(found, "COLOPHON-MISSING")

    def test_long_chapter_with_a_date_is_not_a_colophon(self):
        """본문에 '1929년 10월 … 이메일' 이 있다고 판권으로 뽑으면 안 된다(상용본 오탐 회귀)."""
        body = "<p>1929년 10월 뉴욕 연방은행은 금리를 올렸다. 문의는 이메일로 받는다.</p>" + LONG_BODY
        book = Book(docs=[cover_doc(), Doc("ch1", body=body), colophon_doc(body=FULL)])
        found = self.check(book)
        self.assertNoCode(found, "COLOPHON-DUP")
        self.assertClean(found)

    def test_author_bio_page_is_not_a_second_colophon(self):
        """저자 소개의 '2000년 창해출판사' 를 판권 중복으로 세면 안 된다(상용본 18권 오탐 회귀)."""
        bio = ("<h1>지은이 소개</h1><p>홍길동. 2000년 창해출판사에서 첫 책을 냈고 2002년 광개토출판에서 "
               "두 번째 책을 냈다. 이메일로 독자 편지를 받는다.</p>")
        book = Book(docs=[cover_doc(), Doc("ch1"), Doc("bio", body=bio, title="지은이 소개"),
                          colophon_doc(body=FULL)])
        self.assertNoCode(self.check(book), "COLOPHON-DUP")

    def test_copyright_notice_page_is_not_a_second_colophon(self):
        notice = ("<p>이 전자책은 대한민국 저작권법의 보호를 받는 저작물입니다. 출판권자의 허락 없이 "
                  "복제할 수 없습니다. 문의는 이메일(ebook@example.com)로 받고 있습니다.</p>")
        book = Book(docs=[cover_doc(), Doc("ch1"), colophon_doc(body=FULL),
                          Doc("notice", body=notice, title="저작권")])
        self.assertNoCode(self.check(book), "COLOPHON-DUP")

    def test_two_real_colophons_are_duplicates(self):
        book = Book(docs=[cover_doc(), Doc("ch1"), colophon_doc(body=FULL), colophon_doc("colophon2", body=FULL)])
        self.assertCode(self.check(book), "COLOPHON-DUP", Level.ERROR)

    def test_colophon_near_the_front_is_info(self):
        book = Book(docs=[cover_doc(), colophon_doc(body=FULL)] + [Doc(f"ch{i}") for i in range(5)])
        self.assertEqual(self.assertCode(self.check(book), "COLOPHON-POSITION").level, Level.INFO)

    def test_colophon_at_the_end_says_nothing(self):
        book = Book(docs=[cover_doc()] + [Doc(f"ch{i}") for i in range(5)] + [colophon_doc(body=FULL)])
        self.assertNoCode(self.check(book), "COLOPHON-POSITION")


class IsbnTest(BookTest):
    def test_valid_isbn_is_accepted(self):
        body = FULL + "<p>ISBN 979-11-6811-999-4</p>"
        self.assertNoCode(self.check(book_with_colophon(body)), "COLOPHON-ISBN")

    def test_isbn_with_addendum_code(self):
        body = FULL + "<p>ISBN 978-89-349-9500-5 05300</p>"
        self.assertNoCode(self.check(book_with_colophon(body)), "COLOPHON-ISBN")

    def test_wrong_check_digit(self):
        body = FULL + "<p>ISBN 978-0-00-000000-1</p>"
        self.assertCode(self.check(book_with_colophon(body)), "COLOPHON-ISBN", Level.ERROR)

    def test_no_isbn_is_info_only(self):
        found = self.check(book_with_colophon(FULL))
        self.assertEqual(self.assertCode(found, "COLOPHON-ISBN").level, Level.INFO)
        self.assertClean(found)

    def test_ecn_instead_of_isbn(self):
        body = FULL + "<p>ECN 발급 예정</p>"
        self.assertNoCode(self.check(book_with_colophon(body)), "COLOPHON-ISBN")

    def test_check_digit_algorithm(self):
        self.assertTrue(is_valid_isbn("9791168119994"))
        self.assertTrue(is_valid_isbn("0306406152"))
        self.assertTrue(is_valid_isbn("043942089X"))
        self.assertFalse(is_valid_isbn("9780000000001"))
        self.assertFalse(is_valid_isbn("123"))

    def test_text_forms(self):
        self.assertTrue(_isbn_text_valid("978-89-349-9500-5 05300"))
        self.assertTrue(_isbn_text_valid("979 - 11 -5581-257-0 )"))
        self.assertFalse(_isbn_text_valid("978-0-00-000000-1"))


class TitleMatchTest(unittest.TestCase):
    """판권의 도서명 대조는 부제·시리즈명·권 표기 때문에 느슨해야 한다."""

    def test_matches(self):
        for title, text in (("김팔봉 수호지 10", "수호지 10 적막강산 편 전자책 발행 2021년"),
                            ("글쓰기 쉽게 하기(How to write easily", "글쓰기 쉽게 하기 ⓒ 송숙희"),
                            ("첫단추 시리즈 006 제1차세계대전", "제1차세계대전 초판 발행"),
                            ("채근담 : 에버그린 문고 46", "채근담 엮은이 박건삼")):
            with self.subTest(title=title):
                self.assertTrue(_title_present(title, normalize(text)))

    def test_does_not_match_unrelated_text(self):
        self.assertFalse(_title_present("성공하는 남자의 디테일 1", normalize("발행 2012년 2월 1일 저자 김소진")))


if __name__ == "__main__":
    unittest.main()
