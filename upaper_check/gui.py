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

# check_fn(epub_path) -> (요약 한 줄, 보고서 경로, 오류 없음 여부)
CheckFn = Callable[[str], tuple[str, str, bool]]


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
        self._closing = False
        self._update_info: update_check.UpdateInfo | None = None
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
        tk.Checkbutton(opts, text="새 버전 확인", variable=self.var_update_check, command=self._on_update_toggle,
                       font=FONT_BODY, bg=COLOR["paper"], activebackground=COLOR["paper"]).pack(side="left", padx=(12, 0))

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
        self.lbl_update.configure(text=f"새 버전 {info.latest}이 있습니다 (현재 {info.current})")
        if not self.frm_update.winfo_manager():
            # 기록 칸보다 먼저 자리를 잡아야 보인다(기록 칸이 남은 공간을 다 차지하므로)
            self.frm_update.pack(fill="x", padx=20, pady=(0, 12), side="bottom", before=self.log)

    def _hide_update_notice(self) -> None:
        self._update_info = None
        self.frm_update.pack_forget()

    def _update_open(self) -> None:
        """다운로드가 아니라 책갈피 툴 페이지를 연다 — 내려받기는 그 페이지가 맡는다."""
        info = self._update_info
        if info is not None and info.url.startswith(update_check.SITE):
            try:
                webbrowser.open(info.url)
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
        self._closing = True
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
