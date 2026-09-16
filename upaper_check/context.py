"""검사 모듈들이 공유하는 컨텍스트 — 문서 파싱 결과를 한 번만 계산해 캐시한다."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from upaper_check.epub import EpubPackage, ManifestItem
from upaper_check.xhtml import parse_xhtml, text_of

DEFAULT_RULES_PATH = Path(__file__).with_name("default_rules.json")


def load_rules(override_path: str | None = None) -> dict:
    rules = json.loads(DEFAULT_RULES_PATH.read_text(encoding="utf-8"))
    if override_path:
        override = json.loads(Path(override_path).read_text(encoding="utf-8"))
        rules = deep_merge(rules, override)
    return rules


def deep_merge(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class Context:
    def __init__(self, pkg: EpubPackage, rules: dict):
        self.pkg = pkg
        self.rules = rules
        self._roots: dict[str, object] = {}
        self._texts: dict[str, str] = {}

    def path(self, item: ManifestItem) -> str:
        return self.pkg.item_path(item)

    def root(self, item: ManifestItem):
        path = self.path(item)
        if path not in self._roots:
            self._roots[path] = parse_xhtml(self.pkg.read(path)) if self.pkg.exists(path) else None
        return self._roots[path]

    def text(self, item: ManifestItem) -> str:
        path = self.path(item)
        if path not in self._texts:
            self._texts[path] = text_of(self.root(item))
        return self._texts[path]

    def docs(self) -> list[ManifestItem]:
        return self.pkg.spine_docs()
