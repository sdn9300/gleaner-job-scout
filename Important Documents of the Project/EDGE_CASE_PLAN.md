# EDGE_CASE_PLAN.md — The Gleaner
**Multi-Board Job Scraper | Sprint Build 1**
Version: 1.0 | Last Updated: 2026-06-14

---

## Purpose

This document catalogs every known edge case across The Gleaner's pipeline — input edge cases, adapter-specific failure modes, schema violations, filter boundary conditions, writer failures, and configuration errors — with expected behavior, detection method, handling code, and a test case for each.

**Governing principle:** An edge case that is not documented is a bug waiting to happen at the worst possible time (live demo, public Sheet, badge submission). Every edge case below has one of three outcomes: handled gracefully with a logged warning, handled gracefully with a sensible default, or a documented hard failure with a clear error message. **Silent failure is never an acceptable outcome.**

---

## Table of Contents

1. [Edge Case Categories & Severity Framework](#1-edge-case-categories--severity-framework)
2. [Input & CLI Argument Edge Cases](#2-input--cli-argument-edge-cases)
3. [Naukri Adapter Edge Cases](#3-naukri-adapter-edge-cases)
4. [RemoteOK Adapter Edge Cases](#4-remoteok-adapter-edge-cases)
5. [Wellfound Adapter Edge Cases](#5-wellfound-adapter-edge-cases)
6. [Indeed Adapter Edge Cases](#6-indeed-adapter-edge-cases)
7. [Cross-Adapter & Schema Edge Cases](#7-cross-adapter--schema-edge-cases)
8. [Filter Pipeline Edge Cases](#8-filter-pipeline-edge-cases)
9. [Writer Edge Cases — CSV](#9-writer-edge-cases--csv)
10. [Writer Edge Cases — Google Sheets](#10-writer-edge-cases--google-sheets)
11. [Environment & Configuration Edge Cases](#11-environment--configuration-edge-cases)
12. [Security & Credential Edge Cases](#12-security--credential-edge-cases)
13. [Concurrency & State Edge Cases](#13-concurrency--state-edge-cases)
14. [Live Demo Edge Cases](#14-live-demo-edge-cases)
15. [Edge Case Test Matrix (Summary)](#15-edge-case-test-matrix-summary)

---

## 1. Edge Case Categories & Severity Framework

### 1.1 Severity Levels

| Severity | Definition | Required Response |
|---|---|---|
| **P0 — Critical** | Causes pipeline crash, data loss, or credential leak | Must be handled before any phase ships |
| **P1 — High** | Causes incorrect/missing data in final output without crashing | Must be handled before Phase 7 |
| **P2 — Medium** | Degrades quality (e.g., a few malformed rows) but pipeline succeeds | Should be handled; document if deferred |
| **P3 — Low** | Cosmetic or rare; acceptable to document as a known limitation | May be deferred to Sprint 2 |

### 1.2 Edge Case Entry Format

Each edge case below follows this structure:

```
### EC-XXX: [Name]
Severity: P0/P1/P2/P3
Scenario:    [What input/condition triggers this]
Expected:    [What the system should do]
Detection:   [How to verify this is handled]
Handling:    [Code pattern or logic]
Test:        [Unit test reference]
```

---

## 2. Input & CLI Argument Edge Cases

### EC-001: Empty or Whitespace-Only `--role`
**Severity:** P1

**Scenario:** User runs `python gleaner.py --role "" --location "Bangalore"` or `--role "   "`.

**Expected:** Argument validation rejects this before any adapter is called. Clear error message, non-zero exit code.

**Detection:** `python gleaner.py --role "" --location "Bangalore"` should print an error and exit, not produce an empty CSV.

**Handling:**
```python
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True)
    parser.add_argument("--location", required=True)
    args = parser.parse_args()

    if not args.role.strip():
        parser.error("--role cannot be empty or whitespace-only")
    if not args.location.strip():
        parser.error("--location cannot be empty or whitespace-only")

    args.role = args.role.strip()
    args.location = args.location.strip()
    return args
```

**Test:**
```python
def test_empty_role_rejected():
    result = subprocess.run(
        ["python", "gleaner.py", "--role", "", "--location", "Bangalore"],
        capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "role" in result.stderr.lower()
```

---

### EC-002: `--limit` is Zero or Negative
**Severity:** P2

**Scenario:** `--limit 0` or `--limit -5`.

**Expected:** `--limit 0` produces a valid (empty) CSV with headers only — not an error, since "give me zero results" is a technically valid (if odd) request. `--limit -5` is rejected at argument parsing — negative limits are never meaningful.

**Detection:**
```bash
python gleaner.py --role "x" --location "y" --limit 0 --output out.csv
# Should produce out.csv with header row only, 0 data rows

python gleaner.py --role "x" --location "y" --limit -5 --output out.csv
# Should error: "--limit must be a non-negative integer"
```

**Handling:**
```python
parser.add_argument("--limit", type=int, default=100)
# ... after parsing:
if args.limit < 0:
    parser.error("--limit must be a non-negative integer")
```

```python
# In main(), slicing with limit=0 naturally produces []
clean = clean[:args.limit]   # clean[:0] == [] — no special case needed
```

**Test:**
```python
def test_limit_zero_produces_header_only_csv():
    # Run pipeline with --limit 0, then check CSV has 1 line (header)
    ...

def test_negative_limit_rejected():
    result = subprocess.run([..., "--limit", "-5"], capture_output=True, text=True)
    assert result.returncode != 0
```

---

### EC-003: Unknown Board Name in `--boards`
**Severity:** P2

**Scenario:** `--boards naukri,linkedin,remoteok` — "linkedin" is not a registered adapter.

**Expected:** Unknown board names are skipped with a warning. The pipeline continues with the valid boards (`naukri`, `remoteok`). If ALL board names are invalid, the pipeline should error out (nothing to do).

**Handling:**
```python
def resolve_adapters(boards_arg: str) -> list[BoardAdapter]:
    if boards_arg == "all":
        return [cls() for cls in ADAPTER_REGISTRY.values()]

    names = [n.strip().lower() for n in boards_arg.split(",")]
    adapters = []
    for name in names:
        if name in ADAPTER_REGISTRY:
            adapters.append(ADAPTER_REGISTRY[name]())
        else:
            log.warning(f"Unknown board '{name}' — skipping. "
                        f"Valid options: {list(ADAPTER_REGISTRY.keys())}")

    if not adapters:
        raise ValueError(
            f"No valid boards specified. Got: {boards_arg}. "
            f"Valid options: {list(ADAPTER_REGISTRY.keys())} or 'all'"
        )
    return adapters
```

**Test:**
```python
def test_unknown_board_skipped_with_warning(caplog):
    adapters = resolve_adapters("naukri,linkedin")
    assert len(adapters) == 1
    assert "Unknown board 'linkedin'" in caplog.text

def test_all_unknown_boards_raises():
    with pytest.raises(ValueError):
        resolve_adapters("linkedin,glassdoor")
```

---

### EC-004: `--output` Path Has Non-Existent Parent Directory
**Severity:** P1

**Scenario:** `--output results/2026/jobs.csv` but `results/2026/` doesn't exist.

**Expected:** Either the directory is created automatically, or a clear `OSError` is raised before the pipeline runs (not after fetching — wasted API calls are worse than an early error).

**Handling:**
```python
def main():
    args = parse_args()

    # Validate output path BEFORE fetching anything
    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        log.info(f"Created output directory: {output_dir}")

    # ... proceed with fetch
```

**Test:**
```python
def test_output_directory_created(tmp_path):
    output_path = tmp_path / "nested" / "dir" / "jobs.csv"
    # ... run main() with --output set to output_path
    assert output_path.parent.exists()
```

---

### EC-005: `--role` or `--location` Contains Special Characters
**Severity:** P1

**Scenario:** `--role "C++ Developer"` or `--location "São Paulo"` — contains `+`, non-ASCII characters, or symbols that affect URL construction and keyword matching.

**Expected:**
- URL construction: all special characters URL-encoded correctly (`urllib.parse.quote_plus`)
- Slug generation (Naukri): `+` and non-alphanumeric characters handled without producing invalid URLs
- Keyword matching (filters): `"C++".lower().split()` → `["c++"]` — substring matching on `"c++"` still works correctly since `.lower()` doesn't strip symbols

**Handling:**
```python
# Naukri slugify — strip non-alphanumeric except hyphens
def _slugify(self, text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)   # drop special chars
    text = re.sub(r'\s+', '-', text)
    return text

# "C++ Developer" -> "c developer" -> "c-developer"
# Document this lossy behavior in README — "++" is dropped, which is
# an acceptable approximation for URL slugs

# Firecrawl-based adapters (Wellfound, Indeed) — use quote_plus, which
# handles unicode and symbols correctly without lossy transformation
from urllib.parse import quote_plus
url = f"https://in.indeed.com/jobs?q={quote_plus(role)}&l={quote_plus(location)}"
# "São Paulo" -> "S%C3%A3o+Paulo" — correct
```

**Test:**
```python
def test_slugify_handles_special_chars():
    adapter = NaukriAdapter()
    assert adapter._slugify("C++ Developer") == "c-developer"

def test_unicode_location_url_encoded():
    adapter = IndeedAdapter()
    url = adapter._build_url("data scientist", "São Paulo")
    assert "%C3%A3" in url or "S%C3%A3o" in url
```

---

## 3. Naukri Adapter Edge Cases

### EC-010: HTTP 403 Forbidden
**Severity:** P1

**Scenario:** Naukri detects the request as a bot (missing/suspicious User-Agent, too many requests from same IP) and returns 403.

**Expected:** Adapter raises `RuntimeError` with a descriptive message including the status code and URL. Caught by `fetch_all()` in the orchestrator, logged as WARNING, pipeline continues with other boards.

**Handling:**
```python
def fetch(self, role: str, location: str) -> list[dict]:
    url = self._build_url(role, location)
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36")
    }
    response = requests.get(url, headers=headers, timeout=15)

    if response.status_code == 403:
        raise RuntimeError(
            f"Naukri returned 403 Forbidden for {url}. "
            f"Possible bot detection — try rotating User-Agent or "
            f"adding longer delays."
        )
    if response.status_code != 200:
        raise RuntimeError(
            f"Naukri returned {response.status_code} for {url}"
        )

    time.sleep(1)
    # ... continue parsing
```

**Test:**
```python
def test_403_raises_runtime_error():
    adapter = NaukriAdapter()
    mock_resp = MagicMock(status_code=403)
    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="403"):
            adapter.fetch("data scientist", "bangalore")
```

---

### EC-011: HTTP 429 Too Many Requests
**Severity:** P1

**Scenario:** Repeated runs in quick succession trigger rate limiting.

**Expected:** Same as 403 — `RuntimeError` with status code, caught by orchestrator. Additionally, the error message should suggest the specific remediation (wait longer, reduce request frequency).

**Handling:**
```python
if response.status_code == 429:
    retry_after = response.headers.get("Retry-After", "unknown")
    raise RuntimeError(
        f"Naukri returned 429 Too Many Requests for {url}. "
        f"Retry-After: {retry_after}. Wait before retrying."
    )
```

**Test:**
```python
def test_429_includes_retry_after_in_message():
    adapter = NaukriAdapter()
    mock_resp = MagicMock(status_code=429, headers={"Retry-After": "60"})
    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="60"):
            adapter.fetch("data scientist", "bangalore")
```

---

### EC-012: Selectors Match Zero Cards (Selector Drift)
**Severity:** P1

**Scenario:** Naukri changes their HTML structure; `soup.select(".jobTuple")` returns an empty list even though the page loaded successfully (HTTP 200) and contains job listings.

**Expected:** Adapter does NOT raise an error (the request succeeded). It logs a clear warning pointing to `selectors.md` and returns `[]`. This is distinguishable from "no jobs exist for this query" only by a human checking the page — but the warning gives the right next action.

**Handling:**
```python
cards = soup.select(self.CARD_SELECTOR)
if not cards:
    log.warning(
        f"Naukri: 0 job cards found for selector "
        f"'{self.CARD_SELECTOR}' at {url}. "
        f"This usually means Naukri's HTML structure changed. "
        f"Check selectors.md and update via DevTools inspection. "
        f"(Response was 200 OK with {len(response.text)} bytes — "
        f"the page loaded, but the selector didn't match anything.)"
    )
    return []
```

**Test:**
```python
def test_zero_cards_logs_warning_with_selector_hint(caplog):
    adapter = NaukriAdapter()
    mock_resp = MagicMock(status_code=200, text="<html><body>No matching divs</body></html>")
    with patch("requests.get", return_value=mock_resp):
        results = adapter.fetch("data scientist", "bangalore")
    assert results == []
    assert "selectors.md" in caplog.text
```

---

### EC-013: Job Card Missing Individual Fields (Partial Selector Match)
**Severity:** P2

**Scenario:** The card container selector matches, but a sub-selector (e.g., `.postedDate`) doesn't match for a specific card — some Naukri listings omit the posted date entirely.

**Expected:** That specific card still produces a valid job dict — required fields (`title`, `company`, `location`, `link`) must be present, but `posted_at` defaults to `''`. If a REQUIRED field's selector fails for one card, that single card is skipped (logged at DEBUG, not WARNING — this is common and not actionable) while other cards are processed normally.

**Handling:**
```python
for card in cards:
    try:
        title_el = card.select_one(self.TITLE_SELECTOR)
        company_el = card.select_one(self.COMPANY_SELECTOR)
        location_el = card.select_one(self.LOCATION_SELECTOR)
        link_el = card.select_one(self.LINK_SELECTOR)

        if not all([title_el, company_el, location_el, link_el]):
            log.debug("Naukri: card missing a required field selector; skipping card")
            continue

        posted_el = card.select_one(self.POSTED_SELECTOR)  # optional

        job = {
            "source": "naukri",
            "title": title_el.get_text(strip=True),
            "company": company_el.get_text(strip=True),
            "location": location_el.get_text(strip=True),
            "link": self._absolute_link(link_el["href"]),
            "posted_at": posted_el.get_text(strip=True) if posted_el else "",
            "description": ""
        }
        results.append(self._validate_schema(job))
    except (AttributeError, KeyError) as e:
        log.debug(f"Naukri: error parsing card, skipping: {e}")
        continue
```

**Test:**
```python
def test_card_missing_posted_date_still_included():
    html = '<div class="jobTuple"><a class="title" href="/job1">Data Scientist</a>' \
           '<div class="subTitle">Acme</div><div class="locWdth">Bangalore</div></div>'
    # No .postedDate element present
    # ... mock and verify result has posted_at == ""

def test_card_missing_title_skipped():
    html = '<div class="jobTuple"><div class="subTitle">Acme</div></div>'
    # No title at all -> card is skipped entirely, not included with empty title
```

---

### EC-014: Relative vs Absolute Links Mixed on Same Page
**Severity:** P2

**Scenario:** Some job cards have `href="https://www.naukri.com/job/123"` (absolute, e.g., sponsored listings) while others have `href="/job/456"` (relative).

**Expected:** Both are normalized to absolute URLs. Detection is per-link, not per-page.

**Handling:**
```python
def _absolute_link(self, href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return f"https://www.naukri.com{href}"
    # Relative without leading slash (rare) — treat as path from domain root
    return f"https://www.naukri.com/{href}"
```

**Test:**
```python
@pytest.mark.parametrize("href,expected", [
    ("https://www.naukri.com/job/123", "https://www.naukri.com/job/123"),
    ("/job/456", "https://www.naukri.com/job/456"),
    ("job/789", "https://www.naukri.com/job/789"),
])
def test_absolute_link_normalization(href, expected):
    adapter = NaukriAdapter()
    assert adapter._absolute_link(href) == expected
```

---

### EC-015: Encoding Issues — Garbled Company Names
**Severity:** P2

**Scenario:** Company names with non-ASCII characters (e.g., "Société Générale", or company names in Devanagari script) appear garbled (`SociÃ©tÃ© GÃ©nÃ©rale`) due to incorrect response encoding detection.

**Expected:** `response.encoding` explicitly set to `'utf-8'` before accessing `response.text`, since `requests` sometimes guesses encoding incorrectly from headers.

**Handling:**
```python
response = requests.get(url, headers=headers, timeout=15)
response.encoding = 'utf-8'   # force UTF-8, don't trust auto-detection
soup = BeautifulSoup(response.text, 'lxml')
```

**Test:**
```python
def test_encoding_forced_to_utf8():
    adapter = NaukriAdapter()
    mock_resp = MagicMock(status_code=200, text="Société Générale")
    mock_resp.encoding = 'ISO-8859-1'  # wrong initial guess
    with patch("requests.get", return_value=mock_resp):
        adapter.fetch("data scientist", "bangalore")
    assert mock_resp.encoding == 'utf-8'
```

---

### EC-016: Request Timeout
**Severity:** P1

**Scenario:** Naukri's server is slow or unresponsive; the request hangs indefinitely without a timeout.

**Expected:** A `timeout` parameter on `requests.get()` (15 seconds recommended) ensures the adapter fails fast rather than hanging the entire pipeline.

**Handling:**
```python
try:
    response = requests.get(url, headers=headers, timeout=15)
except requests.Timeout:
    log.warning(f"Naukri: request to {url} timed out after 15s")
    return []
except requests.ConnectionError as e:
    log.warning(f"Naukri: connection error: {e}")
    return []
```

**Test:**
```python
def test_timeout_returns_empty_list_with_warning(caplog):
    adapter = NaukriAdapter()
    with patch("requests.get", side_effect=requests.Timeout):
        results = adapter.fetch("data scientist", "bangalore")
    assert results == []
    assert "timed out" in caplog.text
```

---

## 4. RemoteOK Adapter Edge Cases

### EC-020: First Element is Not a Metadata Blob (API Change)
**Severity:** P1

**Scenario:** RemoteOK changes their API and `data[0]` is now a real job listing, not metadata — blindly skipping it would silently drop a valid result.

**Expected:** Detect the metadata blob by structure (it lacks a `position` key, or has a `legal` key) rather than blindly assuming index `[0]`.

**Handling:**
```python
def fetch(self, role: str, location: str) -> list[dict]:
    response = requests.get(
        "https://remoteok.com/api",
        headers={"User-Agent": "Mozilla/5.0 (compatible; GleanerBot/1.0)"},
        timeout=15
    )
    if response.status_code != 200:
        log.warning(f"RemoteOK API returned {response.status_code}")
        return []

    data = response.json()

    # Filter out the metadata blob by structure, not by position
    jobs_raw = [item for item in data if "position" in item and "id" in item]

    if len(jobs_raw) == len(data):
        log.debug("RemoteOK: no metadata blob detected (API format may have changed)")
    elif len(data) - len(jobs_raw) > 1:
        log.warning(
            f"RemoteOK: {len(data) - len(jobs_raw)} items lacked 'position'/'id' "
            f"keys — expected exactly 1 (metadata blob). API format may have changed."
        )
```

**Test:**
```python
def test_metadata_blob_detected_by_structure():
    mock_data = [
        {"legal": "...", "some_other_field": "..."},  # metadata, no 'position'
        {"id": "123", "position": "Python Dev", "company": "X", "tags": ["python"]}
    ]
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = mock_data
        mock_get.return_value.status_code = 200
        results = RemoteOKAdapter().fetch("python", "remote")
    assert len(results) == 1
    assert results[0]["title"] == "Python Dev"

def test_no_metadata_blob_logs_debug(caplog):
    mock_data = [
        {"id": "1", "position": "Python Dev", "tags": ["python"]},
        {"id": "2", "position": "JS Dev", "tags": ["javascript"]}
    ]
    # ... all items have 'position' and 'id' -> debug log expected
```

---

### EC-021: `tags` Field is Missing or Not a List
**Severity:** P2

**Scenario:** A job entry has `tags: null` or omits the `tags` key entirely.

**Expected:** Treated as an empty list — does not crash, simply contributes nothing to the tag-based keyword match (title-based match still applies).

**Handling:**
```python
tags = job.get("tags") or []   # handles both missing key and null value
if not isinstance(tags, list):
    tags = []
tags = [str(t).lower() for t in tags]
```

**Test:**
```python
@pytest.mark.parametrize("tags_value", [None, [], "not-a-list", 123])
def test_malformed_tags_handled(tags_value):
    job = {"position": "Python Developer", "tags": tags_value, "id": "1"}
    # ... should not raise, role filter still works via title match
```

---

### EC-022: `description` Field Contains Deeply Nested or Malformed HTML
**Severity:** P2

**Scenario:** `description` contains malformed HTML (unclosed tags, script tags, embedded CSS) that could break naive parsing or, worse, get written into the CSV/Sheet with executable content.

**Expected:** `BeautifulSoup(desc, 'lxml').get_text()` strips ALL tags including `<script>` and `<style>` content text (BS4's `get_text()` includes script/style text by default — must explicitly remove these elements first).

**Handling:**
```python
def _strip_html(self, html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, 'lxml')
    # Remove script and style elements entirely — get_text() would
    # otherwise include their inner text content
    for element in soup(["script", "style"]):
        element.decompose()
    text = soup.get_text(separator=" ", strip=True)
    # Collapse multiple whitespace
    text = re.sub(r'\s+', ' ', text)
    return text
```

**Test:**
```python
def test_script_tags_fully_removed():
    adapter = RemoteOKAdapter()
    html = "<p>Great role</p><script>alert('xss')</script>"
    result = adapter._strip_html(html)
    assert "alert" not in result
    assert "Great role" in result

def test_malformed_html_does_not_crash():
    adapter = RemoteOKAdapter()
    html = "<p>Unclosed paragraph <div>nested <span>deeply"
    result = adapter._strip_html(html)  # should not raise
    assert "nested" in result
```

---

### EC-023: Same Job Posted Multiple Times by RemoteOK Itself
**Severity:** P3

**Scenario:** RemoteOK occasionally lists the same job twice (different `id`, identical `position`/`company`) due to repost or their own data issues.

**Expected:** Not RemoteOK adapter's responsibility — this is handled by the global `dedupe()` in `filters.py`, which operates on `(company, title)` regardless of source-internal IDs. Document this as the reason dedupe operates post-merge, not per-adapter.

**Handling:** None needed in adapter — covered by EC-040 (dedupe edge cases).

---

## 5. Wellfound Adapter Edge Cases

### EC-030: Firecrawl Returns HTTP 200 But Empty `extract.jobs`
**Severity:** P1

**Scenario:** Firecrawl successfully scrapes the page (no error) but the extraction schema matches zero jobs — could mean (a) genuinely no results for this query, (b) the page structure doesn't match what the extract schema expects, or (c) the page returned a "no results" state.

**Expected:** Cannot distinguish (a)/(b)/(c) automatically. Log a warning covering all three possibilities, return `[]`. Does not raise.

**Handling:**
```python
result = self.app.scrape_url(url, params={...})
jobs = result.get("extract", {}).get("jobs", [])

if not jobs:
    log.warning(
        f"Wellfound: 0 jobs extracted for '{role}' in '{location}'. "
        f"Possible causes: (1) no matching listings, (2) Firecrawl "
        f"extract schema didn't match page structure, (3) Firecrawl "
        f"quota exhausted (check 'success' field in response). "
        f"Raw response keys: {list(result.keys())}"
    )
    return []
```

**Test:**
```python
def test_empty_extract_logs_diagnostic_warning(caplog):
    mock_result = {"extract": {"jobs": []}, "success": True}
    with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test"}):
        with patch("firecrawl.FirecrawlApp.scrape_url", return_value=mock_result):
            results = WellfoundAdapter().fetch("data scientist", "remote")
    assert results == []
    assert "Firecrawl" in caplog.text
```

---

### EC-031: Firecrawl Quota Exhausted — `success: False` or HTTP 402/429
**Severity:** P1

**Scenario:** Firecrawl's free tier monthly quota is used up. The SDK may raise an exception or return a response with `success: False` and an error message about billing/quota.

**Expected:** Detected explicitly (not just "0 jobs") so the warning message is actionable and distinct from EC-030.

**Handling:**
```python
try:
    result = self.app.scrape_url(url, params={...})
except Exception as e:
    error_str = str(e).lower()
    if "quota" in error_str or "rate limit" in error_str or "402" in error_str or "429" in error_str:
        log.warning(
            f"Wellfound: Firecrawl quota/rate-limit error: {e}. "
            f"Consider WeWorkRemotely RSS fallback (see ARCHITECTURE.md ADR for pivot)."
        )
    else:
        log.warning(f"Wellfound: Firecrawl error: {e}")
    return []

if result.get("success") is False:
    log.warning(
        f"Wellfound: Firecrawl reported failure: "
        f"{result.get('error', 'no error message provided')}"
    )
    return []
```

**Test:**
```python
def test_quota_error_identified_distinctly(caplog):
    with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test"}):
        with patch("firecrawl.FirecrawlApp.scrape_url",
                    side_effect=Exception("402 Payment Required - quota exceeded")):
            results = WellfoundAdapter().fetch("data scientist", "remote")
    assert results == []
    assert "quota" in caplog.text.lower()
```

---

### EC-032: Extracted Job Missing `location` Field
**Severity:** P2

**Scenario:** Firecrawl's extraction returns a job object where `location` is absent or empty — common for remote-only boards where location is implicit.

**Expected:** Default to `'Remote'`, consistent with the RemoteOK adapter's convention for this board type.

**Handling:**
```python
for raw_job in jobs:
    job = {
        "source": "wellfound",
        "title": raw_job.get("title", ""),
        "company": raw_job.get("company", ""),
        "location": raw_job.get("location") or "Remote",
        "link": raw_job.get("link", ""),
        "posted_at": "",
        "description": ""
    }
```

**Test:**
```python
@pytest.mark.parametrize("location_value", [None, "", "  "])
def test_missing_location_defaults_to_remote(location_value):
    raw_job = {"title": "ML Engineer", "company": "X", "location": location_value, "link": "https://wellfound.com/j/1"}
    # ... process and assert location == "Remote"
```

---

### EC-033: Extracted `link` is a Wellfound Internal Search/Redirect URL, Not a Job Posting
**Severity:** P2

**Scenario:** Firecrawl's extraction occasionally captures a navigation link (e.g., "View all jobs at this company" → company profile URL) instead of the specific job posting URL.

**Expected:** Cannot be fully prevented at extraction time (depends on Firecrawl's interpretation of the schema), but the schema's `required: ["title", "company", "link"]` ensures `link` is at least present and non-empty. Document as a known limitation — accuracy of `link` depends on Firecrawl's extraction quality, not on Gleaner's code.

**Handling:** None beyond schema enforcement (link must be non-empty, must start with `http`). Document in README's "Known Limitations":

```markdown
## Known Limitations
- Wellfound and Indeed adapters rely on Firecrawl's LLM-based structured
  extraction. While link, title, and company are required by the extract
  schema, occasional extraction inaccuracies (e.g., a company profile URL
  instead of a specific job posting URL) may occur. This is a property of
  the underlying extraction service, not a bug in Gleaner's pipeline.
```

**Test:** Not unit-testable (depends on external service behavior) — document only.

---

## 6. Indeed Adapter Edge Cases

### EC-040: Cloudflare Challenge Not Resolved Despite Wait Action
**Severity:** P1

**Scenario:** Even with `{"type": "wait", "milliseconds": 2000}`, Firecrawl's response contains the Cloudflare challenge page content (e.g., "Checking your browser before accessing...") instead of job listings.

**Expected:** Detect this specific failure mode by checking if the extracted `jobs` list is empty AND optionally inspecting raw markdown/HTML for known Cloudflare challenge strings, to give a more specific warning than a generic "0 results."

**Handling:**
```python
CLOUDFLARE_MARKERS = [
    "checking your browser",
    "cf-browser-verification",
    "ray id",
    "cloudflare"
]

result = self.app.scrape_url(url, params={
    "formats": ["extract", "markdown"],  # request markdown too, for diagnosis
    "actions": [{"type": "wait", "milliseconds": 2000}],
    "extract": {"schema": INDEED_EXTRACT_SCHEMA}
})

jobs = result.get("extract", {}).get("jobs", [])

if not jobs:
    markdown = (result.get("markdown") or "").lower()
    if any(marker in markdown for marker in CLOUDFLARE_MARKERS):
        log.warning(
            "Indeed: Cloudflare challenge detected in response despite "
            "wait action. Try increasing wait to 4000-5000ms, or use "
            "Indeed Publisher API fallback (set INDEED_PUBLISHER_ID)."
        )
    else:
        log.warning("Indeed: 0 jobs extracted. Possible no-results or extraction mismatch.")
    return []
```

**Test:**
```python
def test_cloudflare_challenge_detected(caplog):
    mock_result = {
        "extract": {"jobs": []},
        "markdown": "Checking your browser before accessing in.indeed.com. Ray ID: abc123"
    }
    with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test"}):
        with patch("firecrawl.FirecrawlApp.scrape_url", return_value=mock_result):
            results = IndeedAdapter().fetch("data scientist", "bangalore")
    assert results == []
    assert "Cloudflare" in caplog.text
```

---

### EC-041: Sponsored Listings Mixed with Organic Results
**Severity:** P2

**Scenario:** Indeed's extraction includes sponsored/promoted listings alongside organic ones. Sponsored listings often have `link` containing `/pagead/clk?` or `/rc/clk?` redirect patterns.

**Expected:** Sprint 1 does NOT filter these out (documented as out of scope in PROBLEM_STATEMENT). However, the `_absolute_link()` method must still correctly handle these redirect-style relative links so they don't produce broken URLs.

**Handling:**
```python
def _absolute_link(self, href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return f"https://in.indeed.com{href}"
    return f"https://in.indeed.com/{href}"

# Note: /pagead/clk?... and /rc/clk?... both start with "/" and are
# handled correctly by this method. They produce valid (if redirect-y)
# absolute URLs. Filtering sponsored content is a Sprint 2 stretch goal
# (see PROBLEM_STATEMENT.md HAR-018 "Known Challenges" table).
```

**Test:**
```python
@pytest.mark.parametrize("href", [
    "/pagead/clk?mo=r&ad=abc123",
    "/rc/clk?jk=xyz789",
    "/viewjob?jk=def456"
])
def test_sponsored_and_organic_links_both_normalized(href):
    adapter = IndeedAdapter()
    result = adapter._absolute_link(href)
    assert result.startswith("https://in.indeed.com")
```

---

### EC-042: `posted_at` in Relative Format ("3 days ago") vs ISO Format
**Severity:** P3

**Scenario:** Indeed (and Naukri) often return `posted_at` as relative strings ("Today", "3 days ago", "30+ days ago") rather than ISO dates. The canonical schema documents `posted_at` as "ISO date if available, else empty string" — but Firecrawl extraction may return the relative string as-is.

**Expected:** Sprint 1 does NOT parse relative dates into ISO format (out of scope). The relative string is passed through as-is in `posted_at`. This is a documented limitation, not a bug — the field is still populated and human-readable.

**Handling:** None — pass through as extracted. Document:

```markdown
## Known Limitations
- `posted_at` may contain relative date strings ("3 days ago", "Today")
  rather than strict ISO 8601 dates, depending on what the source board
  provides. Parsing relative dates to absolute dates is a Sprint 2
  enhancement.
```

**Test:** Not applicable (no transformation to test) — verify schema validation doesn't reject non-ISO strings:

```python
def test_relative_date_string_passes_schema_validation():
    job = {
        "source": "indeed", "title": "X", "company": "Y",
        "location": "Bangalore", "link": "https://in.indeed.com/job/1",
        "posted_at": "3 days ago", "description": ""
    }
    validated = BoardAdapter()._validate_schema(job)
    assert validated["posted_at"] == "3 days ago"
```

---

### EC-043: `time.sleep(2)` Combined with `wait: 2000ms` Action Causes Excessive Total Latency
**Severity:** P3

**Scenario:** Each Indeed fetch takes ~4-6 seconds (2s Firecrawl wait + processing time + 2s post-call sleep). If the pipeline is run with `--boards indeed` repeatedly during testing (e.g., 10 manual test runs during Phase 3B), this adds up to over a minute of pure latency.

**Expected:** This is a known, accepted cost — documented so it doesn't appear to be a "hang" during testing. Not a bug; a design trade-off (see ARCHITECTURE.md ADR-002 — sequential execution).

**Handling:** None — document expected latency:

```markdown
## Performance Notes
- The Indeed adapter takes approximately 4-6 seconds per fetch call due
  to Firecrawl's stealth rendering wait action (2s) plus a post-call
  rate-limit courtesy sleep (2s). This is expected and by design.
```

**Test:** Not applicable — timing-based tests are flaky; document instead.

---

## 7. Cross-Adapter & Schema Edge Cases

### EC-050: Adapter Returns a Non-List (e.g., `None` or a Dict)
**Severity:** P0

**Scenario:** A bug in an adapter causes `fetch()` to return `None` instead of `[]`, or returns a single `dict` instead of `list[dict]`. `all_jobs.extend(None)` raises `TypeError`; `all_jobs.extend({...})` iterates dict keys (silent corruption — extremely dangerous).

**Expected:** `fetch_all()` defensively validates the return type of every adapter call, treating a non-list return as an adapter error (same handling as an exception).

**Handling:**
```python
def fetch_all(adapters, role, location):
    all_jobs = []
    for adapter in adapters:
        try:
            results = adapter.fetch(role, location)
            if not isinstance(results, list):
                log.error(
                    f"{adapter.name}: fetch() returned {type(results).__name__}, "
                    f"expected list. Treating as empty result."
                )
                results = []
            log.info(f"{adapter.name}: fetched {len(results)} listings")
            all_jobs.extend(results)
        except EnvironmentError as e:
            log.error(f"{adapter.name} skipped: {e}")
        except Exception as e:
            log.warning(f"{adapter.name} failed: {e}")
    return all_jobs
```

**Test:**
```python
def test_non_list_return_treated_as_empty(caplog):
    bad_adapter = MagicMock()
    bad_adapter.name = "badboard"
    bad_adapter.fetch.return_value = None  # bug: should be []

    result = fetch_all([bad_adapter], "role", "location")
    assert result == []
    assert "expected list" in caplog.text

def test_dict_return_not_silently_iterated(caplog):
    bad_adapter = MagicMock()
    bad_adapter.name = "badboard"
    bad_adapter.fetch.return_value = {"title": "oops"}  # bug: dict not list

    result = fetch_all([bad_adapter], "role", "location")
    assert result == []  # NOT ['title'] — would happen if extend() ran on a dict
```

---

### EC-051: Job Dict Contains Extra/Unexpected Fields
**Severity:** P3

**Scenario:** An adapter (perhaps during future extension) includes extra fields beyond the canonical schema, e.g., `salary`, `job_type`.

**Expected:** Extra fields do not break the pipeline. `_validate_schema()` does not strip them (it only ensures required fields exist and fills optional defaults). The CSV writer's `extrasaction="ignore"` silently drops them from CSV output. The Sheets writer explicitly maps only `CANONICAL_FIELDS`, so extras are dropped there too.

**Handling:** Already covered by `extrasaction="ignore"` (EC-060) and explicit field mapping in `write_to_sheet`. No additional code — but document the behavior so it's not mistaken for a bug:

```markdown
## Schema Evolution Note
Extra fields beyond the canonical 7 are preserved through
_validate_schema() but silently dropped by both writers. To surface
a new field, follow the Schema Evolution Policy in ARCHITECTURE.md
Section 6.
```

**Test:**
```python
def test_extra_fields_dropped_silently_by_csv_writer(tmp_path):
    jobs = [{
        "source": "naukri", "title": "X", "company": "Y",
        "location": "Z", "link": "https://x.com",
        "posted_at": "", "description": "",
        "salary": "10 LPA"  # extra field, not in CANONICAL_FIELDS
    }]
    path = tmp_path / "out.csv"
    write_csv(jobs, str(path))
    with open(path, encoding="utf-8-sig") as f:
        header = f.readline()
    assert "salary" not in header
```

---

### EC-052: Required Field Present but Contains Only Whitespace
**Severity:** P1

**Scenario:** `title = "   "` — technically a non-empty string, but semantically empty after stripping.

**Expected:** `_validate_schema()` must check `.strip()`, not just truthiness, when validating required fields. `"   "` is truthy in Python (`bool("   ") == True`) but should be treated as missing.

**Handling:**
```python
def _validate_schema(self, job: dict) -> dict:
    required = {"source", "title", "company", "location", "link"}
    optional = {"posted_at": "", "description": ""}

    for field in required:
        value = job.get(field, "")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"{self.name}: Required field '{field}' is missing, "
                f"empty, or whitespace-only: {job!r}"
            )

    for field, default in optional.items():
        value = job.get(field)
        if value is None or not isinstance(value, str):
            job[field] = default

    return {
        k: (v.strip() if isinstance(v, str) else v)
        for k, v in job.items()
    }
```

**Test:**
```python
@pytest.mark.parametrize("field", ["source", "title", "company", "location", "link"])
def test_whitespace_only_required_field_rejected(field):
    job = {
        "source": "naukri", "title": "X", "company": "Y",
        "location": "Z", "link": "https://x.com"
    }
    job[field] = "   "  # whitespace only
    with pytest.raises(ValueError, match="whitespace-only"):
        BoardAdapter()._validate_schema(job)
```

---

### EC-053: `source` Field Does Not Match Adapter's Own Name
**Severity:** P2

**Scenario:** A copy-paste error in `boards/indeed.py` results in `job["source"] = "wellfound"` (leftover from copying the Wellfound adapter as a template).

**Expected:** This is a development-time bug, but it's worth a defensive check since it would cause silent misattribution in the output (e.g., Indeed-sourced jobs labeled as Wellfound, breaking dedupe assumptions and reporting accuracy).

**Handling:**
```python
# In _validate_schema, accept an optional expected_source check
def _validate_schema(self, job: dict, expected_source: str = None) -> dict:
    # ... existing validation ...
    if expected_source and job.get("source") != expected_source:
        raise ValueError(
            f"{self.name}: job['source'] = '{job.get('source')}' does not "
            f"match expected '{expected_source}'. Possible copy-paste error "
            f"in adapter implementation."
        )
    return job

# In boards/indeed.py:
validated = self._validate_schema(job, expected_source="indeed")
```

**Test:**
```python
def test_mismatched_source_field_rejected():
    job = {
        "source": "wellfound",  # WRONG — should be 'indeed'
        "title": "X", "company": "Y", "location": "Z",
        "link": "https://x.com"
    }
    with pytest.raises(ValueError, match="does not match expected"):
        BoardAdapter()._validate_schema(job, expected_source="indeed")
```

---

## 8. Filter Pipeline Edge Cases

### EC-060: `dedupe()` on a List with All Identical Jobs
**Severity:** P2

**Scenario:** All four boards happen to return the exact same job (e.g., a very generic search returns one dominant listing everywhere).

**Expected:** `dedupe()` returns a single-element list. No crash, no special-case logic needed — this is the normal case of the algorithm working correctly.

**Test:**
```python
def test_dedupe_all_identical_collapses_to_one():
    jobs = [
        {"company": "Acme", "title": "Data Scientist", "source": "naukri", "location": "X", "link": "a"},
        {"company": "acme", "title": "data scientist", "source": "remoteok", "location": "Y", "link": "b"},
        {"company": "ACME", "title": "DATA SCIENTIST", "source": "wellfound", "location": "Z", "link": "c"},
    ]
    result = dedupe(jobs)
    assert len(result) == 1
    assert result[0]["source"] == "naukri"  # first occurrence wins
```

---

### EC-061: `dedupe()` Key Fields Are Missing (Defensive)
**Severity:** P1

**Scenario:** Despite `_validate_schema()` enforcing required fields, a defensive check is warranted in `filters.py` since filters may be called independently of adapters (e.g., in tests, or future direct CSV re-processing where rows might have been hand-edited and lost a field).

**Expected:** `dedupe()` does not raise `KeyError` if `company` or `title` is missing — uses `.get()` with empty-string default, treating missing fields as empty strings for key purposes (multiple such rows would then collapse together, which is acceptable — they're already malformed).

**Handling:**
```python
def dedupe(jobs: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for job in jobs:
        key = (
            job.get("company", "").strip().lower(),
            job.get("title", "").strip().lower()
        )
        if key not in seen:
            seen.add(key)
            result.append(job)
    return result
```

**Test:**
```python
def test_dedupe_handles_missing_keys_gracefully():
    jobs = [
        {"source": "naukri", "location": "X", "link": "a"},  # no company/title
        {"source": "remoteok", "location": "Y", "link": "b"}, # no company/title
    ]
    result = dedupe(jobs)  # both have key ("", "") -> collapse to 1
    assert len(result) == 1
```

---

### EC-062: `filter_by_role()` with Role Containing Stop Words Only
**Severity:** P3

**Scenario:** `--role "the of"` (degenerate input — unlikely but possible via typo or test).

**Expected:** Keywords `["the", "of"]` will match almost any text containing common English words, resulting in a filter that passes nearly everything through. This is a "garbage in, garbage out" case — not handled specially, but documented.

**Handling:** None — document as expected behavior:

```markdown
## Known Limitations
- filter_by_role() performs simple substring keyword matching with no
  stop-word filtering. A role query consisting only of common English
  words will match most listings. Users should provide specific role
  terms (e.g., "data scientist", not "the data").
```

**Test:** Not applicable (no bug to test) — optionally a documentation test:
```python
def test_stopword_role_matches_broadly():
    jobs = [{"title": "Software Engineer", "description": "Join the team", ...}]
    result = filter_by_role(jobs, "the of")
    assert len(result) == 1  # "the" matches "the team" -- expected, documented
```

---

### EC-063: `filter_by_location()` — Location Substring Matches Unintended Locations
**Severity:** P3

**Scenario:** `--location "Delhi"` matches both "New Delhi" and, hypothetically, a location string like "Delhi Avenue, Toronto" (extremely unlikely but theoretically possible with malformed location data from an adapter).

**Expected:** Substring matching is intentional and documented (ADR-level decision in ARCHITECTURE.md). The trade-off (some false positives possible with adversarial/malformed data, but correctly handles "Bangalore" matching "Bangalore, Karnataka") is accepted. No special handling.

**Handling:** None — document:

```markdown
## Known Limitations
- filter_by_location() uses substring matching, which correctly handles
  "Bangalore" matching "Bangalore, Karnataka, India" but could
  theoretically produce false positives with adversarial or malformed
  location strings (e.g., a location literally containing the query as
  a substring of an unrelated place name). This has not been observed
  in practice with the four supported boards.
```

---

### EC-064: All Jobs Filtered Out — Final Result is Empty List
**Severity:** P1

**Scenario:** `filter_by_role` + `filter_by_location` + `dedupe` reduce the result set to zero rows — e.g., a very specific role/location combination with genuinely no matches across any board.

**Expected:** The pipeline does NOT crash. `write_csv([], path)` produces a valid CSV with header row only, 0 data rows. `write_to_sheet([], url)` clears the sheet and writes only the header row. The final summary message clearly states `0` rows, prompting the user to broaden their search.

**Handling:**
```python
# write_csv and write_to_sheet already handle empty lists correctly
# (the for loop simply doesn't execute). The key addition is in main():

clean = pipeline(all_jobs, args.role, args.location)
clean = clean[:args.limit]

if len(clean) == 0:
    log.warning(
        f"0 jobs remain after filtering for role='{args.role}', "
        f"location='{args.location}'. Consider broadening your search "
        f"terms (e.g., a more general role, or 'Remote' as location)."
    )

write_csv(clean, args.output)
# ... etc
print(f"Done. {len(clean)} jobs written to {args.output}")
```

**Test:**
```python
def test_zero_results_produces_valid_empty_csv(tmp_path):
    path = tmp_path / "empty.csv"
    write_csv([], str(path))
    with open(path, encoding="utf-8-sig") as f:
        lines = f.readlines()
    assert len(lines) == 1  # header only
    assert "source" in lines[0] and "title" in lines[0]

def test_zero_results_logs_actionable_warning(caplog):
    # ... run pipeline that results in [], check for "broadening" suggestion
    pass
```

---

## 9. Writer Edge Cases — CSV

### EC-070: Field Value Contains a Comma, Quote, or Newline
**Severity:** P1

**Scenario:** `description = 'We need someone who can "think outside the box," and also work nights.'` — contains commas, double quotes, and potentially newlines (from stripped HTML with `<br>` tags converted to `\n`).

**Expected:** `csv.DictWriter` handles RFC 4180 quoting automatically (wraps fields containing commas/quotes/newlines in double quotes, escapes internal quotes by doubling them). No manual escaping needed — but this must be verified, not assumed, since manual string concatenation elsewhere could bypass it.

**Handling:**
```python
# csv.DictWriter handles this correctly BY DEFAULT as long as we use
# writer.writerow(dict) and never manually build CSV lines via string
# concatenation. The only requirement is correct usage:

writer = csv.DictWriter(f, fieldnames=CANONICAL_FIELDS, extrasaction="ignore")
writer.writeheader()
for job in jobs:
    row = {field: job.get(field, "") for field in CANONICAL_FIELDS}
    writer.writerow(row)   # <-- csv module handles quoting/escaping here
```

**Test:**
```python
def test_csv_handles_commas_quotes_newlines(tmp_path):
    jobs = [{
        "source": "naukri", "title": "X", "company": "Y",
        "location": "Z", "link": "https://x.com",
        "posted_at": "", "description": 'Needs "out of the box" thinking, and grit.\nAlso teamwork.'
    }]
    path = tmp_path / "out.csv"
    write_csv(jobs, str(path))

    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["description"] == 'Needs "out of the box" thinking, and grit.\nAlso teamwork.'
```

---

### EC-071: Output File Already Exists with Different Content
**Severity:** P2

**Scenario:** `jobs.csv` exists from a previous run with different data. The current run should overwrite it completely, not append.

**Expected:** `write_csv` opens with mode `'w'` (write, truncate), not `'a'` (append) — confirmed by the architecture spec, but worth an explicit test since "append vs overwrite" bugs are easy to introduce accidentally.

**Handling:**
```python
def write_csv(jobs: list[dict], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # 'w' not 'a'
        # ...
```

**Test:**
```python
def test_csv_overwrites_not_appends(tmp_path):
    path = tmp_path / "out.csv"

    write_csv([{"source": "naukri", "title": "First", "company": "A",
                 "location": "X", "link": "a", "posted_at": "", "description": ""}], str(path))

    write_csv([{"source": "remoteok", "title": "Second", "company": "B",
                 "location": "Y", "link": "b", "posted_at": "", "description": ""}], str(path))

    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 1  # NOT 2 — second write replaced, didn't append
    assert rows[0]["title"] == "Second"
```

---

### EC-072: Output Path is Not Writable (Permission Denied / Disk Full)
**Severity:** P1

**Scenario:** `--output /root/jobs.csv` on a system where the user lacks write permission, or the disk is full.

**Expected:** `OSError` (specifically `PermissionError` or `OSError: [Errno 28] No space left on device`) propagates up to `main()`, where it is caught and reported as a fatal, clear error — distinguished from adapter/network errors, since this is a local environment problem the user must fix.

**Handling:**
```python
# In main():
try:
    write_csv(clean, args.output)
except OSError as e:
    log.error(f"FATAL: Could not write to {args.output}: {e}")
    log.error("Check directory permissions and available disk space.")
    sys.exit(1)
```

**Test:**
```python
def test_permission_error_propagates_with_clear_message(caplog):
    with patch("builtins.open", side_effect=PermissionError("Permission denied")):
        with pytest.raises(SystemExit):
            # ... call main() or a wrapper that catches OSError
            pass
    assert "FATAL" in caplog.text
    assert "permissions" in caplog.text.lower()
```

---

### EC-073: Extremely Long `description` Field (>5000 characters)
**Severity:** P3

**Scenario:** A job description from Firecrawl extraction includes the entire job posting page text, including benefits, company history, EEO statements — potentially several thousand characters.

**Expected:** Truncate to 500 characters (per ARCHITECTURE.md schema spec) for readability in the Sheet/CSV, appending an ellipsis to signal truncation.

**Handling:**
```python
DESCRIPTION_MAX_CHARS = 500

def _truncate_description(text: str, max_chars: int = DESCRIPTION_MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."

# Applied in each adapter after HTML stripping:
job["description"] = self._truncate_description(stripped_text)
```

**Test:**
```python
def test_description_truncated_at_500_chars():
    long_text = "A" * 1000
    result = _truncate_description(long_text)
    assert len(result) == 503  # 500 chars + "..."
    assert result.endswith("...")

def test_short_description_unchanged():
    short_text = "Short description"
    assert _truncate_description(short_text) == short_text
```

---

## 10. Writer Edge Cases — Google Sheets

### EC-080: `GOOGLE_SERVICE_ACCOUNT_JSON` Path Points to Non-Existent File
**Severity:** P1

**Scenario:** `.env` has `GOOGLE_SERVICE_ACCOUNT_JSON=/wrong/path/key.json` — env var is set, but the file doesn't exist (typo, moved file, wrong path copied).

**Expected:** `gspread.service_account(filename=...)` raises `FileNotFoundError`. This must be caught in `write_to_sheet` (or by the caller in `main()`) and reported with the specific path that was attempted, distinct from "env var not set at all" (EC-081).

**Handling:**
```python
def write_to_sheet(jobs: list[dict], sheet_url: str) -> None:
    sa_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not sa_path:
        raise EnvironmentError(
            "GOOGLE_SERVICE_ACCOUNT_JSON not set in .env. "
            "See README Appendix A for setup."
        )
    if not os.path.isfile(sa_path):
        raise FileNotFoundError(
            f"GOOGLE_SERVICE_ACCOUNT_JSON points to '{sa_path}', "
            f"but this file does not exist. Check the path in .env."
        )
    gc = gspread.service_account(filename=sa_path)
    # ...
```

**Test:**
```python
def test_missing_credential_file_raises_clear_error():
    with patch.dict(os.environ, {"GOOGLE_SERVICE_ACCOUNT_JSON": "/nonexistent/path.json"}):
        with pytest.raises(FileNotFoundError, match="/nonexistent/path.json"):
            write_to_sheet([], "https://docs.google.com/spreadsheets/d/xxx")

def test_unset_env_var_raises_environment_error():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(EnvironmentError, match="GOOGLE_SERVICE_ACCOUNT_JSON not set"):
            write_to_sheet([], "https://docs.google.com/spreadsheets/d/xxx")
```

---

### EC-081: Sheet Exists But Not Shared with Service Account (403 from Sheets API)
**Severity:** P1

**Scenario:** Service account JSON is valid and the file path is correct, but the target Sheet was never shared with the service account's email. `gc.open_by_url(sheet_url)` raises `gspread.exceptions.APIError` with a 403 status.

**Expected:** Caught and translated into an actionable message that names the specific remediation (share the Sheet with the service account email, which should be extracted from the JSON for display).

**Handling:**
```python
import json as jsonlib

def write_to_sheet(jobs, sheet_url):
    sa_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    # ... existence checks from EC-080 ...

    gc = gspread.service_account(filename=sa_path)

    try:
        sheet = gc.open_by_url(sheet_url)
    except gspread.exceptions.APIError as e:
        if "403" in str(e) or "PERMISSION_DENIED" in str(e):
            with open(sa_path) as f:
                sa_email = jsonlib.load(f).get("client_email", "<unknown>")
            raise PermissionError(
                f"Google Sheets API returned 403 for {sheet_url}. "
                f"Share this Sheet with the service account email: "
                f"{sa_email} (Editor access required)."
            ) from e
        raise
```

**Test:**
```python
def test_403_error_includes_service_account_email(tmp_path):
    sa_file = tmp_path / "sa.json"
    sa_file.write_text(json.dumps({"client_email": "bot@project.iam.gserviceaccount.com"}))

    with patch.dict(os.environ, {"GOOGLE_SERVICE_ACCOUNT_JSON": str(sa_file)}):
        with patch("gspread.service_account") as mock_sa:
            mock_gc = MagicMock()
            mock_gc.open_by_url.side_effect = gspread.exceptions.APIError(
                MagicMock(json=lambda: {"error": {"code": 403, "status": "PERMISSION_DENIED"}})
            )
            mock_sa.return_value = mock_gc

            with pytest.raises(PermissionError, match="bot@project.iam.gserviceaccount.com"):
                write_to_sheet([], "https://docs.google.com/spreadsheets/d/xxx")
```

---

### EC-082: Sheet URL is Valid Format But Points to a Sheet That Was Deleted
**Severity:** P2

**Scenario:** `sheet_url` is well-formed but the Sheet has been deleted or moved to trash. `gc.open_by_url()` raises `gspread.exceptions.SpreadsheetNotFound`.

**Expected:** Distinct error message from EC-081 (403/permission) vs "not found" — different remediations (recreate/restore the sheet vs. fix sharing).

**Handling:**
```python
    try:
        sheet = gc.open_by_url(sheet_url)
    except gspread.exceptions.SpreadsheetNotFound:
        raise FileNotFoundError(
            f"No Google Sheet found at {sheet_url}. "
            f"It may have been deleted or the URL may be incorrect."
        )
    except gspread.exceptions.APIError as e:
        # ... 403 handling from EC-081
```

**Test:**
```python
def test_deleted_sheet_distinct_error_from_permission_error():
    with patch.dict(os.environ, {"GOOGLE_SERVICE_ACCOUNT_JSON": "/valid/path.json"}):
        with patch("os.path.isfile", return_value=True):
            with patch("gspread.service_account") as mock_sa:
                mock_gc = MagicMock()
                mock_gc.open_by_url.side_effect = gspread.exceptions.SpreadsheetNotFound()
                mock_sa.return_value = mock_gc

                with pytest.raises(FileNotFoundError, match="deleted"):
                    write_to_sheet([], "https://docs.google.com/spreadsheets/d/deleted")
```

---

### EC-083: Row Count Exceeds Google Sheets API Batch Limits
**Severity:** P3

**Scenario:** `append_rows()` is called with a very large number of rows (e.g., 5000+ from a `--limit 5000` run) — Google Sheets API has practical limits on request payload size (~2MB per request, ~10 million cells per sheet).

**Expected:** For Sprint 1's expected scale (50-200 rows), this is a non-issue. Document as a known scale limit; if `--limit` exceeds a threshold (e.g., 1000), log an informational note about potential batching needs.

**Handling:**
```python
SHEETS_BATCH_WARNING_THRESHOLD = 1000

def write_to_sheet(jobs, sheet_url):
    if len(jobs) > SHEETS_BATCH_WARNING_THRESHOLD:
        log.info(
            f"Writing {len(jobs)} rows to Google Sheets — this exceeds "
            f"{SHEETS_BATCH_WARNING_THRESHOLD} rows. If this fails due to "
            f"API payload limits, consider batching append_rows() calls."
        )
    # ... proceed with single append_rows() call; batching is a
    # Sprint 2+ enhancement if ever needed at this scale
```

**Test:**
```python
def test_large_row_count_logs_info(caplog):
    jobs = [{"source": "naukri", "title": f"Job {i}", "company": "X",
             "location": "Y", "link": "z", "posted_at": "", "description": ""}
            for i in range(1500)]
    # ... mock gspread successfully, verify info log fires
    assert "1500 rows" in caplog.text
```

---

## 11. Environment & Configuration Edge Cases

### EC-090: `.env` File Does Not Exist At All
**Severity:** P1

**Scenario:** First-time setup — user clones the repo, runs `python gleaner.py ...` without ever copying `.env.example` to `.env`.

**Expected:** `load_dotenv()` does NOT raise if `.env` doesn't exist (this is `python-dotenv`'s default behavior — it silently does nothing). However, this means `FIRECRAWL_API_KEY` etc. will be `None`, and the relevant adapters will raise `EnvironmentError` at instantiation — which IS the correct behavior, but the error message should reference `.env.example` so the user knows what to do.

**Handling:**
```python
# In boards/wellfound.py and boards/indeed.py __init__:
def __init__(self):
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "FIRECRAWL_API_KEY not set. Copy .env.example to .env and "
            "add your Firecrawl API key (get one at firecrawl.dev)."
        )
    self.app = FirecrawlApp(api_key=api_key)
```

This is already covered by HAR-005/HAR-018 acceptance criteria — EC-090 simply confirms the error message must reference `.env.example` specifically, not just say "not set."

**Test:**
```python
def test_missing_env_file_error_references_env_example():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(EnvironmentError, match=r"\.env\.example"):
            WellfoundAdapter()
```

---

### EC-091: `.env` Contains Trailing Whitespace or Quotes Around Values
**Severity:** P2

**Scenario:** `.env` file has `FIRECRAWL_API_KEY="fc-abc123"` (with quotes) or `FIRECRAWL_API_KEY=fc-abc123 ` (trailing space) — common copy-paste artifacts.

**Expected:** `python-dotenv` handles surrounding quotes correctly by default (strips them). Trailing whitespace, however, is NOT stripped by `python-dotenv` and would be included in the API key, causing authentication failures with a confusing error from Firecrawl/Google rather than a clear "malformed key" error.

**Handling:**
```python
# Defensive stripping at the point of use:
api_key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
if not api_key:
    raise EnvironmentError(...)
```

Apply `.strip()` to every secret read from `os.environ`, not just `FIRECRAWL_API_KEY`.

**Test:**
```python
def test_trailing_whitespace_in_env_var_stripped():
    with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "fc-abc123 \n"}):
        adapter = WellfoundAdapter()
        assert adapter.app.api_key == "fc-abc123"  # no trailing whitespace
```

---

### EC-092: `config.yaml` is Missing or Malformed YAML
**Severity:** P2

**Scenario:** `config.yaml` is accidentally deleted, or has a YAML syntax error (e.g., inconsistent indentation) introduced during editing.

**Expected:** The system falls back to hardcoded defaults rather than crashing — `config.yaml` provides overrides to defaults, not the defaults themselves. A warning is logged if the file is missing or unparseable.

**Handling:**
```python
DEFAULT_CONFIG = {
    "boards": ["naukri", "remoteok", "wellfound", "indeed"],
    "limits": {
        "default_limit": 100,
        "naukri_sleep_seconds": 1,
        "indeed_sleep_seconds": 2,
        "description_max_chars": 500
    },
    "output": {"default_filename": "jobs.csv", "encoding": "utf-8-sig"},
    "logging": {"level": "INFO"}
}

def load_config(path: str = "config.yaml") -> dict:
    if not os.path.isfile(path):
        log.warning(f"{path} not found — using built-in defaults.")
        return DEFAULT_CONFIG
    try:
        with open(path) as f:
            user_config = yaml.safe_load(f) or {}
        # Shallow merge — user_config keys override defaults
        merged = {**DEFAULT_CONFIG, **user_config}
        return merged
    except yaml.YAMLError as e:
        log.warning(f"{path} contains invalid YAML ({e}) — using built-in defaults.")
        return DEFAULT_CONFIG
```

**Test:**
```python
def test_missing_config_yaml_falls_back_to_defaults(caplog):
    config = load_config("/nonexistent/config.yaml")
    assert config == DEFAULT_CONFIG
    assert "not found" in caplog.text

def test_malformed_yaml_falls_back_to_defaults(tmp_path, caplog):
    bad_yaml = tmp_path / "config.yaml"
    bad_yaml.write_text("boards:\n  - naukri\n - remoteok\n")  # bad indentation
    config = load_config(str(bad_yaml))
    assert config == DEFAULT_CONFIG
    assert "invalid YAML" in caplog.text
```

---

### EC-093: `firecrawl-py` SDK Version Mismatch (API Signature Changed)
**Severity:** P2

**Scenario:** `requirements.txt` specifies `firecrawl-py>=0.0.16`, but a newer installed version changes `scrape_url()`'s parameter names or return structure (e.g., `extract` key renamed, or `params` argument restructured).

**Expected:** Pin the version more strictly (`firecrawl-py==0.0.16` rather than `>=`) to avoid silent breakage from upstream changes during the sprint. If a version mismatch causes a `TypeError` on the `scrape_url()` call signature, this should be caught by the general exception handler in the adapter (EC-031 pattern) and logged with the actual error — not crash the pipeline.

**Handling:**
```
# requirements.txt — use exact pins for SDKs with unstable APIs
firecrawl-py==0.0.16
```

```python
# Adapter-level catch-all already covers TypeError from signature mismatches:
try:
    result = self.app.scrape_url(url, params={...})
except TypeError as e:
    log.error(
        f"{self.name}: Firecrawl SDK call failed with TypeError: {e}. "
        f"This may indicate a firecrawl-py version mismatch. "
        f"Check requirements.txt pin (expected firecrawl-py==0.0.16)."
    )
    return []
except Exception as e:
    log.warning(f"{self.name}: Firecrawl error: {e}")
    return []
```

**Test:**
```python
def test_sdk_typeerror_logged_with_version_hint(caplog):
    with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test"}):
        with patch("firecrawl.FirecrawlApp.scrape_url",
                    side_effect=TypeError("scrape_url() got an unexpected keyword argument 'params'")):
            results = WellfoundAdapter().fetch("data scientist", "remote")
    assert results == []
    assert "version mismatch" in caplog.text
```

---

## 12. Security & Credential Edge Cases

### EC-100: Service Account JSON Accidentally Logged on Exception
**Severity:** P0

**Scenario:** An unhandled exception's traceback includes a local variable that contains the full service account JSON contents (e.g., if `gspread.service_account()` is called inside a try/except that logs `locals()` or the exception's `__dict__` for debugging).

**Expected:** No code path ever logs full credential contents, even in error paths. Exception messages reference the FILE PATH, never the file's contents.

**Handling:**
```python
# NEVER do this:
# except Exception as e:
#     log.error(f"Failed with locals: {locals()}")  # <-- could leak credentials

# ALWAYS do this:
except Exception as e:
    log.error(f"Google Sheets write failed: {type(e).__name__}: {e}")
    # Only the exception's string representation, never local variable dumps
```

**Test:** This is enforced by code review discipline + the security audit grep (Phase 7.2 in IMPLEMENTATION_PLAN.md), not by a unit test per se. Add a static check:

```python
# tests/test_security.py
def test_no_locals_dumps_in_writers():
    with open("writers.py") as f:
        source = f.read()
    assert "locals()" not in source
    assert "vars()" not in source  # another way to dump all variables
```

---

### EC-101: `.env` Values Echoed in `--help` or Error Messages
**Severity:** P0

**Scenario:** A poorly written error message includes the actual env var VALUE rather than just its presence/absence: `f"FIRECRAWL_API_KEY={api_key} is invalid"`.

**Expected:** Error messages reference variable NAMES, never VALUES, for any secret-bearing environment variable.

**Handling:**
```python
# NEVER:
# raise ValueError(f"Invalid API key: {api_key}")

# ALWAYS:
if not api_key:
    raise EnvironmentError("FIRECRAWL_API_KEY not set or empty.")
# If the key IS set but rejected by the API (auth failure), the
# resulting exception comes from the Firecrawl SDK itself — verify
# (during testing) that the SDK's error messages don't include the
# full key. If they do, catch and re-raise with a redacted message:

except Exception as e:
    msg = str(e)
    if api_key in msg:
        msg = msg.replace(api_key, "***REDACTED***")
    log.warning(f"Firecrawl auth error: {msg}")
```

**Test:**
```python
def test_invalid_key_error_does_not_echo_key_value(caplog):
    fake_key = "fc-supersecret123"
    with patch.dict(os.environ, {"FIRECRAWL_API_KEY": fake_key}):
        with patch("firecrawl.FirecrawlApp.scrape_url",
                    side_effect=Exception(f"Auth failed for key {fake_key}")):
            WellfoundAdapter().fetch("x", "y")
    assert fake_key not in caplog.text
    assert "REDACTED" in caplog.text
```

---

### EC-102: `git add .` Run Before `.gitignore` is in Place
**Severity:** P0

**Scenario:** During Phase 0, if Cline creates `.env` (with real values, e.g., by mistakenly populating `.env.example` with actual secrets) or `credentials/service_account.json` BEFORE `.gitignore` is created/committed, an early `git add .` could stage them.

**Expected:** `.gitignore` is created in Step 0.2 (scaffold) BEFORE any `.env` population (Step 0.4) or credential placement. The IMPLEMENTATION_PLAN.md ordering already enforces this, but EC-102 documents WHY that ordering matters — it's not arbitrary.

**Handling:** Process discipline + the Phase 7.2 security audit acts as the final backstop:

```bash
# Defense in depth — run this check at the START of Phase 7 (not just end)
# to catch the mistake early if it happened during Phase 0-6:
git status --porcelain | grep -E "^\?\? \.env$|service_account\.json" && \
  echo "WARNING: secret files are untracked but present — verify .gitignore" || \
  echo "OK: no secret files found in working tree status"
```

**Test:** Process/checklist item, not a unit test. Already covered by IMPLEMENTATION_PLAN.md Phase 7.2.

---

### EC-103: Firecrawl or Google API Key Has Broader Permissions Than Needed
**Severity:** P1

**Scenario:** The Google service account is granted Owner/Editor role at the PROJECT level (not just on the specific Sheet), or the Firecrawl API key is a "full account" key rather than a scoped key (if Firecrawl supports scoping).

**Expected:** This is a setup-time concern, not a runtime one — document the principle of least privilege in `README.md` Appendix A:

```markdown
## Security Notes (Appendix A)
- The service account should NOT be granted any project-level IAM roles.
  It only needs access to the specific Sheet(s) it writes to, granted via
  the Sheet's own Share dialog (Editor access on that Sheet only).
- If Firecrawl supports scoped/restricted API keys, prefer those over
  full-account keys for this project.
```

**Test:** Not testable in code — documentation-only mitigation.

---

## 13. Concurrency & State Edge Cases

### EC-110: Running Two Instances of `gleaner.py` Simultaneously, Same `--output`
**Severity:** P2

**Scenario:** User accidentally runs the CLI twice in parallel (e.g., two terminal tabs) with the same `--output jobs.csv`. Both processes open the file for writing; whichever finishes last "wins," but the file could theoretically be in an inconsistent state if both write concurrently (interleaved writes — though Python's file buffering makes true interleaving unlikely for small files, it's not guaranteed).

**Expected:** Sprint 1 does NOT implement file locking — this is a single-user CLI tool, and concurrent runs against the same output file are a user error, not a system fault. Document as a known limitation. The Google Sheets writer has a similar concern (`worksheet.clear()` from one run could clear data mid-write from another), also documented.

**Handling:** None — document:

```markdown
## Known Limitations
- Running multiple instances of gleaner.py concurrently with the same
  --output path or --sheet URL is not supported and may produce
  inconsistent results. Run one instance at a time.
```

**Test:** Not unit-testable — documentation only.

---

### EC-111: `dedupe()` Behavior is Order-Dependent — Adapter Execution Order Matters
**Severity:** P3

**Scenario:** Because `dedupe()` keeps the FIRST occurrence of a `(company, title)` key, and adapters run in a fixed order (`ADAPTER_REGISTRY` order: naukri, remoteok, wellfound, indeed), the SAME job appearing on multiple boards will always be attributed to whichever board appears first in the registry — even if, e.g., the RemoteOK version has a more complete `description`.

**Expected:** This is a deliberate, documented trade-off (see ARCHITECTURE.md ADR-005). Not a bug. However, it means the registry order is a meaningful design choice, not arbitrary — document why Naukri is first (it's the "template" adapter and often has the most location-specific accuracy for India-based searches) and RemoteOK second (most reliable, good descriptions).

**Handling:** None — document the implication of registry order:

```markdown
## Design Note: Adapter Order and Deduplication
ADAPTER_REGISTRY order is: naukri, remoteok, wellfound, indeed.
Because dedupe() keeps the first occurrence of a (company, title) match,
this order determines which board's version of a duplicate listing
"wins" in the final output. This order was chosen because Naukri
typically has the most location-accurate listings for India-based
searches, and RemoteOK typically has the most complete descriptions
among the remaining boards. If output quality issues arise from this
ordering (e.g., a board with less complete data is winning duplicates),
consider reordering ADAPTER_REGISTRY rather than changing dedupe() logic.
```

**Test:**
```python
def test_dedupe_order_dependent_on_registry_order():
    # Simulates the same job from naukri (first) and remoteok (second)
    jobs = [
        {"source": "naukri", "company": "Acme", "title": "Data Scientist",
         "location": "Bangalore", "link": "naukri-link", "description": ""},
        {"source": "remoteok", "company": "acme", "title": "data scientist",
         "location": "Remote", "link": "remoteok-link", "description": "Full JD here"},
    ]
    result = dedupe(jobs)
    assert len(result) == 1
    assert result[0]["source"] == "naukri"  # first occurrence wins, per registry order
```

---

## 14. Live Demo Edge Cases

### EC-120: Internet Connection Drops Mid-Demo
**Severity:** P1 (for the sprint demo specifically)

**Scenario:** During the recorded demo clip, the network connection drops between starting the pipeline run and it completing.

**Expected:** This is a live-environment risk, not a code bug — but the pipeline's per-adapter error isolation (EC-050 pattern) means a mid-run connection drop affects only the adapters that haven't completed yet. Adapters that already returned results keep those results in `all_jobs`. The demo would show some boards succeeding and others failing with connection warnings — not ideal for a demo, but not a crash.

**Mitigation (process, not code):**
```
Pre-demo checklist:
[ ] Run the full pipeline ONCE successfully before recording, to "warm up"
    any DNS caches and confirm connectivity
[ ] Have a pre-generated jobs.csv and a pre-populated Google Sheet ready
    as a fallback — if the live run fails, the demo can show the
    PREVIOUS successful run's artifacts while narrating "here's a run
    I did just before this recording"
[ ] Record on a wired connection if possible, not WiFi
```

**Test:** Not applicable — operational mitigation only.

---

### EC-121: Google Sheet Was Manually Edited Between Runs (Stale Formatting)
**Severity:** P3

**Scenario:** Between the Phase 5 test write and the Phase 6/7 full pipeline run, someone manually adds a column, changes header formatting, or adds a filter view to the Sheet via the UI.

**Expected:** `worksheet.clear()` clears CELL VALUES but does NOT remove filter views, conditional formatting rules, or column width changes. If a manually-added filter view references a column that no longer has matching data after `clear()` + rewrite, the filter view may show "no rows" even though data exists below it.

**Handling:** None in code — document as a demo-prep note:

```markdown
## Demo Prep Note
If the target Google Sheet has been manually edited (extra columns,
filter views, etc.) between test runs, consider creating a FRESH Sheet
for the final demo recording to avoid stale UI elements (filter views,
frozen rows) that could make populated data appear empty in the
recording. worksheet.clear() clears cell values only, not view-level
UI state.
```

**Test:** Not applicable — operational note only.

---

### EC-122: Demo Role/Location Combination Returns Fewer Than 50 Rows on Recording Day
**Severity:** P2

**Scenario:** The role/location combination that worked well during Phase 1-6 development (e.g., "data scientist" / "Bangalore") happens to return fewer listings on the day of recording — job boards' content changes daily.

**Expected:** Pre-test the exact demo command 15-30 minutes before recording (not hours before) to confirm it still yields ≥50 rows. Have a documented fallback query ready.

**Handling:** Process mitigation:

```markdown
## Demo Prep Note
Re-run the exact demo command shortly before recording:
  python gleaner.py --role "data scientist" --location "Bangalore" \
    --output jobs.csv --sheet <URL> --boards all

If final count < 50:
  Fallback query (broader role, pre-tested):
  python gleaner.py --role "engineer" --location "Bangalore" \
    --output jobs.csv --sheet <URL> --boards all

  Or fallback location (Remote tends to have high RemoteOK + Wellfound yield):
  python gleaner.py --role "data scientist" --location "Remote" \
    --output jobs.csv --sheet <URL> --boards all
```

**Test:** Not applicable — operational note only.

---

## 15. Edge Case Test Matrix (Summary)

| ID | Component | Severity | One-Line Description | Test File |
|---|---|---|---|---|
| EC-001 | CLI | P1 | Empty/whitespace `--role` rejected | test_cli.py |
| EC-002 | CLI | P2 | `--limit 0` valid, negative rejected | test_cli.py |
| EC-003 | CLI | P2 | Unknown board names skipped/error if all unknown | test_gleaner.py |
| EC-004 | CLI | P1 | Output directory auto-created | test_gleaner.py |
| EC-005 | CLI | P1 | Special chars in role/location URL-encoded | test_naukri.py, test_indeed.py |
| EC-010 | Naukri | P1 | HTTP 403 → RuntimeError with context | test_naukri.py |
| EC-011 | Naukri | P1 | HTTP 429 → RuntimeError with Retry-After | test_naukri.py |
| EC-012 | Naukri | P1 | 0 cards → warning pointing to selectors.md | test_naukri.py |
| EC-013 | Naukri | P2 | Card missing optional field still included | test_naukri.py |
| EC-014 | Naukri | P2 | Mixed relative/absolute links normalized | test_naukri.py |
| EC-015 | Naukri | P2 | UTF-8 encoding forced | test_naukri.py |
| EC-016 | Naukri | P1 | Request timeout handled | test_naukri.py |
| EC-020 | RemoteOK | P1 | Metadata blob detected by structure | test_remoteok.py |
| EC-021 | RemoteOK | P2 | Missing/malformed `tags` field | test_remoteok.py |
| EC-022 | RemoteOK | P2 | Script/style tags stripped from description | test_remoteok.py |
| EC-023 | RemoteOK | P3 | Cross-board dupes handled by global dedupe | (covered by EC-060) |
| EC-030 | Wellfound | P1 | Empty extract → diagnostic warning | test_wellfound.py |
| EC-031 | Wellfound | P1 | Quota error identified distinctly | test_wellfound.py |
| EC-032 | Wellfound | P2 | Missing location → 'Remote' default | test_wellfound.py |
| EC-033 | Wellfound | P2 | Extraction link accuracy — documented limitation | (docs only) |
| EC-040 | Indeed | P1 | Cloudflare challenge detected | test_indeed.py |
| EC-041 | Indeed | P2 | Sponsored link redirects normalized | test_indeed.py |
| EC-042 | Indeed | P3 | Relative date strings passed through | test_indeed.py |
| EC-043 | Indeed | P3 | ~4-6s latency per call — documented | (docs only) |
| EC-050 | Schema | P0 | Non-list adapter return handled defensively | test_gleaner.py |
| EC-051 | Schema | P3 | Extra fields dropped silently by writers | test_writers.py |
| EC-052 | Schema | P1 | Whitespace-only required field rejected | test_base.py |
| EC-053 | Schema | P2 | `source` mismatch detected | test_base.py |
| EC-060 | Filters | P2 | dedupe on all-identical jobs | test_filters.py |
| EC-061 | Filters | P1 | dedupe handles missing keys | test_filters.py |
| EC-062 | Filters | P3 | Stop-word role — documented | (docs only) |
| EC-063 | Filters | P3 | Location substring matching — documented | (docs only) |
| EC-064 | Filters | P1 | All-filtered-out → valid empty CSV + warning | test_filters.py, test_writers.py |
| EC-070 | CSV Writer | P1 | Commas/quotes/newlines in fields handled | test_writers.py |
| EC-071 | CSV Writer | P2 | Overwrite, not append | test_writers.py |
| EC-072 | CSV Writer | P1 | Permission/disk errors reported clearly | test_writers.py |
| EC-073 | CSV Writer | P3 | Description truncated at 500 chars | test_writers.py |
| EC-080 | Sheets Writer | P1 | Missing credential file → clear error | test_writers.py |
| EC-081 | Sheets Writer | P1 | 403 → service account email in error | test_writers.py |
| EC-082 | Sheets Writer | P2 | Deleted sheet → distinct error | test_writers.py |
| EC-083 | Sheets Writer | P3 | Large row counts → informational log | test_writers.py |
| EC-090 | Config | P1 | Missing `.env` → error references `.env.example` | test_wellfound.py, test_indeed.py |
| EC-091 | Config | P2 | Trailing whitespace in env vars stripped | test_wellfound.py |
| EC-092 | Config | P2 | Missing/malformed config.yaml → defaults | test_gleaner.py |
| EC-093 | Config | P2 | Firecrawl SDK version mismatch handled | test_wellfound.py |
| EC-100 | Security | P0 | No `locals()`/`vars()` dumps in writers.py | test_security.py |
| EC-101 | Security | P0 | Secrets never echoed in error messages | test_wellfound.py |
| EC-102 | Security | P0 | `.gitignore` precedes secret file creation | (process checklist) |
| EC-103 | Security | P1 | Least-privilege credentials — documented | (docs only) |
| EC-110 | Concurrency | P2 | Concurrent runs — documented limitation | (docs only) |
| EC-111 | Concurrency | P3 | dedupe order depends on registry order — documented | test_filters.py |
| EC-120 | Demo | P1 | Network drop mid-demo — operational mitigation | (process checklist) |
| EC-121 | Demo | P3 | Stale Sheet UI state — operational note | (process checklist) |
| EC-122 | Demo | P2 | Demo query yields <50 rows — fallback queries | (process checklist) |

**Total edge cases documented: 54**

### Severity Distribution

| Severity | Count |
|---|---|
| P0 (Critical) | 4 |
| P1 (High) | 19 |
| P2 (Medium) | 21 |
| P3 (Low) | 10 |

### Coverage by Phase (cross-reference to IMPLEMENTATION_PLAN.md)

| Implementation Phase | Edge Cases to Address During That Phase |
|---|---|
| Phase 0 (Scaffold) | EC-001 through EC-005 (CLI), EC-090/091/092 (config) |
| Phase 1 (Naukri) | EC-010 through EC-016 |
| Phase 2 (RemoteOK) | EC-020 through EC-023 |
| Phase 3A (Wellfound) | EC-030 through EC-033, EC-093 |
| Phase 3B (Indeed) | EC-040 through EC-043 |
| Phase 4 (Filters) | EC-060 through EC-064, EC-111 |
| Phase 5 (Writers) | EC-070 through EC-083 |
| Phase 6 (Integration) | EC-050 through EC-053, EC-064 |
| Phase 7 (Polish/Push) | EC-100 through EC-103, EC-110, EC-120 through EC-122 |
