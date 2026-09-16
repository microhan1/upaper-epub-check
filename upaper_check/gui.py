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

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:  # pragma: no cover - 배포본에는 항상 포함
    DND_AVAILABLE = False

FILE_TYPES = [("EPUB 파일", "*.epub"), ("모든 파일", "*.*")]
TITLE = "유페이퍼 EPUB 검수"
WINDOW_SIZE = "640x560"
EPUB_SUFFIX = ".epub"
COLOR = {"paper": "#FAF6EF", "ink": "#2C2822", "brown": "#6B4F3B", "gold": "#C9A66B",
         "red": "#8E2B2B", "green": "#2F5D2A", "muted": "#6B6257", "zone": "#F5F1E8"}
FONT_BODY = ("Malgun Gothic", 10)
FONT_ZONE = ("Malgun Gothic", 13, "bold")
FONT_TITLE = ("Malgun Gothic", 14, "bold")

# check_fn(epub_path) -> (요약 한 줄, 보고서 경로, 오류 없음 여부)
CheckFn = Callable[[str], tuple[str, str, bool]]


class DropWindow:
    def __init__(self, check_fn: CheckFn):
        self.check_fn = check_fn
        self.root = TkinterDnD.Tk() if DND_AVAILABLE else tk.Tk()
        self.root.title(TITLE)
        self.root.geometry(WINDOW_SIZE)
        self.root.configure(bg=COLOR["paper"])
        self.auto_open = tk.BooleanVar(value=True)
        self.last_report = ""
        self._build()
        if DND_AVAILABLE:
            self._enable_drop()

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

    def _build_buttons(self) -> None:
        bar = tk.Frame(self.root, bg=COLOR["paper"])
        bar.pack(fill="x", padx=20, pady=(0, 8))
        tk.Button(bar, text="파일 선택…", command=self.pick_files, font=FONT_BODY,
                  bg=COLOR["brown"], fg="white", relief="flat", padx=12).pack(side="left")
        self.open_button = tk.Button(bar, text="보고서 열기", command=self.open_last_report, font=FONT_BODY,
                                     state="disabled", relief="flat", padx=12)
        self.open_button.pack(side="left", padx=8)
        tk.Checkbutton(bar, text="검사 후 보고서 자동 열기", variable=self.auto_open, font=FONT_BODY,
                       bg=COLOR["paper"], activebackground=COLOR["paper"]).pack(side="right")

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

    def mainloop(self) -> None:
        self.root.mainloop()

    def destroy(self) -> None:
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
    """창을 만들었다 바로 닫고 드롭 기능 가용 여부를 돌려준다 (배포본 점검용)."""
    window = DropWindow(lambda _p: ("", "", True))
    window.destroy()
    return "dnd:available" if DND_AVAILABLE else "dnd:unavailable"
