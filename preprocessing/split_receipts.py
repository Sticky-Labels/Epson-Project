import re

def split_into_single_receipts(input_file, output_file):
    with open(input_file, 'r', encoding='latin-1') as f:
        content = f.read()

    # Remove existing separators
    content = content.replace('--- NEXT OCCURRENCE ---', '')

    # Split on each check number occurrence
    # Each receipt starts just before "eck#:"
    parts = re.split(r'(?=\w*eck#:)', content)

    # Clean and filter
    receipts = []
    for part in parts:
        part = part.strip()
        if 'eck#:' in part and len(part) > 50:
            receipts.append(part)

    # Write with separators
    combined = '\n\n--- NEXT OCCURRENCE ---\n\n'.join(receipts)
    with open(output_file, 'w', encoding='latin-1', errors='replace') as f:
        f.write(combined)

    print(f"Split into {len(receipts)} individual receipts")
    print(f"Saved to {output_file}")

    # Preview first receipt
    print("\nPreview of first receipt:")
    print(receipts[0][:300])

if __name__ == '__main__':
    split_into_single_receipts('tcp_data_mod2.txt', 'tcp_data_single.txt')
