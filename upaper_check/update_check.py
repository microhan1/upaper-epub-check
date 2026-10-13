"""창을 연 뒤 하루 한 번: 책갈피 툴 사이트에 더 새 버전이 있는지 묻는다.

보내는 것은 도구 이름(slug)·버전·"win" 뿐이다 — EPUB 파일·경로·기기·사용자 정보는 보내지 않는다.
창이 뜨고 1.5초 뒤 백그라운드 스레드에서 한 번 묻고, 화면을 막지 않는다. 오프라인·시간 초과·
HTTP 오류·이상한 JSON 은 모두 조용히 넘어간다. 더 새 버전인지는 서버가 정한다(`updateAvailable`).
null 은 '비교할 수 없음'이라 아무것도 보여 주지 않는다. 표준 라이브러리만 쓴다.
(참고 구현: 책갈피 툴 music-tag-filler 의 update_check.py — 같은 구조·같은 규칙)
"""
from __future__ import annotations

import dataclasses
import datetime
import json
import threading
import urllib.parse
import urllib.request
from typing import Callable

API = "https://chaekgalpi.co.kr/api/tools/{slug}/latest"
SITE = "https://chaekgalpi.co.kr/"  # 알림은 이 사이트의 페이지만 연다
SLUG = "upaperepub"
TIMEOUT = 4.0
DELAY_MS = 1500
MAX_BYTES = 64 * 1024
MAX_VERSION_LEN = 32


@dataclasses.dataclass
class UpdateInfo:
    latest: str
    current: str
    url: str


def today() -> str:
    return datetime.date.today().isoformat()


def should_check(prefs, day: str) -> bool:
    """확인이 켜져 있고 오늘 아직 서버 답을 받지 않았다."""
    return bool(getattr(prefs, "update_check", True)) and getattr(prefs, "update_check_last", "") != day


def fetch(slug: str, version: str, *, opener: Callable = urllib.request.urlopen) -> dict | None:
    """서버의 답, 실패하면 None."""
    query = urllib.parse.urlencode({"v": version, "os": "win"})
    req = urllib.request.Request(f"{API.format(slug=slug)}?{query}",
                                 headers={"User-Agent": f"chaekgalpi-tool/{slug}/{version}",
                                          "Accept": "application/json"})
    try:
        with opener(req, timeout=TIMEOUT) as resp:
            if getattr(resp, "status", 200) != 200:
                return None
            data = json.loads(resp.read(MAX_BYTES).decode("utf-8"))
    except Exception:  # 오프라인·시간 초과·HTTP 오류·이상한 JSON: 아무 말도 하지 않는다
        return None
    return data if isinstance(data, dict) else None


def interpret(data: dict | None, version: str, skipped: str = "") -> UpdateInfo | None:
    """서버가 더 새 버전이 있다고 했고, 사용자가 [다음에] 로 넘긴 버전이 아니며,
    링크가 책갈피 툴 사이트를 가리킬 때만 UpdateInfo."""
    if not isinstance(data, dict) or data.get("updateAvailable") is not True:
        return None
    latest, url = data.get("latest"), data.get("url")
    if not isinstance(latest, str) or not latest.strip() or len(latest) > MAX_VERSION_LEN:
        return None
    if not isinstance(url, str) or not url.startswith(SITE):
        return None
    latest = latest.strip()
    if latest == (skipped or "").strip():
        return None
    return UpdateInfo(latest, version, url)


def check_async(root, slug: str, version: str, prefs, on_result: Callable[[UpdateInfo | None, bool], None], *,
                fetcher: Callable = fetch, day: str | None = None) -> bool:
    """지금부터 DELAY_MS 뒤 한 번 확인하도록 예약한다. on_result(info, answered) 는 Tk 스레드에서
    돈다: 서버가 답했으면 answered=True(호출한 쪽이 그때 날짜를 기록), 알림을 띄울 때만 info 가 있다.
    확인할 차례가 아니면 False."""
    if not should_check(prefs, day or today()):
        return False
    skipped = getattr(prefs, "update_check_skipped", "")

    def work() -> None:
        data = fetcher(slug, version)
        info = interpret(data, version, skipped)
        try:
            root.after(0, lambda: on_result(info, data is not None))
        except Exception:  # 그사이 창이 닫혔다
            pass

    def start() -> None:
        threading.Thread(target=work, name="update-check", daemon=True).start()

    try:
        root.after(DELAY_MS, start)
    except Exception:
        return False
    return True
