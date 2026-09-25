"""테스트 공통 도우미 — 책을 임시 폴더에 만들고 검사 결과를 코드 집합으로 돌려준다."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from builders import Book  # noqa: E402
from upaper_check.checks import run_all  # noqa: E402
from upaper_check.context import Context, load_rules  # noqa: E402
from upaper_check.epub import EpubPackage  # noqa: E402
from upaper_check.findings import Level  # noqa: E402

REGRESSION_EPUB = r"D:\my\PDF To Epub\dist\스캔북 컨버터\doc\하늘은 왜 파래요 - microhan.epub"


class BookTest(unittest.TestCase):
    """책을 만들어 검사하는 테스트의 기반. 각 테스트가 자기 임시 폴더를 쓴다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def path(self, name: str = "book.epub") -> str:
        return os.path.join(self.tmp, name)

    def build(self, book: Book | None = None, name: str = "book.epub") -> str:
        return (book or Book()).build(self.path(name))

    def check(self, book: Book | None = None, name: str = "book.epub", **rule_overrides):
        """책을 만들어 검사하고 findings 를 돌려준다."""
        return check_path(self.build(book, name), **rule_overrides)

    # ---------- 단언 ----------
    def assertCode(self, findings, code: str, level: Level | None = None):
        found = [f for f in findings if f.code == code and (level is None or f.level == level)]
        self.assertTrue(found, f"{code}{'/' + level.name if level else ''} 가 없습니다: {summary(findings)}")
        return found[0]

    def assertNoCode(self, findings, code: str):
        found = [f for f in findings if f.code == code]
        self.assertFalse(found, f"{code} 가 잘못 잡혔습니다: {[f.message for f in found]}")

    def assertClean(self, findings):
        errors = [f for f in findings if f.level == Level.ERROR]
        self.assertEqual(errors, [], f"오류가 없어야 합니다: {[f'{f.code}: {f.message}' for f in errors]}")


def check_path(epub_path: str, **rule_overrides):
    rules = load_rules()
    for key, value in rule_overrides.items():
        if isinstance(value, dict) and isinstance(rules.get(key), dict):
            rules[key].update(value)
        else:
            rules[key] = value
    return run_all(Context(EpubPackage(epub_path), rules))


def codes(findings, level: Level | None = None) -> set[str]:
    return {f.code for f in findings if level is None or f.level == level}


def summary(findings) -> str:
    return ", ".join(f"{f.code}({f.level.name})" for f in findings) or "(지적 없음)"
