"""exe 시작 그림(PyInstaller --splash) 닫기.

exe 는 켜자마자 압축을 푸는 동안 assets/splash.png 를 보여 준다(upaper_check.spec 의 Splash). 그림은 파이썬이
시작되기 전에 뜨므로 코드는 닫기만 한다 — 창이 다 그려진 뒤, 또는 창 없이 검사하는 길(아이콘 위 끌어놓기·명령줄)에
들어서자마자. 파이썬으로 바로 돌릴 때는 pyi_splash 모듈이 없어 아무 일도 하지 않는다.
"""
from __future__ import annotations


def close() -> None:
    try:
        import pyi_splash
        pyi_splash.close()
    except Exception:   # 모듈 없음(소스 실행)·이미 닫힘·Tcl 오류 — 어느 쪽이든 프로그램은 계속 간다
        pass
