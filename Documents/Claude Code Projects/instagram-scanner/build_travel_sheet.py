#!/usr/bin/env python3
"""
Build Travel Hit List Excel from enriched Obsidian notes.
One tab per city/collection. Uploads to Google Drive via browser.
"""

import json
import re
from pathlib import Path
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

OBSIDIAN_BASE = Path("/Users/robertliu/Library/Mobile Documents/iCloud~md~obsidian/Documents/Rob's Valut/Rob's Personal Vault")
TRAVEL_FOLDER = OBSIDIAN_BASE / "Instagram/Travel"
OUTPUT_PATH   = Path.home() / "Desktop" / "Travel Hit List.xlsx"

TODAY = datetime.now().strftime("%Y-%m-%d")

# ── Styling ──────────────────────────────────────────────────────────────────────
HEADER_FILL   = PatternFill("solid", fgColor="1A1A2E")   # dark navy
HEADER_FONT   = Font(bold=True, color="FFFFFF", size=11)
ALT_FILL      = PatternFill("solid", fgColor="F0F4FF")   # light blue-grey
WHITE_FILL    = PatternFill("solid", fgColor="FFFFFF")
LINK_FONT     = Font(color="0563C1", underline="single")
NORMAL_FONT   = Font(size=10)
WRAP_ALIGN    = Alignment(wrap_text=True, vertical="top")
CENTER_ALIGN  = Alignment(horizontal="center", vertical="top")
THIN_BORDER   = Border(
    bottom=Side(style="thin", color="D0D0D0"),
    right=Side(style="thin", color="D0D0D0"),
)

COLUMNS = [
    ("Place Name",        28),
    ("Type",              14),
    ("Address",           35),
    ("Cuisine",           16),
    ("Price Range",       12),
    ("Why Recommended",   50),
    ("Highlights",        45),
    ("Hours",             18),
    ("Reservation",       12),
    ("Source",            18),
    ("Instagram",         12),
    ("Date Added",        12),
]


def _parse_field(content: str, field: str) -> str:
    m = re.search(rf'^{field}:\s*"?([^"\n]+)"?\s*$', content, re.MULTILINE)
    return m.group(1).strip() if m else ""

def _parse_section(content: str, heading: str) -> str:
    m = re.search(rf'## {heading}\n\n(.+?)(?:\n##|\Z)', content, re.DOTALL)
    return m.group(1).strip() if m else ""

def _parse_bold_field(content: str, label: str) -> str:
    m = re.search(rf'\*\*{label}:\*\*\s*(.+)', content)
    return m.group(1).strip() if m else ""

def read_travel_notes() -> dict[str, list[dict]]:
    """Read all travel notes and group by collection."""
    by_city: dict[str, list[dict]] = {}

    for note_path in sorted(TRAVEL_FOLDER.rglob("*.md")):
        try:
            content = note_path.read_text(encoding="utf-8")

            collection = _parse_field(content, "collection")
            if not collection:
                # Fall back: find travel city tag
                tags_match = re.search(r'tags:.*?(?=\ndate:)', content, re.DOTALL)
                tags = tags_match.group(0) if tags_match else ""
                known = ["Japan","Taiwan","Korea","Bangkok","Seattle","LA","Vancouver",
                         "Vancuver","Vegas","London","Paris","New York","Barcelona",
                         "Italy","Spain","Iceland"]
                collection = next((c for c in known if c.lower().replace(" ","-") in tags.lower()), "Other")

            place_name  = _parse_bold_field(content, "City")  # Actually the h1
            h1 = re.search(r'^# (.+)$', content, re.MULTILINE)
            place_name  = h1.group(1).strip() if h1 else note_path.stem

            address     = _parse_bold_field(content, "Address")
            place_type  = _parse_bold_field(content, "Type") or _parse_field(content, "type")
            cuisine     = _parse_bold_field(content, "Cuisine")
            price_range = _parse_bold_field(content, "Price Range")
            hours       = _parse_bold_field(content, "Hours")
            reservation = _parse_bold_field(content, "Reservation needed")
            source      = _parse_field(content, "source")
            ig_url      = _parse_field(content, "instagram_url")
            date_added  = _parse_field(content, "date")

            why         = _parse_section(content, "Why Recommended")
            highlights_raw = _parse_section(content, "Highlights")
            # Convert "- item\n- item" to "item | item"
            highlights = " | ".join(
                l.lstrip("- ").strip()
                for l in highlights_raw.splitlines()
                if l.strip().startswith("-")
            ) if highlights_raw else ""

            # Skip notes with no meaningful place name
            if not place_name or place_name.lower() in ("unknown", "untitled"):
                continue

            by_city.setdefault(collection, []).append({
                "Place Name":      place_name,
                "Type":            place_type,
                "Address":         address if address not in ("Not listed", "") else "",
                "Cuisine":         cuisine,
                "Price Range":     price_range,
                "Why Recommended": why[:300] if why else "",
                "Highlights":      highlights[:200] if highlights else "",
                "Hours":           hours,
                "Reservation":     reservation,
                "Source":          source,
                "Instagram":       ig_url,
                "Date Added":      date_added or TODAY,
            })

        except Exception as e:
            print(f"  Skip {note_path.name}: {e}")

    return by_city


def _apply_header(ws, col_defs):
    """Write styled header row."""
    for col_idx, (name, width) in enumerate(col_defs, 1):
        cell = ws.cell(row=1, column=col_idx, value=name)
        cell.font   = HEADER_FONT
        cell.fill   = HEADER_FILL
        cell.alignment = CENTER_ALIGN
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    ws.row_dimensions[1].height = 22
    ws.freeze_panes = "A2"


def _write_row(ws, row_idx: int, row: dict, col_defs):
    fill = ALT_FILL if row_idx % 2 == 0 else WHITE_FILL
    for col_idx, (name, _) in enumerate(col_defs, 1):
        val = row.get(name, "")
        cell = ws.cell(row=row_idx, column=col_idx, value=val)
        cell.fill      = fill
        cell.border    = THIN_BORDER
        cell.alignment = WRAP_ALIGN

        # Make Instagram URL a hyperlink
        if name == "Instagram" and val and val.startswith("http"):
            cell.value     = "View post"
            cell.hyperlink = val
            cell.font      = LINK_FONT
        else:
            cell.font = NORMAL_FONT

    ws.row_dimensions[row_idx].height = 60


def build_excel(by_city: dict[str, list[dict]]) -> Path:
    wb = openpyxl.Workbook()

    # Remove default sheet
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    # Sort: common cities first
    priority = ["Japan","Taiwan","Korea","Bangkok","Seattle","LA","Vancouver",
                "Vegas","London","Paris","New York","Barcelona","Italy","Spain","Iceland"]
    ordered = sorted(by_city.keys(), key=lambda c: (priority.index(c) if c in priority else 99, c))

    # Summary tab first
    _build_summary(wb, by_city, ordered)

    for city in ordered:
        rows = by_city[city]
        ws = wb.create_sheet(title=city[:31])  # Sheet name max 31 chars
        _apply_header(ws, COLUMNS)

        for i, row in enumerate(rows, 2):
            _write_row(ws, i, row, COLUMNS)

        # Auto-filter
        ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}1"

        print(f"  {city}: {len(rows)} places")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(OUTPUT_PATH))
    print(f"\n✓ Saved: {OUTPUT_PATH}")
    return OUTPUT_PATH


def _build_summary(wb, by_city: dict, ordered: list):
    """Create a Summary tab with counts per city."""
    ws = wb.create_sheet(title="Summary", index=0)

    # Title
    ws.merge_cells("A1:D1")
    title_cell = ws["A1"]
    title_cell.value     = "Travel Hit List"
    title_cell.font      = Font(bold=True, size=16, color="1A1A2E")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 36

    # Sub-header
    ws.merge_cells("A2:D2")
    sub = ws["A2"]
    sub.value     = f"Generated {TODAY}  •  {sum(len(v) for v in by_city.values())} total recommendations"
    sub.font      = Font(size=10, color="666666", italic=True)
    sub.alignment = Alignment(horizontal="center")
    ws.row_dimensions[2].height = 18

    # Column headers
    headers = ["City", "# Places", "Types", ""]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col, value=h)
        cell.font      = HEADER_FONT
        cell.fill      = HEADER_FILL
        cell.alignment = CENTER_ALIGN

    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 10
    ws.column_dimensions["C"].width = 40
    ws.column_dimensions["D"].width = 15

    for i, city in enumerate(ordered, 5):
        rows = by_city[city]
        types = ", ".join(sorted({r.get("Type","") for r in rows if r.get("Type")}))

        ws.cell(row=i, column=1, value=city).font = Font(bold=True, size=11)
        ws.cell(row=i, column=2, value=len(rows)).alignment = CENTER_ALIGN
        ws.cell(row=i, column=3, value=types[:80]).font = Font(size=10, color="444444")

        # Link to sheet tab
        link_cell = ws.cell(row=i, column=4, value="→ View")
        link_cell.hyperlink = f"#{city}!A1"
        link_cell.font      = LINK_FONT
        link_cell.alignment = CENTER_ALIGN

        fill = ALT_FILL if i % 2 == 0 else WHITE_FILL
        for col in range(1, 5):
            ws.cell(row=i, column=col).fill = fill

    ws.freeze_panes = "A5"


if __name__ == "__main__":
    print("\nBuilding Travel Hit List Excel...")
    print(f"Reading notes from: {TRAVEL_FOLDER}")
    print()

    by_city = read_travel_notes()
    total = sum(len(v) for v in by_city.values())
    print(f"Found {total} places across {len(by_city)} cities\n")

    if not by_city:
        print("No notes found. Run scan.py --enrich first.")
        exit(1)

    path = build_excel(by_city)
    print(f"\nDone. File saved to Desktop: {path.name}")
    print("Now uploading to Google Drive...")
