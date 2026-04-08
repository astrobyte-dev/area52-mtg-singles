#!/usr/bin/env python3
"""
Area52 MTG Singles Scraper (v3 - fixed resume path)
Fetches all in-stock MTG singles from singles.area52.com.au
using Shopify's built-in products.json API endpoint.

Output: area52_mtg_singles.csv (saved next to this script)
"""

import requests
import csv
import time
import json
import os
from datetime import datetime

# Always save files next to the script, regardless of where Python is run from
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

BASE_URL     = "https://singles.area52.com.au/collections/mtg-singles-instock/products.json"
OUTPUT_FILE  = os.path.join(SCRIPT_DIR, "area52_mtg_singles.csv")
PROGRESS_FILE = os.path.join(SCRIPT_DIR, "area52_scraper_progress.json")

LIMIT        = 250   # Max allowed by Shopify per page
DELAY        = 1.5   # Seconds between requests
MAX_RETRIES  = 5     # Retries per page
RETRY_DELAY  = 10    # Seconds to wait before retrying


def fetch_page(page: int) -> list:
    params = {"limit": LIMIT, "page": page}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(BASE_URL, params=params, timeout=30)
            if response.status_code == 429:
                wait = RETRY_DELAY * attempt
                print(f"\n  Rate limited (429). Waiting {wait}s before retry {attempt}/{MAX_RETRIES}...", flush=True)
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json().get("products", [])
        except requests.exceptions.Timeout:
            print(f"\n  Timeout on page {page}, attempt {attempt}/{MAX_RETRIES}. Retrying in {RETRY_DELAY}s...", flush=True)
            time.sleep(RETRY_DELAY)
        except requests.exceptions.ConnectionError:
            print(f"\n  Connection error on page {page}, attempt {attempt}/{MAX_RETRIES}. Retrying in {RETRY_DELAY}s...", flush=True)
            time.sleep(RETRY_DELAY)
        except requests.exceptions.HTTPError as e:
            print(f"\n  HTTP error on page {page}: {e}")
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
                "Card Name":    title,
                "Set":          set_name,
                "Type":         product_type,
                "Condition":    variant.get("title", "").strip(),
                "Price (AUD)":  f"${variant.get('price', '')}",
                "In Stock":     "Yes" if variant.get("available", False) else "No",
                "Inventory Qty": variant.get("inventory_quantity", ""),
                "SKU":          variant.get("sku", ""),
                "Tags":         tags_str,
            })
    return rows


def save_progress(page: int, rows: list):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_completed_page": page, "rows": rows}, f)
    print(f" [progress saved]", end="", flush=True)


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        print(f"  Found saved progress: {PROGRESS_FILE}")
        answer = input("  Resume from where it left off? (y/n): ").strip().lower()
        if answer == "y":
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            start_page = data["last_completed_page"] + 1
            rows = data["rows"]
            print(f"  Resuming from page {start_page} with {len(rows)} existing rows.\n")
            return start_page, rows
    return 1, []


def write_csv(rows: list):
    fieldnames = ["Card Name", "Set", "Type", "Condition", "Price (AUD)",
                  "In Stock", "Inventory Qty", "SKU", "Tags"]
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    print("=" * 55)
    print("  Area52 MTG Singles Scraper v3")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Script dir: {SCRIPT_DIR}")
    print("=" * 55)
    print()

    start_page, all_rows = load_progress()
    page = start_page

    try:
        while True:
            print(f"  Fetching page {page}...", end=" ", flush=True)
            products = fetch_page(page)

            if not products:
                print("done (no more products).")
                break

            rows = parse_products(products)
            all_rows.extend(rows)
            print(f"got {len(products)} products ({len(rows)} variants). Total: {len(all_rows)}", end=" ")

            save_progress(page, all_rows)
            print()

            if len(products) < LIMIT:
                break

            page += 1
            time.sleep(DELAY)

    except KeyboardInterrupt:
        print("\n\n  Interrupted. Progress saved - re-run and choose 'y' to resume.")
        write_csv(all_rows)
        print(f"  Partial CSV written: {OUTPUT_FILE}")
        return

    except Exception as e:
        print(f"\n\n  Error: {e}")
        print("  Progress saved - re-run and choose 'y' to resume.")
        write_csv(all_rows)
        print(f"  Partial CSV written: {OUTPUT_FILE}")
        return

    write_csv(all_rows)
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)

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
