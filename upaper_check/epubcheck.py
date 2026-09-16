"""선택 기능: epubcheck(자바) 결과를 검수 결과에 합친다. 유페이퍼 적합성 검사와 같은 엔진."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

from upaper_check.findings import Finding, Level

SEVERITY_MAP = {"FATAL": Level.ERROR, "ERROR": Level.ERROR, "WARNING": Level.WARN,
                "USAGE": Level.INFO, "INFO": Level.INFO}
TIMEOUT_SECONDS = 300


def find_jar(explicit: str | None) -> str | None:
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    env = os.environ.get("EPUBCHECK_JAR")
    if env and os.path.isfile(env):
        return env
    local = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools", "epubcheck.jar")
    return local if os.path.isfile(local) else None


def run(epub_path: str, jar: str) -> list[Finding]:
    if shutil.which("java") is None:
        return [Finding("EPUBCHECK", Level.WARN, "java 를 찾을 수 없어 epubcheck 를 건너뜁니다.", "")]
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "epubcheck.json")
        cmd = ["java", "-jar", jar, epub_path, "--json", out]
        try:
            subprocess.run(cmd, capture_output=True, timeout=TIMEOUT_SECONDS, check=False)
        except (subprocess.TimeoutExpired, OSError) as exc:
            return [Finding("EPUBCHECK", Level.WARN, f"epubcheck 실행 실패: {exc}", "")]
        if not os.path.isfile(out):
            return [Finding("EPUBCHECK", Level.WARN, "epubcheck 가 결과 파일을 만들지 않았습니다.", "")]
        with open(out, encoding="utf-8") as fh:
            return _parse(json.load(fh))


def _parse(data: dict) -> list[Finding]:
    findings: list[Finding] = []
    for msg in data.get("messages", []):
        level = SEVERITY_MAP.get(str(msg.get("severity", "")).upper(), Level.INFO)
        if level == Level.INFO:
            continue
        locations = msg.get("locations") or [{}]
        loc = locations[0]
        where = loc.get("path", "")
        if loc.get("line", -1) not in (None, -1):
            where = f"{where}:{loc.get('line')}"
        findings.append(Finding(f"EPUBCHECK-{msg.get('ID', '')}", level, msg.get("message", ""), where,
                                "유페이퍼 판매신청 시 적합성 검사에서 같은 오류가 납니다."))
    return findings
