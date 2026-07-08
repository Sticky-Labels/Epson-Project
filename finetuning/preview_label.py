#!/usr/bin/env python3
"""
preview_label.py
================
Renders ESC/POS label output as PNG images for visual preview.

Usage:
    python preview_label.py --input results_train_constrained.json --check 561611
"""

import json
import argparse
import sys
from PIL import Image, ImageDraw, ImageFont

PAPER_WIDTH_PX = 384
PADDING        = 14
LINE_SPACING   = 5
BG_COLOR       = (255, 255, 255)
FG_COLOR       = (0, 0, 0)
REVERSE_BG     = (0, 0, 0)
REVERSE_FG     = (255, 255, 255)

def get_font(size, bold=False):
    candidates = [
        "/System/Library/Fonts/Supplemental/Courier New Bold.ttf" if bold else
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/Library/Fonts/Courier New Bold.ttf" if bold else "/Library/Fonts/Courier New.ttf",
        "/System/Library/Fonts/Courier.dfont",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()

FONT_SM      = get_font(18)
FONT_SM_BOLD = get_font(18, bold=True)
FONT_MD      = get_font(24, bold=True)
FONT_LG      = get_font(30, bold=True)

class LabelRenderer:
    def __init__(self):
        self.lines = []

    def add(self, text="", bold=False, large=False, huge=False,
            reverse=False, center=False, separator=False, indent=0):
        self.lines.append(dict(text=text, bold=bold, large=large, huge=huge,
                               reverse=reverse, center=center,
                               separator=separator, indent=indent))

    def _font_for(self, line):
        if line["huge"]:   return FONT_LG
        if line["large"]:  return FONT_MD
        if line["bold"]:   return FONT_SM_BOLD
        return FONT_SM

    def render(self, output_path: str):
        # Calculate height
        total_h = PADDING * 2
        for line in self.lines:
            f = self._font_for(line)
            _, _, _, h = f.getbbox(line["text"] or " ")
            total_h += h + LINE_SPACING

        img  = Image.new("RGB", (PAPER_WIDTH_PX, total_h), BG_COLOR)
        draw = ImageDraw.Draw(img)
        y = PADDING

        for line in self.lines:
            f    = self._font_for(line)
            text = line["text"] or ""
            _, _, tw, th = f.getbbox(text or " ")
            line_h = th + LINE_SPACING

            if line["separator"]:
                mid = y + line_h // 2
                draw.line([(PADDING, mid), (PAPER_WIDTH_PX - PADDING, mid)],
                          fill=FG_COLOR, width=1)
                y += line_h
                continue

            if line["reverse"]:
                draw.rectangle([(0, y - 2), (PAPER_WIDTH_PX, y + line_h + 2)],
                                fill=REVERSE_BG)
                x = (PAPER_WIDTH_PX - tw) // 2
                draw.text((x, y), text, font=f, fill=REVERSE_FG)
            else:
                if line["center"]:
                    x = (PAPER_WIDTH_PX - tw) // 2
                else:
                    x = PADDING + line["indent"]
                draw.text((x, y), text, font=f, fill=FG_COLOR)

            y += line_h

        img.save(output_path)
        print(f"✅ Saved: {output_path}")


def format_date_full(date_str):
    if not date_str:
        return ""
    parts = date_str.split('/')
    if len(parts) == 3 and len(parts[2]) == 2:
        parts[2] = "20" + parts[2]
    return "/".join(parts)

import re

def clean_table_number(table):
    if not table:
        return ""
    cleaned = table.strip()
    if cleaned.lower().startswith("table:"):
        cleaned = cleaned[6:].strip()
    return cleaned

def clean_item_name(item_name):
    if not item_name:
        return ""
    # Only strip plain integer prefix, not fractions like 1/2
    return re.sub(r'^\d+(?!/)\s+', '', item_name.strip())

def get_customer_name(receipt):
    customer = receipt.get("customer_name")
    table    = clean_table_number(receipt.get("table_number") or "")
    if not customer and table:
        return f"Table: {table}"
    return customer or None

def fix_fraction_item(item):
    modifiers = list(item.get("modifiers") or [])
    item_name = item.get("item_name") or ""
    if modifiers and re.match(r'^\d+/\d+$', str(modifiers[0]).strip()):
        fraction  = modifiers.pop(0)
        item_name = f"{fraction} {item_name}"
        item = dict(item)
        item["item_name"] = item_name
        item["modifiers"] = modifiers
    return item

def get_order_items(receipt):
    items = receipt.get("order_items") or []
    return [
        fix_fraction_item(i) for i in items
        if i.get("item_name") and not i["item_name"].startswith("!")
    ]

def filter_modifiers(modifiers):
    return [m for m in (modifiers or []) if m and not str(m).startswith("!")]


def render_checklist(receipt, output_path):
    r = LabelRenderer()

    date      = format_date_full(receipt.get("date"))
    check_num = receipt.get("check_number") or ""
    table     = receipt.get("table_number") or ""
    pickup    = receipt.get("pickup_time") or ""
    items     = get_order_items(receipt)

    # Logo
    r.add("[ DINO'S LOGO ]", center=True, bold=True)
    r.add()

    # SPORTS LOUNGE plain text, then DINO in reverse bar
    r.add("SPORTS LOUNGE", center=True, bold=True)
    r.add("DINO", reverse=True, huge=True, center=True)

    # Date + Pick Up Time header (two columns)
    pickup_label = "Pick Up Time"
    pad = 32 - len(date) - len(pickup_label)
    r.add(f"{date}{' ' * max(1,pad)}{pickup_label}")

    # Check number + actual pickup time value
    pickup_val = pickup if pickup else ""
    check_str  = f"# {check_num}"
    pad2 = 32 - len(check_str) - len(pickup_val)
    r.add(f"{check_str}{' ' * max(1,pad2)}{pickup_val}")

    r.add(f"Table: {clean_table_number(table)}")
    r.add(separator=True)

    # Items — no customer name reverse bar on checklist
    for item in items:
        qty       = item.get("quantity") or 1
        item_name = clean_item_name(item.get("item_name") or "")
        modifiers = filter_modifiers(item.get("modifiers") or [])
        r.add(f"☐  {qty}  {item_name}", bold=True, large=True)
        for mod in modifiers:
            r.add(str(mod), indent=28)

    r.add(separator=True)
    r.add()
    r.add("Bag             Of")
    r.add()
    r.add("Packed By _____________________")
    r.add()
    r.add("3883 ROUTE 30 EAST", center=True)
    r.add("Latrobe, PA 15650", center=True)
    r.add("PHONE: (724) 539-2566", center=True)
    r.add("www.dinoslatrobe.com", center=True)
    r.add()
    r.add("Thank You", huge=True, center=True)

    r.render(output_path)


def render_item_label(receipt, item, sequence, total, output_path):
    r = LabelRenderer()

    check_num = receipt.get("check_number") or ""
    pickup    = receipt.get("pickup_time") or ""
    customer  = get_customer_name(receipt)
    item_name = clean_item_name(item.get("item_name") or "")
    modifiers = filter_modifiers(item.get("modifiers") or [])

    r.add("DINO", huge=True, center=True)
    r.add()

    seq_str    = f"{sequence} of {total}"
    order_str  = f"Order {check_num}"
    pad        = 32 - len(order_str) - len(seq_str)
    r.add(f"{order_str}{' ' * max(1, pad)}{seq_str}")

    pickup_str = f"Pick Up Time {pickup}" if pickup else "Pick Up Time"
    r.add(pickup_str)
    r.add(separator=True)

    if customer:
        r.add(customer.upper(), bold=True, large=True)
    r.add(separator=True)

    r.add(item_name, huge=True)
    for mod in modifiers:
        r.add(str(mod), indent=20)

    r.render(output_path)


def main():
    parser = argparse.ArgumentParser(description="Preview Dino's labels as PNG images")
    parser.add_argument("--input",   required=True)
    parser.add_argument("--check",   required=True)
    parser.add_argument("--out-dir", default=".")
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)
    receipts = data if isinstance(data, list) else data.get("data", [])
    matches  = [r for r in receipts if str(r.get("check_number")) == str(args.check)]

    if not matches:
        print(f"❌ Check#{args.check} not found")
        sys.exit(1)

    receipt  = matches[0]
    items    = get_order_items(receipt)
    expanded = []
    for item in items:
        qty = int(item.get("quantity") or 1)
        for _ in range(qty):
            expanded.append(item)

    total = len(expanded)

    print(f"Rendering checklist for Check#{args.check}...")
    render_checklist(receipt, f"{args.out_dir}/checklist_{args.check}.png")

    for i, item in enumerate(expanded):
        path = f"{args.out_dir}/item_{args.check}_{i+1}of{total}.png"
        print(f"Rendering item label {i+1}/{total}...")
        render_item_label(receipt, item, i + 1, total, path)

    print("\n✅ All done — open the PNG files to preview")

if __name__ == "__main__":
    main()
