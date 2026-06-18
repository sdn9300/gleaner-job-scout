# IMPLEMENTATION_PLAN.md — Gleaner
**Multi-Board Job Scraper | Sprint Build 1**
Version: 1.0 | Last Updated: 2026-06-14

---

## How to Use This Document

This is the build-order companion to `ARCHITECTURE.md` and `PROBLEM_STATEMENT.md`. Where the architecture doc explains *why* and the problem statement defines *done*, this document is the *how, in what order, with what commands*.

Each phase contains:
- **Goal** — what exists at the end of this phase that didn't exist before
- **Pre-flight** — what must be true before starting
- **Cline prompt(s)** — the exact prompt(s) to give Cline, in plan mode
- **Manual verification** — commands to run and what success looks like
- **Checkpoint** — the go/no-go gate before moving to the next phase
- **Time budget** — allocated minutes (cumulative against the 120-minute clock)
- **Rollback** — what to do if this phase fails

Follow phases in order. Do not start Phase N+1 until Phase N's checkpoint passes or you've deliberately invoked its rollback/pivot.

---

## Phase Index

| Phase | Title | Time Budget | Cumulative |
|---|---|---|---|
| 0 | Environment & Scaffold | 0:00–15:00 | 15 min |
| 1 | Naukri Adapter (HTML) | 15:00–35:00 | 35 min |
| — | Break | 35:00–37:00 | 37 min |
| 2 | RemoteOK Adapter (API) | 37:00–50:00 | 50 min |
| 3A | Wellfound Adapter (Firecrawl) | 50:00–65:00 | 65 min |
| 3B | Indeed Adapter (Firecrawl Stealth) | 65:00–80:00 | 80 min |
| 4 | Filters Module | 80:00–87:00 | 87 min |
| 5 | Writers Module | 87:00–95:00 | 95 min |
| 6 | Pipeline Integration | 95:00–100:00 | 100 min |
| 7 | Polish, Push & Demo | 100:00–120:00 | 120 min |

---

## Phase 0 — Environment & Scaffold

**Goal:** A correctly structured, importable Python package exists. No scraping logic yet.

**Time Budget:** 0:00–15:00 (15 minutes)

### Pre-flight Checklist

```
[ ] Python 3.10+ installed: python --version
[ ] pip available: pip --version
[ ] VS Code + Cline extension installed and configured
[ ] GitHub CLI authenticated: gh auth status
[ ] Firecrawl API key obtained (firecrawl.dev → dashboard → API key)
[ ] Google Cloud service account created and JSON key downloaded
      (see Appendix A for one-time setup steps)
[ ] Target Google Sheet created and shared with service account email
[ ] Indeed Publisher ID registered (optional but recommended)
      Register at: https://ads.indeed.com/jobroll/xmlfeed
[ ] Screen recorder running (for Phase 7 demo clip)
```

### Step 0.1 — Create Project Directory

```bash
mkdir gleaner && cd gleaner
git init
```

### Step 0.2 — Cline Prompt (Plan Mode)

Use plan mode. Read the diff before approving every file.

```
Create a Python project structure:

- gleaner.py — entry point with argparse for
  --role, --location, --limit, --output, --sheet, --boards

- boards/ package with __init__.py, base.py
  (abstract BoardAdapter with fetch(role, location) -> list[dict],
  a `name` property derived from class name, and a
  _validate_schema(job: dict) -> dict helper that enforces
  required fields {source, title, company, location, link} and
  defaults optional fields {posted_at: '', description: ''})
  plus four empty adapters: naukri.py, remoteok.py, wellfound.py, indeed.py
  — each with a class stub inheriting BoardAdapter

- filters.py with three empty function stubs:
  dedupe(jobs), filter_by_role(jobs, role), filter_by_location(jobs, location)

- writers.py with two empty function stubs:
  write_csv(jobs, path), write_to_sheet(jobs, sheet_url)
  and a CANONICAL_FIELDS list constant:
  ["source", "title", "company", "location", "link", "posted_at", "description"]

- config.yaml with default boards list, limits, and logging config

- requirements.txt — requests, beautifulsoup4, lxml, pyyaml,
  python-dotenv, gspread, google-auth, firecrawl-py

- .env.example documenting FIRECRAWL_API_KEY,
  GOOGLE_SERVICE_ACCOUNT_JSON, INDEED_PUBLISHER_ID

- .gitignore — exclude .env, *.csv, __pycache__/, *.pyc,
  credentials/, *.json (except package.json if relevant — exclude
  service account and credential JSON specifically)

- README.md with project title and placeholder sections
  (Overview, Setup, Usage, Architecture, Boards, Limitations)

- selectors.md — placeholder for Naukri CSS selectors with a
  "Last verified:" date field

- tests/ directory (empty, with __init__.py)

Do not implement adapter logic, filter logic, or writer logic yet.
Keep everything minimal and importable.
```

### Step 0.3 — Manual Verification

```bash
# 1. All stubs importable
python -c "from boards.base import BoardAdapter; from boards.naukri import NaukriAdapter; from boards.remoteok import RemoteOKAdapter; from boards.wellfound import WellfoundAdapter; from boards.indeed import IndeedAdapter; print('OK')"

# 2. CLI help works
python gleaner.py --help

# 3. Abstract base class is actually abstract
python -c "
from boards.base import BoardAdapter
import inspect
assert inspect.isabstract(BoardAdapter)
assert 'fetch' in BoardAdapter.__abstractmethods__
print('Abstract contract OK')
"

# 4. Dependencies install cleanly
pip install -r requirements.txt
```

Expected `--help` output should show all six flags: `--role`, `--location`, `--limit`, `--output`, `--sheet`, `--boards`.

### Step 0.4 — Environment Setup

```bash
cp .env.example .env
# Edit .env and fill in:
#   FIRECRAWL_API_KEY=fc-...
#   GOOGLE_SERVICE_ACCOUNT_JSON=/absolute/path/to/credentials/service_account.json
#   INDEED_PUBLISHER_ID=...  (optional)
```

```bash
mkdir -p credentials
# Move downloaded service account JSON into credentials/
# Confirm credentials/ is in .gitignore
```

### Checkpoint 0

```
[ ] All five imports succeed (base + 4 adapters)
[ ] python gleaner.py --help shows all 6 flags
[ ] BoardAdapter is confirmed abstract with fetch() as abstract method
[ ] pip install -r requirements.txt completes without error
[ ] .env exists and is populated (not committed)
[ ] git status shows .env as untracked
```

**If checkpoint fails:** Do not proceed. A broken scaffold compounds errors in every subsequent phase. Re-run the Cline prompt with corrections, or fix manually — this phase has no acceptable shortcuts.

---

## Phase 1 — Naukri Adapter (HTML Scraping)

**Goal:** `NaukriAdapter.fetch()` returns real, schema-valid job listings from Naukri.com.

**Time Budget:** 15:00–35:00 (20 minutes)

### Pre-flight

```
[ ] Phase 0 checkpoint passed
[ ] Browser open to Naukri.com, DevTools ready
[ ] selectors.md open for editing
```

### Step 1.1 — Inspect Naukri's HTML Structure (5 min)

Before writing any code, open `https://www.naukri.com/data-scientist-jobs-in-bangalore` in a browser and use DevTools to identify:

1. The job card container selector (repeats once per listing)
2. The title element selector within a card
3. The company name selector
4. The location selector
5. The link `<a href>` selector
6. The posted date selector (if visible)

**Record these in `selectors.md` immediately** with today's date as "Last verified."

```markdown
# selectors.md

## Naukri
Last verified: 2026-06-14

| Field | Selector | Notes |
|---|---|---|
| Job card container | `.jobTuple` or `.srp-jobtuple-wrapper` | Naukri changes this periodically — check both |
| Title | `.title` or `a.title` | |
| Company | `.subTitle` or `.comp-name` | |
| Location | `.locWdth` or `.ellipsis.fleft.locWdth` | |
| Link | `a.title[href]` | Usually absolute already, but verify |
| Posted date | `.fleft.postedDate` or `.job-post-day` | Often relative ("3 days ago") |

Fallback selectors (if primary fails):
| Field | Fallback |
|---|---|
| Title | `[data-id] .title` |
| Link | first `<a>` inside card container |
```

### Step 1.2 — Cline Prompt (Plan Mode)

```
Implement NaukriAdapter(BoardAdapter) in boards/naukri.py.

Requirements:
- _slugify(text) helper: lowercase, replace whitespace with hyphens
  ("Data Scientist" -> "data-scientist")
- _build_url(role, location): construct
  https://www.naukri.com/{role-slug}-jobs-in-{location-slug}
- fetch(role, location):
  - Build the URL
  - GET request with a realistic browser User-Agent header
  - If status_code != 200, raise RuntimeError with status code and URL
  - time.sleep(1) after the request
  - Parse with BeautifulSoup(response.text, 'lxml')
  - Select job cards using selectors from selectors.md
  - For each card, extract title, company, location, link, posted_at
  - Make link absolute: prepend "https://www.naukri.com" if it starts with "/"
  - Strip whitespace from all extracted text
  - Build a dict with source='naukri' plus extracted fields
  - Call self._validate_schema(job) on each dict; skip and log warning
    on ValueError
  - If 0 cards found, log a warning suggesting selectors.md may need
    updating, and return []
  - Return the list of validated dicts

Import logging and configure a module-level logger.
Use try/except around individual card parsing so one malformed card
doesn't abort the whole page.
```

### Step 1.3 — First Manual Test (Isolated Adapter)

Before running the full CLI, test the adapter directly:

```bash
python -c "
from boards.naukri import NaukriAdapter
import json
adapter = NaukriAdapter()
results = adapter.fetch('data scientist', 'bangalore')
print(f'Got {len(results)} results')
if results:
    print(json.dumps(results[0], indent=2))
"
```

### Step 1.4 — Diagnostic Checklist (If 0 Results)

```
1. Open the constructed URL in a real browser. Does it show listings?
   - If NO: URL pattern may be wrong. Check Naukri's current URL format manually.
   - If YES: selectors are likely stale. Re-run Step 1.1.

2. Check response.status_code manually:
   python -c "
   import requests
   r = requests.get('https://www.naukri.com/data-scientist-jobs-in-bangalore',
                     headers={'User-Agent': 'Mozilla/5.0'})
   print(r.status_code, len(r.text))
   "
   - 200 + long response: parsing issue (selectors)
   - 403/429: blocked — try different User-Agent, add delay, or pivot

3. If still failing after 10 minutes total on this adapter:
   INVOKE ROLLBACK (see below). Do not exceed the time budget.
```

### Step 1.5 — First End-to-End CLI Run

Once the adapter returns results in isolation, wire a minimal CLI test:

```bash
python gleaner.py --role "python developer" --location "Bangalore" --output jobs.csv --boards naukri
```

**Inspect `jobs.csv`** — open it as a spreadsheet, not in a text editor:

```
[ ] Are titles clean (no extra whitespace, no truncation artifacts)?
[ ] Is the link column showing full https:// URLs?
[ ] Any obviously duplicate rows (same company + title)?
[ ] Is company name populated for every row?
```

**Note issues but do not fix them now** — dedup and filtering happen in Phase 4.

### Checkpoint 1

```
[ ] NaukriAdapter().fetch(...) returns ≥1 result in isolation
[ ] All required schema fields populated for every row
[ ] All link values are absolute (start with https://)
[ ] selectors.md updated with today's date
[ ] CLI run with --boards naukri produces non-empty jobs.csv
```

### Rollback / Pivot for Phase 1

If Naukri returns 0 results after exhausting the diagnostic checklist (10 minutes max):

```python
# Pivot adapter: boards/naukri.py fallback to Hacker News "Who is Hiring"
# Implement as NaukriAdapter.fetch() fallback:
#   1. Search HN for the latest "Who is Hiring?" thread (algolia API:
#      https://hn.algolia.com/api/v1/search_by_date?query=Who%20is%20Hiring&tags=story)
#   2. Fetch top-level comments via HN API
#   3. Parse comments for role/location keyword matches
#   4. Map to canonical schema with source='naukri' (or rename to 'hn'
#      and document the substitution in README)
```

Document this pivot in the README's "Known Limitations" section if invoked. **Move to Phase 2 regardless of outcome** — do not let Naukri consume more than 20 minutes total.

---

## BREAK (35:00–37:00)

Stretch, water, bathroom. Two minutes. Set a timer.

---

## Phase 2 — RemoteOK Adapter (Public JSON API)

**Goal:** `RemoteOKAdapter.fetch()` returns real listings from RemoteOK's public API, filtered by role keyword.

**Time Budget:** 37:00–50:00 (13 minutes)

### Pre-flight

```
[ ] Phase 1 checkpoint passed (or pivot documented)
[ ] No additional setup required — RemoteOK API is unauthenticated
```

### Step 2.1 — Inspect the API Response Shape (2 min)

```bash
curl -s -A "Mozilla/5.0" https://remoteok.com/api | python -m json.tool | head -50
```

Confirm:
- Index `[0]` is a metadata/legal object (not a job)
- Index `[1]` onward are job objects with keys: `position`, `company`, `location`, `url`, `tags`, `date`, `description`

### Step 2.2 — Cline Prompt (Plan Mode)

```
Implement RemoteOKAdapter(BoardAdapter) in boards/remoteok.py.

Requirements:
- fetch(role, location):
  - GET https://remoteok.com/api with header
    {"User-Agent": "Mozilla/5.0 (compatible; GleanerBot/1.0)"}
  - If status_code != 200, log warning and return []
  - Parse JSON; skip index [0] (metadata blob)
  - For each remaining job:
    - keywords = role.lower().split()
    - position = job.get("position", "").lower()
    - tags = [t.lower() for t in job.get("tags", [])]
    - Keep the job if ANY keyword appears in position OR in any tag
      (substring match, not exact)
  - For each kept job, build canonical dict:
    - source = 'remoteok'
    - title = job['position']
    - company = job['company']
    - location = job.get('location') or 'Remote'
    - link = job['url']
    - posted_at = job.get('date', '')
    - description = strip HTML from job.get('description', '')
      using BeautifulSoup(desc, 'lxml').get_text()
  - Call self._validate_schema(job) on each dict; skip on ValueError
    with a warning log
  - Return the list

This is the simplest adapter — no rate limiting needed (single API call).
```

### Step 2.3 — Manual Test (Isolated Adapter)

```bash
python -c "
from boards.remoteok import RemoteOKAdapter
import json
adapter = RemoteOKAdapter()
results = adapter.fetch('python', 'remote')
print(f'Got {len(results)} results')
if results:
    print(json.dumps(results[0], indent=2))
    assert results[0]['source'] == 'remoteok'
    assert results[0]['location']  # never empty
    assert '<' not in results[0]['description']  # no HTML
    print('Schema checks passed')
"
```

### Step 2.4 — CLI Run with Both Boards

```bash
python gleaner.py --role "python developer" --location "Bangalore" --output jobs.csv --boards naukri,remoteok
```

```
[ ] jobs.csv now contains rows with source=naukri AND source=remoteok
[ ] RemoteOK rows have location='Remote' or a real location, never empty
[ ] RemoteOK descriptions contain no HTML tags
```

### Checkpoint 2

```
[ ] RemoteOKAdapter().fetch(...) returns ≥1 result
[ ] source='remoteok' on all returned dicts
[ ] location never empty (defaults to 'Remote')
[ ] description has no HTML tags
[ ] Combined CSV (naukri + remoteok) has rows from both sources
```

### Rollback / Pivot for Phase 2

RemoteOK is the most reliable board — a failure here is almost always a User-Agent or network issue, not a structural one.

```
IF curl returns non-JSON or empty:
  → Check network connectivity
  → Try without the User-Agent header (some networks strip custom headers)
  → If still failing after 5 minutes: skip RemoteOK, document in README,
    move to Phase 3A. Three boards is an acceptable minimum.
```

---

## Phase 3A — Wellfound Adapter (Firecrawl SDK)

**Goal:** `WellfoundAdapter.fetch()` returns real listings extracted via Firecrawl's structured extraction.

**Time Budget:** 50:00–65:00 (15 minutes)

### Pre-flight

```
[ ] Phase 2 checkpoint passed
[ ] FIRECRAWL_API_KEY set in .env
[ ] Firecrawl quota checked (firecrawl.dev dashboard) — confirm remaining credits
```

### Step 3A.1 — Verify Firecrawl Connectivity (2 min)

```bash
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
from firecrawl import FirecrawlApp
app = FirecrawlApp(api_key=os.environ['FIRECRAWL_API_KEY'])
result = app.scrape_url('https://example.com', params={'formats': ['markdown']})
print('Firecrawl connection OK' if result else 'Firecrawl returned empty')
"
```

If this fails, resolve Firecrawl auth before proceeding — Phase 3B depends on the same key.

### Step 3A.2 — Cline Prompt (Plan Mode)

```
Implement WellfoundAdapter(BoardAdapter) in boards/wellfound.py.

Requirements:
- __init__: load FIRECRAWL_API_KEY from environment via python-dotenv;
  raise EnvironmentError with a clear message if missing; instantiate
  FirecrawlApp(api_key=...)
- fetch(role, location):
  - Build URL: https://wellfound.com/jobs?role={role}&location={location}
    (URL-encode role and location with urllib.parse.quote_plus)
  - Call self.app.scrape_url(url, params={
        "formats": ["extract"],
        "extract": {
            "schema": {
                "type": "object",
                "properties": {
                    "jobs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "company": {"type": "string"},
                                "location": {"type": "string"},
                                "link": {"type": "string"}
                            },
                            "required": ["title", "company", "link"]
                        }
                    }
                }
            }
        }
    })
  - Extract result.get("extract", {}).get("jobs", [])
  - If empty, log warning "Wellfound returned 0 results. Possible
    quota exhaustion or no matches." and return []
  - For each job, build canonical dict with source='wellfound',
    defaulting location to 'Remote' if missing
  - Call self._validate_schema(job) on each dict, skip on ValueError
  - Return the list

Wrap the scrape_url call in try/except for any Firecrawl exception
(quota, timeout, etc.) — log warning and return [] rather than raising.
```

### Step 3A.3 — Manual Test (Isolated Adapter)

```bash
python -c "
from boards.wellfound import WellfoundAdapter
import json
adapter = WellfoundAdapter()
results = adapter.fetch('data scientist', 'remote')
print(f'Got {len(results)} results')
if results:
    print(json.dumps(results[0], indent=2))
    assert results[0]['source'] == 'wellfound'
    print('Schema check passed')
else:
    print('0 results — check Firecrawl quota or try a broader role')
"
```

### Step 3A.4 — CLI Run with Three Boards

```bash
python gleaner.py --role "data scientist" --location "Bangalore" --output jobs.csv --boards naukri,remoteok,wellfound
```

### Checkpoint 3A

```
[ ] WellfoundAdapter().fetch(...) returns ≥1 result, OR returns []
    with a clear warning log (acceptable if quota exhausted)
[ ] source='wellfound' on all returned dicts (when non-empty)
[ ] No unhandled exception even on quota error
```

### Rollback / Pivot for Phase 3A

```
IF Firecrawl quota exhausted OR Wellfound returns 0 after 2 tries:
  → Implement WeWorkRemotely RSS fallback inside WellfoundAdapter.fetch():

    import feedparser
    feed = feedparser.parse("https://weworkremotely.com/categories/remote-programming-jobs.rss")
    for entry in feed.entries:
        if any(kw in entry.title.lower() for kw in role.lower().split()):
            yield {
                "source": "wellfound",  # or rename to "wwr" + document
                "title": entry.title,
                "company": entry.get("author", "Unknown"),
                "location": "Remote",
                "link": entry.link,
                "posted_at": entry.get("published", ""),
                "description": entry.get("summary", "")
            }

  → Add feedparser to requirements.txt if using this pivot
  → Document substitution in README "Known Limitations"

DO NOT exceed 15 minutes on this phase. Move to Phase 3B regardless.
```

---

## Phase 3B — Indeed Adapter (Firecrawl Stealth)

**Goal:** `IndeedAdapter.fetch()` returns real listings from Indeed despite Cloudflare protection, via Firecrawl stealth + wait action.

**Time Budget:** 65:00–80:00 (15 minutes)

### Pre-flight

```
[ ] Phase 3A checkpoint passed (or pivot documented)
[ ] FIRECRAWL_API_KEY confirmed working (from Step 3A.1)
[ ] INDEED_PUBLISHER_ID set in .env (optional, for fallback)
```

### Step 3B.1 — Cline Prompt (Plan Mode)

```
Implement IndeedAdapter(BoardAdapter) in boards/indeed.py.

Requirements:
- __init__: load FIRECRAWL_API_KEY from environment via python-dotenv;
  raise EnvironmentError if missing; instantiate FirecrawlApp(api_key=...)
- _build_url(role, location): construct
  https://in.indeed.com/jobs?q={role}&l={location}
  (URL-encode with urllib.parse.quote_plus)
- _absolute_link(href): if href starts with "/", prepend
  "https://in.indeed.com"; otherwise return as-is
- fetch(role, location):
  - Build the URL
  - Call self.app.scrape_url(url, params={
        "formats": ["extract"],
        "actions": [{"type": "wait", "milliseconds": 2000}],
        "extract": {
            "schema": {
                "type": "object",
                "properties": {
                    "jobs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "company": {"type": "string"},
                                "location": {"type": "string"},
                                "link": {"type": "string"},
                                "posted_at": {"type": "string"},
                                "description": {"type": "string"}
                            },
                            "required": ["title", "company", "link"]
                        }
                    }
                }
            }
        }
    })
  - Extract result.get("extract", {}).get("jobs", [])
  - If empty, log warning "Indeed returned 0 results (Firecrawl). Consider
    Indeed Publisher API fallback (set INDEED_PUBLISHER_ID)." and return []
  - For each job:
    - Apply self._absolute_link() to the link field
    - Build canonical dict with source='indeed', default location to ''
      (will be filtered if doesn't match query — don't default to 'Remote'
      since Indeed India results are location-specific)
    - Call self._validate_schema(job), skip on ValueError
  - time.sleep(2) after the scrape_url call
  - Wrap entire Firecrawl call in try/except — on any exception,
    log warning with the exception message and return []
  - Return the list

Also add a separate method _fetch_via_publisher_api(role, location)
that is NOT called automatically — implement it as documented fallback:
  - Read INDEED_PUBLISHER_ID from environment; if missing, log warning
    and return []
  - GET http://api.indeed.com/ads/apisearch with params:
    publisher, q=role, l=location, format=json, v=2, limit=25, co=in
  - Map response.json()["results"] to canonical schema:
    source='indeed', title=jobtitle, company=company, location=city,
    link=url, posted_at=date, description=snippet
  - Add a code comment explaining this is the fallback path, activated
    manually if Firecrawl quota is exhausted (e.g., by calling this
    method instead of the Firecrawl path in fetch())
```

### Step 3B.2 — Manual Test (Isolated Adapter)

```bash
python -c "
from boards.indeed import IndeedAdapter
import json, time
adapter = IndeedAdapter()
start = time.time()
results = adapter.fetch('data scientist', 'bangalore')
elapsed = time.time() - start
print(f'Got {len(results)} results in {elapsed:.1f}s')
if results:
    print(json.dumps(results[0], indent=2))
    assert results[0]['source'] == 'indeed'
    assert results[0]['link'].startswith('https://')
    print('Schema check passed')
else:
    print('0 results — check Firecrawl quota, or try Publisher API fallback')
"
```

Expect 4–8 seconds elapsed (2s wait action + Firecrawl processing + 2s sleep).

### Step 3B.3 — CLI Run with All Four Boards

```bash
python gleaner.py --role "data scientist" --location "Bangalore" --output jobs.csv --boards naukri,remoteok,wellfound,indeed
```

### Checkpoint 3B

```
[ ] IndeedAdapter().fetch(...) returns ≥1 result, OR returns []
    with a clear warning (acceptable if quota exhausted or Cloudflare blocks)
[ ] All link values start with https:// (relative links converted)
[ ] source='indeed' on all returned dicts (when non-empty)
[ ] No unhandled exception even on Cloudflare block or quota error
[ ] _fetch_via_publisher_api method exists (even if not called by default)
```

### Rollback / Pivot for Phase 3B

```
IF Firecrawl quota exhausted on Indeed (shared quota with Wellfound —
   check this first if both 3A and 3B failed):
  → Activate _fetch_via_publisher_api() inside fetch():
      if INDEED_PUBLISHER_ID is set:
          return self._fetch_via_publisher_api(role, location)
      else:
          log warning, return []

IF Indeed returns 0 even with valid Firecrawl + 2s wait:
  → Try increasing wait to 4000ms (Cloudflare challenge may take longer)
  → Try www.indeed.com instead of in.indeed.com as a one-time test
  → If still 0 after 10 minutes total on this phase:
      ACCEPT 3 boards (naukri, remoteok, wellfound) as the demo baseline.
      Document Indeed as "implemented, pending Firecrawl quota" in README.
      Move to Phase 4. Do not exceed time budget.
```

**This phase has the highest variance.** Three working boards + Indeed implemented-but-quota-limited is a perfectly defensible Sprint 1 outcome. Do not sacrifice Phase 4–7 time trying to force Indeed past 80:00.

---

## Phase 4 — Filters Module

**Goal:** `filters.py` fully implemented and unit-tested. Running the full pipeline shows row count dropping at each stage.

**Time Budget:** 80:00–87:00 (7 minutes)

### Pre-flight

```
[ ] At least 2 of 4 adapters returning results (ideally 3-4)
[ ] Combined raw jobs.csv has been inspected manually (Phase 1.5)
```

### Step 4.1 — Cline Prompt (Plan Mode)

```
Implement the three functions in filters.py. All must be pure functions
(no mutation of input, no side effects, no I/O).

1. dedupe(jobs: list[dict]) -> list[dict]
   - Build a set of (company, title) keys, lowercased and stripped
   - Keep first occurrence of each key, in original order
   - Return a new list

2. filter_by_role(jobs: list[dict], role: str) -> list[dict]
   - Split role into lowercase keywords by whitespace
   - For each job, concatenate title.lower() + " " + description.lower()
   - Keep the job if ANY keyword appears as a substring in that
     concatenation
   - Return a new list

3. filter_by_location(jobs: list[dict], location: str) -> list[dict]
   - Lowercase the target location
   - For each job, lowercase job['location']
   - Keep the job if the target location is a substring of the job
     location, OR if the job location equals 'remote'
   - Return a new list

Add type hints and docstrings. Do not import anything beyond the
standard library.
```

### Step 4.2 — Unit Tests (Write Alongside)

```
Write tests/test_filters.py covering:
- dedupe: removes exact (company, title) duplicates, case-insensitive,
  does not mutate input
- filter_by_role: keeps title matches, keeps description matches,
  drops non-matches
- filter_by_location: keeps exact location matches (substring),
  keeps 'Remote' regardless of query, drops mismatches
```

```bash
pytest tests/test_filters.py -v
```

### Step 4.3 — Manual Verification with Real Data

```bash
python -c "
import csv
from filters import filter_by_role, filter_by_location, dedupe

with open('jobs.csv', encoding='utf-8-sig') as f:
    jobs = list(csv.DictReader(f))

print(f'Raw: {len(jobs)}')

step1 = filter_by_role(jobs, 'data scientist')
print(f'After role filter: {len(step1)}')

step2 = filter_by_location(step1, 'bangalore')
print(f'After location filter: {len(step2)}')

step3 = dedupe(step2)
print(f'After dedupe: {len(step3)}')
"
```

Each number should be ≤ the previous. Watch the row count drop and the quality go up.

### Checkpoint 4

```
[ ] pytest tests/test_filters.py passes all tests
[ ] Manual pipeline run shows monotonically decreasing (or equal) counts
[ ] dedupe does not raise on empty input: dedupe([]) == []
[ ] filter_by_role('') keywords edge case handled (empty role unlikely
    but shouldn't crash)
```

---

## Phase 5 — Writers Module

**Goal:** `write_csv` and `write_to_sheet` both implemented. CSV always works; Sheets works if credentials are correct.

**Time Budget:** 87:00–95:00 (8 minutes)

### Pre-flight

```
[ ] Phase 4 checkpoint passed
[ ] Google Sheet created and shared with service account email
    (verify in Sheet's Share dialog — service account email should
    have Editor access)
```

### Step 5.1 — Cline Prompt (Plan Mode)

```
Implement both functions in writers.py.

1. write_csv(jobs: list[dict], path: str) -> None
   - Use csv.DictWriter with fieldnames=CANONICAL_FIELDS,
     extrasaction='ignore'
   - Open file with encoding='utf-8-sig', newline=''
   - Write header row, then one row per job
   - For each job, fill missing fields with '' via job.get(field, '')
   - Print "Wrote {n} rows to {path}" after writing

2. write_to_sheet(jobs: list[dict], sheet_url: str) -> None
   - Read GOOGLE_SERVICE_ACCOUNT_JSON from environment; raise
     EnvironmentError with clear message if not set
   - Authenticate: gspread.service_account(filename=sa_path)
   - Open sheet: gc.open_by_url(sheet_url)
   - Get first worksheet: sheet.get_worksheet(0)
   - Clear the worksheet
   - Append CANONICAL_FIELDS as header row
   - Build rows as list of lists (one per job, fields in
     CANONICAL_FIELDS order, missing -> '')
   - append_rows(rows, value_input_option='USER_ENTERED') — single
     batch call, not a loop
   - Print "Wrote {n} rows to Google Sheet" after writing
   - Never print or log the service account path or its contents
```

### Step 5.2 — Unit Test for CSV Writer (Real I/O, Temp Files)

```
Write tests/test_writers.py covering write_csv:
- writes correct header (all CANONICAL_FIELDS present)
- missing optional fields become empty string, not 'None'
- file is readable back via csv.DictReader with utf-8-sig encoding

write_to_sheet is integration-tested manually (Step 5.4) — mocking
gspread for unit tests is optional and lower priority given time budget.
```

```bash
pytest tests/test_writers.py -v
```

### Step 5.3 — Manual Test: CSV Writer

```bash
python -c "
from writers import write_csv
test_jobs = [
    {'source': 'naukri', 'title': 'Data Scientist', 'company': 'Acme',
     'location': 'Bangalore', 'link': 'https://example.com/1'}
]
write_csv(test_jobs, 'test_output.csv')
"
cat test_output.csv
```

Confirm all 7 columns present, missing fields (`posted_at`, `description`) are empty strings.

### Step 5.4 — Manual Test: Google Sheets Writer

```bash
python -c "
from writers import write_to_sheet
test_jobs = [
    {'source': 'naukri', 'title': 'Data Scientist', 'company': 'Acme',
     'location': 'Bangalore', 'link': 'https://example.com/1'}
]
write_to_sheet(test_jobs, 'PASTE_YOUR_SHEET_URL_HERE')
"
```

Open the Sheet in a browser — confirm header row + 1 data row appear.

### Checkpoint 5

```
[ ] pytest tests/test_writers.py passes
[ ] write_csv produces a CSV with correct headers and empty-string
    defaults for missing optional fields
[ ] write_to_sheet successfully clears and populates the target Sheet
    (verified visually in browser)
[ ] Service account JSON path not printed anywhere in output
```

### Rollback / Pivot for Phase 5

```
IF write_to_sheet fails (auth error, sharing not configured, quota):
  → Log the specific gspread exception message
  → Common fixes:
      - Re-check Sheet is shared with the exact service account email
        (find it in the JSON key file: "client_email" field)
      - Confirm Sheets API + Drive API both enabled in Google Cloud Console
      - Confirm GOOGLE_SERVICE_ACCOUNT_JSON path in .env is absolute,
        not relative
  → If unresolved after 5 minutes:
      ACCEPT CSV-only output. Document in README:
      "Google Sheets output requires service account setup — see
      Appendix A. CSV output (jobs.csv) is the primary deliverable."
      Move to Phase 6. The CSV can be manually uploaded to Sheets later
      or shared as a public Gist.
```

---

## Phase 6 — Pipeline Integration

**Goal:** `gleaner.py` orchestrates all adapters, filters, and writers in one CLI command with per-adapter error isolation.

**Time Budget:** 95:00–100:00 (5 minutes)

### Pre-flight

```
[ ] Phases 1-5 checkpoints passed (with pivots documented as needed)
```

### Step 6.1 — Cline Prompt (Plan Mode)

```
Update gleaner.py to implement the full pipeline:

1. ADAPTER_REGISTRY: dict mapping board name strings to adapter classes
   {"naukri": NaukriAdapter, "remoteok": RemoteOKAdapter,
    "wellfound": WellfoundAdapter, "indeed": IndeedAdapter}

2. resolve_adapters(boards_arg: str) -> list[BoardAdapter]
   - If boards_arg == "all", instantiate all four
   - Otherwise split on comma, instantiate only named boards
   - Skip unknown board names with a warning log

3. fetch_all(adapters: list[BoardAdapter], role: str, location: str) -> list[dict]
   - For each adapter, call adapter.fetch(role, location) inside try/except
   - On EnvironmentError: log.error(f"{adapter.name} skipped: {e}")
   - On any other Exception: log.warning(f"{adapter.name} failed: {e}")
   - Log info: f"{adapter.name}: fetched {len(results)} listings" on success
   - Return the merged list across all adapters

4. pipeline(jobs: list[dict], role: str, location: str) -> list[dict]
   - Apply filter_by_role, then filter_by_location, then dedupe in that
     order
   - Log the count after each step:
     f"After role filter: {len(jobs)}"
     f"After location filter: {len(jobs)}"
     f"After dedupe: {len(jobs)}"

5. main():
   - parse_args() via argparse with all flags
   - load_dotenv()
   - configure logging per config.yaml (level=INFO, format string)
   - adapters = resolve_adapters(args.boards)
   - all_jobs = fetch_all(adapters, args.role, args.location)
   - clean = pipeline(all_jobs, args.role, args.location)
   - clean = clean[:args.limit]
   - write_csv(clean, args.output)  -- unconditional, no try/except
   - if args.sheet:
       try: write_to_sheet(clean, args.sheet)
       except Exception as e: log.warning(f"Google Sheets write failed: {e}")
   - print(f"Done. {len(clean)} jobs written to {args.output}")

if __name__ == "__main__": main()
```

### Step 6.2 — Full Pipeline Run (All Available Boards)

```bash
python gleaner.py \
  --role "data scientist" \
  --location "Bangalore" \
  --output jobs.csv \
  --sheet "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID" \
  --boards all
```

Expected console output pattern:
```
INFO naukri: fetched 18 listings
INFO remoteok: fetched 12 listings
INFO wellfound: fetched 9 listings
INFO indeed: fetched 14 listings
INFO After role filter: 47
INFO After location filter: 35
INFO After dedupe: 29
Wrote 29 rows to jobs.csv
Wrote 29 rows to Google Sheet
Done. 29 jobs written to jobs.csv
```

(Numbers are illustrative — actual counts depend on live data.)

### Step 6.3 — Verify ≥50 Rows Target

If the final count is below 50:

```bash
# Broaden the role term
python gleaner.py --role "developer" --location "Bangalore" --output jobs2.csv --boards all

# Or try a second location and merge
python gleaner.py --role "data scientist" --location "Remote" --output jobs3.csv --boards all
```

Merge CSVs if needed:
```bash
python -c "
import csv
all_rows = []
for f in ['jobs.csv', 'jobs2.csv']:
    with open(f, encoding='utf-8-sig') as fh:
        all_rows.extend(csv.DictReader(fh))
from filters import dedupe
merged = dedupe(all_rows)
from writers import write_csv
write_csv(merged, 'jobs_final.csv')
print(f'{len(merged)} total rows after merge + dedupe')
"
```

### Checkpoint 6

```
[ ] python gleaner.py --role ... --location ... --output jobs.csv
    --sheet ... --boards all completes without crashing
[ ] Console shows per-board fetch counts and per-filter-step counts
[ ] jobs.csv has ≥50 rows (or merge strategy applied to reach 50)
[ ] If --sheet provided, Google Sheet reflects the same data
[ ] At least one adapter failure (if any occurred) was logged as a
    WARNING, not a crash
```

---

## Phase 7 — Polish, Push & Demo

**Goal:** Public GitHub repo, public Google Sheet, and a 60–90 second demo clip — all four submission artifacts ready.

**Time Budget:** 100:00–120:00 (20 minutes)

### Step 7.1 — README Completion (5 min)

```
Update README.md with:
- Project title + one-line description
- Architecture summary (link to ARCHITECTURE.md if present, or inline
  ASCII diagram of the adapter pattern)
- Setup instructions:
  1. pip install -r requirements.txt
  2. cp .env.example .env and fill in values
  3. Google Cloud service account setup steps (Appendix A)
- Usage examples:
  python gleaner.py --role "data scientist" --location "Bangalore"
    --output jobs.csv --sheet <URL>
- Board overview table (the 4-board strategy matrix)
- Known Limitations section — document any pivots invoked during
  this build (e.g., "Indeed adapter implemented but Firecrawl quota
  limited live results; Publisher API fallback documented in code")
- Link to public Google Sheet
- Link to demo clip (add after recording)
```

### Step 7.2 — Security Audit (5 min) — MANDATORY GATE

**Do not skip. Do not rush. This is the one irreversible mistake.**

```bash
# 1. Confirm .env is ignored
git check-ignore -v .env
# Expected output: .gitignore:N:.env	.env

# 2. Confirm credentials directory is ignored
git check-ignore -v credentials/service_account.json
# Expected output should show a matching .gitignore rule

# 3. Confirm neither appears in git status as staged
git status
# .env and credentials/*.json should be absent or listed as "untracked
# and ignored" — NOT in "Changes to be committed"

# 4. Search for hardcoded secrets
grep -rn "FIRECRAWL_API_KEY\s*=\s*['\"]" --include="*.py" .
grep -rn "fc-" --include="*.py" .
grep -rn "GOOGLE_SERVICE_ACCOUNT" --include="*.py" . | grep -v "os.environ\|os.getenv"
# All three should return NO matches

# 5. Confirm .env.example contains no real values
cat .env.example
# Should show empty values or placeholders only
```

```
[ ] git check-ignore confirms .env is ignored
[ ] git check-ignore confirms credentials/ is ignored
[ ] git status shows clean working tree (no secrets staged)
[ ] grep finds zero hardcoded API keys
[ ] .env.example contains placeholders only
```

**If any check fails:** fix it now. Do not proceed to Step 7.3 until all five pass.

### Step 7.3 — Git Commit & GitHub Push (3 min)

```bash
git add .
git status   # final visual check — review the file list
git commit -m "Sprint 1 — The Gleaner"

gh repo create gleaner --public --source=. --push
```

Verify:
```bash
# Open in browser (incognito, to confirm public access)
gh repo view --web
```

```
[ ] Repo is public and loads without authentication
[ ] .env is NOT visible in the repo file listing
[ ] credentials/ directory is NOT visible (or only .gitkeep is)
[ ] All source files present: gleaner.py, boards/, filters.py,
    writers.py, requirements.txt, README.md, selectors.md
```

### Step 7.4 — Record Demo Clip (5 min)

**Script (60–90 seconds total):**

```
[0:00-0:10] Terminal visible. Brief verbal intro:
            "This is The Gleaner — scrapes 4 job boards into one
            filtered dataset."

[0:10-0:40] Run the command live:
            python gleaner.py --role "data scientist"
              --location "Bangalore" --output jobs.csv
              --sheet <URL> --boards all
            Let the console output scroll — per-board counts,
            filter steps, final summary.

[0:40-0:60] Switch to browser. Refresh the Google Sheet.
            Show 50+ rows populating/visible.

[0:60-0:80] Switch to GitHub. Show the repo — README, file structure.

[0:80-0:90] Closing line:
            "Sprint 1 of the AI Job Agent Cohort — repo and Sheet
            linked below. #Gleaner"
```

```
[ ] Clip is 60-90 seconds (trim if needed)
[ ] Terminal run, Sheet refresh, and repo are all visible
[ ] Audio (if any) is clear
```

### Step 7.5 — LinkedIn Post & Slack Submission (2 min)

Post structure (see MISSION_PLAN.md Section 11.3 for full guidance):
1. Hook line
2. What it does (2-3 lines)
3. Technical bullets (adapter pattern, 4 boards, filter pipeline)
4. One-line lesson per board
5. Teaser for Sprint 2 (Resume Shapeshifter)
6. Links in comments: repo + Sheet
7. Hashtags: `#Gleaner #Python #WebScraping #DataEngineering #AIEngineering #BuildInPublic`

Submit to cohort Slack:
```
[ ] Public GitHub repo URL
[ ] Public Google Sheet URL
[ ] LinkedIn post URL
[ ] Submitted before Monday 9 AM IST
```

### Checkpoint 7 (Final Sprint Checkpoint)

```
[ ] README.md complete with setup, usage, board overview, limitations
[ ] Security audit (Step 7.2) — all 5 checks passed
[ ] GitHub repo public, pushed, verified in incognito browser
[ ] Google Sheet public, ≥50 rows, verified in incognito browser
[ ] Demo clip recorded, 60-90 seconds, all 3 artifacts shown
[ ] LinkedIn post drafted/published
[ ] Slack submission with all 4 links
```

---

## Appendix A — One-Time Google Cloud Setup

Complete this **before** Phase 0 begins (not during the sprint).

```
1. Go to console.cloud.google.com → create new project (or use existing)

2. Enable APIs:
   - Google Sheets API
   - Google Drive API
   (APIs & Services → Library → search and enable each)

3. Create Service Account:
   - IAM & Admin → Service Accounts → Create Service Account
   - Name: "gleaner-sheets-writer" (or similar)
   - No roles needed at project level
   - Create Key → JSON → download

4. Note the service account email from the JSON file:
   "client_email": "gleaner-xxx@your-project.iam.gserviceaccount.com"

5. Create the target Google Sheet:
   - sheets.new in browser
   - Name it (e.g., "The Gleaner — Job Listings")
   - Share → add the service account email → Editor access
   - Copy the Sheet URL

6. Store the downloaded JSON:
   mkdir -p credentials
   mv ~/Downloads/your-project-xxxx.json credentials/service_account.json

7. Set in .env:
   GOOGLE_SERVICE_ACCOUNT_JSON=/absolute/path/to/gleaner/credentials/service_account.json
```

---

## Appendix B — Time Budget Contingency Table

If running behind schedule, this table shows the minimum viable cut for each phase and the time saved.

| Phase | Full Scope | Minimum Viable Cut | Time Saved |
|---|---|---|---|
| 1 (Naukri) | Live scrape + selectors.md | HN "Who is Hiring" pivot | ~10 min |
| 3A (Wellfound) | Firecrawl extraction | WeWorkRemotely RSS pivot | ~8 min |
| 3B (Indeed) | Firecrawl stealth + wait | Skip entirely, document as "implemented pending quota" | ~15 min |
| 5 (Sheets) | Live Sheet write | CSV-only, manual upload post-sprint | ~5 min |
| 7 (README) | Full documentation | Minimal README (title, setup, usage only) | ~3 min |

**Absolute floor for a demoable Sprint 1:** Phases 0, 2 (RemoteOK — most reliable), 4, 5 (CSV only), 6, 7 (minimal). This produces a working 1-2 board pipeline with clean CSV output, a public repo, and a short demo. Not ideal, but ships.

---

## Appendix C — Full Command Reference

```bash
# Setup
pip install -r requirements.txt
cp .env.example .env

# Test individual adapters
python -c "from boards.naukri import NaukriAdapter; print(NaukriAdapter().fetch('data scientist','bangalore'))"
python -c "from boards.remoteok import RemoteOKAdapter; print(RemoteOKAdapter().fetch('python','remote'))"
python -c "from boards.wellfound import WellfoundAdapter; print(WellfoundAdapter().fetch('data scientist','remote'))"
python -c "from boards.indeed import IndeedAdapter; print(IndeedAdapter().fetch('data scientist','bangalore'))"

# Run tests
pytest tests/ -v

# Full pipeline run
python gleaner.py --role "data scientist" --location "Bangalore" \
  --output jobs.csv --sheet "<SHEET_URL>" --boards all

# Security audit
git check-ignore -v .env
git check-ignore -v credentials/service_account.json
git status
grep -rn "fc-" --include="*.py" .

# Ship
git add . && git commit -m "Sprint 1 — The Gleaner"
gh repo create gleaner --public --source=. --push
```
