"""보고서 출력(콘솔·JSON·HTML), 명령줄, epubcheck 연동, 창 기동."""
from __future__ import annotations

import contextlib
import io
import json
import os
import unittest

from builders import Book, Doc, colophon_doc, cover_doc
from helpers import BookTest
from upaper_check import epubcheck
from upaper_check.cli import check_file_for_gui, main  # noqa: F401
from upaper_check.findings import Finding, Level, count_by_level, sort_findings
from upaper_check.report import Report

BAD_BOOK = Book(version="3.0", publisher="홍길동출판")


class ReportTest(BookTest):
    def make_report(self, book: Book | None = None) -> Report:
        from upaper_check.checks import run_all
        from upaper_check.cli import _cover_preview, _meta_summary
        from upaper_check.context import Context, load_rules
        from upaper_check.epub import EpubPackage
        ctx = Context(EpubPackage(self.build(book)), load_rules())
        return Report(ctx.pkg.path, run_all(ctx), _meta_summary(ctx), *_cover_preview(ctx))

    def test_console_has_verdict_and_checklist(self):
        text = self.make_report().to_console()
        self.assertIn("통과 (오류 없음)", text)
        self.assertIn("판매신청 전 마지막 확인", text)
        self.assertIn("도서소개·저자소개는 4000bytes", text)

    def test_json_structure(self):
        data = json.loads(self.make_report(BAD_BOOK).to_json())
        self.assertFalse(data["passed"])
        self.assertEqual(data["counts"]["오류"], sum(1 for f in data["findings"] if f["level"] == "오류"))
        self.assertIn("도서명", data["metadata"])
        for key in ("code", "level", "message", "location", "hint"):
            self.assertIn(key, data["findings"][0])

    def test_html_embeds_cover_and_verdict(self):
        html = self.make_report().to_html()
        self.assertIn('class="verdict pass"', html)
        self.assertIn("data:image/jpeg;base64,", html)   # 표지를 보고서에 실어 눈으로 확인하게 한다
        self.assertIn("유페이퍼 EPUB 검수 보고서", html)

    def test_html_marks_failure(self):
        self.assertIn('class="verdict fail"', self.make_report(BAD_BOOK).to_html())

    def test_html_escapes_markup_in_messages(self):
        book = Book(title="<script>alert(1)</script>")
        self.assertNotIn("<script>alert(1)</script>", self.make_report(book).to_html())

    def test_findings_are_sorted_by_severity(self):
        findings = [Finding("B", Level.INFO, "정보"), Finding("A", Level.ERROR, "오류"),
                    Finding("C", Level.WARN, "경고"), Finding("D", Level.MANUAL, "확인")]
        self.assertEqual([f.level for f in sort_findings(findings)],
                         [Level.ERROR, Level.WARN, Level.MANUAL, Level.INFO])
        self.assertEqual(count_by_level(findings)[Level.ERROR], 1)


def run_cli(*argv: str) -> int:
    """명령줄을 돌리고 종료 코드만 돌려준다(테스트 출력이 콘솔을 덮지 않게)."""
    with contextlib.redirect_stdout(io.StringIO()):
        return main(list(argv))


class CommandLineTest(BookTest):
    def test_exit_code_zero_for_clean_book(self):
        self.assertEqual(run_cli(self.build(), "--quiet", "--no-epubcheck"), 0)

    def test_exit_code_one_for_book_with_errors(self):
        self.assertEqual(run_cli(self.build(BAD_BOOK), "--quiet", "--no-epubcheck"), 1)

    def test_exit_code_two_for_unreadable_file(self):
        path = self.path("broken.epub")
        with open(path, "wb") as fh:
            fh.write(b"not a zip")
        self.assertEqual(run_cli(path, "--quiet", "--no-epubcheck"), 2)

    def test_worst_exit_code_wins_over_several_books(self):
        clean, bad = self.build(name="clean.epub"), self.build(BAD_BOOK, name="bad.epub")
        self.assertEqual(run_cli(clean, bad, "--quiet", "--no-epubcheck"), 1)

    def test_auto_named_reports(self):
        path = self.build(name="내 책.epub")
        run_cli(path, "--html", "--json", "--quiet", "--no-epubcheck")
        base = os.path.splitext(path)[0]
        self.assertTrue(os.path.isfile(base + "_검수보고서.html"))
        self.assertTrue(os.path.isfile(base + "_검수보고서.json"))

    def test_explicit_report_paths(self):
        html, js = self.path("r.html"), self.path("r.json")
        run_cli(self.build(), "--html", html, "--json", js, "--quiet", "--no-epubcheck")
        self.assertTrue(os.path.isfile(html) and os.path.isfile(js))

    def test_shared_report_path_for_several_books_is_rejected(self):
        """경로를 하나로 주면 뒤 책이 앞 책 보고서를 덮어쓴다 — 조용히 잃지 않도록 막는다."""
        books = [self.build(name="a.epub"), self.build(name="b.epub")]
        for option in ("--json", "--html"):
            with self.subTest(option=option), contextlib.redirect_stderr(io.StringIO()) as err:
                with self.assertRaises(SystemExit):
                    run_cli(*books, option, self.path("one.json"), "--quiet", "--no-epubcheck")
                self.assertIn("덮어씁니다", err.getvalue())

    def test_auto_named_reports_for_several_books(self):
        books = [self.build(name="a.epub"), self.build(name="b.epub")]
        run_cli(*books, "--json", "--quiet", "--no-epubcheck")
        for name in ("a", "b"):
            self.assertTrue(os.path.isfile(self.path(f"{name}_검수보고서.json")), name)

    def test_publisher_options(self):
        book = Book(publisher="내출판사",
                    docs=[cover_doc(), Doc("ch1"),
                          colophon_doc(body="<h1>판권</h1><p>테스트 도서</p><p>지은이 홍길동</p>"
                                            "<p>발행일 2026년 9월 1일</p><p>발행처 내출판사</p><p>정가 5,900원</p>")])
        path = self.build(book)
        self.assertEqual(run_cli(path, "--quiet", "--no-epubcheck"), 1)
        self.assertEqual(run_cli(path, "--publisher", "내출판사", "--quiet", "--no-epubcheck"), 0)
        self.assertEqual(run_cli(path, "--any-publisher", "--quiet", "--no-epubcheck"), 0)

    def test_rules_file_overrides_limits(self):
        rules_path = self.path("rules.json")
        with open(rules_path, "w", encoding="utf-8") as fh:
            json.dump({"limits": {"max_epub_bytes": 500}}, fh)
        path = self.build()
        self.assertEqual(run_cli(path, "--quiet", "--no-epubcheck"), 0)
        self.assertEqual(run_cli(path, "--rules", rules_path, "--quiet", "--no-epubcheck"), 1)

    def test_gui_helper_writes_report_next_to_book(self):
        summary, report_path, passed = check_file_for_gui(self.build())
        self.assertTrue(passed)
        self.assertIn("통과", summary)
        self.assertTrue(report_path.endswith("book_검수보고서.html"))
        self.assertTrue(os.path.isfile(report_path))


class EpubcheckTest(BookTest):
    def test_severity_mapping_and_info_filter(self):
        payload = {"messages": [
            {"ID": "RSC-005", "severity": "ERROR", "message": "문법 오류",
             "locations": [{"path": "OEBPS/a.xhtml", "line": 12}]},
            {"ID": "HTM-014", "severity": "WARNING", "message": "권장 사항", "locations": [{"path": "OEBPS/b.xhtml"}]},
            {"ID": "INF-001", "severity": "INFO", "message": "정보", "locations": []},
            {"ID": "PKG-001", "severity": "FATAL", "message": "치명", "locations": []},
        ]}
        findings = epubcheck._parse(payload)
        self.assertEqual([f.level for f in findings], [Level.ERROR, Level.WARN, Level.ERROR])
        self.assertEqual(findings[0].location, "OEBPS/a.xhtml:12")
        self.assertTrue(findings[0].code.startswith("EPUBCHECK-"))

    def test_find_jar_prefers_explicit_path_then_env(self):
        jar = self.path("epubcheck.jar")
        open(jar, "wb").close()
        self.assertEqual(epubcheck.find_jar(jar), jar)
        self.assertIsNone(epubcheck.find_jar(self.path("nope.jar")))
        os.environ["EPUBCHECK_JAR"] = jar
        self.addCleanup(os.environ.pop, "EPUBCHECK_JAR", None)
        self.assertEqual(epubcheck.find_jar(None), jar)

    def test_cli_warns_when_given_jar_is_missing(self):
        book = self.build()
        self.assertEqual(run_cli(book, "--quiet", "--epubcheck", self.path("nope.jar")), 0)


class GuiTest(unittest.TestCase):
    def test_window_starts_and_reports_drag_and_drop_support(self):
        from upaper_check import gui
        try:
            result = gui.selftest()
        except Exception as exc:                      # 화면이 없는 환경
            self.skipTest(f"창을 띄울 수 없음: {exc}")
        self.assertIn(result, ("dnd:available", "dnd:unavailable"))


if __name__ == "__main__":
    unittest.main()
