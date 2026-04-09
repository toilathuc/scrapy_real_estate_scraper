import argparse
import asyncio
import csv
import datetime as dt
import json
import random
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    from crawl4ai import AsyncWebCrawler
except ImportError:  # pragma: no cover
    AsyncWebCrawler = None


BASE_URL = "https://batdongsan.com.vn"
DEFAULT_LISTING_URL = "https://batdongsan.com.vn/nha-dat-ban"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().with_name("crawler_config.json")
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


def _extract_listing_links(html):
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

    return filtered


def _listing_page_url(base_url, page_num):
    if page_num <= 1:
        return base_url
    return f"{base_url}/p{page_num}"


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


def _guess_district_from_url(url):
    path = urlparse(url).path.lower()
    district_matches = re.findall(r"-quan-([a-z0-9-]+)", path)
    if district_matches:
        return district_matches[0].replace("-", " ").title()
    return "N/A"


def _guess_city_from_url(url):
    path = urlparse(url).path.lower()
    m = re.search(r"nha-dat-ban-([a-z0-9-]+)", path)
    if not m:
        return "N/A"

    slug = m.group(1)
    # If district appears in the same slug, keep only city part.
    slug = re.sub(r"-quan-[a-z0-9-]+", "", slug)
    slug = re.sub(r"-huyen-[a-z0-9-]+", "", slug)
    slug = re.sub(r"-thi-xa-[a-z0-9-]+", "", slug)
    slug = re.sub(r"-thanh-pho-[a-z0-9-]+", "", slug)
    slug = re.sub(r"-tp-[a-z0-9-]+", "", slug)
    slug = slug.strip("-")

    return slug.replace("-", " ").title() if slug else "N/A"


def _parse_detail(html, url):
    guessed_city = _guess_city_from_url(url)
    guessed_district = _guess_district_from_url(url)
    result = {
        "source": "batdongsan.com.vn",
        "scraped_at": dt.datetime.now(dt.UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "title": "N/A",
        "description": "N/A",
        "city": guessed_city,
        "district": guessed_district,
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

    result["bedrooms"] = _extract_number(text, r"(\d+)\s*(phong ngu|phòng ngủ)")
    result["bathrooms"] = _extract_number(text, r"(\d+)\s*(wc|phong tam|phòng tắm)")

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


def _load_existing_links(output_file):
    existing = set()
    if not output_file.exists():
        return existing
    with output_file.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get("listing_url")
            if url:
                existing.add(url)
    return existing


def _append_rows(rows, output_file):
    output_file.parent.mkdir(parents=True, exist_ok=True)
    write_header = not output_file.exists() or output_file.stat().st_size == 0
    with output_file.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def _load_config(config_path):
    if not config_path.exists():
        return {}

    with config_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
        return data if isinstance(data, dict) else {}


async def _collect_listing_links(
    crawler, start_url, max_pages, max_items, page_delay_min, page_delay_max
):
    collected = []
    seen = set()

    for page in range(1, max_pages + 1):
        if max_items and len(collected) >= max_items:
            break

        page_url = _listing_page_url(start_url, page)
        res = await crawler.arun(url=page_url)
        if not getattr(res, "success", False):
            print(f"[PAGE {page}] FAIL {page_url}")
            continue

        links = _extract_listing_links(getattr(res, "html", ""))
        new_links = [x for x in links if x not in seen]
        for link in new_links:
            seen.add(link)
            collected.append(link)
            if max_items and len(collected) >= max_items:
                break

        print(
            f"[PAGE {page}] found={len(links)} new={len(new_links)} total={len(collected)}"
        )

        if not new_links:
            # likely reached the tail or blocked pagination
            print(f"[PAGE {page}] no new listing links, stopping pagination.")
            break

        await asyncio.sleep(random.uniform(page_delay_min, page_delay_max))

    return collected


async def _fetch_details(crawler, links, detail_delay_min, detail_delay_max):
    rows = []
    for idx, link in enumerate(links, 1):
        res = await crawler.arun(url=link)
        if not getattr(res, "success", False):
            print(f"[{idx}/{len(links)}] FAIL {link}")
            continue
        rows.append(_parse_detail(getattr(res, "html", ""), link))
        print(f"[{idx}/{len(links)}] OK   {link}")
        await asyncio.sleep(random.uniform(detail_delay_min, detail_delay_max))
    return rows


async def main(args):
    if AsyncWebCrawler is None:
        raise RuntimeError(
            "crawl4ai is not installed. Install it before running this script."
        )

    config_path = Path(args.config)
    config = _load_config(config_path)

    start_url = args.start_url or config.get("start_url") or DEFAULT_LISTING_URL
    output_file = Path(args.output)
    existing_links = _load_existing_links(output_file) if args.resume else set()
    print(f"Resume mode={args.resume}. Existing links in file={len(existing_links)}")
    print(f"Using start URL: {start_url}")

    async with AsyncWebCrawler() as crawler:
        links = await _collect_listing_links(
            crawler=crawler,
            start_url=start_url,
            max_pages=args.max_pages,
            max_items=args.max_items,
            page_delay_min=args.page_delay_min,
            page_delay_max=args.page_delay_max,
        )

        links = [x for x in links if x not in existing_links]
        if not links:
            print("No new links to crawl.")
            return

        print(f"Crawling {len(links)} detail pages...")
        rows = await _fetch_details(
            crawler=crawler,
            links=links,
            detail_delay_min=args.detail_delay_min,
            detail_delay_max=args.detail_delay_max,
        )
        _append_rows(rows, output_file)
        print(f"Done. Appended {len(rows)} rows -> {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Crawl batdongsan.com.vn listings with pagination and resume support."
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to JSON config file containing start_url.",
    )
    parser.add_argument(
        "--start-url",
        type=str,
        default=None,
        help="Listing URL root (e.g., nha-dat-ban-ha-noi, nha-dat-ban-da-nang, nha-dat-ban).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=50,
        help="Maximum listing pages to scan. Increase gradually for large runs.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=1000,
        help="Maximum detail listings to crawl in this run.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(
            Path(__file__).resolve().parents[1] / "output" / "listings_crawl4ai.csv"
        ),
        help="Output CSV path.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip listing URLs already existing in output file.",
    )
    parser.add_argument("--page-delay-min", type=float, default=1.0)
    parser.add_argument("--page-delay-max", type=float, default=2.0)
    parser.add_argument("--detail-delay-min", type=float, default=0.6)
    parser.add_argument("--detail-delay-max", type=float, default=1.4)
    cli_args = parser.parse_args()

    asyncio.run(main(cli_args))
