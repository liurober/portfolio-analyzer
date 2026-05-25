# instagram-scanner

Instagram saved-post scanner for Rob Liu — collect, extract, and route posts to Obsidian + Google Sheets.

## What it does

Scans saved Instagram collections via the private API, extracts content with Claude vision, and saves:
- **Travel posts** → Obsidian `Instagram/Travel/{City}/` + Travel Hit List Excel
- **AI/Prompt posts** → Obsidian `Instagram/AI-Skills/` or `Instagram/AI-Prompts/`
- **Food & Drink** → Obsidian `Instagram/Food-Drink/`

## Scripts

| Script | Purpose |
|---|---|
| `collect_collection_urls.py` | Snapshot all collection URLs via Instagram API |
| `scan_from_urls.py` | Process posts → Obsidian notes + Excel |
| `build_travel_sheet.py` | Rebuild Travel Hit List Excel from Obsidian notes |
| `cleanup_travel_notes.py` | Fix missing addresses + delete junk entries |
| `run_after_taiwan.sh` | Chain: collect → scan all → build Excel |

## Skill

See [SKILL.md](SKILL.md) for the full workflow documentation including post-scan audit process.

## Setup

```bash
pip install anthropic openpyxl faster-whisper requests pillow
```

Configure `~/.instagram-session.json` with session cookies before scanning.
