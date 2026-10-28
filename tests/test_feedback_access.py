"""「의견 보내기」 공통 후속(2026-10-27) — Tab 으로 닿고 Enter·Space 로 열리는 링크, 마우스를 올리면
뜨는 작은 설명, 언어 코드 하나의 규칙(ko… → 한국어 페이지, 그 밖 → 영어 페이지).
브라우저는 가짜, 설정은 임시 폴더, 새 버전 확인은 끈다 — 네트워크에 닿으면 실패.

키 누름: 만든 키 이벤트는 창이 시스템 키보드 초점을 가져야 위젯에 닿고, 그 초점을 빼앗으면 사용자가
치던 글자를 가로챈다. 그래서 Tk 가 그 키에 묶어 둔 스크립트를 그대로 실행하고(키가 들어올 때 Tk 가
하는 일), Tab 순서는 Tk 의 <Tab> 바인딩이 쓰는 tk_focusNext·tk_focusPrev 로 본다.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import time
import unittest
import urllib.parse
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import net_guard  # noqa: E402,F401  — 시험이 운영 서버를 치지 못하게
from test_feedback import NoNetwork  # noqa: E402
from upaper_check import __version__  # noqa: E402
from upaper_check import update_check as uc  # noqa: E402

KO_PAGE = "https://chaekgalpi.co.kr/tools/upaperepub"
EN_PAGE = "https://chaekgalpi.co.kr/en/tools/upaperepub"
TIP_KO = "안 되는 것·불편한 것·바라는 기능을 알려 주세요(브라우저가 열립니다)"
KOREAN = ("ko", "ko-KR", "ko_KR", "KO", "Ko-kr", " ko ", "kor")
ENGLISH = ("en", "ja", "zh", "zh-CN", "zh_CN", "zh-TW", "fr", "de", "EN", "en-US", "ja-JP", "pt-BR", "xx", "kr",
           "english")
MISSING = (None, "", "   ")
URL_KO = "https://chaekgalpi.co.kr/tools/upaperepub?utm_source=app&utm_medium=update"
URL_EN = "https://chaekgalpi.co.kr/en/tools/upaperepub?utm_source=app&utm_medium=update"


def page_of(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


# ------------------------------------------------------------------ c. 언어 규칙
class LanguageRuleTest(unittest.TestCase):
    def setUp(self):
        self.net = NoNetwork().__enter__()
        self.addCleanup(lambda: self.assertEqual(self.net.calls, []))
        self.addCleanup(self.net.__exit__)

    def test_korean_codes_get_the_korean_page(self):
        for lang in KOREAN:
            with self.subTest(lang=lang):
                self.assertTrue(uc.is_korean(lang))
                self.assertEqual(page_of(uc.feedback_url(uc.SLUG, __version__, lang)), KO_PAGE)

    def test_every_other_code_gets_the_english_page(self):
        for lang in ENGLISH:
            with self.subTest(lang=lang):
                self.assertFalse(uc.is_korean(lang))
                self.assertEqual(page_of(uc.feedback_url(uc.SLUG, __version__, lang)), EN_PAGE)

    def test_no_language_is_this_tools_default_korean(self):
        self.assertEqual(uc.DEFAULT_LANG, "ko")
        for lang in MISSING:
            with self.subTest(lang=lang):
                self.assertEqual(page_of(uc.feedback_url(uc.SLUG, __version__, lang)), KO_PAGE)
        with mock.patch.object(uc, "DEFAULT_LANG", "en"):      # 규칙이 정말 기본값을 읽는다
            self.assertEqual(page_of(uc.feedback_url(uc.SLUG, __version__, None)), EN_PAGE)

    def test_default_matches_the_window_language(self):
        from upaper_check import gui
        self.assertEqual(uc.DEFAULT_LANG, gui.UI_LANG)

    def test_every_address_has_the_same_shape(self):
        for lang in KOREAN + ENGLISH + MISSING:
            for version in (__version__, "", None):
                url = uc.feedback_url(uc.SLUG, version, lang)
                with self.subTest(lang=lang, version=version):
                    self.assertTrue(url.startswith("https://chaekgalpi.co.kr/"), url)
                    self.assertTrue(url.endswith("#feedback"), url)
                    q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
                    self.assertEqual(q["utm_source"], ["app"])
                    self.assertEqual(q["utm_medium"], ["feedback"])
                    self.assertEqual(q.get("v"), [version] if version else None)

    def test_update_page_uses_the_same_rule(self):
        info = uc.UpdateInfo("9.9.9", __version__, URL_KO, URL_EN)
        for lang in KOREAN + ENGLISH + MISSING:
            with self.subTest(lang=lang):
                expected = URL_KO if uc.is_korean(lang) else URL_EN
                self.assertEqual(uc.page_for(info, lang), expected)
                self.assertEqual(page_of(uc.page_for(info, lang)),
                                 page_of(uc.feedback_url(uc.SLUG, __version__, lang)))   # 두 링크가 같은 쪽으로

    def test_update_page_without_an_english_page_stays_korean(self):
        for url_en in (None, "", "https://example.com/en/tools/upaperepub"):
            info = uc.UpdateInfo("9.9.9", __version__, URL_KO, url_en)
            for lang in ("en", "ja", "fr"):
                with self.subTest(url_en=url_en, lang=lang):
                    self.assertEqual(uc.page_for(info, lang), URL_KO)

    def test_server_english_page_is_read_only_from_the_site(self):
        base = {"updateAvailable": True, "latest": "9.9.9", "url": URL_KO}
        self.assertEqual(uc.interpret(dict(base, urlEn=URL_EN), __version__).url_en, URL_EN)
        for bad in ("https://evil.example/en", 3, None, ""):
            with self.subTest(bad=bad):
                self.assertIsNone(uc.interpret(dict(base, urlEn=bad), __version__).url_en)
        self.assertIsNone(uc.interpret(base, __version__).url_en)


# ------------------------------------------------------------------ 창
def press(widget, sequence: str) -> str:
    """Tk 가 이 위젯의 sequence 에 묶어 둔 스크립트를, 키가 들어왔을 때처럼 실행한다.
    "break"(Tcl 코드 3)를 돌려주면 그 뒤 클래스 바인딩은 돌지 않는다."""
    script = widget.bind(sequence)
    if not script:
        raise AssertionError(f"{sequence} 에 묶인 것이 없다")
    fields = dict.fromkeys("#bhkstwxyEXYD", "0")
    fields["W"] = str(widget)
    script = re.sub(r"%([#a-zA-Z])", lambda m: fields.get(m.group(1), "??"), script)
    code = widget.tk.eval(f"catch {{{script}}} ::press_result")
    if code not in ("0", "3"):
        raise AssertionError(widget.tk.eval("set ::press_result"))
    return "break" if code == "3" else ""


class WindowCase(unittest.TestCase):
    """창은 클래스에 하나(pytest 에서 Tk 를 시험마다 새로 만들면 가끔 tk.tcl 을 못 찾는다)."""

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
        win.feedback_tip.hide()
        win._hide_update_notice()
        win._show_focus(False)
        win.root.geometry("+120+80")
        self.wait(lambda: abs(win.root.winfo_x() - 120) <= 1)
        self.opened: list = []
        patcher = mock.patch.object(self.gui.webbrowser, "open", side_effect=self._fake_open)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.net = NoNetwork().__enter__()
        self.addCleanup(self.assert_clean)
        self.addCleanup(self.net.__exit__)

    def _fake_open(self, url, *args, **kwargs):
        self.opened.append(url)
        return True

    def assert_clean(self):
        self.assertEqual(self.net.calls, [], "네트워크에 닿았다")
        self.assertFalse(os.path.exists(self.path), "설정 파일을 썼다")

    def wait(self, cond, timeout: float = 3.0) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            self.win.root.update()
            if cond():
                return True
            time.sleep(0.01)
        return False

    @property
    def link(self):
        return self.win.feedback_button

    def url(self, lang="ko"):
        return uc.feedback_url(uc.SLUG, __version__, lang)


# ------------------------------------------------------------------ a. 키보드
class KeyboardTest(WindowCase):
    def test_link_is_a_tab_stop_right_after_the_update_checkbox(self):
        self.win.root.update()
        self.assertIn(str(self.link.cget("takefocus")), ("1", "true", "True"))
        self.assertIs(self.win.chk_update.tk_focusNext(), self.link)     # Tab
        self.assertIs(self.link.tk_focusPrev(), self.win.chk_update)     # Shift+Tab
        self.assertIsNot(self.link.tk_focusNext(), self.link)            # 거기서 다시 Tab 하면 넘어간다

    def test_tab_order_from_the_first_button(self):
        self.win.root.update()
        first = self.win.root.tk_focusNext()                             # 창에서 처음 Tab 이 닿는 곳
        self.assertEqual(first.cget("text"), "파일 선택…")
        seen, w = [], first
        for _ in range(4):
            w = w.tk_focusNext()
            seen.append(w)
        self.assertEqual(seen[1:3], [self.win.chk_update, self.link])
        self.assertNotIn(self.win.open_button, seen[:3])                 # 꺼진 [보고서 열기] 는 건너뛴다
        back, w = [], self.link
        for _ in range(3):
            w = w.tk_focusPrev()
            back.append(w)
        self.assertEqual(back[0], self.win.chk_update)
        self.assertEqual(back[2], first)                                 # Shift+Tab 은 정확히 거꾸로

    def test_enter_and_space_each_open_the_page_exactly_once(self):
        for key in self.gui.FEEDBACK_KEYS:
            with self.subTest(key):
                self.opened.clear()
                self.assertEqual(press(self.link, key), "break")        # Button 기본 Space 가 한 번 더 열지 않게
                self.assertEqual(self.opened, [self.url()])
        self.assertEqual(set(self.gui.FEEDBACK_KEYS), {"<Return>", "<KP_Enter>", "<space>"})

    def test_class_space_binding_is_cut_off(self):
        """break 가 없으면 Tk Button 의 <space> 가 invoke 로 한 번 더 연다 — 그 바인딩이 실제로 있는지."""
        self.assertTrue(self.link.bind_class("Button", "<Key-space>"))
        self.assertEqual(self.link.bindtags()[0], str(self.link))        # 위젯 바인딩이 먼저 돈다

    def test_keys_mouse_and_invoke_together(self):
        for key in ("<Return>", "<space>", "<KP_Enter>"):
            press(self.link, key)
        self.link.invoke()
        self.assertEqual(self.opened, [self.url()] * 4)

    def test_focus_ring_on_and_off_without_changing_size(self):
        win, link = self.win, self.link
        win.root.update_idletasks()
        size = (link.winfo_reqwidth(), link.winfo_reqheight())
        paper, brown = self.gui.COLOR["paper"], self.gui.COLOR["brown"]
        self.assertGreaterEqual(int(link.cget("highlightthickness")), 1)
        self.assertEqual(str(link.cget("highlightbackground")), paper)  # 꺼짐: 바탕색과 같아 안 보인다
        press(link, "<FocusIn>")
        self.assertEqual(str(link.cget("highlightbackground")), brown)  # 켜짐
        self.assertEqual(str(link.cget("highlightcolor")), brown)
        win.root.update_idletasks()
        self.assertEqual((link.winfo_reqwidth(), link.winfo_reqheight()), size)
        press(link, "<FocusOut>")
        self.assertEqual(str(link.cget("highlightbackground")), paper)
        win.root.update_idletasks()
        self.assertEqual((link.winfo_reqwidth(), link.winfo_reqheight()), size)
        self.assertEqual(self.opened, [])                                # 초점만으로는 열지 않는다

    def test_other_keys_do_nothing(self):
        for seq in ("<Key-a>", "<Key-1>", "<Escape>", "<Tab>", "<F1>", "<BackSpace>", "<Delete>", "<Up>"):
            with self.subTest(seq):
                self.assertFalse(self.link.bind(seq))
                self.assertFalse(self.link.bind_class("Button", seq))
        self.assertEqual(self.opened, [])

    def test_keyboard_with_no_browser_writes_the_address(self):
        with mock.patch.object(self.gui.webbrowser, "open", return_value=False):
            press(self.link, "<space>")
        self.assertIn(self.url() + "\n", self.win.log.get("1.0", "end"))
        self.win.log.config(state="normal")
        self.win.log.delete("1.0", "end")
        self.win.log.config(state="disabled")


# ------------------------------------------------------------------ b. 툴팁
class TooltipTest(WindowCase):
    def setUp(self):
        super().setUp()
        self.win.feedback_tip.DELAY_MS = 30        # 인스턴스에만 — 실제 지연 시험은 이것을 지운다
        self.addCleanup(lambda: vars(self.win.feedback_tip).pop("DELAY_MS", None))
        self.addCleanup(self.win.feedback_tip.hide)

    @property
    def tip(self):
        return self.win.feedback_tip

    def hover(self) -> bool:
        self.link.event_generate("<Enter>", x=2, y=2)
        return self.wait(lambda: self.tip.tip is not None and self.tip.tip.winfo_ismapped()
                         and self.tip.tip.winfo_width() > 1 and self.tip.label.winfo_width() > 1)

    def leave(self):
        self.link.event_generate("<Leave>", x=2, y=2)
        self.win.root.update()

    def test_hover_shows_and_leave_hides(self):
        self.assertIsNone(self.tip.tip)
        self.assertTrue(self.hover())
        self.assertEqual(self.tip.label.cget("text"), TIP_KO)
        self.leave()
        self.assertIsNone(self.tip.tip)
        self.assertTrue(self.hover())                                    # 다시 올려도 뜬다
        self.assertEqual(self.opened, [])                                # 올리기만 해서는 열지 않는다

    def test_leaving_before_the_delay_shows_nothing(self):
        self.link.event_generate("<Enter>", x=2, y=2)
        self.leave()
        self.wait(lambda: False, timeout=0.2)
        self.assertIsNone(self.tip.tip)

    def test_real_delay_is_between_400_and_500_ms(self):
        del self.tip.DELAY_MS                                            # 이 시험만 실제 지연으로
        self.assertTrue(400 <= self.tip.DELAY_MS <= 500)
        start = time.time()
        self.link.event_generate("<Enter>", x=2, y=2)
        self.wait(lambda: False, timeout=0.15)
        self.assertIsNone(self.tip.tip)                                  # 아직 안 떴다
        self.assertTrue(self.wait(lambda: self.tip.tip is not None))
        self.assertGreaterEqual(time.time() - start, 0.4)

    def test_click_hides_and_opens_once(self):
        self.assertTrue(self.hover())
        self.link.event_generate("<ButtonPress-1>", x=2, y=2)
        self.win.root.update()
        self.assertIsNone(self.tip.tip)                                  # 누르는 순간 사라진다
        self.link.event_generate("<ButtonRelease-1>", x=2, y=2)
        self.win.root.update()
        self.assertEqual(self.opened, [self.url()])                      # 떼면 한 번 연다
        self.assertTrue(self.hover())
        press(self.link, "<Return>")
        self.assertIsNone(self.tip.tip)
        self.assertEqual(len(self.opened), 2)

    def test_text_is_not_empty_in_any_language(self):
        texts = {lang: t["tip"] for lang, t in self.gui.FEEDBACK_TEXT.items()}
        self.assertEqual(texts["ko"], TIP_KO)
        self.assertTrue(all(t.strip() for t in texts.values()))
        self.assertEqual(len(set(texts.values())), len(texts))
        self.win.lang = "en"
        self.assertTrue(self.hover())
        self.assertEqual(self.tip.label.cget("text"), texts["en"])      # 창의 lang 을 따른다

    def test_note_is_a_borderless_window_below_the_link(self):
        self.assertTrue(self.hover())
        tip = self.tip.tip
        self.assertTrue(tip.wm_overrideredirect())
        self.assertGreaterEqual(tip.winfo_rooty(), self.link.winfo_rooty() + self.link.winfo_height())

    def assert_inside(self, where: str):
        root, tip = self.win.root, self.tip.tip
        tx, ty, tw, th = tip.winfo_rootx(), tip.winfo_rooty(), tip.winfo_width(), tip.winfo_height()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        self.assertGreaterEqual(tx, 0, where)
        self.assertLessEqual(tx + tw, sw, where)
        self.assertGreaterEqual(ty, 0, where)
        self.assertLessEqual(ty + th, sh, where)
        left, right = max(root.winfo_rootx(), 0), min(root.winfo_rootx() + root.winfo_width(), sw)
        if right - left >= tw:                                           # 창이 화면에 다 보이면 창 안에도
            self.assertGreaterEqual(tx, left, where)
            self.assertLessEqual(tx + tw, right, where)

    def test_stays_inside_window_and_screen_at_every_edge(self):
        root = self.win.root
        root.update()
        sw, sh, w = root.winfo_screenwidth(), root.winfo_screenheight(), root.winfo_width()
        places = {"왼쪽 끝": (0, 80), "오른쪽 끝": (sw - w, 80), "왼쪽 밖": (-300, 80),
                  "오른쪽 밖": (sw - 200, 80), "아래 끝": (120, sh - 230)}
        for where, (x, y) in places.items():
            with self.subTest(where):
                self.tip.hide()
                root.geometry(f"+{x}+{y}")
                self.assertTrue(self.wait(lambda: abs(root.winfo_x() - x) <= 1), where)
                self.assertTrue(self.hover(), where)
                self.assert_inside(where)

    def test_destroying_the_link_takes_the_note_with_it(self):
        """링크가 사라지면 설명도 — 다른 시험이 같은 창을 쓰므로 가짜 위젯으로 본다."""
        widget = self.gui.tk.Label(self.win.root, text="x")
        widget.pack()
        tip = self.gui.Tooltip(widget, lambda: "설명")
        tip.show()
        shown = tip.tip
        self.assertTrue(shown.winfo_exists())
        widget.destroy()
        self.win.root.update()
        self.assertIsNone(tip.tip)
        self.assertFalse(shown.winfo_exists())


# ------------------------------------------------------------------ 새 버전 알림과 공존
class UpdatePageTest(WindowCase):
    def test_update_button_follows_the_window_language(self):
        info = uc.UpdateInfo("9.9.9", __version__, URL_KO, URL_EN)
        for lang, expected in (("ko", URL_KO), (None, URL_KO), ("en", URL_EN), ("zh-TW", URL_EN)):
            with self.subTest(lang=lang):
                self.opened.clear()
                self.win.lang = lang
                self.win._on_update_result(info, answered=False)
                self.assertTrue(self.win.frm_update.winfo_manager())
                self.win._update_open()
                self.assertEqual(self.opened, [expected])

    def test_keyboard_link_leaves_the_notice_alone(self):
        info = uc.UpdateInfo("9.9.9", __version__, URL_KO)
        self.win._on_update_result(info, answered=False)
        press(self.link, "<Return>")
        self.assertTrue(self.win.frm_update.winfo_manager())
        self.win._update_open()
        self.assertEqual(self.opened, [self.url(), URL_KO])


if __name__ == "__main__":
    unittest.main()
