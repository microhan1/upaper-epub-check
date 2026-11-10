# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 레시피 — 단일 EXE(유페이퍼EPUB검수.exe).

    python -m PyInstaller --noconfirm upaper_check.spec

default_rules.json 은 코드가 Path(__file__).with_name() 으로 읽으므로
번들 안에서도 upaper_check/ 폴더 밑에 같은 이름으로 실어 보낸다.

시작 그림(assets/splash.png, 만드는 법은 assets/make_splash.py): onefile exe 는 켜질 때 압축을 푸느라 몇 초 동안
아무것도 안 보이므로, 그동안 작은 그림을 띄운다. 그림은 Tcl/Tk 만 먼저 풀어 파이썬이 시작되기 전에 뜨고,
창이 다 그려지면 코드(upaper_check/splash.py)가 닫는다.
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
splash = Splash(
    os.path.join(ROOT, "assets", "splash.png"),
    binaries=a.binaries,
    datas=a.datas,
    text_pos=None,        # 그림에 적힌 글자만 보이고, 푸는 진행 문구는 안 쓴다
    minify_script=True,
    always_on_top=True,
)
exe = EXE(
    pyz, a.scripts, splash, splash.binaries, a.binaries, a.datas, [],
    name="유페이퍼EPUB검수",
    console=False,   # 창 모드: 더블클릭 시 검은 콘솔 없이 GUI 만. 아이콘 위 드롭은 보고서를 브라우저로 연다.
    upx=False,
    icon=None,
)
