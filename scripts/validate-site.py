#!/usr/bin/env python3
"""Package-free structural validation for the JRSphere static website."""

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse
import json
import re
import struct
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SITE_ORIGIN = "https://jrspherejrs.github.io"
SITE_BASE = "/website/"
HTML_FILES = (Path("index.html"), Path("404.html"))
CSS_FILES = tuple(sorted((ROOT / "assets/css").glob("*.css")))
errors: list[str] = []
checks = 0


def check(condition: bool, message: str) -> None:
    global checks
    checks += 1
    if not condition:
        errors.append(message)


class Document(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.references: list[tuple[str, str]] = []
        self.meta: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.scripts: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self.json_parts: list[str] = []
        self.title_parts: list[str] = []
        self.in_json = False
        self.in_title = False
        self.lang = ""
        self.h1_count = 0
        self.main_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "html":
            self.lang = values.get("lang", "")
        if tag == "title":
            self.in_title = True
        if tag == "h1":
            self.h1_count += 1
        if tag == "main":
            self.main_count += 1
        if "id" in values:
            self.ids.append(values["id"])
        for attribute in ("href", "src"):
            if values.get(attribute):
                self.references.append((attribute, values[attribute]))
        if tag == "meta":
            self.meta.append(values)
        if tag == "link":
            self.links.append(values)
        if tag == "img":
            self.images.append(values)
        if tag == "script":
            self.scripts.append(values)
            self.in_json = values.get("type") == "application/ld+json"

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if tag == "script":
            self.in_json = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self.in_json:
            self.json_parts.append(data)

    @property
    def title(self) -> str:
        return " ".join(" ".join(self.title_parts).split())


def load_html(path: Path) -> Document:
    parser = Document()
    parser.feed((ROOT / path).read_text(encoding="utf-8"))
    parser.close()
    return parser


def local_target(source: Path, reference: str) -> tuple[Path, str] | None:
    parsed = urlparse(reference)
    if parsed.scheme in {"mailto", "tel", "data"}:
        return None
    if parsed.scheme in {"http", "https"}:
        if f"{parsed.scheme}://{parsed.netloc}" != SITE_ORIGIN:
            return None
        raw_path = parsed.path
    elif parsed.scheme or parsed.netloc:
        return None
    else:
        raw_path = parsed.path

    if raw_path.startswith(SITE_BASE):
        raw_path = raw_path[len(SITE_BASE):]
        target = ROOT / unquote(raw_path)
    elif raw_path.startswith("/"):
        errors.append(f"{source}: local root path is outside {SITE_BASE}: {reference}")
        return None
    elif raw_path:
        target = (ROOT / source.parent / unquote(raw_path)).resolve()
    else:
        target = (ROOT / source).resolve()

    if target == ROOT or raw_path.endswith("/"):
        target = target / "index.html"
    return target, unquote(parsed.fragment)


documents = {path: load_html(path) for path in HTML_FILES}

for path, document in documents.items():
    check(document.lang == "en", f"{path}: expected lang='en'")
    check(bool(document.title), f"{path}: title is missing")
    check(document.h1_count == 1, f"{path}: expected exactly one h1")
    check(document.main_count == 1, f"{path}: expected exactly one main landmark")
    duplicates = sorted({item for item in document.ids if document.ids.count(item) > 1})
    check(not duplicates, f"{path}: duplicate IDs: {duplicates}")
    check(all("alt" in image for image in document.images), f"{path}: image without alt attribute")
    script_sources = [script.get("src") for script in document.scripts if script.get("src")]
    expected_sources = ["assets/js/navigation.js"] if path == Path("index.html") else []
    check(script_sources == expected_sources, f"{path}: unexpected executable script source")
    check(
        all(script.get("src") or script.get("type") == "application/ld+json" for script in document.scripts),
        f"{path}: unexpected inline executable script found",
    )

    robots = [item.get("content") for item in document.meta if item.get("name") == "robots"]
    if path == Path("404.html"):
        check(robots == ["noindex, nofollow"], "404.html: expected noindex, nofollow")
    else:
        check(robots in ([], ["noindex, nofollow"]), "index.html: unexpected robots directive")

    for attribute, reference in document.references:
        result = local_target(path, reference)
        if result is None:
            continue
        target, fragment = result
        check(target.is_file(), f"{path}: missing target for {attribute}='{reference}'")
        if fragment and target.is_file() and target.suffix == ".html":
            relative = target.relative_to(ROOT)
            target_document = documents.get(relative) or load_html(relative)
            check(fragment in target_document.ids, f"{path}: missing fragment target '{reference}'")

index = documents[Path("index.html")]
properties = {item.get("property"): item.get("content") for item in index.meta if item.get("property")}
names = {item.get("name"): item.get("content") for item in index.meta if item.get("name")}
expected_title = "JRSphere | Software products and development services"
expected_description = (
    "JRSphere is a hybrid software company building products and providing "
    "software development services."
)
check(index.title == expected_title, "index.html: title mismatch")
check(names.get("description") == expected_description, "index.html: description mismatch")
check(properties.get("og:title") == expected_title, "index.html: Open Graph title mismatch")
check(properties.get("og:description") == expected_description, "index.html: Open Graph description mismatch")
check(names.get("twitter:title") == expected_title, "index.html: Twitter title mismatch")
check(names.get("twitter:description") == expected_description, "index.html: Twitter description mismatch")
check(properties.get("og:image") == names.get("twitter:image"), "index.html: social-image URLs differ")
check(properties.get("og:image:width") == "1200", "index.html: social-image width mismatch")
check(properties.get("og:image:height") == "630", "index.html: social-image height mismatch")

json_text = "".join(index.json_parts)
check(bool(json_text.strip()), "index.html: JSON-LD missing")
if json_text.strip():
    try:
        graph = json.loads(json_text)["@graph"]
        organization = next(item for item in graph if item["@type"] == "Organization")
        website = next(item for item in graph if item["@type"] == "WebSite")
        check(organization["sameAs"] == ["https://github.com/JRSphere"], "index.html: sameAs mismatch")
        check(website["publisher"]["@id"] == organization["@id"], "index.html: publisher relationship mismatch")
    except (json.JSONDecodeError, KeyError, StopIteration, TypeError) as error:
        errors.append(f"index.html: invalid JSON-LD graph: {error}")

for css_path in CSS_FILES:
    relative_css = css_path.relative_to(ROOT)
    css = css_path.read_text(encoding="utf-8")
    without_comments = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    check(without_comments.count("{") == without_comments.count("}"), f"{relative_css}: unbalanced braces")
    for _, reference in re.findall(r"url\(\s*(['\"]?)(.*?)\1\s*\)", without_comments):
        if reference.startswith(("data:", "http://", "https://", "#")):
            continue
        target = (css_path.parent / unquote(urlparse(reference).path)).resolve()
        check(target.is_file(), f"{relative_css}: missing url() asset '{reference}'")

favicon = ROOT / "assets/icons/favicon.svg"
try:
    ET.parse(favicon)
except (ET.ParseError, OSError) as error:
    errors.append(f"assets/icons/favicon.svg: invalid SVG XML: {error}")
else:
    checks += 1

social = ROOT / "assets/images/og/jrsphere-social.png"
try:
    data = social.read_bytes()
    check(data.startswith(b"\x89PNG\r\n\x1a\n"), "social image: invalid PNG signature")
    width, height = struct.unpack(">II", data[16:24])
    check((width, height) == (1200, 630), f"social image: expected 1200x630, got {width}x{height}")
    check(len(data) <= 180_000, "social image: exceeds 180 KB budget")
except (OSError, struct.error) as error:
    errors.append(f"social image: unreadable PNG: {error}")

try:
    sitemap_root = ET.parse(ROOT / "sitemap.xml").getroot()
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locations = [item.text for item in sitemap_root.findall("sm:url/sm:loc", namespace)]
    check(locations == [f"{SITE_ORIGIN}{SITE_BASE}"], "sitemap.xml: URL set mismatch")
except (ET.ParseError, OSError) as error:
    errors.append(f"sitemap.xml: invalid XML: {error}")

check((ROOT / ".nojekyll").is_file(), ".nojekyll is missing")
for forbidden in ("package.json", "package-lock.json", "node_modules"):
    check(not (ROOT / forbidden).exists(), f"production dependency artifact found: {forbidden}")
check(not (ROOT / "robots.txt").exists(), "robots.txt exists despite approved deferral")

if errors:
    print(f"FAIL: {len(errors)} issue(s) across {checks} checks")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)

robots_state = "release-blocked" if names.get("robots") == "noindex, nofollow" else "indexable"
print(f"PASS: {checks} package-free static-site checks; homepage state: {robots_state}")
