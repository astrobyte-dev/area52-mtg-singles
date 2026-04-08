#!/usr/bin/env python3
"""
Area52 MTG Singles Scraper — CI/headless version.
Fetches all in-stock MTG singles from singles.area52.com.au
using Shopify's products.json API endpoint.
Output: site/data.csv
"""

import requests
import csv
import time
import os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
OUTPUT_FILE = os.path.join(ROOT_DIR, "site", "data.csv")

BASE_URL = "https://singles.area52.com.au/collections/mtg-singles-instock/products.json"
LIMIT = 250
DELAY = 1.5
MAX_RETRIES = 5
RETRY_DELAY = 10


def fetch_page(page: int) -> list:
    params = {"limit": LIMIT, "page": page}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(BASE_URL, params=params, timeout=30)
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
                "Qty In Stock": variant.get("inventory_quantity", ""),
                "Inventory Qty": variant.get("inventory_quantity", ""),
                "SKU": variant.get("sku", ""),
                "Tags": tags_str,
            })
    return rows


def write_csv(rows: list):
    fieldnames = ["Card Name", "Set", "Type", "Condition", "Price (AUD)",
                  "In Stock", "Qty In Stock", "Inventory Qty", "SKU", "Tags"]
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    print("=" * 55)
    print("  Area52 MTG Singles Scraper (CI)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

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

    write_csv(all_rows)
    in_stock = sum(1 for r in all_rows if r["In Stock"] == "Yes")

    print()
    print("=" * 55)
    print(f"  Done! CSV saved to: {OUTPUT_FILE}")
    print(f"  Total variants  : {len(all_rows)}")
    print(f"  In stock        : {in_stock}")
    print(f"  Out of stock    : {len(all_rows) - in_stock}")
    print("=" * 55)


if __name__ == "__main__":
    main()
