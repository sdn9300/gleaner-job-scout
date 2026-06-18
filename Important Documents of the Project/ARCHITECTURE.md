# ARCHITECTURE.md — The Gleaner
**Multi-Board Job Scraper | Sprint Build 1**
Version: 1.0 | Last Updated: 2026-06-14

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Directory Structure](#2-directory-structure)
3. [Component Map](#3-component-map)
4. [Data Flow Architecture](#4-data-flow-architecture)
5. [Module Specifications](#5-module-specifications)
   - 5.1 `gleaner.py` — Entry Point & Orchestrator
   - 5.2 `boards/base.py` — Abstract Adapter Contract
   - 5.3 `boards/naukri.py` — HTML Scraping Adapter
   - 5.4 `boards/remoteok.py` — Public API Adapter
   - 5.5 `boards/wellfound.py` — Firecrawl Adapter
   - 5.6 `boards/indeed.py` — Firecrawl Stealth Adapter
   - 5.7 `filters.py` — Pipeline Cleaning Layer
   - 5.8 `writers.py` — Output Layer
6. [Canonical Data Schema](#6-canonical-data-schema)
7. [Configuration Architecture](#7-configuration-architecture)
8. [Error Handling Architecture](#8-error-handling-architecture)
9. [Scraping Strategy Matrix](#9-scraping-strategy-matrix)
10. [Interface Contracts](#10-interface-contracts)
11. [Architecture Decision Records (ADRs)](#11-architecture-decision-records-adrs)
12. [Extension Points](#12-extension-points)
13. [CONDUCTOR Integration Contract](#13-conductor-integration-contract)
14. [Dependency Graph](#14-dependency-graph)

---

## 1. System Overview

The Gleaner is a **CLI-driven, adapter-based ETL pipeline** for job market data. It follows the Extract → Transform → Load (ETL) pattern:

- **Extract:** Four board adapters pull raw job listings from Naukri, RemoteOK, Wellfound, and Indeed using three different web acquisition strategies.
- **Transform:** A three-stage filter pipeline removes noise (off-topic roles, wrong locations, duplicates).
- **Load:** Two writers persist the clean dataset to local CSV and a public Google Sheet.

### Design Philosophy

Three principles govern every decision in this architecture:

**1. Adapter isolation.** Each board's quirks — its URL patterns, authentication, rate limits, and HTML/JSON/Firecrawl differences — are fully contained within its adapter. The pipeline never knows which board it is talking to.

**2. Schema as contract.** All adapters output the same seven-field dict. Downstream components depend on this contract unconditionally. Missing optional fields are empty strings, never `None`.

**3. Graceful degradation.** One failing adapter does not kill the pipeline. One failing writer does not suppress the other. The system delivers what it can and documents what it couldn't.

---

## 2. Directory Structure

```
gleaner/
│
├── gleaner.py              # CLI entry point and pipeline orchestrator
│
├── boards/                   # Board adapter package
│   ├── __init__.py           # Exports all four adapters
│   ├── base.py               # Abstract BoardAdapter base class
│   ├── naukri.py             # HTML scraping adapter (requests + BeautifulSoup)
│   ├── remoteok.py           # Public JSON API adapter
│   ├── wellfound.py          # Firecrawl SDK adapter
│   └── indeed.py             # Firecrawl stealth adapter
│
├── filters.py                # Pipeline cleaning functions (dedupe, role, location)
├── writers.py                # Output layer (CSV + Google Sheets)
│
├── config.yaml               # Default configuration (boards, limits, timeouts)
├── selectors.md              # Naukri CSS selector reference (last-verified date)
│
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variable template
├── .gitignore                # Excludes .env, *.csv, credentials/*.json
├── README.md                 # Setup and usage documentation
│
├── tests/                    # Unit test suite
│   ├── test_scaffold.py
│   ├── test_naukri.py
│   ├── test_remoteok.py
│   ├── test_wellfound.py
│   ├── test_indeed.py
│   ├── test_filters.py
│   └── test_writers.py
│
└── credentials/              # Gitignored — service account JSON lives here
    └── .gitkeep
```

---

## 3. Component Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                           gleaner.py                              │
│                      CLI Entry Point & Orchestrator                 │
│                                                                     │
│  argparse: --role --location --limit --output --sheet --boards      │
└────────────────────────────┬────────────────────────────────────────┘
                             │ instantiates + calls .fetch()
             ┌───────────────┼───────────────────┐
             │               │                   │                   │
             ▼               ▼                   ▼                   ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │   naukri.py  │ │ remoteok.py  │ │ wellfound.py │ │  indeed.py   │
    │              │ │              │ │              │ │              │
    │ requests +   │ │ Public JSON  │ │  Firecrawl   │ │  Firecrawl   │
    │ BeautifulSoup│ │ API          │ │  SDK         │ │  Stealth     │
    └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
           │                │                │                │
           └────────────────┴────────────────┴────────────────┘
                                     │
                              list[dict] (merged)
                                     │
                             ┌───────▼───────┐
                             │  filters.py   │
                             │               │
                             │ filter_by_role│
                             │ filter_by_loc │
                             │ dedupe        │
                             └───────┬───────┘
                                     │
                              list[dict] (clean)
                                     │
                    ┌────────────────┴─────────────────┐
                    │                                  │
             ┌──────▼──────┐                   ┌──────▼──────┐
             │  write_csv  │                   │write_to_sheet│
             │  (local)    │                   │ (gspread)   │
             └──────┬──────┘                   └──────┬──────┘
                    │                                  │
               jobs.csv                         Google Sheet
             (always written)                  (if --sheet provided)
```

---

## 4. Data Flow Architecture

### 4.1 Full Pipeline Sequence

```
Step 0: Parse CLI arguments
        role="data scientist", location="bangalore",
        limit=100, output="jobs.csv", sheet=<URL>

Step 1: Load configuration
        config.yaml → defaults
        .env → secrets (FIRECRAWL_API_KEY, GOOGLE_SERVICE_ACCOUNT_JSON)

Step 2: Instantiate adapters
        boards = [NaukriAdapter(), RemoteOKAdapter(),
                  WellfoundAdapter(), IndeedAdapter()]

Step 3: Fetch (per adapter, sequential, wrapped in try/except)
        ┌──────────────────────────────────────────────────┐
        │ for adapter in boards:                           │
        │     try:                                         │
        │         results = adapter.fetch(role, location)  │
        │         log(f"{adapter.name}: {len(results)}")   │
        │         all_jobs.extend(results)                 │
        │     except Exception as e:                       │
        │         log(WARNING, f"{adapter.name}: {e}")     │
        └──────────────────────────────────────────────────┘
        → all_jobs: merged list[dict], schema validated

Step 4: Filter
        4a. filter_by_role(all_jobs, role)
            → drops rows where role keywords absent from title + description
        4b. filter_by_location(role_filtered, location)
            → drops rows where location doesn't match (keeps 'Remote')
        4c. dedupe(location_filtered)
            → drops rows with duplicate (company.lower(), title.lower())

Step 5: Apply limit
        clean_jobs = dedupe_result[:limit]

Step 6: Write
        write_csv(clean_jobs, output_path)           # always
        if sheet_url:
            write_to_sheet(clean_jobs, sheet_url)    # conditional

Step 7: Summary
        log(f"Done. {len(clean_jobs)} jobs written to {output_path}")
```

### 4.2 Per-Adapter Data Flow

#### Naukri (HTML Scraping)
```
NaukriAdapter.fetch(role, location)
  │
  ├─ _build_url(role, location)
  │    "data-scientist" + "bangalore"
  │    → https://www.naukri.com/data-scientist-jobs-in-bangalore
  │
  ├─ requests.get(url, headers={"User-Agent": ...})
  │    → HTTP 200 or raise RuntimeError
  │
  ├─ time.sleep(1)
  │
  ├─ BeautifulSoup(response.text, 'lxml')
  │
  ├─ soup.select(".jobTupleHeader")  ← from selectors.md
  │    for card in job_cards:
  │        title   = card.select_one(".title").get_text(strip=True)
  │        company = card.select_one(".subTitle").get_text(strip=True)
  │        location= card.select_one(".ellipsis").get_text(strip=True)
  │        link    = _absolute_link(card.select_one("a")["href"])
  │        posted  = card.select_one(".fleft").get_text(strip=True)
  │
  └─ return [{"source":"naukri","title":...,"company":...,...}]
```

#### RemoteOK (Public API)
```
RemoteOKAdapter.fetch(role, location)
  │
  ├─ requests.get("https://remoteok.com/api",
  │               headers={"User-Agent": ...})
  │    → JSON array
  │
  ├─ data = response.json()[1:]  ← skip metadata blob at index 0
  │
  ├─ for job in data:
  │      keywords = role.lower().split()
  │      position = job.get("position","").lower()
  │      tags     = [t.lower() for t in job.get("tags",[])]
  │      if any(kw in position or kw in tags for kw in keywords):
  │          keep job
  │
  ├─ for matched_job:
  │      description = BeautifulSoup(
  │                      matched_job.get("description",""),
  │                      "lxml").get_text()
  │
  └─ return [{"source":"remoteok","title":position,
              "company":company,"location":location or "Remote",...}]
```

#### Wellfound (Firecrawl SDK)
```
WellfoundAdapter.fetch(role, location)
  │
  ├─ _load_env()  → FIRECRAWL_API_KEY or raise EnvironmentError
  │
  ├─ FirecrawlApp(api_key=key)
  │
  ├─ url = f"https://wellfound.com/jobs?role={role}&location={location}"
  │         (URL-encoded)
  │
  ├─ result = app.scrape_url(url, params={
  │               "formats": ["extract"],
  │               "extract": {
  │                   "schema": {
  │                       "type": "object",
  │                       "properties": {
  │                           "jobs": {
  │                               "type": "array",
  │                               "items": {
  │                                   "type": "object",
  │                                   "properties": {
  │                                       "title": {"type": "string"},
  │                                       "company": {"type": "string"},
  │                                       "location": {"type": "string"},
  │                                       "link": {"type": "string"}
  │                                   }
  │                               }
  │                           }
  │                       }
  │                   }
  │               }
  │           })
  │
  ├─ jobs = result.get("extract", {}).get("jobs", [])
  │    if not jobs: log WARNING, return []
  │
  └─ return [{"source":"wellfound","title":j["title"],...}]
```

#### Indeed (Firecrawl Stealth)
```
IndeedAdapter.fetch(role, location)
  │
  ├─ _load_env()  → FIRECRAWL_API_KEY or raise EnvironmentError
  │
  ├─ FirecrawlApp(api_key=key)
  │
  ├─ url = f"https://in.indeed.com/jobs?q={quote_plus(role)}&l={quote_plus(location)}"
  │
  ├─ result = app.scrape_url(url, params={
  │               "formats": ["extract"],
  │               "actions": [{"type": "wait", "milliseconds": 2000}],
  │               "extract": { ... same schema as Wellfound + posted_at + description ... }
  │           })
  │
  ├─ jobs = result.get("extract", {}).get("jobs", [])
  │    if not jobs: log WARNING, return []
  │
  ├─ for job in jobs:
  │      job["link"] = _absolute_link(job["link"])
  │      # relative /pagead/clk?... → https://in.indeed.com/pagead/clk?...
  │
  ├─ time.sleep(2)
  │
  └─ return [{"source":"indeed","title":j["title"],...}]
```

### 4.3 Filter Pipeline Data Flow

```
Input: all_jobs (merged, unfiltered)
       e.g. 180 rows: 60 naukri + 45 remoteok + 38 wellfound + 37 indeed

        ▼ filter_by_role(jobs, "data scientist")

  Rule: ANY keyword from role in title.lower() OR description.lower()
  Keywords extracted: ["data", "scientist"]
  Effect: drops "Frontend Developer", "Java Engineer", "DevOps SRE"
  Output: ~140 rows (estimate; actual depends on board content)

        ▼ filter_by_location(jobs, "bangalore")

  Rule: location.lower() contains "bangalore"
        OR location.lower() == "remote"
  Effect: drops "Mumbai", "Delhi", "San Francisco", "London" listings
  Output: ~95 rows (estimate)

        ▼ dedupe(jobs)

  Rule: unique on (company.strip().lower(), title.strip().lower())
  Key: ("flipkart", "data scientist") — keeps first occurrence, drops rest
  Effect: removes cross-board duplicates
  Output: ~78 rows (estimate)

        ▼ [:limit]  (default limit=100, so no truncation here)

  Final output: 78 clean, unique, relevant, location-matched rows
```

---

## 5. Module Specifications

### 5.1 `gleaner.py` — Entry Point & Orchestrator

**Responsibility:** Parse CLI arguments, instantiate adapters, run the pipeline, report summary.

**Must not contain:** Scraping logic, filtering logic, schema validation. Those belong in their respective modules.

```python
# Interface
def main() -> None:
    args = parse_args()          # argparse
    config = load_config()       # config.yaml
    load_dotenv()                # .env

    adapters = resolve_adapters(args.boards, config)
    all_jobs  = fetch_all(adapters, args.role, args.location)

    clean = pipeline(all_jobs, args.role, args.location)
    clean = clean[:args.limit]

    write_csv(clean, args.output)
    if args.sheet:
        write_to_sheet(clean, args.sheet)

    print(f"Done. {len(clean)} jobs written to {args.output}")
```

**CLI Interface:**

| Flag | Type | Default | Description |
|---|---|---|---|
| `--role` | str | required | Job role to search for |
| `--location` | str | required | Target city or region |
| `--limit` | int | `100` | Max rows in final output (post-dedupe) |
| `--output` | str | `jobs.csv` | Local CSV file path |
| `--sheet` | str | `None` | Google Sheet URL (optional) |
| `--boards` | str | `all` | Comma-separated: `naukri,remoteok,wellfound,indeed` |

**`resolve_adapters` logic:**
```python
ADAPTER_REGISTRY = {
    "naukri":   NaukriAdapter,
    "remoteok": RemoteOKAdapter,
    "wellfound": WellfoundAdapter,
    "indeed":   IndeedAdapter,
}

def resolve_adapters(boards_arg, config):
    names = boards_arg.split(",") if boards_arg != "all" \
            else config.get("boards", list(ADAPTER_REGISTRY.keys()))
    return [ADAPTER_REGISTRY[n]() for n in names if n in ADAPTER_REGISTRY]
```

---

### 5.2 `boards/base.py` — Abstract Adapter Contract

**Responsibility:** Define the interface every board adapter must implement. The rest of the system depends only on this interface, never on concrete adapter classes.

```python
from abc import ABC, abstractmethod

class BoardAdapter(ABC):
    """
    Abstract base class for all job board adapters.

    Every concrete adapter must implement fetch() and return a list
    of dicts conforming to the canonical job schema. The pipeline
    depends on this contract unconditionally — missing required fields
    or wrong types are bugs in the adapter, not in the pipeline.
    """

    @property
    def name(self) -> str:
        """Human-readable adapter name for logging."""
        return self.__class__.__name__.replace("Adapter", "").lower()

    @abstractmethod
    def fetch(self, role: str, location: str) -> list[dict]:
        """
        Fetch job listings for the given role and location.

        Args:
            role:     Job role search term (e.g. "data scientist")
            location: Target location (e.g. "bangalore")

        Returns:
            List of job dicts conforming to the canonical schema.
            Empty list on 0 results or non-fatal errors.
            Never raises on network or parsing errors — logs WARNING instead.

        Raises:
            EnvironmentError: If a required API key or credential is missing.
                              (Raised at instantiation time, not fetch time.)
        """
        ...

    def _validate_schema(self, job: dict) -> dict:
        """
        Enforces canonical schema on a raw dict. Fills missing
        optional fields with ''. Strips whitespace from all string values.
        Raises ValueError if a required field is missing or empty.
        """
        required = {"source", "title", "company", "location", "link"}
        optional = {"posted_at": "", "description": ""}

        for field in required:
            if not job.get(field, "").strip():
                raise ValueError(
                    f"{self.name}: Required field '{field}' missing or empty "
                    f"in job dict: {job}"
                )

        for field, default in optional.items():
            job.setdefault(field, default)
            if job[field] is None:
                job[field] = default

        # Strip whitespace from all string values
        return {k: v.strip() if isinstance(v, str) else v
                for k, v in job.items()}
```

**Why `name` is a property, not a constructor argument:**
The adapter name is derived from the class name automatically. This prevents the inconsistency of `NaukriAdapter(name="naukri")` vs `NaukriAdapter(name="Naukri")` — a small but real source of log noise.

**Why `_validate_schema` lives on the base class:**
Schema validation is a concern of the contract, not of the individual adapters. Putting it on `BoardAdapter` means every adapter gets validation for free by calling `self._validate_schema(job)` before appending to results.

---

### 5.3 `boards/naukri.py` — HTML Scraping Adapter

**Responsibility:** Scrape Naukri's server-rendered HTML job search pages.

**Key design decisions:**

| Decision | Rationale |
|---|---|
| `lxml` parser over `html.parser` | Faster; more lenient with malformed HTML (Naukri occasionally serves broken tags) |
| `time.sleep(1)` mandatory | Naukri actively rate-limits rapid sequential requests; a 1s delay reduces 429 risk |
| `RuntimeError` on non-200 | Non-200 is almost always a structural failure (blocked, wrong URL); the caller needs to know |
| `selectors.md` as external reference | Selectors change without notice; keeping them documented separately enables rapid repair without touching adapter code |

**Slug normalization:**
```python
def _slugify(self, text: str) -> str:
    """
    "Data Scientist" → "data-scientist"
    "New Delhi"      → "new-delhi"
    """
    return re.sub(r'\s+', '-', text.strip().lower())
```

**Absolute link normalization:**
```python
NAUKRI_BASE = "https://www.naukri.com"

def _absolute_link(self, href: str) -> str:
    if href.startswith("http"):
        return href
    return f"{self.NAUKRI_BASE}{href}"
```

**Selector dependency:** All CSS selectors used in this adapter are documented in `selectors.md` with their last-verified date. If `fetch()` returns 0 results and returns no error, the first diagnostic step is always to verify selectors against current Naukri HTML in DevTools.

---

### 5.4 `boards/remoteok.py` — Public API Adapter

**Responsibility:** Consume RemoteOK's public JSON API and filter results client-side.

**Key design decisions:**

| Decision | Rationale |
|---|---|
| `data[1:]` to skip metadata blob | RemoteOK's API always returns a metadata object as `[0]`; it is not a job listing |
| Client-side keyword filter | RemoteOK's API returns all jobs regardless of query; there is no server-side role filter |
| BeautifulSoup for HTML stripping | `description` field contains embedded HTML; stripping with BS4 is safer than regex for nested tags |
| Default location to `'Remote'` | Many RemoteOK listings have `null` or `""` location; the board is remote-first, so this default is semantically correct |

**Tag matching logic:**
```python
def _matches_role(self, job: dict, role: str) -> bool:
    keywords = role.lower().split()
    position = job.get("position", "").lower()
    tags = [t.lower() for t in job.get("tags", [])]
    return any(kw in position or any(kw in tag for tag in tags)
               for kw in keywords)
```

**Why RemoteOK needs no `time.sleep`:**
A single API call returns all available listings. There is no pagination and no repeated request, so rate-limit courtesy is not required.

---

### 5.5 `boards/wellfound.py` — Firecrawl SDK Adapter

**Responsibility:** Extract job listings from Wellfound's JavaScript-rendered pages via Firecrawl's structured extraction.

**Key design decisions:**

| Decision | Rationale |
|---|---|
| Firecrawl over Playwright | Wellfound requires JS rendering. Playwright is viable but adds headless browser weight and setup complexity to a sprint. Firecrawl is a managed service: one import, one API call. |
| Extract schema (not raw markdown) | Firecrawl's `extract` format with a JSON schema returns structured data directly. Raw `markdown` format would require a secondary parsing step. |
| Fail open on empty result | Firecrawl's free tier has a quota. Quota exhaustion returns a valid response with 0 jobs. The adapter returns `[]` and logs a warning rather than raising — the pipeline continues with results from other boards. |
| `EnvironmentError` at instantiation | Fail fast if the API key is missing, before any HTTP call is made. |

**Firecrawl extract schema:**
```python
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "jobs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title":    {"type": "string"},
                    "company":  {"type": "string"},
                    "location": {"type": "string"},
                    "link":     {"type": "string"}
                },
                "required": ["title", "company", "link"]
            }
        }
    }
}
```

---

### 5.6 `boards/indeed.py` — Firecrawl Stealth Adapter

**Responsibility:** Extract job listings from Indeed India's Cloudflare-protected, JavaScript-rendered pages via Firecrawl's stealth mode.

**Key design decisions:**

| Decision | Rationale |
|---|---|
| `in.indeed.com` over `www.indeed.com` | India-targeted search. `www.indeed.com` returns US-biased results even with location set. |
| `wait` action (2000ms) | Indeed's job cards render after an additional JS hydration step that fires ~1–2 seconds after initial page load. Without the wait, Firecrawl extracts empty containers. |
| `time.sleep(2)` after call | Stealth scraping requests are heavier server-side operations than standard HTML fetches. The sleep reduces the risk of IP-level rate limiting on the Firecrawl proxy pool. |
| Separate `_absolute_link` method | Indeed uses relative links internally (`/pagead/clk?...`). These must be prepended with `https://in.indeed.com` before they are usable. |
| Publisher API as documented fallback | Not wired into the adapter by default — it requires a separate `INDEED_PUBLISHER_ID`. Documented in code comments and `README.md` as the fallback path when Firecrawl quota is exhausted. |

**Firecrawl call with wait action:**
```python
result = self.app.scrape_url(url, params={
    "formats": ["extract"],
    "actions": [
        {"type": "wait", "milliseconds": 2000}
    ],
    "extract": {
        "schema": INDEED_EXTRACT_SCHEMA
    }
})
```

**Indeed extract schema (richer than Wellfound — description and posted_at often available):**
```python
INDEED_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "jobs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title":       {"type": "string"},
                    "company":     {"type": "string"},
                    "location":    {"type": "string"},
                    "link":        {"type": "string"},
                    "posted_at":   {"type": "string"},
                    "description": {"type": "string"}
                },
                "required": ["title", "company", "link"]
            }
        }
    }
}
```

**Indeed Publisher API fallback (when Firecrawl quota exhausted):**
```python
# Fallback — activate by setting INDEED_PUBLISHER_ID in .env
# Register free at: https://ads.indeed.com/jobroll/xmlfeed
def _fetch_via_publisher_api(self, role: str, location: str) -> list[dict]:
    publisher_id = os.getenv("INDEED_PUBLISHER_ID")
    if not publisher_id:
        log.warning("INDEED_PUBLISHER_ID not set. Indeed skipped.")
        return []

    params = {
        "publisher": publisher_id,
        "q": role,
        "l": location,
        "format": "json",
        "v": "2",
        "limit": 25,
        "co": "in"          # country = India
    }
    response = requests.get(
        "http://api.indeed.com/ads/apisearch",
        params=params
    )
    if response.status_code != 200:
        log.warning(f"Indeed Publisher API returned {response.status_code}.")
        return []

    return [
        {
            "source":      "indeed",
            "title":       job["jobtitle"],
            "company":     job["company"],
            "location":    job["city"],
            "link":        job["url"],
            "posted_at":   job.get("date", ""),
            "description": job.get("snippet", "")
        }
        for job in response.json().get("results", [])
    ]
```

---

### 5.7 `filters.py` — Pipeline Cleaning Layer

**Responsibility:** Three pure functions that clean the merged job list. Pure means: no side effects, no I/O, no mutations of the input list.

**Why pure functions and not a class:**
Filters have no state. A `FilterPipeline` class would add complexity without benefit. Pure functions are testable in isolation, composable in any order, and trivially replaceable.

**`dedupe(jobs: list[dict]) -> list[dict]`**
```python
def dedupe(jobs: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for job in jobs:
        key = (
            job.get("company", "").strip().lower(),
            job.get("title",   "").strip().lower()
        )
        if key not in seen:
            seen.add(key)
            result.append(job)
    return result
```

Design notes:
- `set` lookup is O(1); list traversal is O(n); total is O(n)
- First occurrence wins — this preserves board priority order (Naukri → RemoteOK → Wellfound → Indeed)
- Does not mutate `jobs` — `result` is a new list

**`filter_by_role(jobs: list[dict], role: str) -> list[dict]`**
```python
def filter_by_role(jobs: list[dict], role: str) -> list[dict]:
    keywords = role.lower().split()
    result = []
    for job in jobs:
        haystack = (
            job.get("title",       "").lower() + " " +
            job.get("description", "").lower()
        )
        if any(kw in haystack for kw in keywords):
            result.append(job)
    return result
```

Design notes:
- Keyword split on whitespace — "data scientist" → `["data", "scientist"]`
- ANY keyword match (OR logic, not AND) — more inclusive; reduces false negatives
- `title + description` concatenated to a single haystack — single pass per job
- Jobs with empty title AND empty description are dropped (no haystack → no match)

**`filter_by_location(jobs: list[dict], location: str) -> list[dict]`**
```python
def filter_by_location(jobs: list[dict], location: str) -> list[dict]:
    target = location.lower()
    result = []
    for job in jobs:
        job_loc = job.get("location", "").lower()
        if target in job_loc or job_loc == "remote":
            result.append(job)
    return result
```

Design notes:
- Substring match on location (`"bangalore"` in `"bangalore, karnataka"`) — handles formatted city names
- `"remote"` is always kept regardless of location query — remote jobs are globally relevant
- Case-insensitive throughout

**Filter composition in `gleaner.py`:**
```python
def pipeline(jobs, role, location):
    jobs = filter_by_role(jobs, role)
    jobs = filter_by_location(jobs, location)
    jobs = dedupe(jobs)
    return jobs
```

The composition order is fixed in `gleaner.py`, not in `filters.py`. This keeps each filter function dumb (a single concern) and makes the orchestration readable in one place.

---

### 5.8 `writers.py` — Output Layer

**Responsibility:** Two functions that write the clean job list to two destinations. Each is independently callable. Neither depends on the other.

**`write_csv(jobs: list[dict], path: str) -> None`**

```python
CANONICAL_FIELDS = [
    "source", "title", "company", "location",
    "link", "posted_at", "description"
]

def write_csv(jobs: list[dict], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=CANONICAL_FIELDS,
            extrasaction="ignore"   # silently drops non-canonical fields
        )
        writer.writeheader()
        for job in jobs:
            # Fill missing optional fields with empty string
            row = {field: job.get(field, "") for field in CANONICAL_FIELDS}
            writer.writerow(row)
    print(f"Wrote {len(jobs)} rows to {path}")
```

Design notes:
- `utf-8-sig` encoding adds a BOM that Excel requires to correctly detect UTF-8 — avoids Devanagari/CJK garbling in company names
- `extrasaction="ignore"` — extra fields in job dicts (future adapters may add fields) do not cause writer failures
- `newline=""` is required by Python's `csv` module to prevent double newlines on Windows

**`write_to_sheet(jobs: list[dict], sheet_url: str) -> None`**

```python
def write_to_sheet(jobs: list[dict], sheet_url: str) -> None:
    sa_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not sa_path:
        raise EnvironmentError(
            "GOOGLE_SERVICE_ACCOUNT_JSON not set in .env"
        )

    gc        = gspread.service_account(filename=sa_path)
    sheet     = gc.open_by_url(sheet_url)
    worksheet = sheet.get_worksheet(0)

    worksheet.clear()
    worksheet.append_row(CANONICAL_FIELDS)            # header row

    rows = [[job.get(f, "") for f in CANONICAL_FIELDS]
            for job in jobs]
    worksheet.append_rows(rows, value_input_option="USER_ENTERED")

    print(f"Wrote {len(jobs)} rows to Google Sheet")
```

Design notes:
- `worksheet.clear()` before writing — idempotent; re-running overwrites rather than appending
- `append_rows()` (batch) over `append_row()` in a loop — one API call instead of N; avoids Google Sheets API rate limits (100 req/100s per user)
- `value_input_option="USER_ENTERED"` — Sheet interprets dates and URLs naturally
- Service account path never logged or printed

---

## 6. Canonical Data Schema

This schema is the single source of truth. Every adapter must produce it. Every filter function must read it. Every writer must write it. No exceptions.

```python
# Canonical job dict — all seven fields, always present
{
    "source":      str,   # REQUIRED — 'naukri'|'remoteok'|'wellfound'|'indeed'
    "title":       str,   # REQUIRED — clean job title, no HTML, no leading/trailing whitespace
    "company":     str,   # REQUIRED — company name, no HTML
    "location":    str,   # REQUIRED — city string or 'Remote'; never None or ''
    "link":        str,   # REQUIRED — absolute URL starting with 'https://'
    "posted_at":   str,   # OPTIONAL — ISO date 'YYYY-MM-DD' if available, else ''
    "description": str,   # OPTIONAL — plain text snippet ≤500 chars, else ''
}
```

### Schema Enforcement Rules

| Rule | Who enforces it |
|---|---|
| Required fields non-empty | `BoardAdapter._validate_schema()` |
| `link` is absolute URL | Each adapter's `_absolute_link()` method |
| No HTML in any field | Each adapter's text extraction logic |
| `None` replaced with `''` | `BoardAdapter._validate_schema()` |
| `description` truncated at 500 chars | Optional; recommended in adapters, enforced in CSV writer via `extrasaction` |
| Field order in output | `CANONICAL_FIELDS` list in `writers.py` |

### Schema Evolution Policy

The canonical schema is frozen for Sprint 1. If a new field is needed (e.g., `salary`, `job_type`, `skills_required`), the process is:

1. Add the field to `CANONICAL_FIELDS` in `writers.py` as optional (default `''`)
2. Update `BoardAdapter._validate_schema()` to include the new optional field
3. Update any adapter that can supply the new field
4. Update the CONDUCTOR integration contract if applicable
5. Bump the schema version in this document

Do not add fields to individual adapters without following this process. Undocumented extra fields are silently dropped by the CSV writer's `extrasaction="ignore"` and will never appear in output.

---

## 7. Configuration Architecture

### 7.1 Configuration Layers

The system uses a three-layer configuration hierarchy. Later layers override earlier ones.

```
Layer 1: config.yaml (static defaults)
         ↓ overridden by
Layer 2: .env (secrets and environment-specific values)
         ↓ overridden by
Layer 3: CLI arguments (per-run runtime values)
```

### 7.2 `config.yaml`

```yaml
# config.yaml — static defaults, safe to commit
boards:
  - naukri
  - remoteok
  - wellfound
  - indeed

limits:
  default_limit: 100
  naukri_sleep_seconds: 1
  indeed_sleep_seconds: 2
  description_max_chars: 500

output:
  default_filename: jobs.csv
  encoding: utf-8-sig

google_sheets:
  header_row: true
  value_input_option: USER_ENTERED

logging:
  level: INFO         # DEBUG for verbose scraping output
  format: "%(asctime)s %(levelname)s %(name)s: %(message)s"
```

### 7.3 `.env` — Secrets (never committed)

```bash
# .env — gitignored; copy from .env.example

# Firecrawl (required for Wellfound and Indeed adapters)
FIRECRAWL_API_KEY=fc-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Google Sheets service account (required for --sheet flag)
GOOGLE_SERVICE_ACCOUNT_JSON=/absolute/path/to/credentials/service_account.json

# Indeed Publisher API fallback (optional; free registration at ads.indeed.com)
INDEED_PUBLISHER_ID=12345678901234567890
```

### 7.4 `.env.example` — Template (committed)

```bash
# .env.example — template; copy to .env and fill values

FIRECRAWL_API_KEY=          # get from firecrawl.dev/dashboard
GOOGLE_SERVICE_ACCOUNT_JSON= # absolute path to downloaded service account JSON
INDEED_PUBLISHER_ID=         # optional; from ads.indeed.com/jobroll/xmlfeed
```

### 7.5 Secret Access Pattern

All secret access follows the same pattern across the codebase:

```python
# Pattern: read from os.environ, fail fast if missing
value = os.environ.get("VAR_NAME")
if not value:
    raise EnvironmentError(
        "VAR_NAME not set. See .env.example for setup instructions."
    )
```

`python-dotenv` loads `.env` at the top of `gleaner.py` via `load_dotenv()`. Every module that needs a secret reads it from `os.environ` directly — they do not import or call `load_dotenv()` themselves.

---

## 8. Error Handling Architecture

### 8.1 Error Taxonomy

| Error Class | Cause | Response | Propagates? |
|---|---|---|---|
| `EnvironmentError` | Missing API key or credential at instantiation | Logged as ERROR; adapter excluded from run | No — caught in `fetch_all()` |
| `RuntimeError` (Naukri) | Non-200 HTTP response | Logged as WARNING | No — caught in `fetch_all()` |
| `requests.Timeout` | Board too slow to respond | Logged as WARNING | No |
| `requests.ConnectionError` | Network failure | Logged as WARNING | No |
| `KeyError` / `AttributeError` | Selector mismatch (Naukri HTML changed) | Logged as WARNING with field name | No |
| `json.JSONDecodeError` | Malformed API response | Logged as WARNING | No |
| `gspread.exceptions.*` | Google Sheets auth or API error | Logged as WARNING; CSV still written | No |
| `ValueError` (schema validation) | Adapter produced malformed dict | Logged as WARNING; row skipped | No |
| Unhandled exception in adapter | Unexpected failure | Logged as ERROR with traceback | No — caught by broad except |

### 8.2 Adapter Error Isolation

The core pattern in `fetch_all()` in `gleaner.py`:

```python
def fetch_all(adapters, role, location):
    all_jobs = []
    for adapter in adapters:
        try:
            results = adapter.fetch(role, location)
            log.info(f"{adapter.name}: fetched {len(results)} listings")
            all_jobs.extend(results)
        except EnvironmentError as e:
            log.error(f"{adapter.name} skipped: {e}")
        except Exception as e:
            log.warning(f"{adapter.name} failed: {e}")
    return all_jobs
```

One adapter failing (403, timeout, selector break, quota exhaustion) produces a log line and nothing else. The pipeline proceeds with results from the remaining adapters.

### 8.3 Writer Error Isolation

```python
# In gleaner.py
write_csv(clean_jobs, args.output)      # always — no try/except; CSV failure is fatal

if args.sheet:
    try:
        write_to_sheet(clean_jobs, args.sheet)
    except Exception as e:
        log.warning(f"Google Sheets write failed: {e}")
        log.warning("CSV output is still valid. Upload manually if needed.")
```

CSV failure is treated as fatal — if we can't write the primary output, the run has failed.
Sheets failure is treated as advisory — the CSV is always the canonical output.

### 8.4 Schema Validation Error Isolation

```python
# Inside each adapter's fetch() method
valid_jobs = []
for raw_job in raw_results:
    try:
        validated = self._validate_schema(raw_job)
        valid_jobs.append(validated)
    except ValueError as e:
        log.warning(f"{self.name}: Skipping malformed job: {e}")
return valid_jobs
```

One malformed dict drops that row; it does not abort the adapter's entire result set.

---

## 9. Scraping Strategy Matrix

This is the architectural taxonomy of the four boards. The board-selection logic — which tool to use for which target — is the core engineering decision in the system.

```
┌─────────────────┬────────────────────┬─────────────────────┬────────────────┐
│ Dimension       │ Naukri             │ RemoteOK            │ Wellfound      │
├─────────────────┼────────────────────┼─────────────────────┼────────────────┤
│ Rendering       │ Server-side HTML   │ JSON API response   │ JS-rendered    │
│ Auth required   │ No                 │ No                  │ Firecrawl key  │
│ Bot protection  │ Low (UA check)     │ None                │ Moderate       │
│ Data format     │ HTML → parse       │ JSON → map          │ Firecrawl→JSON │
│ Rate limit      │ Informal (1s sleep)│ None                │ Firecrawl quota│
│ Selector risk   │ High               │ None                │ None           │
│ Reliability     │ Medium             │ Very high           │ Medium         │
│ Speed           │ Slow               │ Very fast           │ Medium         │
│ Description     │ Snippet only       │ Full HTML           │ Varies         │
│ posted_at       │ Inconsistent       │ Always available    │ Rarely         │
│ Fallback        │ HN Who Is Hiring   │ None needed         │ WeWorkRemotely │
└─────────────────┴────────────────────┴─────────────────────┴────────────────┘

┌─────────────────┬──────────────────────────────────────────────────────────┐
│ Dimension       │ Indeed                                                   │
├─────────────────┼──────────────────────────────────────────────────────────┤
│ Rendering       │ JS-rendered                                              │
│ Auth required   │ Firecrawl key                                            │
│ Bot protection  │ Very high (Cloudflare; requests always fails)            │
│ Data format     │ Firecrawl extract → JSON                                 │
│ Rate limit      │ Firecrawl quota + 2s sleep                               │
│ Selector risk   │ None (Firecrawl abstraction)                             │
│ Reliability     │ Medium (Cloudflare challenge timing-sensitive)           │
│ Speed           │ Slowest (2s wait + 2s sleep = ~4s per call)              │
│ Description     │ Often available (Indeed shows snippets on listing pages) │
│ posted_at       │ Often available                                          │
│ Fallback        │ Indeed Publisher API (INDEED_PUBLISHER_ID in .env)       │
└─────────────────┴──────────────────────────────────────────────────────────┘
```

**Decision rule: which tool to use for a new board?**

```
Does the board have a public API or RSS feed?
  YES → Use it. JSON API > everything else.
  NO  ↓
Is the board server-rendered (no JS required)?
  YES → requests + BeautifulSoup.
  NO  ↓
Is the board JS-rendered without aggressive bot protection?
  YES → Firecrawl (standard mode, no wait action).
  NO  ↓
Does the board use Cloudflare or equivalent bot protection?
  YES → Firecrawl stealth mode with wait action.
  STILL FAILING → Look for an official developer/publisher API.
```

---

## 10. Interface Contracts

### 10.1 `BoardAdapter.fetch()` Contract

```
Signature:  fetch(role: str, location: str) -> list[dict]

Preconditions:
  - role is a non-empty string (e.g. "data scientist")
  - location is a non-empty string (e.g. "bangalore")
  - Any required API keys have been validated at instantiation

Postconditions:
  - Returns a list (possibly empty, never None)
  - Each dict in the list satisfies the canonical schema
  - Required fields are non-empty strings
  - Optional fields are strings ('' if unavailable, never None)
  - All link values are absolute URLs
  - No HTML tags in any field value
  - source field equals the board's name

Error behaviour:
  - EnvironmentError if a required key is missing (raised at __init__, not here)
  - Returns [] on network errors, 0 results, quota exhaustion (logs WARNING)
  - Never raises on recoverable failures
```

### 10.2 `filters.py` Function Contracts

```
dedupe(jobs: list[dict]) -> list[dict]
  - Preconditions:  jobs is a list (possibly empty)
  - Postconditions: returned list ⊆ input list (no new dicts created)
                    len(result) ≤ len(input)
                    no two dicts share (company.lower(), title.lower())
                    input list is not mutated

filter_by_role(jobs: list[dict], role: str) -> list[dict]
  - Preconditions:  role is a non-empty string
  - Postconditions: every returned dict has at least one role keyword
                    in its title or description (case-insensitive)
                    input list is not mutated

filter_by_location(jobs: list[dict], location: str) -> list[dict]
  - Preconditions:  location is a non-empty string
  - Postconditions: every returned dict has location containing the
                    query string, OR location == 'remote'
                    input list is not mutated
```

### 10.3 `writers.py` Function Contracts

```
write_csv(jobs: list[dict], path: str) -> None
  - Preconditions:  jobs is a list (possibly empty); path is writable
  - Postconditions: file at path exists; first row is CANONICAL_FIELDS header;
                    subsequent rows are job data in canonical field order;
                    missing optional fields written as ''
  - Side effects:   creates or overwrites file at path; prints confirmation
  - Raises:         OSError if path is not writable

write_to_sheet(jobs: list[dict], sheet_url: str) -> None
  - Preconditions:  GOOGLE_SERVICE_ACCOUNT_JSON set in env;
                    Sheet at sheet_url shared with service account email
  - Postconditions: first worksheet cleared; header row written;
                    all job rows written in canonical field order
  - Side effects:   modifies remote Google Sheet; prints confirmation
  - Raises:         EnvironmentError if service account JSON path not set
                    gspread exceptions propagate to caller (caught in gleaner.py)
```

---

## 11. Architecture Decision Records (ADRs)

### ADR-001: Abstract Adapter Pattern over Conditional Branching

**Status:** Accepted
**Date:** 2026-06-14

**Context:**
The pipeline must support four job boards, each with a different scraping strategy. The naive approach is a single function with `if board == "naukri": ... elif board == "remoteok": ...` branching.

**Decision:**
Abstract base class `BoardAdapter` with a single abstract method `fetch()`. Each board is a separate class in a separate file.

**Options Considered:**

| Option | Complexity | Extensibility | Testability |
|---|---|---|---|
| Conditional branching in gleaner.py | Low initial | Poor (modify gleaner.py per board) | Poor (can't test boards in isolation) |
| Abstract base class (chosen) | Medium initial | Excellent (new file = new board) | Excellent (each adapter tested independently) |
| Plugin/entry-point system | High | Very good | Good | 

**Consequences:**
- Adding a fifth board requires one new file; zero changes to `gleaner.py`, `filters.py`, or `writers.py`
- Each adapter is independently testable with mocks
- `boards/__init__.py` must export all adapters (minor maintenance cost)

---

### ADR-002: Sequential Adapter Execution over Parallel

**Status:** Accepted
**Date:** 2026-06-14

**Context:**
Four adapters could be run concurrently with `asyncio` or `concurrent.futures.ThreadPoolExecutor` to reduce total fetch time.

**Decision:**
Sequential execution in Sprint 1.

**Options Considered:**

| Option | Speed | Complexity | Rate-limit risk |
|---|---|---|---|
| Sequential (chosen) | Slower (~10–15s total) | Low | Low |
| ThreadPoolExecutor | ~3–4x faster | Medium | Higher (concurrent requests to same boards) |
| asyncio | Fastest | High (async adapters required) | Highest |

**Rationale:**
Sprint 1 is a 120-minute build. Parallel execution requires either thread safety guarantees for `all_jobs.extend()` or result aggregation logic. Sequential execution is correct, readable, and debuggable. The total fetch time (~10–15 seconds across four boards) is not a user-facing latency problem for a CLI batch job.

**Consequence:**
ThreadPoolExecutor is the obvious Sprint 2 upgrade path if fetch time becomes a concern. The adapter interface does not need to change — each `fetch()` call is already stateless and thread-safe by design.

---

### ADR-003: Filter Order (Role → Location → Dedupe)

**Status:** Accepted
**Date:** 2026-06-14

**Context:**
Three filter operations must run in some order. The order affects performance (sets processed per step) and correctness (deduplication should operate on the final relevant set).

**Decision:**
`filter_by_role` → `filter_by_location` → `dedupe`

**Rationale:**
- Role filter eliminates the most noise (off-topic listings are common): running it first minimises the set that subsequent filters must process
- Location filter further reduces the set before deduplication
- Deduplication last ensures the dedupe key space reflects only relevant, location-matched listings — deduplicating early would consume the key budget on listings that would have been filtered anyway
- All three are O(n); the order is a correctness and clarity decision, not a performance one

**Consequence:**
The order is fixed in `gleaner.py`'s `pipeline()` function. It is not configurable. If a use case requires a different order, a new pipeline function should be defined rather than parameterising the existing one.

---

### ADR-004: CSV as Primary Output, Google Sheets as Secondary

**Status:** Accepted
**Date:** 2026-06-14

**Context:**
Two output destinations. One requires only filesystem access; the other requires OAuth credentials, an active internet connection, and a correctly shared Sheet.

**Decision:**
CSV is always written first, unconditionally. Google Sheets write is conditional on `--sheet` flag and wrapped in a try/except that allows the run to succeed even if Sheets fails.

**Rationale:**
Google Sheets write can fail for reasons entirely outside the data pipeline: expired service account, wrong sharing settings, Sheets API quota, network issues. The job data itself is correct and should not be lost because of an output-layer failure. CSV on local disk is the guaranteed record. Sheets is the public showcase artifact.

**Consequence:**
If Sheets write fails, the operator must manually upload the CSV to the Sheet (or fix the credential and re-run). This is an acceptable manual step for a CLI tool.

---

### ADR-005: `(company, title)` as Dedupe Key over URL

**Status:** Accepted
**Date:** 2026-06-14

**Context:**
Deduplication requires a key that identifies the same job across multiple boards. Two natural candidates: URL or `(company, title)`.

**Decision:**
`(company.lower().strip(), title.lower().strip())`

**Options Considered:**

| Key | Pros | Cons |
|---|---|---|
| URL | Unique per board, no false positives | Same job has different URLs on Naukri vs Indeed vs RemoteOK — fails cross-board |
| (company, title) (chosen) | Works cross-board; same job on 3 boards correctly deduplicated | False positive if same company has two genuinely different roles with identical titles (rare) |
| (company, title, location) | Fewer false positives | Remote listings may have different location strings per board |

**Consequence:**
In the rare case where a company has two roles with identical titles in the same location (e.g., two "Data Scientist" openings at the same firm), the second will be incorrectly dropped. This is an acceptable trade-off — the probability is low, and the cost is one missing listing, not a corrupted dataset.

---

## 12. Extension Points

The architecture is designed with four explicit extension points. Each can be exercised without modifying existing code.

### 12.1 Adding a New Board Adapter

1. Create `boards/{boardname}.py`
2. Implement `class {BoardName}Adapter(BoardAdapter)` with `fetch()`
3. Add to `ADAPTER_REGISTRY` in `gleaner.py`
4. Export from `boards/__init__.py`
5. Write tests in `tests/test_{boardname}.py`

No other files change.

### 12.2 Adding a New Filter Function

1. Add function to `filters.py` following the same pure-function contract
2. Call it in `gleaner.py`'s `pipeline()` function in the correct position
3. Write tests in `tests/test_filters.py`

### 12.3 Adding a New Output Writer

1. Add function to `writers.py`
2. Add a CLI flag in `gleaner.py` to trigger it
3. Call it in `gleaner.py` after `write_csv()`, wrapped in try/except

### 12.4 Adding a New Output Format (`--format json`)

The JSON output format is the CONDUCTOR integration path. When implemented:

1. Add `--format` flag: `choices=["csv", "json"], default="csv"`
2. Add `write_json(jobs, path)` to `writers.py`
3. Implement using `json.dumps([job for job in jobs], indent=2)`
4. Output file: `jobs.json` (or `--output` path with `.json` extension)

The JSON format is what CONDUCTOR's Research Agent will consume. The canonical schema maps directly to the CONDUCTOR input contract (see Section 13).

---

## 13. CONDUCTOR Integration Contract

The Gleaner is **Component 1** of CONDUCTOR. When the CONDUCTOR orchestration layer is built, Gleaner's output becomes its input. The integration contract defines the handoff.

### 13.1 CONDUCTOR Input JSON Schema

```json
{
  "run_id": "string (UUID)",
  "timestamp": "string (ISO 8601)",
  "query": {
    "role": "string",
    "location": "string",
    "boards": ["string"]
  },
  "stats": {
    "raw_fetched":          "integer",
    "after_role_filter":    "integer",
    "after_location_filter":"integer",
    "after_dedupe":         "integer",
    "final":                "integer"
  },
  "jobs": [
    {
      "source":      "string",
      "title":       "string",
      "company":     "string",
      "location":    "string",
      "link":        "string",
      "posted_at":   "string",
      "description": "string",
      "relevance_score": null
    }
  ]
}
```

`relevance_score` is `null` from Gleaner. CONDUCTOR's Research Agent populates it via LLM classification before passing downstream to AlignResume and Overture.

### 13.2 Producing CONDUCTOR-Compatible Output

```python
# In gleaner.py — activated by --format json
import uuid, datetime, json

def write_conductor_json(jobs, query, stats, path):
    payload = {
        "run_id":    str(uuid.uuid4()),
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "query":     query,
        "stats":     stats,
        "jobs":      [{**job, "relevance_score": None} for job in jobs]
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"CONDUCTOR payload written to {path}")
```

### 13.3 CONDUCTOR Pipeline Position

```
[ Gleaner ]
     │
     │  jobs.json (CONDUCTOR payload)
     ▼
[ Research Agent ]        ← scores each listing for relevance
     │
     │  ranked_jobs.json
     ▼
[ Orchestrator ]          ← routes to downstream agents per job
     │
     ├──► [ AlignResume ]     ← rewrites resume per JD
     ├──► [ Overture ]        ← drafts cold email per company
     └──► [ Auto-Apply PDF ]  ← generates tailored application package
```

---

## 14. Dependency Graph

### 14.1 Module Import Graph

```
gleaner.py
  ├── boards/__init__.py
  │     ├── boards/base.py          (abc, abstractmethod)
  │     ├── boards/naukri.py        (requests, bs4, time, re)
  │     ├── boards/remoteok.py      (requests, bs4)
  │     ├── boards/wellfound.py     (firecrawl, os, dotenv)
  │     └── boards/indeed.py        (firecrawl, os, dotenv, urllib.parse, time)
  ├── filters.py                    (no external imports — pure Python)
  ├── writers.py                    (csv, os, gspread, google.oauth2)
  └── (stdlib: argparse, logging, json, uuid, datetime)
```

### 14.2 External Dependency Registry

| Package | Version pin | Used by | Purpose |
|---|---|---|---|
| `requests` | `>=2.31` | naukri, remoteok | HTTP client |
| `beautifulsoup4` | `>=4.12` | naukri, remoteok | HTML/text parsing |
| `lxml` | `>=4.9` | naukri, remoteok | BS4 parser backend |
| `firecrawl-py` | `>=0.0.16` | wellfound, indeed | JS-rendering + extraction |
| `python-dotenv` | `>=1.0` | wellfound, indeed, writers | `.env` loading |
| `gspread` | `>=5.12` | writers | Google Sheets API client |
| `google-auth` | `>=2.0` | writers | Service account auth |
| `pyyaml` | `>=6.0` | gleaner | `config.yaml` loading |

### 14.3 Python Version

**Minimum:** Python 3.10 (required for `match` statements if used in future; `list[dict]` type hints without `from __future__ import annotations`)

**Recommended:** Python 3.11+ (faster; improved error messages)

### 14.4 No Circular Dependencies

```
gleaner.py  →  boards/*, filters.py, writers.py
boards/*      →  boards/base.py, external libs
filters.py    →  (no internal imports)
writers.py    →  (no internal imports from this project)
```

No module in `boards/` imports from `filters.py` or `writers.py`. No module imports from `gleaner.py`. The dependency graph is a strict DAG with `gleaner.py` as the root.
