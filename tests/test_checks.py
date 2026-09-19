"""검수 규칙 테스트 — good.epub 은 오류 0, bad.epub 은 각 규칙이 정확히 잡히는지 확인.

python -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import make_fixtures  # noqa: E402
from upaper_check.checks import run_all  # noqa: E402
from upaper_check.checks.colophon import is_valid_isbn  # noqa: E402
from upaper_check.cli import check_file_for_gui, main  # noqa: E402
from upaper_check.context import Context, load_rules  # noqa: E402
from upaper_check.epub import EpubPackage  # noqa: E402
from upaper_check.findings import Level  # noqa: E402


def run(path: str, **rule_overrides):
    rules = load_rules()
    rules.update(rule_overrides)
    return run_all(Context(EpubPackage(path), rules))


def codes(findings, level=None):
    return {f.code for f in findings if level is None or f.level == level}


class FixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.good = os.path.join(cls.tmp.name, "good.epub")
        cls.bad = os.path.join(cls.tmp.name, "bad.epub")
        cls.spaced = os.path.join(cls.tmp.name, "spaced.epub")
        make_fixtures.good_epub(cls.good)
        make_fixtures.bad_epub(cls.bad)
        make_fixtures.spaced_colophon_epub(cls.spaced)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()


class GoodEpubTest(FixtureTest):
    def test_no_errors(self):
        findings = run(self.good)
        errors = [f for f in findings if f.level == Level.ERROR]
        self.assertEqual(errors, [], [f"{f.code}: {f.message}" for f in errors])

    def test_manual_cover_check_always_present(self):
        self.assertIn("COVER-TEXT", codes(run(self.good), Level.MANUAL))

    def test_publisher_mismatch_when_expected_changes(self):
        found = codes(run(self.good, publisher_expected="다른출판사"), Level.ERROR)
        self.assertIn("META-PUBLISHER-NAME", found)
        self.assertIn("COLOPHON-PUBLISHER-NAME", found)

    def test_cli_exit_code_zero(self):
        self.assertEqual(main([self.good, "--quiet"]), 0)

    def test_gui_check_writes_report_next_to_epub(self):
        summary, report_path, passed = check_file_for_gui(self.good)
        self.assertTrue(passed)
        self.assertIn("통과", summary)
        self.assertTrue(os.path.isfile(report_path))
        self.assertTrue(report_path.endswith("good_검수보고서.html"))


class BadEpubTest(FixtureTest):
    def setUp(self):
        self.findings = run(self.bad)
        self.errors = codes(self.findings, Level.ERROR)
        self.warns = codes(self.findings, Level.WARN)

    def test_epub3_rejected(self):
        self.assertIn("STRUCT-VERSION", self.errors)

    def test_publisher_name(self):
        self.assertIn("META-PUBLISHER-NAME", self.errors)
        self.assertIn("COLOPHON-PUBLISHER-NAME", self.errors)

    def test_cover_rules(self):
        self.assertIn("COVER-FIRST", self.errors)
        self.assertIn("COVER-DUP", self.errors)
        self.assertIn("COVER-CMYK", self.errors)
        self.assertIn("COVER-SIZE", self.warns)

    def test_colophon_rules(self):
        self.assertIn("COLOPHON-DUP", self.errors)
        self.assertIn("COLOPHON-TITLE", self.errors)
        self.assertIn("COLOPHON-DATE", self.errors)
        self.assertIn("COLOPHON-PRICE", self.errors)
        self.assertIn("COLOPHON-ISBN", self.errors)

    def test_toc_rules(self):
        self.assertIn("TOC-LABEL", self.errors)
        self.assertIn("TOC-TARGET", self.errors)
        self.assertIn("TOC-EMPTY-DOC", self.errors)
        self.assertIn("TOC-DEPTH", self.warns)

    def test_markup_rules(self):
        self.assertIn("TAG-FORBIDDEN", self.errors)
        self.assertIn("ATTR-EVENT", self.errors)
        self.assertIn("ATTR-JAVASCRIPT", self.errors)
        self.assertIn("STYLE-BLACK", self.errors)
        self.assertIn("DOC-XML", self.errors)
        self.assertIn("STYLE-FONT-SIZE", self.warns)
        self.assertIn("TAG-DISCOURAGED", self.warns)
        self.assertIn("DOC-LANG", self.warns)

    def test_image_rules(self):
        self.assertIn("IMG-MISSING", self.errors)
        self.assertIn("IMG-CMYK", self.errors)
        self.assertIn("IMG-UNUSED", self.warns)
        self.assertIn("FONT-UNUSED", self.warns)

    def test_background_black_not_flagged_as_text_color(self):
        black = [f for f in self.findings if f.code == "STYLE-BLACK" and f.location.endswith("style.css")]
        self.assertEqual(len(black), 1)
        self.assertIn("1곳", black[0].message)

    def test_cli_exit_code_one(self):
        self.assertEqual(main([self.bad, "--quiet"]), 1)


class SpacedColophonTest(FixtureTest):
    """'펴 낸 날'처럼 자간을 벌린 판권도 찾아내야 한다 (v0.2.3 회귀)."""

    def setUp(self):
        self.findings = run(self.spaced)

    def test_colophon_is_detected(self):
        found = codes(self.findings)
        self.assertNotIn("COLOPHON-MISSING", found)
        self.assertNotIn("COLOPHON-IMAGE", found)

    def test_no_date_finding(self):
        dates = [f"{f.level.name} {f.message}" for f in self.findings if f.code == "COLOPHON-DATE"]
        self.assertEqual(dates, [])

    def test_no_errors(self):
        errors = [f for f in self.findings if f.level == Level.ERROR]
        self.assertEqual(errors, [], [f"{f.code}: {f.message}" for f in errors])


class DateLabelTest(unittest.TestCase):
    """날짜 표기 정규식 — 자간을 벌린 '펴 낸 날'까지 잡되, 본문 낱말은 잡지 않아야 한다."""

    def test_spaced_date_labels_match(self):
        from upaper_check.checks.colophon import DATE_LABEL, STRICT_DATE_LABEL
        for text in ("펴낸날 2026년 9월 1일", "펴낸 날 2026년 9월 1일", "펴 낸 날 2026년 9월 1일",
                     "펴 낸 날 짜 2026.9.1", "발 행 년 월 일 2026. 9. 1.", "출 간 일 2026-09-01"):
            self.assertTrue(DATE_LABEL.search(text), text)
            self.assertTrue(STRICT_DATE_LABEL.search(text), text)

    def test_spaced_date_label_alone_is_hard_datum(self):
        """정가·ISBN·연락처가 없어도 '펴 낸 날 + 날짜'만으로 판권 후보가 되어야 한다."""
        from upaper_check.checks.colophon import _has_hard_datum
        self.assertTrue(_has_hard_datum("펴 낸 날 2026년 9월 1일"))
        self.assertFalse(_has_hard_datum("펴 낸 날"))

    def test_body_words_not_taken_as_date_label(self):
        from upaper_check.checks.colophon import DATE_LABEL
        for text in ("최초 판단은 옳았다", "그는 발을 헛디뎠다", "출장 간 일이 있었다"):
            self.assertIsNone(DATE_LABEL.search(text), text)


class TitleMatchTest(unittest.TestCase):
    def test_partial_and_subtitle_titles_match(self):
        from upaper_check.checks.colophon import _title_present
        from upaper_check.xhtml import normalize
        self.assertTrue(_title_present("김팔봉 수호지 10", normalize("수호지 10 적막강산 편 전자책 발행 2021년")))
        self.assertTrue(_title_present("글쓰기 쉽게 하기(How to write easily", normalize("글쓰기 쉽게 하기 ⓒ 송숙희")))
        self.assertTrue(_title_present("첫단추 시리즈 006 제1차세계대전", normalize("제1차세계대전 초판 발행")))
        self.assertFalse(_title_present("성공하는 남자의 디테일 1", normalize("발행 2012년 2월 1일 저자 김소진")))


class IsbnTest(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(is_valid_isbn("9791168119994"))
        self.assertTrue(is_valid_isbn("0306406152"))

    def test_text_with_addendum_code_and_spaces(self):
        from upaper_check.checks.colophon import _isbn_text_valid
        self.assertTrue(_isbn_text_valid("978-89-349-9500-5 05300"))   # 부가기호 뒤에 붙은 실제 판권 표기
        self.assertTrue(_isbn_text_valid("979 - 11 -5581-257-0 )"))    # 공백 섞인 표기
        self.assertFalse(_isbn_text_valid("978-0-00-000000-1"))

    def test_invalid(self):
        self.assertFalse(is_valid_isbn("9780000000001"))
        self.assertFalse(is_valid_isbn("123"))


if __name__ == "__main__":
    unittest.main()
