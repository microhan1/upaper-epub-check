"""「의견 보내기」 — 주소 조립, 버튼 콜백, 브라우저를 못 열 때, 문구, 네트워크 0건.
브라우저는 언제나 가짜다 — 이 시험은 실제 브라우저를 열지도, 서버에 닿지도 않는다.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import unittest
import urllib.parse
import urllib.request
import webbrowser
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import net_guard  # noqa: E402  — 시험이 운영 서버를 치지 못하게
from upaper_check import __version__  # noqa: E402
from upaper_check import update_check as uc  # noqa: E402

SLUG = "upaperepub"
KO = "https://chaekgalpi.co.kr/tools/upaperepub?utm_source=app&utm_medium=feedback&v=0.2.8#feedback"
EN = "https://chaekgalpi.co.kr/en/tools/upaperepub?utm_source=app&utm_medium=feedback&v=0.2.8#feedback"
LANGS = ("ko", "en", "ja", "zh-CN")


def query_of(url: str) -> dict:
    return urllib.parse.parse_qs(urllib.parse.urlsplit(url).query, keep_blank_values=True)


# ------------------------------------------------------------------ a. 주소
class AddressTest(unittest.TestCase):
    def test_exact_address_per_language(self):
        expected = {"ko": KO, "en": EN, "ja": EN, "zh-CN": EN}
        for lang, url in expected.items():
            with self.subTest(lang):
                self.assertEqual(uc.feedback_url(SLUG, "0.2.8", lang), url)

    def test_missing_language_gives_korean_page(self):
        for lang in (None, "", "  "):
            with self.subTest(lang=lang):
                self.assertEqual(uc.feedback_url(SLUG, "0.2.8", lang), KO)

    def test_unknown_language_gives_english_page(self):
        """10-27 공통 규칙: ko 로 시작하지 않으면 모두 영어 페이지(v0.2.8 까지는 한국어였다)."""
        for lang in ("fr", "de", "zh-TW", "kr", "xx-YY"):
            with self.subTest(lang=lang):
                self.assertEqual(uc.feedback_url(SLUG, "0.2.8", lang), EN)

    def test_language_code_case_and_separator(self):
        for lang in ("EN", "En", "JA", "zh-cn", "ZH-CN", "zh_CN", " en "):
            with self.subTest(lang=lang):
                self.assertEqual(uc.feedback_url(SLUG, "0.2.8", lang), EN)
        self.assertEqual(uc.feedback_url(SLUG, "0.2.8", "KO"), KO)

    def test_shape_of_every_address(self):
        for lang in LANGS + (None, "fr"):
            for version in ("0.2.8", "", None):
                url = uc.feedback_url(SLUG, version, lang)
                with self.subTest(lang=lang, version=version):
                    self.assertTrue(url.startswith("https://chaekgalpi.co.kr/"), url)
                    self.assertTrue(url.endswith("#feedback"), url)
                    self.assertEqual(url.count("#"), 1)
                    q = query_of(url)
                    self.assertEqual(q["utm_source"], ["app"])
                    self.assertEqual(q["utm_medium"], ["feedback"])
                    self.assertEqual(urllib.parse.urlsplit(url).netloc, "chaekgalpi.co.kr")

    def test_slug_is_this_tool(self):
        self.assertEqual(uc.SLUG, SLUG)


# ------------------------------------------------------------------ b. 버전
class VersionTest(unittest.TestCase):
    def test_ordinary_versions(self):
        for version in ("0.2.1", "v0.2.1", "1.0.0-beta+3", __version__):
            with self.subTest(version):
                url = uc.feedback_url(SLUG, version, "ko")
                self.assertEqual(query_of(url)["v"], [version])
                self.assertTrue(url.endswith("#feedback"))

    def test_plus_is_encoded_not_read_as_space(self):
        self.assertIn("v=1.0.0-beta%2B3#", uc.feedback_url(SLUG, "1.0.0-beta+3", "en"))

    def test_empty_version_drops_the_parameter(self):
        for version in ("", None, "   "):
            with self.subTest(version=version):
                url = uc.feedback_url(SLUG, version, "ko")
                self.assertNotIn("v", query_of(url))
                self.assertEqual(url, "https://chaekgalpi.co.kr/tools/upaperepub?utm_source=app&utm_medium=feedback#feedback")

    def test_strange_values_are_encoded_and_read_back_unchanged(self):
        for version in ("0.2 beta", "1&utm_source=evil", "1#top", "버전 1", "a=b?c/d", "%20", "1\n2", " 0.2.8 "):
            url = uc.feedback_url(SLUG, version, "ko")
            with self.subTest(version=version):
                q = query_of(url)
                self.assertEqual(q["v"], [version])
                self.assertEqual(q["utm_source"], ["app"])          # & 가 끼어들어도 파라미터가 늘지 않는다
                self.assertEqual(sorted(q), ["utm_medium", "utm_source", "v"])
                self.assertEqual(urllib.parse.urlsplit(url).fragment, "feedback")
                self.assertTrue(url.endswith("#feedback"))
                self.assertFalse(any(ch in url for ch in " \n가"), url)


# ------------------------------------------------------------------ c~g. 창의 버튼
class NoNetwork:
    """with 블록 안에서 urlopen·소켓 연결을 기록한다 — 0건이어야 한다."""

    def __enter__(self):
        self.calls: list = []
        self.before = len(net_guard.BLOCKED)

        def record(*args, **kwargs):
            self.calls.append(args)
            raise OSError("시험 중 소켓 차단")

        self._patches = [mock.patch.object(urllib.request, "urlopen", side_effect=record),
                         mock.patch.object(socket.socket, "connect", side_effect=record),
                         mock.patch.object(socket.socket, "connect_ex", side_effect=record),
                         mock.patch.object(socket, "create_connection", side_effect=record)]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        self.calls += net_guard.BLOCKED[self.before:]
        return False


class NoNetworkSelfTest(unittest.TestCase):
    def test_the_recorder_catches_sockets_and_urlopen(self):
        """g 의 '0건' 단언이 헛돌지 않는지 — 연결 시도는 실제로 기록된다(주소는 닫힌 포트, 나가지 않는다)."""
        with NoNetwork() as net:
            for attempt in (lambda: socket.create_connection(("127.0.0.1", 9), timeout=0.1),
                            lambda: self.connect_plain_socket(),
                            lambda: urllib.request.urlopen("https://chaekgalpi.co.kr/")):
                with self.assertRaises(OSError):
                    attempt()
        self.assertEqual(len(net.calls), 3)

    @staticmethod
    def connect_plain_socket():
        with socket.socket() as sock:
            sock.connect(("127.0.0.1", 9))


class FeedbackButtonTest(unittest.TestCase):
    """실제 창을 띄우되 설정 파일은 임시 폴더, 새 버전 확인은 끄고, 브라우저는 가짜로.
    창은 클래스에 하나 — pytest 에서 Tk 를 시험마다 새로 만들면 가끔 tk.tcl 을 못 찾고 건너뛰어졌다."""

    @classmethod
    def setUpClass(cls):
        from upaper_check import gui
        cls.gui = gui
        cls._tmp = tempfile.TemporaryDirectory()
        cls.path = os.path.join(cls._tmp.name, "settings.json")
        try:
            cls.win = gui.DropWindow(lambda _p: ("", "", True), prefs_path=cls.path, check_updates=False)
        except Exception as exc:
            cls._tmp.cleanup()
            raise unittest.SkipTest(f"창을 띄울 수 없음: {exc}")

    @classmethod
    def tearDownClass(cls):
        cls.win.destroy()
        cls._tmp.cleanup()

    def setUp(self):
        win = self.win
        win.lang = self.gui.UI_LANG
        win.last_report = ""
        win._hide_update_notice()
        win.log.config(state="normal")
        win.log.delete("1.0", "end")
        win.log.config(state="disabled")
        if os.path.exists(self.path):
            os.remove(self.path)
        self.net = NoNetwork().__enter__()
        self.addCleanup(self.assert_no_network)
        self.addCleanup(self.net.__exit__)

    def assert_no_network(self):
        self.assertEqual(self.net.calls, [], "의견 보내기 시험이 네트워크에 닿았다")

    def log_text(self) -> str:
        return self.win.log.get("1.0", "end")

    def state(self) -> tuple:
        w = self.win
        return (w.last_report, w.open_button.cget("state"), w.log.cget("state"), w.auto_open.get(),
                w.var_update_check.get(), bool(w.frm_update.winfo_manager()), w.zone.cget("text"),
                os.path.exists(self.path))

    def click(self, opener):
        with mock.patch.object(self.gui.webbrowser, "open", opener):
            self.win.feedback_button.invoke()

    # c. 콜백
    def test_click_opens_the_feedback_page_once(self):
        opener = mock.Mock(return_value=True)
        self.click(opener)
        opener.assert_called_once_with(uc.feedback_url(SLUG, __version__, "ko"))
        self.assertEqual(opener.call_args.args[0],
                         f"https://chaekgalpi.co.kr/tools/upaperepub?utm_source=app&utm_medium=feedback&v={__version__}#feedback")
        self.assertEqual(self.log_text().strip(), "")       # 성공하면 아무 말도 안 한다

    def test_callback_without_the_button(self):
        opener = mock.Mock(return_value=True)
        with mock.patch.object(self.gui.webbrowser, "open", opener):
            self.win.send_feedback()
        self.assertEqual(opener.call_count, 1)

    def test_changing_language_changes_the_next_address(self):
        opener = mock.Mock(return_value=True)
        self.click(opener)
        self.win.lang = "en"
        self.click(opener)
        self.win.lang = "zh-CN"
        self.click(opener)
        urls = [c.args[0] for c in opener.call_args_list]
        self.assertEqual(urls[0], uc.feedback_url(SLUG, __version__, "ko"))
        self.assertEqual(urls[1], uc.feedback_url(SLUG, __version__, "en"))
        self.assertTrue(urls[1].startswith("https://chaekgalpi.co.kr/en/tools/"))
        self.assertEqual(urls[2], urls[1])

    def test_each_click_opens_once(self):
        opener = mock.Mock(return_value=True)
        for _ in range(3):
            self.click(opener)
        self.assertEqual(opener.call_count, 3)

    # d. 실패
    def test_failures_show_a_copyable_address_and_keep_the_window(self):
        url = uc.feedback_url(SLUG, __version__, "ko")
        failures = {"False": mock.Mock(return_value=False),
                    "None": mock.Mock(return_value=None),
                    "webbrowser.Error": mock.Mock(side_effect=webbrowser.Error("no browser")),
                    "OSError": mock.Mock(side_effect=OSError("access denied")),
                    "RuntimeError": mock.Mock(side_effect=RuntimeError("odd"))}
        for name, opener in failures.items():
            with self.subTest(name):
                before = self.state()
                self.click(opener)                          # 예외가 밖으로 나오지 않는다
                self.assertEqual(self.state(), before)
                text = self.log_text()
                self.assertIn(self.gui.FEEDBACK_TEXT["ko"]["failed"], text)
                self.assertIn(url + "\n", text)            # 주소가 한 줄로 온전히 — 그대로 복사할 수 있다
                self.assertTrue(self.win.root.winfo_exists())

    def test_failure_text_follows_the_language(self):
        self.win.lang = "ja"
        self.click(mock.Mock(return_value=False))
        self.assertIn(self.gui.FEEDBACK_TEXT["ja"]["failed"], self.log_text())
        self.assertIn(uc.feedback_url(SLUG, __version__, "ja"), self.log_text())

    def test_window_still_works_after_a_failure(self):
        self.click(mock.Mock(side_effect=OSError))
        self.win.run_files(["책.txt"])                      # 검사 흐름이 계속 돈다
        self.assertIn("건너뜀: 책.txt", self.log_text())
        opener = mock.Mock(return_value=True)
        self.click(opener)
        opener.assert_called_once()

    def test_unknown_language_falls_back_to_korean_text(self):
        self.win.lang = "fr"
        self.click(mock.Mock(return_value=False))
        self.assertIn(self.gui.FEEDBACK_TEXT["ko"]["failed"], self.log_text())
        self.assertIn(uc.feedback_url(SLUG, __version__, "fr"), self.log_text())   # 페이지는 영어

    # e. 문구
    def test_button_shows_the_korean_label(self):
        self.assertEqual(self.win.feedback_button.cget("text"), "의견 보내기")

    def test_button_sits_next_to_the_update_checkbox(self):
        self.win.root.update()
        siblings = self.win.feedback_button.master.winfo_children()
        labels = [w.cget("text") for w in siblings]
        self.assertIn("새 버전 확인", labels)
        self.assertTrue(self.win.feedback_button.winfo_ismapped())
        right = self.win.feedback_button.winfo_x() + self.win.feedback_button.winfo_width()
        self.assertLessEqual(right, self.win.feedback_button.master.winfo_width())   # 잘리지 않는다

    # f. 새 버전 확인에 영향 없음
    def test_update_notice_still_works_beside_the_button(self):
        info = uc.UpdateInfo("9.9.9", __version__, "https://chaekgalpi.co.kr/tools/upaperepub")
        self.win._on_update_result(info, True)
        self.win.root.update_idletasks()
        self.assertTrue(self.win.frm_update.winfo_manager())
        opener = mock.Mock(return_value=True)
        self.click(opener)
        self.assertTrue(self.win.frm_update.winfo_manager())   # 의견 보내기는 알림을 건드리지 않는다
        with mock.patch.object(self.gui.webbrowser, "open") as opened:
            self.win._update_open()
        opened.assert_called_once_with(info.url)


class FeedbackTextTest(unittest.TestCase):
    def test_every_language_has_every_key(self):
        from upaper_check import gui
        self.assertEqual(set(gui.FEEDBACK_TEXT), set(LANGS))
        keys = set(gui.FEEDBACK_TEXT["ko"])
        for lang in LANGS:
            with self.subTest(lang):
                self.assertEqual(set(gui.FEEDBACK_TEXT[lang]), keys)
                for key, text in gui.FEEDBACK_TEXT[lang].items():
                    self.assertTrue(text.strip(), f"{lang}.{key} 가 비었다")

    def test_labels_are_the_series_wording(self):
        from upaper_check import gui
        labels = {lang: gui.FEEDBACK_TEXT[lang]["label"] for lang in LANGS}
        self.assertEqual(labels, {"ko": "의견 보내기", "en": "Send feedback", "ja": "ご意見を送る", "zh-CN": "发送反馈"})

    def test_every_language_maps_to_an_existing_page(self):
        from upaper_check import gui
        for lang in gui.FEEDBACK_TEXT:
            with self.subTest(lang):
                path = urllib.parse.urlsplit(uc.feedback_url(SLUG, "1", lang)).path
                self.assertIn(path, ("/tools/upaperepub", "/en/tools/upaperepub"))


# ------------------------------------------------------------------ f. 명령줄 회귀
class CommandLineTest(unittest.TestCase):
    def run_cli(self, *args):
        env = dict(os.environ, PYTHONIOENCODING="utf-8", HTTP_PROXY="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9")
        return subprocess.run([sys.executable, os.path.join(ROOT, "upaper_check.py"), *args],
                              capture_output=True, timeout=60, env=env)

    def test_version_is_unchanged_in_shape(self):
        p = self.run_cli("--version")
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout.decode("utf-8").strip(), f"upaper_check {__version__}")

    def test_help_has_no_feedback_line(self):
        """창이 있는 도구라 --help 는 그대로 — 의견 보내기는 창의 버튼이 맡는다."""
        p = self.run_cli("--help")
        out = p.stdout.decode("utf-8")
        self.assertEqual(p.returncode, 0)
        self.assertIn("--epubcheck", out)
        self.assertNotIn("feedback", out)
        self.assertNotIn("chaekgalpi", out)


if __name__ == "__main__":
    unittest.main()
