# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 레시피 — 단일 EXE(유페이퍼EPUB검수.exe).

    python -m PyInstaller --noconfirm upaper_check.spec

default_rules.json 은 코드가 Path(__file__).with_name() 으로 읽으므로
번들 안에서도 upaper_check/ 폴더 밑에 같은 이름으로 실어 보낸다.
"""
import os

from PyInstaller.utils.hooks import collect_data_files

ROOT = os.path.abspath(os.getcwd())

# tkinterdnd2 는 플랫폼별 tkdnd 바이너리를 폴더째 들고 있다 — Windows 64bit 것만 싣는다 (Tcl 8.6 / 9 둘 다).
dnd_datas = [(src, dst) for src, dst in collect_data_files("tkinterdnd2")
             if "win-x64" in src.replace("\\", "/")]

a = Analysis(
    [os.path.join(ROOT, "upaper_check.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "upaper_check", "default_rules.json"), "upaper_check")] + dnd_datas,
    hiddenimports=["PIL._tkinter_finder", "tkinter", "tkinter.filedialog", "tkinter.scrolledtext", "tkinterdnd2"],
    excludes=["matplotlib", "numpy", "scipy", "pandas", "IPython", "jupyter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="유페이퍼EPUB검수",
    console=False,   # 창 모드: 더블클릭 시 검은 콘솔 없이 GUI 만. 아이콘 위 드롭은 보고서를 브라우저로 연다.
    upx=False,
    icon=None,
)
