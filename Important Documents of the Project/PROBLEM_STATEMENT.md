# PROBLEM_STATEMENT.md — The Gleaner
**Multi-Board Job Scraper | Sprint Build 1**
Version: 1.1 | Last Updated: 2026-06-14

---

## Project Overview

The Gleaner is a CLI-driven, multi-board job scraping system that pulls listings from four sources — Naukri (HTML), RemoteOK (Public API), Wellfound (Firecrawl), and Indeed (Firecrawl + stealth) — filters and deduplicates them, and writes the output to both a local CSV and a public Google Sheet.

**Deliverables:**
- Public GitHub repo: `gleaner/`
- CLI: `python gleaner.py --role "..." --location "..." → jobs.csv`
- Public Google Sheet: 50+ filtered, deduplicated rows
- 60–90 second LinkedIn demo clip

**Architecture Pattern:** One abstract `BoardAdapter` base class → four concrete adapters → shared filter/dedupe pipeline → two writers (CSV + Google Sheets).

---

## Phase Map

```
Phase 0  │ Scaffold & Architecture Setup
Phase 1  │ Board Adapter — Naukri (HTML Scraping)
Phase 2  │ Board Adapter — RemoteOK (Public JSON API)
Phase 3A │ Board Adapter — Wellfound (Firecrawl SDK)
Phase 3B │ Board Adapter — Indeed (Firecrawl + Stealth)
Phase 4  │ Filter & Deduplication Engine
Phase 5  │ Writers — CSV + Google Sheets
Phase 6  │ CLI Integration & Full Pipeline Run
Phase 7  │ Polish, GitHub Push & Demo
```

---

## Canonical Job Schema

Every adapter must return `list[dict]` conforming to this schema. No exceptions.

| Field | Type | Required | Notes |
|---|---|---|---|
| `source` | str | ✅ | `'naukri'` / `'remoteok'` / `'wellfound'` / `'indeed'` |
| `title` | str | ✅ | Clean job title, no HTML |
| `company` | str | ✅ | Company name |
| `location` | str | ✅ | City/region string or `'Remote'` |
| `link` | str | ✅ | Absolute URL to the job posting |
| `posted_at` | str | ❌ | ISO date string if available, else `''` |
| `description` | str | ❌ | Plain text snippet if available, else `''` |

---

## Phase 0 — Scaffold & Architecture Setup

**Objective:** Generate the full project skeleton in one Cline prompt. No adapter logic yet. The structure must be correct before any implementation begins.

---

### HAR-001 — Project Scaffold

**Type:** Setup
**Effort:** Small

**Problem Statement:**
The project needs a clean, importable Python package structure before any scraping logic is written. Mixing scaffold and implementation in the same step causes structural debt that is hard to undo.

**Acceptance Criteria:**
- [ ] `gleaner.py` exists at project root with `argparse` wired for `--role`, `--location`, `--limit` (default: 100), `--output` (default: `jobs.csv`), `--sheet` (optional Google Sheet URL)
- [ ] `boards/` directory exists as a Python package with `__init__.py`
- [ ] `boards/base.py` contains an abstract `BoardAdapter(ABC)` class with abstract method `fetch(self, role: str, location: str) -> list[dict]`
- [ ] Four empty adapter stubs exist: `boards/naukri.py`, `boards/remoteok.py`, `boards/wellfound.py`, `boards/indeed.py` — each imports `BoardAdapter` and has a `pass`-level class body
- [ ] `writers.py` exists with two empty function stubs: `write_csv(jobs, path)` and `write_to_sheet(jobs, sheet_url)`
- [ ] `filters.py` exists with three empty function stubs: `dedupe(jobs)`, `filter_by_role(jobs, role)`, `filter_by_location(jobs, location)`
- [ ] `requirements.txt` contains: `requests`, `beautifulsoup4`, `lxml`, `pyyaml`, `python-dotenv`, `gspread`, `google-auth`, `firecrawl-py`
- [ ] `.env.example` documents all required env vars: `FIRECRAWL_API_KEY`, `GOOGLE_SERVICE_ACCOUNT_JSON`
- [ ] `.gitignore` includes: `.env`, `*.csv`, `__pycache__/`, `*.pyc`, `credentials.json`, `service_account.json`
- [ ] `README.md` exists with project title and placeholder sections

**Definition of Done:**
- `python -c "from boards.base import BoardAdapter"` runs without error
- `python gleaner.py --help` prints usage with all four flags
- Git `status` shows all files tracked except `.env` and `*.csv`

**Unit Tests:**
```python
# test_scaffold.py
import importlib, inspect, abc

def test_base_adapter_is_abstract():
    mod = importlib.import_module("boards.base")
    assert hasattr(mod, "BoardAdapter")
    assert inspect.isabstract(mod.BoardAdapter)

def test_fetch_is_abstract_method():
    from boards.base import BoardAdapter
    assert "fetch" in BoardAdapter.__abstractmethods__

def test_stub_adapters_importable():
    for name in ["boards.naukri", "boards.remoteok", "boards.wellfound", "boards.indeed"]:
        importlib.import_module(name)
```

---

## Phase 1 — Board Adapter: Naukri (HTML Scraping)

**Objective:** Implement the first working adapter using `requests` + `BeautifulSoup`. This is the template all other adapters follow structurally.

---

### HAR-002 — NaukriAdapter Implementation

**Type:** Feature
**Effort:** Medium

**Problem Statement:**
Naukri.com is server-rendered HTML, making it accessible via `requests`. The URL pattern is deterministic. The adapter must normalize role and location strings into URL slugs, fetch the page, parse job cards with correct CSS selectors, and return schema-compliant dicts. Rate-limit courtesy (1s sleep) is mandatory.

**Acceptance Criteria:**
- [ ] `NaukriAdapter` inherits from `BoardAdapter` and implements `fetch(role, location) -> list[dict]`
- [ ] URL constructed as: `https://www.naukri.com/{role-slug}-jobs-in-{location-slug}` (lowercase, spaces → hyphens)
- [ ] Request sent with a realistic `User-Agent` header to avoid 403s
- [ ] `time.sleep(1)` called after every HTTP request
- [ ] Non-200 response raises a descriptive `RuntimeError` (not a silent empty list)
- [ ] HTML parsed with `BeautifulSoup(response.text, 'lxml')`
- [ ] Each job card yields a dict conforming to the canonical schema with `source='naukri'`
- [ ] `link` field is always an absolute URL (prepend domain if relative)
- [ ] `description` field stripped of HTML tags if present
- [ ] Empty result set (0 cards) logs a clear warning but does not raise

**Definition of Done:**
- `python gleaner.py --role "data scientist" --location "Kolkata" --output jobs.csv` produces a non-empty CSV with `source=naukri` rows
- All returned dicts pass schema validation (required fields non-empty)
- No unhandled exceptions on 403 or 0-result pages

**Unit Tests:**
```python
# test_naukri.py
from boards.naukri import NaukriAdapter
from unittest.mock import patch, MagicMock

def test_slug_generation():
    adapter = NaukriAdapter()
    url = adapter._build_url("Data Scientist", "New Delhi")
    assert "data-scientist" in url
    assert "new-delhi" in url

def test_non200_raises():
    adapter = NaukriAdapter()
    mock_resp = MagicMock(status_code=403)
    with patch("requests.get", return_value=mock_resp):
        try:
            adapter.fetch("data scientist", "bangalore")
            assert False, "Should have raised"
        except RuntimeError:
            pass

def test_schema_compliance():
    adapter = NaukriAdapter()
    # Inject mock HTML with known card structure
    # Verify returned dicts have all required keys
    required = {"source", "title", "company", "location", "link"}
    # ... (mock fetch and validate)
    pass
```

---

### HAR-003 — Selector Maintenance Document

**Type:** Documentation
**Effort:** Small

**Problem Statement:**
Naukri's CSS selectors change without notice. Without a documented selector file, fixing breakages requires re-inspecting DevTools from scratch — costly under time pressure.

**Acceptance Criteria:**
- [ ] `selectors.md` created at project root
- [ ] Documents the CSS selectors used to find: job card container, title, company, location, link, posted_at
- [ ] Includes the date selectors were last verified
- [ ] Includes fallback selectors (second-choice) for title and link if available

**Definition of Done:**
- `selectors.md` committed to repo
- NaukriAdapter references selector logic that matches the documented selectors

---

## Phase 2 — Board Adapter: RemoteOK (Public JSON API)

**Objective:** Implement the fastest adapter — a clean API call with JSON parsing. No HTML parsing. Demonstrates the principle: always check for an API before scraping HTML.

---

### HAR-004 — RemoteOKAdapter Implementation

**Type:** Feature
**Effort:** Small

**Problem Statement:**
RemoteOK exposes a public `/api` endpoint returning a JSON array. The first item is a metadata blob and must be skipped. Results must be filtered client-side by role keyword match (position or tags), since the endpoint returns all jobs. HTML in the `description` field must be stripped.

**Acceptance Criteria:**
- [ ] `RemoteOKAdapter` inherits from `BoardAdapter` and implements `fetch(role, location) -> list[dict]`
- [ ] Hits `https://remoteok.com/api` with a `User-Agent` header (RemoteOK blocks default Python UA)
- [ ] First item `[0]` always skipped (metadata blob)
- [ ] Role filter applied: only keep rows where `position` or any tag in `tags` contains the role keyword (case-insensitive substring match)
- [ ] Field mapping: `source='remoteok'`, `title=position`, `company=company`, `location=location or 'Remote'`, `link=url`, `posted_at=date`, `description=description` (HTML stripped)
- [ ] HTML stripped from description using `BeautifulSoup(desc, 'lxml').get_text()`
- [ ] Returns empty list (not error) if no role matches found

**Definition of Done:**
- `from boards.remoteok import RemoteOKAdapter; RemoteOKAdapter().fetch("python", "remote")` returns ≥1 result with correct schema
- `source` field equals `'remoteok'` on all returned dicts
- `location` field is never `None` or empty (defaults to `'Remote'`)

**Unit Tests:**
```python
# test_remoteok.py
from boards.remoteok import RemoteOKAdapter
from unittest.mock import patch
import json

MOCK_API_RESPONSE = [
    {"legal": "skip this"},  # metadata blob
    {
        "position": "Senior Python Developer",
        "company": "Acme Corp",
        "location": "",
        "url": "https://remoteok.com/jobs/123",
        "date": "2026-06-01",
        "description": "<p>Great role</p>",
        "tags": ["python", "django"]
    }
]

def test_skips_first_item():
    adapter = RemoteOKAdapter()
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = MOCK_API_RESPONSE
        mock_get.return_value.status_code = 200
        results = adapter.fetch("python", "remote")
    assert all(r.get("title") != "skip this" for r in results)

def test_location_defaults_to_remote():
    adapter = RemoteOKAdapter()
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = MOCK_API_RESPONSE
        mock_get.return_value.status_code = 200
        results = adapter.fetch("python", "remote")
    assert results[0]["location"] == "Remote"

def test_html_stripped_from_description():
    adapter = RemoteOKAdapter()
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = MOCK_API_RESPONSE
        mock_get.return_value.status_code = 200
        results = adapter.fetch("python", "remote")
    assert "<p>" not in results[0]["description"]
```

---

## Phase 3A — Board Adapter: Wellfound (Firecrawl SDK)

**Objective:** Implement the JS-rendered board adapter using Firecrawl. This demonstrates the principle: when `requests` sees an empty shell, delegate to a headless scraping service.

---

### HAR-005 — WellfoundAdapter Implementation

**Type:** Feature
**Effort:** Medium

**Problem Statement:**
Wellfound renders job listings via JavaScript. A plain `requests` call returns an empty shell with no card data. Firecrawl handles JS rendering and structured extraction. The adapter must read the API key from `.env`, construct the correct URL, invoke Firecrawl's `scrape_url` with an extract schema, and map the response to the canonical schema.

**Acceptance Criteria:**
- [ ] `WellfoundAdapter` inherits from `BoardAdapter` and implements `fetch(role, location) -> list[dict]`
- [ ] Reads `FIRECRAWL_API_KEY` from environment via `python-dotenv` — raises `EnvironmentError` if missing
- [ ] URL constructed as: `https://wellfound.com/jobs?role={role}&location={location}` (URL-encoded)
- [ ] Uses `firecrawl.FirecrawlApp.scrape_url()` with an extract schema requesting: `title`, `company`, `location`, `link` as a list
- [ ] Maps response to canonical schema with `source='wellfound'`
- [ ] If Firecrawl returns 0 results or quota error, logs warning and returns empty list (does not crash pipeline)
- [ ] Fallback documented in code comment: if quota exhausted → swap for WeWorkRemotely RSS feed

**Definition of Done:**
- With a valid `FIRECRAWL_API_KEY` in `.env`, adapter returns ≥1 result for a broad search term
- `EnvironmentError` raised immediately if key is missing (fail-fast)
- Pipeline continues gracefully if Wellfound returns 0 rows

**Unit Tests:**
```python
# test_wellfound.py
import os
from unittest.mock import patch, MagicMock

def test_raises_without_api_key():
    with patch.dict(os.environ, {}, clear=True):
        try:
            from boards.wellfound import WellfoundAdapter
            WellfoundAdapter()
            assert False, "Should raise EnvironmentError"
        except (EnvironmentError, KeyError):
            pass

def test_schema_compliance_on_valid_response():
    mock_result = {
        "extract": {
            "jobs": [
                {"title": "ML Engineer", "company": "StartupX",
                 "location": "Remote", "link": "https://wellfound.com/jobs/1"}
            ]
        }
    }
    with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test-key"}):
        with patch("firecrawl.FirecrawlApp.scrape_url", return_value=mock_result):
            from boards.wellfound import WellfoundAdapter
            adapter = WellfoundAdapter()
            results = adapter.fetch("ml engineer", "remote")
    assert results[0]["source"] == "wellfound"
    assert results[0]["title"] == "ML Engineer"
```

---

## Phase 3B — Board Adapter: Indeed (Firecrawl + Stealth)

**Objective:** Implement the Indeed adapter. Indeed is simultaneously JS-rendered and aggressively anti-bot, making it the most technically challenging board. The lesson it teaches: when a site actively resists scraping, use a service built to handle bot detection rather than fighting it at the HTTP layer.

---

### HAR-018 — IndeedAdapter Implementation

**Type:** Feature
**Effort:** Medium-Large

**Problem Statement:**
Indeed is the highest-volume job board globally and a critical source for Data Science, ML, and AI roles. Unlike Naukri (server-rendered, friendly) or RemoteOK (public API), Indeed actively deploys Cloudflare bot protection and JavaScript-rendered content. Plain `requests` returns a challenge page, not job listings. Firecrawl's stealth mode handles both the JS rendering and the bot-detection layer. The adapter must construct the correct locale-aware URL, invoke Firecrawl with appropriate options, parse structured results, and map them to the canonical schema.

**Why Not Direct HTML Scraping:**
Indeed's Cloudflare protection returns HTTP 403 or a JS challenge to headless requests without browser fingerprinting. Attempting `requests.get("https://in.indeed.com/jobs?q=...")` will yield either a 403 or an empty body with a CAPTCHA page. Firecrawl's stealth rendering is the correct engineering path. If Firecrawl quota is exhausted, the fallback is the Indeed Publisher API (requires free registration at indeed.com/publisher).

**URL Strategy:**
- India-targeted: `https://in.indeed.com/jobs?q={role}&l={location}`
- Remote/global: `https://www.indeed.com/jobs?q={role}&remotejob=032b3046-06a3-4876-8dfd-474eb5e7ed11`
- URL-encode role and location (spaces → `+` or `%20`)

**Acceptance Criteria:**
- [ ] `IndeedAdapter` inherits from `BoardAdapter` and implements `fetch(role, location) -> list[dict]`
- [ ] Reads `FIRECRAWL_API_KEY` from environment via `python-dotenv` — raises `EnvironmentError` if missing
- [ ] Constructs URL: `https://in.indeed.com/jobs?q={role_encoded}&l={location_encoded}`
- [ ] Invokes `firecrawl.FirecrawlApp.scrape_url()` with `actions=[{"type": "wait", "milliseconds": 2000}]` to allow JS to fully render
- [ ] Uses Firecrawl extract schema to pull a list of: `title`, `company`, `location`, `link`, `posted_at`, `description`
- [ ] Maps response to canonical schema with `source='indeed'`
- [ ] `link` field normalized to absolute URL — Indeed internally uses relative paths like `/pagead/clk?...`; prepend `https://in.indeed.com` if relative
- [ ] `description` field stripped of HTML entities and tags
- [ ] If Firecrawl returns 0 results or a quota/auth error: logs a warning and returns empty list (does not crash pipeline)
- [ ] Fallback strategy documented in code comment: if Firecrawl exhausted → use Indeed Publisher API at `http://api.indeed.com/ads/apisearch`
- [ ] `time.sleep(2)` called after each Firecrawl call (stealth requests are slower; avoid hammering)

**Definition of Done:**
- With valid `FIRECRAWL_API_KEY`, `IndeedAdapter().fetch("data scientist", "Bangalore")` returns ≥1 result with correct schema
- All returned `link` values are absolute URLs starting with `https://`
- `source` field equals `'indeed'` on all returned dicts
- Pipeline continues gracefully (warning only) if Indeed returns 0 rows

**Indeed Publisher API Fallback (if Firecrawl quota exhausted):**
```python
# Fallback — requires free Indeed Publisher account
# Register at: https://ads.indeed.com/jobroll/xmlfeed
INDEED_PUBLISHER_ID = os.getenv("INDEED_PUBLISHER_ID")
params = {
    "publisher": INDEED_PUBLISHER_ID,
    "q": role,
    "l": location,
    "format": "json",
    "v": "2",
    "limit": 25
}
response = requests.get("http://api.indeed.com/ads/apisearch", params=params)
data = response.json()
# data["results"] → list of job dicts with jobtitle, company, city, url, date, snippet
```

**Unit Tests:**
```python
# test_indeed.py
import os
from unittest.mock import patch, MagicMock

def test_raises_without_api_key():
    with patch.dict(os.environ, {}, clear=True):
        try:
            from boards.indeed import IndeedAdapter
            IndeedAdapter()
            assert False, "Should raise EnvironmentError"
        except (EnvironmentError, KeyError):
            pass

def test_url_construction():
    with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test"}):
        from boards.indeed import IndeedAdapter
        adapter = IndeedAdapter()
        url = adapter._build_url("data scientist", "Bangalore")
    assert "in.indeed.com" in url
    assert "data" in url.lower()
    assert "bangalore" in url.lower() or "Bangalore" in url

def test_relative_links_made_absolute():
    with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test"}):
        from boards.indeed import IndeedAdapter
        adapter = IndeedAdapter()
    relative = "/pagead/clk?mo=r&ad=-6NYlbfkN0..."
    assert adapter._absolute_link(relative).startswith("https://in.indeed.com")

def test_schema_compliance():
    mock_result = {
        "extract": {
            "jobs": [
                {
                    "title": "Data Scientist",
                    "company": "Flipkart",
                    "location": "Bangalore",
                    "link": "https://in.indeed.com/jobs/view/12345",
                    "posted_at": "2026-06-10",
                    "description": "Looking for a Data Scientist..."
                }
            ]
        }
    }
    with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test"}):
        with patch("firecrawl.FirecrawlApp.scrape_url", return_value=mock_result):
            from boards.indeed import IndeedAdapter
            adapter = IndeedAdapter()
            results = adapter.fetch("data scientist", "bangalore")
    assert results[0]["source"] == "indeed"
    assert results[0]["title"] == "Data Scientist"
    assert results[0]["link"].startswith("https://")

def test_empty_result_does_not_raise():
    mock_result = {"extract": {"jobs": []}}
    with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test"}):
        with patch("firecrawl.FirecrawlApp.scrape_url", return_value=mock_result):
            from boards.indeed import IndeedAdapter
            adapter = IndeedAdapter()
            results = adapter.fetch("data scientist", "bangalore")
    assert results == []
```

**Known Challenges & Mitigations:**

| Challenge | Mitigation |
|---|---|
| Cloudflare bot detection | Firecrawl stealth mode handles this; do not use raw `requests` |
| Indeed paginates at 15 results/page | Firecrawl extract schema should capture all visible cards on first render; pagination is a stretch goal |
| Sponsored listings mixed with organic | Filter: drop rows where `link` contains `pagead/clk` and `sponsored=true` in URL params (stretch) |
| Location mismatch (India vs global) | Always use `in.indeed.com` for India-targeted searches; `www.indeed.com` for remote |
---

## Phase 4 — Filter & Deduplication Engine

**Objective:** Build the `filters.py` module that cleans the merged job list before writing. The filter stage is what separates a scraper from a pipeline.

---

### HAR-006 — Deduplication

**Type:** Feature
**Effort:** Small

**Problem Statement:**
The same job posting can appear on multiple boards. Without deduplication, the CSV/Sheet will have exact duplicates that erode user trust and inflate the row count with junk. The dedupe key is `(company, title)` normalized to lowercase and stripped.

**Acceptance Criteria:**
- [ ] `dedupe(jobs: list[dict]) -> list[dict]` implemented in `filters.py`
- [ ] Dedupe key: `(company.strip().lower(), title.strip().lower())`
- [ ] First occurrence of each key is kept; subsequent duplicates discarded
- [ ] Original list not mutated (return a new list)
- [ ] Row count after dedupe is ≤ row count before dedupe

**Definition of Done:**
- Input of 10 rows with 3 exact `(company, title)` duplicates → output of 7 rows
- Case-insensitive: `("OpenAI", "ML Engineer")` and `("openai", "ml engineer")` dedupe to one row

**Unit Tests:**
```python
# test_filters.py
from filters import dedupe

def test_removes_exact_duplicates():
    jobs = [
        {"title": "ML Engineer", "company": "OpenAI", "source": "naukri"},
        {"title": "ML Engineer", "company": "OpenAI", "source": "remoteok"},
        {"title": "Data Scientist", "company": "Google", "source": "naukri"},
    ]
    result = dedupe(jobs)
    assert len(result) == 2

def test_case_insensitive_dedupe():
    jobs = [
        {"title": "ML Engineer", "company": "OpenAI", "source": "naukri"},
        {"title": "ml engineer", "company": "openai", "source": "wellfound"},
    ]
    result = dedupe(jobs)
    assert len(result) == 1

def test_does_not_mutate_input():
    jobs = [{"title": "A", "company": "B", "source": "x"}]
    original_len = len(jobs)
    dedupe(jobs)
    assert len(jobs) == original_len
```

---

### HAR-007 — Role Filter

**Type:** Feature
**Effort:** Small

**Problem Statement:**
Board searches are keyword-based and imprecise. A search for "python developer" may return frontend roles or QA roles that mention Python tangentially. The role filter enforces that the search term appears in the job title or description.

**Acceptance Criteria:**
- [ ] `filter_by_role(jobs: list[dict], role: str) -> list[dict]` implemented in `filters.py`
- [ ] Splits `role` into individual keywords by whitespace
- [ ] Keeps rows where ANY keyword from `role` appears in `title` OR `description` (case-insensitive)
- [ ] Rows with empty `title` and empty `description` are dropped
- [ ] Returns new list; does not mutate input

**Definition of Done:**
- Role `"python developer"` discards rows where neither `title` nor `description` contain `python` or `developer`
- Rows where `title = "Frontend React Engineer"` and `description = ""` are dropped when role is `"python"`

**Unit Tests:**
```python
from filters import filter_by_role

def test_keeps_matching_title():
    jobs = [{"title": "Python Data Scientist", "description": "", "company": "X", "source": "y", "location": "z", "link": "l"}]
    assert len(filter_by_role(jobs, "python")) == 1

def test_drops_non_matching():
    jobs = [{"title": "Frontend React Developer", "description": "", "company": "X", "source": "y", "location": "z", "link": "l"}]
    assert len(filter_by_role(jobs, "python")) == 0

def test_matches_in_description():
    jobs = [{"title": "Engineer", "description": "Experience with Python required", "company": "X", "source": "y", "location": "z", "link": "l"}]
    assert len(filter_by_role(jobs, "python")) == 1
```

---

### HAR-008 — Location Filter

**Type:** Feature
**Effort:** Small

**Problem Statement:**
Location-parameterized searches still return off-target results (e.g., a Bangalore search returning San Francisco listings). Remote jobs are always valid regardless of location query.

**Acceptance Criteria:**
- [ ] `filter_by_location(jobs: list[dict], location: str) -> list[dict]` implemented in `filters.py`
- [ ] Keeps rows where `location` field contains the query location string (case-insensitive substring)
- [ ] Keeps rows where `location` field equals `'Remote'` (case-insensitive) regardless of query
- [ ] Drops all other rows
- [ ] Returns new list; does not mutate input

**Definition of Done:**
- Location query `"Bangalore"` keeps rows with `location = "Bangalore, Karnataka"` and `location = "Remote"`, drops `location = "San Francisco"`

**Unit Tests:**
```python
from filters import filter_by_location

def test_keeps_matching_location():
    jobs = [{"location": "Bangalore, Karnataka", "title": "X", "company": "Y", "source": "z", "link": "l"}]
    assert len(filter_by_location(jobs, "Bangalore")) == 1

def test_keeps_remote():
    jobs = [{"location": "Remote", "title": "X", "company": "Y", "source": "z", "link": "l"}]
    assert len(filter_by_location(jobs, "Bangalore")) == 1

def test_drops_wrong_location():
    jobs = [{"location": "San Francisco", "title": "X", "company": "Y", "source": "z", "link": "l"}]
    assert len(filter_by_location(jobs, "Bangalore")) == 0
```

---

## Phase 5 — Writers: CSV + Google Sheets

**Objective:** Implement both output writers in `writers.py`. The CSV writer is the fallback always-works path. The Google Sheets writer is the public showcase artifact.

---

### HAR-009 — CSV Writer

**Type:** Feature
**Effort:** Small

**Problem Statement:**
The CSV writer is the simplest, most reliable output. It must handle the full canonical schema, write headers on the first row, and work correctly even when optional fields (`posted_at`, `description`) are missing from some rows.

**Acceptance Criteria:**
- [ ] `write_csv(jobs: list[dict], path: str) -> None` implemented in `writers.py`
- [ ] Uses Python's built-in `csv.DictWriter`
- [ ] Column order: `source, title, company, location, link, posted_at, description`
- [ ] Missing fields default to empty string (not `None`, not `"None"`)
- [ ] Encodes output as UTF-8 with `encoding='utf-8-sig'` for Excel compatibility
- [ ] Prints confirmation: `Wrote {n} rows to {path}`

**Definition of Done:**
- Output CSV opens correctly in Excel/Google Sheets without encoding errors
- All 7 columns present in header even if all rows have empty `description`

**Unit Tests:**
```python
import csv, tempfile, os
from writers import write_csv

def test_writes_correct_columns():
    jobs = [{"source": "naukri", "title": "DS", "company": "X", "location": "Kolkata", "link": "http://x.com"}]
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name
    write_csv(jobs, path)
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        assert "description" in reader.fieldnames
        assert "posted_at" in reader.fieldnames

def test_missing_optional_fields_become_empty_string():
    jobs = [{"source": "remoteok", "title": "Eng", "company": "Y", "location": "Remote", "link": "http://y.com"}]
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name
    write_csv(jobs, path)
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["description"] == ""
    assert rows[0]["posted_at"] == ""
```

---

### HAR-010 — Google Sheets Writer

**Type:** Feature
**Effort:** Medium

**Problem Statement:**
The public Google Sheet is the headline deliverable — the artifact shared on LinkedIn. The writer must authenticate via service account (not OAuth), clear existing content, write headers, then write all rows. Credentials must never appear in logs or output.

**Acceptance Criteria:**
- [ ] `write_to_sheet(jobs: list[dict], sheet_url: str) -> None` implemented in `writers.py`
- [ ] Reads service account JSON path from `GOOGLE_SERVICE_ACCOUNT_JSON` env var
- [ ] Authenticates using `gspread.service_account(filename=...)`
- [ ] Opens the Sheet by URL using `gc.open_by_url(sheet_url)`
- [ ] Targets the first worksheet (`sheet.get_worksheet(0)`)
- [ ] Clears existing content with `worksheet.clear()`
- [ ] Writes header row: `['source', 'title', 'company', 'location', 'link', 'posted_at', 'description']`
- [ ] Writes all job rows in order
- [ ] Prints confirmation: `Wrote {n} rows to Google Sheet`
- [ ] Service account JSON path, key contents, and `.env` values never printed to stdout

**Definition of Done:**
- Running `write_to_sheet(jobs, sheet_url)` with valid credentials and a shared Sheet populates it with correct headers and ≥50 rows
- Re-running clears and repopulates (idempotent)
- `EnvironmentError` raised immediately if `GOOGLE_SERVICE_ACCOUNT_JSON` env var is missing

**Google Cloud Setup Steps (one-time):**
1. Create project in Google Cloud Console
2. Enable Google Sheets API + Google Drive API
3. Create Service Account → download JSON key → store path in `.env`
4. Share the target Sheet with the service account email (`*@*.iam.gserviceaccount.com`) as Editor
5. Confirm `.env` and the JSON key file are in `.gitignore`

---

## Phase 6 — CLI Integration & Full Pipeline Run

**Objective:** Wire all adapters, filters, and writers into `gleaner.py`. The pipeline must run end-to-end from a single CLI command.

---

### HAR-011 — Full Pipeline Integration

**Type:** Integration
**Effort:** Medium

**Problem Statement:**
Individual components work in isolation. This ticket connects them into a single, ordered pipeline with correct error propagation, progress logging, and graceful fallback when one adapter fails.

**Pipeline Order:**
```
parse CLI args
  → for each enabled adapter: adapter.fetch(role, location)
      adapters: NaukriAdapter, RemoteOKAdapter, WellfoundAdapter, IndeedAdapter
  → merge all results into one list
  → filter_by_role()
  → filter_by_location()
  → dedupe()
  → write_csv()
  → if --sheet provided: write_to_sheet()
  → print final summary
```

**Acceptance Criteria:**
- [ ] `gleaner.py` imports all four adapters, all three filter functions, and both writers
- [ ] Each adapter is called in try/except — failure of one adapter logs a warning and continues with results from other adapters
- [ ] Progress logged at each stage: fetch totals, post-filter count, post-dedupe count, final write count
- [ ] `--limit` arg caps total rows after dedupe (not before)
- [ ] `--sheet` arg is optional; omitting it skips `write_to_sheet` silently
- [ ] Final summary printed: `Done. {n} jobs written to {output_path}`

**Definition of Done:**
```bash
python gleaner.py \
  --role "data scientist" \
  --location "Bangalore" \
  --output jobs.csv \
  --sheet "https://docs.google.com/spreadsheets/d/..."
```
Produces: non-empty `jobs.csv` + populated Google Sheet + no unhandled exceptions.

**Integration Test:**
```python
# test_pipeline.py
import subprocess, csv, os

def test_end_to_end_csv():
    result = subprocess.run(
        ["python", "gleaner.py",
         "--role", "python developer",
         "--location", "bangalore",
         "--output", "test_output.csv"],
        capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0
    assert os.path.exists("test_output.csv")
    with open("test_output.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) >= 1
    assert all("title" in r and "link" in r for r in rows)
```

---

### HAR-012 — Fallback Handling & Break-Glass Pivots

**Type:** Resilience
**Effort:** Small

**Problem Statement:**
Live scraping is unreliable. Selectors break. APIs rate-limit. Firecrawl quotas exhaust. The pipeline must degrade gracefully with documented pivots, not crash.

**Acceptance Criteria:**
- [ ] Naukri 0-result → logs `WARNING: Naukri returned 0 results. Check selectors.md.`
- [ ] RemoteOK non-200 → logs `WARNING: RemoteOK API returned {status}. Skipping.`
- [ ] Wellfound/Firecrawl quota error → logs `WARNING: Firecrawl quota exhausted. Wellfound results skipped.`
- [ ] Indeed/Firecrawl quota or bot-block error → logs `WARNING: Indeed scrape failed ({reason}). Consider Indeed Publisher API fallback.`
- [ ] Google Sheets auth failure → logs `WARNING: Google Sheets write failed: {error}. CSV output still written.`
- [ ] Pipeline always writes CSV even if Sheets fails
- [ ] Fallback pivot documented in `README.md`:
  - Naukri 0 → swap role/location combo; else use HN "Who Is Hiring" RSS
  - Firecrawl exhausted (Wellfound) → swap to WeWorkRemotely RSS feed
  - Firecrawl exhausted (Indeed) → swap to Indeed Publisher API (`http://api.indeed.com/ads/apisearch`); requires free publisher account registration
  - Google service account fails → ship CSV only, post public Gist

**Definition of Done:**
- With `FIRECRAWL_API_KEY=invalid`, pipeline completes with a warning (not a crash) and writes CSV from Naukri + RemoteOK
- With `--sheet` pointing to an unshared Sheet, pipeline warns and still writes CSV

---

## Phase 7 — Polish, GitHub Push & Demo

**Objective:** Ship the four public artifacts required for badge submission: public repo, public Sheet, LinkedIn demo clip, Slack submission.

---

### HAR-013 — README Completion

**Type:** Documentation
**Effort:** Small

**Acceptance Criteria:**
- [ ] README includes: project title, one-line description, architecture diagram (ASCII or image), setup instructions (`pip install -r requirements.txt`, `.env` setup), usage examples with CLI args, three-board overview table, link to public Google Sheet, badge/demo clip link
- [ ] Setup section covers Google Cloud service account setup steps
- [ ] `selectors.md` link included for Naukri selector maintenance

**Definition of Done:**
- A new contributor can clone the repo and run the gleaner in under 10 minutes following only the README

---

### HAR-014 — Security Audit Before Push

**Type:** Security
**Effort:** Small

**Problem Statement:**
Credentials leaked to a public GitHub repo cannot be un-leaked. This ticket is a mandatory checkpoint before any `git push`.

**Acceptance Criteria:**
- [ ] `.env` listed in `.gitignore` — verified with `git check-ignore -v .env`
- [ ] Service account JSON file listed in `.gitignore` — verified with `git check-ignore`
- [ ] `git status` shows `.env` and JSON credential file as untracked (not staged)
- [ ] `git log --all --full-history -- .env` returns no results
- [ ] `requirements.txt` does not contain any secrets
- [ ] API keys do not appear hardcoded in any `.py` file (grep check)

**Definition of Done:**
- `grep -r "FIRECRAWL_API_KEY\s*=" boards/ gleaner.py writers.py` returns no matches
- `git status` shows clean working tree except for untracked `.env` and credential files

---

### HAR-015 — GitHub Push

**Type:** Deployment
**Effort:** Small

**Acceptance Criteria:**
- [ ] `git init && git add . && git commit -m "Sprint 1 — The Gleaner"` executed
- [ ] `gh repo create gleaner --public --source=. --push` executed (or manual repo creation + push)
- [ ] Repo is public and accessible without login
- [ ] Root contains: `gleaner.py`, `boards/`, `filters.py`, `writers.py`, `requirements.txt`, `README.md`, `.env.example`, `.gitignore`, `selectors.md`
- [ ] `.env` and credential JSON are NOT in the repo

**Definition of Done:**
- `https://github.com/sdn9300/gleaner` (or equivalent) is publicly accessible and shows all required files

---

### HAR-016 — LinkedIn Demo Clip & Post

**Type:** Marketing
**Effort:** Small

**Demo Clip Script (60–90 seconds):**
1. Show empty terminal — run `python gleaner.py --role "data scientist" --location "bangalore" --output jobs.csv --sheet <URL>`
2. Show live console output: fetch counts per board, filter counts, dedupe count, "Wrote N rows"
3. Switch to browser — refresh the Google Sheet — show 50+ rows populating live
4. Show GitHub repo URL in browser
5. Voiceover or caption: "Built The Gleaner — 4 job boards → one filtered CSV → live Google Sheet. Sprint 1 of the AI Job Agent Cohort."

**Acceptance Criteria:**
- [ ] Clip is 60–90 seconds, no longer
- [ ] All three artifacts visible: terminal run, Sheet refresh, repo URL
- [ ] Posted to LinkedIn with hashtag `#Gleaner`
- [ ] Google Sheet link in post is publicly viewable (anyone-with-link)

---

### HAR-017 — Badge Submission

**Type:** Admin
**Effort:** Trivial

**Acceptance Criteria:**
- [ ] Public GitHub repo URL submitted to cohort Slack
- [ ] Public Google Sheet URL submitted to cohort Slack
- [ ] LinkedIn post URL submitted to cohort Slack
- [ ] All three submitted by Monday 9 AM IST

**Definition of Done:**
- Submission confirmed in Slack thread. Badge earned.

---

## Ticket Summary

| Ticket | Phase | Title | Effort | Type |
|---|---|---|---|---|
| HAR-001 | 0 | Project Scaffold | Small | Setup |
| HAR-002 | 1 | NaukriAdapter Implementation | Medium | Feature |
| HAR-003 | 1 | Selector Maintenance Document | Small | Documentation |
| HAR-004 | 2 | RemoteOKAdapter Implementation | Small | Feature |
| HAR-005 | 3A | WellfoundAdapter Implementation | Medium | Feature |
| HAR-018 | 3B | IndeedAdapter Implementation | Medium-Large | Feature |
| HAR-006 | 4 | Deduplication | Small | Feature |
| HAR-007 | 4 | Role Filter | Small | Feature |
| HAR-008 | 4 | Location Filter | Small | Feature |
| HAR-009 | 5 | CSV Writer | Small | Feature |
| HAR-010 | 5 | Google Sheets Writer | Medium | Feature |
| HAR-011 | 6 | Full Pipeline Integration | Medium | Integration |
| HAR-012 | 6 | Fallback Handling | Small | Resilience |
| HAR-013 | 7 | README Completion | Small | Documentation |
| HAR-014 | 7 | Security Audit Before Push | Small | Security |
| HAR-015 | 7 | GitHub Push | Small | Deployment |
| HAR-016 | 7 | LinkedIn Demo Clip & Post | Small | Marketing |
| HAR-017 | 7 | Badge Submission | Trivial | Admin |

**Total tickets: 18**

---

## Dependency Graph

```
HAR-001 (Scaffold)
  └─► HAR-002 (Naukri)
        └─► HAR-003 (selectors.md)
  └─► HAR-004 (RemoteOK)
  └─► HAR-005 (Wellfound)      ← Phase 3A, parallel with 3B
  └─► HAR-018 (Indeed)         ← Phase 3B, parallel with 3A
  └─► HAR-006, HAR-007, HAR-008 (Filters — parallel with adapters)
  └─► HAR-009 (CSV Writer)
  └─► HAR-010 (Sheets Writer)

HAR-002 + HAR-004 + HAR-005 + HAR-018
+ HAR-006 + HAR-007 + HAR-008
+ HAR-009 + HAR-010
  └─► HAR-011 (Full Pipeline Integration)
        └─► HAR-012 (Fallback Handling)
              └─► HAR-013 (README)
                    └─► HAR-014 (Security Audit) ← GATE
                          └─► HAR-015 (GitHub Push)
                                └─► HAR-016 (Demo Clip)
                                      └─► HAR-017 (Badge Submission)
```

**HAR-014 is a hard gate. Nothing gets pushed before security audit passes.**

---

## Key Architectural Decisions

| Decision | Rationale |
|---|---|
| Abstract `BoardAdapter` base class | Isolates board-specific quirks from the pipeline. Adding a 4th board = implement one method. |
| `(company, title)` as dedupe key | Most reliable cross-board identifier. URL-based dedup fails because boards use different URL formats for the same job. |
| Filters applied after merge, not per-adapter | Single consistent filter logic. Per-adapter filtering would require duplicating logic in 4 places. |
| `--limit` applied after dedupe | Ensures the limit reflects truly unique, clean results — not raw scraped count. |
| CSV always written; Sheets is optional | Sheets can fail for auth reasons. CSV is the fallback that always works. |
| `.env` + service account JSON in `.gitignore` | Non-negotiable security boundary. Credentials in a public repo cannot be un-leaked. |
| Indeed uses Firecrawl, not raw `requests` | Indeed's Cloudflare bot protection returns 403 or a JS challenge to plain HTTP requests. Firecrawl stealth mode is the correct path. Publisher API is the documented fallback. |
| Wellfound and Indeed share Firecrawl but differ in URL and wait config | Both are JS-rendered with bot protection, but Indeed requires an additional `wait` action (2s) for full render. They are separate adapters, not parameterized siblings, because their extract schemas and URL patterns differ. |
