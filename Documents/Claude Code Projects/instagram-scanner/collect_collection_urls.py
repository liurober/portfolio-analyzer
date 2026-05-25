#!/usr/bin/env python3
"""
Collect post URLs for Instagram saved collections using the web API directly.
Bypasses Playwright — uses saved session cookies from ~/.instagram-session.json.
Saves results to /tmp/collection_urls.json for scan_api.py to consume.
"""
import json
import time
import requests
from pathlib import Path

SESSION_FILE = Path.home() / ".instagram-session.json"

COLLECTIONS_TO_FETCH = {
    # Already scanned in first pass — collect new posts only
    "Taiwan":    "17993409370769103",
    "Spain":     "18028137425000482",
    "Barcelona": "18263074000240310",
    "Japan":     "17962527776584391",
    "Korea":     "18014572816617634",
    "Bangkok":   "18076602889546929",
    "Vancouver": "18218326192226445",   # stored as "Vancuver" in Instagram
    "LA":        "17906050457774211",
    "Recipes":   "18049490191723514",
    "AI":        "18586387528049071",
    "AI prompt": "17884965672396366",
    "Seattle":   "17990372764957738",
    "Vegas":     "17935999712724854",
    "London":    "17931072299648223",
    "Paris":     "17882555972992923",
    "New York":  "18083321191358825",
    "Italy":     "18021597329008690",
    "Iceland":   "18364319491031274",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "X-IG-App-ID": "936619743392459",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.instagram.com/",
}


def load_cookies() -> dict:
    data = json.loads(SESSION_FILE.read_text())
    return {c["name"]: c["value"] for c in data["cookies"]}


def fetch_collection(collection_id: str, name: str, cookies: dict) -> list[str]:
    urls = []
    max_id = ""
    page = 0
    while True:
        params = {"num_results": 50}
        if max_id:
            params["max_id"] = max_id
        try:
            resp = requests.get(
                f"https://www.instagram.com/api/v1/feed/collection/{collection_id}/posts/",
                params=params, headers=HEADERS, cookies=cookies, timeout=20
            )
            if resp.status_code != 200:
                print(f"  HTTP {resp.status_code} on page {page+1}, stopping")
                break
            data = resp.json()
        except Exception as e:
            print(f"  Error page {page+1}: {e}")
            break

        items = data.get("items", [])
        for item in items:
            media = item.get("media") or item
            code = media.get("code") or media.get("shortcode")
            if code:
                urls.append(f"https://www.instagram.com/p/{code}/")

        page += 1
        max_id = data.get("next_max_id", "")
        more = data.get("more_available", False)
        print(f"  Page {page}: +{len(items)} posts (total: {len(urls)}, more: {more})")

        if not more or not max_id or not items:
            break
        time.sleep(0.5)

    return urls


def main():
    print("Collecting Instagram collection URLs via API\n")
    cookies = load_cookies()

    # Load existing state to skip already-processed URLs
    state_file = Path.home() / ".instagram-scan-state.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    processed = set(state.get("processed_posts", []))
    print(f"Already processed: {len(processed)} posts\n")

    result = {}
    for name, coll_id in COLLECTIONS_TO_FETCH.items():
        print(f"[{name}] collection ID: {coll_id}")
        all_urls = fetch_collection(coll_id, name, cookies)
        new_urls = [u for u in all_urls if u not in processed]
        result[name] = {"all": all_urls, "new": new_urls}
        print(f"  Total: {len(all_urls)} | New (unprocessed): {len(new_urls)}\n")
        time.sleep(1)

    out = Path("/tmp/collection_urls.json")
    out.write_text(json.dumps(result, indent=2))
    print(f"Saved to {out}")
    for name, data in result.items():
        print(f"  {name}: {len(data['new'])} new posts to process")


if __name__ == "__main__":
    main()
