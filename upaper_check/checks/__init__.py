"""모든 검사 모듈을 순서대로 실행한다."""
from __future__ import annotations

from upaper_check.checks import colophon, cover, images, markup, metadata, structure, toc
from upaper_check.context import Context
from upaper_check.findings import Finding

CHECK_MODULES = (structure, metadata, cover, colophon, toc, markup, images)


def run_all(ctx: Context) -> list[Finding]:
    findings: list[Finding] = []
    for module in CHECK_MODULES:
        findings.extend(module.check(ctx))
    return findings
