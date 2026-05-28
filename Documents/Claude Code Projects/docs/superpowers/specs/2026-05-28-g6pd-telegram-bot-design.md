# G6PD Scanner Telegram Bot — Design Spec

**Date:** 2026-05-28
**Stream:** Aiden
**Status:** Approved — ready for implementation

---

## 1. Purpose

A private Telegram bot that accepts a photo of any product label (medicine, food, cosmetic, supplement, household chemical) and determines whether any visible ingredient is a known G6PD deficiency trigger. Built for Aiden's safety — quick scan before giving any product to a G6PD-deficient child.

---

## 2. Scope

**In scope:**
- Photo input → ingredient extraction → G6PD risk check → response
- Checks across all trigger categories: drugs, foods, food additives, cosmetics, herbals, environmental chemicals
- Web search fallback for ingredients not in the local database
- Private access (whitelisted Telegram user IDs only)
- Always-on deployment on Railway (free tier)

**Out of scope:**
- Text-based ingredient lookup (photo only for now)
- Multi-language label support (English + Chinese only via Claude Vision)
- Storage of scan history
- PDF/document uploads

---

## 3. Architecture

```
agents/g6pd-bot/
├── bot.py                  # Telegram polling loop + message handlers
├── checker.py              # Local DB lookup logic
├── vision.py               # Claude Vision API call (extract + check)
├── web_search.py           # Claude web search fallback for unknown ingredients
├── g6pd_triggers.json      # Master trigger database (sourced from Obsidian note)
├── config.py               # Env var loading
├── requirements.txt
├── Procfile                # Railway: "worker: python bot.py"
└── railway.toml
```

**Deployment:** Railway.app, always-on worker process (not web server). GitHub auto-deploy on push to `main`.

---

## 4. Data Layer — `g6pd_triggers.json`

Structured JSON sourced from `Aiden Health record/G6PD Drug Triggers.md`. Organized into 6 categories. Loaded once at startup into memory.

```json
{
  "drugs": {
    "primaquine": { "risk": "high", "notes": "Antimalarial — #1 most documented trigger" },
    "dapsone": { "risk": "high", "notes": "Skin/antimycobacterial — severe hemolysis" },
    "paracetamol": { "risk": "medium", "notes": "Normal doses tolerated; avoid overdose" }
  },
  "foods": {
    "fava beans": { "risk": "high", "notes": "Also: broad beans, Windsor beans — #1 food trigger" },
    "bitter melon": { "risk": "medium", "notes": "Well-documented trigger" }
  },
  "food_additives": {
    "e220": { "risk": "high", "notes": "Sulfur dioxide — synthetic sulfite" },
    "sodium metabisulfite": { "risk": "high", "notes": "E223 — found in pickled foods, shrimp" },
    "tartrazine": { "risk": "high", "notes": "E102 — yellow azo dye" }
  },
  "cosmetics": {
    "camphor": { "risk": "high", "notes": "Oxidative; dangerous transdermally in infants" },
    "menthol": { "risk": "high", "notes": "Cooling products — avoid in babies especially" },
    "henna": { "risk": "high", "notes": "Lawsone compound — hemolytic in neonates" }
  },
  "herbals": {
    "berberine": { "risk": "high", "notes": "Derived from Huang Lian — avoid as supplement" },
    "rhizoma coptidis": { "risk": "high", "notes": "Huang Lian — banned in Singapore 1978 for G6PD" }
  },
  "chemicals": {
    "naphthalene": { "risk": "high", "notes": "Mothballs — #1 household trigger" },
    "aniline dyes": { "risk": "high", "notes": "Fabric and industrial dyes" }
  }
}
```

**Lookup logic in `checker.py`:**
- Normalize ingredient strings (lowercase, strip punctuation)
- Match against all keys + common aliases (e.g. "e220" matches "sulfur dioxide", "sulphur dioxide")
- Return: `{ingredient, category, risk, notes}` or `None` if not found

---

## 5. Components

### `config.py`
Loads 3 required env vars. Raises on startup if missing.

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From BotFather |
| `ANTHROPIC_API_KEY` | Existing Anthropic key |
| `ALLOWED_USER_IDS` | Comma-separated Telegram user IDs (e.g. `"123456,789012"`) |

### `vision.py` — Claude Vision + Local Check (primary path)
Single Claude API call per scan:

**Input:** Photo (base64) + system prompt containing the full `g6pd_triggers.json` as context

**System prompt instructs Claude to:**
1. Extract ALL ingredients, E-numbers, active/inactive components visible in the photo
2. Cross-check every extracted item against the provided G6PD trigger list
3. Return a structured JSON response:
```json
{
  "product_name": "Baby cooling gel",
  "total_ingredients": 12,
  "matches": [
    { "ingredient": "camphor", "category": "cosmetics", "risk": "high", "notes": "..." }
  ],
  "unknowns": ["glycerin", "aqua", "carbomer"],
  "clean": ["zinc oxide", "shea butter"]
}
```

**Model:** `claude-sonnet-4-5` with vision. Enable prompt caching on the system prompt (G6PD list is large — cache saves tokens on every scan). Sonnet is the right balance for vision + medical reasoning at this volume; Opus is overkill.

### `web_search.py` — Fallback for Unknowns
Called only when `vision.py` returns items in the `unknowns` list.

**Logic:**
- For each unknown ingredient: one Claude API call with `web_search_tool` enabled
- Query: `"[ingredient] G6PD deficiency risk hemolysis"`
- Claude searches, cites source, returns risk assessment
- Result flagged as `"source": "web"` to distinguish from local DB entries

**Rate control:** Max 5 web searches per scan to limit API cost.

### `bot.py` — Telegram Handlers

| Handler | Trigger | Action |
|---|---|---|
| `/start` | User opens bot | Welcome message + instructions |
| `/help` | | Same as /start |
| `photo` | User sends image | Run scan pipeline, return formatted result |
| Any other message | | "Send a photo of a product label to check for G6PD triggers." |

**Access control:** Every handler checks `update.effective_user.id` against `ALLOWED_USER_IDS`. Non-whitelisted users get no response (silent drop).

---

## 6. Response Format

```
🔍 Scanning [product name or "product"]... ⏳

──────────────────────

🔴 HIGH RISK — DO NOT USE
  💊 Camphor (cosmetic ingredient)
     ↳ Oxidative agent — dangerous for infants transdermally

🟡 MEDIUM RISK — Consult doctor first
  🧪 Propylene Glycol (additive)
     ↳ Medium-risk excipient

✅ No triggers found in 9 other ingredients

──────────────────────
🌐 Web-searched (not in local DB):
  • Glycerin — No known G6PD risk (WHO Drug Info)
  • Aqua — Safe

──────────────────────
⚠️ This is a reference tool only. Always confirm with a doctor or pharmacist.
```

**If all clear:**
```
✅ All clear — no G6PD triggers found in 12 scanned ingredients.

⚠️ This is a reference tool only. Always confirm with a doctor or pharmacist.
```

---

## 7. Error Handling

| Scenario | Bot Response |
|---|---|
| Photo too blurry / no text detected | "⚠️ I couldn't read the ingredients clearly. Try a clearer, closer photo." |
| Claude API error | "⚠️ Scan failed — please try again in a moment." |
| Non-whitelisted user | Silent drop (no response) |
| Photo is not a product label | "I see a photo but couldn't find ingredient information. Please send a close-up of the ingredients list." |
| Web search limit hit (>5 unknowns) | Show top 5, note: "X additional unknown ingredients not searched — check manually." |

---

## 8. Deployment — Railway

**Steps:**
1. Create Railway project linked to `agents/g6pd-bot/` directory in GitHub repo
2. Set env vars in Railway dashboard: `TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY`, `ALLOWED_USER_IDS`
3. `Procfile`: `worker: python bot.py`
4. `railway.toml`: sets root directory, no build command needed
5. Railway auto-deploys on every push to `main`

**Free tier:** Railway's Hobby plan ($5/mo) supports always-on workers. No sleep timeout like Render's free tier.

---

## 9. Cost Estimate (Anthropic API)

| Scan type | Calls | Approx cost |
|---|---|---|
| Clean scan (no unknowns) | 1 Vision call | ~$0.01–0.03 |
| Scan with web fallback (5 unknowns) | 1 Vision + 5 search | ~$0.05–0.10 |
| Monthly (50 scans avg) | — | ~$1–5/mo |

Prompt caching on the system prompt (G6PD list) reduces token cost by ~60% on the list portion.

---

## 10. Setup Steps for Rob (Pre-Build)

1. **Create Telegram bot via @BotFather:**
   - Open Telegram → search `@BotFather` → `/newbot`
   - Name: `G6PD Scanner` | Username: `g6pd_scanner_bot` (or similar available)
   - Copy the token → save as `TELEGRAM_BOT_TOKEN`

2. **Get your Telegram user ID:**
   - Message `@userinfobot` on Telegram → it returns your numeric user ID
   - Add family members' IDs to `ALLOWED_USER_IDS`

3. **Create Railway account** at railway.app → connect GitHub

---

## 11. Future Enhancements (Out of Scope Now)

- Text input mode: type an ingredient name directly
- `/history` command: log of last N scans
- Auto-update trigger DB from Obsidian note on bot restart
- Multi-language support (Japanese, Chinese label OCR)
- Push notifications: "New G6PD trigger added to DB"
