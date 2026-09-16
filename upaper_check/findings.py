"""검수 결과 한 건을 표현하는 자료형."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Level(str, Enum):
    ERROR = "오류"      # 승인 거부 사유가 될 수 있음 — 반드시 수정
    WARN = "경고"       # 제휴사 뷰어 문제·권장 규격 이탈 — 수정 권장
    INFO = "정보"       # 참고 사항
    MANUAL = "수동확인"  # 프로그램이 판단할 수 없어 사람이 눈으로 확인


LEVEL_ORDER = {Level.ERROR: 0, Level.WARN: 1, Level.MANUAL: 2, Level.INFO: 3}


@dataclass
class Finding:
    code: str            # 예: COVER-SIZE
    level: Level
    message: str         # 무엇이 문제인지
    location: str = ""   # 파일 경로 등
    hint: str = ""       # 어떻게 고치면 되는지
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "level": self.level.value,
            "message": self.message,
            "location": self.location,
            "hint": self.hint,
        }


def sort_findings(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (LEVEL_ORDER[f.level], f.code, f.location))


def count_by_level(findings: list[Finding]) -> dict[Level, int]:
    counts = {level: 0 for level in Level}
    for finding in findings:
        counts[finding.level] += 1
    return counts
