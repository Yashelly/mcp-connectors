"""Small shared text helpers; website structure stays in each adapter."""
import json
import re

from bs4 import BeautifulSoup, Tag

from .errors import ConnectorError
from .models import Salary


def clean(value) -> str | None:
    if value is None:
        return None
    text = value.get_text(" ", strip=True) if isinstance(value, (Tag, BeautifulSoup)) else str(value)
    return re.sub(r"\s+", " ", re.sub(r"[\u200b-\u200d\ufeff]", "", text)).strip() or None


def text_at(node, selector):
    return clean(node.select_one(selector))


def number(value) -> float | None:
    if value is None:
        return None
    match = re.search(r"\d[\d\s\u00a0]*(?:[.,]\d+)?", clean(value) or "")
    return float(re.sub(r"\s", "", match[0]).replace(",", ".")) if match else None


def salary(raw: str | None) -> Salary | None:
    raw = clean(raw)
    if not raw:
        return None
    # Remove thousands separators, while preserving spaces around range separators.
    numeric = re.sub(r"(?<=\d)[ \u00a0](?=\d{3}(?:\D|$))", "", raw)
    nums = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", numeric)[:2]]
    minimum = nums[0] if nums else None
    maximum = nums[1] if len(nums) > 1 else (None if re.search(r"\b(nuo|from)\b", raw, re.I) else minimum)
    if re.search(r"\b(iki|up to)\b", raw, re.I) and len(nums) == 1:
        minimum, maximum = None, nums[0]
    period = "MONTH" if re.search(r"mėn|month", raw, re.I) else "HOUR" if re.search(r"val\.|hour", raw, re.I) else None
    return Salary(minimum=minimum, maximum=maximum, currency="EUR" if re.search(r"€|EUR", raw, re.I) else None,
                  period=period, raw=raw)


def requirements(fragment: str) -> list[str] | None:
    soup = BeautifulSoup(fragment, "html.parser")
    result = []
    for heading in soup.find_all(["h2", "h3", "p", "div"]):
        heading_text = clean(heading) or ""
        if len(heading_text) > 100 or not re.search(r"reikalavimai|requirements|mes tikimės|privalumas", heading_text, re.I):
            continue
        for sibling in heading.next_siblings:
            if not isinstance(sibling, Tag):
                continue
            if sibling.name not in {"ul", "ol", "div"}:
                break
            values = sibling.select("li")
            if values:
                result.extend(filter(None, (clean(x) for x in values)))
            elif sibling.name == "div" and "jobad_txt" in sibling.get("class", []):
                result.append(clean(sibling))
            else:
                break
    return list(dict.fromkeys(filter(None, result))) or None


def json_nodes(soup):
    nodes = []
    def walk(value):
        if isinstance(value, dict):
            nodes.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            walk(json.loads(script.string or script.get_text()))
        except (ValueError, TypeError):
            continue
    return nodes


def verification_required(soup) -> bool:
    title = (clean(soup.title) or "").lower()
    text = (clean(soup) or "").lower()
    markers = ("verify you are human", "checking your browser", "tikriname jūsų naršyklę",
               "saugumo patvirtinimo atlikimas", "patvirtinti kad esate ne robotas",
               "enable javascript and cookies")
    return any(m in title for m in ("just a moment", "luktelėkite")) or any(m in text for m in markers)


def inspect_page(html: str, status: int = 200, url: str | None = None):
    soup = BeautifulSoup(html, "html.parser")
    if status in {401, 403, 429} or verification_required(soup) or "access denied" in (clean(soup) or "").lower():
        raise ConnectorError("blocked", "Site requires verification or denied/rate-limited the request", url, status)
    if status in {404, 410}:
        raise ConnectorError("not_found", "Listing/page no longer exists", url, status)
    if status >= 400:
        raise ConnectorError("network_error", f"Site returned HTTP {status}", url, status)
    return soup


def require_title(title):
    if not title:
        raise ConnectorError("layout_changed", "Expected listing title is missing")
    return title
