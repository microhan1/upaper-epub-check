"""시험 중 네트워크 차단(net_guard) 자체를 확인한다 — 이 가드가 빠지면 시험이 운영 서버를 칠 수 있다."""
from __future__ import annotations

import glob
import os
import sys
import unittest
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import net_guard  # noqa: E402
from upaper_check import update_check as uc  # noqa: E402

TESTS_DIR = os.path.join(ROOT, "tests")


class NetGuardTest(unittest.TestCase):
    def test_default_entry_points_are_the_guard(self):
        self.assertIs(uc.fetch.__kwdefaults__["opener"], net_guard.guard_urlopen)
        self.assertIs(urllib.request.urlopen, net_guard.guard_urlopen)
        self.assertIs(uc.check_async.__kwdefaults__["fetcher"], net_guard.no_fetch)
        self.assertIsNone(uc.check_async.__kwdefaults__["fetcher"](uc.SLUG, "0.0.0"))

    def test_fetch_without_opener_is_recorded_and_returns_none(self):
        net_guard.drain()
        self.assertIsNone(uc.fetch(uc.SLUG, "0.2.7"))
        taken = net_guard.drain()
        self.assertEqual(len(taken), 1)
        self.assertTrue(taken[0].startswith("https://chaekgalpi.co.kr/api/tools/upaperepub/latest?"), taken[0])

    def test_a_test_that_sends_a_request_fails(self):
        class Leaky(unittest.TestCase):
            def runTest(self):
                uc.fetch(uc.SLUG, "0.2.7")

        result = unittest.TestResult()
        Leaky().run(result)
        self.assertEqual(len(result.failures) + len(result.errors), 1)
        self.assertIn("네트워크 요청", (result.failures + result.errors)[0][1])
        self.assertEqual(net_guard.BLOCKED, [])

    def test_every_test_module_installs_the_guard(self):
        """helpers 를 거치거나 직접 import — 어느 모듈 하나만 따로 돌려도 가드가 깔린다."""
        for path in glob.glob(os.path.join(TESTS_DIR, "test_*.py")):
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
            with self.subTest(os.path.basename(path)):
                self.assertTrue("import net_guard" in src or "from helpers import" in src)


if __name__ == "__main__":
    unittest.main()
