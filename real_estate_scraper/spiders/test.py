import argparse
import asyncio
import csv
import datetime as dt
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    from crawl4ai import AsyncWebCrawler
except ImportError:  # pragma: no cover - handled at runtime when crawl is requested
    AsyncWebCrawler = None


LISTING_URL = "https://batdongsan.com.vn/nha-dat-ban-cau-giay"
BASE_URL = "https://batdongsan.com.vn"
OUTPUT_COLUMNS = [
    "source",
    "scraped_at",
    "title",
    "description",
    "price",
    "price_raw",
    "city",
    "district",
    "ward",
    "address",
    "property_size",
    "property_size_raw",
    "property_type",
    "bedrooms",
    "bathrooms",
    "amenities",
    "currency",
    "listing_id",
    "crawl_status",
    "listing_url",
]


def _normalize_space(value):
    if not value:
        return "N/A"
    return re.sub(r"\s+", " ", str(value)).strip()


def _extract_listing_links(html, max_items):
    # Real listing pages on this source typically contain urls ending with -pr{digits}
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html or "", flags=re.IGNORECASE)
    filtered = []
    seen = set()

    for href in hrefs:
        if href.startswith("javascript:") or href.startswith("mailto:"):
            continue

        absolute = urljoin(BASE_URL, href)
        parsed = urlparse(absolute)
        if parsed.netloc and "batdongsan.com.vn" not in parsed.netloc:
            continue

        path = parsed.path.lower()
        if not re.search(r"-pr\d+", path):
            continue

        if not ("/ban-" in path or "/nha-dat-ban" in path):
            continue

        if any(
            ext in path
            for ext in [".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".svg"]
        ):
            continue

        if absolute in seen:
            continue
        seen.add(absolute)
        filtered.append(absolute)

        if len(filtered) >= max_items:
            break

    return filtered


def _json_ld_candidates(html):
    scripts = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html or "",
        flags=re.IGNORECASE | re.DOTALL,
    )

    candidates = []
    for raw in scripts:
        data = raw.strip()
        if not data:
            continue
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            continue

        if isinstance(parsed, list):
            candidates.extend([x for x in parsed if isinstance(x, dict)])
        elif isinstance(parsed, dict):
            candidates.append(parsed)
    return candidates


def _pick_price_from_jsonld(item):
    offers = item.get("offers")
    if isinstance(offers, dict):
        price = offers.get("price")
        currency = offers.get("priceCurrency")
        if price is not None:
            return f"{price} {currency}" if currency else str(price)
    return None


def _extract_number(text, pattern):
    m = re.search(pattern, text or "", flags=re.IGNORECASE)
    return _normalize_space(m.group(1)) if m else "N/A"


def _extract_listing_id(url):
    m = re.search(r"-pr(\d+)", url)
    return m.group(1) if m else "N/A"


def _best_jsonld_candidate(candidates):
    def score(item):
        s = 0
        t = str(item.get("@type", "")).lower()
        if "breadcrumb" in t:
            s -= 5
        if "article" in t or "residence" in t or "product" in t or "offer" in t:
            s += 3
        if item.get("offers"):
            s += 3
        if item.get("address"):
            s += 2
        if item.get("description"):
            s += 1
        if item.get("name"):
            s += 1
        return s

    if not candidates:
        return None
    return sorted(candidates, key=score, reverse=True)[0]


def _parse_detail(html, url):
    result = {
        "source": "batdongsan.com.vn",
        "scraped_at": dt.datetime.now(dt.UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "title": "N/A",
        "description": "N/A",
        "city": "Ha Noi - Cau Giay",
        "district": "Cau Giay",
        "ward": "N/A",
        "price": "N/A",
        "price_raw": "N/A",
        "address": "N/A",
        "property_size": "N/A",
        "property_size_raw": "N/A",
        "property_type": "N/A",
        "bedrooms": "N/A",
        "bathrooms": "N/A",
        "amenities": "",
        "currency": "VND",
        "listing_id": _extract_listing_id(url),
        "crawl_status": "ok",
        "listing_url": url,
    }

    candidates = _json_ld_candidates(html)
    best = _best_jsonld_candidate(candidates)
    if best:
        name = best.get("name")
        if name:
            result["title"] = _normalize_space(name)

        desc = best.get("description")
        if desc:
            result["description"] = _normalize_space(desc)

        address = best.get("address")
        if isinstance(address, dict):
            addr = address.get("streetAddress") or address.get("addressLocality")
            if addr:
                result["address"] = _normalize_space(addr)

        prop_type = best.get("category")
        if prop_type:
            result["property_type"] = _normalize_space(prop_type)

    for item in candidates:
        price = _pick_price_from_jsonld(item)
        if price and result["price_raw"] == "N/A":
            result["price_raw"] = _normalize_space(price)
            result["price"] = _normalize_space(price)

        floor_size = item.get("floorSize")
        if isinstance(floor_size, dict):
            value = floor_size.get("value")
            unit = floor_size.get("unitCode")
            if value is not None and result["property_size"] == "N/A":
                size = _normalize_space(f"{value} {unit or ''}")
                result["property_size"] = size
                result["property_size_raw"] = size

    # Fallback regex extraction when json-ld is incomplete.
    text = _normalize_space(re.sub(r"<[^>]+>", " ", html or ""))
    if result["price_raw"] == "N/A":
        m = re.search(
            r"(\d+[\d\.,]*)\s*(ty|trieu|nghin|tỷ|triệu)", text, flags=re.IGNORECASE
        )
        if m:
            price_text = _normalize_space(" ".join(m.groups()))
            result["price_raw"] = price_text
            result["price"] = price_text
    if result["property_size_raw"] == "N/A":
        m = re.search(r"(\d+[\d\.,]*)\s*(m2|m²)", text, flags=re.IGNORECASE)
        if m:
            size_text = _normalize_space(" ".join(m.groups()))
            result["property_size_raw"] = size_text
            result["property_size"] = size_text

    if result["title"] == "N/A":
        m = re.search(
            r"<title>(.*?)</title>", html or "", flags=re.IGNORECASE | re.DOTALL
        )
        if m:
            result["title"] = _normalize_space(m.group(1))

    # Simple text-derived fallbacks for model features.
    result["bedrooms"] = _extract_number(text, r"(\d+)\s*(phong ngu|phòng ngủ)")
    result["bathrooms"] = _extract_number(text, r"(\d+)\s*(wc|phong tam|phòng tắm)")

    # Infer property type by url path if still missing.
    if result["property_type"] == "N/A":
        lower_path = urlparse(url).path.lower()
        if "/ban-can-ho-chung-cu" in lower_path:
            result["property_type"] = "Apartment"
        elif "/ban-nha-rieng" in lower_path:
            result["property_type"] = "Private house"
        elif "/ban-nha-mat-pho" in lower_path:
            result["property_type"] = "Townhouse"
        elif "/ban-dat" in lower_path:
            result["property_type"] = "Land"

    return result


async def _fetch_details(crawler, links):
    rows = []
    for idx, link in enumerate(links, 1):
        res = await crawler.arun(url=link)
        if not getattr(res, "success", False):
            print(f"[{idx}/{len(links)}] FAIL {link}")
            continue
        rows.append(_parse_detail(getattr(res, "html", ""), link))
        print(f"[{idx}/{len(links)}] OK   {link}")
    return rows


def _write_csv(rows, output_file):
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


async def main(max_items, output_file):
    if AsyncWebCrawler is None:
        raise RuntimeError(
            "crawl4ai is not installed. Install it before running this script."
        )

    async with AsyncWebCrawler() as crawler:
        listing = await crawler.arun(url=LISTING_URL)
        if not getattr(listing, "success", False):
            raise RuntimeError(
                "Cannot open listing page. Check anti-bot/proxy settings."
            )

        links = _extract_listing_links(
            getattr(listing, "html", ""), max_items=max_items
        )
        if not links:
            raise RuntimeError(
                "No detail links found. Selectors/pattern may need update."
            )

        print(f"Found {len(links)} links. Crawling detail pages...")
        rows = await _fetch_details(crawler, links)
        _write_csv(rows, output_file)
        print(f"Done. Wrote {len(rows)} rows -> {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Quick Crawl4AI test for Batdongsan Cau Giay."
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=20,
        help="Maximum number of detail links to crawl.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(
            Path(__file__).resolve().parents[1] / "output" / "caugiay_crawl4ai.csv"
        ),
        help="Output CSV path.",
    )
    args = parser.parse_args()

    asyncio.run(main(max_items=args.max_items, output_file=Path(args.output)))
