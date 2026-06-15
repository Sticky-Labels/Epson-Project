#!/usr/bin/env python3
"""
finetuning/ollama_inference.py
==============================
End-to-end receipt parser using a local Ollama model (llama3.2).
Replaces ft.py + testing.py for the inference step.

Reads test.json (or any training split), runs each receipt through
the local Llama model, validates the JSON output against the receipt
schema, and prints a full quality report.

Usage:
    python ollama_inference.py                        # runs on test.json
    python ollama_inference.py --split train          # runs on train.json
    python ollama_inference.py --limit 10             # first 10 receipts only
    python ollama_inference.py --output results.json  # save results to file
    python ollama_inference.py --receipt "Date 06/03/25 ..."  # single receipt

Requirements:
    pip install requests jsonschema
    Ollama installed and running: https://ollama.com
    Model pulled: ollama pull llama3.2
"""

import json
import re
import sys
import time
import argparse
import requests
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OLLAMA_URL    = "http://localhost:11434/api/generate"
OLLAMA_MODEL  = "llama3.2"
SPLITS_DIR    = "training_splits"
DEFAULT_SPLIT = "test"

# ---------------------------------------------------------------------------
# JSON Schema (matches tts_gen.py / testing.py)
# ---------------------------------------------------------------------------

RECEIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "customer_name":   {"type": ["string", "null"]},
        "date":            {"type": ["string", "null"]},
        "time":            {"type": ["string", "null"]},
        "check_number":    {"type": ["string", "null"]},
        "table_number":    {"type": ["string", "null"]},
        "pickup_time":     {"type": ["string", "null"]},
        "total_amount":    {"type": ["string", "null"]},
        "restaurant_name": {"type": ["string", "null"]},
        "confidence_score":{"type": ["number",  "null"]},
        "order_items": {
            "type": ["array", "null"],
            "items": {
                "type": "object",
                "properties": {
                    "item_name":   {"type": ["string",  "null"]},
                    "quantity":    {"type": ["integer", "null"]},
                    "modifiers":   {"type": ["array",   "null"], "items": {"type": "string"}},
                    "price":       {"type": ["string",  "null"]},
                    "seat_number": {"type": ["string",  "null"]},
                },
                "required": ["item_name", "quantity", "modifiers", "price", "seat_number"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "customer_name", "date", "time", "check_number", "table_number",
        "pickup_time", "total_amount", "restaurant_name", "confidence_score",
        "order_items",
    ],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert at parsing restaurant receipt data from Epson thermal kitchen printers.
The receipt text contains ESC/POS printer artifacts, abbreviations, and noisy formatting.
Extract the structured information and return ONLY a valid JSON object — no explanation, no markdown, no code blocks.

JSON schema (all fields required, use null if not present):
{
  "customer_name": string or null,
  "date": "MM/DD/YY" or null,
  "time": "H:MMam/pm" or null,
  "check_number": 6-digit string or null,
  "table_number": string or null,
  "pickup_time": string or null,
  "total_amount": null (kitchen tickets never have totals),
  "restaurant_name": string or null,
  "confidence_score": 0.0-1.0,
  "order_items": [
    {
      "seat_number": string or null,
      "item_name": string or null,
      "quantity": integer,
      "modifiers": [list of strings],
      "price": string or null
    }
  ]
}

Rules:
- order_items MUST be a list, never null — use [] if no items found
- quantity MUST be an integer (e.g. 1, 2, 3) — never a string
- Each indented line under an item is a modifier, not a separate item
- Lines starting with a number (e.g. "1 Wings Large") are items with quantity
- Seat dividers like [Seat 1] group items by seat
- total_amount is ALWAYS null (not printed on kitchen tickets) — always include it
- modifiers MUST be a list of strings — never null, use [] if none
- price is ALWAYS null unless explicitly shown
- Return ONLY the JSON object, nothing else"""


def build_prompt(receipt_text: str) -> str:
    return f"{SYSTEM_PROMPT}\n\nRECEIPT TEXT:\n{receipt_text}\n\nJSON:"


# ---------------------------------------------------------------------------
# Ollama client
# ---------------------------------------------------------------------------

def check_ollama_running() -> bool:
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def call_ollama(prompt: str, retries: int = 3) -> Optional[str]:
    """Call Ollama API and return raw text response."""
    payload = {
        "model":  OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
            "num_predict": 2048,   # enough for full JSON with many order items
            "num_ctx": 4096,       # context window
        },
    }

    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except requests.exceptions.Timeout:
            print(f"   ⏳ Timeout on attempt {attempt}/{retries}, retrying...")
            time.sleep(5)
        except Exception as e:
            print(f"   ❌ Ollama error (attempt {attempt}/{retries}): {e}")
            time.sleep(3)

    return None


# ---------------------------------------------------------------------------
# JSON extraction and validation
# ---------------------------------------------------------------------------

def extract_json(raw: str) -> Optional[str]:
    """Pull the first {...} block out of raw model output."""
    if not raw:
        return None

    # Try direct parse first
    try:
        json.loads(raw)
        return raw
    except Exception:
        pass

    # Find first { ... } block
    start = raw.find('{')
    if start == -1:
        return None

    depth = 0
    for i, ch in enumerate(raw[start:], start):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                candidate = raw[start:i+1]
                try:
                    json.loads(candidate)
                    return candidate
                except Exception:
                    pass

    return None


def validate_schema(parsed: Dict) -> Tuple[bool, str]:
    try:
        import jsonschema
        jsonschema.validate(instance=parsed, schema=RECEIPT_SCHEMA)
        return True, "ok"
    except ImportError:
        # jsonschema not installed — do basic checks manually
        required = ["customer_name", "date", "time", "check_number",
                    "table_number", "pickup_time", "total_amount",
                    "restaurant_name", "confidence_score", "order_items"]
        missing = [f for f in required if f not in parsed]
        if missing:
            return False, f"Missing fields: {missing}"
        return True, "ok"
    except Exception as e:
        return False, str(e)


def score_receipt(parsed: Dict, expected: Optional[Dict] = None) -> Dict:
    """Compute quality scores for a single parsed receipt."""
    scores = {
        "has_date":         bool(parsed.get("date")),
        "has_check_number": bool(parsed.get("check_number")),
        "has_order_items":  isinstance(parsed.get("order_items"), list) and len(parsed.get("order_items", [])) > 0,
        "date_format_ok":   bool(re.match(r'^\d{1,2}/\d{1,2}/\d{2}$', parsed.get("date") or "")),
        "check_6digit":     bool(re.match(r'^\d{6}$', parsed.get("check_number") or "")),
        "items_have_names": all(
            item.get("item_name") for item in (parsed.get("order_items") or [])
        ) if parsed.get("order_items") else False,
    }

    # Field match against expected if provided
    if expected:
        try:
            exp = json.loads(expected) if isinstance(expected, str) else expected
            scores["date_match"]         = parsed.get("date")          == exp.get("date")
            scores["check_match"]        = parsed.get("check_number")  == exp.get("check_number")
            scores["customer_match"]     = parsed.get("customer_name") == exp.get("customer_name")
            scores["table_match"]        = parsed.get("table_number")  == exp.get("table_number")
            scores["item_count_match"]   = (
                len(parsed.get("order_items") or []) ==
                len(exp.get("order_items") or [])
            )
        except Exception:
            pass

    return scores


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def parse_receipt(receipt_text: str, verbose: bool = True) -> Dict:
    """Parse a single receipt text string → structured dict."""
    prompt   = build_prompt(receipt_text)
    raw      = call_ollama(prompt)
    json_str = extract_json(raw) if raw else None

    if not json_str:
        if verbose:
            print(f"   ❌ No valid JSON in model output")
            if raw:
                print(f"   Raw: {raw[:200]}")
        return {}

    try:
        parsed = json.loads(json_str)
    except Exception as e:
        if verbose:
            print(f"   ❌ JSON parse error: {e}")
        return {}

    # Ensure order_items is always a list
    if parsed.get("order_items") is None:
        parsed["order_items"] = []

    return parsed


def run_on_split(
    split: str = DEFAULT_SPLIT,
    limit: Optional[int] = None,
    output_file: Optional[str] = None,
    verbose: bool = True,
) -> List[Dict]:
    """Run inference on a training split file and print quality report."""

    filepath = f"{SPLITS_DIR}/{split}.json"
    print(f"\n{'='*60}")
    print(f"OLLAMA RECEIPT PARSER — {split.upper()} SPLIT")
    print(f"Model: {OLLAMA_MODEL}  |  File: {filepath}")
    print(f"{'='*60}")

    # Check Ollama is running
    if not check_ollama_running():
        print("❌ Ollama is not running. Start it with: ollama serve")
        sys.exit(1)
    print("✅ Ollama is running\n")

    # Load data
    try:
        with open(filepath) as f:
            raw_data = json.load(f)
        data = raw_data if isinstance(raw_data, list) else raw_data.get("data", [])
    except FileNotFoundError:
        print(f"❌ File not found: {filepath}")
        sys.exit(1)

    if limit:
        data = data[:limit]

    print(f"Receipts to process: {len(data)}\n")

    results      = []
    valid_json   = 0
    schema_ok    = 0
    has_items    = 0
    date_correct = 0
    check_correct = 0

    for i, entry in enumerate(data, 1):
        inp    = entry.get("input", "")
        target = entry.get("target", None)

        # Extract just the receipt text — strip the embedded system prompt
        # that tts_gen.py bakes into the input field (it's verbose and eats context)
        if "RECEIPT TEXT:" in inp:
            receipt_text = inp.split("RECEIPT TEXT:")[1].split("EXTRACTION RULES:")[0].strip()
        elif "Receipt Text:" in inp:
            receipt_text = inp.split("Receipt Text:")[1].split("\n\nInstructions:")[0].strip()
        else:
            receipt_text = inp

        check_hint = re.search(r'eck#:(\d+)', receipt_text)
        check_hint = check_hint.group(1) if check_hint else "?"

        print(f"[{i}/{len(data)}] Check#{check_hint}")

        parsed = parse_receipt(receipt_text, verbose=verbose)

        if not parsed:
            print(f"   ❌ Failed\n")
            results.append({"check_number": check_hint, "error": "parse_failed"})
            continue

        valid_json += 1

        # Schema validation
        ok, err = validate_schema(parsed)
        if ok:
            schema_ok += 1
            schema_status = "✅ schema ok"
        else:
            schema_status = f"⚠️  schema: {err[:60]}"

        # Scores
        scores = score_receipt(parsed, target)
        if scores.get("has_order_items"):
            has_items += 1
        if scores.get("date_format_ok"):
            date_correct += 1
        if scores.get("check_6digit"):
            check_correct += 1

        item_count = len(parsed.get("order_items") or [])
        print(f"   date={parsed.get('date')}  check={parsed.get('check_number')}  "
              f"customer={parsed.get('customer_name')}  items={item_count}  {schema_status}")

        if verbose and parsed.get("order_items"):
            for item in parsed["order_items"][:3]:
                mods = ", ".join(str(m) for m in (item.get("modifiers") or []) if m is not None)
                print(f"      • {item.get('quantity')}x {item.get('item_name')}"
                      + (f"  [{mods}]" if mods else ""))
            if item_count > 3:
                print(f"      ... +{item_count-3} more")

        print()

        result = dict(parsed)
        result["_file_id"] = entry.get("file_id", i)
        results.append(result)

    # ---------------------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------------------
    total = len(data)
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"  Receipts processed   : {total}")
    print(f"  Valid JSON output    : {valid_json}/{total} ({round(valid_json/total*100) if total else 0}%)")
    print(f"  Schema compliant     : {schema_ok}/{total}")
    print(f"  Has order_items      : {has_items}/{total}")
    print(f"  Correct date format  : {date_correct}/{total}")
    print(f"  6-digit check number : {check_correct}/{total}")
    print()

    pct = (valid_json / total * 100) if total else 0
    if pct >= 90:   grade = "🟢 EXCELLENT"
    elif pct >= 70: grade = "🟡 GOOD"
    elif pct >= 50: grade = "🟠 FAIR"
    else:           grade = "🔴 POOR"
    print(f"  Overall grade: {grade}  ({pct:.1f}% valid JSON)")
    print(f"{'='*60}\n")

    # Save output
    if output_file:
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"✅ Results saved to {output_file}")

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="End-to-end receipt parser using local Ollama/Llama3.2",
    )
    parser.add_argument("--split",   default=DEFAULT_SPLIT,
                        help="Which split to run: train / val / test (default: test)")
    parser.add_argument("--limit",   type=int, default=None,
                        help="Max receipts to process (default: all)")
    parser.add_argument("--output",  default=None,
                        help="Save results JSON to this file")
    parser.add_argument("--receipt", default=None,
                        help="Parse a single receipt text string directly")
    parser.add_argument("--quiet",   action="store_true",
                        help="Suppress per-item detail output")
    args = parser.parse_args()

    if args.receipt:
        # Single receipt mode
        if not check_ollama_running():
            print("❌ Ollama is not running. Start it with: ollama serve")
            sys.exit(1)
        result = parse_receipt(args.receipt, verbose=not args.quiet)
        print(json.dumps(result, indent=2))
    else:
        run_on_split(
            split=args.split,
            limit=args.limit,
            output_file=args.output,
            verbose=not args.quiet,
        )


if __name__ == "__main__":
    main()
