"""목차(NCX) 검사 — 빈 목차명·깊이·링크 대상, 그리고 내용 없는 본문 파일."""
from __future__ import annotations

import posixpath

from upaper_check.context import Context
from upaper_check.findings import Finding, Level
from upaper_check.xhtml import image_srcs


def check(ctx: Context) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(_check_nav_points(ctx))
    findings.extend(_check_empty_docs(ctx))
    return findings


def _check_nav_points(ctx: Context) -> list[Finding]:
    pkg = ctx.pkg
    ncx = pkg.ncx_item()
    if ncx is None:
        return []
    ncx_path = pkg.item_path(ncx)
    ncx_dir = posixpath.dirname(ncx_path)
    points = pkg.nav_points()
    if not points:
        return [Finding("TOC-EMPTY", Level.WARN, "toc.ncx 에 목차 항목(navPoint)이 하나도 없습니다.", ncx_path)]
    max_depth = ctx.rules["limits"]["max_toc_depth"]
    findings: list[Finding] = []
    for index, point in enumerate(points, start=1):
        if not point.label:
            findings.append(Finding("TOC-LABEL", Level.ERROR,
                                    f"{index}번째 목차 항목의 목차명이 비어 있습니다 (→ {point.src}).", ncx_path,
                                    "목차명이 없으면 승인이 거부됩니다. navLabel 에 제목을 넣으세요."))
        target = pkg.resolve(point.src, ncx_dir)
        if point.src and not pkg.exists(target):
            findings.append(Finding("TOC-TARGET", Level.ERROR,
                                    f"목차 '{point.label}' 의 링크 대상이 없습니다: {point.src}", ncx_path))
    deepest = max(p.depth for p in points)
    if deepest > max_depth:
        findings.append(Finding("TOC-DEPTH", Level.WARN,
                                f"목차 깊이가 {deepest}단계입니다. 유페이퍼는 {max_depth}단계까지 지원합니다.", ncx_path))
    return findings


def _check_empty_docs(ctx: Context) -> list[Finding]:
    min_chars = ctx.rules["limits"]["empty_doc_min_chars"]
    findings: list[Finding] = []
    for item in ctx.docs():
        root = ctx.root(item)
        if root is None:
            continue
        if len(ctx.text(item)) >= min_chars or image_srcs(root):
            continue
        findings.append(Finding("TOC-EMPTY-DOC", Level.ERROR,
                                "내용이 없는 빈 본문(html) 파일입니다.", ctx.path(item),
                                "빈 목차는 승인이 거부됩니다. 파일을 삭제하거나 내용을 채우세요."))
    return findings
