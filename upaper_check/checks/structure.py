"""컨테이너 구조·EPUB 버전·파일 크기·목차 개수 검사."""
from __future__ import annotations

import os
import zipfile

from upaper_check.context import Context
from upaper_check.epub import EPUB_MIMETYPE, MIMETYPE_PATH, NCX_TYPE
from upaper_check.findings import Finding, Level

EPUB2_PREFIX = "2."
BYTES_PER_MB = 1024 * 1024


def check(ctx: Context) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(_check_mimetype(ctx))
    findings.extend(_check_version(ctx))
    findings.extend(_check_ncx(ctx))
    findings.extend(_check_spine_and_manifest(ctx))
    findings.extend(_check_sizes(ctx))
    return findings


def _check_mimetype(ctx: Context) -> list[Finding]:
    pkg = ctx.pkg
    infos = list(pkg.zip.infolist())
    if MIMETYPE_PATH not in pkg.names:
        return [Finding("STRUCT-MIMETYPE", Level.ERROR, "mimetype 파일이 없습니다.", MIMETYPE_PATH,
                        "EPUB 규격 위반이라 적합성 검사에 걸립니다. Sigil/Calibre 로 다시 저장하면 생깁니다.")]
    if not infos or infos[0].filename != MIMETYPE_PATH:
        return [Finding("STRUCT-MIMETYPE", Level.ERROR,
                        "mimetype 파일이 ZIP 의 첫 번째 항목이 아닙니다.",
                        MIMETYPE_PATH, "EPUB 규격: mimetype 이 첫 항목이며 무압축(Stored)이어야 합니다. "
                        "Sigil/Calibre 로 다시 저장하면 해결됩니다.")]
    first = infos[0]
    findings: list[Finding] = []
    if first.compress_type != zipfile.ZIP_STORED:
        findings.append(Finding("STRUCT-MIMETYPE", Level.ERROR,
                                "mimetype 파일이 압축되어 있습니다(무압축이어야 함).", MIMETYPE_PATH,
                                "Sigil/Calibre 로 다시 저장하거나 zip -X0 로 mimetype 을 먼저 넣으세요."))
    content = pkg.read(MIMETYPE_PATH).decode("ascii", errors="replace").strip()
    if content != EPUB_MIMETYPE:
        findings.append(Finding("STRUCT-MIMETYPE", Level.ERROR,
                                f"mimetype 내용이 잘못되었습니다: {content!r}", MIMETYPE_PATH,
                                f"내용은 정확히 {EPUB_MIMETYPE} 이어야 합니다."))
    return findings


def _check_version(ctx: Context) -> list[Finding]:
    expected = str(ctx.rules.get("epub_version_expected", "2.0"))
    version = ctx.pkg.version
    if not version:
        return [Finding("STRUCT-VERSION", Level.ERROR, "OPF <package> 에 version 속성이 없습니다.",
                        ctx.pkg.opf_path, f'<package version="{expected}" ...> 로 지정하세요.')]
    if version.startswith(expected[:2]):
        return [Finding("STRUCT-VERSION", Level.INFO, f"EPUB 버전 {version} (유페이퍼 기준 EPUB 2 계열).",
                        ctx.pkg.opf_path)]
    return [Finding("STRUCT-VERSION", Level.ERROR,
                    f"EPUB 버전이 {version} 입니다. 유페이퍼 웹에디터는 EPUB {expected} 기준입니다.",
                    ctx.pkg.opf_path,
                    "Calibre 변환(출력 EPUB 버전 2) 또는 Sigil 로 EPUB 2 로 저장하세요. "
                    "toc.ncx 와 <meta name=\"cover\"> 가 함께 필요합니다.")]


def _check_ncx(ctx: Context) -> list[Finding]:
    pkg = ctx.pkg
    ncx = pkg.ncx_item()
    if ncx is None:
        return [Finding("STRUCT-NCX", Level.ERROR, "목차 파일(toc.ncx)이 manifest 에 없습니다.", pkg.opf_path,
                        f'manifest 에 media-type="{NCX_TYPE}" 항목을 추가하고 <spine toc="ncx"> 로 연결하세요.')]
    if not pkg.exists(pkg.item_path(ncx)):
        return [Finding("STRUCT-NCX", Level.ERROR, f"toc.ncx 파일이 실제로 없습니다: {ncx.href}", pkg.opf_path)]
    if not pkg.toc_id:
        return [Finding("STRUCT-NCX", Level.WARN, "<spine> 에 toc 속성이 없습니다.", pkg.opf_path,
                        f'<spine toc="{ncx.id}"> 로 NCX 를 연결하세요.')]
    return []


def _check_spine_and_manifest(ctx: Context) -> list[Finding]:
    pkg = ctx.pkg
    findings: list[Finding] = []
    if not pkg.spine_ids:
        findings.append(Finding("STRUCT-SPINE", Level.ERROR, "<spine> 이 비어 있습니다.", pkg.opf_path))
    for idref in pkg.spine_ids:
        if idref not in pkg.manifest:
            findings.append(Finding("STRUCT-SPINE", Level.ERROR,
                                    f"spine 의 idref 가 manifest 에 없습니다: {idref}", pkg.opf_path))
    for item in pkg.manifest.values():
        if not pkg.exists(pkg.item_path(item)):
            findings.append(Finding("STRUCT-MANIFEST", Level.ERROR,
                                    f"manifest 항목의 파일이 EPUB 안에 없습니다: {item.href}", pkg.opf_path,
                                    "파일을 추가하거나 manifest 에서 항목을 제거하세요."))
    return findings


def _check_sizes(ctx: Context) -> list[Finding]:
    pkg = ctx.pkg
    limits = ctx.rules["limits"]
    findings: list[Finding] = []
    epub_bytes = os.path.getsize(pkg.path)
    if epub_bytes > limits["max_epub_bytes"]:
        findings.append(Finding("SIZE-EPUB", Level.ERROR,
                                f"EPUB 파일 크기 {epub_bytes / BYTES_PER_MB:.1f}MB — "
                                f"{limits['max_epub_bytes'] / BYTES_PER_MB:.0f}MB 이하여야 합니다.",
                                os.path.basename(pkg.path), "이미지 해상도·용량을 줄이고 사용하지 않는 폰트를 제거하세요."))
    docs = ctx.docs()
    if len(docs) > limits["max_spine_docs"]:
        findings.append(Finding("TOC-COUNT", Level.ERROR,
                                f"본문(html) 파일이 {len(docs)}개 — {limits['max_spine_docs']}개 이하여야 합니다.",
                                pkg.opf_path, "짧은 장을 합쳐 html 개수를 줄이세요 (다운로드·뷰잉 오류 방지)."))
    for item in docs:
        path = pkg.item_path(item)
        if pkg.exists(path) and pkg.size_of(path) > limits["max_html_bytes"]:
            findings.append(Finding("SIZE-HTML", Level.ERROR,
                                    f"html 크기 {pkg.size_of(path) / 1024:.0f}KB — "
                                    f"{limits['max_html_bytes'] / 1024:.0f}KB 이하여야 합니다.",
                                    path, "장을 여러 html 로 나누거나 불필요한 태그·인라인 스타일을 정리하세요."))
    return findings
