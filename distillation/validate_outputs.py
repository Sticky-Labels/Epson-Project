#!/usr/bin/env python3
"""
distillation/validate_outputs.py — Priority 4 of the Epson receipt-parsing project
====================================================================================
Loads processed_predictions.json (output of distillation/test.py) and runs a
structured quality check on every receipt, then prints a per-receipt report and
an overall summary score.

Checks performed per receipt:
  1. check_number    — must be a 6-digit numeric string
  2. date            — must be in MM/DD/YY format
  3. order_items     — must be non-empty; each item_name must be a known Dino's
                       menu item (or close to one — exact matches + known abbrev
                       expansions from fix_item_names())
  4. customer_name   — present (not null); a warning if absent but not a failure
  5. table_number    — present (not null); warning if absent

NOTE: total_amount is intentionally excluded from all quality metrics.
This is a known data collection limitation: the Wireshark capture only sees
kitchen order tickets sent over port 9100. The dollar total is printed on the
separate customer receipt and is never transmitted over this port.

Usage:
    python validate_outputs.py
    python validate_outputs.py --input path/to/processed_predictions.json
    python validate_outputs.py --verbose          # show full item lists
"""

import json
import re
import sys
import argparse
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Known Dino's menu items — sourced from fix_item_names() in test.py
# This is the authoritative list; if an item_name is in this set it is valid.
# The set covers both canonical names (values in the replacements dict)
# AND common raw forms that pass through fix_item_names() unchanged.
# ---------------------------------------------------------------------------

KNOWN_MENU_ITEMS = {
    # --- Beverages ---
    "Iron City Light", "Michelob Ultra", "Busch Light", "Blake's Cider",
    "Redd's Apple Ale", "Yuengling", "Coors Light", "Crown Peach", "Kahlua",
    "Diet Mountain Dew", "Pinot Grigio",

    # --- Wings ---
    "Wings Small", "Wings Large", "Wings & Fries", "Wing & Fries",
    "100 Wings", "Wings", "Spicy Fried Buffalo Chicken",
    "Sweet & Hot", "Garlic & Butter", "Garlic & Parmesan",
    "Super Lewis", "Slicker", "Hot", "Mild", "BBQ",
    "Lewis", "Blue Cheese", "Celery", "Ranch",

    # --- Sandwiches ---
    "Italian Stallion Sandwich", "Philly Steak Sandwich",
    "Philly Chicken Sandwich", "Buffalo Chicken Sandwich",
    "Chicken Parm Sandwich", "Charbroiled Sandwich",
    "1/2 Buffalo Chicken Sandwich", "Dino Burger Sandwich",
    "Philly Steak", "Philly Chicken",
    "Italian Panini", "Pannini",
    "Clara's Chicken Bacon Ranch", "Matteo's Meatball",
    "Don Corleone", "Gia's Sriracha Slaw Chicken & Swiss",
    "Buffalo Chicken Sandwich", "Chicken Parmesan", "French Dip",

    # --- Burgers ---
    "Gourmet Burger", "Dino Burger",
    "Vegetarian Chipotle Black Bean Burger", "Steakhouse Burger",
    "Maria's Double Cheesy", "Sal's Sriracha Slaw & Swiss",
    "Pepper Jack Mushroom Burger", "Buffalo Bacon Burger",
    "Buffalo Bleu Burger", "Buffalo Chicken Burger",
    "Double Cheesy",

    # --- Platters & Entrees ---
    "Chicken Platter", "Cajun Baked Chicken", "Teriyaki Grilled Chicken",
    "Buffalo Mac & Cheese", "Bacon Mac & Cheese",
    "1/2 Rack Platter", "Full Rack Platter", "Rib & Shrimp Platter",
    "1/2 Rack & Wings", "1/2 Rack & 10 Wings",
    "1/2Rack&Wings",  # compact form seen in receipts
    "OpenTurkyPlatte", "Open Turkey Platter",

    # --- Appetizers ---
    "Basket of Home Fries", "Basket of Skinny Minny Fries",
    "Basket of Chippers", "Basket of Hot Cheese Balls",
    "Bavarian Pretzels & Beer Cheese Dip", "Buffalo Chicken Dip",
    "Spinach & Artichoke Dip", "Awesome Onion Petals",
    "Potato Skins",

    # --- Salads ---
    "Chicken Bacon Ranch Salad", "Buffalo Chicken Salad",
    "Spinach Chicken Salad", "Charbroiled Chicken Salad",
    "Charbroiled Steak Salad", "Chef Salad",

    # --- Sides / Downgrade markers ---
    "Downgrade to Chippers", "Downgrade to Fries",
    "Skinny Fry", "Home Fry", "Cole Slaw",

    # --- Kids / Specials ---
    "kids Meals", "K-Wing&Fry", "Sm Spec Pizza",
    "Quesadilla", "Veal Sand", "Foil Pan",

    # --- Generic item forms seen raw in receipts ---
    "Charbroiled  Sa",   # truncated by printer width — treated as valid
    "ItalStalSandwic",
    "DinoBurgrSandwi",
    "1/2Rack&Wings",
    "ItalStalSandwich",
}

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_DATE_PATTERN = re.compile(r'^\d{1,2}/\d{1,2}/\d{2}$')
_CHECK_PATTERN = re.compile(r'^\d{6}$')


def check_date(date_val: Optional[str]) -> Tuple[bool, str]:
    if date_val is None:
        return False, "date is null"
    if not _DATE_PATTERN.match(str(date_val)):
        return False, f"date '{date_val}' is not MM/DD/YY format"
    return True, "ok"


def check_check_number(check_val: Optional[str]) -> Tuple[bool, str]:
    if check_val is None:
        return False, "check_number is null"
    s = str(check_val).strip()
    if not _CHECK_PATTERN.match(s):
        return False, f"check_number '{s}' is not a 6-digit number"
    return True, "ok"


def check_order_items(items: Optional[list]) -> Tuple[bool, str, List[str]]:
    """Returns (passed, message, list_of_unknown_items)."""
    if not items:
        return False, "order_items is empty or null", []
    if not isinstance(items, list):
        return False, "order_items is not a list", []

    unknown = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("item_name", "") or ""
        name = name.strip()
        if not name:
            continue
        # Check exact membership first, then case-insensitive
        if name not in KNOWN_MENU_ITEMS:
            lower_known = {k.lower() for k in KNOWN_MENU_ITEMS}
            if name.lower() not in lower_known:
                unknown.append(name)

    if unknown:
        return (
            False,
            f"{len(unknown)} unrecognised item name(s): {unknown}",
            unknown,
        )
    return True, f"{len(items)} item(s) — all names recognised", []


# ---------------------------------------------------------------------------
# Per-receipt validation
# ---------------------------------------------------------------------------

def validate_receipt(receipt: Dict, verbose: bool = False) -> Dict:
    """
    Run all checks on a single receipt dict.
    Returns a result dict with per-check pass/fail and an overall score.
    """
    results = {
        "file_id": receipt.get("file_id", "?"),
        "check_number": receipt.get("check_number"),
        "date": receipt.get("date"),
        "customer_name": receipt.get("customer_name"),
        "table_number": receipt.get("table_number"),
        "checks": {},
        "warnings": [],
        "score": 0.0,        # 0.0 – 1.0 (excludes total_amount)
        "passed": False,
    }

    checks = {}

    # --- Mandatory checks ---
    ok, msg = check_check_number(receipt.get("check_number"))
    checks["check_number_6digit"] = {"passed": ok, "message": msg}

    ok, msg = check_date(receipt.get("date"))
    checks["date_format_MM/DD/YY"] = {"passed": ok, "message": msg}

    ok, msg, unknown = check_order_items(receipt.get("order_items"))
    checks["order_items_nonempty_and_valid"] = {
        "passed": ok,
        "message": msg,
        "unknown_items": unknown,
    }

    # --- Warnings (logged but not counted as failures) ---
    if not receipt.get("customer_name"):
        results["warnings"].append("customer_name is null")
    if not receipt.get("table_number"):
        results["warnings"].append("table_number is null")

    results["checks"] = checks

    # Score = fraction of mandatory checks that passed
    total = len(checks)
    passed_count = sum(1 for v in checks.values() if v["passed"])
    results["score"] = round(passed_count / total, 3) if total else 0.0
    results["passed"] = (passed_count == total)

    return results


# ---------------------------------------------------------------------------
# Pretty printer
# ---------------------------------------------------------------------------

def print_receipt_report(result: Dict, verbose: bool = False) -> None:
    status = "✅ PASS" if result["passed"] else "❌ FAIL"
    check_num = result.get("check_number") or "?"
    date = result.get("date") or "?"
    name = result.get("customer_name") or "(null)"
    score_pct = int(result["score"] * 100)

    print(f"\n  Receipt file_id={result['file_id']}  check#{check_num}  "
          f"date={date}  server={name}")
    print(f"  {status}  score={score_pct}%")

    for check_name, info in result["checks"].items():
        icon = "  ✓" if info["passed"] else "  ✗"
        print(f"  {icon}  {check_name}: {info['message']}")
        if not info["passed"] and info.get("unknown_items") and verbose:
            for item in info["unknown_items"]:
                print(f"        • unrecognised: '{item}'")

    for warning in result["warnings"]:
        print(f"  ⚠   {warning}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Validate processed_predictions.json against Dino's menu and schema rules.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Note: total_amount is intentionally excluded from all checks.
It is a known data collection limitation (kitchen tickets on port 9100
never contain the dollar total — that is printed on the customer receipt only).
""",
    )
    parser.add_argument(
        "--input",
        default="processed_predictions.json",
        metavar="FILE",
        help="Path to processed_predictions.json (default: ./processed_predictions.json)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show full item lists for unrecognised names",
    )
    args = parser.parse_args()

    # Load file
    try:
        with open(args.input, "r", encoding="utf-8") as fh:
            predictions = json.load(fh)
    except FileNotFoundError:
        print(f"❌ File not found: {args.input}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error in {args.input}: {e}")
        sys.exit(1)

    if not isinstance(predictions, list):
        print("❌ Expected a JSON array at the top level of processed_predictions.json")
        sys.exit(1)

    print(f"\n{'='*60}")
    print("RECEIPT OUTPUT VALIDATION REPORT")
    print(f"  Source: {args.input}")
    print(f"  Total receipts: {len(predictions)}")
    print(f"{'='*60}")
    print("""
NOTE: total_amount is excluded from all quality metrics.
      This is a known data collection limitation, not a model failure.
      See project README for details.
""")

    # Run per-receipt validation
    all_results = []
    for receipt in predictions:
        result = validate_receipt(receipt, verbose=args.verbose)
        all_results.append(result)
        print_receipt_report(result, verbose=args.verbose)

    # --- Overall summary ---
    total = len(all_results)
    passed = sum(1 for r in all_results if r["passed"])
    avg_score = sum(r["score"] for r in all_results) / total if total else 0.0
    scores_by_check = {}
    for check_name in ["check_number_6digit", "date_format_MM/DD/YY", "order_items_nonempty_and_valid"]:
        n_passed = sum(1 for r in all_results if r["checks"].get(check_name, {}).get("passed"))
        scores_by_check[check_name] = n_passed

    all_unknown = []
    for r in all_results:
        items_check = r["checks"].get("order_items_nonempty_and_valid", {})
        all_unknown.extend(items_check.get("unknown_items", []))

    null_customer = sum(1 for r in all_results if "customer_name is null" in r.get("warnings", []))
    null_table    = sum(1 for r in all_results if "table_number is null"  in r.get("warnings", []))

    print(f"\n{'='*60}")
    print("OVERALL SUMMARY")
    print(f"{'='*60}")
    print(f"  Receipts validated         : {total}")
    print(f"  Fully passing              : {passed}/{total} "
          f"({'100' if total == 0 else str(round(passed/total*100))}%)")
    print(f"  Average score              : {avg_score*100:.1f}%")
    print()
    print("  Per-check pass rates:")
    for cname, n in scores_by_check.items():
        print(f"    {cname:<40} {n}/{total} ({round(n/total*100) if total else 0}%)")
    print()
    print("  Warnings (not failures):")
    print(f"    Missing customer_name    : {null_customer}/{total}")
    print(f"    Missing table_number     : {null_table}/{total}")
    print()
    if all_unknown:
        from collections import Counter
        freq = Counter(all_unknown).most_common(10)
        print(f"  ⚠  Unrecognised item names ({len(all_unknown)} total, top 10):")
        for name, count in freq:
            print(f"      {count:3}×  '{name}'")
    else:
        print("  ✅ No unrecognised item names detected")
    print()

    # Grade
    pct = avg_score * 100
    if pct >= 90:
        grade = "🟢 EXCELLENT"
    elif pct >= 70:
        grade = "🟡 GOOD"
    elif pct >= 50:
        grade = "🟠 FAIR"
    else:
        grade = "🔴 POOR — review model output quality"
    print(f"  Quality grade: {grade}  ({pct:.1f}% average score)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
