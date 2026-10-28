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
POLL_MS = 100                        # Tk 스레드가 서버 답이 왔는지 보는 간격
MAX_BYTES = 64 * 1024
MAX_VERSION_LEN = 32

# 「의견 보내기」: 툴 페이지의 의견 칸(#feedback)을 브라우저로 열기만 한다 — 프로그램은 서버에 요청하지 않는다.
# 주소는 이 상수로만 조립한다(설정·서버 응답에서 받지 않는다). utm_source=app 이라야 관리자 화면에 프로그램으로 찍힌다.
FEEDBACK_PAGE_KO = SITE + "tools/{slug}"
FEEDBACK_PAGE_EN = SITE + "en/tools/{slug}"      # 일본어·중국어 페이지는 없어 영어 페이지로
FEEDBACK_QUERY = "utm_source=app&utm_medium=feedback"
FEEDBACK_ANCHOR = "#feedback"
DEFAULT_LANG = "ko"                               # 언어를 모를 때 = 이 툴의 화면 언어(한국어 전용)
KOREAN_PREFIX = "ko"


@dataclasses.dataclass
class UpdateInfo:
    latest: str
    current: str
    url: str
    url_en: str | None = None                     # 서버가 영어 페이지를 따로 줄 때(urlEn)


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


def is_korean(lang: str | None) -> bool:
    """화면 언어가 받을 페이지 — 책갈피 툴 공통 규칙. 첫 부분이 ko(ko·ko-KR)면 한국어 페이지,
    그 밖의 모든 코드(en·ja·zh-CN·zh-TW·fr·모르는 코드)는 영어 페이지. None·빈 값은 이 툴의 기본(한국어)."""
    code = (lang or "").strip() or DEFAULT_LANG
    return code.lower().startswith(KOREAN_PREFIX)


def page_for(info: UpdateInfo, lang: str | None) -> str:
    """[업데이트] 가 열 페이지: 한국어 화면은 url, 그 밖은 서버가 사이트 안의 영어 페이지를 줬을 때 그 페이지."""
    if not is_korean(lang) and info.url_en and info.url_en.startswith(SITE):
        return info.url_en
    return info.url


def feedback_url(slug: str, version: str | None, lang: str | None) -> str:
    """의견 칸 주소. 페이지는 is_korean() 규칙으로 고른다.
    버전은 그대로 인코딩해 붙이고(앞의 v 도 그대로), 비어 있으면 v 를 뺀다."""
    page = FEEDBACK_PAGE_KO if is_korean(lang) else FEEDBACK_PAGE_EN
    query = FEEDBACK_QUERY
    if version is not None and str(version).strip():
        query += "&v=" + urllib.parse.quote(str(version), safe="")
    return f"{page.format(slug=slug)}?{query}{FEEDBACK_ANCHOR}"


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
    url_en = data.get("urlEn")
    url_en = url_en if isinstance(url_en, str) and url_en.startswith(SITE) else None
    return UpdateInfo(latest, version, url, url_en)


def check_async(root, slug: str, version: str, prefs, on_result: Callable[[UpdateInfo | None, bool], None], *,
                fetcher: Callable = fetch, day: str | None = None) -> bool:
    """지금부터 DELAY_MS 뒤 한 번 확인하도록 예약한다. on_result(info, answered) 는 Tk 스레드에서
    돈다: 서버가 답했으면 answered=True(호출한 쪽이 그때 날짜를 기록), 알림을 띄울 때만 info 가 있다.
    확인할 차례가 아니면 False."""
    if not should_check(prefs, day or today()):
        return False
    skipped = getattr(prefs, "update_check_skipped", "")
    box: dict = {}

    # 작업 스레드는 서버 답을 box 에 담기만 하고 Tk 객체를 하나도 쥐지 않는다. 예전에는
    # root.after(0, on_result) 로 넘겼는데, 요청 중에 창을 닫으면 그 스레드가 창의 마지막 참조를
    # 쥔 채 끝나면서 Tk 변수를 메인 스레드 밖에서 풀었고 Tcl 이 프로세스를 죽였다
    # ("Tcl_AsyncDelete: async handler deleted by the wrong thread", v0.2.6). 이제 Tk 스레드가 가져간다.
    def work(box=box) -> None:
        box["data"] = fetcher(slug, version)

    def poll() -> None:
        if "data" not in box:
            try:
                root.after(POLL_MS, poll)
            except Exception:  # 그사이 창이 닫혔다
                pass
            return
        data = box["data"]
        on_result(interpret(data, version, skipped), data is not None)

    def start() -> None:
        threading.Thread(target=work, name="update-check", daemon=True).start()
        poll()

    try:
        root.after(DELAY_MS, start)
    except Exception:
        return False
    return True
