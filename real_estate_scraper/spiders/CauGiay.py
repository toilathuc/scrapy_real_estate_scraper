import argparse
import asyncio
import csv
import datetime as dt
import json
import random
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
try:
    from playwright.async_api import async_playwright
except ImportError:  # pragma: no cover
    async_playwright = None

try:
    from crawl4ai import AsyncWebCrawler
except ImportError:  # pragma: no cover
    AsyncWebCrawler = None


class _FallbackResult:
    def __init__(self, success, html):
        self.success = success
        self.html = html


class _FallbackAsyncWebCrawler:
    def __init__(self, timeout=30):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def arun(self, url):
        def _fetch():
            return requests.get(
                url,
                timeout=self.timeout,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 "
                    "Safari/537.36"
                },
            )

        try:
            response = await asyncio.to_thread(_fetch)
            if response.status_code >= 400:
                return _FallbackResult(False, "")
            return _FallbackResult(True, response.text)
        except Exception:
            return _FallbackResult(False, "")


class _PlaywrightFallbackCrawler:
    def __init__(self, timeout=45000):
        self.timeout = timeout
        self._pw = None
        self._browser = None
        self._context = None

    async def __aenter__(self):
        if async_playwright is None:
            raise RuntimeError("playwright is not installed")

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 "
                "Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            java_script_enabled=True,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        return False

    async def arun(self, url):
        page = await self._context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
            await page.wait_for_timeout(random.randint(1200, 2500))
            html = await page.content()
            return _FallbackResult(True, html)
        except Exception:
            return _FallbackResult(False, "")
        finally:
            await page.close()


BASE_URL = "https://batdongsan.com.vn"
DEFAULT_LISTING_URL = "https://batdongsan.com.vn/nha-dat-ban"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().with_name("crawler_config.json")
DEFAULT_STATE_PATH = Path(__file__).resolve().with_name("crawler_state.json")
DEFAULT_DEBUG_DIR = Path(__file__).resolve().parents[1] / "output" / "debug_challenges"
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

CHALLENGE_MARKERS = [
    "just a moment",
    "checking your browser",
    "cf-chl",
    "cloudflare",
    "attention required",
]


def _normalize_space(value):
    if not value:
        return "N/A"
    return re.sub(r"\s+", " ", str(value)).strip()


def _is_challenge_html(html):
    text = (html or "").lower()
    return any(marker in text for marker in CHALLENGE_MARKERS)


def _safe_part(value):
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_") or "unknown"


def _save_challenge_html(debug_dir, label, url, attempt, html):
    if not debug_dir or not html:
        return None

    debug_dir = Path(debug_dir)
    debug_dir.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    parsed = urlparse(url)
    slug = _safe_part(parsed.path.split("/")[-1] or parsed.path)
    label_slug = _safe_part(label.lower().replace(" ", "_"))
    file_name = f"{ts}_{label_slug}_a{attempt}_{slug}.html"
    file_path = debug_dir / file_name
    file_path.write_text(html, encoding="utf-8")
    return file_path


def _blocked_row(url, reason="challenge"):
    return {
        "source": "batdongsan.com.vn",
        "scraped_at": dt.datetime.now(dt.UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "title": "N/A",
        "description": "N/A",
        "price": "N/A",
        "price_raw": "N/A",
        "city": "N/A",
        "district": "N/A",
        "ward": "N/A",
        "address": "N/A",
        "property_size": "N/A",
        "property_size_raw": "N/A",
        "property_type": "N/A",
        "bedrooms": "N/A",
        "bathrooms": "N/A",
        "amenities": "",
        "currency": "VND",
        "listing_id": _extract_listing_id(url),
        "crawl_status": reason,
        "listing_url": url,
    }


async def _fetch_with_challenge_retry(
    crawler,
    url,
    label,
    debug_dir=None,
    max_attempts=4,
    retry_wait_min=2.0,
    retry_wait_max=4.0,
    challenge_wait_min=8.0,
    challenge_wait_max=14.0,
):
    last_res = _FallbackResult(False, "")
    challenge_seen = False

    for attempt in range(1, max_attempts + 1):
        res = await crawler.arun(url=url)
        last_res = res
        success = getattr(res, "success", False)
        html = getattr(res, "html", "")

        if not success:
            if attempt < max_attempts:
                wait_for = random.uniform(retry_wait_min, retry_wait_max)
                print(f"[{label}] attempt {attempt}/{max_attempts} failed, retry in {wait_for:.1f}s")
                await asyncio.sleep(wait_for)
            continue

        if _is_challenge_html(html):
            challenge_seen = True
            saved = _save_challenge_html(debug_dir, label, url, attempt, html)
            if saved:
                print(f"[{label}] challenge snapshot saved: {saved}")
            if attempt < max_attempts:
                wait_for = random.uniform(challenge_wait_min, challenge_wait_max)
                print(f"[{label}] challenge detected on attempt {attempt}/{max_attempts}, retry in {wait_for:.1f}s")
                await asyncio.sleep(wait_for)
            continue

        return res, False

    return last_res, challenge_seen


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


def _state_key(start_url, output_file):
    return f"{start_url}|{Path(output_file).resolve()}"


def _load_state(state_path):
    if not state_path.exists():
        return {"runs": {}}

    with state_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        return {"runs": {}}

    runs = data.get("runs")
    if not isinstance(runs, dict):
        data["runs"] = {}

    return data


def _save_state(state_path, state_data):
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w", encoding="utf-8") as f:
        json.dump(state_data, f, ensure_ascii=False, indent=2)


def _get_resume_page(state_data, start_url, output_file):
    key = _state_key(start_url, output_file)
    run = state_data.get("runs", {}).get(key, {})
    if not isinstance(run, dict):
        return 1

    next_page = run.get("next_page", 1)
    if isinstance(next_page, int) and next_page >= 1:
        return next_page
    return 1


def _update_resume_page(state_data, start_url, output_file, next_page):
    state_data.setdefault("runs", {})
    key = _state_key(start_url, output_file)
    state_data["runs"][key] = {
        "start_url": start_url,
        "output_file": str(Path(output_file).resolve()),
        "next_page": max(1, int(next_page)),
        "updated_at": dt.datetime.now(dt.UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    }


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
    crawler,
    start_url,
    start_page,
    max_pages,
    max_items,
    page_delay_min,
    page_delay_max,
    debug_dir,
    output_file,
):
    collected = []
    seen = set()
    last_successful_page = start_page - 1

    for page in range(start_page, start_page + max_pages):
        if max_items and len(collected) >= max_items:
            break

        page_url = _listing_page_url(start_url, page)
        res, challenge_seen = await _fetch_with_challenge_retry(
            crawler=crawler,
            url=page_url,
            label=f"PAGE {page}",
            debug_dir=debug_dir,
        )
        if not getattr(res, "success", False):
            print(f"[PAGE {page}] FAIL {page_url}")
            continue

        if challenge_seen:
            print(f"[PAGE {page}] blocked by challenge after retries: {page_url}")
            _append_rows([_blocked_row(page_url, "blocked_listing")], output_file)
            continue

        last_successful_page = page

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

    next_page = max(start_page, last_successful_page + 1)
    return collected, next_page


async def _fetch_details(
    crawler, links, output_file, detail_delay_min, detail_delay_max, debug_dir
):
    rows = []
    for idx, link in enumerate(links, 1):
        res, challenge_seen = await _fetch_with_challenge_retry(
            crawler=crawler,
            url=link,
            label=f"DETAIL {idx}",
            debug_dir=debug_dir,
        )
        if not getattr(res, "success", False):
            print(f"[{idx}/{len(links)}] FAIL {link}")
            continue
        if challenge_seen:
            print(f"[{idx}/{len(links)}] CHALLENGE {link}")
            _append_rows([_blocked_row(link, "blocked")], output_file)
            continue
        row = _parse_detail(getattr(res, "html", ""), link)
        rows.append(row)
        _append_rows([row], output_file)
        print(f"[{idx}/{len(links)}] OK   {link}")
        await asyncio.sleep(random.uniform(detail_delay_min, detail_delay_max))
    return rows


async def main(args):
    crawler_cls = AsyncWebCrawler
    crawler_name = "crawl4ai"
    if AsyncWebCrawler is None and async_playwright is not None:
        crawler_cls = _PlaywrightFallbackCrawler
        crawler_name = "playwright-fallback"
        print("crawl4ai is not installed. Falling back to Playwright mode.")
    elif AsyncWebCrawler is None:
        crawler_cls = _FallbackAsyncWebCrawler
        crawler_name = "http-fallback"
        print("crawl4ai/playwright not installed. Falling back to basic HTTP mode.")

    config_path = Path(args.config)
    config = _load_config(config_path)

    start_url = args.start_url or config.get("start_url") or DEFAULT_LISTING_URL
    output_file = Path(args.output)
    state_path = Path(args.state_file)
    debug_dir = Path(args.debug_dir)
    state_data = _load_state(state_path)

    if args.start_page and args.start_page > 0:
        start_page = args.start_page
    elif args.resume:
        start_page = _get_resume_page(state_data, start_url, output_file)
    else:
        start_page = 1

    existing_links = _load_existing_links(output_file) if args.resume else set()
    print(f"Crawler backend: {crawler_name}")
    print(f"Resume mode={args.resume}. Existing links in file={len(existing_links)}")
    print(f"Using start URL: {start_url}")
    print(f"Starting from page: {start_page}")

    async with crawler_cls() as crawler:
        links, next_page = await _collect_listing_links(
            crawler=crawler,
            start_url=start_url,
            start_page=start_page,
            max_pages=args.max_pages,
            max_items=args.max_items,
            page_delay_min=args.page_delay_min,
            page_delay_max=args.page_delay_max,
            debug_dir=debug_dir,
            output_file=output_file,
        )

        links = [x for x in links if x not in existing_links]
        if not links:
            print("No new links to crawl.")
            return

        print(f"Crawling {len(links)} detail pages...")
        rows = await _fetch_details(
            crawler=crawler,
            links=links,
            output_file=output_file,
            detail_delay_min=args.detail_delay_min,
            detail_delay_max=args.detail_delay_max,
            debug_dir=debug_dir,
        )
        _update_resume_page(state_data, start_url, output_file, next_page)
        _save_state(state_path, state_data)
        print(f"Saved resume state. Next run will start at page: {next_page}")
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
    parser.add_argument(
        "--start-page",
        type=int,
        default=None,
        help="Override page to start scanning from (default: resume state or page 1).",
    )
    parser.add_argument(
        "--state-file",
        type=str,
        default=str(DEFAULT_STATE_PATH),
        help="Path to JSON state file used to persist pagination progress.",
    )
    parser.add_argument(
        "--debug-dir",
        type=str,
        default=str(DEFAULT_DEBUG_DIR),
        help="Directory to save HTML snapshots for challenge pages.",
    )
    parser.add_argument("--page-delay-min", type=float, default=1.0)
    parser.add_argument("--page-delay-max", type=float, default=2.0)
    parser.add_argument("--detail-delay-min", type=float, default=0.6)
    parser.add_argument("--detail-delay-max", type=float, default=1.4)
    cli_args = parser.parse_args()

    asyncio.run(main(cli_args))
