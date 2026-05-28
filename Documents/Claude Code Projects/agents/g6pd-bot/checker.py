import json
import re
from pathlib import Path


def normalize(s: str) -> str:
    """Lowercase, strip whitespace, replace hyphens/underscores with space."""
    return re.sub(r"[-_]+", " ", s.strip().lower())


def load_db(path: str) -> dict:
    """Load g6pd_triggers.json and return parsed dict."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def lookup(ingredient: str, db: dict) -> dict | None:
    """
    Search all categories for ingredient by exact name or alias.
    Returns dict with {ingredient, matched_as, category, risk, notes} or None.
    """
    norm_input = normalize(ingredient)

    for category, items in db.items():
        for key, data in items.items():
            # Check canonical name
            if norm_input == normalize(key):
                return {
                    "ingredient": ingredient,
                    "matched_as": key,
                    "category": category,
                    "risk": data["risk"],
                    "notes": data.get("notes", ""),
                }
            # Check aliases
            for alias in data.get("aliases", []):
                if norm_input == normalize(alias):
                    return {
                        "ingredient": ingredient,
                        "matched_as": key,
                        "category": category,
                        "risk": data["risk"],
                        "notes": data.get("notes", ""),
                    }

    return None


# Pre-load DB at module import for reuse
_DB_PATH = Path(__file__).parent / "g6pd_triggers.json"
DB: dict = load_db(str(_DB_PATH))
