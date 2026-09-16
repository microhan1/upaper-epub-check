"""XHTML 문서 파싱·텍스트 추출 유틸리티."""
from __future__ import annotations

import re

from lxml import etree, html as lxml_html

SKIP_TEXT_TAGS = {"script", "style", "head", "title"}
IMAGE_TAGS = {"img", "image"}
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
_WS = re.compile(r"[\s﻿​]+")          # 공백 + BOM/제로폭 문자(일부 EPUB 본문에 섞여 있음)
_LOOSE = re.compile(r"[\s﻿​:：\-_–—·.,'\"“”‘’()\[\]『』「」《》〈〉!?]+")


def local_name(el) -> str:
    tag = el.tag
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def parse_xhtml(data: bytes):
    parser = etree.XMLParser(recover=True, resolve_entities=False, no_network=True, huge_tree=True)
    try:
        root = etree.fromstring(data, parser)
        if root is not None:
            return root
    except etree.XMLSyntaxError:
        pass
    try:
        return lxml_html.fromstring(data)
    except (etree.ParserError, ValueError):
        return None


def iter_elements(root):
    if root is None:
        return
    for el in root.iter():
        if isinstance(el.tag, str):
            yield el


def _inside_skipped(el) -> bool:
    parent = el.getparent()
    while parent is not None:
        if local_name(parent) in SKIP_TEXT_TAGS:
            return True
        parent = parent.getparent()
    return False


def text_of(root) -> str:
    parts: list[str] = []
    for el in iter_elements(root):
        if local_name(el) in SKIP_TEXT_TAGS or _inside_skipped(el):
            continue
        if el.text:
            parts.append(el.text)
        if el.tail:
            parts.append(el.tail)
    return _WS.sub(" ", " ".join(parts)).strip()


def image_srcs(root) -> list[str]:
    srcs: list[str] = []
    for el in iter_elements(root):
        if local_name(el) not in IMAGE_TAGS:
            continue
        src = el.get("src") or el.get(XLINK_HREF) or el.get("href")
        if src:
            srcs.append(src)
    return srcs


def root_lang(root) -> str:
    if root is None:
        return ""
    return (root.get(XML_LANG) or root.get("lang") or "").strip()


def stylesheet_hrefs(root) -> list[str]:
    hrefs: list[str] = []
    for el in iter_elements(root):
        rel = (el.get("rel") or "").lower()
        if local_name(el) == "link" and "stylesheet" in rel and el.get("href"):
            hrefs.append(el.get("href"))
    return hrefs


def style_texts(root) -> list[str]:
    """style 속성값과 <style> 블록 내용을 모두 모은다."""
    found: list[str] = []
    for el in iter_elements(root):
        if el.get("style"):
            found.append(el.get("style"))
        if local_name(el) == "style" and el.text:
            found.append(el.text)
    return found


def doc_title(root) -> str:
    for el in iter_elements(root):
        if local_name(el) == "title":
            return (el.text or "").strip()
    return ""


def normalize(text: str) -> str:
    """공백·문장부호 제거 + 소문자 — 느슨한 포함 비교용 ('정글만리 3' 과 '정글만리3권', '채근담 : 문고' 와 '채근담')."""
    return _LOOSE.sub("", text or "").lower()
