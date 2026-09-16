"""본문 마크업 검사 — 금지 태그·이벤트 속성·검정 글자색·고정 글자 크기·언어 설정·XML 문법."""
from __future__ import annotations

import re
from collections import Counter

from upaper_check.context import Context
from upaper_check.epub import ManifestItem, is_well_formed
from upaper_check.findings import Finding, Level
from upaper_check.xhtml import iter_elements, local_name, root_lang, style_texts, stylesheet_hrefs

BLACK_COLOR = re.compile(
    r"(?<![-\w])color\s*:\s*(#000000|#000|black|rgb\(\s*0\s*,\s*0\s*,\s*0\s*\))(?![0-9a-fA-F])", re.IGNORECASE)
FIXED_FONT_SIZE = re.compile(r"font-size\s*:\s*\d+(\.\d+)?\s*(pt|px)\b", re.IGNORECASE)
BLACK_ATTR_VALUES = {"#000000", "#000", "black"}
JAVASCRIPT_HREF = "javascript:"
EVENT_ATTR_PREFIX = "on"
XHTML_DOCTYPE_HINT = "XHTML 1.1"


def check(ctx: Context) -> list[Finding]:
    findings: list[Finding] = []
    tag_usage: dict[str, dict[str, int]] = {}   # 태그 → {파일: 개수}
    for item in ctx.docs():
        findings.extend(_check_doc(ctx, item, tag_usage))
    findings.extend(_check_css_files(ctx))
    findings.extend(_summarize_tags(ctx, tag_usage))
    return findings


def _check_doc(ctx: Context, item: ManifestItem, tag_usage: dict[str, dict[str, int]]) -> list[Finding]:
    path = ctx.path(item)
    if not ctx.pkg.exists(path):
        return []
    findings: list[Finding] = []
    ok, error = is_well_formed(ctx.pkg.read(path))
    if not ok:
        findings.append(Finding("DOC-XML", Level.ERROR, f"XHTML 문법 오류(well-formed 아님): {error}", path,
                                "유페이퍼 적합성 검사(epubcheck)를 통과하지 못합니다. 태그 닫힘·& 이스케이프를 확인하세요."))
    root = ctx.root(item)
    if root is None:
        return findings
    findings.extend(_check_forbidden_tags(ctx, root, path, tag_usage))
    findings.extend(_check_attributes(root, path))
    findings.extend(_check_styles(style_texts(root), path))
    findings.extend(_check_lang(root, path))
    findings.extend(_check_stylesheet_links(ctx, item, root, path))
    return findings


def _check_forbidden_tags(ctx: Context, root, path: str, tag_usage: dict[str, dict[str, int]]) -> list[Finding]:
    """금지 태그는 파일별 오류로, 비권장·EPUB2 미지원 태그는 집계만(요약은 _summarize_tags)."""
    tag_rules = ctx.rules["tags"]
    forbidden = set(tag_rules["forbidden"])
    tracked = set(tag_rules["unsupported_epub2"]) | set(tag_rules["discouraged"])
    counts = Counter(local_name(el) for el in iter_elements(root))
    findings: list[Finding] = []
    for tag, count in sorted(counts.items()):
        if tag in forbidden:
            findings.append(Finding("TAG-FORBIDDEN", Level.ERROR, f"금지 태그 <{tag}> {count}개.", path,
                                    "스크립트·프레임·폼·멀티미디어 태그는 뷰어에서 동작하지 않고 적합성 검사에 걸립니다. 제거하세요."))
        elif tag in tracked:
            tag_usage.setdefault(tag, {})[path] = count
    return findings


def _summarize_tags(ctx: Context, tag_usage: dict[str, dict[str, int]]) -> list[Finding]:
    unsupported = set(ctx.rules["tags"]["unsupported_epub2"])
    findings: list[Finding] = []
    for tag in sorted(tag_usage):
        per_file = tag_usage[tag]
        total = sum(per_file.values())
        where = ", ".join(f"{p.rsplit('/', 1)[-1]}({n})" for p, n in sorted(per_file.items()))
        if tag in unsupported:
            findings.append(Finding("TAG-EPUB2", Level.WARN,
                                    f"EPUB 2 뷰어가 지원하지 않는 태그 <{tag}> — {len(per_file)}개 파일, 총 {total}개.",
                                    where, "svg/math/HTML5 구조 태그는 div/p/img 로 바꾸세요."))
        else:
            findings.append(Finding("TAG-DISCOURAGED", Level.WARN,
                                    f"권장하지 않는 태그 <{tag}> — {len(per_file)}개 파일, 총 {total}개.",
                                    where, "유페이퍼 승인은 되지만 li/ul 은 일부 제휴사 뷰어에서 깨져 제휴사 상용이 거부될 수 있고, "
                                    "표(table)는 이미지로 넣기를 권장합니다."))
    return findings


def _check_attributes(root, path: str) -> list[Finding]:
    events, js_links, black_fonts = 0, 0, 0
    for el in iter_elements(root):
        for name, value in el.attrib.items():
            key = local_name_of_attr(name)
            if key.startswith(EVENT_ATTR_PREFIX) and len(key) > 2:
                events += 1
            if key in ("href", "src") and value.strip().lower().startswith(JAVASCRIPT_HREF):
                js_links += 1
            if key == "color" and local_name(el) == "font" and value.strip().lower() in BLACK_ATTR_VALUES:
                black_fonts += 1
    findings: list[Finding] = []
    if events:
        findings.append(Finding("ATTR-EVENT", Level.ERROR, f"onclick 등 이벤트 속성 {events}개.", path, "제거하세요."))
    if js_links:
        findings.append(Finding("ATTR-JAVASCRIPT", Level.ERROR, f"javascript: 링크 {js_links}개.", path, "제거하세요."))
    if black_fonts:
        findings.append(Finding("STYLE-BLACK", Level.ERROR, f"<font color=\"#000000\"> {black_fonts}개.", path,
                                "검정 글자색을 지정하면 야간모드에서 글자가 보이지 않아 승인이 거부됩니다. color 지정을 없애세요."))
    return findings


def local_name_of_attr(name: str) -> str:
    return name.rsplit("}", 1)[-1].lower()


def _check_styles(styles: list[str], path: str) -> list[Finding]:
    joined = "\n".join(styles)
    findings: list[Finding] = []
    black = len(BLACK_COLOR.findall(joined))
    if black:
        findings.append(Finding("STYLE-BLACK", Level.ERROR, f"글자색 검정(#000000/black) 지정 {black}곳.", path,
                                "야간모드에서 글자가 보이지 않아 승인이 거부됩니다. color 지정을 제거하거나 #000 이 아닌 색으로 바꾸세요."))
    fixed = len(FIXED_FONT_SIZE.findall(joined))
    if fixed:
        findings.append(Finding("STYLE-FONT-SIZE", Level.WARN, f"글자 크기를 pt/px 고정값으로 지정한 곳 {fixed}곳.", path,
                                "em 또는 % 상대값으로 바꾸세요 (독자가 글자 크기를 조절할 수 있어야 함)."))
    return findings


def _check_lang(root, path: str) -> list[Finding]:
    if root_lang(root):
        return []
    return [Finding("DOC-LANG", Level.WARN, "<html> 에 xml:lang/lang 언어 설정이 없습니다.", path,
                    '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ko" lang="ko"> 로 지정하세요.')]


def _check_stylesheet_links(ctx: Context, item: ManifestItem, root, path: str) -> list[Finding]:
    findings: list[Finding] = []
    for href in stylesheet_hrefs(root):
        target = ctx.pkg.resolve_from(item, href)
        if not ctx.pkg.exists(target):
            findings.append(Finding("CSS-MISSING", Level.ERROR, f"연결된 스타일시트가 없습니다: {href}", path))
    return findings


def _check_css_files(ctx: Context) -> list[Finding]:
    findings: list[Finding] = []
    for item in ctx.pkg.manifest.values():
        path = ctx.path(item)
        if not item.is_css or not ctx.pkg.exists(path):
            continue
        css = ctx.pkg.read(path).decode("utf-8", errors="replace")
        findings.extend(_check_styles([css], path))
    return findings
