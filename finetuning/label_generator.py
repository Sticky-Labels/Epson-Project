#!/usr/bin/env python3
"""
finetuning/label_generator.py
==============================
Generates ESC/POS print commands for Dino's ToGo label system.
Takes parsed receipt JSON (from ollama_inference.py) and prints:
  1. One Checklist Label  (order overview with checkboxes)
  2. One Item Label per item (individual sticky label per menu item)

Spec: Dino's Latrobe PA - ILS Specifications (Sticky Labels LLC, revised 27-Jun-16)
Printer: Epson TM-T88 Re-Stick / Epson L100 — 58mm paper width

Usage:
    python label_generator.py --input results_constrained.json
    python label_generator.py --input results_constrained.json --check 561611
    python label_generator.py --input results_constrained.json --check 561611 --dry-run
    python label_generator.py --input results_constrained.json --printer-ip 192.168.1.50
"""

import json
import socket
import argparse
import sys
from typing import Optional

# ---------------------------------------------------------------------------
# ESC/POS byte constants
# ---------------------------------------------------------------------------

ESC = b'\x1b'
GS  = b'\x1d'

INIT            = ESC + b'@'
BOLD_ON         = ESC + b'E\x01'
BOLD_OFF        = ESC + b'E\x00'
FONT_NORMAL     = GS + b'!\x00'
FONT_DOUBLE_H   = GS + b'!\x10'   # 2x height only
FONT_DOUBLE     = GS + b'!\x11'   # 2x width + 2x height
ALIGN_LEFT      = ESC + b'a\x00'
ALIGN_CENTER    = ESC + b'a\x01'
ALIGN_RIGHT     = ESC + b'a\x02'
REVERSE_ON      = GS + b'B\x01'
REVERSE_OFF     = GS + b'B\x00'
LF              = b'\n'
FEED_LINES      = lambda n: ESC + b'd' + bytes([n])
CUT_PARTIAL     = GS + b'V\x01'

PAPER_WIDTH_CHARS = 32

DEFAULT_PRINTER_IP   = "192.168.1.100"
DEFAULT_PRINTER_PORT = 9100

RESTAURANT_ADDRESS = "3883 ROUTE 30 EAST"
RESTAURANT_CITY    = "Latrobe, PA 15650"
RESTAURANT_PHONE   = "PHONE: (724) 539-2566"
RESTAURANT_WEB     = "www.dinoslatrobe.com"

# ---------------------------------------------------------------------------
# ESC/POS helpers
# ---------------------------------------------------------------------------

def encode(text: str) -> bytes:
    return text.encode('ascii', errors='replace')

def truncate(text: str, max_chars: int = PAPER_WIDTH_CHARS) -> str:
    return text[:max_chars] if text else ""

def separator(char: str = "-") -> bytes:
    return encode(char * PAPER_WIDTH_CHARS) + LF

def checkbox_line(qty: int, item_name: str) -> bytes:
    """☐  1  ItemName — checkbox + quantity + name, bold double size."""
    text = f"  {qty}  {truncate(item_name, PAPER_WIDTH_CHARS - 5)}"
    return (
        FONT_DOUBLE +
        BOLD_ON +
        b'\xfe' +
        encode(text) +
        LF +
        BOLD_OFF +
        FONT_NORMAL
    )

def condiment_line(text: str, indent: int = 4) -> bytes:
    indented = " " * indent + truncate(text, PAPER_WIDTH_CHARS - indent)
    return encode(indented) + LF

def send_to_printer(data: bytes, ip: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(10)
            s.connect((ip, port))
            s.sendall(data)
        return True
    except Exception as e:
        print(f"❌ Printer error: {e}")
        return False

# ---------------------------------------------------------------------------
# Data extraction helpers
# ---------------------------------------------------------------------------

def format_date_full(date_str: Optional[str]) -> str:
    """Convert MM/DD/YY to MM/DD/YYYY for display."""
    if not date_str:
        return ""
    parts = date_str.split('/')
    if len(parts) == 3 and len(parts[2]) == 2:
        parts[2] = "20" + parts[2]
    return "/".join(parts)

def clean_table_number(table: Optional[str]) -> str:
    """Strip 'Table:' prefix if the model accidentally included it."""
    if not table:
        return ""
    cleaned = table.strip()
    if cleaned.lower().startswith("table:"):
        cleaned = cleaned[6:].strip()
    return cleaned

def clean_item_name(item_name: str) -> str:
    """Strip leading whole-number quantity if the model accidentally included it.
    e.g. '1 Wings Large' → 'Wings Large'
    but '1/2 Rack&Wings' → '1/2 Rack&Wings' (fraction, not a quantity)
    """
    if not item_name:
        return ""
    import re
    # Only strip if it's a plain integer followed by a space, not a fraction (1/2, 3/4 etc)
    return re.sub(r'^\d+(?!/)\s+', '', item_name.strip())

def get_customer_name(receipt: dict) -> Optional[str]:
    """
    Customer name from receipt['customer_name'].
    Exception 561633 type: if no customer name but table number exists,
    use table number as customer name.
    """
    customer = receipt.get("customer_name")
    table    = clean_table_number(receipt.get("table_number") or "")
    if not customer and table:
        return f"Table: {table}"
    return customer or None

def get_pickup_time(receipt: dict) -> Optional[str]:
    return receipt.get("pickup_time") or None

def get_order_items(receipt: dict) -> list:
    """Return real order items — filter out ! marker lines."""
    items = receipt.get("order_items") or []
    return [
        item for item in items
        if item.get("item_name") and not item["item_name"].startswith("!")
    ]

def filter_modifiers(modifiers: list) -> list:
    """Filter out ! marker lines from modifiers (customer name / pickup time markers)."""
    return [m for m in (modifiers or []) if m and not str(m).startswith("!")]

# ---------------------------------------------------------------------------
# Checklist label
# ---------------------------------------------------------------------------

def build_checklist(receipt: dict) -> bytes:
    """
    Layout per spec:
        [LOGO]
        SPORTS LOUNGE  (plain text, centered)
        [DINO]         (reverse text bar, only DINO)
        MM/DD/YYYY          Pick Up Time
        # XXXXXX            HH:MM AM
        Table:
        --------------------------------
        ☐  1  ItemName  (bold, double)
            Condiment
        ================================
        Bag ___________  Of ________
        Packed By ______________________
        [address]
        Thank You
    """
    buf = bytearray()
    buf += INIT

    # --- Logo placeholder ---
    buf += ALIGN_CENTER
    buf += BOLD_ON
    buf += encode("[ DINO'S LOGO ]") + LF
    buf += BOLD_OFF
    buf += LF

    # --- "SPORTS LOUNGE" in plain text above the DINO bar ---
    buf += ALIGN_CENTER
    buf += BOLD_ON
    buf += encode("SPORTS LOUNGE") + LF
    buf += BOLD_OFF

    # --- "DINO" in reverse text bar (only DINO, not SPORTS LOUNGE) ---
    buf += REVERSE_ON
    buf += BOLD_ON
    buf += FONT_DOUBLE
    dino_line = "DINO".center(PAPER_WIDTH_CHARS)
    buf += encode(dino_line) + LF
    buf += FONT_NORMAL
    buf += BOLD_OFF
    buf += REVERSE_OFF

    # --- Header info ---
    buf += ALIGN_LEFT

    date      = format_date_full(receipt.get("date"))
    pickup    = get_pickup_time(receipt)
    check_num = receipt.get("check_number") or ""
    table     = receipt.get("table_number") or ""

    # Date left, "Pick Up Time" right-aligned on same line
    pickup_label = "Pick Up Time"
    pad = PAPER_WIDTH_CHARS - len(date) - len(pickup_label)
    buf += encode(date + " " * max(1, pad) + pickup_label) + LF

    # Check number left, actual pickup time right-aligned
    pickup_val = pickup if pickup else ""
    pad2 = PAPER_WIDTH_CHARS - len(f"# {check_num}") - len(pickup_val)
    buf += encode(f"# {check_num}" + " " * max(1, pad2) + pickup_val) + LF

    buf += encode(f"Table: {clean_table_number(table)}") + LF
    buf += separator("-")

    # --- Order items with checkboxes (NO customer name reverse bar on checklist) ---
    items = get_order_items(receipt)
    for item in items:
        qty       = item.get("quantity") or 1
        item_name = clean_item_name(item.get("item_name") or "")
        modifiers = filter_modifiers(item.get("modifiers") or [])

        buf += checkbox_line(qty, item_name)
        for mod in modifiers:
            buf += condiment_line(str(mod))

    buf += separator("=")

    # --- Footer ---
    buf += LF
    buf += encode("Bag") + encode(" " * 12) + encode("Of") + encode(" " * 8) + LF
    buf += LF
    buf += encode("Packed By ") + encode("_" * 22) + LF
    buf += LF
    buf += ALIGN_CENTER
    buf += encode(RESTAURANT_ADDRESS) + LF
    buf += encode(RESTAURANT_CITY) + LF
    buf += encode(RESTAURANT_PHONE) + LF
    buf += encode(RESTAURANT_WEB) + LF
    buf += LF
    buf += BOLD_ON
    buf += FONT_DOUBLE
    buf += encode("Thank You") + LF
    buf += FONT_NORMAL
    buf += BOLD_OFF

    buf += FEED_LINES(4)
    buf += CUT_PARTIAL

    return bytes(buf)

# ---------------------------------------------------------------------------
# Item label
# ---------------------------------------------------------------------------

def build_item_label(receipt: dict, item: dict, sequence: int, total_items: int) -> bytes:
    """
    Layout per spec:
        DINO  (centered bold)
        Order XXXXXX         N of X
        Pick Up Time HH:MM AM
        --------------------------------
        Customer Name (large bold)
        --------------------------------
        Item Name (large bold)
        Condiment
        Condiment
    """
    buf = bytearray()
    buf += INIT
    buf += ALIGN_CENTER
    buf += BOLD_ON
    buf += FONT_DOUBLE
    buf += encode("DINO") + LF
    buf += FONT_NORMAL
    buf += BOLD_OFF
    buf += LF

    buf += ALIGN_LEFT
    check_num  = receipt.get("check_number") or ""
    pickup     = get_pickup_time(receipt)
    customer   = get_customer_name(receipt)
    item_name  = clean_item_name(item.get("item_name") or "")
    modifiers  = filter_modifiers(item.get("modifiers") or [])

    seq_str    = f"{sequence} of {total_items}"
    order_line = f"Order {check_num}"
    pad        = PAPER_WIDTH_CHARS - len(order_line) - len(seq_str)
    buf += encode(order_line + " " * max(1, pad) + seq_str) + LF

    pickup_str = f"Pick Up Time {pickup}" if pickup else "Pick Up Time"
    buf += encode(truncate(pickup_str)) + LF
    buf += separator("-")

    if customer:
        buf += BOLD_ON
        buf += FONT_DOUBLE_H
        buf += encode(truncate(customer.upper())) + LF
        buf += FONT_NORMAL
        buf += BOLD_OFF

    buf += separator("-")
    buf += BOLD_ON
    buf += FONT_DOUBLE
    buf += encode(truncate(item_name)) + LF
    buf += FONT_NORMAL
    buf += BOLD_OFF

    for mod in modifiers:
        if mod:
            buf += condiment_line(str(mod))

    buf += FEED_LINES(4)
    buf += CUT_PARTIAL

    return bytes(buf)

# ---------------------------------------------------------------------------
# Main print job
# ---------------------------------------------------------------------------

def print_order(receipt: dict, printer_ip: str = DEFAULT_PRINTER_IP,
                printer_port: int = DEFAULT_PRINTER_PORT, dry_run: bool = False) -> bool:
    check_num = receipt.get("check_number") or "unknown"
    items     = get_order_items(receipt)

    if not items:
        print(f"⚠️  Check#{check_num}: no order items found, skipping")
        return False

    expanded = []
    for item in items:
        qty = int(item.get("quantity") or 1)
        for _ in range(qty):
            expanded.append(item)

    total = len(expanded)
    print(f"\n📋 Check#{check_num} — {total} item label(s) + 1 checklist")

    checklist_data = build_checklist(receipt)
    item_data_list = [
        build_item_label(receipt, item, i + 1, total)
        for i, item in enumerate(expanded)
    ]

    if dry_run:
        print(f"\n--- CHECKLIST ({len(checklist_data)} bytes) ---")
        print(checklist_data.hex(' '))
        for i, data in enumerate(item_data_list):
            print(f"\n--- ITEM LABEL {i+1}/{total} ({len(data)} bytes) ---")
            print(data.hex(' '))
        return True

    print(f"  Sending checklist...", end=" ")
    ok = send_to_printer(checklist_data, printer_ip, printer_port)
    print("✅" if ok else "❌")

    for i, data in enumerate(item_data_list):
        print(f"  Sending item label {i+1}/{total}...", end=" ")
        ok = send_to_printer(data, printer_ip, printer_port)
        print("✅" if ok else "❌")

    return True

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate and print Dino's ToGo labels via ESC/POS")
    parser.add_argument("--input",        required=True)
    parser.add_argument("--check",        default=None)
    parser.add_argument("--printer-ip",   default=DEFAULT_PRINTER_IP)
    parser.add_argument("--printer-port", type=int, default=DEFAULT_PRINTER_PORT)
    parser.add_argument("--dry-run",      action="store_true")
    args = parser.parse_args()

    try:
        with open(args.input) as f:
            data = json.load(f)
        receipts = data if isinstance(data, list) else data.get("data", [])
    except FileNotFoundError:
        print(f"❌ File not found: {args.input}")
        sys.exit(1)

    if args.check:
        receipts = [r for r in receipts if str(r.get("check_number")) == str(args.check)]
        if not receipts:
            print(f"❌ Check#{args.check} not found in {args.input}")
            sys.exit(1)

    print(f"Loaded {len(receipts)} receipt(s) from {args.input}")
    if args.dry_run:
        print("DRY RUN — output is hex, nothing sent to printer\n")

    for receipt in receipts:
        if receipt.get("error"):
            continue
        print_order(receipt, printer_ip=args.printer_ip,
                    printer_port=args.printer_port, dry_run=args.dry_run)

    print("\n✅ Done")

if __name__ == "__main__":
    main()
