"""EPUB 압축 파일을 열어 OPF·spine·manifest·NCX를 읽는 얇은 래퍼."""
from __future__ import annotations

import posixpath
import zipfile
from dataclasses import dataclass, field
from urllib.parse import unquote

from lxml import etree

CONTAINER_PATH = "META-INF/container.xml"
MIMETYPE_PATH = "mimetype"
EPUB_MIMETYPE = "application/epub+zip"
XHTML_TYPES = {"application/xhtml+xml", "text/html"}
NCX_TYPE = "application/x-dtbncx+xml"
FONT_TYPES = {
    "application/vnd.ms-opentype", "application/x-font-ttf", "application/x-font-truetype",
    "application/x-font-opentype", "application/font-woff", "application/font-woff2",
    "font/ttf", "font/otf", "font/woff", "font/woff2", "application/font-sfnt",
}
FONT_EXTENSIONS = (".ttf", ".otf", ".woff", ".woff2")


class EpubLoadError(Exception):
    """EPUB 자체를 열 수 없을 때."""


@dataclass
class ManifestItem:
    id: str
    href: str
    media_type: str
    properties: set[str] = field(default_factory=set)

    @property
    def is_xhtml(self) -> bool:
        return self.media_type in XHTML_TYPES

    @property
    def is_image(self) -> bool:
        return self.media_type.startswith("image/")

    @property
    def is_font(self) -> bool:
        return self.media_type in FONT_TYPES or self.href.lower().endswith(FONT_EXTENSIONS)

    @property
    def is_css(self) -> bool:
        return self.media_type == "text/css"


@dataclass
class Metadata:
    title: str = ""
    creators: list[str] = field(default_factory=list)
    publisher: str = ""
    language: str = ""
    date: str = ""
    identifiers: list[str] = field(default_factory=list)
    cover_id: str = ""


@dataclass
class NavPoint:
    label: str
    src: str
    depth: int


@dataclass
class GuideRef:
    type: str
    href: str


def local_tag(tag) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def parse_xml(data: bytes):
    parser = etree.XMLParser(recover=True, resolve_entities=False, no_network=True, huge_tree=True)
    try:
        return etree.fromstring(data, parser)
    except etree.XMLSyntaxError:
        return None


def is_well_formed(data: bytes) -> tuple[bool, str]:
    parser = etree.XMLParser(recover=False, resolve_entities=False, no_network=True, huge_tree=True)
    try:
        etree.fromstring(data, parser)
        return True, ""
    except etree.XMLSyntaxError as exc:
        return False, str(exc)


class EpubPackage:
    def __init__(self, path: str):
        self.path = path
        try:
            self.zip = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError) as exc:
            raise EpubLoadError(f"ZIP(EPUB) 파일을 열 수 없습니다: {exc}") from exc
        self.infos = {info.filename: info for info in self.zip.infolist()}
        self.names = set(self.infos)
        self.opf_path = self._find_opf()
        self.opf_dir = posixpath.dirname(self.opf_path)
        self.opf = parse_xml(self.read(self.opf_path))
        if self.opf is None:
            raise EpubLoadError(f"OPF 파일을 해석할 수 없습니다: {self.opf_path}")
        self.version = (self.opf.get("version") or "").strip()
        self.metadata = self._parse_metadata()
        self.manifest = self._parse_manifest()
        self.spine_ids = self._parse_spine()
        self.toc_id = self._spine_toc_attr()
        self.guide = self._parse_guide()

    # ---------- 파일 접근 ----------
    def exists(self, name: str) -> bool:
        return name in self.names

    def read(self, name: str) -> bytes:
        return self.zip.read(name)

    def read_xml(self, name: str):
        return parse_xml(self.read(name))

    def size_of(self, name: str) -> int:
        return self.infos[name].file_size

    def resolve(self, href: str, base_dir: str | None = None) -> str:
        """href(상대경로, 퍼센트 인코딩, #조각 포함 가능)를 ZIP 내부 경로로 정규화."""
        base = self.opf_dir if base_dir is None else base_dir
        clean = unquote(href.split("#", 1)[0].split("?", 1)[0])
        joined = posixpath.join(base, clean) if base else clean
        normalized = posixpath.normpath(joined)
        return normalized[2:] if normalized.startswith("./") else normalized

    def item_path(self, item: ManifestItem) -> str:
        return self.resolve(item.href)

    def resolve_from(self, item: ManifestItem, href: str) -> str:
        """문서(item) 안에서 쓰인 상대 href 를 ZIP 경로로."""
        return self.resolve(href, posixpath.dirname(self.item_path(item)))

    # ---------- 구조 ----------
    def _find_opf(self) -> str:
        if CONTAINER_PATH not in self.names:
            raise EpubLoadError("META-INF/container.xml 이 없습니다. EPUB 구조가 아닙니다.")
        container = parse_xml(self.read(CONTAINER_PATH))
        if container is None:
            raise EpubLoadError("META-INF/container.xml 을 해석할 수 없습니다.")
        for rootfile in container.iter():
            if local_tag(rootfile.tag) == "rootfile" and rootfile.get("full-path"):
                full_path = rootfile.get("full-path")
                if full_path not in self.names:
                    raise EpubLoadError(f"container.xml 이 가리키는 OPF 가 없습니다: {full_path}")
                return full_path
        raise EpubLoadError("container.xml 에 rootfile(OPF 경로)이 없습니다.")

    def _parse_metadata(self) -> Metadata:
        meta = Metadata()
        for el in self.opf.iter():
            name = local_tag(el.tag)
            text = (el.text or "").strip()
            if name == "title" and not meta.title:
                meta.title = text
            elif name == "creator" and text:
                meta.creators.append(text)
            elif name == "publisher" and not meta.publisher:
                meta.publisher = text
            elif name == "language" and not meta.language:
                meta.language = text
            elif name == "date" and not meta.date:
                meta.date = text
            elif name == "identifier" and text:
                meta.identifiers.append(text)
            elif name == "meta" and el.get("name") == "cover" and el.get("content"):
                meta.cover_id = el.get("content")
        return meta

    def _parse_manifest(self) -> dict[str, ManifestItem]:
        items: dict[str, ManifestItem] = {}
        for el in self.opf.iter():
            if local_tag(el.tag) != "item":
                continue
            item_id = el.get("id") or ""
            props = set((el.get("properties") or "").split())
            items[item_id] = ManifestItem(item_id, el.get("href") or "", el.get("media-type") or "", props)
        return items

    def _parse_spine(self) -> list[str]:
        return [el.get("idref") for el in self.opf.iter()
                if local_tag(el.tag) == "itemref" and el.get("idref")]

    def _spine_toc_attr(self) -> str:
        for el in self.opf.iter():
            if local_tag(el.tag) == "spine":
                return el.get("toc") or ""
        return ""

    def _parse_guide(self) -> list[GuideRef]:
        return [GuideRef(el.get("type") or "", el.get("href") or "")
                for el in self.opf.iter() if local_tag(el.tag) == "reference"]

    # ---------- 편의 ----------
    def spine_items(self) -> list[ManifestItem]:
        return [self.manifest[i] for i in self.spine_ids if i in self.manifest]

    def spine_docs(self) -> list[ManifestItem]:
        return [item for item in self.spine_items() if item.is_xhtml]

    def ncx_item(self) -> ManifestItem | None:
        if self.toc_id and self.toc_id in self.manifest:
            return self.manifest[self.toc_id]
        for item in self.manifest.values():
            if item.media_type == NCX_TYPE:
                return item
        return None

    def nav_points(self) -> list[NavPoint]:
        ncx = self.ncx_item()
        if ncx is None or not self.exists(self.item_path(ncx)):
            return []
        root = self.read_xml(self.item_path(ncx))
        if root is None:
            return []
        points: list[NavPoint] = []
        for el in root.iter():
            if local_tag(el.tag) == "navMap":
                self._walk_nav(el, 1, points)
                break
        return points

    def _walk_nav(self, parent, depth: int, out: list[NavPoint]) -> None:
        for child in parent:
            if local_tag(child.tag) != "navPoint":
                continue
            src = ""
            for sub in child:
                if local_tag(sub.tag) == "content":
                    src = sub.get("src") or ""
            out.append(NavPoint(self._nav_label(child), src, depth))
            self._walk_nav(child, depth + 1, out)

    @staticmethod
    def _nav_label(nav_point) -> str:
        for sub in nav_point:
            if local_tag(sub.tag) == "navLabel":
                return " ".join(t.strip() for t in sub.itertext() if t.strip())
        return ""
