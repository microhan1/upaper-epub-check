"""시작 속도 — 검사 엔진(lxml·Pillow) 늦게 불러오기와 exe 시작 그림 닫기."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import types
import unittest
from unittest import mock

from helpers import ROOT, BookTest
from upaper_check import cli, splash

PY = sys.executable
IMPORT_PROBE = ("import sys; import upaper_check.{mod}; "
                "print(sorted(m for m in ('lxml', 'PIL') if m in sys.modules or any(k.startswith(m + '.') for k in sys.modules)))")


def heavy_after_import(module: str) -> str:
    """새 파이썬에서 모듈 하나만 불러온 뒤 lxml·PIL 이 올라왔는지 본다."""
    env = dict(os.environ, PYTHONPATH=ROOT)
    out = subprocess.run([PY, "-c", IMPORT_PROBE.format(mod=module)], capture_output=True, text=True, env=env, cwd=ROOT)
    return out.stdout.strip() or out.stderr.strip()


class DeferredEngineTest(BookTest):
    def setUp(self):
        super().setUp()
        self._saved = cli._engine
        cli._engine = None
        self.addCleanup(setattr, cli, "_engine", self._saved)

    def test_cli_and_gui_modules_do_not_pull_lxml_or_pillow(self):
        self.assertEqual(heavy_after_import("cli"), "[]")
        self.assertEqual(heavy_after_import("gui"), "[]")
        self.assertEqual(heavy_after_import("splash"), "[]")

    def test_load_engine_loads_once_and_returns_same_bundle(self):
        first = cli.load_engine()
        self.assertIs(cli.load_engine(), first)
        for name in ("epubcheck", "run_all", "find_cover_image", "Context", "load_rules",
                     "EpubLoadError", "EpubPackage", "Report"):
            self.assertTrue(hasattr(first, name), name)

    def test_concurrent_callers_get_one_engine_without_error(self):
        results, errors = [], []

        def worker():
            try:
                results.append(cli.load_engine())
            except Exception as exc:  # pragma: no cover - 실패 진단용
                errors.append(exc)
        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 8)
        self.assertTrue(all(r is results[0] for r in results))

    def test_check_right_after_preload_starts_gives_same_result(self):
        """창이 뜨자마자(배경 불러오기가 끝나기 전에) 파일을 넣어도 결과가 같다."""
        path = self.build()
        thread = threading.Thread(target=cli.preload_engine, daemon=True)
        thread.start()
        early = cli.check_file_for_gui(path)
        thread.join(10)
        late = cli.check_file_for_gui(path)
        self.assertEqual(early, late)
        self.assertTrue(early[2])

    def test_preload_failure_is_silent_and_retried_on_use(self):
        with mock.patch.object(cli, "load_engine", side_effect=ImportError("가짜 실패")):
            cli.preload_engine()          # 예외가 밖으로 나오지 않는다
        self.assertIsNone(cli._engine)
        self.assertIsNotNone(cli.load_engine())


class SplashCloseTest(unittest.TestCase):
    def _fake_pyi_splash(self, close):
        module = types.ModuleType("pyi_splash")
        module.close = close
        return mock.patch.dict(sys.modules, {"pyi_splash": module})

    def test_without_pyi_splash_does_nothing(self):
        with mock.patch.dict(sys.modules, {"pyi_splash": None}):   # import 가 ImportError 를 낸다
            splash.close()

    def test_calls_pyi_splash_close_once(self):
        close = mock.Mock()
        with self._fake_pyi_splash(close):
            splash.close()
        close.assert_called_once_with()

    def test_close_error_is_swallowed(self):
        with self._fake_pyi_splash(mock.Mock(side_effect=RuntimeError("이미 닫힘"))):
            splash.close()

    def test_cli_path_closes_splash_before_checking(self):
        order = []
        with mock.patch.object(cli.splash, "close", side_effect=lambda: order.append("close")), \
                mock.patch.object(cli, "_check_one", side_effect=lambda *a: order.append("check") or 0):
            cli.main(["book.epub", "--no-epubcheck"])
        self.assertEqual(order, ["close", "check"])

    def test_gui_path_closes_splash_only_after_window_is_drawn(self):
        from upaper_check import gui
        order = []
        fake_window = mock.Mock()
        fake_window.root.update.side_effect = lambda: order.append("drawn")
        fake_window.mainloop.side_effect = lambda: order.append("loop")
        with mock.patch.object(gui, "DropWindow", return_value=fake_window), \
                mock.patch.object(gui.splash, "close", side_effect=lambda: order.append("close")):
            gui.run_window(lambda _p: ("", "", True), after_shown=lambda: order.append("preload"))
        self.assertEqual(order, ["drawn", "close", "preload", "loop"])

    def test_gui_path_closes_splash_even_if_window_creation_fails(self):
        from upaper_check import gui
        closed = []
        with mock.patch.object(gui, "DropWindow", side_effect=RuntimeError("Tk 없음")), \
                mock.patch.object(gui.splash, "close", side_effect=lambda: closed.append(True)):
            with self.assertRaises(RuntimeError):
                gui.run_window(lambda _p: ("", "", True))
        self.assertEqual(closed, [True])

    def test_selftest_path_closes_splash(self):
        from upaper_check import gui
        closed = []
        with mock.patch.dict(os.environ, {cli.SELFTEST_ENV: "1"}), \
                mock.patch.object(gui, "selftest", return_value="dnd:available"), \
                mock.patch.object(cli.splash, "close", side_effect=lambda: closed.append(True)), \
                mock.patch("builtins.print"):
            self.assertEqual(cli.main([]), cli.EXIT_PASS)
        self.assertEqual(closed, [True])


class SplashAssetTest(unittest.TestCase):
    def test_splash_png_exists_small_and_listed_in_spec(self):
        png = os.path.join(ROOT, "assets", "splash.png")
        self.assertTrue(os.path.isfile(png))
        self.assertLess(os.path.getsize(png), 20 * 1024)
        with open(png, "rb") as fh:
            self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n")
        with open(os.path.join(ROOT, "upaper_check.spec"), encoding="utf-8") as fh:
            spec = fh.read()
        self.assertIn("Splash(", spec)
        self.assertIn("splash.png", spec)
        self.assertIn("splash.binaries", spec)


if __name__ == "__main__":
    unittest.main()
