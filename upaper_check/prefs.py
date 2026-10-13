"""창의 설정 — 프로그램 옆 settings.json (책갈피 툴 공통 방식).

EXE 로 실행하면 EXE 가 있는 폴더, 소스로 실행하면 저장소 폴더에 둔다. 누구나 고칠 수 있는
파일이라 읽을 때 형식을 검사하고, 어긋난 값은 기본값으로 되돌린다. 저장할 때는 이 모듈이
모르는 키도 지우지 않는다(다른 판이 쓴 설정을 보존).
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys

SETTINGS_NAME = "settings.json"
MAX_DAY_LEN = 10        # YYYY-MM-DD
MAX_VERSION_LEN = 32


def app_dir() -> str:
    """settings.json 이 놓이는 폴더 — EXE 옆, 소스 실행이면 저장소 폴더."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def settings_path() -> str:
    return os.path.join(app_dir(), SETTINGS_NAME)


@dataclasses.dataclass
class Prefs:
    update_check: bool = True          # 하루 한 번 책갈피 툴 사이트에 새 버전을 묻는다
    update_check_last: str = ""        # 서버가 마지막으로 답한 날(YYYY-MM-DD)
    update_check_skipped: str = ""     # [다음에] 를 누른 버전 — 그 버전은 다시 알리지 않는다


def _read(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load(path: str | None = None) -> Prefs:
    data = _read(path or settings_path())
    defaults = Prefs()

    def typed(key: str, kind: type):
        value = data.get(key, getattr(defaults, key))
        return value if isinstance(value, kind) else getattr(defaults, key)

    return Prefs(update_check=typed("update_check", bool),
                 update_check_last=typed("update_check_last", str).strip()[:MAX_DAY_LEN],
                 update_check_skipped=typed("update_check_skipped", str).strip()[:MAX_VERSION_LEN])


def save(prefs: Prefs, path: str | None = None) -> None:
    """실패해도 조용히 넘어간다 — 읽기 전용 폴더에서 실행해도 검사는 계속돼야 한다."""
    target = path or settings_path()
    data = _read(target)
    data.update(dataclasses.asdict(prefs))
    try:
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass
