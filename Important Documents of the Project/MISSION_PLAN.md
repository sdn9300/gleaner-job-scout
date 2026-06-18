# MISSION_PLAN.md — The Gleaner
**Multi-Board Job Scraper | Sprint Build 1**
Version: 1.0 | Last Updated: 2026-06-14

---

## 1. Mission Statement

Build a production-quality, CLI-driven job intelligence pipeline that aggregates, cleans, and surfaces real job listings from four major boards into a single queryable dataset — demonstrating mastery of web scraping strategy (HTML, public API, JS-rendered, anti-bot), data pipeline engineering, and structured output writing, all within a 120-minute live sprint.

The Gleaner is not a toy scraper. It is the data-acquisition layer of a larger autonomous job application system. Every architectural decision made here — the abstract adapter interface, the canonical schema, the filter/dedupe pipeline — is made with downstream consumption in mind.

---

## 2. Strategic Context

### 2.1 Position in the CONDUCTOR Pipeline

The Gleaner is **Component 1** of the CONDUCTOR system — the entry point through which all job intelligence flows.

```
┌─────────────────────────────────────────────────────────────────┐
│                        CONDUCTOR PIPELINE                       │
│                                                                 │
│  [ Gleaner ] ──► [ Research Agent ] ──► [ Orchestrator ]      │
│       │                                        │                │
│  Raw job data                         Candidate Profile JSON    │
│  (jobs.csv / Sheet)                            │                │
│                                       ┌────────▼────────┐       │
│                                       │  AlignResume    │       │
│                                       │  Overture       │       │
│                                       │  Auto-Apply PDF │       │
│                                       │  Memory Module  │       │
│                                       └─────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

Without The Gleaner, the rest of CONDUCTOR has no jobs to act on. The quality of the data it produces — the cleanliness of titles, the accuracy of links, the completeness of descriptions — directly determines how well every downstream component performs.

This is not an isolated side project. It is the foundation.

### 2.2 Relationship to Existing Portfolio

| Project | Role | Relationship to Gleaner |
|---|---|---|
| **AlignResume** | AI resume optimizer | Downstream consumer — rewrites bullets for jobs Gleaner finds |
| **Future Fit** | Skill trend analytics | Sibling intelligence layer — Future Fit analyzes market trends; Gleaner finds live openings |
| **Overture** (planned) | Cold email bot | Downstream consumer — drafts outreach emails for companies in Gleaner output |
| **CONDUCTOR** (planned) | Full orchestration pipeline | Gleaner is its data-acquisition module |

### 2.3 Why Build This Now

The AI Job Agent Cohort provides a structured forcing function. Without it, The Gleaner risks being deprioritized behind Future Fit completions and Overture planning. The 120-minute sprint format imposes the right constraint: ship a working system, not a perfect one.

The timing is also correct sequentially. Future Fit's analysis layer is substantially built. The next logical gap in the portfolio is live data acquisition — the bridge between trend intelligence (what skills will matter) and real opportunity intelligence (which companies are hiring for them now).

---

## 3. Project Goals

### 3.1 Primary Goals (Must Achieve by Minute 120)

| Goal | Measurable Outcome |
|---|---|
| Scrape four boards | Naukri, RemoteOK, Wellfound, Indeed each returning ≥1 result |
| Clean pipeline | Filter + dedupe reduces raw row count by ≥10% |
| Public CSV | `jobs.csv` on disk with ≥50 rows and all 7 canonical fields |
| Public Google Sheet | Same rows, publicly viewable via anyone-with-link |
| Public GitHub repo | Full project pushed with README and `.gitignore` |
| Demo clip | 60–90 second terminal→Sheet→repo clip ready for LinkedIn |

### 3.2 Secondary Goals (This Week, Post-Sprint)

| Goal | Measurable Outcome |
|---|---|
| README fully documented | New contributor can run the scraper in <10 minutes |
| `selectors.md` maintained | Naukri CSS selectors documented with last-verified date |
| Indeed Publisher API fallback wired | Fallback path tested and documented |
| Unit test suite passing | `pytest` green on all HAR-00x tests |
| LinkedIn post live | Demo clip + repo URL posted with `#Gleaner` |

### 3.3 Stretch Goals (Sprint 2 and Beyond)

| Goal | Notes |
|---|---|
| `--boards` CLI flag | Let user specify which boards to include: `--boards naukri,remoteok` |
| Pagination support | Fetch beyond page 1 for Naukri and Indeed |
| LLM relevance classifier | One Claude call per row to score relevance 0–10 (mentioned in sprint PDF) |
| Incremental mode | `--since 24h` flag — only fetch listings posted in the last N hours |
| CONDUCTOR handoff contract | Define the JSON schema that Gleaner outputs to CONDUCTOR's Research Agent |
| Naukri multi-page scraping | Currently fetches page 1 only; extend to N pages via `--limit` awareness |

---

## 4. Scope Boundaries

### 4.1 In Scope

- Four board adapters: Naukri, RemoteOK, Wellfound, Indeed
- Canonical schema enforcement across all four adapters
- Three filter functions: `dedupe`, `filter_by_role`, `filter_by_location`
- Two writers: CSV (local) and Google Sheets (public)
- CLI interface with `--role`, `--location`, `--limit`, `--output`, `--sheet`
- Error handling and graceful adapter-level fallback
- Public GitHub repo with documentation
- LinkedIn demo artifact

### 4.2 Explicitly Out of Scope (Sprint 1)

- LinkedIn job board scraping (requires auth)
- Glassdoor scraping (heavily protected, separate sprint)
- Auto-application submission (that is Overture's job)
- Resume tailoring per listing (that is AlignResume's job)
- Persistent database storage (CSV is the output format for now)
- CONDUCTOR orchestration wiring (architectural sketch only)
- Full pagination across all boards

---

## 5. Architecture Decisions & Rationale

### 5.1 The Abstract Adapter Pattern

**Decision:** All board adapters implement a single abstract base class `BoardAdapter` with one required method: `fetch(role, location) -> list[dict]`.

**Rationale:**
The pipeline downstream — filters, writers, `gleaner.py` itself — must be completely board-agnostic. Each board has wildly different access patterns (HTML vs JSON API vs Firecrawl), authentication requirements (none vs API key), and rate limits. The adapter pattern isolates this complexity at the board layer. The pipeline never knows or cares which board it is talking to.

This is not over-engineering for a sprint. It is the correct pattern for a system that will grow. Adding a fifth board (Glassdoor, LinkedIn, AngelCo) means implementing one method. Without this pattern, adding a board means modifying `gleaner.py`, the filters, and the writers — a brittle and error-prone coupling.

**Precedent:** This same pattern — one interface, many implementations — is how production data ingestion systems (Fivetran, Airbyte) handle source diversity.

### 5.2 Four-Strategy Scraping Taxonomy

The four boards were chosen deliberately to demonstrate every major web data acquisition strategy:

```
Strategy         │ Board       │ Difficulty │ Key Lesson
─────────────────┼─────────────┼────────────┼──────────────────────────────────
Server HTML      │ Naukri      │ Medium     │ requests + BS4; selector fragility
Public JSON API  │ RemoteOK    │ Low        │ Always check for API first
JS-rendered      │ Wellfound   │ Medium     │ Firecrawl for headless rendering
Anti-bot + JS    │ Indeed      │ High       │ Firecrawl stealth; publisher API fallback
```

This taxonomy is a portfolio signal: you understand that "scraping" is not one thing. You pick the right tool per target, not the same hammer for every nail.

### 5.3 Canonical Schema as Contract

**Decision:** Every adapter must return the same seven-field schema regardless of what the source provides.

**Rationale:** Without schema enforcement, the filter and writer layers would need defensive checks for every possible field combination from every board. With it, they assume the contract and trust it. This is the same reason REST APIs have documented response schemas and GraphQL has types — the consumer must be able to rely on the shape of the data.

Missing optional fields (`posted_at`, `description`) default to empty string `''`, never `None`. This prevents type errors in the CSV writer and Google Sheets API without requiring the consumer to check for nulls.

### 5.4 Filter Order: Role → Location → Dedupe

**Decision:** Filters applied in this order: `filter_by_role` → `filter_by_location` → `dedupe`.

**Rationale:**
- Role filter first: eliminates the largest class of noise (off-topic listings) before location filtering, reducing the set that location filter must process
- Location filter second: eliminates geographic mismatches from the role-filtered set
- Dedupe last: deduplicating before filtering would remove one occurrence of a job that would have been filtered anyway; deduplicating after ensures only relevant, location-matched jobs are counted against the dedupe key space

This order minimizes unnecessary computation and produces the cleanest final set.

### 5.5 Why Indeed Uses Firecrawl, Not requests

Plain `requests` to Indeed's job search returns one of three responses: HTTP 403, a Cloudflare JS challenge page, or an empty HTML shell with no job cards. Indeed has invested significantly in bot detection. The correct engineering response is not to try to defeat their protection with rotating proxies and user-agent spoofing — that arms race is expensive and fragile. The correct response is to use a service (Firecrawl) that handles browser fingerprinting, JS rendering, and challenge pages as a managed concern.

The Indeed Publisher API is the documented fallback: a free, rate-limited, official API that returns JSON. It requires a one-time publisher account registration. It is slower and more restrictive than Firecrawl but completely reliable.

---

## 6. Board-by-Board Technical Strategy

### 6.1 Naukri

| Property | Detail |
|---|---|
| Access method | `requests` + `BeautifulSoup` (server-rendered HTML) |
| URL pattern | `https://www.naukri.com/{role-slug}-jobs-in-{location-slug}` |
| Rate limit strategy | `time.sleep(1)` after each request |
| Fragility risk | **High** — CSS selectors change without notice |
| Mitigation | `selectors.md` with last-verified date; clear error on 0 results |
| Fallback | Pre-tested role/location combo; else HN "Who Is Hiring" RSS |
| Key challenge | Relative vs absolute links — must prepend domain |

### 6.2 RemoteOK

| Property | Detail |
|---|---|
| Access method | Public JSON API (`https://remoteok.com/api`) |
| Filter strategy | Client-side keyword match on `position` and `tags` |
| Rate limit strategy | None required; single API call returns all listings |
| Fragility risk | **Low** — JSON API contract is stable |
| Mitigation | Skip first item (metadata blob); strip HTML from `description` |
| Fallback | None needed — most reliable board |
| Key challenge | Location field often empty; default to `'Remote'` |

### 6.3 Wellfound

| Property | Detail |
|---|---|
| Access method | Firecrawl Python SDK (`scrape_url` with extract schema) |
| URL pattern | `https://wellfound.com/jobs?role={role}&location={location}` |
| Auth | `FIRECRAWL_API_KEY` from `.env` |
| Rate limit strategy | Firecrawl manages this internally |
| Fragility risk | **Medium** — dependent on Firecrawl quota and site structure |
| Mitigation | Graceful empty-list return on quota exhaustion |
| Fallback | WeWorkRemotely RSS feed |
| Key challenge | Firecrawl free tier quota; monitor usage |

### 6.4 Indeed

| Property | Detail |
|---|---|
| Access method | Firecrawl stealth mode with 2s wait action |
| URL pattern | `https://in.indeed.com/jobs?q={role}&l={location}` (India) |
| Auth | `FIRECRAWL_API_KEY` from `.env` (same key as Wellfound) |
| Rate limit strategy | `time.sleep(2)` after each Firecrawl call |
| Fragility risk | **High** — anti-bot measures change; JS render timing varies |
| Mitigation | Wait action; graceful fallback to Publisher API |
| Fallback | Indeed Publisher API (`http://api.indeed.com/ads/apisearch`); requires `INDEED_PUBLISHER_ID` in `.env` |
| Key challenge | Relative links (`/pagead/clk?...`) must be made absolute; sponsored listings may need filtering |

---

## 7. Data Quality Standards

The Gleaner's output is only as useful as its data quality. The following standards are non-negotiable for the Google Sheet to be credible as a public portfolio artifact.

### 7.1 Per-Field Quality Requirements

| Field | Quality Standard |
|---|---|
| `source` | Always one of: `naukri`, `remoteok`, `wellfound`, `indeed`. No empty values. |
| `title` | No HTML tags. No leading/trailing whitespace. No encoding artifacts (`&amp;`, `&#39;`). |
| `company` | No HTML tags. Non-empty. Title case preferred but not enforced. |
| `location` | Non-empty. Defaults to `'Remote'` when board provides null. No HTML. |
| `link` | Always absolute URL (`https://...`). Verified absolute in each adapter. |
| `posted_at` | ISO date string if available (`YYYY-MM-DD`), else empty string `''`. Never `None`. |
| `description` | HTML stripped. Truncated to 500 chars if very long (readability in Sheet). Never `None`. |

### 7.2 Pipeline-Level Quality Gates

```
Raw fetch output
  │
  ▼ filter_by_role()        ← Drops off-topic listings
  │
  ▼ filter_by_location()    ← Drops geographic mismatches (keeps 'Remote')
  │
  ▼ dedupe()                ← Drops (company, title) duplicates across boards
  │
  ▼ --limit cap             ← Applied to final clean set only
  │
  ▼ write_csv() / write_to_sheet()
```

**Minimum viable output:** ≥50 rows after all filters and dedupe. If below 50, broaden the role search term or add a second location.

### 7.3 Honest Data Limitations

The following limitations are real and must be documented in README.md:

- **No pagination:** Each board fetches page 1 only. True listing counts per board are higher.
- **Description completeness varies:** RemoteOK provides full descriptions; Naukri often provides snippets only; Indeed/Wellfound depend on Firecrawl extraction quality.
- **`posted_at` availability:** RemoteOK always provides this. Naukri provides it inconsistently. Wellfound and Indeed may not return it depending on Firecrawl's extraction.
- **Indeed sponsored listings:** Firecrawl may extract sponsored listings alongside organic. These are not filtered out in Sprint 1.
- **Wellfound/Indeed Firecrawl accuracy:** Structured extraction via LLM-based Firecrawl is accurate but not 100% reliable. Occasional missing fields or malformed links may occur.

---

## 8. Risk Register

### 8.1 Technical Risks

| Risk | Probability | Impact | Mitigation | Owner |
|---|---|---|---|---|
| Naukri CSS selectors broken | High (sites change weekly) | Medium | `selectors.md` with DevTools re-inspection playbook; HN fallback | HAR-003 |
| Indeed returns 0 results via Firecrawl | Medium | Medium | 2s wait action; Indeed Publisher API fallback documented | HAR-018 |
| Firecrawl free tier quota exhausted mid-sprint | Medium | Medium | Monitor quota before sprint; WeWorkRemotely RSS for Wellfound; Publisher API for Indeed | HAR-012 |
| Google Sheets service account auth failure | Low-Medium | Medium | CSV-only fallback; public Gist as alternative; rehearse auth setup before sprint | HAR-010 |
| RemoteOK API rate limit or downtime | Low | Low | No mitigation needed; most stable board; skip gracefully | HAR-004 |
| Cline agent loops on a file | Low | High | Start new task; narrow scope to one file; paste only the relevant adapter | Sprint execution |
| `.env` accidentally committed | Low | Critical | HAR-014 security gate; `git check-ignore` mandatory before push | HAR-014 |

### 8.2 Portfolio Risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Project perceived as "just a scraper" | Medium | Medium | Emphasize the adapter pattern, pipeline architecture, and CONDUCTOR positioning in README and LinkedIn post |
| Weak DS signal in portfolio | Medium | Medium | Future Fit provides the DS fundamentals; Gleaner is an AI engineering + pipeline project; these are complementary, not competing |
| Sprint not completed in 120 minutes | Low-Medium | Low | Pre-decided pivots (CSV-only, 3 boards instead of 4) maintain the demo even if Sheets or Indeed fail |
| LinkedIn post doesn't gain traction | Low | Low | Clip quality and `#Gleaner` hashtag are within control; reach is not |

### 8.3 Pre-Sprint Checklist (Run Before Minute 0)

```
[ ] Firecrawl API key obtained and quota checked (firecrawl.dev dashboard)
[ ] Google Cloud project created, Sheets API enabled
[ ] Service account JSON downloaded and stored outside project directory
[ ] Target Google Sheet created and shared with service account email
[ ] .env.example template ready to copy to .env
[ ] Python 3.10+ installed; pip available
[ ] Cline extension installed and configured in VS Code
[ ] GitHub CLI (`gh`) installed and authenticated
[ ] Screen recorder running (OBS or equivalent) — captures the demo clip
[ ] Indeed Publisher ID registered (takes ~2 minutes at indeed.com/publisher) — optional but have it ready
```

---

## 9. Sprint Execution Plan

### 9.1 The 120-Minute Clock

```
TIME        │ TARGET                                          │ EXIT CONDITION
────────────┼─────────────────────────────────────────────────┼──────────────────────────────
0:00–5:00   │ Environment check: .env, Firecrawl quota,       │ Terminal open, .env populated
            │ Google Sheet created and shared                  │
────────────┼─────────────────────────────────────────────────┼──────────────────────────────
5:00–15:00  │ HAR-001: Scaffold via Cline (plan mode)         │ `python gleaner.py --help`
            │ Read diff before approving every file            │ works; all stubs importable
────────────┼─────────────────────────────────────────────────┼──────────────────────────────
15:00–35:00 │ HAR-002: Naukri adapter                         │ Naukri CSV has ≥1 row;
            │ HAR-003: selectors.md                           │ titles clean, links absolute
────────────┼─────────────────────────────────────────────────┼──────────────────────────────
35:00–37:00 │ BREAK — stretch, water, bathroom               │ —
────────────┼─────────────────────────────────────────────────┼──────────────────────────────
37:00–50:00 │ HAR-004: RemoteOK adapter                       │ RemoteOK adds rows to CSV;
            │                                                 │ source='remoteok' verified
────────────┼─────────────────────────────────────────────────┼──────────────────────────────
50:00–65:00 │ HAR-005: Wellfound adapter (Firecrawl)          │ Wellfound adds rows; or
            │ → If quota hit: WeWorkRemotely RSS              │ fallback confirmed working
────────────┼─────────────────────────────────────────────────┼──────────────────────────────
65:00–80:00 │ HAR-018: Indeed adapter (Firecrawl stealth)     │ Indeed adds rows; or Publisher
            │ → If quota hit: Publisher API fallback          │ API fallback confirmed
────────────┼─────────────────────────────────────────────────┼──────────────────────────────
80:00–90:00 │ HAR-006/007/008: filters.py                     │ Combined run shows row count
            │ HAR-009/010: writers.py (CSV + Sheets)         │ drop after filter + dedupe
            │ HAR-011: Pipeline integration                   │
────────────┼─────────────────────────────────────────────────┼──────────────────────────────
90:00–100:00│ Full 4-board run + Google Sheet refresh         │ Sheet live with ≥50 rows;
            │                                                 │ all columns populated
────────────┼─────────────────────────────────────────────────┼──────────────────────────────
100:00–110:00│ HAR-013: README polish                         │ README has usage example,
             │ HAR-014: Security audit (mandatory gate)       │ selectors.md linked; .env
             │                                                │ confirmed absent from git
────────────┼─────────────────────────────────────────────────┼──────────────────────────────
110:00–115:00│ HAR-015: GitHub push                           │ Public repo URL live
────────────┼─────────────────────────────────────────────────┼──────────────────────────────
115:00–120:00│ HAR-016: Record demo clip (this video)         │ 60–90s clip captured
             │ HAR-017: Slack submission noted for Monday     │
```

### 9.2 If-Then Decision Tree (Live Debugging Protocol)

The following decisions are **pre-made**. Do not debug live. Pick the branch and keep moving.

```
IF Naukri returns 0 cards:
  → Try pre-tested combo: role="software engineer", location="Mumbai"
  → If still 0: swap NaukriAdapter for HN "Who Is Hiring" RSS adapter (pre-coded stub)
  → Continue with 3 remaining boards

IF Firecrawl quota exhausted (affects Wellfound OR Indeed):
  → Wellfound: swap to WeWorkRemotely RSS feed
  → Indeed: swap to Indeed Publisher API (INDEED_PUBLISHER_ID in .env)
  → If Publisher ID not available: skip Indeed, continue with 3 boards

IF Google Sheets write fails:
  → Log error, skip Sheets entirely
  → CSV is the deliverable; upload CSV to Google Drive manually
  → Post CSV link in Slack instead of Sheet link
  → Sheets becomes a post-sprint 10-minute extension

IF Cline enters an infinite loop:
  → Kill the task immediately
  → Open new Cline task
  → Paste ONLY the one file being worked on
  → Narrow the prompt to a single function

IF total rows after filters < 50:
  → Run a second query with a broader role: "developer" instead of "python developer"
  → Merge both CSVs before writing to Sheet
```

---

## 10. Post-Sprint Roadmap

### 10.1 This Week (By Monday 9 AM IST)

- Complete badge submission: repo URL + Sheet URL + LinkedIn post URL → cohort Slack
- Write unit test suite (`pytest tests/`) for all filter functions and both writers
- Verify `selectors.md` reflects current Naukri selectors
- Add Indeed Publisher API as a tested fallback, not just a documented one

### 10.2 Sprint 2 — The Resume Shapeshifter

As outlined in the cohort PDF: take the JDs harvested here and have Claude rewrite the resume to match each one. This is the direct bridge between Gleaner output and AlignResume's functionality. The Gleaner's `jobs.csv` becomes the input; Sprint 2 produces a tailored resume per JD.

This is also the first time the two existing portfolio projects (AlignResume + Gleaner) become directly connected in a live pipeline demonstration.

### 10.3 CONDUCTOR Integration (Medium-Term)

The Gleaner's role in CONDUCTOR requires defining a formal handoff contract:

```json
// Proposed CONDUCTOR input schema from Gleaner
{
  "run_id": "uuid",
  "timestamp": "2026-06-14T10:00:00Z",
  "query": { "role": "data scientist", "location": "bangalore" },
  "stats": {
    "raw_fetched": 180,
    "after_role_filter": 140,
    "after_location_filter": 95,
    "after_dedupe": 78,
    "final": 78
  },
  "jobs": [
    {
      "source": "naukri",
      "title": "Senior Data Scientist",
      "company": "PhonePe",
      "location": "Bangalore",
      "link": "https://www.naukri.com/...",
      "posted_at": "2026-06-13",
      "description": "...",
      "relevance_score": null  // populated by Research Agent in Sprint 3+
    }
  ]
}
```

This JSON contract should be defined now (even if CONDUCTOR is not yet built) so that future integration is a schema match, not a refactor.

### 10.4 Planned Enhancements (Backlog)

| Enhancement | Value | Effort | Priority |
|---|---|---|---|
| `--boards` flag to select boards | Flexibility | Small | High |
| Naukri pagination (pages 2–N) | More listings | Medium | High |
| LLM relevance classifier per row | Quality signal | Medium | Medium |
| Incremental mode (`--since 24h`) | Reduce duplicate runs | Medium | Medium |
| LinkedIn scraper | High-value board | Large | Low (auth friction) |
| Glassdoor scraper | Salary + review data | Large | Low (heavy bot protection) |
| Persistent SQLite storage | Deduplication across runs | Medium | Medium |
| `--format json` output option | CONDUCTOR compatibility | Small | High |

---

## 11. Portfolio Positioning

### 11.1 What This Project Demonstrates

**AI Engineering skills:**
- Multi-strategy data acquisition (HTML, API, Firecrawl/stealth) — demonstrates knowing when to use which tool
- Abstract adapter design pattern — demonstrates production-grade software design thinking
- Pipeline architecture with graceful fallback — demonstrates resilience engineering
- Firecrawl SDK integration — demonstrates working with modern AI-adjacent infrastructure

**Data Engineering skills:**
- ETL pipeline: extract (four adapters) → transform (filter/dedupe) → load (CSV/Sheets)
- Schema design and enforcement across heterogeneous sources
- Data quality standards and honest documentation of limitations

**Software Engineering skills:**
- Abstract base class design
- CLI design with `argparse`
- `python-dotenv` for secrets management
- `gspread` for Google Sheets API
- Defensive coding (try/except per adapter, graceful fallback)

### 11.2 How to Talk About This Project

**In a resume bullet (Data Engineer / AI Engineer roles):**
> Built a CLI-driven multi-board job scraper (Naukri, RemoteOK, Wellfound, Indeed) using an adapter design pattern across three web acquisition strategies — HTML scraping, public JSON API, and Firecrawl stealth rendering — with a filter/dedupe pipeline writing 50+ clean listings to CSV and Google Sheets per run.

**In a resume bullet (Data Scientist / Analyst roles):**
> Engineered a job market data acquisition pipeline aggregating real-time listings across four platforms, producing a clean, deduplicated dataset that feeds downstream skill-trend analysis and resume optimization workflows.

**In an interview (system design question):**
> "I built The Gleaner as the data ingestion layer of a larger autonomous job application pipeline. The core design decision was an abstract adapter interface — `BoardAdapter.fetch(role, location) → list[dict]` — that isolates each board's quirks from the downstream pipeline. This means the filter logic, dedupe logic, and writers are completely board-agnostic. Adding a fifth board is one new Python file. I also discovered that scraping strategy isn't one-size-fits-all: Naukri is friendly HTML, RemoteOK has a public API, and Indeed actively resists scraping — each requires a different tool."

### 11.3 LinkedIn Post Strategy

**Hook options (A/B test):**
- Option A: "I built a bot that scrapes 4 job boards simultaneously. Here's what I learned."
- Option B: "4 job boards. 1 script. 50+ real listings in 2 minutes. Here's how The Gleaner works."
- Option C: "I automated the most annoying part of job hunting. Live demo in the clip below."

**Post structure:**
1. Hook (1 line)
2. What it does (2–3 lines, non-technical)
3. What I built under the hood (3–4 bullet points, technical but readable)
4. Key learning from each board (4 quick lines — one per board)
5. What's next (Resume Shapeshifter / CONDUCTOR teaser)
6. CTA: "Repo + live Google Sheet in the comments."

**Hashtags:** `#Gleaner` `#Python` `#WebScraping` `#DataEngineering` `#AIEngineering` `#BuildInPublic` `#JobSearch`

---

## 12. Success Criteria

### 12.1 Sprint Success (Minute 120)

| Criterion | Target | Verification |
|---|---|---|
| Boards functional | ≥3 of 4 returning results | Console log per-board count |
| Row count | ≥50 after filter + dedupe | Final summary line in terminal |
| Google Sheet | Live, publicly viewable, ≥50 rows | Open in incognito browser |
| GitHub repo | Public, all files present, .env absent | Open repo in incognito browser |
| Demo clip | 60–90 seconds, all three artifacts shown | Play back the recording |

### 12.2 Post-Sprint Success (End of Week)

| Criterion | Target | Verification |
|---|---|---|
| Badge submitted | Slack submission confirmed | Cohort Slack thread |
| Unit tests | `pytest` green on all filter and writer tests | CI or local run |
| LinkedIn post | Live with demo clip | Post URL |
| README complete | New contributor setup in <10 minutes | Walk through README cold |

### 12.3 Long-Term Success (CONDUCTOR Integration)

| Criterion | Target | Verification |
|---|---|---|
| Gleaner feeds Resume Shapeshifter | Sprint 2 uses `jobs.csv` as input | Sprint 2 demo |
| CONDUCTOR handoff contract defined | JSON schema documented and versioned | `CONDUCTOR_CONTRACT.md` |
| Gleaner cited in portfolio narrative | Resume and LinkedIn mention CONDUCTOR pipeline | Application materials |

---

## 13. Constraints & Guardrails

### 13.1 Hard Constraints

- `.env` must never be committed to git. No exceptions. HAR-014 is a mandatory gate.
- The Google Sheet must be public (anyone-with-link). Private Sheets cannot be demoed.
- The demo clip must be recorded as part of the sprint session, not re-recorded later.
- Service account JSON credentials must never appear in terminal output, logs, or README.
- The canonical schema is frozen for Sprint 1. No new fields without updating all adapters, filters, and writers.

### 13.2 Quality Guardrails

- No adapter may return `None` values in required fields. Empty string `''` is the minimum.
- No adapter may silently swallow errors. Errors must be logged as `WARNING` at minimum.
- The `dedupe` function must not mutate its input list. Caller code depends on this.
- `--limit` applies to the final cleaned set, never to per-adapter raw counts.
- HTML must be stripped from all text fields before writing to CSV or Sheets.

### 13.3 Time Guardrails

- If a single adapter takes more than 15 minutes to implement: stop, note the blocker, move to the next adapter, return if time allows.
- If the full pipeline integration (HAR-011) is not working by minute 90: fall back to writing the CSV from whichever adapters are working and skip the Google Sheets write.
- Do not attempt to debug Indeed's Firecrawl integration for more than 10 minutes. Take the fallback.

---

## 14. Definitions

| Term | Definition |
|---|---|
| **Board adapter** | A concrete implementation of `BoardAdapter` for one job site |
| **Canonical schema** | The seven-field dict format all adapters must return |
| **Dedupe** | Removal of rows sharing the same `(company.lower(), title.lower())` pair |
| **Stealth mode** | Firecrawl's bot-detection bypass capability using browser fingerprinting |
| **Publisher API** | Indeed's official, rate-limited developer API (free tier) |
| **CONDUCTOR** | The planned multi-agent orchestration pipeline of which Gleaner is the data layer |
| **Handoff contract** | The JSON schema defining what Gleaner outputs for downstream CONDUCTOR components |
| **Sprint 1** | This 120-minute build session; output is The Gleaner v1.0 |
| **Sprint 2** | The Resume Shapeshifter — uses Gleaner output to tailor resumes per JD |
