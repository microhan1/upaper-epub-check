"""끌어다 놓기 창 — 인자 없이 실행(EXE 더블클릭)했을 때 뜬다.

창 안으로 EPUB 을 떨어뜨리거나 [파일 선택] 으로 고르면 검사하고, 결과 요약을 창에 적은 뒤
HTML 보고서를 브라우저로 연다. 드롭 기능은 tkinterdnd2 가 있을 때만 켜지고, 없으면 파일 선택만 된다.
"""
from __future__ import annotations

import os
import webbrowser
from typing import Callable

import tkinter as tk
from tkinter import filedialog, scrolledtext

from upaper_check import __version__ as APP_VERSION
from upaper_check import prefs as prefs_mod
from upaper_check import update_check

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:  # pragma: no cover - 배포본에는 항상 포함
    DND_AVAILABLE = False

FILE_TYPES = [("EPUB 파일", "*.epub"), ("모든 파일", "*.*")]
TITLE = "유페이퍼 EPUB 검수"
WINDOW_SIZE = "640x640"   # 선택 줄·새 버전 알림 줄이 생겨도 기록 칸이 여섯 줄 넘게 남도록
EPUB_SUFFIX = ".epub"
COLOR = {"paper": "#FAF6EF", "ink": "#2C2822", "brown": "#6B4F3B", "gold": "#C9A66B",
         "red": "#8E2B2B", "green": "#2F5D2A", "muted": "#6B6257", "zone": "#F5F1E8"}
FONT_BODY = ("Malgun Gothic", 10)
FONT_ZONE = ("Malgun Gothic", 13, "bold")
FONT_TITLE = ("Malgun Gothic", 14, "bold")
FONT_LINK = ("Malgun Gothic", 10, "underline")

TIP_BG = "#FFFFE1"
UI_LANG = "ko"   # 창은 한국어 전용 — 「의견 보내기」 문구만 책갈피 툴 공통 4개 언어를 갖춰 둔다
FEEDBACK_TEXT = {
    "ko": {"label": "의견 보내기",
           "tip": "안 되는 것·불편한 것·바라는 기능을 알려 주세요(브라우저가 열립니다)",
           "failed": "브라우저를 열지 못했습니다. 아래 주소를 복사해 브라우저 주소창에 붙여 넣어 주세요:"},
    "en": {"label": "Send feedback",
           "tip": "Tell us what's broken or missing (opens your browser)",
           "failed": "Couldn't open your browser. Copy this address into your browser's address bar:"},
    "ja": {"label": "ご意見を送る",
           "tip": "不具合・ご要望をお知らせください（ブラウザが開きます）",
           "failed": "ブラウザを開けませんでした。次のアドレスをコピーしてブラウザのアドレス欄に貼り付けてください："},
    "zh-CN": {"label": "发送反馈",
              "tip": "告诉我们问题或建议（将打开浏览器）",
              "failed": "无法打开浏览器。请复制以下地址并粘贴到浏览器地址栏："},
}
FEEDBACK_KEYS = ("<Return>", "<KP_Enter>", "<space>")   # 링크에 초점이 있을 때 누르면 여는 키

# check_fn(epub_path) -> (요약 한 줄, 보고서 경로, 오류 없음 여부)
CheckFn = Callable[[str], tuple[str, str, bool]]


class Tooltip:
    """마우스를 올린 위젯 아래 작은 설명(표준 tkinter 만). 문구는 보일 때마다 text_fn 으로 읽는다."""

    DELAY_MS = 450
    WRAP = 320
    GAP = 4

    def __init__(self, widget: tk.Misc, text_fn: Callable[[], str]) -> None:
        self.widget, self.text_fn = widget, text_fn
        self.tip: tk.Toplevel | None = None
        self.label: tk.Label | None = None
        self._job: str | None = None
        widget.bind("<Enter>", lambda _e: self._schedule(), add="+")
        for seq in ("<Leave>", "<ButtonPress>", "<Destroy>"):
            widget.bind(seq, lambda _e: self.hide(), add="+")

    def _schedule(self) -> None:
        self._cancel()
        self._job = self.widget.after(self.DELAY_MS, self.show)

    def _cancel(self) -> None:
        if self._job is None:
            return
        try:
            self.widget.after_cancel(self._job)
        except tk.TclError:
            pass
        self._job = None

    def show(self) -> None:
        self._job = None
        if self.tip is None:
            self.tip = tk.Toplevel(self.widget)
            self.tip.wm_overrideredirect(True)
            self.tip.wm_attributes("-topmost", True)
            self.label = tk.Label(self.tip, justify="left", bg=TIP_BG, fg=COLOR["ink"], font=FONT_BODY,
                                  relief="solid", bd=1, padx=6, pady=3, wraplength=self.WRAP)
            self.label.pack()
        self.label.configure(text=self.text_fn())
        self.place()

    def place(self) -> None:
        """링크 오른쪽 끝 아래에 맞춘 뒤 창 안, 다시 화면 안으로 당긴다 — 창을 화면 끝에 붙여도 잘리지 않게."""
        w, tip = self.widget, self.tip
        tip.update_idletasks()
        tw, th = tip.winfo_reqwidth(), tip.winfo_reqheight()
        x = w.winfo_rootx() + w.winfo_width() - tw
        y = w.winfo_rooty() + w.winfo_height() + self.GAP
        top = w.winfo_toplevel()
        left, right = top.winfo_rootx(), top.winfo_rootx() + top.winfo_width()
        if tw <= right - left:
            x = min(max(x, left), right - tw)
        x = min(max(x, 0), w.winfo_screenwidth() - tw)
        y = min(max(y, 0), w.winfo_screenheight() - th)
        tip.wm_geometry(f"+{x}+{y}")

    def hide(self) -> None:
        self._cancel()
        tip, self.tip, self.label = self.tip, None, None
        if tip is None:
            return
        try:
            tip.destroy()
        except tk.TclError:
            pass


class DropWindow:
    def __init__(self, check_fn: CheckFn, *, prefs_path: str | None = None, check_updates: bool = True,
                 fetcher: Callable | None = None):
        """prefs_path·fetcher 는 시험용 — 사용자 설정 파일과 실제 서버를 건드리지 않고 돌리기 위해."""
        self.check_fn = check_fn
        self.prefs_path = prefs_path
        self.prefs = prefs_mod.load(prefs_path)
        self.root = TkinterDnD.Tk() if DND_AVAILABLE else tk.Tk()
        self.root.title(TITLE)
        self.root.geometry(WINDOW_SIZE)
        self.root.configure(bg=COLOR["paper"])
        self.auto_open = tk.BooleanVar(value=True)
        self.var_update_check = tk.BooleanVar(value=self.prefs.update_check)
        self.last_report = ""
        self.lang = UI_LANG
        self._closing = False
        self._update_info: update_check.UpdateInfo | None = None
        self.root.protocol("WM_DELETE_WINDOW", self.destroy)   # X 버튼도 같은 정리 경로로
        self._build()
        if DND_AVAILABLE:
            self._enable_drop()
        if check_updates:
            update_check.check_async(self.root, update_check.SLUG, APP_VERSION, self.prefs,
                                     self._on_update_result, fetcher=fetcher or update_check.fetch)

    # ---------- 화면 구성 ----------
    def _build(self) -> None:
        tk.Label(self.root, text="유페이퍼 EPUB 검수", font=FONT_TITLE, fg=COLOR["brown"],
                 bg=COLOR["paper"]).pack(pady=(14, 2))
        tk.Label(self.root, text="업로드 전에 표지·판권·출판사명·EPUB 버전·금지 태그를 검사합니다.",
                 font=FONT_BODY, fg=COLOR["muted"], bg=COLOR["paper"]).pack()
        self.zone = tk.Label(self.root, text=self._zone_text(), font=FONT_ZONE, fg=COLOR["brown"],
                             bg=COLOR["zone"], relief="ridge", bd=2, height=5, cursor="hand2")
        self.zone.pack(fill="x", padx=20, pady=14)
        self.zone.bind("<Button-1>", lambda _e: self.pick_files())
        self._build_buttons()
        self.log = scrolledtext.ScrolledText(self.root, height=12, font=FONT_BODY, bg="white",
                                             fg=COLOR["ink"], wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, padx=20, pady=(0, 14))
        self.log.tag_config("pass", foreground=COLOR["green"])
        self.log.tag_config("fail", foreground=COLOR["red"])
        self.log.tag_config("muted", foreground=COLOR["muted"])
        self._build_update_notice()

    def _build_update_notice(self) -> None:
        """창 아래 한 줄 알림(모달 아님). 처음에는 숨겨 두고, 새 버전이 있을 때만 기록 칸 아래에 끼운다."""
        self.frm_update = tk.Frame(self.root, bg=COLOR["zone"], bd=1, relief="solid")
        self.lbl_update = tk.Label(self.frm_update, text="", font=FONT_BODY, fg=COLOR["brown"], bg=COLOR["zone"])
        self.lbl_update.pack(side="left", padx=(10, 6), pady=6)
        tk.Button(self.frm_update, text="다음에", command=self._update_later, font=FONT_BODY,
                  relief="flat", padx=10).pack(side="right", padx=(4, 8), pady=4)
        tk.Button(self.frm_update, text="업데이트", command=self._update_open, font=FONT_BODY,
                  bg=COLOR["brown"], fg="white", relief="flat", padx=10).pack(side="right", pady=4)

    def _build_buttons(self) -> None:
        bar = tk.Frame(self.root, bg=COLOR["paper"])
        bar.pack(fill="x", padx=20, pady=(0, 8))
        tk.Button(bar, text="파일 선택…", command=self.pick_files, font=FONT_BODY,
                  bg=COLOR["brown"], fg="white", relief="flat", padx=12).pack(side="left")
        self.open_button = tk.Button(bar, text="보고서 열기", command=self.open_last_report, font=FONT_BODY,
                                     state="disabled", relief="flat", padx=12)
        self.open_button.pack(side="left", padx=8)
        # 선택 항목은 버튼 아래 줄에 — 한 줄에 몰면 기본 창 너비(640)에서 글자가 잘린다
        opts = tk.Frame(self.root, bg=COLOR["paper"])
        opts.pack(fill="x", padx=16, pady=(0, 6))
        tk.Checkbutton(opts, text="검사 후 보고서 자동 열기", variable=self.auto_open, font=FONT_BODY,
                       bg=COLOR["paper"], activebackground=COLOR["paper"]).pack(side="left")
        self.chk_update = tk.Checkbutton(opts, text="새 버전 확인", variable=self.var_update_check,
                                         command=self._on_update_toggle, font=FONT_BODY, bg=COLOR["paper"],
                                         activebackground=COLOR["paper"])
        self.chk_update.pack(side="left", padx=(12, 0))
        self._build_feedback_link(opts)

    def _build_feedback_link(self, parent: tk.Misc) -> None:
        """「새 버전 확인」 다음 Tab 자리. Enter·Space 로 열고, 초점이 있는 동안 갈색 테두리를 그린다
        (테두리 칸은 늘 있고 색만 바뀌어 크기가 그대로다)."""
        link = tk.Button(parent, text=self._text("label"), command=self.send_feedback, font=FONT_LINK,
                         fg=COLOR["brown"], bg=COLOR["paper"], activebackground=COLOR["paper"],
                         activeforeground=COLOR["brown"], relief="flat", bd=0, cursor="hand2", takefocus=True,
                         highlightthickness=1, highlightbackground=COLOR["paper"], highlightcolor=COLOR["paper"])
        link.pack(side="right", padx=(0, 4))
        for seq in FEEDBACK_KEYS:   # break: Button 기본 Space 바인딩이 한 번 더 열지 않게
            link.bind(seq, lambda _e: (self.send_feedback(), "break")[1])
        link.bind("<FocusIn>", lambda _e: self._show_focus(True))
        link.bind("<FocusOut>", lambda _e: self._show_focus(False))
        self.feedback_button = link
        self.feedback_tip = Tooltip(link, lambda: self._text("tip"))

    def _show_focus(self, focused: bool) -> None:
        color = COLOR["brown"] if focused else COLOR["paper"]
        self.feedback_button.configure(highlightbackground=color, highlightcolor=color)

    @staticmethod
    def _zone_text() -> str:
        if DND_AVAILABLE:
            return "여기에 EPUB 파일을 끌어다 놓으세요\n(여러 개 가능 · 클릭하면 파일 선택)"
        return "클릭해서 EPUB 파일을 선택하세요\n(끌어다 놓기 모듈이 없어 드롭은 꺼져 있습니다)"

    def _enable_drop(self) -> None:
        for widget in (self.root, self.zone, self.log):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)

    # ---------- 동작 ----------
    def _on_drop(self, event) -> None:
        paths = self.root.tk.splitlist(event.data)
        self.run_files(paths)

    def pick_files(self) -> None:
        paths = filedialog.askopenfilenames(title="검사할 EPUB 파일", filetypes=FILE_TYPES)
        if paths:
            self.run_files(paths)

    def run_files(self, paths) -> None:
        for path in paths:
            self._run_one(os.path.normpath(path))

    def _run_one(self, path: str) -> None:
        name = os.path.basename(path)
        if not path.lower().endswith(EPUB_SUFFIX):
            self._append(f"건너뜀: {name} — EPUB 파일이 아닙니다.\n", "muted")
            return
        self._append(f"검사 중: {name}\n", "muted")
        self.root.update_idletasks()
        try:
            summary, report_path, passed = self.check_fn(path)
        except Exception as exc:  # 어떤 EPUB 이든 창이 죽지 않게
            self._append(f"실패: {name} — {exc}\n\n", "fail")
            return
        self._append(f"{summary}\n보고서: {report_path}\n\n", "pass" if passed else "fail")
        self.last_report = report_path
        self.open_button.config(state="normal")
        if self.auto_open.get():
            open_report(report_path)

    def open_last_report(self) -> None:
        open_report(self.last_report)

    def _text(self, key: str) -> str:
        return FEEDBACK_TEXT.get(self.lang, FEEDBACK_TEXT[UI_LANG])[key]

    def send_feedback(self) -> None:
        """책갈피 툴 페이지의 의견 칸을 브라우저로 연다 — 프로그램은 서버에 아무것도 보내지 않는다.
        브라우저를 못 열면 주소를 기록 칸에 적어 복사할 수 있게 한다."""
        self.feedback_tip.hide()   # 브라우저 위에 설명이 남지 않게
        url = update_check.feedback_url(update_check.SLUG, APP_VERSION, self.lang)
        try:
            opened = webbrowser.open(url)
        except Exception:  # webbrowser.Error·OSError 등 — 창은 그대로 둔다
            opened = False
        if not opened:
            self._append(f"{self._text('failed')}\n{url}\n\n", "muted")

    def _append(self, text: str, tag: str) -> None:
        self.log.config(state="normal")
        self.log.insert("end", text, tag)
        self.log.see("end")
        self.log.config(state="disabled")

    # ---------- 새 버전 알림 ----------
    def _save_prefs(self) -> None:
        self.prefs.update_check = bool(self.var_update_check.get())
        prefs_mod.save(self.prefs, self.prefs_path)

    def _on_update_result(self, info: update_check.UpdateInfo | None, answered: bool) -> None:
        """Tk 스레드. 서버가 답했을 때만 날짜를 기록 — 오프라인이었으면 다음 실행 때 다시 묻는다."""
        if self._closing:
            return
        if answered:
            self.prefs.update_check_last = update_check.today()
            self._save_prefs()
        if info is not None and self.var_update_check.get():
            self._update_info = info
            self._show_update_notice()

    def _show_update_notice(self) -> None:
        info = self._update_info
        if info is None:
            return
        self.lbl_update.configure(text=f"새 버전이 나왔습니다: {info.latest} (현재 {info.current})")
        if not self.frm_update.winfo_manager():
            # 기록 칸보다 먼저 자리를 잡아야 보인다(기록 칸이 남은 공간을 다 차지하므로)
            self.frm_update.pack(fill="x", padx=20, pady=(0, 12), side="bottom", before=self.log)

    def _hide_update_notice(self) -> None:
        self._update_info = None
        self.frm_update.pack_forget()

    def _update_open(self) -> None:
        """다운로드가 아니라 책갈피 툴 페이지를 연다 — 내려받기는 그 페이지가 맡는다."""
        info = self._update_info
        page = update_check.page_for(info, self.lang) if info is not None else ""
        if page.startswith(update_check.SITE):
            try:
                webbrowser.open(page)
            except Exception:
                pass
        self._hide_update_notice()

    def _update_later(self) -> None:
        if self._update_info is not None:
            self.prefs.update_check_skipped = self._update_info.latest   # 더 새 판이 나오면 다시 알린다
            self._save_prefs()
        self._hide_update_notice()

    def _on_update_toggle(self) -> None:
        self._save_prefs()
        if not self.var_update_check.get():
            self._hide_update_notice()

    def mainloop(self) -> None:
        self.root.mainloop()

    def destroy(self) -> None:
        """남은 after 예약(새 버전 확인의 0.1초 확인 등)을 지우고 닫는다 — 닫힌 창의 예약이 남아
        있으면 Tk 가 '없는 명령'이라고 오류를 낸다."""
        if self._closing:
            return
        self._closing = True
        try:
            for pending in self.root.tk.splitlist(self.root.tk.call("after", "info")):
                self.root.after_cancel(pending)
        except tk.TclError:
            pass
        self.root.destroy()


def open_report(path: str) -> None:
    if path and os.path.isfile(path):
        webbrowser.open(f"file:///{os.path.abspath(path)}")


def show_message(text: str) -> None:
    """콘솔이 없는 창 모드에서 오류를 알릴 때."""
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(TITLE, text)
    root.destroy()


def run_window(check_fn: CheckFn) -> None:
    DropWindow(check_fn).mainloop()


def selftest() -> str:
    """창을 만들었다 바로 닫고 드롭 기능 가용 여부를 돌려준다 (배포본 점검용).
    새 버전 확인은 하지 않는다 — 점검이 서버에 묻거나 설정 파일을 쓰면 안 된다."""
    window = DropWindow(lambda _p: ("", "", True), check_updates=False)
    window.destroy()
    return "dnd:available" if DND_AVAILABLE else "dnd:unavailable"
