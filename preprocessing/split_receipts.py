import re

def split_into_single_receipts(input_file, output_file):
    with open(input_file, 'r', encoding='latin-1') as f:
        full = f.read()

    # Remove existing separators
    content = full.replace('--- NEXT OCCURRENCE ---', '')

    # Split on each check number occurrence
    parts = re.split(r'(?=\w*eck#:)', content)

    receipts = []
    for part in parts:
        part = part.strip()
        if 'eck#:' not in part or len(part) <= 50:
            continue

        # Trim at the end boundary: long run of garbled printer separator chars
        end_match = re.search(r'(ï¿½{5,}|ÔøΩ{5,})', part)
        if end_match:
            cut_pos = end_match.start() + len(end_match.group())
            part = part[:cut_pos].strip()

        receipts.append(part)

    # Build date map by scanning full file linearly.
    # The thermal printer only prints "Date XX/XX/XX" once per session —
    # subsequent receipts in the same session only have a Time line.
    # Strategy: walk through all check number positions in order, tracking
    # the most recently seen date as we go.
    date_pattern = re.compile(r'Date (\d{2}/\d{2}/\d{2})', re.IGNORECASE)
    time_pattern = re.compile(r'Time (\d+:\d+[ap]m)', re.IGNORECASE)
    check_pattern = re.compile(r'\w*eck#:(\d+)')

    # Collect all events (dates, times, check numbers) with their positions
    events = []
    for m in date_pattern.finditer(content):
        events.append(('date', m.start(), m.group(1)))
    for m in time_pattern.finditer(content):
        events.append(('time', m.start(), m.group(1)))
    for m in check_pattern.finditer(content):
        events.append(('check', m.start(), m.group(1)))
    events.sort(key=lambda x: x[1])

    # Walk events in order, keeping track of last seen date and time
    date_map = {}  # check_number -> "Date MM/DD/YY\n    Time HH:MMam"
    last_date = None
    last_time = None
    for kind, pos, value in events:
        if kind == 'date':
            last_date = value
        elif kind == 'time':
            last_time = value
        elif kind == 'check':
            if last_date:
                header = f"Date {last_date}"
                if last_time:
                    header += f"\n    Time {last_time}"
                date_map[value] = header

    # Prepend the date header to each receipt
    receipts_with_dates = []
    for receipt in receipts:
        check_match = re.search(r'\w*eck#:(\d+)', receipt)
        if check_match:
            check_num = check_match.group(1)
            date_header = date_map.get(check_num, '')
            if date_header and not receipt.startswith('Date'):
                receipt = date_header + '\n' + receipt
        receipts_with_dates.append(receipt)

    # Deduplicate by check number — Wireshark captures duplicate TCP packets normally
    seen_check_nums = set()
    deduped = []
    duplicate_count = 0
    for receipt in receipts_with_dates:
        check_match = re.search(r'\w*eck#:(\d+)', receipt)
        if check_match:
            check_num = check_match.group(1)
            if check_num in seen_check_nums:
                duplicate_count += 1
                continue
            seen_check_nums.add(check_num)
        deduped.append(receipt)

    # Check which receipts are missing a date header
    missing_date_checks = []
    for receipt in deduped:
        check_match = re.search(r'\w*eck#:(\d+)', receipt)
        check_num = check_match.group(1) if check_match else '?'
        if not receipt.startswith('Date'):
            missing_date_checks.append(check_num)

    # Write with separators
    combined = '\n\n--- NEXT OCCURRENCE ---\n\n'.join(deduped)
    with open(output_file, 'w', encoding='latin-1', errors='replace') as f:
        f.write(combined)

    # --- Summary ---
    print(f"\n--- Receipt Splitting Summary ---")
    print(f"  Raw receipt chunks found : {len(receipts_with_dates)}")
    print(f"  Duplicates removed       : {duplicate_count}")
    print(f"  Unique receipts output   : {len(deduped)}")
    print(f"  Receipts with date header: {len(deduped) - len(missing_date_checks)}/{len(deduped)}")
    if missing_date_checks:
        print(f"  Missing date header      : {len(missing_date_checks)} (check numbers: {missing_date_checks})")
    else:
        print(f"  Missing date header      : 0 — all receipts have dates")
    print(f"\nSaved to {output_file}")

    # Preview first two receipts
    for i, r in enumerate(deduped[:2]):
        print(f"\n--- Receipt {i+1} preview ---")
        print(r[:300])
        print("...")

if __name__ == '__main__':
    split_into_single_receipts('tcp_data_mod2.txt', 'tcp_data_single.txt')
