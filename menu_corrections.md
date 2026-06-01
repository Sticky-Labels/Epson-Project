# Dino's Sports Lounge — Menu Correction Mappings

All abbreviations and OCR errors found in raw Wireshark receipt data, corrected
against the official Dino's Sports Lounge menu (dinoslatrobe.com/menu).

Each entry shows: `Raw receipt text` → `Corrected menu item name`

---

## Special Notes

- **Slicker** — is a *real* Dino's wing flavor (BBQ + Hot + Garlic combined). It was
  previously flagged as garbage and removed. This was corrected — it must be preserved.
- **DOWNGRD C** → `Downgrade to Chippers` — Chippers are "fresh cut seasoned potato
  chips," the specific menu item name. Not just "Downgrade."
- **Fuzzy matching** — in addition to the exact mappings below, the pipeline uses
  difflib fuzzy matching (cutoff 0.82) to catch near-misses not in this list.

---

## Sandwiches

| Raw Text | Corrected Name | Menu Section |
|---|---|---|
| `Ital Stal Sandw` | Italian Stallion Sandwich | Super Sandwiches |
| `Ital Stal Sand` | Italian Stallion Sandwich | Super Sandwiches |
| `Ital Panini` | Italian Panini | Super Sandwiches |
| `Philly Stk Sand` | Philly Steak Sandwich | Super Sandwiches |
| `Philly Chx Sand` | Philly Chicken Sandwich | Super Sandwiches |
| `Philly Stk` | Philly Steak | Super Sandwiches |
| `Philly Chx` | Philly Chicken | Super Sandwiches |
| `Buf Chix Sand` | Buffalo Chicken Sandwich | Super Sandwiches |
| `Buffalo Chix Sa` | Buffalo Chicken Sandwich | Super Sandwiches |
| `1/2BuffChixSand` | 1/2 Buffalo Chicken Sandwich | Super Sandwiches |
| `Chix Parm Sand` | Chicken Parm Sandwich | Super Sandwiches |
| `Chix Parm` | Chicken Parmesan | Super Sandwiches |
| `Clara CBR` | Clara's Chicken Bacon Ranch | Super Sandwiches |
| `Mat Mtball` | Matteo's Meatball | Super Sandwiches |
| `Don Corl` | Don Corleone | Super Sandwiches |
| `Gia Srira` | Gia's Sriracha Slaw Chicken & Swiss | Super Sandwiches |
| `Fr Dip` | French Dip | Super Sandwiches |
| `Charb roiled Sa` | Charbroiled Sandwich | Super Sandwiches |
| `Chix Philly Sa` | Chicken Philly Sandwich | Super Sandwiches |
| `Dino Burger San` | Dino Burger Sandwich | Gourmet Burgers |
| `Dino Burger Sa` | Dino Burger Sandwich | Gourmet Burgers |
| `Dino B urger San` | Dino Burger Sandwich | Gourmet Burgers |

---

## Burgers

| Raw Text | Corrected Name | Menu Section |
|---|---|---|
| `Veg Chip BLK` | Vegetarian Chipotle Black Bean Burger | Gourmet Burgers |
| `Stlhse Burger` | Steakhouse Burger | Gourmet Burgers |
| `Maria Dbl Chz` | Maria's Double Cheesy | Gourmet Burgers |
| `Sal Srira` | Sal's Sriracha Slaw & Swiss | Gourmet Burgers |
| `Pep Jk Mush` | Pepper Jack Mushroom Burger | Gourmet Burgers |
| `Buf Bacon` | Buffalo Bacon Burger | Gourmet Burgers |
| `Buf Bleu` | Buffalo Bleu Burger | Gourmet Burgers |
| `Buf Chix Burger` | Buffalo Chicken Burger | Gourmet Burgers |

---

## Wings

| Raw Text | Corrected Name | Notes |
|---|---|---|
| `Sw & Hot` | Sweet & Hot | Award-winning flavor |
| `Swt Hot` | Sweet & Hot | Alternate abbreviation |
| `G & B` | Garlic & Butter | |
| `G & P` | Garlic & Parmesan | |
| `Sup Lewis` | Super Lewis | "The Hottest" flavor on menu |
| `Slicker` | *(keep as-is)* | Real flavor: BBQ + Hot + Garlic |

---

## Appetizers (Warm Ups)

| Raw Text | Corrected Name | Menu Section |
|---|---|---|
| `Bskt Home Fry` | Basket of Home Fries | Warm Ups |
| `Bskt Skny Mny` | Basket of Skinny Minny Fries | Warm Ups |
| `Bskt Chip` | Basket of Chippers | Warm Ups |
| `Bskt HCB` | Basket of Hot Cheese Balls | Warm Ups |
| `Bav Pret` | Bavarian Pretzels & Beer Cheese Dip | Warm Ups |
| `Buf Chix Dip` | Buffalo Chicken Dip | Warm Ups |
| `Spin Art Dip` | Spinach & Artichoke Dip | Warm Ups |
| `Awe On Pet` | Awesome Onion Petals | Warm Ups |
| `Pot S kins` | Potato Skins | Warm Ups |

---

## Salads

| Raw Text | Corrected Name | Menu Section |
|---|---|---|
| `Chix Bac Ranch` | Chicken Bacon Ranch Salad | Salads |
| `Buf Chix Sal` | Buffalo Chicken Salad | Salads |
| `Spin Chix Sal` | Spinach Chicken Salad | Salads |
| `Chrb Chix Sal` | Charbroiled Chicken Salad | Salads |
| `Chrb Stk Sal` | Charbroiled Steak Salad | Salads |
| `Spinach Chix S` | Spinach Chicken Salad | Salads |

---

## Platters (Double Play)

| Raw Text | Corrected Name | Menu Section |
|---|---|---|
| `Cajun Bkd Chx` | Cajun Baked Chicken | Double Play Platter |
| `Ter Grll Chx` | Teriyaki Grilled Chicken | Double Play Platter |
| `Buf Mac Chz` | Buffalo Mac & Cheese | Double Play Platter |
| `Bac Mac Chz` | Bacon Mac & Cheese | Double Play Platter |

---

## Ribs

| Raw Text | Corrected Name | Menu Section |
|---|---|---|
| `1/2 Rack Plt` | 1/2 Rack Platter | Dino's Sweet BBQ Ribs |
| `Full Rack Plt` | Full Rack Platter | Dino's Sweet BBQ Ribs |
| `Rib Shrmp Plt` | Rib & Shrimp Platter | Dino's Sweet BBQ Ribs |
| `1/2 Rack Wi` | 1/2 Rack & Wings | Dino's Sweet BBQ Ribs |
| `1/2 Rack &10 Wi` | 1/2 Rack & 10 Wings | Dino's Sweet BBQ Ribs |

---

## Drinks & Misc

| Raw Text | Corrected Name | Notes |
|---|---|---|
| `IC LITE` | Iron City Light | Local Pittsburgh beer |
| `IC LI TE` | Iron City Light | Split-word printer artifact |
| `Italian City Light` | Iron City Light | OCR misread |
| `MICH ULTRA` | Michelob Ultra | |
| `MICH ULTR` | Michelob Ultra | Truncated |
| `Miche Ultra` | Michelob Ultra | OCR misread |
| `BUSCH LIGHT` | Busch Light | |
| `BLAKE S CIDER` | Blake's Cider | |
| `REDDS APPLE` | Redd's Apple Ale | |
| `Pino Grigio` | Pinot Grigio | OCR misread |
| `Diet Mo untain D` | Diet Mountain Dew | Split-word printer artifact |
| `Diet Mo` | Diet Mountain Dew | Truncated |

---

## Modifiers

| Raw Text | Corrected Name |
|---|---|
| `CHX` | Chicken |
| `Chix` | Chicken |
| `HOME FRY` | Home Fry |
| `Home FRY` | Home Fry |
| `FF` | French Fries |
| `Butte` | Butter |
| `DOWNGRD C` | Downgrade to Chippers |
| `DOWNGRD F` | Downgrade to Fries |

---

## Printer Line-Break Artifacts

The thermal printer frequently splits words across two lines with embedded newline
characters. These are fixed by stripping `\n` and `\r` before any other processing.

Examples seen in raw data:
- `Wi\nngs` → `Wings`
- `Ch\neck#:` → `Check#:`
- `Sl\noppy` → `Sloppy`
- `IC LI\nTE` → `IC LITE` → `Iron City Light`

---

## Garbage Filter

The following strings are removed entirely as they are not food items:

`UUS10U DigiCert Inc`, `U DigiCert TLS RSA SHA256 2020`, `Pin`, `Ra`, `Hom`,
`Grav`, `Chi`, `Buf`, `Coron`, `Melt`, `Hot`, `Mild`, `Draft`, `Fried`,
`Italian`, `Grilled`, `NO MUSTARD`, `Mustard`, `Cheese`, `ToGo`, `Small`,
`Large`, `Skinny Fry`, `Home Fry`, `Cole Slaw`, `Ranch`, `Blue`, `Peppercorn`,
`Chix`, `Philly`, `No Pink`, `Cajun`

Any item name under 3 characters is also discarded.

---

*Last updated: Week 2 — verified against dinoslatrobe.com/menu*
