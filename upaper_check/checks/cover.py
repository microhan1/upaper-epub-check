"""표지 검사 — 존재·첫 장 배치·중복·이미지 규격."""
from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError

from upaper_check.context import Context
from upaper_check.epub import ManifestItem
from upaper_check.findings import Finding, Level
from upaper_check.xhtml import image_srcs

COVER_KEYWORD = "cover"
COVER_PAGE_MAX_TEXT = 40      # 이 글자 수 이하 + 이미지 1장 = 표지 페이지로 간주
CMYK_MODE = "CMYK"
COVER_IMAGE_PROPERTY = "cover-image"


def check(ctx: Context) -> list[Finding]:
    cover = find_cover_image(ctx)
    if cover is None:
        return [Finding("COVER-MISSING", Level.ERROR, "표지 이미지를 찾을 수 없습니다.", ctx.pkg.opf_path,
                        '<meta name="cover" content="표지이미지id"/> 를 OPF metadata 에 넣고, '
                        "첫 번째 spine 문서에서 그 이미지를 표시하세요.")]
    findings: list[Finding] = []
    cover_path = ctx.path(cover)
    if not ctx.pkg.exists(cover_path):
        return [Finding("COVER-MISSING", Level.ERROR, f"표지 이미지 파일이 없습니다: {cover.href}", ctx.pkg.opf_path)]
    findings.extend(_check_placement(ctx, cover))
    findings.extend(_check_image(ctx, cover))
    findings.append(Finding("COVER-TEXT", Level.MANUAL,
                            "표지에 도서명·저자명·출판사명이 모두 들어 있는지 눈으로 확인하세요. "
                            "(개인 출판자는 출판사명 '유페이퍼' 표기 필요, 성인 도서는 19세 미만 구독 불가 빨간 띠지)",
                            cover_path, "", {"cover_path": cover_path}))
    return findings


def find_cover_image(ctx: Context) -> ManifestItem | None:
    pkg = ctx.pkg
    meta_cover = pkg.manifest.get(pkg.metadata.cover_id)
    if meta_cover is not None and meta_cover.is_image:
        return meta_cover
    for item in pkg.manifest.values():
        if COVER_IMAGE_PROPERTY in item.properties and item.is_image:
            return item
    from_guide = _cover_from_guide(ctx)
    if from_guide is not None:
        return from_guide
    docs = ctx.docs()
    if docs and _is_cover_page(ctx, docs[0]):
        return _image_item_of(ctx, docs[0])
    for item in pkg.manifest.values():
        if item.is_image and COVER_KEYWORD in (item.id + item.href).lower():
            return item
    return None


def _cover_from_guide(ctx: Context) -> ManifestItem | None:
    for ref in ctx.pkg.guide:
        if ref.type.lower() != COVER_KEYWORD:
            continue
        target = ctx.pkg.resolve(ref.href)
        for item in ctx.pkg.manifest.values():
            if ctx.path(item) == target:
                return item if item.is_image else _image_item_of(ctx, item)
    return None


def _image_item_of(ctx: Context, doc: ManifestItem) -> ManifestItem | None:
    root = ctx.root(doc)
    if root is None:
        return None
    for src in image_srcs(root):
        target = ctx.pkg.resolve_from(doc, src)
        for item in ctx.pkg.manifest.values():
            if item.is_image and ctx.path(item) == target:
                return item
    return None


def _is_cover_page(ctx: Context, doc: ManifestItem) -> bool:
    root = ctx.root(doc)
    if root is None:
        return False
    return len(image_srcs(root)) == 1 and len(ctx.text(doc)) <= COVER_PAGE_MAX_TEXT


def _docs_showing(ctx: Context, cover: ManifestItem) -> list[ManifestItem]:
    cover_path = ctx.path(cover)
    showing: list[ManifestItem] = []
    for doc in ctx.docs():
        root = ctx.root(doc)
        if root is None:
            continue
        if any(ctx.pkg.resolve_from(doc, src) == cover_path for src in image_srcs(root)):
            showing.append(doc)
    return showing


def _check_placement(ctx: Context, cover: ManifestItem) -> list[Finding]:
    docs = ctx.docs()
    showing = _docs_showing(ctx, cover)
    findings: list[Finding] = []
    if not docs:
        return findings
    if docs[0] not in showing:
        findings.append(_first_doc_finding(ctx, docs[0]))
    if len(showing) > 1:
        names = ", ".join(d.href for d in showing)
        findings.append(Finding("COVER-DUP", Level.ERROR,
                                f"표지 이미지가 {len(showing)}개 문서에 중복으로 들어 있습니다: {names}",
                                ctx.pkg.opf_path, "표지가 중복이면 승인이 거부됩니다. 하나만 남기세요 "
                                "(웹에디터에서 편집하면 표지가 하나 더 생기니 그때도 삭제)."))
    return findings


def _first_doc_finding(ctx: Context, first: ManifestItem) -> Finding:
    """첫 장이 OPF 표지 이미지를 쓰지 않는 경우 — 이미지 한 장짜리 표지 페이지면 정보, 아니면 오류."""
    if _is_cover_page(ctx, first):
        return Finding("COVER-FIRST", Level.INFO,
                       f"첫 장({first.href})은 표지 페이지로 보이지만 OPF <meta name=\"cover\"> 가 가리키는 이미지와 다른 파일을 씁니다.",
                       ctx.pkg.opf_path, "같은 표지 이미지를 쓰도록 맞추면 뷰어 서가 썸네일과 첫 장이 일치합니다.")
    return Finding("COVER-FIRST", Level.ERROR,
                   f"첫 번째 본문 파일({first.href})이 표지가 아닙니다. 파일 첫 장에는 표지가 있어야 합니다.",
                   ctx.pkg.opf_path, "표지 xhtml 을 spine 맨 앞으로 옮기세요.")


def _check_image(ctx: Context, cover: ManifestItem) -> list[Finding]:
    rules = ctx.rules["cover"]
    path = ctx.path(cover)
    try:
        image = Image.open(io.BytesIO(ctx.pkg.read(path)))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        return [Finding("COVER-UNREADABLE", Level.ERROR, f"표지 이미지를 열 수 없습니다: {exc}", path)]
    width, height = image.size
    findings: list[Finding] = []
    if not rules["min_width"] <= width <= rules["max_width"]:
        findings.append(Finding("COVER-SIZE", Level.WARN,
                                f"표지 가로 {width}px — 유페이퍼 권장 범위 {rules['min_width']}~{rules['max_width']}px 를 벗어납니다 "
                                f"(현재 {width}x{height}).", path,
                                f"가로 {rules['recommended_width']}px / 세로 {rules['recommended_height']}px 가 유페이퍼 뷰어에 가장 적합합니다."))
    elif (width, height) != (rules["recommended_width"], rules["recommended_height"]):
        findings.append(Finding("COVER-SIZE", Level.INFO,
                                f"표지 {width}x{height}px — 권장 범위 안입니다 "
                                f"(가장 적합한 크기는 {rules['recommended_width']}x{rules['recommended_height']}).", path))
    if image.mode == CMYK_MODE:
        findings.append(Finding("COVER-CMYK", Level.ERROR, "표지 이미지가 CMYK 입니다. RGB 로 저장해야 합니다.", path,
                                "포토샵/GIMP 에서 RGB 모드로 변환 후 다시 저장하세요 (안드로이드 표시 오류 방지)."))
    if cover.media_type not in rules["recommended_formats"]:
        findings.append(Finding("COVER-FORMAT", Level.INFO,
                                f"표지 형식 {cover.media_type} — 유페이퍼는 JPG 를 권장합니다.", path))
    return findings
