"""OPF 메타데이터(제목·저자·출판사·언어·식별자) 검사."""
from __future__ import annotations

from upaper_check.context import Context
from upaper_check.findings import Finding, Level
from upaper_check.xhtml import normalize

KOREAN_LANG_PREFIX = "ko"


def check(ctx: Context) -> list[Finding]:
    meta = ctx.pkg.metadata
    opf = ctx.pkg.opf_path
    findings: list[Finding] = []
    if not meta.title:
        findings.append(Finding("META-TITLE", Level.ERROR, "OPF 에 <dc:title>(도서명)이 없습니다.", opf))
    if not meta.creators:
        findings.append(Finding("META-CREATOR", Level.ERROR, "OPF 에 <dc:creator>(저자명)가 없습니다.", opf))
    findings.extend(_check_language(meta.language, opf))
    findings.extend(_check_publisher(ctx, meta.publisher, opf))
    if not meta.identifiers:
        findings.append(Finding("META-IDENTIFIER", Level.WARN, "OPF 에 <dc:identifier> 가 없습니다.", opf,
                                "ISBN 이 있으면 ISBN, 없으면 urn:uuid 값을 넣으세요 (적합성 검사 항목)."))
    if not meta.date:
        findings.append(Finding("META-DATE", Level.INFO, "OPF 에 <dc:date>(발행일)가 없습니다.", opf))
    return findings


def _check_language(language: str, opf: str) -> list[Finding]:
    if not language:
        return [Finding("META-LANGUAGE", Level.ERROR, "OPF 에 <dc:language> 가 없습니다.", opf,
                        "<dc:language>ko</dc:language> 를 추가하세요.")]
    if not language.lower().startswith(KOREAN_LANG_PREFIX):
        return [Finding("META-LANGUAGE", Level.INFO, f"OPF 언어가 {language} 입니다 (한국어 도서는 ko).", opf)]
    return []


def _check_publisher(ctx: Context, publisher: str, opf: str) -> list[Finding]:
    expected = ctx.rules.get("publisher_expected") or ""
    if not publisher:
        hint = f"<dc:publisher>{expected}</dc:publisher> 를 추가하세요." if expected else "<dc:publisher> 를 추가하세요."
        return [Finding("META-PUBLISHER", Level.ERROR, "OPF 에 <dc:publisher>(출판사명)가 없습니다.", opf, hint)]
    if expected and normalize(publisher) != normalize(expected):
        return [Finding("META-PUBLISHER-NAME", Level.ERROR,
                        f"OPF 출판사명이 '{publisher}' 입니다. 기대값: '{expected}'.", opf,
                        "개인(출판사 미등록) 출판자는 출판사명이 반드시 '유페이퍼'여야 합니다. "
                        "등록된 출판사라면 --publisher 출판사명 옵션으로 기대값을 바꾸세요.")]
    return []
