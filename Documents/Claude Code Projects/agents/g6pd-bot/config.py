import os
from dotenv import load_dotenv

load_dotenv(override=True)

def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(f"Missing required env var: {key}")
    return val

TELEGRAM_BOT_TOKEN: str = _require("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY: str = _require("ANTHROPIC_API_KEY")

_raw_ids = _require("ALLOWED_USER_IDS")
ALLOWED_USER_IDS: set[int] = {int(uid.strip()) for uid in _raw_ids.split(",")}
