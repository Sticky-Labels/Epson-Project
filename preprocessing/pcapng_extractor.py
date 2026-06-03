#!/usr/bin/env python3
"""
pcapng_extractor.py — Priority 1 of the Epson receipt-parsing project
======================================================================
Reads one or more .pcapng files directly (no Wireshark installation
required), extracts TCP port-9100 ESC/POS printer payloads, cleans the
ESC/POS escape sequences, and writes a deduplicated receipt file in the
same format as split_receipts.py's tcp_data_single.txt output:

    <receipt text for check N>

    --- NEXT OCCURRENCE ---

    <receipt text for check N+1>
    ...

Date and time headers are prepended using the same linear-scan logic as
split_receipts.py: the thermal printer only emits "Date XX/XX/XX" once
per TCP connection; subsequent packets in the same connection carry only
item data, so we track the last-seen date+time as we walk packets in
timestamp order.

Usage (single file):
    python pcapng_extractor.py Dino-1.pcapng

Usage (multiple files, merged + deduped):
    python pcapng_extractor.py Dino-1.pcapng Dino-2.pcapng Dino-3.pcapng

Usage (merge new data with existing tcp_data_single.txt):
    python pcapng_extractor.py *.pcapng --merge tcp_data_single.txt

Output written to tcp_data_extracted.txt by default; use --output to override.
"""

import struct
import re
import sys
import os
import argparse
from collections import defaultdict
from typing import List, Dict, Tuple, Optional


# ---------------------------------------------------------------------------
# pcapng binary parser
# ---------------------------------------------------------------------------

BLOCK_SHB = 0x0A0D0D0A   # Section Header Block
BLOCK_IDB = 0x00000001   # Interface Description Block
BLOCK_EPB = 0x00000006   # Enhanced Packet Block
BLOCK_SPB = 0x00000003   # Simple Packet Block (rare, older format)


def _read_u32_le(data: bytes, offset: int) -> int:
    return struct.unpack_from('<I', data, offset)[0]


def _read_u16_be(data: bytes, offset: int) -> int:
    return struct.unpack_from('>H', data, offset)[0]


def parse_pcapng(filepath: str) -> List[Tuple[int, bytes]]:
    """
    Parse a pcapng file and return a list of (timestamp_us, raw_packet_bytes)
    for every EPB block found.  Timestamp is in microseconds since epoch
    (standard pcapng resolution unless IDB tsresol option says otherwise —
    all Wireshark captures from this project use the default 10^-6).
    """
    with open(filepath, 'rb') as fh:
        data = fh.read()

    file_len = len(data)
    offset = 0
    packets: List[Tuple[int, bytes]] = []

    while offset + 8 <= file_len:
        block_type = _read_u32_le(data, offset)
        block_len  = _read_u32_le(data, offset + 4)

        if block_len < 12 or offset + block_len > file_len:
            break  # truncated or corrupt — stop gracefully

        if block_type == BLOCK_EPB:
            # Enhanced Packet Block layout:
            #   [0-3]   block type
            #   [4-7]   block total length
            #   [8-11]  interface ID
            #  [12-15]  timestamp high (upper 32 bits)
            #  [16-19]  timestamp low  (lower 32 bits)
            #  [20-23]  captured packet length
            #  [24-27]  original packet length
            #  [28 ...] packet data (padded to 32-bit boundary)
            ts_hi   = _read_u32_le(data, offset + 12)
            ts_lo   = _read_u32_le(data, offset + 16)
            cap_len = _read_u32_le(data, offset + 20)
            pkt_data = data[offset + 28 : offset + 28 + cap_len]
            timestamp = (ts_hi << 32) | ts_lo  # microseconds
            packets.append((timestamp, pkt_data))

        offset += block_len

    return packets


# ---------------------------------------------------------------------------
# Ethernet / IPv4 / TCP dissector
# ---------------------------------------------------------------------------

def extract_tcp_payload(
    raw_packet: bytes,
) -> Tuple[Optional[int], Optional[int], Optional[bytes]]:
    """
    Dissect a raw Ethernet frame and return (src_port, dst_port, tcp_payload).
    Returns (None, None, None) for non-TCP or malformed packets.
    """
    if len(raw_packet) < 14:
        return None, None, None

    eth_type = _read_u16_be(raw_packet, 12)
    if eth_type != 0x0800:   # not IPv4
        return None, None, None

    ip_start = 14
    if len(raw_packet) < ip_start + 20:
        return None, None, None

    ip_proto = raw_packet[ip_start + 9]
    if ip_proto != 6:        # not TCP
        return None, None, None

    ihl = (raw_packet[ip_start] & 0x0F) * 4
    tcp_start = ip_start + ihl
    if len(raw_packet) < tcp_start + 20:
        return None, None, None

    src_port = _read_u16_be(raw_packet, tcp_start)
    dst_port = _read_u16_be(raw_packet, tcp_start + 2)
    data_offset = ((raw_packet[tcp_start + 12] >> 4) & 0x0F) * 4
    payload = raw_packet[tcp_start + data_offset:]

    return src_port, dst_port, payload


# ---------------------------------------------------------------------------
# ESC/POS cleaner
# ---------------------------------------------------------------------------

# ESC/POS escape sequences we want to strip (Epson TM-series kitchen printer).
# Patterns are tried in the order they appear in the alternation — most
# specific first so longer sequences are consumed before single-byte fallbacks.
_ESCPOS_PATTERNS = re.compile(
    r'\x1b!\x01'          # ESC ! 0x01 — normal font restore (very common here)
    r'|\x1b!\x31'         # ESC ! 0x31 — enlarged/bold font select
    r'|\x1b!.'            # ESC ! n    — any other font select
    r'|\x1br.'            # ESC r n    — select print colour
    r'|\x1bi'             # ESC i      — partial cut
    r'|\x1b[A-Z@\\\[\]^_`a-z]'  # other single-byte ESC sequences
    r'|\x10\x04.'         # DLE EOT n  — real-time status request (3 bytes)
    r'|\x00+',            # null padding bytes
    re.DOTALL,
)

# Seat-divider lines:  ÄÄ[Seat 1]ÄÄÄÄÄÄÄÄÄÄ  →  [Seat 1]
_SEAT_DIVIDER = re.compile(r'[Ä\xc4]+(\[Seat\s*\d+\])[Ä\xc4]*', re.IGNORECASE)

# ToGo banner:  ®® ToGo N ¯¯¯¯¯¯¯¯¯¯  →  ToGo N
_TOGO_BANNER = re.compile(r'[®¯\xa9\xaf]+\s*(ToGo\s*\d+)\s*[®¯\xa9\xaf]*', re.IGNORECASE)

# Separator lines of Ü or Ä characters (printed as thick horizontal rules)
_SEPARATOR_CHARS = re.compile(r'[ÜÄ\xdc\xc4]{4,}')


def clean_escpos(raw: str) -> str:
    """
    Strip ESC/POS control sequences and printer-specific artifacts from
    a decoded (latin-1) payload string, returning readable plain text.

    Processing order:
      1. Strip ESC/POS binary sequences
      2. Clean up seat-divider lines  (ÄÄ[Seat 1]ÄÄ → [Seat 1])
      3. Clean up ToGo banners        (®® ToGo 1 ¯¯ → ToGo 1)
      4. Replace separator char runs  (ÜÜÜÜ → ----)
      5. Remove CR, collapse blank lines, rstrip each line
    """
    text = _ESCPOS_PATTERNS.sub('', raw)
    text = _SEAT_DIVIDER.sub(r'\1', text)
    text = _TOGO_BANNER.sub(r'\1', text)
    text = _SEPARATOR_CHARS.sub('----------------------------------------', text)

    text = text.replace('\r', '')
    text = re.sub(r'\n{3,}', '\n\n', text)

    lines = [line.rstrip() for line in text.split('\n')]
    text = '\n'.join(lines)

    return text.strip()


# ---------------------------------------------------------------------------
# Receipt reconstruction from TCP stream
# ---------------------------------------------------------------------------

def extract_receipts_from_packets(
    packets: List[Tuple[int, bytes]],
    printer_port: int = 9100,
) -> List[Dict]:
    """
    Given a list of (timestamp, raw_packet) pairs (sorted by timestamp),
    reconstruct per-receipt text by grouping packets by TCP source port
    (each TCP connection from the POS terminal = one print job = one receipt).

    Returns a list of dicts:
        {
            'check_number': str,
            'text': str,            # cleaned receipt text WITH date header
            'date': str | None,
            'time': str | None,
        }
    """
    # Group payloads by source port, preserving timestamp order
    by_src: Dict[int, List[Tuple[int, bytes]]] = defaultdict(list)
    for ts, raw in sorted(packets, key=lambda x: x[0]):
        src, dst, payload = extract_tcp_payload(raw)
        if src is None:
            continue
        if dst != printer_port:
            continue
        if not payload or len(payload) < 3:
            continue
        by_src[src].append((ts, payload))

    # Decode and concatenate payloads for each connection
    connections: List[Tuple[int, str]] = []  # (first_ts, full_text)
    for src_port, chunks in by_src.items():
        first_ts = chunks[0][0]
        raw_text = b''.join(p for _, p in chunks).decode('latin-1', errors='replace')
        cleaned = clean_escpos(raw_text)
        if cleaned:
            connections.append((first_ts, cleaned))

    # Sort connections chronologically
    connections.sort(key=lambda x: x[0])

    # ---------------------------------------------------------------------------
    # Date/time header logic (mirrors split_receipts.py linear scan)
    # The thermal printer emits "Date MM/DD/YY  Time H:MMam" at the start of
    # each TCP connection, so it IS present in every connection's payload here.
    # We still apply the same "carry last-seen date forward" logic as
    # split_receipts.py does for robustness, in case a fragmented capture
    # misses the header packet.
    # ---------------------------------------------------------------------------
    date_pattern = re.compile(r'Date\s+(\d{1,2}/\d{1,2}/\d{2,4})', re.IGNORECASE)
    time_pattern = re.compile(r'Time\s+(\d{1,2}:\d{2}[ap]m)', re.IGNORECASE)
    check_pattern = re.compile(r'\w*eck#:(\d+)')

    last_date: Optional[str] = None
    last_time: Optional[str] = None
    receipts: List[Dict] = []

    for first_ts, text in connections:
        # Extract date/time from this connection's text
        dm = date_pattern.search(text)
        tm = time_pattern.search(text)
        if dm:
            last_date = dm.group(1)
        if tm:
            last_time = tm.group(1)

        # Extract check number
        cm = check_pattern.search(text)
        if not cm:
            continue  # not a receipt (status or control packet)
        check_num = cm.group(1)

        # Prepend date header if not already present
        if last_date and not text.startswith('Date'):
            header = f"Date {last_date}"
            if last_time:
                header += f"\n    Time {last_time}"
            text = header + '\n' + text

        receipts.append({
            'check_number': check_num,
            'text': text,
            'date': last_date,
            'time': last_time,
        })

    return receipts


# ---------------------------------------------------------------------------
# Merge with existing tcp_data_single.txt
# ---------------------------------------------------------------------------

def load_existing_receipts(filepath: str) -> Dict[str, str]:
    """
    Parse an existing tcp_data_single.txt (--- NEXT OCCURRENCE --- separated)
    and return a dict of {check_number: receipt_text}.
    """
    try:
        with open(filepath, 'r', encoding='latin-1', errors='replace') as fh:
            content = fh.read()
    except FileNotFoundError:
        return {}

    check_pattern = re.compile(r'\w*eck#:(\d+)')
    existing: Dict[str, str] = {}

    for block in content.split('--- NEXT OCCURRENCE ---'):
        block = block.strip()
        if not block:
            continue
        cm = check_pattern.search(block)
        if cm:
            existing[cm.group(1)] = block

    return existing


# ---------------------------------------------------------------------------
# End-boundary trimming (same heuristic as split_receipts.py)
# ---------------------------------------------------------------------------

def trim_end_boundary(text: str) -> str:
    """
    Trim at the long separator run printed at the end of each receipt.
    Keep through the first separator (it marks end-of-items) but drop
    trailing newlines and control residue after it.
    """
    # The ESC/POS cleaner already converts separator chars → dashes.
    # Find the last dashes run and cut after it.
    sep_pattern = re.compile(r'-{20,}')
    m = None
    for m in sep_pattern.finditer(text):
        pass  # walk to last match
    if m:
        text = text[:m.end()].strip()
    return text


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def process_pcapng_files(
    pcapng_files: List[str],
    merge_file: Optional[str],
    output_file: str,
    printer_port: int = 9100,
) -> None:
    print(f"\n{'='*60}")
    print("pcapng_extractor.py — Epson receipt extraction pipeline")
    print(f"{'='*60}")
    print(f"  Input files   : {', '.join(os.path.basename(f) for f in pcapng_files)}")
    if merge_file:
        print(f"  Merge with    : {merge_file}")
    print(f"  Output file   : {output_file}")
    print(f"  Printer port  : {printer_port}")

    # ------------------------------------------------------------------
    # Step 1: Parse all pcapng files
    # ------------------------------------------------------------------
    all_packets: List[Tuple[int, bytes]] = []
    total_raw_packets = 0

    for filepath in pcapng_files:
        if not os.path.exists(filepath):
            print(f"\n  ⚠️  File not found: {filepath} — skipping")
            continue
        pkts = parse_pcapng(filepath)
        total_raw_packets += len(pkts)
        all_packets.extend(pkts)
        print(f"\n  ✅ {os.path.basename(filepath)}: {len(pkts)} EPB packets")

    print(f"\n  Total packets parsed : {total_raw_packets}")

    # ------------------------------------------------------------------
    # Step 2: Extract receipts
    # ------------------------------------------------------------------
    receipts = extract_receipts_from_packets(all_packets, printer_port)
    print(f"  Raw receipt chunks   : {len(receipts)}")

    # ------------------------------------------------------------------
    # Step 3: Trim end boundaries and deduplicate by check number
    # (pcapng captures often contain duplicate TCP packets — normal)
    # ------------------------------------------------------------------
    seen_checks: set = set()
    deduped_from_pcapng: List[Dict] = []
    duplicate_count = 0

    for r in receipts:
        text = trim_end_boundary(r['text'])
        if len(text) < 30:
            continue  # too short to be a real receipt
        check = r['check_number']
        if check in seen_checks:
            duplicate_count += 1
            continue
        seen_checks.add(check)
        r['text'] = text
        deduped_from_pcapng.append(r)

    print(f"  Duplicates removed   : {duplicate_count}")
    print(f"  Unique (new) receipts: {len(deduped_from_pcapng)}")

    # ------------------------------------------------------------------
    # Step 4: Merge with existing file if requested
    # ------------------------------------------------------------------
    existing: Dict[str, str] = {}
    if merge_file:
        existing = load_existing_receipts(merge_file)
        print(f"  Existing receipts    : {len(existing)} (from {merge_file})")

    # Build combined dict; existing file wins on conflicts so we don't
    # overwrite already-labeled data with new captures of the same check
    combined: Dict[str, str] = {}
    combined.update({r['check_number']: r['text'] for r in deduped_from_pcapng})
    overlap = len(set(combined.keys()) & set(existing.keys()))
    combined.update(existing)  # existing takes precedence

    print(f"  Overlap (same check#): {overlap}")
    print(f"  Combined total       : {len(combined)}")

    # ------------------------------------------------------------------
    # Step 5: Quality check — which receipts are missing a date header
    # ------------------------------------------------------------------
    missing_dates = [k for k, v in combined.items() if not v.startswith('Date')]
    if missing_dates:
        print(f"\n  ⚠️  Receipts missing date header ({len(missing_dates)}): "
              f"{sorted(missing_dates)}")
    else:
        print(f"\n  ✅ All {len(combined)} receipts have date headers")

    # ------------------------------------------------------------------
    # Step 6: Write output
    # ------------------------------------------------------------------
    # Sort by check number numerically for consistent ordering
    sorted_receipts = sorted(combined.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0)
    combined_text = '\n\n--- NEXT OCCURRENCE ---\n\n'.join(text for _, text in sorted_receipts)

    with open(output_file, 'w', encoding='latin-1', errors='replace') as fh:
        fh.write(combined_text)

    print(f"\n  ✅ Output written to: {output_file}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("EXTRACTION SUMMARY")
    print(f"{'='*60}")
    print(f"  Total EPB packets parsed : {total_raw_packets}")
    print(f"  Port-9100 printer chunks : {len(receipts) + duplicate_count}")
    print(f"  Duplicates removed       : {duplicate_count}")
    print(f"  New unique receipts      : {len(deduped_from_pcapng)}")
    if merge_file:
        print(f"  Existing receipts merged : {len(existing)}")
    print(f"  ─────────────────────────────────────────")
    print(f"  Final combined total     : {len(combined)}")
    print(f"  Missing date headers     : {len(missing_dates)}")
    print(f"  Output file              : {output_file}")
    print(f"{'='*60}")

    # Preview first two new receipts
    if deduped_from_pcapng:
        print("\n--- Preview: first new receipt ---")
        print(deduped_from_pcapng[0]['text'][:400])
        print("...")
        if len(deduped_from_pcapng) > 1:
            print("\n--- Preview: second new receipt ---")
            print(deduped_from_pcapng[1]['text'][:400])
            print("...")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract ESC/POS receipt data from pcapng files (no Wireshark required).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single file
  python pcapng_extractor.py Dino-6.pcapng

  # Multiple files merged
  python pcapng_extractor.py Dino-6.pcapng Dino-7.pcapng

  # Merge new pcapngs with existing receipt file
  python pcapng_extractor.py Dino-6.pcapng --merge tcp_data_single.txt

  # Custom output path
  python pcapng_extractor.py *.pcapng --output combined_receipts.txt
""",
    )
    parser.add_argument(
        'pcapng_files',
        nargs='+',
        metavar='FILE.pcapng',
        help="One or more .pcapng files to process",
    )
    parser.add_argument(
        '--merge',
        metavar='EXISTING_TXT',
        default=None,
        help="Existing tcp_data_single.txt to merge with (new data + existing, deduped)",
    )
    parser.add_argument(
        '--output',
        metavar='OUTPUT_TXT',
        default='tcp_data_extracted.txt',
        help="Output file path (default: tcp_data_extracted.txt)",
    )
    parser.add_argument(
        '--port',
        type=int,
        default=9100,
        help="Printer TCP port to capture (default: 9100)",
    )

    args = parser.parse_args()

    process_pcapng_files(
        pcapng_files=args.pcapng_files,
        merge_file=args.merge,
        output_file=args.output,
        printer_port=args.port,
    )


if __name__ == '__main__':
    main()
