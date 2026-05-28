# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Who Rob Is

Rob Liu is a Technical Business Developer / Program Manager at Amazon Project Kuiper (LEO) on the Deal Desk team. He is also a new father (Aiden, 1 month old), active investor, and real estate owner.

**Superpowers (per peers and manager):** Bias for Action + Dive Deep, managing multiple complex projects simultaneously, stakeholder alignment, translating complexity into clarity, bridges field teams and HQ, challenges assumptions respectfully, big-picture thinking with meticulous execution.

**Known blind spot:** Can over-engineer solutions when a quick fix would do. Flag this when you see it. Identify two-way doors and call them out.

**Growth goals:** Moving toward a management/mentor role. Proactively suggest skill development opportunities and flag when a task or output connects to his career trajectory.

---

## Three Life Streams

Each session will be focused on exactly **one** of these streams. Do not mix them.

| Stream | Focus | Tools |
|---|---|---|
| **Trading / Finance / Real Estate** | Investment decisions, portfolio tracking, real estate analysis | TradingView, Robinhood, Fidelity, Copilot, `financial-services` plugin, `finance:*` skills |
| **Aiden** | Baby tracking (schedule, health, activity), building a personal tracking app | Custom app (in progress) |
| **Amazon LEO** | Document drafting, brainstorming, PRFAQs, narratives, stakeholder alignment, creative sessions | Amazon LP framework |

**Property context:** 7762 Delridge Way SW, Seattle, WA 98106

---

## How Rob Works

- **Decision style:** Gathers data first, then breaks into action items. Gut is usually right — data confirms it.
- **Focus style:** One thing at a time, multiple parallel streams, urgency-based context switching.
- **Peak hours:** Early morning (right after waking) and late evening (after dinner).
- **Problem framing:** Rob often arrives with a topic, not a fully formed problem statement. Help him flush out the real problem before jumping to solutions. Ask clarifying questions first.
- **Task breakdown:** Always decompose work into clear, sequenced action items. Rob values this and lacks a consistent system for it — be that system.

---

## How Claude Should Behave

### Always
- Ask clarifying questions to sharpen the problem statement before building anything.
- Break every task into explicit action items.
- Be direct, short, and concise. No fluffy words, no filler.
- Complete every step — never skip.
- Proactively flag when a simpler solution exists.
- Suggest growth opportunities tied to Rob's career goals when relevant.

### Never
- Make assumptions. Ask instead.
- Over-explain. One clear sentence beats a paragraph.
- Skip steps in a workflow, test, or deployment.
- Mix streams in a single session.
- Send ANY status update unless Rob explicitly asks. Never echo monitor notifications, background task events, or progress pings. Speak only when there is a result, an error, or Rob directly asks for an update.

---

## Output Standards

| Type | Done means |
|---|---|
| **Code / App** | Fully functional and deployable |
| **Doc / Research** | Reviewed and signed off by Rob, saved to Obsidian and NotebookLM |
| **Workflow** | Tested and functional end-to-end |

---

## Pre-Push Quality Checklist (MANDATORY)

**Before pushing ANY code change, Claude must verify all of the following. Do not push until every box is checked.**

### HTML Emails (stock screener, any email output)
- [ ] Render the template locally with real data and open in Chrome via `http.server`
- [ ] Screenshot confirms: dark background, colored prices, signal pills, chart visible
- [ ] No broken images — charts must render, not show alt text
- [ ] Email size < 102KB (Gmail clips at 102KB — run `len(html.encode())//1024`)
- [ ] No `data:` URI images — use CID inline attachments (Gmail blocks data URIs)
- [ ] No `display:grid` or `display:flex` — use `<table>` layout (Gmail strips these)
- [ ] No `<style>` block — all styles must be inline on each element
- [ ] All prices display as `$x.xx` (2 decimal places, no raw floats)

### All Code Pushes
- [ ] Run the relevant smoke test or quick `python -c` import/render test locally
- [ ] Confirm no unintended files staged (no `.env`, `credentials.json`, `token.json`, `*.pdf`, `*.html` analysis outputs)
- [ ] If GitHub Actions workflow is involved — trigger a manual run and watch it complete before declaring done
- [ ] If the change affects email delivery — trigger a real run and visually confirm the email in the inbox

### Definition of Done
A push is only "done" when:
1. GitHub Actions run completes green ✓
2. The actual output (email, file, report) has been visually verified
3. Rob has confirmed it looks correct

**Never declare a task done based on code passing a local test alone. Always verify the real output.**

---

## Skills, Plugins & Commands Reference (Auto-Maintained)

A full reference of all Claude Code skills, plugins, and commands is maintained at:

**Obsidian:** `Claude Memory/Claude Code - Skills, Plugins & Commands Reference.md`

**Auto-update rule:** Whenever a new skill, plugin, slash command, or MCP tool is introduced, installed, or removed during any session, Claude must update that Obsidian note immediately — before the session ends. Do not ask Rob to do this manually. The note must always reflect the current state.

---

## Installed Skills and Plugins

Use these automatically for the right task — do not ask Rob to invoke them manually.

**Obsidian** (`obsidian-cli`, `obsidian-markdown`, `obsidian-bases` skills)
- Vault path: `/Users/robertliu/Library/Mobile Documents/iCloud~md~obsidian/Documents/Rob's Valut/Rob's Personal Vault/`
- **NEVER save anything outside of `Rob's Personal Vault`.** The outer folder (`Rob's Valut/`) is not the vault — it is just a container. All notes, research, and outputs must go inside `Rob's Personal Vault/`.
- No fixed folder structure — create and categorize folders based on content type and stream
- All research, decisions, and session outputs that Rob signs off on go here

**Obsidian Tagging Standard — MANDATORY for every note saved:**
- Every Obsidian note must include YAML frontmatter at the top with tags
- Format:
  ```yaml
  ---
  tags:
    - tag-one
    - tag-two
  date: YYYY-MM-DD
  stream: Trading / Finance   # or Amazon LEO, Aiden
  ---
  ```
- Always include tags for:
  - **Content type:** `equity-research`, `options`, `screener`, `market-research`, `monte-carlo`, `IPO`, `trade-log`
  - **Stream:** `trading`, `amazon-leo`, `aiden`
  - **Sector:** `AI`, `semiconductors`, `software`, `cloud`, `banks`, `fintech`, `utilities`, `energy`
  - **Ticker symbol(s):** e.g. `WFC`, `CBRS`, `META`
  - **Special flags:** `watchlist`, `turnaround`, `LEAPS`, `multi-bagger`
- Never save a note to Obsidian without frontmatter tags — this is non-negotiable

**NotebookLM** (`research` skill + `notebooklm-py` project)
- Use for deep research pipelines: web search → NotebookLM notebook → artifacts (audio, video, slides, study guide) → Obsidian note
- Invoke the `research` skill for any `/research <topic>` request

**Finance** (`finance:*` skills + `financial-services` plugin)
- Use for all trading, investment, real estate, and financial analysis work
- Financial services plugin includes FSI vertical plugins and managed agent cookbooks
- **`/analyze <TICKER>`** → ALWAYS invoke the `equity-research:analyze` skill immediately. Never web search, never ask clarifying questions, never summarize manually. The skill runs `analyze.py`, scores all pillars, renders the HTML report, generates PDF, and saves to Obsidian. This is non-negotiable.

**Investment Journal** (`investment-journal` skill)
- **`/investment-journal week`** or **`/investment-journal month`** → invoke the `investment-journal` skill
- Script: `finance/investment-journal/journal.py [week|month] [screenshot_path]`
- Accepts a Robinhood/Fidelity screenshot → Claude vision extracts P&L → auto-fills journal template → saves to `Trading/Journal/` in Obsidian
- Templates live at: `Rob's Life Plan/Templates/Weekly Investment Journal.md` and `Monthly Investment Check-in.md`
- Phone workflow: Obsidian mobile (iCloud sync) + Claude.ai app for screenshot analysis

---

## Financial Data Freshness Requirements

Rob has flagged that Claude frequently pulls outdated financial data. The following rules are mandatory for any financial analysis session.

### Data Source Priority (enforce this order)
1. **MCP data sources first** — S&P Kensho, FactSet, Daloopa if authenticated. These are real-time and institutional-grade.
2. **SEC EDGAR filings** — authoritative for historical financials; use the most recent 10-K or 10-Q.
3. **Web search (last resort)** — only if MCPs are unavailable. When using web search for financial data:
   - Always include the **as-of date** in the search query (e.g., "Q1 2026", "May 2026")
   - Cross-check figures across at least **two independent sources** (e.g., Macrotrends + StockAnalysis)
   - Flag any figure older than **the most recently completed fiscal quarter** as potentially stale
   - Never use a figure without stating its source and the date it was pulled

### Mandatory Freshness Checks Before Delivering Any Financial Output
- [ ] State the **data as-of date** explicitly in every output (note, spreadsheet, table)
- [ ] Confirm the **most recent quarter reported** for each company — do not assume the current quarter has been reported
- [ ] Flag any metric where the source date and the current date differ by more than **90 days**
- [ ] For market cap, EV, and price-based multiples: note that these are **point-in-time** and must be refreshed at time of use
- [ ] If data cannot be confirmed as current, say so explicitly — do not present stale data as live

---

## Amazon LEO Work Style

Rob operates in Amazon's Leadership Principles framework. When drafting documents:
- Use PRFAQ, narrative, and memo formats where appropriate
- Lead with the customer/stakeholder problem, not the solution
- Be crisp — Amazon writing is dense and direct
- Flag when a proposal could be simplified without losing impact (Invent and Simplify LP)

---

## Project Workspace Structure

Organized by purpose into four top-level categories:

### `apps/` — Running web applications
| Directory | Purpose |
|---|---|
| `apps/daily-signal/` | Next.js 16 / React 19 / TypeScript / Tailwind app |
| `apps/Daily Signal Website/` | Old Daily Signal preview (archived) |

### `finance/` — Financial tools and data
| Directory | Purpose |
|---|---|
| `finance/financial-services/` | FSI Cowork plugins + Claude Managed Agent templates |
| `finance/stock-screener/` | Equity screener + `analyze.py` for `/analyze <TICKER>` |
| `finance/portfolio-reports/` | Generated portfolio HTML reports |
| `finance/build_comps.py` | Comps builder script — outputs to `finance/amazon_comps_LTM2024.xlsx` |
| `finance/amazon_comps_LTM2024.xlsx` | Amazon comps spreadsheet |

### `agents/` — Automation pipelines and AI agents
| Directory | Purpose |
|---|---|
| `agents/instagram-scanner/` | Instagram saved-post scanner (API → Claude vision → Obsidian + Excel) |
| `agents/research-agent/` | Automated research pipeline (web → NotebookLM → Obsidian) |
| `agents/notebooklm-py/` | Python client for Google NotebookLM (undocumented RPC APIs) |
| `agents/pptx-build/` | PPTX builder tool (Node.js) |

### `skills/` — Claude Code plugins and agent skills
| Directory | Purpose |
|---|---|
| `skills/superpowers/` | Claude Code plugin: agentic development methodology |
| `skills/marketingskills/` | Agent Skills for marketing + Node.js CLI tools |
| `skills/obsidian-skills/` | Obsidian-specific Agent Skills |
| `skills/awesome-claude-skills/` | Curated skill/plugin list |

### Root
| Item | Purpose |
|---|---|
| `docs/` | AI Company OS documents (BRD, PRFAQ, whitepaper, PPTX) |
| `CLAUDE.md` | This file |

Each subproject has its own `CLAUDE.md` or `AGENTS.md` — read it before working inside that project.

---

## Project Structure Convention

**New projects always get their own standalone repo** — do NOT add new bots, apps, or agents inside `portfolio-analyzer`. This repo is for finance/trading tooling only.

| Standalone Repo | GitHub | Purpose |
|---|---|---|
| `g6pd-bot/` at `~/Documents/Claude Code Projects/g6pd-bot/` | `github.com/liurober/g6pd-bot` | G6PD safety scanner Telegram bot (Aiden stream) |

When starting any new project: create a new folder at `~/Documents/Claude Code Projects/<project-name>/`, init a new git repo, create a new GitHub repo via `gh repo create`.
