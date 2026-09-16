"""판권 페이지 검사 — 존재·중복·필수 항목(도서명·저자명·출판사명·출간일·정가)·ISBN."""
from __future__ import annotations

import re
from dataclasses import dataclass

from upaper_check.context import Context
from upaper_check.epub import ManifestItem
from upaper_check.findings import Finding, Level
from upaper_check.xhtml import doc_title, image_srcs, normalize

COLOPHON_WORD = "판권"
MAX_COLOPHON_CHARS = 6000   # 판권 페이지는 짧다 — 긴 본문 장(章)이 키워드 우연 일치로 뽑히지 않게
HEADING_CHARS = 40          # 본문 첫머리 이만큼을 제목으로 간주
TAIL_DOCS_FOR_IMAGE_COLOPHON = 3
CONTACT_INFO = re.compile(r"(출판등록|등록번호|등록\s*[:：|]|전자우편|이메일|e-?mail|홈페이지|팩스|전화\s*[:：|]?\s*\d)", re.IGNORECASE)
STRICT_DATE_LABEL = re.compile(
    r"(발행일|발\s*행\s*일|초판|1판|펴낸날|펴낸\s*날|출간일|발행년월일|(인쇄|발\s*행|출간)\s*[:：|]?\s*(19|20)\d{2})")
HARD_CONTACT = re.compile(r"(출판등록|등록번호|팩스|전화\s*[:：|]?\s*\d)")   # 본문에 흔한 '이메일·홈페이지'는 제외
MIN_CHUNK_CHARS = 4
TITLE_SPLIT = re.compile(r"[\s:：\-—_|,()\[\]（）]+")

TITLE_LABEL = re.compile(r"(도서명|책\s*제목|서\s*명|제\s*목)\s*[:：|]")
AUTHOR_LABEL = re.compile(r"(지은이|지\s*은\s*이|저\s*자|글쓴이|지음|엮은이|저술|작가|저\s*:)")
PUBLISHER_LABEL = re.compile(r"(펴낸곳|펴\s*낸\s*곳|발행처|발\s*행\s*처|출판사|출\s*판\s*사|발행인|발\s*행\s*인|펴낸이|펴\s*낸\s*이|출판)")
DATE_LABEL = re.compile(r"(발행일|발\s*행\s*일|출간일|출\s*간\s*일|발행|초판|출간|펴낸날|펴낸\s*날|발행년월일)")
DATE_VALUE = re.compile(  # 연·월(·일). 월 1~12, 일 1~31 로 제한해 출판등록번호(제2006-000017호)를 날짜로 오인하지 않게
    r"(19|20)\d{2}\s*[.년/\-]\s*(0?[1-9]|1[0-2])(?!\d)\s*([.월/\-]\s*(0?[1-9]|[12]\d|3[01])(?!\d)\s*일?)?")
PRICE_LABEL = re.compile(r"(정\s*가|값|가\s*격|판매가)\s*[:：]?\s*[\d,]+\s*원?")
PRICE_VALUE = re.compile(r"\d{1,3}(,\d{3})+\s*원")
ISBN_VALUE = re.compile(r"ISBN[\s:：\-]*([0-9][0-9Xx\-\s]{8,30})")   # 공백·하이픈 섞인 표기, 뒤의 부가기호까지 잡힘
ISBN13_LEN, ISBN10_LEN = 13, 10
ISBN_WORD = re.compile(r"ISBN|ECN", re.IGNORECASE)


@dataclass
class Candidate:
    item: ManifestItem
    index: int
    text: str
    score: int


def check(ctx: Context) -> list[Finding]:
    candidates = find_candidates(ctx)
    if not candidates:
        return _missing(ctx)
    findings: list[Finding] = []
    strong = [c for c in candidates if is_strong(c)]
    if len(strong) > 1:
        names = ", ".join(c.item.href for c in strong)
        findings.append(Finding("COLOPHON-DUP", Level.ERROR,
                                f"판권 페이지가 {len(strong)}개로 보입니다: {names}", ctx.pkg.opf_path,
                                "판권이 중복이면 승인이 거부됩니다. 하나만 남기세요."))
    best = max(candidates, key=lambda c: c.score)
    findings.extend(_check_required(ctx, best))
    findings.extend(_check_isbn(best, ctx.path(best.item)))
    findings.extend(_check_position(ctx, best))
    return findings


def _missing(ctx: Context) -> list[Finding]:
    """텍스트 판권이 없을 때 — 끝부분에 이미지만 있는 페이지가 있으면 이미지 판권일 수 있으니 수동 확인으로."""
    docs = ctx.docs()
    for item in docs[-TAIL_DOCS_FOR_IMAGE_COLOPHON:]:
        root = ctx.root(item)
        if root is not None and image_srcs(root) and not ctx.text(item):
            return [Finding("COLOPHON-IMAGE", Level.MANUAL,
                            f"텍스트 판권을 찾지 못했습니다. 끝부분의 이미지 페이지({item.href})가 판권이라면 "
                            "도서명·저자명·출판사명·출간일·정가가 그림에 있는지 눈으로 확인하세요.", ctx.path(item))]
    return [Finding("COLOPHON-MISSING", Level.ERROR, "판권 페이지를 찾을 수 없습니다.", ctx.pkg.opf_path,
                    "도서명·저자명·출판사명·출간일·정가가 들어간 판권 페이지를 (가급적 맨 뒤에) 추가하세요.")]


def find_candidates(ctx: Context) -> list[Candidate]:
    min_hits = ctx.rules["colophon"]["min_keyword_hits"]
    candidates: list[Candidate] = []
    for index, item in enumerate(ctx.docs()):
        text = ctx.text(item)
        heading = _heading(ctx, item, text)
        if len(text) > MAX_COLOPHON_CHARS and COLOPHON_WORD not in heading:
            continue
        score = _score(ctx, text, heading)
        if score >= min_hits and _has_hard_datum(text):
            candidates.append(Candidate(item, index, text, score))
    return candidates


def _has_hard_datum(text: str) -> bool:
    """판권이라면 ISBN·정가·출판등록/전화·'발행일+날짜' 중 하나는 있다 — 날짜와 '이메일'만 있는 본문 장을 거른다."""
    if any(rx.search(text) for rx in (ISBN_WORD, PRICE_LABEL, HARD_CONTACT)):
        return True
    return bool(STRICT_DATE_LABEL.search(text) and DATE_VALUE.search(text))


def _heading(ctx: Context, item: ManifestItem, text: str) -> str:
    return f"{doc_title(ctx.root(item))} {item.href} {text[:HEADING_CHARS]}"


def _score(ctx: Context, text: str, heading: str) -> int:
    """구조 신호(발행일·펴낸곳·저자·정가·ISBN·연락처) + 규칙 파일의 키워드. '판권' 제목이면 가산."""
    signals = (DATE_LABEL, DATE_VALUE, PUBLISHER_LABEL, AUTHOR_LABEL, PRICE_LABEL, ISBN_WORD, CONTACT_INFO)
    score = sum(1 for rx in signals if rx.search(text))
    score += sum(1 for kw in ctx.rules["colophon"]["page_keywords"] if kw.lower() in text.lower())
    if COLOPHON_WORD in heading:
        score += ctx.rules["colophon"]["min_keyword_hits"]
    return score


def is_strong(cand: Candidate) -> bool:
    """중복 판정에 쓰는 '확실한 판권': 제목이 판권이거나, 발행일 표기 + 날짜 + 펴낸곳 + (ISBN·연락처·정가) 가 모두 있는 페이지.

    저자 소개("2000년 창해출판사")나 본문("1929년 10월 … 채권 발행"), 저작권 고지 페이지는 여기 걸리지 않는다."""
    text = cand.text
    if COLOPHON_WORD in f"{cand.item.href} {text[:HEADING_CHARS]}":
        return True
    has_date = bool(STRICT_DATE_LABEL.search(text) and DATE_VALUE.search(text))
    has_extra = any(rx.search(text) for rx in (ISBN_WORD, CONTACT_INFO, PRICE_LABEL))
    return has_date and bool(PUBLISHER_LABEL.search(text)) and has_extra


def _check_required(ctx: Context, cand: Candidate) -> list[Finding]:
    meta = ctx.pkg.metadata
    text, path = cand.text, ctx.path(cand.item)
    norm = normalize(text)
    findings: list[Finding] = []
    if not (_title_present(meta.title, norm) or TITLE_LABEL.search(text)):
        findings.append(Finding("COLOPHON-TITLE", Level.ERROR,
                                f"판권에 도서명이 없습니다 (OPF 제목: '{meta.title}').", path,
                                "OPF <dc:title> 과 같은 도서명을 판권에 적으세요."))
    if not (any(normalize(c) in norm for c in meta.creators if c) or AUTHOR_LABEL.search(text)):
        findings.append(Finding("COLOPHON-AUTHOR", Level.ERROR, "판권에 저자명(지은이)이 없습니다.", path,
                                "예: 지은이 홍길동"))
    findings.extend(_check_publisher(ctx, text, norm, path))
    if not DATE_VALUE.search(text):
        findings.append(Finding("COLOPHON-DATE", Level.ERROR, "판권에 출간일(발행일)이 없습니다.", path,
                                "예: 발행일 2026년 8월 2일"))
    elif not DATE_LABEL.search(text):
        findings.append(Finding("COLOPHON-DATE", Level.WARN, "판권에 날짜는 있으나 '발행일/출간일' 표기가 없습니다.", path))
    if not (PRICE_LABEL.search(text) or PRICE_VALUE.search(text)):
        findings.append(Finding("COLOPHON-PRICE", Level.ERROR, "판권에 정가가 없습니다.", path,
                                "예: 정가 5,900원 — 유페이퍼 등록 가격과 같아야 합니다."))
    return findings


def _title_present(title: str, norm_text: str) -> bool:
    """전체 제목 → 부제 앞부분 → 인접 어절 묶음(4자 이상) 순으로 느슨하게 대조.

    '김팔봉 수호지 10' 은 판권의 '수호지 10' 으로, '첫단추 시리즈 006 제1차세계대전' 은 '제1차세계대전' 으로 통과한다."""
    if not title:
        return False
    head = normalize(re.split(r"[:：\-—_|(（\[]", title)[0])
    if normalize(title) in norm_text or (len(head) >= 2 and head in norm_text):
        return True
    return any(run in norm_text for run in _chunk_runs(title))


def _chunk_runs(title: str) -> list[str]:
    """제목 어절의 모든 인접 묶음 중 정규화 길이가 MIN_CHUNK_CHARS 이상인 것 (긴 것부터)."""
    chunks = [normalize(c) for c in TITLE_SPLIT.split(title) if normalize(c)]
    runs = ["".join(chunks[i:j]) for i in range(len(chunks)) for j in range(i + 1, len(chunks) + 1)]
    return sorted((r for r in runs if len(r) >= MIN_CHUNK_CHARS), key=len, reverse=True)


def _check_publisher(ctx: Context, text: str, norm: str, path: str) -> list[Finding]:
    meta = ctx.pkg.metadata
    expected = ctx.rules.get("publisher_expected") or ""
    has_label = bool(PUBLISHER_LABEL.search(text))
    has_name = bool(meta.publisher and normalize(meta.publisher) in norm)
    if not (has_label or has_name):
        return [Finding("COLOPHON-PUBLISHER", Level.ERROR, "판권에 출판사명(펴낸곳/발행처)이 없습니다.", path,
                        f"예: 발행처 {expected or '출판사명'}")]
    if expected and normalize(expected) not in norm:
        return [Finding("COLOPHON-PUBLISHER-NAME", Level.ERROR,
                        f"판권에 출판사명 '{expected}' 가 없습니다.", path,
                        "개인 출판자는 표지·판권 모두 출판사명을 '유페이퍼'로 적어야 합니다. "
                        "등록된 출판사라면 --publisher 옵션으로 기대값을 바꾸세요.")]
    return []


def _check_isbn(cand: Candidate, path: str) -> list[Finding]:
    match = ISBN_VALUE.search(cand.text)
    if match:
        if not _isbn_text_valid(match.group(1)):
            return [Finding("COLOPHON-ISBN", Level.ERROR, f"판권의 ISBN 검증 실패: {match.group(1).strip()}", path,
                            "자릿수(10/13)와 체크 디지트를 확인하세요.")]
        return []
    if ISBN_WORD.search(cand.text):
        return []
    return [Finding("COLOPHON-ISBN", Level.INFO, "판권에 ISBN/ECN 표기가 없습니다.", path,
                    "유페이퍼에서 ISBN 을 대신 발급받는 경우 비워도 됩니다. 직접 발급받았다면 판권에 적으세요.")]


def _isbn_text_valid(raw: str) -> bool:
    """'978-89-349-9500-5 05300' 처럼 부가기호가 붙어 있으면 앞 13자리(또는 10자리)만 검증한다."""
    cleaned = re.sub(r"[^0-9Xx]", "", raw)
    if len(cleaned) in (ISBN13_LEN, ISBN10_LEN):
        return is_valid_isbn(cleaned)
    if len(cleaned) > ISBN13_LEN:
        return is_valid_isbn(cleaned[:ISBN13_LEN]) or is_valid_isbn(cleaned[:ISBN10_LEN])
    return False


def is_valid_isbn(digits: str) -> bool:
    if len(digits) == 13 and digits.isdigit():
        total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits[:12]))
        return (10 - total % 10) % 10 == int(digits[12])
    if len(digits) == 10:
        body, last = digits[:9], digits[9].upper()
        if not body.isdigit():
            return False
        total = sum(int(d) * (10 - i) for i, d in enumerate(body))
        check_val = (11 - total % 11) % 11
        return last == ("X" if check_val == 10 else str(check_val))
    return False


def _check_position(ctx: Context, cand: Candidate) -> list[Finding]:
    near_end = ctx.rules["colophon"]["expect_near_end"]
    total = len(ctx.docs())
    if cand.index < total - near_end:
        return [Finding("COLOPHON-POSITION", Level.INFO,
                        f"판권 페이지가 {cand.index + 1}/{total} 번째에 있습니다. 유페이퍼는 가급적 도서 마지막을 권장합니다.",
                        ctx.path(cand.item))]
    return []
