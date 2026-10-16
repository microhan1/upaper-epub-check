"""새 버전 확인 — 하루 한 번, 끄기, 조용한 실패, 보내는 것, 알림이 뜨는 조건, 창 연동.
네트워크는 언제나 가짜다 — 이 시험은 실제 서버에 닿지 않는다.
(참고 구현 music-tag-filler 의 시험 30건을 같은 구성으로 옮기고, 이 도구의 창 연동 시험을 더했다)
"""
from __future__ import annotations

import io
import json
import os
import socket
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import net_guard  # noqa: E402,F401  — 시험이 운영 서버를 치지 못하게
from upaper_check import prefs as prefs_mod  # noqa: E402
from upaper_check import update_check as uc  # noqa: E402

DAY = "2026-10-13"
SLUG = "upaperepub"
OK = {"slug": SLUG, "latest": "0.3.0", "tag": "v0.3.0", "client": "0.2.6", "updateAvailable": True,
      "url": "https://chaekgalpi.co.kr/tools/upaperepub?utm_source=app&utm_medium=update"}


class FakeRoot:
    """after() 는 콜백을 바로 부른다. 백그라운드 스레드도 그 자리에서 돈다(InlineThread)."""

    def __init__(self):
        self.delays = []

    def after(self, ms, fn):
        self.delays.append(ms)
        fn()


class InlineThread:
    def __init__(self, target, name=None, daemon=None):
        self.target = target

    def start(self):
        self.target()


class FakeResp(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200):
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def counting(answer):
    calls = []

    def fetcher(slug, version):
        calls.append((slug, version))
        return answer

    return fetcher, calls


class InlineThreadTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(uc.threading, "Thread", InlineThread)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_once(self, prefs, fetcher, day=DAY):
        """한 번 실행: 예약하고, 서버가 답했을 때만 날짜를 기록한다(창이 하는 대로)."""
        results = []

        def on_result(info, answered):
            results.append(info)
            if answered:
                prefs.update_check_last = day

        root = FakeRoot()
        scheduled = uc.check_async(root, SLUG, "0.2.6", prefs, on_result, fetcher=fetcher, day=day)
        return scheduled, results, root


# ------------------------------------------------------------------ 얼마나 자주
class HowOftenTest(InlineThreadTest):
    def test_same_day_twice_asks_once(self):
        p = prefs_mod.Prefs()
        fetcher, calls = counting(OK)
        self.run_once(p, fetcher)
        self.run_once(p, fetcher)
        self.assertEqual(len(calls), 1)
        self.run_once(p, fetcher, day="2026-10-14")
        self.assertEqual(len(calls), 2)

    def test_switched_off_never_asks(self):
        p = prefs_mod.Prefs(update_check=False)
        fetcher, calls = counting(OK)
        scheduled, results, _ = self.run_once(p, fetcher)
        self.assertFalse(scheduled)
        self.assertEqual((calls, results), ([], []))

    def test_offline_does_not_use_up_the_day(self):
        p = prefs_mod.Prefs()
        fetcher, calls = counting(None)
        self.run_once(p, fetcher)
        self.run_once(p, fetcher)
        self.assertEqual(len(calls), 2)
        self.assertEqual(p.update_check_last, "")

    def test_waits_one_and_a_half_seconds_first(self):
        _, _, root = self.run_once(prefs_mod.Prefs(), counting(OK)[0])
        self.assertEqual(root.delays[0], 1500)


# ------------------------------------------------------------------ 무엇을 보내나
class WhatIsSentTest(unittest.TestCase):
    def test_request_carries_only_slug_version_and_os(self):
        seen = {}

        def opener(req, timeout):
            seen["url"], seen["timeout"] = req.full_url, timeout
            seen["headers"] = {k.lower(): v for k, v in req.header_items()}
            return FakeResp(json.dumps(OK).encode())

        self.assertEqual(uc.fetch(SLUG, "0.2.6", opener=opener), OK)
        url = urllib.parse.urlsplit(seen["url"])
        self.assertEqual((url.scheme, url.netloc, url.path), ("https", "chaekgalpi.co.kr", "/api/tools/upaperepub/latest"))
        self.assertEqual(urllib.parse.parse_qs(url.query), {"v": ["0.2.6"], "os": ["win"]})
        self.assertEqual(seen["timeout"], 4.0)
        self.assertEqual(seen["headers"]["user-agent"], "chaekgalpi-tool/upaperepub/0.2.6")
        self.assertLessEqual(set(seen["headers"]), {"user-agent", "accept"})   # 사용자·기기 정보는 없다

    def test_failures_are_silent(self):
        def make_opener(behaviour):
            def opener(req, timeout):
                if behaviour == "urlerror":
                    raise urllib.error.URLError("offline")
                if behaviour == "timeout":
                    raise socket.timeout("slow")
                if behaviour == "http500":
                    raise urllib.error.HTTPError(req.full_url, 500, "boom", {}, None)
                if behaviour == "oserror":
                    raise OSError("reset")
                if behaviour == "badjson":
                    return FakeResp(b"<html>not json")
                if behaviour == "list":
                    return FakeResp(b"[1, 2]")
                return FakeResp(json.dumps(OK).encode(), status=500)
            return opener

        for behaviour in ("urlerror", "timeout", "http500", "badjson", "list", "status500", "oserror"):
            with self.subTest(behaviour=behaviour):
                self.assertIsNone(uc.fetch(SLUG, "0.2.6", opener=make_opener(behaviour)))


# ------------------------------------------------------------------ 알림이 뜨는 조건
class WhenNoticeShowsTest(InlineThreadTest):
    def test_no_notice_unless_server_says_true(self):
        for flag in (False, None, "true", 1):
            with self.subTest(flag=flag):
                self.assertIsNone(uc.interpret(dict(OK, updateAvailable=flag), "0.2.6"))

    def test_notice_once_when_newer(self):
        fetcher, _ = counting(OK)
        _, results, _ = self.run_once(prefs_mod.Prefs(), fetcher)
        self.assertEqual(results, [uc.UpdateInfo("0.3.0", "0.2.6", OK["url"])])

    def test_later_hides_that_version_but_not_a_newer_one(self):
        p = prefs_mod.Prefs(update_check_skipped="0.3.0")
        self.assertIsNone(uc.interpret(OK, "0.2.6", p.update_check_skipped))
        self.assertEqual(uc.interpret(dict(OK, latest="0.3.1"), "0.2.6", p.update_check_skipped).latest, "0.3.1")

    def test_only_pages_of_the_tools_site_are_opened(self):
        for url in ("https://github.com/microhan1/upaper-epub-check/releases", "http://chaekgalpi.co.kr/tools/x",
                    "https://chaekgalpi.co.kr.evil.example/", "javascript:alert(1)", None, 5):
            with self.subTest(url=url):
                self.assertIsNone(uc.interpret(dict(OK, url=url), "0.2.6"))

    def test_odd_versions_show_nothing(self):
        for latest in ("", "   ", None, 3, "x" * 40):
            with self.subTest(latest=latest):
                self.assertIsNone(uc.interpret(dict(OK, latest=latest), "0.2.6"))


# ------------------------------------------------------------------ 창을 닫아도 죽지 않기 (v0.2.7)
class ThreadSafetyTest(unittest.TestCase):
    def test_the_thread_holds_no_tk_object(self):
        """작업 스레드가 창을 붙잡으면 안 된다 — 마지막 참조를 쥐고 끝나면 Tk 객체가 메인 스레드 밖에서
        풀리고 Tcl 이 프로세스를 죽인다."""
        captured = {}

        class CaptureThread:
            def __init__(self, target, name=None, daemon=None):
                captured["target"] = target

            def start(self):
                pass

        class Root:
            def after(self, ms, fn):
                if ms == uc.DELAY_MS:
                    fn()

        root, on_result = Root(), lambda info, answered: None
        with mock.patch.object(uc.threading, "Thread", CaptureThread):
            uc.check_async(root, SLUG, "0.2.7", prefs_mod.Prefs(), on_result, fetcher=lambda s, v: OK, day=DAY)
        target = captured["target"]
        held = [c.cell_contents for c in (target.__closure__ or ())] + list(target.__defaults__ or ())
        self.assertFalse(any(x is root or x is on_result for x in held))

    def test_closing_while_the_request_is_out_does_not_abort_tcl(self):
        """고치기 전에는 'Tcl_AsyncDelete: async handler deleted by the wrong thread' 로 죽었다(v0.2.6)."""
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "close_while_asking.py")
            with open(script, "w", encoding="utf-8") as fh:
                fh.write(CLOSE_WHILE_ASKING.format(root=ROOT, tests=os.path.join(ROOT, "tests"), prefs=os.path.join(tmp, "settings.json")))
            p = subprocess.run([sys.executable, "-W", "ignore", script], capture_output=True, timeout=120)
        out = (p.stdout + p.stderr).decode("utf-8", "replace")
        self.assertEqual(p.returncode, 0, out[-800:])
        self.assertIn("survived", out)
        self.assertNotIn("Tcl_AsyncDelete", out)


CLOSE_WHILE_ASKING = r"""
import sys, time
sys.path.insert(0, {root!r})
sys.path.insert(0, {tests!r})
import net_guard          # 이 자식 프로세스도 운영 서버를 치지 못하게
from upaper_check import gui
def slow(slug, version):
    time.sleep(1.5)          # 창이 닫힐 때 요청이 아직 나가 있다
    return {{"latest": "9.9.9", "updateAvailable": True, "url": "https://chaekgalpi.co.kr/tools/upaperepub"}}
for _ in range(3):
    win = gui.DropWindow(lambda _p: ("", "", True), prefs_path={prefs!r}, fetcher=slow)
    win.root.after(1700, win.destroy)      # 요청을 보낸 지 0.2초 뒤
    win.root.mainloop()
    del win
    time.sleep(2.0)          # 창이 없는 채로 스레드가 끝난다
print("survived")
"""


# ------------------------------------------------------------------ 설정 파일
class SettingsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = os.path.join(self._tmp.name, "settings.json")

    def write(self, data):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def test_settings_are_type_checked(self):
        self.write({"update_check": "no", "update_check_last": 20261013, "update_check_skipped": ["0.3.0"]})
        p = prefs_mod.load(self.path)
        self.assertEqual((p.update_check, p.update_check_last, p.update_check_skipped), (True, "", ""))

    def test_missing_or_broken_file_gives_defaults(self):
        self.assertEqual(prefs_mod.load(self.path), prefs_mod.Prefs())
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("{ not json")
        self.assertEqual(prefs_mod.load(self.path), prefs_mod.Prefs())

    def test_save_keeps_keys_it_does_not_know(self):
        self.write({"other_tool_option": 7})
        prefs_mod.save(prefs_mod.Prefs(update_check_last=DAY), self.path)
        with open(self.path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["other_tool_option"], 7)
        self.assertEqual(data["update_check_last"], DAY)

    def test_settings_live_next_to_the_program(self):
        with mock.patch.object(prefs_mod.sys, "frozen", True, create=True), \
             mock.patch.object(prefs_mod.sys, "executable", r"C:\tools\upaper\유페이퍼EPUB검수.exe"):
            self.assertEqual(prefs_mod.settings_path(), os.path.join(r"C:\tools\upaper", "settings.json"))


# ------------------------------------------------------------------ 창 연동
class WindowNoticeTest(unittest.TestCase):
    """실제 창을 띄우되 설정 파일은 임시 폴더, 서버는 가짜로."""

    def setUp(self):
        from upaper_check import gui
        self.gui = gui
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = os.path.join(self._tmp.name, "settings.json")
        try:
            self.win = gui.DropWindow(lambda _p: ("", "", True), prefs_path=self.path, check_updates=False)
        except Exception as exc:
            self.skipTest(f"창을 띄울 수 없음: {exc}")
        self.addCleanup(self.win.destroy)
        self.info = uc.UpdateInfo("0.3.0", "0.2.6", OK["url"])

    def saved(self) -> dict:
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_answer_records_the_day_and_shows_one_line(self):
        self.win._on_update_result(self.info, True)
        self.win.root.update_idletasks()
        self.assertEqual(self.saved()["update_check_last"], uc.today())
        self.assertTrue(self.win.frm_update.winfo_manager())
        self.assertEqual(self.win.lbl_update.cget("text"), "새 버전이 나왔습니다: 0.3.0 (현재 0.2.6)")

    def test_no_answer_records_nothing_and_shows_nothing(self):
        self.win._on_update_result(None, False)
        self.assertFalse(os.path.exists(self.path))
        self.assertFalse(self.win.frm_update.winfo_manager())

    def test_update_button_opens_only_the_tools_site(self):
        self.win._on_update_result(self.info, True)
        with mock.patch.object(self.gui.webbrowser, "open") as opened:
            self.win._update_open()
        opened.assert_called_once_with(OK["url"])
        self.assertFalse(self.win.frm_update.winfo_manager())
        self.win._update_info = uc.UpdateInfo("0.3.0", "0.2.6", "https://evil.example/")
        with mock.patch.object(self.gui.webbrowser, "open") as opened:
            self.win._update_open()
        opened.assert_not_called()

    def test_later_remembers_the_version(self):
        self.win._on_update_result(self.info, True)
        self.win._update_later()
        self.assertEqual(self.saved()["update_check_skipped"], "0.3.0")
        self.assertFalse(self.win.frm_update.winfo_manager())

    def test_switching_off_hides_the_notice_and_is_saved(self):
        self.win._on_update_result(self.info, True)
        self.win.var_update_check.set(False)
        self.win._on_update_toggle()
        self.assertFalse(self.win.frm_update.winfo_manager())
        self.assertIs(self.saved()["update_check"], False)

    def test_layout_above_the_notice_does_not_move(self):
        self.win.root.update()
        before = (self.win.zone.winfo_y(), self.win.open_button.winfo_y(), self.win.log.winfo_y())
        self.win._on_update_result(self.info, True)
        self.win.root.update()
        after = (self.win.zone.winfo_y(), self.win.open_button.winfo_y(), self.win.log.winfo_y())
        self.assertEqual(before, after)
        self.assertGreater(self.win.frm_update.winfo_y(), self.win.log.winfo_y())

    def test_window_asks_through_check_async_with_this_tool(self):
        seen = []

        def fake_fetcher(slug, version):
            seen.append((slug, version))
            return None

        with mock.patch.object(uc.threading, "Thread", InlineThread):
            win = self.gui.DropWindow(lambda _p: ("", "", True), prefs_path=self.path, fetcher=fake_fetcher)
            self.addCleanup(win.destroy)
            win.root.after(1600, win.root.quit)
            win.root.mainloop()
        from upaper_check import __version__
        self.assertEqual(seen, [(SLUG, __version__)])
        self.assertFalse(os.path.exists(self.path))   # 답이 없었으니 날짜도 안 쓴다

    def test_selftest_never_asks_or_writes(self):
        with mock.patch.object(uc, "fetch") as fetch, \
             mock.patch.object(prefs_mod, "save") as save:
            self.assertIn(self.gui.selftest(), ("dnd:available", "dnd:unavailable"))
        fetch.assert_not_called()
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
