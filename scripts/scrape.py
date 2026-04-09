#!/usr/bin/env python3
"""
Area52 MTG Singles Scraper — CI/headless version.
Phase 1: Fetch all MTG singles via Shopify products.json API.
Phase 2: Enrich in-stock items with real inventory quantities
         by scraping individual product pages.
Output: site/data.csv
"""

import requests
import csv
import time
import os
import re
import json
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
OUTPUT_FILE = os.path.join(ROOT_DIR, "data", "area52_mtg_singles.csv")

BASE_URL = "https://singles.area52.com.au"
API_URL = f"{BASE_URL}/collections/mtg-singles-instock/products.json"
LIMIT = 250
DELAY = 2.0
MAX_RETRIES = 5
RETRY_DELAY = 15

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
})

# ── Phase 1: Fetch product listings via API ─────────────────────────


def fetch_page(page: int) -> list:
    params = {"limit": LIMIT, "page": page}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = SESSION.get(API_URL, params=params, timeout=30)
            if response.status_code == 429:
                wait = RETRY_DELAY * attempt
                print(f"  Rate limited (429). Waiting {wait}s (attempt {attempt}/{MAX_RETRIES})...")
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json().get("products", [])
        except requests.exceptions.Timeout:
            print(f"  Timeout on page {page}, attempt {attempt}/{MAX_RETRIES}. Retrying...")
            time.sleep(RETRY_DELAY)
        except requests.exceptions.ConnectionError:
            print(f"  Connection error on page {page}, attempt {attempt}/{MAX_RETRIES}. Retrying...")
            time.sleep(RETRY_DELAY)
        except requests.exceptions.HTTPError as e:
            print(f"  HTTP error on page {page}: {e}")
            raise
    raise RuntimeError(f"Failed to fetch page {page} after {MAX_RETRIES} attempts.")


def parse_products(products: list) -> list:
    skip_keywords = [
        "near mint", "lightly played", "moderately played",
        "heavily played", "damaged", "foil", "nm", "lp", "mp", "hp",
        "common", "uncommon", "rare", "mythic", "token"
    ]
    rows = []
    for product in products:
        title = product.get("title", "").strip()
        product_type = product.get("product_type", "").strip()
        tags = product.get("tags", [])
        tags_str = ", ".join(tags)

        set_name = ""
        for tag in tags:
            if not any(kw in tag.lower() for kw in skip_keywords):
                set_name = tag.strip()
                break

        for variant in product.get("variants", []):
            rows.append({
                "Card Name": title,
                "Set": set_name,
                "Type": product_type,
                "Condition": variant.get("title", "").strip(),
                "Price (AUD)": f"${variant.get('price', '')}",
                "In Stock": "Yes" if variant.get("available", False) else "No",
                "Qty In Stock": "",
                "Inventory Qty": variant.get("inventory_quantity", ""),
                "SKU": variant.get("sku", ""),
                "Tags": tags_str,
            })
    return rows


def scrape_listings() -> list:
    print("=" * 60)
    print("  Phase 1: Fetching product listings")
    print("=" * 60)

    all_rows = []
    page = 1

    while True:
        print(f"  Fetching page {page}...", end=" ", flush=True)
        products = fetch_page(page)

        if not products:
            print("done (no more products).")
            break

        rows = parse_products(products)
        all_rows.extend(rows)
        print(f"got {len(products)} products ({len(rows)} variants). Total: {len(all_rows)}")

        if len(products) < LIMIT:
            break

        page += 1
        time.sleep(DELAY)

    in_stock = sum(1 for r in all_rows if r["In Stock"] == "Yes")
    print(f"\n  Listings done: {len(all_rows)} variants, {in_stock} in stock.\n")
    return all_rows


# ── Phase 2: Enrich with real quantities ─────────────────────────────


def title_to_handle(title):
    h = title.lower()
    h = re.sub(r'[^a-z0-9]+', '-', h)
    return h.strip('-')


def parse_loose_json(raw):
    """Parse JSON that may have trailing commas."""
    return json.loads(re.sub(r',\s*([}\]])', r'\1', raw))


def fetch_qty_map(handle):
    """Fetch one product page and return {sku: qty}."""
    url = f"{BASE_URL}/products/{handle}"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = SESSION.get(url, timeout=20)
            if resp.status_code == 404:
                return {}
            if resp.status_code == 429:
                wait = RETRY_DELAY * attempt
                print(f"\n    Rate limited. Waiting {wait}s...", flush=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()

            scripts = re.findall(r'<script[^>]*>(.*?)</script>', resp.text, re.DOTALL)
            target_block = next((s for s in scripts if 'variantsInventoryQty' in s), None)
            if not target_block:
                return {}

            m = re.search(r'const variantsInventoryQty = (\{.*?\});', target_block, re.DOTALL)
            if not m:
                return {}
            qty_by_id = parse_loose_json(m.group(1))

            variant_matches = re.findall(
                r'\{"id":(\d+),"title":"([^"]+)","option1":[^,]+,"option2":[^,]+,"option3":[^,]+,"sku":"([^"]*)"',
                target_block
            )

            seen = set()
            sku_qty = {}
            for vid, title, sku in variant_matches:
                if vid in seen or not sku:
                    continue
                seen.add(vid)
                sku_qty[sku] = int(qty_by_id.get(vid, 0))

            return sku_qty

        except requests.exceptions.Timeout:
            print(f"\n    Timeout (attempt {attempt}/{MAX_RETRIES}), retrying...", flush=True)
            time.sleep(RETRY_DELAY)
        except requests.exceptions.ConnectionError:
            print(f"\n    Connection error (attempt {attempt}/{MAX_RETRIES}), retrying...", flush=True)
            time.sleep(RETRY_DELAY)
        except Exception as e:
            print(f"\n    Error for {handle}: {e}", flush=True)
            return {}
    return {}


def enrich_quantities(rows: list) -> list:
    print("=" * 60)
    print("  Phase 2: Fetching real inventory quantities")
    print("=" * 60)

    # Build handle -> set of SKUs (in-stock only)
    handle_to_skus = {}
    for row in rows:
        if row["In Stock"] != "Yes":
            continue
        handle = title_to_handle(row["Card Name"])
        sku = row.get("SKU", "").strip()
        if sku:
            handle_to_skus.setdefault(handle, set()).add(sku)

    total = len(handle_to_skus)
    print(f"  Unique product pages to fetch: {total:,}\n")

    sku_qty = {}
    for idx, handle in enumerate(handle_to_skus, 1):
        print(f"  [{idx}/{total}] {handle[:55]}...", end=" ", flush=True)

        qty_map = fetch_qty_map(handle)
        if qty_map:
            for sku in handle_to_skus[handle]:
                sku_qty[sku] = qty_map.get(sku, 0)
            in_stock_qty = sum(qty_map.get(s, 0) for s in handle_to_skus[handle])
            print(f"qty={in_stock_qty}", flush=True)
        else:
            print("(no data)", flush=True)

        if idx % 100 == 0:
            pct = idx / total * 100
            print(f"  --- {idx}/{total} ({pct:.1f}%) ---")

        time.sleep(DELAY)

    # Apply quantities to rows
    for row in rows:
        sku = row.get("SKU", "").strip()
        if sku in sku_qty:
            row["Qty In Stock"] = str(sku_qty[sku])

    filled = sum(1 for r in rows if r.get("Qty In Stock", ""))
    print(f"\n  Quantities enriched: {filled:,} SKUs with qty data.\n")
    return rows


# ── Output ───────────────────────────────────────────────────────────


def write_csv(rows: list):
    fieldnames = ["Card Name", "Set", "Type", "Condition", "Price (AUD)",
                  "In Stock", "Qty In Stock", "Inventory Qty", "SKU", "Tags"]
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    print()
    print(f"  Area52 MTG Singles Scraper + Qty Enricher (CI)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    rows = scrape_listings()
    rows = enrich_quantities(rows)
    write_csv(rows)

    in_stock = sum(1 for r in rows if r["In Stock"] == "Yes")
    print("=" * 60)
    print(f"  Done! CSV saved to: {OUTPUT_FILE}")
    print(f"  Total variants  : {len(rows)}")
    print(f"  In stock        : {in_stock}")
    print("=" * 60)


if __name__ == "__main__":
    main()
