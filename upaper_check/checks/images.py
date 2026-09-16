"""이미지·폰트 검사 — 깨진 참조·CMYK·manifest 누락·사용하지 않는 파일."""
from __future__ import annotations

import io
import posixpath
import re

from PIL import Image, UnidentifiedImageError

from upaper_check.context import Context
from upaper_check.findings import Finding, Level
from upaper_check.xhtml import image_srcs

CMYK_MODE = "CMYK"
CSS_URL = re.compile(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", re.IGNORECASE)
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".bmp")


def check(ctx: Context) -> list[Finding]:
    referenced = _referenced_paths(ctx)
    findings: list[Finding] = []
    findings.extend(_check_references(ctx, referenced))
    findings.extend(_check_image_files(ctx))
    findings.extend(_check_unused(ctx, referenced))
    return findings


def _referenced_paths(ctx: Context) -> dict[str, list[str]]:
    """참조된 ZIP 경로 → 참조한 문서 목록 (본문 <img> 와 CSS url() 모두)."""
    refs: dict[str, list[str]] = {}
    for doc in ctx.docs():
        root = ctx.root(doc)
        for src in image_srcs(root):
            refs.setdefault(ctx.pkg.resolve_from(doc, src), []).append(ctx.path(doc))
    for item in ctx.pkg.manifest.values():
        path = ctx.path(item)
        if not item.is_css or not ctx.pkg.exists(path):
            continue
        css = ctx.pkg.read(path).decode("utf-8", errors="replace")
        for url in CSS_URL.findall(css):
            refs.setdefault(ctx.pkg.resolve(url, posixpath.dirname(path)), []).append(path)
    return refs


def _missing_finding(target: str, location: str) -> Finding:
    if location.lower().endswith(".css"):
        return Finding("CSS-RES-MISSING", Level.ERROR, f"CSS 가 참조한 파일이 EPUB 안에 없습니다: {target}", location,
                       "폰트 파일을 넣거나 @font-face / url() 선언을 지우세요 (적합성 검사 RSC-007 오류).")
    return Finding("IMG-MISSING", Level.ERROR, f"참조한 이미지가 EPUB 안에 없습니다: {target}", location,
                   "이미지 경로(대소문자 포함)를 확인하세요.")


def _check_references(ctx: Context, referenced: dict[str, list[str]]) -> list[Finding]:
    manifest_paths = {ctx.path(item) for item in ctx.pkg.manifest.values()}
    findings: list[Finding] = []
    for target, users in referenced.items():
        if target.startswith(("http://", "https://", "data:")):
            continue
        location = users[0]
        if not ctx.pkg.exists(target):
            findings.append(_missing_finding(target, location))
        elif target not in manifest_paths and target.lower().endswith(IMAGE_SUFFIXES):
            findings.append(Finding("IMG-MANIFEST", Level.ERROR, f"이미지가 manifest 에 등록되지 않았습니다: {target}",
                                    ctx.pkg.opf_path, "OPF manifest 에 <item> 을 추가하세요 (적합성 검사 오류)."))
    return findings


def _check_image_files(ctx: Context) -> list[Finding]:
    findings: list[Finding] = []
    for item in ctx.pkg.manifest.values():
        path = ctx.path(item)
        if not item.is_image or not ctx.pkg.exists(path) or item.media_type == "image/svg+xml":
            continue
        try:
            image = Image.open(io.BytesIO(ctx.pkg.read(path)))
        except (UnidentifiedImageError, OSError) as exc:
            findings.append(Finding("IMG-UNREADABLE", Level.WARN, f"이미지를 열 수 없습니다: {exc}", path))
            continue
        if image.mode == CMYK_MODE:
            findings.append(Finding("IMG-CMYK", Level.ERROR, "CMYK 이미지입니다. RGB 로 저장해야 합니다.", path,
                                    "일부 안드로이드 뷰어에서 CMYK 이미지가 표시되지 않습니다."))
    return findings


def _check_unused(ctx: Context, referenced: dict[str, list[str]]) -> list[Finding]:
    cover_id = ctx.pkg.metadata.cover_id
    css_text = _all_css(ctx)
    findings: list[Finding] = []
    for item in ctx.pkg.manifest.values():
        path = ctx.path(item)
        if item.is_image and path not in referenced and item.id != cover_id and "cover-image" not in item.properties:
            findings.append(Finding("IMG-UNUSED", Level.WARN, "본문·CSS 어디에서도 쓰지 않는 이미지입니다.", path,
                                    "파일 용량만 키우므로 제거하세요."))
        if item.is_font and posixpath.basename(path) not in css_text:
            findings.append(Finding("FONT-UNUSED", Level.WARN, "CSS @font-face 에서 참조하지 않는 폰트 파일입니다.", path,
                                    "사용하지 않는 폰트는 용량 증가·오류 원인이 되므로 제거하세요."))
    return findings


def _all_css(ctx: Context) -> str:
    chunks: list[str] = []
    for item in ctx.pkg.manifest.values():
        path = ctx.path(item)
        if item.is_css and ctx.pkg.exists(path):
            chunks.append(ctx.pkg.read(path).decode("utf-8", errors="replace"))
    for doc in ctx.docs():
        root = ctx.root(doc)
        if root is not None:
            from upaper_check.xhtml import style_texts
            chunks.extend(style_texts(root))
    return "\n".join(chunks)
