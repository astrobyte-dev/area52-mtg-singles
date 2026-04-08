#!/usr/bin/env python3
"""
Area52 MTG Quantity Enricher (v3 - properly fixed)
Reads area52_mtg_singles.csv, fetches real inventory quantities for
in-stock listings, writes area52_mtg_singles_with_qty.csv.

Run from the same folder as area52_mtg_singles.csv.
Progress is saved every 25 products so it can resume if interrupted.
"""

import requests, csv, json, time, os, re
from datetime import datetime

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV     = os.path.join(SCRIPT_DIR, "area52_mtg_singles.csv")
OUTPUT_CSV    = os.path.join(SCRIPT_DIR, "area52_mtg_singles_with_qty.csv")
PROGRESS_FILE = os.path.join(SCRIPT_DIR, "area52_qty_progress.json")

BASE_URL   = "https://singles.area52.com.au"
DELAY      = 1.5
MAX_RETRY  = 4
RETRY_WAIT = 15


def parse_loose_json(raw):
    """Parse JSON that may have trailing commas (valid JS, not valid JSON)."""
    return json.loads(re.sub(r',\s*([}\]])', r'\1', raw))


def fetch_qty_map(handle):
    """
    Fetch one product page and return {sku: qty} for that product only.
    Extracts data from the FIRST script block containing variantsInventoryQty,
    which belongs to the target product (not the recommended products sidebar).
    """
    url = f"{BASE_URL}/products/{handle}"
    for attempt in range(1, MAX_RETRY + 1):
        try:
            resp = requests.get(url, timeout=20)
            if resp.status_code == 404:
                return {}
            if resp.status_code == 429:
                wait = RETRY_WAIT * attempt
                print(f"\n    Rate limited. Waiting {wait}s...", flush=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()

            # Find FIRST script block containing variantsInventoryQty
            # (this belongs to the target product, not the sidebar products)
            scripts = re.findall(r'<script[^>]*>(.*?)</script>', resp.text, re.DOTALL)
            target_block = next((s for s in scripts if 'variantsInventoryQty' in s), None)
            if not target_block:
                return {}

            # Extract qty map: {variant_id_str: qty_str}
            m = re.search(r'const variantsInventoryQty = (\{.*?\});', target_block, re.DOTALL)
            if not m:
                return {}
            qty_by_id = parse_loose_json(m.group(1))

            # Extract variants from THIS block only (not the whole page)
            # Each variant looks like: {"id":12345,"title":"Near Mint","option1":...,"sku":"XXX"
            variant_matches = re.findall(
                r'\{"id":(\d+),"title":"([^"]+)","option1":[^,]+,"option2":[^,]+,"option3":[^,]+,"sku":"([^"]*)"',
                target_block
            )

            # Deduplicate (same variant can appear twice in the block)
            seen = set()
            sku_qty = {}
            for vid, title, sku in variant_matches:
                if vid in seen or not sku:
                    continue
                seen.add(vid)
                sku_qty[sku] = int(qty_by_id.get(vid, 0))

            return sku_qty

        except requests.exceptions.Timeout:
            print(f"\n    Timeout (attempt {attempt}/{MAX_RETRY}), retrying...", flush=True)
            time.sleep(RETRY_WAIT)
        except requests.exceptions.ConnectionError:
            print(f"\n    Connection error (attempt {attempt}/{MAX_RETRY}), retrying...", flush=True)
            time.sleep(RETRY_WAIT)
        except Exception as e:
            print(f"\n    Error for {handle}: {e}", flush=True)
            return {}
    return {}


def title_to_handle(title):
    h = title.lower()
    h = re.sub(r'[^a-z0-9]+', '-', h)
    return h.strip('-')


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        print(f"  Found saved progress: {PROGRESS_FILE}")
        ans = input("  Resume from where it left off? (y/n): ").strip().lower()
        if ans == "y":
            with open(PROGRESS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            print(f"  Resuming from {data['last_completed']} done, {len(data['sku_qty'])} SKUs enriched.\n")
            return set(data["done_handles"]), data["sku_qty"]
    return set(), {}


def save_progress(done_handles, sku_qty):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "done_handles": list(done_handles),
            "last_completed": len(done_handles),
            "sku_qty": sku_qty
        }, f)


def main():
    print("=" * 60)
    print("  Area52 MTG Quantity Enricher v3")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    if not os.path.exists(INPUT_CSV):
        print(f"  ERROR: Cannot find {INPUT_CSV}")
        return

    with open(INPUT_CSV, encoding="utf-8") as f:
        orig_rows = list(csv.DictReader(f))
    print(f"  Loaded {len(orig_rows):,} rows from CSV.")

    # Build handle -> set of SKUs (in-stock only)
    handle_to_skus = {}
    for row in orig_rows:
        if row.get("In Stock", "").strip() != "Yes":
            continue
        handle = title_to_handle(row["Card Name"])
        sku    = row.get("SKU", "").strip()
        if sku:
            handle_to_skus.setdefault(handle, set()).add(sku)

    total = len(handle_to_skus)
    print(f"  Unique product pages to fetch: {total:,}")
    print()

    done_handles, sku_qty = load_progress()
    remaining = [h for h in handle_to_skus if h not in done_handles]
    print(f"  Remaining: {len(remaining):,}  |  Already done: {len(done_handles):,}")
    print()

    try:
        for idx, handle in enumerate(remaining, 1):
            done_count = len(done_handles) + idx
            print(f"  [{done_count}/{total}] {handle[:55]}...", end=" ", flush=True)

            qty_map = fetch_qty_map(handle)

            if qty_map:
                for sku in handle_to_skus[handle]:
                    sku_qty[sku] = qty_map.get(sku, 0)
                in_stock_qty = sum(qty_map.get(s, 0) for s in handle_to_skus[handle])
                print(f"qty={in_stock_qty}", flush=True)
            else:
                for sku in handle_to_skus[handle]:
                    if sku not in sku_qty:
                        sku_qty[sku] = -1
                print("(no data)", flush=True)

            done_handles.add(handle)

            if idx % 25 == 0:
                save_progress(done_handles, sku_qty)
                pct = done_count / total * 100
                print(f"  --- Progress saved ({done_count}/{total}, {pct:.1f}%) ---")

            time.sleep(DELAY)

    except KeyboardInterrupt:
        print("\n\n  Interrupted. Saving progress...")

    save_progress(done_handles, sku_qty)
    print(f"\n  Progress saved. {len(done_handles):,}/{total:,} pages done.")

    # Write enriched CSV
    fieldnames = list(orig_rows[0].keys())
    if "Qty In Stock" not in fieldnames:
        ins = fieldnames.index("In Stock") + 1
        fieldnames.insert(ins, "Qty In Stock")

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in orig_rows:
            sku = row.get("SKU", "").strip()
            raw = sku_qty.get(sku, "")
            row["Qty In Stock"] = "" if raw == -1 else (str(raw) if raw != "" else "")
            writer.writerow(row)

    filled = sum(1 for r in orig_rows
                 if r.get("In Stock") == "Yes"
                 and sku_qty.get(r.get("SKU","").strip(), "") not in ("", -1))
    print()
    print("=" * 60)
    print(f"  Output: {OUTPUT_CSV}")
    print(f"  In-stock SKUs with qty: {filled:,}")
    print("=" * 60)

    if len(done_handles) >= total and os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
        print("  Progress file cleaned up.")


if __name__ == "__main__":
    main()
