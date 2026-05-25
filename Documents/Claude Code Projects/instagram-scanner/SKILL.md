---
name: instagram-scan
description: Full lifecycle Instagram saved-post scanner — collect via API, extract + route to Obsidian + Google Sheets, then audit and clean up. Invoke for any Instagram scan or post-scan maintenance task.
---

# Instagram Scan

Automates extraction, routing, and quality control of Rob's saved Instagram posts.

---

## Collections and Routing

| Collection | Obsidian Folder | Also → Sheet? |
|---|---|---|
| AI | `Instagram/AI-Skills/` | No |
| AI prompt | `Instagram/AI-Prompts/` | No |
| Japan, Seattle, Taiwan, LA, Vancouver, Bangkok, Korea, Vegas, London, Paris, New York, Barcelona, Italy, Spain, Iceland | `Instagram/Travel/{City}/` | Yes → Travel Hit List |
| Cocktail, Recipes | `Instagram/Food-Drink/` | No |
| Baby Item | **Skip** | — |

---

## State File (Deduplication)

Path: `~/.instagram-scan-state.json`

```json
{
  "processed_posts": ["https://www.instagram.com/p/ABC123/"],
  "failed_posts":    ["https://www.instagram.com/p/XYZ789/"]
}
```

- Load on startup. Create with empty arrays if missing.
- Append to `processed_posts` immediately after saving each note.
- Append to `failed_posts` on error/timeout (prevents infinite retries).
- Skip any URL already in either list.

---

## Scanning Workflow

### Step 1 — Collect URLs (API-first, no Playwright)

Use the Instagram private API — faster and avoids Playwright rate-limiting:

```
GET https://www.instagram.com/api/v1/feed/collection/{collection_id}/posts/?num_results=50
Headers:
  X-IG-App-ID: 936619743392459
  Cookie: <session cookies from browser>
```

Use `collect_collection_urls.py` to iterate all collections and write URLs to JSON.
Paginate using `?max_id=` cursor until no more results.

### Step 2 — Extract and Route Posts

For each URL not in the state file:

1. Fetch post page (or use API JSON).
2. Screenshot for Claude vision analysis.
3. Extract content using schema below — **one note per identified place per post**.
4. Save to Obsidian.
5. For Travel: also append row to Travel Hit List Excel.
6. Append URL to `processed_posts`, save state file immediately.

### Step 3 — Video Handling

**Download — always use curl, never urllib (urllib hangs on slow body reads):**
```python
subprocess.run(
    ["curl", "-sS", "--max-time", "60", "-o", str(tmp), video_url],
    timeout=75, capture_output=True
)
```

**Transcription — multiprocessing hard-kill, never ThreadPoolExecutor:**
```python
# ThreadPoolExecutor.shutdown(wait=True) blocks even after TimeoutError
# Use multiprocessing.Process + terminate()/kill() instead
# Skip files > 8 MB — they hang Whisper indefinitely
MAX_SIZE_MB = 8
TIMEOUT = 120

if video_path.stat().st_size / 1024**2 > MAX_SIZE_MB:
    return ""  # skip

proc = mp.get_context("fork").Process(target=_whisper_worker, args=(path, queue))
proc.start()
proc.join(timeout=TIMEOUT)
if proc.is_alive():
    proc.terminate(); proc.join(5)
    if proc.is_alive(): proc.kill()
    return ""  # timed out
```

---

## Extraction Schema

### Travel Posts

**Critical rule:** `Place name` must be the actual **venue name**, NOT the post caption.
If the post caption is used as-is, the note title is wrong and must be corrected.

```
Place name:       (actual restaurant/hotel/venue name — not the caption)
City:             (city and country)
Type:             restaurant / hotel / bar / cafe / area / activity / shop / other
Address:          (street address — extract from post if visible)
Why recommended:  (from caption, summarized — key reasons)
Instagram source: (@accountname)
```

### AI Skills
```
Technique name:
Description:
Use case:
Source account:
Tags: (3–5 relevant tags)
```

### AI Prompts
```
The prompt: (verbatim if visible)
What it does:
When to use it:
Source account:
```

### Food & Drink
```
Name:
Type: cocktail / recipe / ingredient tip
Description:
Key ingredients or steps:
Source account:
```

---

## Obsidian Note Format

**Filename:** `YYYY-MM-DD-[slug].md`
Slug = first 4 words of post title/caption, lowercased, hyphenated.

**Mandatory YAML frontmatter — every note:**

For Travel:
```yaml
---
tags:
  - instagram
  - travel
  - [city-slug]     # e.g. japan, taiwan, seoul, new-york
  - [type]          # e.g. restaurant, hotel, bar
date: YYYY-MM-DD
stream: Personal
source: @accountname
collection: "Japan"
city: "Tokyo, Japan"
type: "restaurant"
instagram_url: "https://www.instagram.com/p/..."
media_type: image   # or video
---
```

For AI Skills / AI Prompts:
```yaml
---
tags:
  - instagram
  - ai-skills       # or ai-prompts
  - [extracted tags]
date: YYYY-MM-DD
stream: AI
source: @accountname
---
```

For Food & Drink:
```yaml
---
tags:
  - instagram
  - food-drink
  - [cocktail or recipe]
date: YYYY-MM-DD
stream: Personal
source: @accountname
---
```

**Image format:** ALWAYS use Obsidian wiki-links.

```
✓ CORRECT:   ![[2026-05-21-place-img1.jpg]]
✗ WRONG:     ![alt text](path/to/image.jpg)
```

Standard markdown images do not render in Obsidian. This has caused display issues before.

---

## Travel Hit List Excel

File: `/Users/robertliu/Desktop/Travel Hit List.xlsx`
Google Drive ID: `1nMXM11rDOJ-d07R6w29eOavLpEz-GjYX`

Columns per city sheet:
`Place Name | City | Type | Address | Cuisine | Price Range | Why Recommended | Highlights | Hours | Reservation | Source | Instagram | Date Added`

Summary sheet: auto-generated with city counts and total.

- Rebuild Excel after any scan: `python3 build_travel_sheet.py`
- Re-upload to Google Drive after every rebuild and cleanup

---

## Post-Scan Audit Workflow

Run after every major scan batch:

### 1. Image Link Audit
```bash
python3 audit_images.py   # verifies all ![[]] refs exist on disk
```
Expected: 0 missing.
If images exist on disk but don't show in Obsidian → iCloud sync lag (not a real error). Wait 5–10 min.

### 2. Address Quality Audit

Flag all travel notes where `**Address:**` is null / empty / "Not listed" / "Not found".
Group by city and count.

### 3. Classify Missing-Address Entries

For each no-address entry, decide:

**→ Real place: find address and fix**
- Has a specific, identifiable venue name
- Single physical location
- Action: web search the name + city → update `**Address:**` in note AND Excel cell

**→ Junk: delete note + Excel row**
- Place name is a post caption / sentence fragment / emoji / hashtag
- Generic content: listicles, tips, vlogs, apps, product recommendations
- Multi-place posts with no single identifiable venue
- Rule applied strictly: no verified address = deleted

**Detection heuristics for junk:**
- Title starts with a verb, hashtag, emoji, or number ("3 best...", "#japan", "🩶")
- Title is longer than ~40 characters and reads like a sentence
- Title contains "send this to", "save this", "share this", "who do you"
- Product, app, or informational content (no physical location)
- No specific venue name identifiable from note content

### 4. Title Quality Fix

For notes with vague caption-derived titles:
- Update `# H1` to the actual venue name
- Update Excel "Place Name" column to match
- Update `**Address:**` field

Use `cleanup_travel_notes.py` to apply all fixes and deletions in batch.

### 5. Rebuild and Re-upload Excel

```bash
python3 build_travel_sheet.py
# Then upload updated file to Google Drive (Drive ID above)
```

---

## Scripts Reference

| Script | Purpose |
|---|---|
| `collect_collection_urls.py` | Snapshot all collection URLs via Instagram API |
| `scan_from_urls.py` | Process posts from URL file → Obsidian + Excel |
| `scan.py` | Full scan entry point (collect + scan combined) |
| `build_travel_sheet.py` | Read Travel notes → rebuild Excel by city |
| `cleanup_travel_notes.py` | Fix addresses + delete junk (post-scan maintenance) |
| `audit_images.py` | Verify all `![[]]` image refs exist on disk |
| `run_after_taiwan.sh` | Chain: collect → scan all → build Excel |

All scripts located at:
`/Users/robertliu/Documents/Claude Code Projects/instagram-scanner/`

---

## Efficient Batch Scan Order

1. Run `collect_collection_urls.py` once to snapshot all collections.
2. Scan Taiwan first (largest, ~366 posts): `scan_from_urls.py --only Taiwan`
3. Chain all remaining: `run_after_taiwan.sh` (runs in background)
4. Monitor every 270s (stays inside Claude's 5-minute cache window).
5. After completion: `build_travel_sheet.py`
6. Then run post-scan audit (§ above).

---

## Known Issues and Fixes

| Issue | Root Cause | Fix |
|---|---|---|
| Whisper hangs indefinitely | `ThreadPoolExecutor.__exit__` calls `shutdown(wait=True)`, blocks after timeout | Use `multiprocessing.Process` + `terminate()`/`kill()` |
| Large video download hangs | `urllib r.read()` blocks on slow transfers, timeout only applies to connect | Use `curl --max-time 60` subprocess |
| Images not displaying in Obsidian | iCloud sync lag — files on disk but not yet synced to iCloud path | Wait 5–10 min; use `audit_images.py` to confirm refs are valid |
| Claude API 529 overload | High load on Claude API | Catch `anthropic.InternalServerError`, save note with available data, continue |
| Excel too large for base64 MCP upload | ~212KB file = ~283KB base64 — may exceed MCP parameter limit | Use Chrome file upload or update via Drive UI |
| Place names = post captions | Claude extraction uses caption as title when venue name is unclear | Post-scan title fix pass in `cleanup_travel_notes.py` |
| Taiwan scan rate limiting | Instagram throttles rapid API calls | Add 1–2s delay between requests; catch 429s and backoff |

---

## Requirements Log (all sessions)

### Data Collection
- Use Instagram private API (`/api/v1/feed/collection/`), not Playwright — Playwright rate-limits
- Paginate with `?max_id=` cursor
- State file deduplicates across sessions; `failed_posts` prevents infinite retries

### Extraction Quality
- One Obsidian note per identified place per post (multi-place extraction)
- Note H1 = actual venue name, never the raw post caption
- Extract address from caption when visible; flag for post-scan audit when absent
- Videos: capture frame + transcript; add `video` tag

### Storage Format
- Image format: `![[filename.jpg]]` (wiki-link) — never `![](path)` (standard markdown)
- City subfolders: `Instagram/Travel/{City}/`
- Mandatory YAML frontmatter on every note (stream, tags, city, type, source, date)
- `failed_posts` in state file (not just `processed_posts`)

### Data Quality
- Post-scan: audit all travel notes for missing addresses
- Real places with no address → web-search and fill (note + Excel)
- Non-place entries (tips, listicles, vlogs, apps, products) → delete note + Excel row
- Hard rule: travel entry without a verified street address = delete or fix

### Excel / Google Sheets
- Rebuilt from Obsidian notes source-of-truth after each scan
- One sheet per city + Summary sheet with totals
- Re-upload to Google Drive after every rebuild and cleanup run
- Drive file ID: `1nMXM11rDOJ-d07R6w29eOavLpEz-GjYX`

### Automation
- State file prevents duplicate processing across sessions
- `run_after_taiwan.sh` chains all steps end-to-end
- Monitor at 270s intervals (inside Claude's 5-min cache window, cheaper)
