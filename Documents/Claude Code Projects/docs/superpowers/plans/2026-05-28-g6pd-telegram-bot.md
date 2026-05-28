# G6PD Scanner Telegram Bot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a private Telegram bot that accepts a product label photo and returns a G6PD deficiency risk assessment across drugs, foods, cosmetics, herbals, and chemicals — with Claude Vision for extraction and web search fallback for unknown ingredients.

**Architecture:** Python polling bot (`python-telegram-bot` v21 async) deployed as always-on Railway worker. Claude Vision API does ingredient extraction + local DB check in one call; unknown ingredients fall back to Claude with `web_search` tool. G6PD trigger data lives in `g6pd_triggers.json`, loaded once at startup.

**Tech Stack:** Python 3.11+, `python-telegram-bot==21.x`, `anthropic>=0.50.0`, `python-dotenv`, `pytest`, `pytest-asyncio`, Railway.app

---

## File Map

```
agents/g6pd-bot/
├── config.py            # Env var loading — raises on missing vars
├── checker.py           # Local JSON DB lookup with alias + fuzzy matching
├── vision.py            # Claude Vision API: extract ingredients + check DB
├── web_search.py        # Claude web_search fallback for unknowns
├── formatter.py         # Format scan results into Telegram message string
├── bot.py               # Telegram Application: handlers + whitelist + pipeline
├── g6pd_triggers.json   # Master trigger database (all 6 categories)
├── requirements.txt
├── Procfile             # Railway: worker: python bot.py
├── railway.toml         # Railway root dir config
├── .env.example         # Template for secrets
├── .gitignore
└── tests/
    ├── __init__.py
    ├── test_checker.py
    ├── test_vision.py
    ├── test_web_search.py
    └── test_formatter.py
```

---

## Task 1: Project Scaffold

**Files:**
- Create: `agents/g6pd-bot/config.py`
- Create: `agents/g6pd-bot/requirements.txt`
- Create: `agents/g6pd-bot/Procfile`
- Create: `agents/g6pd-bot/railway.toml`
- Create: `agents/g6pd-bot/.env.example`
- Create: `agents/g6pd-bot/.gitignore`
- Create: `agents/g6pd-bot/tests/__init__.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p agents/g6pd-bot/tests
touch agents/g6pd-bot/tests/__init__.py
```

- [ ] **Step 2: Create `agents/g6pd-bot/requirements.txt`**

```
python-telegram-bot==21.3
anthropic>=0.50.0
python-dotenv==1.0.1
pytest==8.2.0
pytest-asyncio==0.23.7
```

- [ ] **Step 3: Create `agents/g6pd-bot/.env.example`**

```
TELEGRAM_BOT_TOKEN=your_bot_token_here
ANTHROPIC_API_KEY=your_anthropic_key_here
ALLOWED_USER_IDS=111111111,222222222
```

- [ ] **Step 4: Create `agents/g6pd-bot/.gitignore`**

```
.env
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 5: Create `agents/g6pd-bot/config.py`**

```python
import os
from dotenv import load_dotenv

load_dotenv()

def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(f"Missing required env var: {key}")
    return val

TELEGRAM_BOT_TOKEN: str = _require("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY: str = _require("ANTHROPIC_API_KEY")

_raw_ids = _require("ALLOWED_USER_IDS")
ALLOWED_USER_IDS: set[int] = {int(uid.strip()) for uid in _raw_ids.split(",")}
```

- [ ] **Step 6: Create `agents/g6pd-bot/Procfile`**

```
worker: python bot.py
```

- [ ] **Step 7: Create `agents/g6pd-bot/railway.toml`**

```toml
[deploy]
startCommand = "python bot.py"
rootDirectory = "agents/g6pd-bot"
```

- [ ] **Step 8: Create `.env` with real credentials (never commit this)**

```bash
# In agents/g6pd-bot/.env — DO NOT COMMIT
TELEGRAM_BOT_TOKEN=8849643828:AAHPGbDeBj3za0yVobeYZwxKkLumcLA5mX0
ANTHROPIC_API_KEY=<your existing anthropic key>
ALLOWED_USER_IDS=8671492802,8932283522
```

- [ ] **Step 9: Install dependencies**

```bash
cd agents/g6pd-bot
pip install -r requirements.txt
```

- [ ] **Step 10: Verify config loads**

```bash
cd agents/g6pd-bot
python -c "import config; print('Users:', config.ALLOWED_USER_IDS)"
```

Expected: `Users: {8671492802, 8932283522}`

- [ ] **Step 11: Commit**

```bash
git add agents/g6pd-bot/config.py agents/g6pd-bot/requirements.txt \
        agents/g6pd-bot/Procfile agents/g6pd-bot/railway.toml \
        agents/g6pd-bot/.env.example agents/g6pd-bot/.gitignore \
        agents/g6pd-bot/tests/__init__.py
git commit -m "feat(g6pd-bot): project scaffold and config"
```

---

## Task 2: Build `g6pd_triggers.json`

**Files:**
- Create: `agents/g6pd-bot/g6pd_triggers.json`

- [ ] **Step 1: Create `agents/g6pd-bot/g6pd_triggers.json`**

Full comprehensive database across all 6 categories. Each entry has `risk`, `notes`, and `aliases` for fuzzy matching.

```json
{
  "drugs": {
    "primaquine": {
      "risk": "high",
      "notes": "Antimalarial — #1 most documented G6PD trigger",
      "aliases": ["primaquine phosphate", "primaquine sulfate"]
    },
    "dapsone": {
      "risk": "high",
      "notes": "Antimycobacterial / skin — causes severe hemolysis",
      "aliases": ["diaphenylsulfone", "aczone"]
    },
    "nitrofurantoin": {
      "risk": "high",
      "notes": "UTI antibiotic — avoid in G6PD",
      "aliases": ["macrobid", "macrodantin", "furadantin"]
    },
    "nitrofural": {
      "risk": "high",
      "notes": "Topical antibiotic",
      "aliases": ["nitrofurazone"]
    },
    "methylene blue": {
      "risk": "high",
      "notes": "Dye and antidote — causes severe oxidative hemolysis",
      "aliases": ["methylthioninium chloride", "methylene blue chloride"]
    },
    "rasburicase": {
      "risk": "high",
      "notes": "Urate oxidase — G6PD test mandatory before use",
      "aliases": ["elitek", "fasturtec"]
    },
    "tafenoquine": {
      "risk": "high",
      "notes": "Newer antimalarial — FDA warns G6PD test required",
      "aliases": ["krintafel", "kozenis"]
    },
    "chloroquine": {
      "risk": "high",
      "notes": "Antimalarial",
      "aliases": ["chloroquine phosphate", "aralen"]
    },
    "hydroxychloroquine": {
      "risk": "high",
      "notes": "Antimalarial / autoimmune",
      "aliases": ["plaquenil", "hydroxychloroquine sulfate"]
    },
    "sulfasalazine": {
      "risk": "high",
      "notes": "IBD / rheumatoid arthritis drug",
      "aliases": ["sulphasalazine", "azulfidine", "salazopyrin"]
    },
    "furazolidone": {
      "risk": "high",
      "notes": "",
      "aliases": ["furoxone"]
    },
    "phenazopyridine": {
      "risk": "high",
      "notes": "Urinary analgesic — OTC in US",
      "aliases": ["pyridium", "azo", "urogesic"]
    },
    "trimethoprim sulfamethoxazole": {
      "risk": "high",
      "notes": "Common antibiotic combo — avoid in G6PD",
      "aliases": ["co-trimoxazole", "bactrim", "septra", "tmp-smx", "trimethoprim-sulfamethoxazole"]
    },
    "sulfamethoxazole": {
      "risk": "high",
      "notes": "Sulfonamide component of Bactrim",
      "aliases": ["sulphamethoxazole"]
    },
    "trimethoprim": {
      "risk": "medium",
      "notes": "Antibiotic — medium risk alone, high risk with sulfamethoxazole",
      "aliases": []
    },
    "aspirin": {
      "risk": "high",
      "notes": "Avoid — also listed as O-Acetylsalicylic acid",
      "aliases": ["o-acetylsalicylic acid", "acetylsalicylic acid", "asa", "anacin", "bufferin", "ecotrin"]
    },
    "mepacrine": {
      "risk": "high",
      "notes": "Antiprotozoal",
      "aliases": ["quinacrine", "atabrine"]
    },
    "nalidixic acid": {
      "risk": "high",
      "notes": "Antibiotic",
      "aliases": ["neggram"]
    },
    "ofloxacin": {"risk": "high", "notes": "Fluoroquinolone antibiotic", "aliases": ["floxin", "ocuflox"]},
    "ciprofloxacin": {"risk": "high", "notes": "Fluoroquinolone antibiotic", "aliases": ["cipro", "ciproxin"]},
    "levofloxacin": {"risk": "high", "notes": "Fluoroquinolone antibiotic", "aliases": ["levaquin"]},
    "moxifloxacin": {"risk": "high", "notes": "Fluoroquinolone antibiotic", "aliases": ["avelox"]},
    "chloramphenicol": {"risk": "high", "notes": "Antibiotic", "aliases": []},
    "doxorubicin": {"risk": "high", "notes": "Chemotherapy", "aliases": ["adriamycin"]},
    "dabrafenib": {"risk": "high", "notes": "Cancer drug — BRAF inhibitor; FDA-warned", "aliases": ["tafinlar"]},
    "trametinib": {"risk": "high", "notes": "Cancer drug — MEK inhibitor; FDA-warned", "aliases": ["mekinist"]},
    "flutamide": {"risk": "high", "notes": "Cancer drug — anti-androgen; FDA-warned", "aliases": ["eulexin"]},
    "pegloticase": {"risk": "high", "notes": "Gout biologic — FDA-warned", "aliases": ["krystexxa"]},
    "probenecid": {"risk": "high", "notes": "Gout / uricosuric", "aliases": ["benemid"]},
    "glibenclamide": {"risk": "high", "notes": "Diabetes drug", "aliases": ["glyburide", "diabeta", "micronase", "glynase"]},
    "glimepiride": {"risk": "high", "notes": "Diabetes drug", "aliases": ["amaryl"]},
    "glipizide": {"risk": "high", "notes": "Diabetes drug", "aliases": ["glucotrol"]},
    "tolazamide": {"risk": "high", "notes": "Diabetes drug", "aliases": ["tolinase"]},
    "tolbutamide": {"risk": "high", "notes": "Diabetes drug", "aliases": []},
    "mesalazine": {"risk": "high", "notes": "IBD drug", "aliases": ["5-aminosalicylic acid", "5-asa", "asacol", "pentasa", "lialda"]},
    "naphthalene": {"risk": "high", "notes": "Mothballs — #1 household chemical trigger", "aliases": ["naphtalin", "mothballs", "moth crystals"]},
    "phenylhydrazine": {"risk": "high", "notes": "Industrial chemical", "aliases": []},
    "sodium nitroprusside": {"risk": "high", "notes": "IV antihypertensive", "aliases": ["nitropress"]},
    "sodium nitrite": {"risk": "high", "notes": "Cyanide antidote / food preservative in cured meats", "aliases": ["e250"]},
    "menadione": {"risk": "high", "notes": "Synthetic Vitamin K3 — avoid", "aliases": ["vitamin k3", "menadione sodium bisulfite"]},
    "menadiol sodium sulfate": {"risk": "high", "notes": "Vitamin K4", "aliases": ["vitamin k4"]},
    "ibuprofen": {"risk": "medium", "notes": "NSAID — generally avoid; paracetamol preferred", "aliases": ["advil", "motrin", "nurofen", "brufen"]},
    "paracetamol": {"risk": "medium", "notes": "Safe at normal doses — avoid high doses or overdose", "aliases": ["acetaminophen", "tylenol", "panadol", "calpol"]},
    "quinine": {"risk": "medium", "notes": "Antimalarial; also in tonic water", "aliases": ["quinine sulfate", "quinamm"]},
    "quinidine": {"risk": "medium", "notes": "Antiarrhythmic", "aliases": ["quinidine sulfate"]},
    "isoniazid": {"risk": "medium", "notes": "TB medication", "aliases": ["inh", "isoniazide", "nydrazid"]},
    "colchicine": {"risk": "medium", "notes": "Gout medication", "aliases": ["colcrys", "mitigare"]},
    "pyrimethamine": {"risk": "medium", "notes": "Antimalarial / antiparasitic", "aliases": ["daraprim"]},
    "vitamin k": {"risk": "medium", "notes": "Avoid synthetic forms (K3); K1 use with caution", "aliases": ["phytonadione", "phytomenadione"]},
    "levodopa": {"risk": "medium", "notes": "Parkinson's drug", "aliases": ["l-dopa", "sinemet"]},
    "streptomycin": {"risk": "medium", "notes": "Antibiotic", "aliases": []},
    "diphenhydramine": {"risk": "low", "notes": "Antihistamine — low risk", "aliases": ["benadryl", "diphenhydramine hydrochloride"]},
    "benzocaine": {"risk": "low", "notes": "Topical anesthetic — low risk", "aliases": []},
    "azathioprine": {"risk": "low", "notes": "Immunosuppressant — do not combine with other G6PD drugs", "aliases": ["imuran"]},
    "pregabalin": {"risk": "low", "notes": "Anticonvulsant / nerve pain — use with caution", "aliases": ["lyrica"]}
  },
  "foods": {
    "fava beans": {
      "risk": "high",
      "notes": "#1 food trigger — absolute avoid",
      "aliases": ["broad beans", "windsor beans", "horse beans", "vicia faba", "habas", "faba beans", "field beans", "ful medames", "fool medames"]
    },
    "bitter melon": {
      "risk": "high",
      "notes": "Well-documented trigger",
      "aliases": ["bitter gourd", "bitter cucumber", "balsam pear", "ampalaya", "karela", "momordica charantia"]
    },
    "tonic water": {
      "risk": "medium",
      "notes": "Contains quinine",
      "aliases": ["indian tonic water", "schweppes tonic"]
    },
    "blueberries": {
      "risk": "medium",
      "notes": "Mixed evidence — avoid in infants and severe G6PD",
      "aliases": []
    },
    "fenugreek": {
      "risk": "medium",
      "notes": "Seeds and supplements — isolated cases",
      "aliases": ["methi", "fenugreek seeds", "fenugreek extract"]
    },
    "soybeans": {
      "risk": "medium",
      "notes": "Legume — caution especially for infants",
      "aliases": ["soy", "soya", "edamame", "soy protein", "soy extract"]
    },
    "peanuts": {
      "risk": "medium",
      "notes": "Legume — use caution",
      "aliases": ["groundnuts", "peanut oil", "arachis oil"]
    },
    "chickpeas": {
      "risk": "medium",
      "notes": "Legume — use caution",
      "aliases": ["garbanzo beans", "gram", "hummus", "falafel", "chana"]
    },
    "lentils": {
      "risk": "medium",
      "notes": "Legume — use caution",
      "aliases": ["dal", "dhal", "red lentils", "green lentils"]
    },
    "eggplant": {
      "risk": "medium",
      "notes": "Isolated reports",
      "aliases": ["aubergine", "garden egg", "brinjal"]
    },
    "pumpkin": {
      "risk": "medium",
      "notes": "Isolated case reports only",
      "aliases": ["squash"]
    }
  },
  "food_additives": {
    "sulfur dioxide": {
      "risk": "high",
      "notes": "Synthetic sulfite — hemolytic in G6PD",
      "aliases": ["sulphur dioxide", "e220", "220", "so2"]
    },
    "sodium sulfite": {
      "risk": "high",
      "notes": "Synthetic sulfite preservative",
      "aliases": ["e221", "221", "sodium sulphite"]
    },
    "sodium bisulfite": {
      "risk": "high",
      "notes": "Synthetic sulfite preservative",
      "aliases": ["e222", "222", "sodium bisulphite", "sodium hydrogen sulfite"]
    },
    "sodium metabisulfite": {
      "risk": "high",
      "notes": "Synthetic sulfite — in pickled foods, shrimp, wine",
      "aliases": ["e223", "223", "sodium metabisulphite", "sodium pyrosulfite"]
    },
    "potassium metabisulfite": {
      "risk": "high",
      "notes": "Synthetic sulfite — in wine, beer",
      "aliases": ["e224", "224", "potassium metabisulphite", "potassium pyrosulfite"]
    },
    "potassium bisulfite": {
      "risk": "high",
      "notes": "Synthetic sulfite",
      "aliases": ["e228", "228", "potassium hydrogen sulfite"]
    },
    "tartrazine": {
      "risk": "high",
      "notes": "Yellow azo dye — artificial coloring",
      "aliases": ["e102", "102", "fd&c yellow 5", "yellow 5", "ci food yellow 4"]
    },
    "sunset yellow": {
      "risk": "high",
      "notes": "Orange azo dye — artificial coloring",
      "aliases": ["e110", "110", "fd&c yellow 6", "yellow 6", "ci food yellow 3"]
    },
    "allura red": {
      "risk": "high",
      "notes": "Red azo dye — artificial coloring",
      "aliases": ["e129", "129", "fd&c red 40", "red 40"]
    },
    "indigo carmine": {
      "risk": "high",
      "notes": "Blue artificial coloring",
      "aliases": ["e132", "132", "fd&c blue 2", "blue 2", "indigotine"]
    },
    "brilliant blue": {
      "risk": "high",
      "notes": "Blue artificial coloring",
      "aliases": ["e133", "133", "fd&c blue 1", "blue 1"]
    },
    "toluidine blue": {
      "risk": "high",
      "notes": "Lab dye; also used medically — avoid",
      "aliases": ["tolonium chloride", "toluidine blue o"]
    },
    "aniline dyes": {
      "risk": "high",
      "notes": "Fabric and industrial dyes — also in some foods",
      "aliases": ["aniline", "aniline based dye", "azo dye"]
    },
    "sodium benzoate": {
      "risk": "medium",
      "notes": "Preservative — some concern in G6PD",
      "aliases": ["e211", "211", "benzoate of soda"]
    },
    "benzoic acid": {
      "risk": "medium",
      "notes": "Preservative",
      "aliases": ["e210", "210"]
    },
    "ascorbic acid": {
      "risk": "medium",
      "notes": "High-dose synthetic Vitamin C — avoid megadoses",
      "aliases": ["vitamin c", "e300", "300", "l-ascorbic acid"]
    }
  },
  "cosmetics": {
    "camphor": {
      "risk": "high",
      "notes": "Oxidative agent — DANGEROUS for infants transdermally; in muscle rubs, cooling gels",
      "aliases": ["camphor oil", "camphorated oil", "natural camphor", "synthetic camphor"]
    },
    "menthol": {
      "risk": "high",
      "notes": "Avoid in babies especially — in toothpaste, mouthwash, cooling creams, mints, vapour rubs",
      "aliases": ["l-menthol", "peppermint menthol", "menthol crystals"]
    },
    "henna": {
      "risk": "high",
      "notes": "Lawsone compound — hemolytic in neonates; black/red Egyptian henna most dangerous",
      "aliases": ["lawsone", "black henna", "red henna", "egyptian henna", "mehndi", "henna powder"]
    },
    "eucalyptus oil": {
      "risk": "high",
      "notes": "PMC study: 13.4% increase in hemolytic phenotype",
      "aliases": ["eucalyptus essential oil", "cineole", "1,8-cineole"]
    },
    "salicylic acid": {
      "risk": "medium",
      "notes": "Aspirin derivative — in acne treatments, exfoliants, anti-dandruff shampoos",
      "aliases": ["2-hydroxybenzoic acid", "bha (when used as salicylic acid)"]
    },
    "propylene glycol": {
      "risk": "medium",
      "notes": "Common excipient in creams and pharmaceuticals",
      "aliases": ["1,2-propanediol", "e1520", "pg"]
    }
  },
  "herbals": {
    "berberine": {
      "risk": "high",
      "notes": "Derived from Huang Lian — caused neonatal kernicterus; banned in Singapore 1978",
      "aliases": ["berberine hydrochloride", "berberine hcl", "berberine sulfate"]
    },
    "rhizoma coptidis": {
      "risk": "high",
      "notes": "Huang Lian / Huanglian — TCM herb; contains berberine",
      "aliases": ["huang lian", "huanglian", "coptis chinensis", "coptis", "goldenthread"]
    },
    "cortex moutan": {
      "risk": "medium",
      "notes": "Mu Dan Pi — TCM herb; pro-oxidative in vitro",
      "aliases": ["mu dan pi", "moutan bark", "peony bark"]
    },
    "radix rehmanniae": {
      "risk": "medium",
      "notes": "Di Huang — TCM herb; pro-oxidative in vitro",
      "aliases": ["di huang", "rehmannia", "chinese foxglove"]
    },
    "radix bupleuri": {
      "risk": "medium",
      "notes": "Chai Hu — TCM herb; pro-oxidative in vitro",
      "aliases": ["chai hu", "bupleurum", "thorowax root"]
    },
    "rhizoma polygoni cuspidati": {
      "risk": "medium",
      "notes": "Hu Zhang / Japanese knotweed — pro-oxidative in vitro",
      "aliases": ["hu zhang", "japanese knotweed", "polygonum cuspidatum", "reynoutria japonica"]
    },
    "flos chimonanthi": {
      "risk": "medium",
      "notes": "TCM herb — pro-oxidative in vitro",
      "aliases": ["wintersweet flower", "chimonanthus"]
    },
    "lonicera japonica": {
      "risk": "medium",
      "notes": "Honeysuckle — common in TCM; use caution",
      "aliases": ["jin yin hua", "honeysuckle", "honeysuckle flower extract"]
    }
  },
  "chemicals": {
    "naphthalene": {
      "risk": "high",
      "notes": "Mothballs and moth crystals — #1 household trigger",
      "aliases": ["naphtalin", "white tar", "mothballs", "moth crystals", "moth flakes"]
    },
    "beta-naphthol": {
      "risk": "high",
      "notes": "Found in some drain/bathroom cleaners",
      "aliases": ["2-naphthol", "z-naphthol", "beta naphthol"]
    },
    "aniline": {
      "risk": "high",
      "notes": "Industrial dye precursor",
      "aliases": ["aniline oil", "aminobenzene", "phenylamine"]
    }
  }
}
```

- [ ] **Step 2: Verify JSON is valid**

```bash
cd agents/g6pd-bot
python -c "import json; db = json.load(open('g6pd_triggers.json')); print(f'Categories: {list(db.keys())}'); print(f'Total entries: {sum(len(v) for v in db.values())}')"
```

Expected output:
```
Categories: ['drugs', 'foods', 'food_additives', 'cosmetics', 'herbals', 'chemicals']
Total entries: 90+
```

- [ ] **Step 3: Commit**

```bash
git add agents/g6pd-bot/g6pd_triggers.json
git commit -m "feat(g6pd-bot): add comprehensive G6PD trigger database JSON"
```

---

## Task 3: `checker.py` — Local DB Lookup

**Files:**
- Create: `agents/g6pd-bot/checker.py`
- Create: `agents/g6pd-bot/tests/test_checker.py`

- [ ] **Step 1: Write the failing tests first**

Create `agents/g6pd-bot/tests/test_checker.py`:

```python
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from checker import load_db, lookup, normalize

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "g6pd_triggers.json")


def test_load_db_returns_dict():
    db = load_db(DB_PATH)
    assert isinstance(db, dict)
    assert "drugs" in db
    assert "foods" in db
    assert "cosmetics" in db


def test_normalize_lowercases_and_strips():
    assert normalize("  Primaquine  ") == "primaquine"
    assert normalize("Fava-Beans") == "fava beans"
    assert normalize("E220") == "e220"


def test_lookup_exact_match():
    db = load_db(DB_PATH)
    result = lookup("primaquine", db)
    assert result is not None
    assert result["risk"] == "high"
    assert result["category"] == "drugs"


def test_lookup_case_insensitive():
    db = load_db(DB_PATH)
    result = lookup("DAPSONE", db)
    assert result is not None
    assert result["risk"] == "high"


def test_lookup_alias_match():
    db = load_db(DB_PATH)
    # "bactrim" is an alias for trimethoprim sulfamethoxazole
    result = lookup("Bactrim", db)
    assert result is not None
    assert result["risk"] == "high"


def test_lookup_alias_trade_name():
    db = load_db(DB_PATH)
    # "tylenol" is an alias for paracetamol
    result = lookup("Tylenol", db)
    assert result is not None
    assert result["risk"] == "medium"


def test_lookup_unknown_returns_none():
    db = load_db(DB_PATH)
    result = lookup("glycerin", db)
    assert result is None


def test_lookup_food_trigger():
    db = load_db(DB_PATH)
    result = lookup("broad beans", db)
    assert result is not None
    assert result["risk"] == "high"
    assert result["category"] == "foods"


def test_lookup_cosmetic_trigger():
    db = load_db(DB_PATH)
    result = lookup("camphor", db)
    assert result is not None
    assert result["category"] == "cosmetics"


def test_lookup_e_number():
    db = load_db(DB_PATH)
    result = lookup("E220", db)
    assert result is not None
    assert result["category"] == "food_additives"
```

- [ ] **Step 2: Run tests — confirm they all fail**

```bash
cd agents/g6pd-bot
python -m pytest tests/test_checker.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'load_db' from 'checker'` (checker.py doesn't exist yet)

- [ ] **Step 3: Create `agents/g6pd-bot/checker.py`**

```python
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
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
cd agents/g6pd-bot
python -m pytest tests/test_checker.py -v
```

Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agents/g6pd-bot/checker.py agents/g6pd-bot/tests/test_checker.py
git commit -m "feat(g6pd-bot): checker with local DB lookup and alias matching"
```

---

## Task 4: `vision.py` — Claude Vision API

**Files:**
- Create: `agents/g6pd-bot/vision.py`
- Create: `agents/g6pd-bot/tests/test_vision.py`

- [ ] **Step 1: Write failing tests**

Create `agents/g6pd-bot/tests/test_vision.py`:

```python
import pytest
import sys
import os
import json
from unittest.mock import MagicMock, patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vision import build_system_prompt, parse_response, scan_photo


def test_build_system_prompt_contains_database():
    db_str = json.dumps({"drugs": {"primaquine": {"risk": "high", "notes": "test", "aliases": []}}})
    prompt = build_system_prompt(db_str)
    assert "primaquine" in prompt
    assert "JSON" in prompt
    assert "matches" in prompt


def test_parse_response_valid_json():
    raw = '{"product_name": "Test Cream", "total_ingredients": 3, "matches": [], "unknowns": [], "clean": ["water"]}'
    result = parse_response(raw)
    assert result["product_name"] == "Test Cream"
    assert result["total_ingredients"] == 3


def test_parse_response_strips_markdown_fences():
    raw = '```json\n{"product_name": null, "total_ingredients": 0, "matches": [], "unknowns": [], "clean": []}\n```'
    result = parse_response(raw)
    assert result["product_name"] is None


def test_parse_response_error_key():
    raw = '{"error": "no_ingredients_visible"}'
    result = parse_response(raw)
    assert "error" in result


def test_parse_response_invalid_json_raises():
    with pytest.raises(ValueError, match="Could not parse Claude response"):
        parse_response("This is not JSON at all")


@patch("vision.anthropic.Anthropic")
def test_scan_photo_calls_api(mock_anthropic_class):
    """Verify scan_photo calls the Anthropic client with correct structure."""
    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client

    expected_json = '{"product_name": "Baby cream", "total_ingredients": 5, "matches": [{"ingredient": "camphor", "matched_as": "camphor", "category": "cosmetics", "risk": "high", "notes": "Dangerous for infants"}], "unknowns": ["glycerin"], "clean": ["water", "zinc oxide"]}'
    mock_client.messages.create.return_value.content = [MagicMock(text=expected_json)]

    result = scan_photo(
        image_bytes=b"fake_image_data",
        media_type="image/jpeg",
        db_str='{"drugs": {}}',
        api_key="test-key"
    )

    assert mock_client.messages.create.called
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-5"
    assert result["product_name"] == "Baby cream"
    assert result["matches"][0]["ingredient"] == "camphor"
    assert result["unknowns"] == ["glycerin"]
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
cd agents/g6pd-bot
python -m pytest tests/test_vision.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'build_system_prompt' from 'vision'`

- [ ] **Step 3: Create `agents/g6pd-bot/vision.py`**

```python
import anthropic
import base64
import json
import re


SYSTEM_PROMPT_TEMPLATE = """\
You are a G6PD deficiency safety scanner for a baby's parent.

Your job:
1. Extract ALL ingredients, E-numbers, active ingredients, inactive ingredients, \
and any chemical or food components visible in the product label photo.
2. Cross-check every extracted item against the G6PD TRIGGER DATABASE below.
3. Return ONLY a valid JSON object — no markdown, no commentary.

Return this exact JSON structure:
{{
  "product_name": "string or null if not visible",
  "total_ingredients": <number of ingredients you extracted>,
  "matches": [
    {{
      "ingredient": "<exact text from label>",
      "matched_as": "<canonical name in database>",
      "category": "drugs|foods|food_additives|cosmetics|herbals|chemicals",
      "risk": "high|medium|low",
      "notes": "<string>"
    }}
  ],
  "unknowns": ["<ingredient not in database and you are unsure about>"],
  "clean": ["<ingredient you are confident is safe>"]
}}

Rules:
- unknowns: ingredients not in the database AND you are not confident about G6PD safety
- clean: water, salt, and ingredients you are confident are G6PD-safe
- If no ingredients are visible, return: {{"error": "no_ingredients_visible"}}
- If the image is not a product label, return: {{"error": "not_a_product_label"}}
- Do not include markdown fences or any text outside the JSON object

G6PD TRIGGER DATABASE:
{db_str}
"""


def build_system_prompt(db_str: str) -> str:
    """Inject the trigger database into the system prompt."""
    return SYSTEM_PROMPT_TEMPLATE.format(db_str=db_str)


def parse_response(raw: str) -> dict:
    """
    Parse Claude's response into a dict.
    Strips markdown fences if present.
    Raises ValueError if not valid JSON.
    """
    # Strip markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Could not parse Claude response: {e}\nRaw: {raw[:200]}")


def scan_photo(
    image_bytes: bytes,
    media_type: str,
    db_str: str,
    api_key: str,
) -> dict:
    """
    Send product label photo to Claude Vision.
    Returns parsed scan result dict.

    Args:
        image_bytes: Raw image data
        media_type: e.g. "image/jpeg", "image/png"
        db_str: JSON string of g6pd_triggers.json (for prompt caching)
        api_key: Anthropic API key
    """
    client = anthropic.Anthropic(api_key=api_key)
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": build_system_prompt(db_str),
                "cache_control": {"type": "ephemeral"},  # Cache the large DB prompt
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Scan this product label for G6PD triggers. Return the JSON response as instructed.",
                    },
                ],
            }
        ],
    )

    return parse_response(response.content[0].text)
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
cd agents/g6pd-bot
python -m pytest tests/test_vision.py -v
```

Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agents/g6pd-bot/vision.py agents/g6pd-bot/tests/test_vision.py
git commit -m "feat(g6pd-bot): vision module with Claude Vision API + prompt caching"
```

---

## Task 5: `web_search.py` — Fallback for Unknowns

**Files:**
- Create: `agents/g6pd-bot/web_search.py`
- Create: `agents/g6pd-bot/tests/test_web_search.py`

- [ ] **Step 1: Write failing tests**

Create `agents/g6pd-bot/tests/test_web_search.py`:

```python
import pytest
import sys
import os
from unittest.mock import MagicMock, patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from web_search import search_ingredient, search_unknowns


@patch("web_search.anthropic.Anthropic")
def test_search_ingredient_safe_result(mock_anthropic_class):
    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client

    # Simulate Claude returning a text response (no tool calls for safe ingredients)
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(type="text", text="Glycerin is a safe humectant with no known G6PD hemolytic risk.")
    ]
    mock_client.messages.create.return_value = mock_response

    result = search_ingredient("glycerin", api_key="test-key")

    assert result["ingredient"] == "glycerin"
    assert result["source"] == "web"
    assert "risk_assessment" in result
    assert result["risk_assessment"] is not None


@patch("web_search.anthropic.Anthropic")
def test_search_unknowns_respects_max_limit(mock_anthropic_class):
    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text="No known G6PD risk.")]
    mock_client.messages.create.return_value = mock_response

    unknowns = ["a", "b", "c", "d", "e", "f", "g"]  # 7 items
    results = search_unknowns(unknowns, api_key="test-key", max_results=5)

    assert len(results) == 5  # capped at max_results
    assert mock_client.messages.create.call_count == 5


def test_search_unknowns_empty_list():
    results = search_unknowns([], api_key="test-key")
    assert results == []
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
cd agents/g6pd-bot
python -m pytest tests/test_web_search.py -v 2>&1 | head -10
```

Expected: `ImportError: cannot import name 'search_ingredient' from 'web_search'`

- [ ] **Step 3: Create `agents/g6pd-bot/web_search.py`**

```python
import anthropic


_SEARCH_PROMPT = """\
Is "{ingredient}" a known trigger for G6PD deficiency (glucose-6-phosphate dehydrogenase deficiency)?
Could it cause hemolysis in a G6PD-deficient person?

Search for the most current medical information and answer concisely:
1. Is there any known G6PD hemolytic risk? (yes / no / uncertain)
2. What is the risk level if any? (high / medium / low / none)
3. Source or basis for your answer

Keep your answer under 100 words.
"""


def search_ingredient(ingredient: str, api_key: str) -> dict:
    """
    Use Claude with web_search tool to check a single unknown ingredient.
    Returns dict: {ingredient, risk_assessment, source}
    """
    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=512,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[
            {
                "role": "user",
                "content": _SEARCH_PROMPT.format(ingredient=ingredient),
            }
        ],
    )

    # Extract the final text response (after any tool use)
    risk_text = ""
    for block in response.content:
        if hasattr(block, "type") and block.type == "text":
            risk_text = block.text
            break

    return {
        "ingredient": ingredient,
        "risk_assessment": risk_text.strip() if risk_text else "No information found.",
        "source": "web",
    }


def search_unknowns(
    unknowns: list[str],
    api_key: str,
    max_results: int = 5,
) -> list[dict]:
    """
    Run web search for each unknown ingredient up to max_results.
    Returns list of {ingredient, risk_assessment, source} dicts.
    """
    if not unknowns:
        return []

    results = []
    for ingredient in unknowns[:max_results]:
        result = search_ingredient(ingredient, api_key=api_key)
        results.append(result)

    return results
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
cd agents/g6pd-bot
python -m pytest tests/test_web_search.py -v
```

Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agents/g6pd-bot/web_search.py agents/g6pd-bot/tests/test_web_search.py
git commit -m "feat(g6pd-bot): web search fallback for unknown ingredients"
```

---

## Task 6: `formatter.py` — Telegram Response Formatter

**Files:**
- Create: `agents/g6pd-bot/formatter.py`
- Create: `agents/g6pd-bot/tests/test_formatter.py`

- [ ] **Step 1: Write failing tests**

Create `agents/g6pd-bot/tests/test_formatter.py`:

```python
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from formatter import format_scan_result, RISK_EMOJI, CATEGORY_EMOJI


def test_risk_emoji_mapping():
    assert RISK_EMOJI["high"] == "🔴"
    assert RISK_EMOJI["medium"] == "🟡"
    assert RISK_EMOJI["low"] == "🟢"


def test_format_all_clear():
    scan = {
        "product_name": "Baby Lotion",
        "total_ingredients": 5,
        "matches": [],
        "unknowns": [],
        "clean": ["water", "zinc oxide", "shea butter", "glycerin", "vitamin e"],
    }
    result = format_scan_result(scan, web_results=[])
    assert "✅" in result
    assert "Baby Lotion" in result
    assert "no G6PD triggers" in result.lower()


def test_format_with_high_risk_match():
    scan = {
        "product_name": "Cooling Gel",
        "total_ingredients": 3,
        "matches": [
            {"ingredient": "Camphor", "matched_as": "camphor", "category": "cosmetics",
             "risk": "high", "notes": "Dangerous for infants transdermally"}
        ],
        "unknowns": [],
        "clean": ["water", "carbomer"],
    }
    result = format_scan_result(scan, web_results=[])
    assert "🔴" in result
    assert "Camphor" in result
    assert "HIGH RISK" in result.upper() or "high risk" in result.lower()


def test_format_with_web_results():
    scan = {
        "product_name": None,
        "total_ingredients": 2,
        "matches": [],
        "unknowns": ["lactobacillus rhamnosus"],
        "clean": ["inulin"],
    }
    web_results = [
        {"ingredient": "lactobacillus rhamnosus", "risk_assessment": "No known G6PD risk.", "source": "web"}
    ]
    result = format_scan_result(scan, web_results=web_results)
    assert "🌐" in result
    assert "lactobacillus rhamnosus" in result.lower()


def test_format_error_no_ingredients():
    scan = {"error": "no_ingredients_visible"}
    result = format_scan_result(scan, web_results=[])
    assert "couldn't read" in result.lower() or "no ingredient" in result.lower()


def test_format_error_not_product_label():
    scan = {"error": "not_a_product_label"}
    result = format_scan_result(scan, web_results=[])
    assert "product label" in result.lower()


def test_disclaimer_always_present():
    scan = {"product_name": "X", "total_ingredients": 0,
            "matches": [], "unknowns": [], "clean": []}
    result = format_scan_result(scan, web_results=[])
    assert "doctor" in result.lower() or "pharmacist" in result.lower()
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
cd agents/g6pd-bot
python -m pytest tests/test_formatter.py -v 2>&1 | head -10
```

Expected: `ImportError: cannot import name 'format_scan_result' from 'formatter'`

- [ ] **Step 3: Create `agents/g6pd-bot/formatter.py`**

```python
RISK_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}
CATEGORY_EMOJI = {
    "drugs": "💊",
    "foods": "🥦",
    "food_additives": "🧪",
    "cosmetics": "💄",
    "herbals": "🌿",
    "chemicals": "☣️",
}
RISK_LABEL = {"high": "HIGH RISK — DO NOT USE", "medium": "MEDIUM RISK — Consult doctor", "low": "LOW RISK — Use caution"}
DISCLAIMER = "\n⚠️ Reference tool only — always confirm with a doctor or pharmacist before use."


def format_scan_result(scan: dict, web_results: list[dict]) -> str:
    """Format scan result dict into a Telegram message string."""

    # Handle error responses
    if "error" in scan:
        error = scan["error"]
        if error == "no_ingredients_visible":
            return "⚠️ I couldn't read the ingredients clearly. Try a clearer, closer photo of the ingredients list."
        if error == "not_a_product_label":
            return "⚠️ This doesn't look like a product label. Please send a close-up photo of an ingredient list."
        return f"⚠️ Scan error: {error}. Please try again."

    product = scan.get("product_name") or "product"
    total = scan.get("total_ingredients", 0)
    matches = scan.get("matches", [])

    lines = [f"🔍 Scanned: *{product}* ({total} ingredient{'s' if total != 1 else ''})\n"]

    if not matches and not web_results:
        lines.append(f"✅ All clear — no G6PD triggers found.")
        lines.append(DISCLAIMER)
        return "\n".join(lines)

    # Group matches by risk level
    for risk_level in ["high", "medium", "low"]:
        level_matches = [m for m in matches if m.get("risk") == risk_level]
        if not level_matches:
            continue
        emoji = RISK_EMOJI[risk_level]
        label = RISK_LABEL[risk_level]
        lines.append(f"\n{emoji} *{label}*")
        for m in level_matches:
            cat_emoji = CATEGORY_EMOJI.get(m.get("category", ""), "•")
            lines.append(f"  {cat_emoji} {m['ingredient']}")
            if m.get("notes"):
                lines.append(f"     ↳ _{m['notes']}_")

    # Clean count
    clean_count = len(scan.get("clean", []))
    if clean_count > 0:
        lines.append(f"\n✅ {clean_count} other ingredient{'s' if clean_count != 1 else ''}: no triggers found")

    # Web search results
    if web_results:
        lines.append("\n🌐 *Web-searched (not in local database):*")
        for r in web_results:
            lines.append(f"  • *{r['ingredient']}* — {r['risk_assessment']}")

    # Unchecked unknowns (if web limit hit)
    unknowns = scan.get("unknowns", [])
    searched_names = {r["ingredient"] for r in web_results}
    unsearched = [u for u in unknowns if u not in searched_names]
    if unsearched:
        lines.append(f"\n⚠️ {len(unsearched)} ingredient(s) not checked — verify manually: {', '.join(unsearched)}")

    lines.append(DISCLAIMER)
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
cd agents/g6pd-bot
python -m pytest tests/test_formatter.py -v
```

Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agents/g6pd-bot/formatter.py agents/g6pd-bot/tests/test_formatter.py
git commit -m "feat(g6pd-bot): response formatter for Telegram messages"
```

---

## Task 7: `bot.py` — Telegram Polling Bot

**Files:**
- Create: `agents/g6pd-bot/bot.py`

- [ ] **Step 1: Create `agents/g6pd-bot/bot.py`**

```python
import json
import logging
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

import config
from checker import DB
from vision import scan_photo
from web_search import search_unknowns
from formatter import format_scan_result

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Pre-serialize DB for prompt injection (done once at startup)
DB_STR = json.dumps(DB)

WELCOME_MESSAGE = """\
👶 *G6PD Safety Scanner*

Send me a photo of any product label — medicine, food, cosmetic, supplement — \
and I'll check every ingredient for G6PD deficiency triggers.

I check against:
💊 Drugs & medications
🥦 Foods & legumes
🧪 Food additives & E-numbers
💄 Cosmetics & topical products
🌿 Herbal & traditional medicines
☣️ Household chemicals

Unknown ingredients get a live web search too.

Just send a photo to get started.
"""


def _is_allowed(user_id: int) -> bool:
    return user_id in config.ALLOWED_USER_IDS


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        return
    await update.message.reply_text(WELCOME_MESSAGE, parse_mode="Markdown")


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        return
    await update.message.reply_text(WELCOME_MESSAGE, parse_mode="Markdown")


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        return
    await update.message.reply_text(
        "📸 Send me a photo of a product label and I'll scan it for G6PD triggers."
    )


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        return

    await update.message.reply_text("🔍 Scanning... please wait.")

    try:
        # Download highest-resolution version of the photo
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()

        # Determine media type
        file_path = file.file_path or ""
        media_type = "image/png" if file_path.endswith(".png") else "image/jpeg"

        # Run vision scan
        scan_result = scan_photo(
            image_bytes=bytes(image_bytes),
            media_type=media_type,
            db_str=DB_STR,
            api_key=config.ANTHROPIC_API_KEY,
        )

        # Web search for unknowns
        web_results = []
        unknowns = scan_result.get("unknowns", [])
        if unknowns:
            web_results = search_unknowns(
                unknowns,
                api_key=config.ANTHROPIC_API_KEY,
                max_results=5,
            )

        # Format and send response
        message = format_scan_result(scan_result, web_results)
        await update.message.reply_text(message, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Scan failed: {e}", exc_info=True)
        await update.message.reply_text(
            "⚠️ Scan failed — something went wrong. Please try again with a clearer photo."
        )


def main() -> None:
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("G6PD Bot started. Polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run all existing tests — confirm nothing broken**

```bash
cd agents/g6pd-bot
python -m pytest tests/ -v
```

Expected: All tests PASS (bot.py has no unit tests — integration tested in Task 8)

- [ ] **Step 3: Commit**

```bash
git add agents/g6pd-bot/bot.py
git commit -m "feat(g6pd-bot): telegram polling bot with full scan pipeline"
```

---

## Task 8: Local Smoke Test

**Goal:** Verify the bot starts, connects to Telegram, and responds to `/start` before deploying.

- [ ] **Step 1: Run all unit tests one final time**

```bash
cd agents/g6pd-bot
python -m pytest tests/ -v --tb=short
```

Expected: All tests green.

- [ ] **Step 2: Start bot locally**

```bash
cd agents/g6pd-bot
python bot.py
```

Expected log output:
```
INFO - G6PD Bot started. Polling...
INFO - Application started
```

- [ ] **Step 3: Test /start in Telegram**

Open Telegram → find your bot by its username → send `/start`

Expected: Welcome message appears with emoji and bullet list.

- [ ] **Step 4: Test with a real product photo**

Take a photo of any baby product, medicine box, or food label. Send to the bot.

Expected:
- Bot replies "🔍 Scanning... please wait."
- Then returns formatted result with risk levels.

- [ ] **Step 5: Test with a non-label photo**

Send a random selfie or landscape photo.

Expected: "⚠️ This doesn't look like a product label..."

- [ ] **Step 6: Stop bot (Ctrl+C) after confirming it works**

---

## Task 9: Deploy to Railway

- [ ] **Step 1: Create Railway account and project**

1. Go to https://railway.app → sign up / log in with GitHub
2. Click **New Project** → **Deploy from GitHub repo**
3. Select the repo containing `agents/g6pd-bot/`
4. Railway detects the `Procfile` automatically

- [ ] **Step 2: Set root directory in Railway**

In Railway project settings → **Source** → set **Root Directory** to `agents/g6pd-bot`

- [ ] **Step 3: Set environment variables in Railway dashboard**

Go to **Variables** tab → add:

```
TELEGRAM_BOT_TOKEN = 8849643828:AAHPGbDeBj3za0yVobeYZwxKkLumcLA5mX0
ANTHROPIC_API_KEY  = <your anthropic key>
ALLOWED_USER_IDS   = 8671492802,8932283522
```

- [ ] **Step 4: Trigger deploy**

Railway auto-deploys on push. Push a small commit to trigger it:

```bash
git commit --allow-empty -m "chore: trigger railway deploy"
git push origin main
```

- [ ] **Step 5: Watch Railway build logs**

In Railway dashboard → **Deployments** → click the active deploy → watch logs.

Expected final log line:
```
INFO - G6PD Bot started. Polling...
```

- [ ] **Step 6: Verify in Telegram**

Send `/start` to the bot from your phone.

Expected: Welcome message. Bot is now live 24/7.

- [ ] **Step 7: Final commit — tag release**

```bash
git tag v1.0.0-g6pd-bot
git push origin v1.0.0-g6pd-bot
```

---

## Self-Review Checklist

- [x] **Spec coverage:**
  - Photo input → vision.py ✓
  - Local DB check → checker.py ✓
  - Web search fallback for unknowns → web_search.py ✓
  - Private whitelist access → bot.py `_is_allowed()` ✓
  - Always-on Railway deployment → Task 9 ✓
  - Prompt caching → vision.py `cache_control` ✓
  - All 6 trigger categories → g6pd_triggers.json ✓
  - Formatted Telegram response with emoji risk levels → formatter.py ✓
  - Max 5 web searches per scan → web_search.py `max_results=5` ✓
  - Error handling (blurry photo, non-label, API failure) → formatter.py + bot.py ✓

- [x] **No placeholders** — all steps have actual code

- [x] **Type consistency:**
  - `scan_photo()` returns `dict` — used as `scan_result` in bot.py ✓
  - `search_unknowns()` returns `list[dict]` — passed as `web_results` to `format_scan_result()` ✓
  - `format_scan_result(scan: dict, web_results: list[dict])` — matches all callers ✓
  - `lookup()` returns `dict | None` — not used directly in bot (Claude handles matching) ✓
  - `DB` loaded in `checker.py` and imported in `bot.py` ✓
