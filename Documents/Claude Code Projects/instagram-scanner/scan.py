#!/usr/bin/env python3
"""
Instagram Saved Posts Scanner — Claude Vision Edition
API-first extraction: caption + images + video frames + audio transcript + Claude analysis.
"""

import anthropic
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── Load API key from .env file if not already set ──────────────────────────────
_env_file = Path.home() / ".instagram-scanner.env"
if _env_file.exists() and not os.environ.get("ANTHROPIC_API_KEY"):
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")

if not os.environ.get("ANTHROPIC_API_KEY"):
    print(f"""
  ── Anthropic API key not found ───────────────────────────────
  Create {_env_file} with:
    ANTHROPIC_API_KEY=sk-ant-your-key-here
  Get your key at: https://console.anthropic.com/settings/keys
  ─────────────────────────────────────────────────────────────
""")
    # Don't exit — Claude analysis will just return {} and notes will still save

import requests
from faster_whisper import WhisperModel
from playwright.sync_api import sync_playwright, Page, BrowserContext

# ── Constants ────────────────────────────────────────────────────────────────────
STATE_FILE         = Path.home() / ".instagram-scan-state.json"
SESSION_FILE       = Path.home() / ".instagram-session.json"
GSHEETS_TOKEN      = Path.home() / ".instagram-gsheets-token.json"
GSHEETS_CREDS      = Path.home() / ".instagram-gsheets-credentials.json"
OBSIDIAN_BASE      = Path("/Users/robertliu/Library/Mobile Documents/iCloud~md~obsidian/Documents/Rob's Valut/Rob's Personal Vault")
MEDIA_FOLDER       = "Instagram/_media"
INSTAGRAM_USER     = "liufongyong"
TODAY              = datetime.now().strftime("%Y-%m-%d")
POST_DELAY         = 1.5
SCROLL_DELAY       = 1.0
MAX_SCROLLS        = 60
WHISPER_MODEL_SIZE = "small"  # 244MB — significantly better on cooking audio vs base (74MB)
VIDEO_FRAMES       = 5
CLAUDE_MODEL       = "claude-haiku-4-5"
GOOGLE_SHEET_NAME  = "Travel Hit List"
GSHEETS_SCOPES     = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

_whisper_model = None
_claude_client = None

IG_SHORTCODE_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"

COLLECTIONS = {
    "AI":        {"folder": "Instagram/AI-Skills",          "type": "ai_skill",  "sheet": False},
    "AI prompt": {"folder": "Instagram/AI-Prompts",         "type": "ai_prompt", "sheet": False},
    "Japan":     {"folder": "Instagram/Travel/Japan",       "type": "travel",    "sheet": True},
    "Seattle":   {"folder": "Instagram/Travel/Seattle",     "type": "travel",    "sheet": True},
    "Taiwan":    {"folder": "Instagram/Travel/Taiwan",      "type": "travel",    "sheet": True},
    "LA":        {"folder": "Instagram/Travel/LA",          "type": "travel",    "sheet": True},
    "Vancouver": {"folder": "Instagram/Travel/Vancouver",   "type": "travel",    "sheet": True},
    "Vancuver":  {"folder": "Instagram/Travel/Vancouver",   "type": "travel",    "sheet": True},
    "Bangkok":   {"folder": "Instagram/Travel/Bangkok",     "type": "travel",    "sheet": True},
    "Korea":     {"folder": "Instagram/Travel/Korea",       "type": "travel",    "sheet": True},
    "Vegas":     {"folder": "Instagram/Travel/Vegas",       "type": "travel",    "sheet": True},
    "London":    {"folder": "Instagram/Travel/London",      "type": "travel",    "sheet": True},
    "Paris":     {"folder": "Instagram/Travel/Paris",       "type": "travel",    "sheet": True},
    "New York":  {"folder": "Instagram/Travel/New York",    "type": "travel",    "sheet": True},
    "Barcelona": {"folder": "Instagram/Travel/Barcelona",   "type": "travel",    "sheet": True},
    "Italy":     {"folder": "Instagram/Travel/Italy",       "type": "travel",    "sheet": True},
    "Spain":     {"folder": "Instagram/Travel/Spain",       "type": "travel",    "sheet": True},
    "Iceland":   {"folder": "Instagram/Travel/Iceland",     "type": "travel",    "sheet": True},
    "Cocktail":  {"folder": "Instagram/Food-Drink",         "type": "food_drink", "sheet": False},
    "Recipes":   {"folder": "Instagram/Food-Drink",         "type": "food_drink", "sheet": False},
    "Baby item": None,
    "Baby Item": None,
}

WEB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "X-IG-App-ID": "936619743392459",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.instagram.com/",
}


# ── State ────────────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"processed_posts": [], "failed_posts": [], "travel_rows": []}

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def is_processed(state: dict, url: str) -> bool:
    return url in state["processed_posts"] or url in state.get("failed_posts", [])

def mark_processed(state: dict, url: str):
    if url not in state["processed_posts"]:
        state["processed_posts"].append(url)
    save_state(state)

def mark_failed(state: dict, url: str):
    state.setdefault("failed_posts", [])
    if url not in state["failed_posts"]:
        state["failed_posts"].append(url)
    save_state(state)


# ── Session ──────────────────────────────────────────────────────────────────────

def load_session() -> tuple[dict, dict]:
    data = json.loads(SESSION_FILE.read_text())
    cookies_list = data["cookies"]
    cookies_dict = {c["name"]: c["value"] for c in cookies_list}
    return cookies_dict, cookies_list

def save_session(ctx: BrowserContext):
    cookies = ctx.cookies("https://www.instagram.com")
    SESSION_FILE.write_text(json.dumps({"cookies": cookies, "saved_at": TODAY}, indent=2))
    print(f"Session saved ({len(cookies)} cookies)")


# ── Instagram API ────────────────────────────────────────────────────────────────

def shortcode_to_id(code: str) -> int:
    n = 0
    for c in code:
        n = n * 64 + IG_SHORTCODE_CHARS.index(c)
    return n

def get_post_data(shortcode: str, cookies: dict) -> Optional[dict]:
    numeric_id = shortcode_to_id(shortcode)
    try:
        resp = requests.get(
            f"https://www.instagram.com/api/v1/media/{numeric_id}/info/",
            cookies=cookies, headers=WEB_HEADERS, timeout=15
        )
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            return items[0] if items else None
    except Exception as e:
        print(f"      API error: {e}")
    return None

def extract_from_api(item: dict) -> dict:
    user = item.get("user", {})
    username = user.get("username", "unknown")
    cap_obj = item.get("caption") or {}
    caption = cap_obj.get("text", "") if isinstance(cap_obj, dict) else ""
    location = (item.get("location") or {}).get("name", "")
    media_type = item.get("media_type", 1)
    shortcode = item.get("code", "")
    url = f"https://www.instagram.com/p/{shortcode}/"

    image_urls = []
    if media_type == 8:
        for media in item.get("carousel_media", [])[:5]:
            candidates = media.get("image_versions2", {}).get("candidates", [])
            if candidates:
                image_urls.append(candidates[0]["url"])
    else:
        candidates = item.get("image_versions2", {}).get("candidates", [])
        if candidates:
            image_urls.append(candidates[0]["url"])

    video_url = ""
    if media_type == 2:
        versions = item.get("video_versions", [])
        if versions:
            sorted_v = sorted(versions, key=lambda v: v.get("width", 9999))
            video_url = sorted_v[0]["url"]

    return {
        "username": f"@{username}",
        "caption": caption,
        "location": location,
        "media_type": media_type,
        "shortcode": shortcode,
        "url": url,
        "image_urls": image_urls,
        "video_url": video_url,
        "hashtags": re.findall(r"#(\w+)", caption)[:10],
    }


# ── Image download ────────────────────────────────────────────────────────────────

def get_media_dir() -> Path:
    d = OBSIDIAN_BASE / MEDIA_FOLDER
    d.mkdir(parents=True, exist_ok=True)
    return d

def download_images(image_urls: list[str], slug: str) -> list[str]:
    media_dir = get_media_dir()
    saved = []
    for i, url in enumerate(image_urls[:5], 1):
        suffix = "jpg" if "jpg" in url.lower() else "webp"
        fname = f"{TODAY}-{slug}-img{i}.{suffix}"
        fpath = media_dir / fname
        if fpath.exists():
            saved.append(fname); continue
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": WEB_HEADERS["User-Agent"],
                "Referer": "https://www.instagram.com/",
            })
            with urllib.request.urlopen(req, timeout=15) as r:
                fpath.write_bytes(r.read())
            saved.append(fname)
        except Exception as e:
            print(f"      Image download failed: {e}")
    return saved


# ── Video processing ──────────────────────────────────────────────────────────────

def get_whisper() -> WhisperModel:
    global _whisper_model
    if _whisper_model is None:
        print(f"  [Whisper] Loading '{WHISPER_MODEL_SIZE}' model...")
        _whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
        print("  [Whisper] Model ready.")
    return _whisper_model

def download_video(video_url: str, slug: str) -> Optional[Path]:
    tmp = Path(tempfile.mktemp(suffix=".mp4", prefix=f"ig-{slug[:20]}-"))
    try:
        print(f"      Downloading video...", end=" ", flush=True)
        result = subprocess.run(
            ["curl", "-sS", "--max-time", "60",
             "-H", f"User-Agent: {WEB_HEADERS['User-Agent']}",
             "-H", "Referer: https://www.instagram.com/",
             "-o", str(tmp), video_url],
            timeout=75, capture_output=True,
        )
        if result.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
            raise RuntimeError(result.stderr.decode()[:120])
        mb = tmp.stat().st_size / 1024 / 1024
        print(f"{mb:.1f} MB")
        return tmp
    except Exception as e:
        print(f"FAILED: {e}")
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return None

def extract_frames(video_path: Path, slug: str, count: int = VIDEO_FRAMES) -> list[str]:
    media_dir = get_media_dir()
    fnames = []
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=10
        )
        duration = float(r.stdout.strip() or "30")
        interval = max(duration / (count + 1), 0.5)
        for i in range(1, count + 1):
            t = round(interval * i, 2)
            fname = f"{TODAY}-{slug}-frame{i}.jpg"
            fpath = media_dir / fname
            subprocess.run(
                ["ffmpeg", "-ss", str(t), "-i", str(video_path),
                 "-vframes", "1", "-q:v", "3", "-y", str(fpath)],
                capture_output=True, timeout=20
            )
            if fpath.exists() and fpath.stat().st_size > 1024:
                fnames.append(fname)
    except Exception as e:
        print(f"      Frame extraction failed: {e}")
    print(f"      {len(fnames)} frame(s) extracted")
    return fnames

def transcribe_video(video_path: Path) -> str:
    import multiprocessing as mp

    MAX_SIZE_MB = 8       # skip transcription for large videos
    TRANSCRIBE_TIMEOUT = 120  # 2-minute hard kill via separate process

    file_size_mb = video_path.stat().st_size / (1024 * 1024)
    if file_size_mb > MAX_SIZE_MB:
        print(f"SKIPPED (video too large: {file_size_mb:.1f}MB)")
        return ""

    def _worker(path_str: str, q: mp.Queue):
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
            segments, info = model.transcribe(
                path_str, beam_size=5, language=None,
                vad_filter=True, vad_parameters={"min_silence_duration_ms": 500},
            )
            texts = [s.text.strip() for s in segments]
            q.put(("ok", " ".join(t for t in texts if t), info.language,
                   getattr(info, "language_probability", 0)))
        except Exception as e:
            q.put(("err", str(e), "", 0))

    print(f"      Transcribing audio ({file_size_mb:.1f}MB)...", end=" ", flush=True)
    ctx = mp.get_context("fork")
    q: mp.Queue = ctx.Queue()
    proc = ctx.Process(target=_worker, args=(str(video_path), q), daemon=True)
    proc.start()
    proc.join(timeout=TRANSCRIBE_TIMEOUT)

    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()
        print(f"TIMEOUT after {TRANSCRIBE_TIMEOUT}s — skipping transcript")
        return ""

    try:
        status, text, lang, conf = q.get_nowait()
        if status == "ok":
            print(f"[{lang} {conf:.0%}] {len(text)} chars")
            return text
        print(f"FAILED: {text}")
        return ""
    except Exception as e:
        print(f"FAILED: {e}")
        return ""

def process_video(video_url: str, slug: str) -> tuple[list[str], str]:
    video_path = download_video(video_url, slug)
    if not video_path:
        return [], ""
    try:
        frames = extract_frames(video_path, slug)
        transcript = transcribe_video(video_path)
        return frames, transcript
    finally:
        try:
            video_path.unlink()
        except Exception:
            pass


# ── Claude Vision Analysis ────────────────────────────────────────────────────────

def get_claude_client() -> anthropic.Anthropic:
    global _claude_client
    if _claude_client is None:
        _claude_client = anthropic.Anthropic()
    return _claude_client

def _fnames_to_image_parts(fnames: list[str]) -> list[dict]:
    """Read frame/image files from _media/ and encode as base64 for Claude."""
    media_dir = get_media_dir()
    parts = []
    for fname in fnames[:5]:
        fpath = media_dir / fname
        if not fpath.exists():
            continue
        try:
            data = base64.standard_b64encode(fpath.read_bytes()).decode("utf-8")
            parts.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": data}
            })
        except Exception:
            pass
    return parts

def _extract_json(text: str) -> dict:
    """
    Extract JSON from Claude response, handling code blocks and arrays.
    If Claude returns a list of items (multi-item post), merge them into
    a single consolidated dict.
    """
    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    text = text.strip()

    # Try array first (e.g. list posts like "brands to know")
    if text.startswith("["):
        items = json.loads(text)
        if items and isinstance(items[0], dict):
            return _merge_list_items(items)
        return {}

    # Try direct object
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in response")
    # Find matching closing brace
    depth, end = 0, -1
    for i, ch in enumerate(text[start:], start):
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        raise ValueError("Unclosed JSON object")

    parsed = json.loads(text[start:end])

    # Handle wrapped arrays: {"travel_items": [...], "items": [...], etc.}
    for key in ("travel_items", "items", "places", "results", "recommendations"):
        if key in parsed and isinstance(parsed[key], list) and parsed[key]:
            return _merge_list_items(parsed[key])

    return parsed

def _merge_list_items(items: list) -> dict:
    """
    Consolidate a list of place dicts (from a multi-item post) into one.
    Uses the first item as the base and appends others into highlights.
    """
    if not items:
        return {}
    base = dict(items[0])
    if len(items) > 1:
        # Collect all place names as highlights for multi-item posts
        all_names = [it.get("place_name", "") for it in items if it.get("place_name")]
        why_parts = [it.get("why_recommended", "") for it in items if it.get("why_recommended")]
        base["place_name"] = items[0].get("place_name", "Multiple recommendations")
        base["why_recommended"] = " | ".join(why_parts[:3]) if why_parts else base.get("why_recommended", "")
        existing_highlights = base.get("highlights") or []
        base["highlights"] = (existing_highlights + all_names[1:])[:8]
        base["_is_list_post"] = True
    return base

def _is_vague_address(address: str) -> bool:
    """Return True if the address is null, empty, or too generic to be useful."""
    if not address or address.lower() in ("null", "none", "n/a", "not listed", "not available"):
        return True
    # Vague if it's just a city/country name (no street number or district detail)
    stripped = address.strip()
    if len(stripped) < 8:
        return True
    # Contains a number or comma (likely a real address or district) → keep it
    if re.search(r'\d', stripped) or "," in stripped or "-" in stripped:
        return False
    # Very short single word / just a city name
    if len(stripped.split()) <= 2:
        return True
    return False

def _web_search_address(place_name: str, city: str, country: str) -> str:
    """
    DuckDuckGo search for the address of a named place.
    Returns the best address string found, or "" if nothing useful.
    """
    if not place_name or not os.environ.get("ANTHROPIC_API_KEY"):
        return ""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        location_ctx = f"{city}, {country}" if country else city
        # Try two queries: exact name + location, then broader
        queries = [
            f'"{place_name}" {location_ctx} address',
            f'{place_name} {location_ctx} restaurant cafe hotel address',
        ]
        snippets = []
        with DDGS() as ddgs:
            for q in queries:
                results = list(ddgs.text(q, max_results=5))
                for r in results:
                    snippets.append(f"[{r.get('title','')}] {r.get('body','')}")
                if len(snippets) >= 8:
                    break

        if not snippets:
            return ""

        combined = "\n".join(snippets[:8])
        client = get_claude_client()
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=120,
            messages=[{"role": "user", "content": f"""These are web search results for "{place_name}" in {location_ctx}.

{combined}

Extract the most specific street address or precise location (neighborhood + street, district, etc.).
Return ONLY the address string. If no specific address is found, return "null"."""}]
        )
        found = resp.content[0].text.strip()
        if found.lower() in ("null", "none", "not found", ""):
            return ""
        # Sanity check — must look like a real address (has a number or comma or district marker)
        if len(found) > 5:
            return found
        return ""

    except Exception as e:
        print(f" [search err: {e}]", end="", flush=True)
        return ""

def analyze_travel_post(caption: str, location: str, transcript: str,
                        frame_fnames: list[str], img_fnames: list[str],
                        collection_city: str) -> list[dict]:
    """
    Send frames + transcript to Claude to extract ALL places in this post.
    A single post may recommend 1–10+ places. Returns a list of place dicts.
    Runs web address search for any vague addresses.
    """
    try:
        client = get_claude_client()
        content = []

        visual_fnames = frame_fnames if frame_fnames else img_fnames
        content.extend(_fnames_to_image_parts(visual_fnames))

        prompt = f"""Analyze this Instagram travel post. Extract EVERY place it recommends — there may be 1 place or 10+.

Instagram Collection (city hint): {collection_city}
Caption (may be in any language): {caption[:1200]}
Instagram location tag: {location or "none"}
Audio transcript (what the creator says): {transcript[:1500] if transcript else "none"}

HOW TO FIND PLACE NAMES:
1. Watch the video frames in sequence — read any visible SIGNAGE, storefront signs, logos, neon signs, menu boards, text overlays
2. Listen to the transcript — the creator will usually say the place name out loud
3. Read the caption — names are often mentioned explicitly
Use the name as it appears in signage or as spoken. Do NOT invent names.

Return a JSON ARRAY — one object per place. Even if there is only one place, return a single-element array.

[
  {{
    "place_name": "exact name from signage or as spoken/written in caption",
    "type": "restaurant|cafe|hotel|bar|izakaya|ramen|sushi|omakase|shop|market|activity|area|temple|onsen|park|attraction|other",
    "city": "actual city name",
    "country": "country",
    "address": "street address, district, or neighborhood — null if unknown",
    "why_recommended": "1-2 sentences in English explaining what makes this place special",
    "highlights": ["specific dish", "key feature", "price point", "must-order item"],
    "price_range": "$|$$|$$$|$$$$|null",
    "cuisine": "cuisine type or null",
    "hours": "opening hours or null",
    "reservation_needed": true|false|null
  }}
]

Also append at the end of your response — AFTER the JSON array — these two lines:
CAPTION_EN: <English translation/summary of the full caption — 3 sentences max>
TRANSCRIPT_EN: <English translation of the audio transcript — null if none>

Return the JSON array first, then the two labeled lines. No other text."""

        content.append({"type": "text", "text": prompt})

        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2500,
            messages=[{"role": "user", "content": content}]
        )
        raw = resp.content[0].text

        # Extract caption_en / transcript_en from labeled lines appended after JSON
        caption_en = ""
        transcript_en = ""
        for line in raw.splitlines():
            if line.startswith("CAPTION_EN:"):
                caption_en = line[len("CAPTION_EN:"):].strip()
            elif line.startswith("TRANSCRIPT_EN:"):
                transcript_en = line[len("TRANSCRIPT_EN:"):].strip()
                if transcript_en.lower() == "null":
                    transcript_en = ""

        # Parse the JSON array
        parsed = _extract_json(raw)
        # _extract_json returns a dict for single objects — wrap in list
        if isinstance(parsed, dict):
            places = [parsed]
        elif isinstance(parsed, list):
            places = parsed
        else:
            places = []

        if not places:
            raise ValueError("No places extracted")

        # Inject shared translation fields + run address search per place
        for place in places:
            place.setdefault("caption_en", caption_en)
            place.setdefault("transcript_en", transcript_en)
            if _is_vague_address(place.get("address")):
                city_r = place.get("city") or collection_city
                country_r = place.get("country") or ""
                print(f"\n        🔍 address search: {place.get('place_name','?')[:30]}...", end="", flush=True)
                found = _web_search_address(place.get("place_name",""), city_r, country_r)
                if found:
                    place["address"] = found
                    print(f" ✓ ({found[:45]})", end="", flush=True)

        names = ", ".join(p.get("place_name","?")[:25] for p in places)
        print(f"✓ {len(places)} place(s): {names[:80]}")
        return places

    except Exception as e:
        print(f"failed ({e})")
        return []
        return {}

def analyze_ai_post(caption: str, transcript: str,
                    frame_fnames: list[str], img_fnames: list[str],
                    post_type: str) -> dict:
    """
    Analyze an AI skill or AI prompt post using frames + transcript.
    post_type: "ai_skill" or "ai_prompt"
    """
    try:
        client = get_claude_client()
        content = []

        visual_fnames = frame_fnames if frame_fnames else img_fnames
        content.extend(_fnames_to_image_parts(visual_fnames))

        if post_type == "ai_prompt":
            prompt = f"""Analyze this Instagram post about an AI prompt or technique.

Audio transcript (what the creator says): {transcript[:2000] if transcript else "none"}
Caption: {caption[:1000]}

Read ALL frames carefully. The frames often contain:
- The actual prompt text written out
- Before/after examples of the prompt in action
- Step-by-step instructions for using it
- Tool or model being used (ChatGPT, Claude, Midjourney, etc.)

Extract everything into this JSON:
{{
  "title": "concise name for this prompt/technique (5 words max)",
  "the_prompt": "the actual prompt text verbatim if visible in frames or transcript — null if not found",
  "what_it_does": "1-2 sentences: what this prompt does and what output it produces",
  "when_to_use": "specific situations or tasks where this prompt is useful",
  "tool": "ChatGPT|Claude|Midjourney|Perplexity|general|other — which AI tool this is for",
  "example_output": "describe the example output shown in the video/frames if any",
  "tags": ["tag1", "tag2", "tag3"],
  "summary_en": "English summary of the full post content (3-4 sentences)"
}}"""
        else:  # ai_skill
            prompt = f"""Analyze this Instagram post about an AI skill, workflow, tool, or technique.

Audio transcript (what the creator says): {transcript[:2000] if transcript else "none"}
Caption: {caption[:1000]}

Read ALL frames carefully — they often show the actual workflow, tool interface, or results.

Extract into this JSON:
{{
  "title": "concise technique/tool name (5 words max)",
  "description": "2-3 sentences: what this technique/tool is and what it does",
  "use_case": "specific real-world problem this solves or task it helps with",
  "how_it_works": "step-by-step explanation of how to use or implement this",
  "tools_mentioned": ["tool1", "tool2"],
  "key_insight": "the single most valuable takeaway from this post",
  "tags": ["tag1", "tag2", "tag3"],
  "summary_en": "English summary of the full post (3-4 sentences)"
}}"""

        content.append({"type": "text", "text": prompt})

        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1200,
            messages=[{"role": "user", "content": content}]
        )
        result = _extract_json(resp.content[0].text)
        title = result.get("title", "?")
        print(f"✓ ({title[:40]})")
        return result
    except Exception as e:
        print(f"failed ({e})")
        return {}


def analyze_recipe_post(caption: str, transcript: str,
                        frame_fnames: list[str], img_fnames: list[str],
                        collection_name: str) -> dict:
    """
    Send frames + transcript to Claude. Extract full recipe:
    name, ingredients with quantities, step-by-step instructions.
    """
    try:
        client = get_claude_client()
        content = []

        visual_fnames = frame_fnames if frame_fnames else img_fnames
        content.extend(_fnames_to_image_parts(visual_fnames))

        ctype = "cocktail" if "cocktail" in collection_name.lower() else "recipe"

        prompt = f"""You are a culinary expert reconstructing a complete, cookable {ctype} from an Instagram video.

You have TWO sources of information — use BOTH together:

1. VIDEO FRAMES (attached images): Show the physical cooking actions, ingredients, equipment, and final result.
   - Look for: ingredient packages/labels with quantities, measuring cups/spoons, text overlays, step-by-step visuals
   - Each frame is a moment in the cooking process — read them in sequence

2. AUDIO TRANSCRIPT (what the creator said aloud):
{transcript[:2000] if transcript else "   [No audio transcript — rely on frames only]"}

3. CAPTION:
{caption[:600]}

Cross-reference both sources to extract the most complete recipe possible:
- Transcript often contains exact quantities, temperatures, and timing the frames don't show
- Frames show technique and visual cues the transcript may skip
- If the transcript says "add 2 tbsp soy sauce" and the frame shows soy sauce being poured → use "2 tbsp soy sauce"
- If transcript is in another language, translate quantities and instructions to English

Return a SINGLE JSON object — translate everything to English:
{{
  "name": "dish or drink name",
  "cuisine": "cuisine type or cocktail style",
  "servings": "e.g. '2 servings' or null",
  "prep_time": "e.g. '10 minutes' or null",
  "cook_time": "e.g. '20 minutes' or null",
  "ingredients": [
    "exact quantity + ingredient name, e.g. '2 tbsp soy sauce'",
    "1 tsp sesame oil",
    "200g spaghetti"
  ],
  "steps": [
    "Step 1: Specific action — include temperatures, timing, technique from transcript + what frames show",
    "Step 2: ...",
    "Step 3: ..."
  ],
  "tips": ["specific tip visible or mentioned"],
  "equipment": ["specific equipment shown or mentioned"],
  "difficulty": "easy|medium|hard",
  "caption_en": "English translation of the caption. Copy as-is if already English.",
  "transcript_en": "Full English translation of the transcript. null if none or unusable."
}}

If the video is a teaser without full instructions, extract whatever steps ARE visible and note what's missing in tips.
Return ONLY the JSON object."""

        content.append({"type": "text", "text": prompt})

        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1800,
            messages=[{"role": "user", "content": content}]
        )
        result = _extract_json(resp.content[0].text)
        print(f"✓ ({result.get('name', '?')[:40]})")
        return result
    except Exception as e:
        print(f"failed ({e})")
        return {}


# ── Obsidian helpers ──────────────────────────────────────────────────────────────

def slugify(text: str, max_words: int = 4) -> str:
    words = re.sub(r"[^\w\s]", "", text.lower()).split()[:max_words]
    return "-".join(words) if words else "untitled"

def _write_obsidian(folder: str, filename: str, content: str):
    dest = OBSIDIAN_BASE / folder
    dest.mkdir(parents=True, exist_ok=True)
    fp = dest / filename
    if fp.exists():
        fp = dest / f"{fp.stem}-{int(time.time())}.md"
    fp.write_text(content, encoding="utf-8")
    print(f"      Saved → {folder}/{fp.name}")

def _overwrite_obsidian(filepath: Path, content: str):
    """Overwrite an existing note in place (used by enrich mode)."""
    filepath.write_text(content, encoding="utf-8")

def image_embeds(fnames: list[str]) -> str:
    return "\n".join(f"![[{f}]]" for f in fnames)

def video_section(frame_fnames: list[str], transcript: str) -> str:
    if not frame_fnames and not transcript:
        return ""
    parts = []
    if frame_fnames:
        parts.append("## Video Frames\n\n" + image_embeds(frame_fnames))
    if transcript:
        parts.append(f"## Video Transcript\n\n{transcript}")
    return "\n\n".join(parts)


# ── Note builders ─────────────────────────────────────────────────────────────────

def save_ai_skill(d: dict, img_fnames: list[str], folder: str,
                  frame_fnames: list[str] = None, transcript: str = ""):
    print("      Claude analysis...", end=" ", flush=True)
    analysis = analyze_ai_post(
        d["caption"], transcript, frame_fnames or [], img_fnames, "ai_skill"
    )

    title       = analysis.get("title") or (d["caption"].split("\n")[0][:80] if d["caption"] else "AI Skill")
    description = analysis.get("description") or analysis.get("summary_en") or d["caption"][:400]
    use_case    = analysis.get("use_case") or ""
    how_it      = analysis.get("how_it_works") or ""
    insight     = analysis.get("key_insight") or ""
    tools       = analysis.get("tools_mentioned") or []
    tags_extra  = analysis.get("tags") or d["hashtags"][:4]
    summary     = analysis.get("summary_en") or ""

    tags_yaml = "\n".join(f"  - {t}" for t in (["ai-skills"] + tags_extra[:4]))
    is_video = d["media_type"] == 2
    video_tag = "\n  - video" if is_video else ""
    media_type_str = "video" if is_video else "image"
    slug = slugify(title)

    use_case_md  = f"\n## Use Case\n\n{use_case}" if use_case else ""
    how_it_md    = f"\n## How It Works\n\n{how_it}" if how_it else ""
    insight_md   = f"\n## Key Insight\n\n{insight}" if insight else ""
    tools_md     = f"\n**Tools:** {', '.join(tools)}" if tools else ""
    vid_block    = video_section(frame_fnames or [], transcript)

    _write_obsidian(folder, f"{TODAY}-{slug}.md", f"""---
tags:
  - instagram
  - ai-skills
{tags_yaml}{video_tag}
date: {TODAY}
stream: AI
source: "{d['username']}"
instagram_url: "{d['url']}"
media_type: {media_type_str}
---

# {title}

**Source:** {d['username']}{tools_md}

## Description

{description}
{use_case_md}
{how_it_md}
{insight_md}

## Images / Cover

{image_embeds(img_fnames) or '_No images_'}

{vid_block}

## Caption

{summary or d['caption']}
""")


def save_ai_prompt(d: dict, img_fnames: list[str], folder: str,
                   frame_fnames: list[str] = None, transcript: str = ""):
    print("      Claude analysis...", end=" ", flush=True)
    analysis = analyze_ai_post(
        d["caption"], transcript, frame_fnames or [], img_fnames, "ai_prompt"
    )

    title        = analysis.get("title") or (d["caption"].split("\n")[0][:60] if d["caption"] else "AI Prompt")
    the_prompt   = analysis.get("the_prompt") or ""
    what_it_does = analysis.get("what_it_does") or ""
    when_to_use  = analysis.get("when_to_use") or ""
    tool         = analysis.get("tool") or ""
    example_out  = analysis.get("example_output") or ""
    summary      = analysis.get("summary_en") or ""
    tags_extra   = analysis.get("tags") or d["hashtags"][:4]

    tags_yaml = "\n".join(f"  - {t}" for t in (["ai-prompts"] + tags_extra[:4]))
    is_video = d["media_type"] == 2
    video_tag = "\n  - video" if is_video else ""
    media_type_str = "video" if is_video else "image"
    slug = slugify(title)

    prompt_md    = f"\n## The Prompt\n\n```\n{the_prompt}\n```" if the_prompt else ""
    does_md      = f"\n## What It Does\n\n{what_it_does}" if what_it_does else ""
    when_md      = f"\n## When To Use\n\n{when_to_use}" if when_to_use else ""
    example_md   = f"\n## Example Output\n\n{example_out}" if example_out else ""
    tool_md      = f"\n**Tool:** {tool}" if tool else ""
    vid_block    = video_section(frame_fnames or [], transcript)

    _write_obsidian(folder, f"{TODAY}-{slug}.md", f"""---
tags:
  - instagram
  - ai-prompts
{tags_yaml}{video_tag}
date: {TODAY}
stream: AI
source: "{d['username']}"
instagram_url: "{d['url']}"
media_type: {media_type_str}
---

# {title}

**Source:** {d['username']}{tool_md}
{prompt_md}
{does_md}
{when_md}
{example_md}

## Images / Cover

{image_embeds(img_fnames) or '_No images_'}

{vid_block}

## Caption

{summary or d['caption']}
""")

def _build_travel_note(d: dict, city: str, img_fnames: list[str],
                       frame_fnames: list[str], transcript: str,
                       analysis: dict) -> tuple[str, str, dict]:
    """
    Build travel note content using Claude analysis.
    Returns (note_content, slug, travel_row_dict).
    """
    # Use Claude data with fallbacks
    place_name = (analysis.get("place_name") or d["location"] or
                  (d["caption"].split("\n")[0][:80] if d["caption"] else city))
    actual_city = analysis.get("city") or city
    country = analysis.get("country") or ""
    city_country = f"{actual_city}, {country}" if country else actual_city
    address = analysis.get("address") or d["location"] or "Not listed"
    why = analysis.get("why_recommended") or (
        " ".join(d["caption"].split("\n")[:2])[:400] if d["caption"] else "See caption"
    )
    highlights = analysis.get("highlights", [])
    place_type = analysis.get("type", "restaurant")
    price_range = analysis.get("price_range") or ""
    cuisine = analysis.get("cuisine") or ""
    hours = analysis.get("hours") or ""
    reservation = analysis.get("reservation_needed")

    # Build highlights block
    highlights_md = "\n".join(f"- {h}" for h in highlights) if highlights else ""

    # Build extra info block
    extra_lines = []
    if cuisine:
        extra_lines.append(f"**Cuisine:** {cuisine}")
    if price_range:
        extra_lines.append(f"**Price Range:** {price_range}")
    if hours:
        extra_lines.append(f"**Hours:** {hours}")
    if reservation is not None:
        extra_lines.append(f"**Reservation needed:** {'Yes' if reservation else 'No'}")
    extra_md = "\n".join(extra_lines)

    # Translated content from Claude (fall back to raw if not available)
    caption_en    = analysis.get("caption_en") or d["caption"]
    transcript_en = analysis.get("transcript_en") or transcript

    city_tag = city.lower().replace(" ", "-")
    is_video = d["media_type"] == 2
    video_tag = "\n  - video" if is_video else ""
    media_type_str = "video" if is_video else "image"
    slug = slugify(place_name)
    highlights_section = ("## Highlights\n\n" + highlights_md) if highlights_md else ""

    # Build video block with translated transcript
    vid_parts = []
    if frame_fnames:
        vid_parts.append("## Video Frames\n\n" + image_embeds(frame_fnames))
    if transcript_en:
        vid_parts.append(f"## Video Transcript\n\n{transcript_en}")
    vid_block = "\n\n".join(vid_parts)

    note = f"""---
tags:
  - instagram
  - travel
  - {city_tag}{video_tag}
date: {TODAY}
stream: Personal
source: "{d['username']}"
collection: "{city}"
city: "{city_country}"
type: "{place_type}"
instagram_url: "{d['url']}"
media_type: {media_type_str}
---

# {place_name}

**City:** {city_country}
**Type:** {place_type}
**Address:** {address}
**Source:** {d['username']}
{extra_md}

## Why Recommended

{why}

{highlights_section}

## Images / Cover

{image_embeds(img_fnames) or '_No images_'}

{vid_block}

## Caption

{caption_en}
"""

    travel_row = {
        "Place Name": place_name,
        "Collection": city,
        "City": city_country,
        "Type": place_type,
        "Address": address,
        "Cuisine": cuisine,
        "Price Range": price_range,
        "Why Recommended": why,
        "Highlights": " | ".join(highlights),
        "Instagram Source": d["username"],
        "Instagram URL": d["url"],
        "Date Added": TODAY,
    }

    return note, slug, travel_row

def save_travel(d: dict, city: str, img_fnames: list[str], folder: str,
                frame_fnames: list[str] = None, transcript: str = "") -> list[dict]:
    """
    Save travel note(s) with Claude vision analysis.
    One post may yield multiple places → one note per place.
    Returns list of travel_row dicts.
    """
    print("      Claude analysis...", end=" ", flush=True)
    places = analyze_travel_post(
        d["caption"], d["location"], transcript,
        frame_fnames or [], img_fnames, city
    )

    if not places:
        # Fallback: save a bare note from caption only
        note, slug, travel_row = _build_travel_note(d, city, img_fnames, frame_fnames or [], transcript, {})
        _write_obsidian(folder, f"{TODAY}-{slug}.md", note)
        return [travel_row]

    rows = []
    seen_slugs: set[str] = set()
    for place in places:
        note, slug, travel_row = _build_travel_note(
            d, city, img_fnames, frame_fnames or [], transcript, place
        )
        # Deduplicate slugs within the same post (e.g. 5 bars → bar1, bar2…)
        base_slug = slug
        counter = 2
        while slug in seen_slugs:
            slug = f"{base_slug}-{counter}"
            counter += 1
        seen_slugs.add(slug)
        _write_obsidian(folder, f"{TODAY}-{slug}.md", note)
        rows.append(travel_row)

    return rows

def _build_recipe_note(d: dict, collection_name: str, img_fnames: list[str],
                       frame_fnames: list[str], transcript: str,
                       analysis: dict) -> tuple[str, str]:
    """Build recipe/cocktail note content. Returns (note_content, slug)."""
    lines = [l for l in d["caption"].split("\n") if l.strip()]
    ctype = "cocktail" if "cocktail" in collection_name.lower() else "recipe"

    name = analysis.get("name") or (lines[0][:80] if lines else "Unknown")
    cuisine = analysis.get("cuisine") or ""
    servings = analysis.get("servings") or ""
    prep_time = analysis.get("prep_time") or ""
    cook_time = analysis.get("cook_time") or ""
    difficulty = analysis.get("difficulty") or ""
    equipment = analysis.get("equipment") or []
    tips = analysis.get("tips") or []

    # Ingredients
    ingredients = analysis.get("ingredients", [])
    if ingredients:
        ingredients_md = "\n".join(f"- {ing}" for ing in ingredients)
    else:
        # Fallback: lines 3-10 of caption
        ingredients_md = "\n".join(f"- {l}" for l in lines[3:10]) if len(lines) > 3 else "_See full caption below_"

    # Steps
    steps = analysis.get("steps", [])
    if steps:
        steps_md = "\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1))
    else:
        steps_md = "_See video frames and transcript below_"

    # Tips
    tips_md = "\n".join(f"- {t}" for t in tips) if tips else ""

    # Meta info block
    meta_lines = []
    if cuisine:
        meta_lines.append(f"**Cuisine:** {cuisine}")
    if servings:
        meta_lines.append(f"**Servings:** {servings}")
    if prep_time:
        meta_lines.append(f"**Prep Time:** {prep_time}")
    if cook_time:
        meta_lines.append(f"**Cook Time:** {cook_time}")
    if difficulty:
        meta_lines.append(f"**Difficulty:** {difficulty}")
    if equipment:
        meta_lines.append(f"**Equipment:** {', '.join(equipment)}")
    meta_md = "\n".join(meta_lines)

    # Translated content from Claude
    caption_en    = analysis.get("caption_en") or d["caption"]
    transcript_en = analysis.get("transcript_en") or transcript

    is_video = d["media_type"] == 2
    video_tag = "\n  - video" if is_video else ""
    media_type_str = "video" if is_video else "image"
    slug = slugify(name)
    tips_section = ("## Tips\n\n" + tips_md) if tips_md else ""

    # Build video block with translated transcript
    vid_parts = []
    if frame_fnames:
        vid_parts.append("## Video Frames\n\n" + image_embeds(frame_fnames))
    if transcript_en:
        vid_parts.append(f"## Video Transcript (English)\n\n{transcript_en}")
    vid_block = "\n\n".join(vid_parts)

    note = f"""---
tags:
  - instagram
  - food-drink
  - {ctype}{video_tag}
date: {TODAY}
stream: Personal
source: "{d['username']}"
instagram_url: "{d['url']}"
media_type: {media_type_str}
---

# {name}

**Type:** {ctype}
**Source:** {d['username']}
{meta_md}

## Ingredients

{ingredients_md}

## Steps

{steps_md}

{tips_section}

## Images / Cover

{image_embeds(img_fnames) or '_No images_'}

{vid_block}

## Caption

{caption_en}
"""
    return note, slug

def save_food_drink(d: dict, collection_name: str, img_fnames: list[str], folder: str,
                    frame_fnames: list[str] = None, transcript: str = ""):
    """Save recipe/cocktail note with Claude vision analysis."""
    print("      Claude analysis...", end=" ", flush=True)
    analysis = analyze_recipe_post(
        d["caption"], transcript,
        frame_fnames or [], img_fnames, collection_name
    )
    note, slug = _build_recipe_note(
        d, collection_name, img_fnames, frame_fnames or [], transcript, analysis
    )
    _write_obsidian(folder, f"{TODAY}-{slug}.md", note)


# ── Post processing ───────────────────────────────────────────────────────────────

def shortcode_from_url(url: str) -> str:
    m = re.search(r"/(p|reel)/([A-Za-z0-9_-]+)/", url)
    return m.group(2) if m else ""

def process_post(url: str, collection_name: str, config: dict,
                 state: dict, cookies: dict) -> bool:
    try:
        shortcode = shortcode_from_url(url)
        if not shortcode:
            print(f"      Could not extract shortcode from {url}")
            mark_failed(state, url); return False

        item = get_post_data(shortcode, cookies)
        if not item:
            print(f"      API returned no data for {shortcode}")
            mark_failed(state, url); return False

        d = extract_from_api(item)
        ctype = config["type"]
        folder = config["folder"]
        (OBSIDIAN_BASE / folder).mkdir(parents=True, exist_ok=True)

        is_video = d["media_type"] == 2
        media_label = "VIDEO" if is_video else "photo"
        cap_preview = d["caption"][:60].replace("\n", " ") if d["caption"] else "(no caption)"
        print(f"      [{media_label}] {d['username']} | {cap_preview}")

        slug = slugify(d["caption"].split("\n")[0][:40] if d["caption"] else shortcode)

        img_fnames = download_images(d["image_urls"], slug)
        print(f"      {len(img_fnames)} cover image(s) downloaded")

        frame_fnames, transcript = [], ""
        if is_video and d["video_url"]:
            frame_fnames, transcript = process_video(d["video_url"], slug)

        if ctype == "ai_skill":
            save_ai_skill(d, img_fnames, folder, frame_fnames, transcript)
        elif ctype == "ai_prompt":
            save_ai_prompt(d, img_fnames, folder, frame_fnames, transcript)
        elif ctype == "travel":
            rows = save_travel(d, collection_name, img_fnames, folder, frame_fnames, transcript)
            if config["sheet"]:
                for row in rows:
                    state.setdefault("travel_rows", []).append(row)
        elif ctype == "food_drink":
            save_food_drink(d, collection_name, img_fnames, folder, frame_fnames, transcript)

        mark_processed(state, url)
        return True

    except Exception as e:
        print(f"      ERROR: {e}")
        traceback.print_exc()
        mark_failed(state, url)
        return False


# ── Collection navigation ─────────────────────────────────────────────────────────

def normalize_url(href: str) -> str:
    url = f"https://www.instagram.com{href}" if href.startswith("/") else href
    return url.split("?")[0].rstrip("/") + "/"

def find_collection_links(page: Page) -> dict:
    known = {
        "AI":        f"https://www.instagram.com/{INSTAGRAM_USER}/saved/ai/18586387528049071/",
        "AI prompt": f"https://www.instagram.com/{INSTAGRAM_USER}/saved/ai-prompt/17884965672396366/",
        "Taiwan":    f"https://www.instagram.com/{INSTAGRAM_USER}/saved/taiwan/17993409370769103/",
        "Japan":     f"https://www.instagram.com/{INSTAGRAM_USER}/saved/japan/17962527776584391/",
        "Seattle":   f"https://www.instagram.com/{INSTAGRAM_USER}/saved/seattle/17990372764957738/",
        "Recipes":   f"https://www.instagram.com/{INSTAGRAM_USER}/saved/recipes/18049490191723514/",
        "LA":        f"https://www.instagram.com/{INSTAGRAM_USER}/saved/la/17906050457774211/",
        "Vancuver":  f"https://www.instagram.com/{INSTAGRAM_USER}/saved/vancuver/18218326192226445/",
        "Bangkok":   f"https://www.instagram.com/{INSTAGRAM_USER}/saved/bangkok/18076602889546929/",
        "Korea":     f"https://www.instagram.com/{INSTAGRAM_USER}/saved/korea/18014572816617634/",
        "Vegas":     f"https://www.instagram.com/{INSTAGRAM_USER}/saved/vegas/17935999712724854/",
        "London":    f"https://www.instagram.com/{INSTAGRAM_USER}/saved/london/17931072299648223/",
        "Paris":     f"https://www.instagram.com/{INSTAGRAM_USER}/saved/paris/17882555972992923/",
        "New York":  f"https://www.instagram.com/{INSTAGRAM_USER}/saved/new-york/18083321191358825/",
        "Barcelona": f"https://www.instagram.com/{INSTAGRAM_USER}/saved/barcelona/18263074000240310/",
        "Italy":     f"https://www.instagram.com/{INSTAGRAM_USER}/saved/italy/18021597329008690/",
        "Spain":     f"https://www.instagram.com/{INSTAGRAM_USER}/saved/spain/18028137425000482/",
        "Iceland":   f"https://www.instagram.com/{INSTAGRAM_USER}/saved/iceland/18364319491031274/",
    }
    print(f"  Using {len(known)} hardcoded collections")
    return known

def collect_post_urls(page: Page, coll_url: str, label: str) -> list[str]:
    try:
        page.goto(coll_url, timeout=45000, wait_until="domcontentloaded")
    except Exception:
        pass
    time.sleep(4)
    urls, seen, no_new = [], set(), 0

    for _ in range(MAX_SCROLLS):
        links = page.query_selector_all("a[href*='/p/'], a[href*='/reel/']")
        new = 0
        for link in links:
            href = link.get_attribute("href") or ""
            if href and href not in seen:
                seen.add(href); urls.append(normalize_url(href)); new += 1
        if new == 0:
            no_new += 1
            if no_new >= 3: break
        else:
            no_new = 0
        page.evaluate("window.scrollBy(0, window.innerHeight * 2.5)")
        time.sleep(SCROLL_DELAY)

    print(f"  Found {len(urls)} posts in '{label}'")
    return urls


# ── Login flow ────────────────────────────────────────────────────────────────────

def ensure_logged_in(pw) -> BrowserContext:
    browser = pw.chromium.launch(headless=True, slow_mo=50)
    ctx = browser.new_context(
        user_agent=WEB_HEADERS["User-Agent"],
        viewport={"width": 1280, "height": 900},
    )
    if SESSION_FILE.exists():
        _, cookies_list = load_session()
        ctx.add_cookies(cookies_list)
        page = ctx.new_page()
        page.goto("https://www.instagram.com/", timeout=30000, wait_until="domcontentloaded")
        time.sleep(2)
        if "login" not in page.url and not page.query_selector("input[name='username']"):
            print("Session valid.")
            page.close()
            return ctx
        page.close()
        print("Session expired, need re-login.")

    browser.close()
    browser = pw.chromium.launch(headless=False)
    ctx = browser.new_context(user_agent=WEB_HEADERS["User-Agent"], viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    page.goto("https://www.instagram.com/accounts/login/", timeout=30000)
    print("Waiting for login...")
    for _ in range(300):
        time.sleep(1)
        if any(c["name"] == "sessionid" for c in ctx.cookies("https://www.instagram.com")):
            print("Logged in!"); break
    save_session(ctx)
    page.close()
    return ctx


# ── Google Sheets export ──────────────────────────────────────────────────────────

SHEET_HEADERS = [
    "Place Name", "Type", "City", "Address", "Cuisine",
    "Price Range", "Why Recommended", "Highlights",
    "Instagram Source", "Instagram URL", "Date Added"
]

def _get_gsheets_client():
    """Authenticate and return a gspread client. Opens browser for first-time OAuth."""
    try:
        import gspread
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
    except ImportError as e:
        print(f"  Missing package: {e}. Run: pip install gspread google-auth-oauthlib")
        return None

    creds = None
    if GSHEETS_TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(GSHEETS_TOKEN), GSHEETS_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds:
            if not GSHEETS_CREDS.exists():
                print(f"""
  ── Google Sheets Setup Required ──────────────────────────────
  1. Go to https://console.cloud.google.com/
  2. Create a project → Enable Google Sheets API + Drive API
  3. Create OAuth 2.0 credentials (Desktop app)
  4. Download JSON → save as: {GSHEETS_CREDS}
  5. Re-run: python scan.py --push-to-sheets
  ──────────────────────────────────────────────────────────────
""")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(str(GSHEETS_CREDS), GSHEETS_SCOPES)
            creds = flow.run_local_server(port=0)

        GSHEETS_TOKEN.write_text(creds.to_json())

    import gspread
    return gspread.authorize(creds)

def export_to_google_sheets(travel_rows: list[dict]) -> Optional[str]:
    """
    Push travel rows to Google Sheets.
    Each city/collection gets its own tab.
    Returns the sheet URL or None on failure.
    """
    if not travel_rows:
        print("  No travel rows to export.")
        return None

    gc = _get_gsheets_client()
    if not gc:
        return None

    import gspread

    # Open or create the spreadsheet
    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        print(f"  Opened existing sheet: '{GOOGLE_SHEET_NAME}'")
    except gspread.SpreadsheetNotFound:
        sh = gc.create(GOOGLE_SHEET_NAME)
        print(f"  Created new sheet: '{GOOGLE_SHEET_NAME}'")

    # Group rows by collection city (the Instagram collection name)
    by_collection: dict[str, list[dict]] = {}
    for row in travel_rows:
        collection = row.get("Collection") or row.get("City", "Unknown")
        # Normalize: strip country part if present, use collection name
        by_collection.setdefault(collection, []).append(row)

    # Get existing worksheet names
    existing_tabs = {ws.title for ws in sh.worksheets()}

    total_added = 0
    for collection, rows in sorted(by_collection.items()):
        tab_name = collection[:30]  # Sheet tab names max ~100 chars but keep short

        if tab_name not in existing_tabs:
            ws = sh.add_worksheet(title=tab_name, rows=500, cols=len(SHEET_HEADERS))
            ws.append_row(SHEET_HEADERS, value_input_option="RAW")
            existing_tabs.add(tab_name)
            print(f"    Created tab: {tab_name}")
        else:
            ws = sh.worksheet(tab_name)

        # Get existing place names to skip dupes
        existing_data = ws.get_all_values()
        existing_places = {r[0].lower() for r in existing_data[1:]} if len(existing_data) > 1 else set()

        new_rows = []
        for row in rows:
            place = row.get("Place Name", "")
            if place.lower() not in existing_places:
                new_rows.append([
                    row.get("Place Name", ""),
                    row.get("Type", ""),
                    row.get("City", ""),
                    row.get("Address", ""),
                    row.get("Cuisine", ""),
                    row.get("Price Range", ""),
                    row.get("Why Recommended", ""),
                    row.get("Highlights", ""),
                    row.get("Instagram Source", ""),
                    row.get("Instagram URL", ""),
                    row.get("Date Added", ""),
                ])
                existing_places.add(place.lower())

        if new_rows:
            ws.append_rows(new_rows, value_input_option="RAW")
            print(f"    {tab_name}: added {len(new_rows)} rows")
            total_added += len(new_rows)
        else:
            print(f"    {tab_name}: all rows already present")

    # Remove default "Sheet1" if it exists and is empty
    try:
        sheet1 = sh.worksheet("Sheet1")
        if sheet1.get_all_values() == []:
            sh.del_worksheet(sheet1)
    except Exception:
        pass

    url = f"https://docs.google.com/spreadsheets/d/{sh.id}"
    print(f"\n  ✓ Google Sheet: {url}  ({total_added} rows added)")
    return url


# ── Enrich existing notes ─────────────────────────────────────────────────────────

def _parse_frontmatter_field(content: str, field: str) -> str:
    """Extract a field value from YAML frontmatter."""
    m = re.search(rf'^{field}:\s*"?([^"\n]+)"?\s*$', content, re.MULTILINE)
    return m.group(1).strip() if m else ""

def _extract_fnames_from_note(content: str, pattern: str) -> list[str]:
    """Extract embedded filenames matching pattern from note content."""
    return re.findall(rf'!\[\[({pattern})\]\]', content)

def enrich_existing_notes(cookies: dict):
    """
    Re-analyze all existing Travel and Food-Drink notes using Claude vision.
    Re-uses already-downloaded frames from _media/ — no video re-download needed.
    Updates notes in place with structured content.
    """
    state = load_state()
    new_travel_rows = []

    folders = [
        (OBSIDIAN_BASE / "Instagram/Travel",     "travel"),
        (OBSIDIAN_BASE / "Instagram/Food-Drink", "food_drink"),
    ]

    total_enriched = 0
    total_failed = 0
    total_skipped = 0

    for folder_path, note_type in folders:
        if not folder_path.exists():
            continue

        notes = sorted(folder_path.glob("*.md"))
        print(f"\n{'─'*55}")
        print(f"[ENRICH] {folder_path.name}  ({len(notes)} notes)")
        print(f"{'─'*55}")

        for i, note_path in enumerate(notes, 1):
            try:
                content = note_path.read_text(encoding="utf-8")

                # Parse key fields from frontmatter
                ig_url = _parse_frontmatter_field(content, "instagram_url")
                if not ig_url:
                    print(f"  [{i}/{len(notes)}] {note_path.name}: no instagram_url, skip")
                    total_skipped += 1
                    continue

                collection = (_parse_frontmatter_field(content, "collection") or
                              _parse_frontmatter_field(content, "city") or "Unknown")
                # If city includes country (e.g. "Tokyo, Japan"), extract just collection part
                # Use the frontmatter collection tag if available
                tags_match = re.search(r'tags:.*?(?=\ndate:)', content, re.DOTALL)
                tags_text = tags_match.group(0) if tags_match else ""
                # Find the travel city tag (after 'travel' and 'video' tags)
                collection_tag = ""
                for known_city in COLLECTIONS.keys():
                    if known_city.lower().replace(" ", "-") in tags_text.lower():
                        collection_tag = known_city
                        break
                if collection_tag:
                    collection = collection_tag

                # Find existing frames and images
                frame_fnames = _extract_fnames_from_note(content, r'[^\]]*frame\d+\.jpg')
                img_fnames = _extract_fnames_from_note(content, r'[^\]]*img\d+\.\w+')

                # Extract existing transcript
                transcript = ""
                t_match = re.search(r'## Video Transcript\n\n(.+?)(?:\n##|\Z)', content, re.DOTALL)
                if t_match:
                    transcript = t_match.group(1).strip()

                # Fetch post data from Instagram API
                shortcode = shortcode_from_url(ig_url)
                if not shortcode:
                    print(f"  [{i}/{len(notes)}] {note_path.name}: bad URL, skip")
                    total_skipped += 1
                    continue

                print(f"  [{i}/{len(notes)}] {note_path.name[:45]}...", end=" ", flush=True)

                item = get_post_data(shortcode, cookies)
                if not item:
                    print("API ✗")
                    total_failed += 1
                    time.sleep(1.5)
                    continue

                d = extract_from_api(item)

                # Run Claude analysis
                if note_type == "travel":
                    analysis = analyze_travel_post(
                        d["caption"], d["location"], transcript,
                        frame_fnames, img_fnames, collection
                    )
                    note_content, _, travel_row = _build_travel_note(
                        d, collection, img_fnames, frame_fnames, transcript, analysis
                    )
                    new_travel_rows.append(travel_row)

                elif note_type == "food_drink":
                    ctype_name = "Cocktail" if "cocktail" in tags_text.lower() else "Recipes"
                    analysis = analyze_recipe_post(
                        d["caption"], transcript,
                        frame_fnames, img_fnames, ctype_name
                    )
                    note_content, _ = _build_recipe_note(
                        d, ctype_name, img_fnames, frame_fnames, transcript, analysis
                    )
                else:
                    total_skipped += 1
                    continue

                _overwrite_obsidian(note_path, note_content)
                total_enriched += 1

            except Exception as e:
                print(f"  [{i}/{len(notes)}] ERROR: {e}")
                traceback.print_exc()
                total_failed += 1

            time.sleep(POST_DELAY)

    # Update state with richer travel rows
    if new_travel_rows:
        state["travel_rows"] = new_travel_rows
        save_state(state)

    print(f"\n{'='*55}")
    print(f"  Enrichment complete.")
    print(f"  Enriched: {total_enriched}  |  Failed: {total_failed}  |  Skipped: {total_skipped}")
    print(f"{'='*55}")

    return new_travel_rows


# ── Reprocess videos mode ─────────────────────────────────────────────────────────

def reprocess_videos(cookies: dict):
    state = load_state()
    processed = list(state["processed_posts"])
    print(f"\nChecking {len(processed)} processed posts for videos...")
    video_urls = []

    for i, url in enumerate(processed, 1):
        sc = shortcode_from_url(url)
        if not sc:
            continue
        item = get_post_data(sc, cookies)
        if item and item.get("media_type") == 2:
            video_urls.append(url)
            print(f"  [VIDEO] {url}")
        if i % 10 == 0:
            print(f"  {i}/{len(processed)} checked...")
        time.sleep(0.5)

    if not video_urls:
        print("No video posts found in processed list.")
        return

    print(f"\nFound {len(video_urls)} video post(s). Removing from processed list...")
    for url in video_urls:
        state["processed_posts"].remove(url)
        if url in state.get("failed_posts", []):
            state["failed_posts"].remove(url)
    save_state(state)
    print(f"Done. Run scan.py normally to re-process these {len(video_urls)} video(s).")


# ── Travel CSV (local backup) ─────────────────────────────────────────────────────

def export_travel_csv(state: dict):
    rows = state.get("travel_rows", [])
    if not rows:
        return
    dest = OBSIDIAN_BASE / "Instagram/Travel"
    dest.mkdir(parents=True, exist_ok=True)
    lines = [",".join(f'"{h}"' for h in SHEET_HEADERS)]
    for row in rows:
        lines.append(",".join(
            f'"{str(row.get(h, "")).replace(chr(34), chr(39))}"'
            for h in SHEET_HEADERS
        ))
    fp = dest / "travel-hit-list.csv"
    fp.write_text("\n".join(lines), encoding="utf-8")
    print(f"Travel CSV → {fp}")


# ── Main ──────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Instagram Saved Posts Scanner — Claude Vision Edition")
    parser.add_argument("--reprocess-videos", action="store_true",
                        help="Queue video posts for re-processing")
    parser.add_argument("--enrich", action="store_true",
                        help="Re-analyze all existing Travel + Food-Drink notes with Claude vision")
    parser.add_argument("--push-to-sheets", action="store_true",
                        help="Push travel rows from state file to Google Sheets")
    parser.add_argument("--only", nargs="+", metavar="COLLECTION",
                        help="Scan only these collections (e.g. --only Taiwan Spain Barcelona)")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("  Instagram Scanner — Claude Vision Edition")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60 + "\n")

    state = load_state()
    print(f"State: {len(state['processed_posts'])} processed, {len(state.get('failed_posts', []))} failed\n")

    cookies, _ = load_session()

    # ── Standalone modes ──

    if args.push_to_sheets:
        rows = state.get("travel_rows", [])
        print(f"Pushing {len(rows)} travel rows to Google Sheets...")
        export_to_google_sheets(rows)
        return

    if args.reprocess_videos:
        reprocess_videos(cookies)
        return

    if args.enrich:
        new_rows = enrich_existing_notes(cookies)
        if new_rows:
            print(f"\nPushing {len(new_rows)} enriched rows to Google Sheets...")
            sheet_url = export_to_google_sheets(new_rows)
            if sheet_url:
                print(f"Sheet: {sheet_url}")
            export_travel_csv(state)
        return

    # ── Normal scan mode ──

    counters = {}

    with sync_playwright() as pw:
        ctx = ensure_logged_in(pw)
        cookies, _ = load_session()
        page = ctx.new_page()

        try:
            discovered = find_collection_links(page)
        except RuntimeError as e:
            print(f"\nFATAL: {e}"); ctx.browser.close(); return

        only_filter = {c.lower() for c in args.only} if args.only else None

        for name, config in COLLECTIONS.items():
            if config is None:
                print(f"\n[SKIP] {name}"); continue
            if only_filter and name.lower() not in only_filter:
                continue

            coll_url = next((u for n, u in discovered.items() if n.lower() == name.lower()), None)
            if not coll_url:
                continue

            print(f"\n{'─'*50}")
            print(f"[COLLECTION] {name}")
            print(f"{'─'*50}")

            try:
                all_urls = collect_post_urls(page, coll_url, name)
                new_urls = [u for u in all_urls if not is_processed(state, u)]
                skipped = len(all_urls) - len(new_urls)
                print(f"  Processing {len(new_urls)} new posts ({skipped} already done)...")

                saved = 0
                for i, url in enumerate(new_urls, 1):
                    print(f"  [{i}/{len(new_urls)}]", end=" ")
                    ok = process_post(url, name, config, state, cookies)
                    if ok:
                        saved += 1
                    time.sleep(POST_DELAY)

                counters[name] = {"saved": saved, "skipped": skipped}
            except Exception as e:
                print(f"  Error: {e}"); traceback.print_exc()
                counters[name] = {"saved": 0, "skipped": 0}

        ctx.browser.close()

    # Export travel data
    export_travel_csv(state)
    travel_rows = state.get("travel_rows", [])
    if travel_rows:
        print(f"\nPushing {len(travel_rows)} travel rows to Google Sheets...")
        export_to_google_sheets(travel_rows)

    # Summary
    ai_skills = counters.get("AI", {}).get("saved", 0)
    ai_prompts = counters.get("AI prompt", {}).get("saved", 0)
    travel = sum(v["saved"] for k, v in counters.items()
                 if COLLECTIONS.get(k) and COLLECTIONS[k] and COLLECTIONS[k].get("type") == "travel")
    food = sum(v["saved"] for k, v in counters.items()
               if COLLECTIONS.get(k) and COLLECTIONS[k] and COLLECTIONS[k].get("type") == "food_drink")
    dupes = sum(v.get("skipped", 0) for v in counters.values())

    print("\n" + "="*60)
    print("  Instagram scan complete.")
    print("─"*60)
    print(f"  AI Skills saved:    {ai_skills}")
    print(f"  AI Prompts saved:   {ai_prompts}")
    print(f"  Travel saved:       {travel}  (+ Google Sheet)")
    print(f"  Food & Drink saved: {food}")
    print(f"  Skipped (dupes):    {dupes}")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
