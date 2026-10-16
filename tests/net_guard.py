"""시험이 운영 서버(chaekgalpi.co.kr)를 치지 못하게 막는 가드 — import 하면 바로 설치된다.

사진 정리 도구에서 GUI 시험이 창을 만들 때마다 「새 버전 확인」이 실제 서버를 쳐 운영 통계에
사람 실행으로 잡혔다(2026-10-15 공통 지시서). 이 도구의 시험은 그때 0건이었지만 같은 구멍을 미리 막는다.

- `fetch` 의 기본 opener 와 `check_async` 의 기본 fetcher 는 정의 시점에 묶여 있어서
  `update_check.fetch = 가짜` 같은 모듈 속성 패치로는 안 막힌다 → `__kwdefaults__` 를 바꾼다.
- 창(`gui.DropWindow`)은 `update_check.fetch` 를 부르므로 fetch 의 opener 가드에 걸린다.
- 막힌 요청은 기록되고, 그 요청을 낸 시험은 정리 단계에서 실패한다.

unittest 에는 conftest 가 없으므로 helpers.py 와 각 시험 모듈이 이 모듈을 import 한다
(test_net_guard 가 모든 test_*.py 가 import 하는지 확인한다).
"""
from __future__ import annotations

import os
import sys
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from upaper_check import update_check as uc  # noqa: E402

BLOCKED: list[str] = []


def guard_urlopen(req, *args, **kwargs):
    """나가려던 주소를 기록하고 네트워크 오류처럼 실패한다."""
    url = getattr(req, "full_url", str(req))
    BLOCKED.append(url)
    raise urllib.error.URLError(f"시험 중 네트워크 차단: {url}")


def no_fetch(slug, version):
    """check_async 의 기본 fetcher 대신 — 묻지 않고 '답 없음'."""
    return None


def drain() -> list[str]:
    """지금까지 기록된 요청을 꺼내고 비운다(가드 자체를 시험할 때만)."""
    taken = BLOCKED[:]
    BLOCKED.clear()
    return taken


def _fail_if_blocked(test: unittest.TestCase, before: int) -> None:
    new = BLOCKED[before:]
    if new:
        del BLOCKED[before:]
        test.fail(f"시험이 네트워크 요청을 내보내려 했다({len(new)}건): {new[0]}")


def _guarded_run(self, result=None):
    self.addCleanup(_fail_if_blocked, self, len(BLOCKED))   # 처음 등록 → 맨 마지막에 확인
    return _original_run(self, result)


def install() -> None:
    urllib.request.urlopen = guard_urlopen
    uc.fetch.__kwdefaults__["opener"] = guard_urlopen
    uc.check_async.__kwdefaults__["fetcher"] = no_fetch
    unittest.TestCase.run = _guarded_run


_original_run = getattr(unittest.TestCase.run, "__wrapped_original__", unittest.TestCase.run)
_guarded_run.__wrapped_original__ = _original_run
install()
