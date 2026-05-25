#!/usr/bin/env python3
"""
cleanup_travel_notes.py
- Fixes missing addresses for real places (Excel + Obsidian notes)
- Renames vague note titles to proper place names
- Deletes junk entries (non-place posts) from Excel + Obsidian
"""

import re
import shutil
from pathlib import Path

import openpyxl

VAULT = Path("/Users/robertliu/Library/Mobile Documents/iCloud~md~obsidian/Documents/Rob's Valut/Rob's Personal Vault/Instagram/Travel")
EXCEL = Path("/Users/robertliu/Desktop/Travel Hit List.xlsx")

# ─── REAL PLACES: fix address (and optionally rename title) ───────────────────
# (sheet, current_excel_place_name, new_place_name, new_address)
FIXES = [
    ("Japan",    "Banten (盤天)",                                          "Banten (盤天)",                          "1-1-4 Ebisuminami, Shibuya-ku, Tokyo 150-0022, 5F Murata Building"),
    ("Japan",    "COIN LUCK",                                              "COIN LUCK",                              "ROUTE89 BLDG. 3F, 4-13-9 Higashi Ueno, Taito-ku, Tokyo 110-0015"),
    ("Japan",    "Kan Agari 燗アガリ",                                     "Kan Agari 燗アガリ",                     "3F New YS Building, 7-16-12 Nishi-Shinjuku, Shinjuku-ku, Tokyo"),
    ("Japan",    "Oniku Karyu",                                            "Oniku Karyu",                            "1-14-6 Ginza, Chuo-ku, Tokyo 104-0061, 7F VORT Ginza Briller"),
    ("Japan",    "Ninja Tokyo",                                            "Ninja Tokyo",                            "Shin-Otemachi Building B1, 2-2-1 Otemachi, Chiyoda-ku, Tokyo"),
    ("Japan",    "ROTOTO",                                                 "ROTOTO",                                 "2-28-3 Nishihara, Shibuya-ku, Tokyo 151-0066, Clover Building 1F"),
    ("Japan",    "在東京就能吃到❗北海道螃蟹🦀",                             "蟹地獄 (Kani Jigoku) Shimbashi",         "B1F New Shinbashi Building, 2-16-1 Shinbashi, Minato-ku, Tokyo"),
    ("Japan",    "鴨TO蔥",                                                 "鴨TO蔥",                                 "6-3-5 Ueno, Taito-ku, Tokyo (Okachimachi branch)"),
    ("Japan",    "Finlandia",                                              "Finlandia Bar Gion",                     "Gion-machi minamigawa, Higashiyama-ku, Kyoto 605-0074"),
    ("Taiwan",   "蕃薯藤溫泉會所 (Organic Yam Nature Onsen)",              "蕃薯藤溫泉會所 (Organic Yam Nature Onsen)", "142 Luofu, Fuxing District, Taoyuan City, Taiwan"),
    ("Taiwan",   "蕃薯藤溫泉會館 Nature Onsen",                            "蕃薯藤溫泉會館 Nature Onsen",            "142 Luofu, Fuxing District, Taoyuan City, Taiwan"),
    ("Taiwan",   "徐家私廚 (Xu's Private Kitchen)",                        "徐家私廚 (Xu's Private Kitchen)",        "No. 37, Lane 313, Fuxing North Road, Songshan District, Taipei"),
    ("Taiwan",   "新莊羊肉棧",                                             "新莊羊肉棧",                             "No. 160, Hougang 1st Road, Xinzhuang District, New Taipei City"),
    ("Korea",    "Dalmaji Plaza BBQ",                                      "Dalmaji Plaza BBQ",                      "112-1 Euljiro, Jung-gu, Seoul"),
    ("Korea",    "Growers",                                                "Growers",                                "Yeonhui-ro 27-gil 52, Seodaemun-gu, Seoul"),
    ("Seattle",  "An authentic Sicilian experience, close to home. 🫶🏼",  "La Fontana Siciliana",                   "120 W Madison St, Belltown, Seattle, WA 98121"),
    ("Seattle",  "First Michelin Recognized Restaurant in the PNW!! ⭐️ @farzicafe.usa", "Farzi Cafe", "515 Bellevue Square, Bellevue, WA 98004"),
    ("Seattle",  "Gorgeous Mexican Restaurant in Bellevue 🌮",             "Cantina Monarca",                        "504 Bellevue Way NE, Bellevue, WA 98004"),
    ("Seattle",  "Must try spot in Chinatown, Seattle!",                   "Itsumono",                               "610 S Jackson St, Seattle, WA 98104"),
    ("Seattle",  "Single Shot",                                            "Single Shot",                            "611 Summit Ave E, Seattle, WA 98101"),
    ("Seattle",  "We love it over at @carnationfarms 😌",                  "Carnation Farms",                        "28901 NE Carnation Farm Rd, Carnation, WA 98014"),
    ("Seattle",  "@wear.willa (the cutest lifestyle + clothing shop in Queen Anne!) hosted a wonde", "El Encanto", "1170 Carillon Point, Kirkland, WA 98033"),
    ("Seattle",  "What's your Ballard Lunch Spot? It might become @bapshimseattle . It's a lunch o", "Bap Shim Seattle", "5210 Ballard Ave NW (back entrance at 20th Ave NW), Seattle, WA 98107"),
    ("Vancouver","Okeya Kyujiro",                                          "Okeya Kyujiro",                          "1038 Mainland St., Vancouver, BC V6B 2T4"),
    ("New York", "Let our menu be your gateway to an extraordinary sensory experience, where tradi", "The Office of Mr. Moto", "120 Saint Marks Place, New York, NY 10009"),
    ("Iceland",  "Soak in our warm geothermal waters and journey through the unique Seven-Step Rit", "Sky Lagoon",  "Vesturvör 44-48, 200 Kópavogur, Iceland"),
]

# ─── JUNK: delete from Excel + Obsidian ───────────────────────────────────────
DELETES = [
    # Japan – non-place posts
    ("Japan", "Expandable Kraft Paper Long Stool"),
    ("Japan", "Matcha in Japan"),
    ("Japan", "1. Smokeless moxibustion – A self-heating patch that warms and relaxes muscles w"),
    ("Japan", "3 legends that you have to visit in Japan! From aged coffee to the most charisma"),
    ("Japan", "3 Tokyo Music Bars That Tourists Don't Know About #japan #japantrip #japantravel"),
    ("Japan", "Did we take advantage of the yen or did it take advantage of us? 😭💸 #japanshoppi"),
    ("Japan", "en↓東京から日帰り、電車で約1時間。暖かくなったら行きたい海カフェBEST10。"),
    ("Japan", "Few things in this life hit like a new set of stationery items, and Tokyo knows"),
    ("Japan", "Getting to Fuuzoku Areas in Tokyo: A Step-by-Step Guide"),
    ("Japan", "In Japan, there's a gym where trainers encourage and motivate members to work ou"),
    ("Japan", "#japan #anime"),
    ("Japan", "Let's learn Japanese Swear Words guys!😎🖕"),
    ("Japan", "My biggest nightmare in Japan 🥲"),
    ("Japan", "Save this for your trip!"),
    ("Japan", "Send this to your friend going to Japan!"),
    ("Japan", "Send this to your Wagyu-loving friends!"),
    ("Japan", "Share this video with your Japan group chat!"),
    ("Japan", "The Best Hotel in Japan (World's Top 50 Hotels)"),
    ("Japan", "Tokyo is THE place to shop. If you're on the hunt for a new golfing wardrobe (or"),
    ("Japan", "When you come to Japan… buy salt!"),
    ("Japan", "Who do you wanna experience this onsen resort with? 🧖‍♀️💆🏻‍♀️🇯🇵"),
    ("Japan", "不少人早上起床後會發現自己臉部水腫，低頭時看到雙下巴😩除了花錢做美容或按摩外，如何能輕鬆瘦臉呢？日前，日本YouTuber「トレぴな」（Torepina）分享了"),
    ("Japan", "去東京發限時超多人私訊問我的酒吧😻"),
    ("Japan", "Don Quijote"),
    # Taiwan
    ("Taiwan", "2026中央政策保底10萬"),
    ("Taiwan", "Speakeasy (unnamed - 6 locations across Taiwan)"),
    ("Taiwan", "孕婦在家破水的正確處理方法！按照這個步驟處理， 到時候不會手忙腳亂 #懷孕 #孕產 #孕期經驗分享 #孕期 #新手媽媽 #孕婦"),
    ("Taiwan", "🩶🩶續"),
    ("Taiwan", "In the relentless pursuit of the American Dream, we're often told to hustle, hus"),
    ("Taiwan", "Unknown Beef Noodle Soup Restaurant"),
    ("Taiwan", "陶棧咖啡 (Tao Zhan Coffee)"),
    ("Taiwan", "Yubaba's Bathhouse-Inspired Hotel"),
    ("Taiwan", "滔涛 Taotao"),
    ("Taiwan", "台中山洋御府天公廟"),
    # Korea
    ("Korea", "Kakao Taxi"),
    ("Korea", "Golf Resort with Swimming Pool & Spa"),
    ("Korea", "釜飯 (Kama-meshi)"),
    ("Korea", "영신축산 (Young Shin Livestock)"),
    # Seattle
    ("Seattle", "a perfect day in cap hill if i do say so myself #seattle #capitolhill #washingto"),
    ("Seattle", "Fire Halloween Outfits! 🤩"),
    ("Seattle", "Rosette cookie filled with farmers' cheese and Walla Walla onion jam."),
    ("Seattle", "Seattle's Ultimate Dining Destination Between Pike & Pine 🍽️✨"),
    ("Seattle", "the perfect river camping spot near Seattle, WA 🐟"),
    ("Seattle", "This + yap = perfection! 😍"),
    ("Seattle", "Views from above."),
    ("Seattle", "Elci"),
    # LA
    ("LA", "Great day for the Sanders family 👏"),
    ("LA", "This is the safest way to build wealth in real estate but also, here's how you c"),
    # Vancouver
    ("Vancouver", "A few Amazon favorites every parent should have! From safety locks and corner gu"),
    # Vegas
    ("Vegas", "Get ready for a thrilling adventure exploring 5 secret bars with @kemoy_martin 🤩"),
    # Paris
    ("Paris", "#ADayTravel 巴黎雖然是旅遊熱門城市，但編輯卻是到了最近才第一次去。一個在巴黎工作了 8 年的友人，和我分享了一份她的私藏清單，沒有巴黎鐵塔，沒有花神"),
    # Barcelona
    ("Barcelona", "Follow for more Barcelona & other hotspots! 💌 | I've put together a list of many"),
]


def build_note_index() -> dict:
    """Returns {city_folder: {h1_lower: Path}}"""
    index = {}
    for city_dir in VAULT.iterdir():
        if not city_dir.is_dir():
            continue
        index[city_dir.name] = {}
        for md in city_dir.glob("*.md"):
            text = md.read_text(errors="ignore")
            h1 = re.search(r'^# (.+)', text, re.MULTILINE)
            if h1:
                key = h1.group(1).strip().lower()
                index[city_dir.name][key] = md
    return index


def update_note_address(path: Path, new_address: str, new_title: str | None = None):
    text = path.read_text(encoding="utf-8", errors="ignore")
    # Update Address field
    text = re.sub(
        r'(\*\*Address:\*\*\s*).*',
        lambda m: f"**Address:** {new_address}",
        text,
        count=1,
    )
    # Update H1 title if renaming
    if new_title:
        text = re.sub(
            r'^(# ).+',
            lambda m: f"# {new_title}",
            text,
            count=1,
            flags=re.MULTILINE,
        )
    path.write_text(text, encoding="utf-8")


def find_note(index: dict, city_folder: str, place_name: str) -> Path | None:
    city_map = index.get(city_folder, {})
    key = place_name.strip().lower()
    # Exact match
    if key in city_map:
        return city_map[key]
    # Prefix match (for truncated Excel names)
    for h1_key, path in city_map.items():
        if h1_key.startswith(key[:40]) or key.startswith(h1_key[:40]):
            return path
    return None


def main():
    print("Loading workbook…")
    wb = openpyxl.load_workbook(EXCEL)
    note_index = build_note_index()

    fixed = []
    deleted_notes = []
    deleted_excel_rows = []
    not_found = []

    # ── FIXES ────────────────────────────────────────────────────────────────
    print("\n=== Fixing addresses ===")
    for sheet, old_name, new_name, new_address in FIXES:
        ws = wb[sheet]
        headers = [c.value for c in ws[1]]
        name_col = next((i for i, h in enumerate(headers) if h and "place" in str(h).lower()), None)
        addr_col = next((i for i, h in enumerate(headers) if h and "address" in str(h).lower()), None)
        if name_col is None or addr_col is None:
            print(f"  SKIP {sheet}/{old_name}: columns not found")
            continue

        row_updated = False
        for row in ws.iter_rows(min_row=2):
            cell_val = row[name_col].value
            if cell_val and (str(cell_val).strip() == old_name or str(cell_val).strip().startswith(old_name[:40])):
                row[addr_col].value = new_address
                if new_name != old_name:
                    row[name_col].value = new_name
                row_updated = True
                break

        note_path = find_note(note_index, sheet, old_name)
        note_updated = False
        if note_path:
            rename = new_name if new_name != old_name else None
            update_note_address(note_path, new_address, rename)
            note_updated = True

        status = "✓" if row_updated else "✗ excel-row-not-found"
        note_status = "✓" if note_updated else "✗ note-not-found"
        print(f"  [{status} excel] [{note_status} note] {sheet}/{new_name}")
        fixed.append((sheet, new_name, row_updated, note_updated))

    # ── DELETES ──────────────────────────────────────────────────────────────
    print("\n=== Deleting junk entries ===")
    # Collect rows to delete per sheet (delete in reverse order to preserve indices)
    rows_to_delete = {}
    for sheet, place_name in DELETES:
        ws = wb[sheet]
        headers = [c.value for c in ws[1]]
        name_col = next((i for i, h in enumerate(headers) if h and "place" in str(h).lower()), None)
        if name_col is None:
            continue

        for row in ws.iter_rows(min_row=2):
            cell_val = row[name_col].value
            if cell_val and (
                str(cell_val).strip() == place_name
                or str(cell_val).strip().startswith(place_name[:40])
                or place_name.startswith(str(cell_val).strip()[:40])
            ):
                row_num = row[0].row
                rows_to_delete.setdefault(sheet, []).append(row_num)
                deleted_excel_rows.append((sheet, place_name))
                break

        note_path = find_note(note_index, sheet, place_name)
        if note_path and note_path.exists():
            note_path.unlink()
            deleted_notes.append(str(note_path.name))
            print(f"  [deleted note] {sheet}/{place_name[:60]}")
        else:
            print(f"  [no note]      {sheet}/{place_name[:60]}")

    # Delete Excel rows (reverse order so row numbers stay valid)
    for sheet, row_nums in rows_to_delete.items():
        ws = wb[sheet]
        for row_num in sorted(set(row_nums), reverse=True):
            ws.delete_rows(row_num)

    # ── Update Summary sheet ──────────────────────────────────────────────────
    summary_ws = wb["Summary"]
    city_counts = {}
    for sheet_name in wb.sheetnames:
        if sheet_name == "Summary":
            continue
        ws = wb[sheet_name]
        count = sum(1 for row in ws.iter_rows(min_row=2, values_only=True) if any(row))
        city_counts[sheet_name] = count

    # Find the total row and update
    total = sum(city_counts.values())
    for row in summary_ws.iter_rows():
        for cell in row:
            if cell.value and "total" in str(cell.value).lower():
                # Update the generated line
                pass

    print(f"\n=== Saving Excel ===")
    wb.save(EXCEL)
    print(f"  Saved: {EXCEL}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'─'*50}")
    print(f"Addresses fixed:      {len(fixed)}")
    print(f"Notes deleted:        {len(deleted_notes)}")
    print(f"Excel rows deleted:   {len(deleted_excel_rows)}")
    remaining = 728 - len(deleted_excel_rows)
    print(f"Remaining places:     {remaining}")
    print(f"{'─'*50}")

    if not_found:
        print("\nNot found (manual check needed):")
        for x in not_found:
            print(f"  {x}")


if __name__ == "__main__":
    main()
