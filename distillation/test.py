import json
import re
from difflib import get_close_matches
from typing import Dict, List, Any, Union

def fix_malformed_json(pred_str: str) -> Dict:
    """Fix malformed JSON from model output"""
    if isinstance(pred_str, dict):
        return pred_str
    
    if not isinstance(pred_str, str):
        return {}
    
    # Add missing opening brace
    if not pred_str.startswith('{'):
        pred_str = '{' + pred_str

    # Add missing closing brace
    if not pred_str.endswith('}'):
        pred_str = pred_str + '}'

    # Fix order_items: wrap each item in {}
    def fix_order_items(match):
        inner = match.group(1)
        parts = re.split(r',(?="item_name")', inner)
        fixed = ['{' + p.strip() + '}' for p in parts if p.strip()]
        return '"order_items":[' + ','.join(fixed) + ']'

    pred_str = re.sub(r'"order_items":\[(.+)\](?=\})', fix_order_items, pred_str, flags=re.DOTALL)

    try:
        return json.loads(pred_str)
    except:
        return {
            "customer_name": None,
            "date": None,
            "time": None,
            "check_number": None,
            "table_number": None,
            "pickup_time": None,
            "total_amount": None,
            "restaurant_name": None,
            "confidence_score": 0.5,
            "order_items": []
        }

def normalize_date(date_str: str) -> str:
    """Fix date format inconsistencies"""
    if not date_str or date_str in ["N/A", "null", "None"]:
        return None
    
    # Handle ISO format (2025-06-25) -> MM/DD/YY
    if '-' in date_str and len(date_str) >= 10:
        parts = date_str.split('-')
        if len(parts) == 3:
            year = parts[0][-2:]  # Last 2 digits of year
            month = parts[1]
            day = parts[2][:2]  # In case of datetime
            return f"{month}/{day}/{year}"
    
    # Handle MM/DD format -> keep as is
    if '/' in date_str and date_str.count('/') == 1:
        return date_str
    
    # Handle MM/DD/YY format
    if '/' in date_str:
        parts = date_str.split('/')
        if len(parts) == 3:
            month, day, year = parts
            if len(year) == 4:
                year = year[-2:]
            return f"{month.zfill(2)}/{day.zfill(2)}/{year}"
    
    return date_str

# All known correction targets — used for fuzzy matching fallback
_CORRECTION_TARGETS = None
_FUZZY_LOG: List[Dict] = []  # Tracks fuzzy matches made this run

def _get_correction_targets(replacements: dict) -> List[str]:
    """Build correction target list once and cache it"""
    global _CORRECTION_TARGETS
    if _CORRECTION_TARGETS is None:
        _CORRECTION_TARGETS = list(replacements.keys())
    return _CORRECTION_TARGETS


def fix_item_names(item_name: str) -> str:
    """Fix common OCR errors in item names"""
    if not item_name:
        return None

    # Remove newlines/carriage returns (printer line-break artifacts e.g. "Wi\nngs", "Ch\neck#:")
    item_name = item_name.replace('\n', '').replace('\r', '')

    # Strip extra whitespace and join split words
    item_name = ' '.join(item_name.split())

    # Filter out garbage — items that are too short or are clearly not food
    garbage = [
        'UUS10U DigiCert Inc', 'U DigiCert TLS RSA SHA256 2020',
        'Pin', 'Ra', 'Hom', 'Grav', 'Chi', 'Buf', 'Coron', 'Melt',
        'Hot', 'Mild', 'Draft', 'Fried', 'Italian', 'Grilled',
        'NO MUSTARD', 'Mustard', 'Cheese', 'ToGo', 'Small', 'Large',
        'Skinny Fry', 'Home Fry', 'Cole Slaw', 'Ranch', 'Blue',
        'Peppercorn', 'Chix', 'Philly', 'No Pink', 'Cajun',
        # Note: 'Slicker' is a real Dino's wing flavor (BBQ + Hot + Garlic) — do NOT add it here
    ]
    if item_name in garbage:
        return None

    # Fix known OCR errors and abbreviations
    replacements = {
        'IC LITE': 'Iron City Light',
        'IC LI TE': 'Iron City Light',
        'Italian City Light': 'Iron City Light',
        'Chix Platter': 'Chicken Platter',
        'Chix Parm Sand': 'Chicken Parm Sandwich',
        'Buffalo Chix Sa': 'Buffalo Chicken Sandwich',
        'Dino Burger San': 'Dino Burger Sandwich',
        'Dino Burger Sa': 'Dino Burger Sandwich',
        'Dino B urger San': 'Dino Burger Sandwich',
        'CHX': 'Chicken',
        'DOWNGRD C': 'Downgrade to Chippers',  # Chippers = fresh cut seasoned chips on menu
        'DOWNGRD F': 'Downgrade to Fries',
        'MICH ULTRA': 'Michelob Ultra',
        'MICH ULTR': 'Michelob Ultra',
        'Miche Ultra': 'Michelob Ultra',
        'BUSCH LIGHT': 'Busch Light',
        'BLAKE S CIDER': "Blake's Cider",
        'REDDS APPLE': "Redd's Apple Ale",
        'Chick en Platter': 'Chicken Platter',
        'Diet Mo untain D': 'Diet Mountain Dew',
        'Diet Mo': 'Diet Mountain Dew',
        'Charb roiled Sa': 'Charbroiled Sandwich',
        'Ital Stal Sandw': 'Italian Stallion Sandwich',
        'Philly Stk Sand': 'Philly Steak Sandwich',
        '1/2 Rack &10 Wi': '1/2 Rack & 10 Wings',
        'Spinach Chix S': 'Spinach Chicken Salad',
        'Wing & Fries': 'Wings & Fries',
        'Spec Fry Buffalo Chix': 'Spicy Fried Buffalo Chicken',
        'Panni': 'Pannini',
        'Chix Philly Sa': 'Chicken Philly Sandwich',
        '1/2BuffChixSand': '1/2 Buffalo Chicken Sandwich',
        'Pot S kins': 'Potato Skins',
        'Pino Grigio': 'Pinot Grigio',
        # Sandwiches (verified against menu)
        'Philly Stk Sand': 'Philly Steak Sandwich',
        'Philly Chx Sand': 'Philly Chicken Sandwich',
        'Philly Stk': 'Philly Steak',
        'Philly Chx': 'Philly Chicken',
        'Ital Stal Sand': 'Italian Stallion Sandwich',
        'Ital Panini': 'Italian Panini',
        'Clara CBR': "Clara's Chicken Bacon Ranch",
        'Mat Mtball': "Matteo's Meatball",
        'Don Corl': 'Don Corleone',
        'Gia Srira': "Gia's Sriracha Slaw Chicken & Swiss",
        'Buf Chix Sand': 'Buffalo Chicken Sandwich',
        'Chix Parm': 'Chicken Parmesan',
        'Fr Dip': 'French Dip',
        # Burgers (verified against menu)
        'Veg Chip BLK': 'Vegetarian Chipotle Black Bean Burger',
        'Stlhse Burger': 'Steakhouse Burger',
        'Maria Dbl Chz': "Maria's Double Cheesy",
        'Sal Srira': "Sal's Sriracha Slaw & Swiss",
        'Pep Jk Mush': 'Pepper Jack Mushroom Burger',
        'Buf Bacon': 'Buffalo Bacon Burger',
        'Buf Bleu': 'Buffalo Bleu Burger',
        'Buf Chix Burger': 'Buffalo Chicken Burger',
        # Wings (verified against menu — all are real flavors)
        'Sw & Hot': 'Sweet & Hot',
        'Swt Hot': 'Sweet & Hot',
        'G & B': 'Garlic & Butter',
        'G & P': 'Garlic & Parmesan',
        'Sup Lewis': 'Super Lewis',
        # Appetizers (verified against menu)
        'Bskt Home Fry': 'Basket of Home Fries',
        'Bskt Skny Mny': 'Basket of Skinny Minny Fries',
        'Bskt Chip': 'Basket of Chippers',
        'Bskt HCB': 'Basket of Hot Cheese Balls',
        'Bav Pret': 'Bavarian Pretzels & Beer Cheese Dip',
        'Buf Chix Dip': 'Buffalo Chicken Dip',
        'Spin Art Dip': 'Spinach & Artichoke Dip',
        'Awe On Pet': 'Awesome Onion Petals',
        # Salads (verified against menu)
        'Chix Bac Ranch': 'Chicken Bacon Ranch Salad',
        'Buf Chix Sal': 'Buffalo Chicken Salad',
        'Spin Chix Sal': 'Spinach Chicken Salad',
        'Chrb Chix Sal': 'Charbroiled Chicken Salad',
        'Chrb Stk Sal': 'Charbroiled Steak Salad',
        # Platters (verified against menu)
        'Cajun Bkd Chx': 'Cajun Baked Chicken',
        'Ter Grll Chx': 'Teriyaki Grilled Chicken',
        'Buf Mac Chz': 'Buffalo Mac & Cheese',
        'Bac Mac Chz': 'Bacon Mac & Cheese',
        # Ribs (verified against menu)
        '1/2 Rack Plt': '1/2 Rack Platter',
        'Full Rack Plt': 'Full Rack Platter',
        'Rib Shrmp Plt': 'Rib & Shrimp Platter',
        '1/2 Rack Wi': '1/2 Rack & Wings',
    }

    for old, new in replacements.items():
        if item_name == old:
            return new

    # Remove items that are just a single word under 3 characters
    if len(item_name) < 3:
        return None

    # Fuzzy match fallback — catch near-misses not in the exact replacements list
    # e.g. "Ital Stal San" → matches "Ital Stal Sandw" → "Italian Stallion Sandwich"

    # At the start of the fuzzy match block, before get_close_matches:
    if item_name in replacements.values():
        return item_name
    
    candidates = _get_correction_targets(replacements)
    close = get_close_matches(item_name, candidates, n=1, cutoff=0.82)
    if close:
        corrected = replacements[close[0]]
        _FUZZY_LOG.append({
            'original': item_name,
            'matched_key': close[0],
            'corrected_to': corrected
        })
        return corrected

    return item_name

def extract_quantity(item_name: str, current_qty: int = 1) -> tuple:
    """Extract quantity from item name"""
    match = re.match(r'^(.+?)\s+(\d+)$', item_name)
    if match:
        return match.group(1), int(match.group(2))
    return item_name, current_qty

def clean_modifiers(modifiers: List) -> List:
    """Clean up modifier list"""
    if not isinstance(modifiers, list):
        return []

    # Fix known modifier abbreviations
    modifier_fixes = {
        'CHX': 'Chicken',
        'Chix': 'Chicken',
        'HOME FRY': 'Home Fry',
        'Home FRY': 'Home Fry',
        'FF': 'French Fries',
        'Butte': 'Butter',
    }

    # Known garbage modifiers to remove
    garbage = [
        'Cornelius', 'U DigiCert TLS RSA SHA256 2020',
        'Pint', 'Coors Light',
    ]

    cleaned = []
    seen = set()
    for mod in modifiers:
        if not isinstance(mod, str):
            continue
        # Skip numeric-only
        if re.match(r'^\d+$', mod):
            continue
        # Skip garbage
        if mod in garbage:
            continue
        # Fix known abbreviations
        mod = modifier_fixes.get(mod, mod)
        # Skip duplicates
        if mod in seen:
            continue
        seen.add(mod)
        cleaned.append(mod)

    return cleaned

def process_prediction(pred: Union[str, Dict]) -> Dict:
    """Main processing function"""
    # Step 1: Fix JSON structure
    if isinstance(pred, str):
        pred = fix_malformed_json(pred)

    if not isinstance(pred, dict):
        pred = {}

    # Step 2: Process each field
    processed = {}

    # Handle nulls consistently
    for field in ['customer_name', 'date', 'time', 'check_number', 'table_number',
                  'pickup_time', 'total_amount', 'restaurant_name']:
        value = pred.get(field)
        if value in ["N/A", "null", "None", "", "h"]:
            processed[field] = None if field != 'table_number' else ("" if value == "" else None)
        else:
            processed[field] = value

    # Fix date format
    if processed.get('date'):
        processed['date'] = normalize_date(processed['date'])

    # Handle confidence score
    processed['confidence_score'] = pred.get('confidence_score', 0.5)

    # Process order items
    order_items = pred.get('order_items', [])
    if not isinstance(order_items, list):
        order_items = []

    processed_items = []
    for item in order_items:
        if not isinstance(item, dict):
            continue

        # Get item name and extract quantity
        item_name = item.get('item_name', '')
        quantity = item.get('quantity', 1)

        # Extract quantity from name if present
        item_name, extracted_qty = extract_quantity(item_name, quantity)
        if extracted_qty != quantity and quantity == 1:
            quantity = extracted_qty

        # Fix item name
        item_name = fix_item_names(item_name)

        # Skip if no valid item name or if it's garbage
        if not item_name:
            continue

        # Build cleaned item
        cleaned_item = {
            'item_name': item_name,
            'quantity': quantity,
            'modifiers': clean_modifiers(item.get('modifiers', [])),
            'price': item.get('price')
        }

        # Add seat number if present
        seat = item.get('seat_number')
        if seat and seat not in ['None', 'null', 'N/A']:
            cleaned_item['seat_number'] = seat

        processed_items.append(cleaned_item)

    # Deduplicate order items
    seen_items = set()
    deduped_items = []
    for item in processed_items:
        key = (item['item_name'], item.get('seat_number'))
        if key not in seen_items:
            seen_items.add(key)
            deduped_items.append(item)

    processed['order_items'] = deduped_items

    return processed

def main():
    """Main execution"""
    # Load existing predictions from file
    print("Loading predictions from test_predictions.json...")
    with open('test_predictions.json', 'r') as f:
        raw_preds = json.load(f)

    # Process all predictions
    print("Applying post-processing...")
    processed_preds = []

    for i, entry in enumerate(raw_preds):
        try:
            processed = process_prediction(entry['predicted'])
            processed['file_id'] = entry['file_id']
            processed_preds.append(processed)
        except Exception as e:
            print(f"Error processing prediction {i}: {e}")

    # Save processed predictions
    with open('processed_predictions.json', 'w') as f:
        json.dump(processed_preds, f, indent=2)

    print(f"Done. Processed {len(processed_preds)} predictions.")
    print("Saved to processed_predictions.json")

    # --- Summary stats ---
    total_items = sum(len(p.get('order_items', [])) for p in processed_preds)
    missing_dates = sum(1 for p in processed_preds if not p.get('date'))
    missing_totals = sum(1 for p in processed_preds if not p.get('total_amount'))

    print(f"\n--- Post-Processing Summary ---")
    print(f"  Receipts processed : {len(processed_preds)}")
    print(f"  Total order items  : {total_items}")
    print(f"  Missing dates      : {missing_dates}/{len(processed_preds)}")
    print(f"  Missing totals     : {missing_totals}/{len(processed_preds)}")

    if _FUZZY_LOG:
        print(f"\n--- Fuzzy Match Corrections ({len(_FUZZY_LOG)} made) ---")
        for entry in _FUZZY_LOG:
            print(f"  '{entry['original']}' → matched '{entry['matched_key']}' → '{entry['corrected_to']}'")
    else:
        print("\n  No fuzzy matches triggered this run.")

if __name__ == "__main__":
    main()
