# EVALUATION_PLAN.md — The Gleaner
**Multi-Board Job Scraper | Sprint Build 1**
Version: 1.0 | Last Updated: 2026-06-14

---

## Purpose

This document defines how The Gleaner's quality is measured — at the unit level, the integration level, the data-output level, and the portfolio-artifact level. It complements the other planning documents:

- `PROBLEM_STATEMENT.md` defines *what done looks like* (acceptance criteria per ticket)
- `IMPLEMENTATION_PLAN.md` defines *how to build it* (phase-by-phase steps)
- `EDGE_CASE_PLAN.md` defines *what could go wrong* (54 documented edge cases)
- `EVALUATION_PLAN.md` (this document) defines *how to verify it actually works, and how well*

**Governing principle:** A pipeline that "runs without crashing" and a pipeline that "produces a dataset someone would trust" are different bars. This document evaluates against the second bar. Every metric here is measurable — either by an automated script, a test suite, or a documented manual checklist with a pass/fail outcome.

---

## Table of Contents

1. [Evaluation Philosophy & Dimensions](#1-evaluation-philosophy--dimensions)
2. [Test Coverage Evaluation](#2-test-coverage-evaluation)
3. [Functional Correctness — Per-Adapter Evaluation](#3-functional-correctness--per-adapter-evaluation)
4. [Data Quality Evaluation](#4-data-quality-evaluation)
5. [Pipeline-Level (End-to-End) Evaluation](#5-pipeline-level-end-to-end-evaluation)
6. [Resilience & Fallback Evaluation](#6-resilience--fallback-evaluation)
7. [Performance Evaluation](#7-performance-evaluation)
8. [Security Evaluation](#8-security-evaluation)
9. [Code Quality Evaluation](#9-code-quality-evaluation)
10. [Artifact & Demo Evaluation](#10-artifact--demo-evaluation)
11. [Automated Evaluation Script](#11-automated-evaluation-script)
12. [Scoring Rubric & Go/No-Go Matrix](#12-scoring-rubric--gono-go-matrix)
13. [Post-Sprint Continuous Evaluation](#13-post-sprint-continuous-evaluation)
14. [CONDUCTOR Readiness Evaluation](#14-conductor-readiness-evaluation)
15. [Evaluation Report Template](#15-evaluation-report-template)

---

## 1. Evaluation Philosophy & Dimensions

### 1.1 Six Evaluation Dimensions

Every component of The Gleaner is evaluated along up to six dimensions. Not every dimension applies to every component (e.g., "performance" is less relevant for `filters.py` than for the Indeed adapter).

```
┌─────────────────────────────────────────────────────────────┐
│  1. CORRECTNESS    Does it do what the spec says?            │
│  2. DATA QUALITY   Is the output trustworthy and clean?      │
│  3. RESILIENCE     Does it degrade gracefully under failure?  │
│  4. PERFORMANCE    Is it fast enough for its use case?        │
│  5. SECURITY       Are credentials and data handled safely?   │
│  6. ARTIFACT READY Is the output presentable to a stranger?   │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Evaluation Timing

```
DURING DEVELOPMENT (Phases 0-6):
  → Unit tests run after each phase (pytest)
  → Manual isolated-adapter tests (per IMPLEMENTATION_PLAN.md)
  → Checkpoint gates per phase

AT INTEGRATION (Phase 6 end):
  → End-to-end pipeline run
  → Data quality scan on jobs.csv
  → Performance timing capture

AT SHIP (Phase 7):
  → Security audit (mandatory gate)
  → Artifact evaluation (repo, Sheet, demo clip)
  → Final scoring against Go/No-Go matrix

POST-SPRINT (ongoing):
  → Weekly data quality re-runs (drift detection)
  → CONDUCTOR readiness re-assessment as components evolve
```

### 1.3 Relationship to PROBLEM_STATEMENT.md

Every Definition of Done in `PROBLEM_STATEMENT.md` (HAR-001 through HAR-018) maps to one or more evaluation checks in this document. This document does not redefine acceptance criteria — it defines *how to measure* whether they were met, with concrete commands and scoring.

---

## 2. Test Coverage Evaluation

### 2.1 Coverage Targets

| Module | Target Line Coverage | Target Branch Coverage | Rationale |
|---|---|---|---|
| `filters.py` | 100% | 100% | Pure functions, no excuse for gaps; this is the easiest module to fully cover |
| `writers.py` | ≥90% | ≥80% | gspread error paths are hard to fully simulate; CSV paths must be 100% |
| `boards/base.py` | 100% | 100% | The contract — every validation branch must be tested |
| `boards/naukri.py` | ≥75% | ≥65% | Selector-dependent parsing is hard to fully mock; error paths covered |
| `boards/remoteok.py` | ≥85% | ≥75% | Most deterministic adapter — should be near-complete |
| `boards/wellfound.py` | ≥75% | ≥65% | Firecrawl response variability limits exhaustive branch coverage |
| `boards/indeed.py` | ≥75% | ≥65% | Same as Wellfound, plus Cloudflare-detection branches |
| `gleaner.py` | ≥80% | ≥70% | Orchestration logic — error isolation paths must be covered |

### 2.2 Coverage Measurement

```bash
pip install pytest-cov

pytest tests/ --cov=. --cov-report=term-missing --cov-report=html \
  --cov-config=.coveragerc
```

```ini
# .coveragerc
[run]
omit =
    tests/*
    venv/*
    */__init__.py

[report]
exclude_lines =
    pragma: no cover
    if __name__ == .__main__.:
    raise NotImplementedError
```

### 2.3 Coverage Evaluation Output Format

```bash
# Run and capture summary
pytest tests/ --cov=. --cov-report=term-missing | tee coverage_report.txt
```

Expected terminal output shape:
```
Name                   Stmts   Miss  Cover   Missing
----------------------------------------------------
filters.py                28      0   100%
writers.py                45      4    91%   88-91
boards/base.py            22      0   100%
boards/naukri.py           67     14    79%   102-115
boards/remoteok.py         38      4    89%   55-58
boards/wellfound.py        41      9    78%   70-78
boards/indeed.py           58     13    78%   95-107
gleaner.py               52      9    83%   120-128
----------------------------------------------------
TOTAL                     351     53    85%
```

### 2.4 Coverage Gate

```
[ ] filters.py == 100% line coverage (non-negotiable — Phase 4 gate)
[ ] boards/base.py == 100% line coverage (non-negotiable — Phase 0 gate)
[ ] writers.py CSV path == 100%; overall ≥ 90%
[ ] All four adapters ≥ 75% line coverage
[ ] gleaner.py ≥ 80% line coverage
[ ] TOTAL coverage ≥ 80%
```

**If TOTAL < 80% at Phase 7:** Identify the highest-impact missing lines (usually error-handling branches in adapters) and prioritize 2-3 additional tests over polish tasks. Coverage gaps in error paths are the most likely place for EDGE_CASE_PLAN.md regressions to hide.

---

## 3. Functional Correctness — Per-Adapter Evaluation

### 3.1 Adapter Evaluation Checklist Template

Each adapter is evaluated against the same eight-point checklist. This is run once per adapter during its implementation phase, and again during Phase 6 integration.

```
┌────────────────────────────────────────────────────────────────┐
│ ADAPTER EVALUATION CHECKLIST — applies to all 4 adapters        │
├────────────────────────────────────────────────────────────────┤
│ [ ] 1. Returns list[dict], never None, on success                │
│ [ ] 2. Returns [] (not exception) on 0 results                   │
│ [ ] 3. Returns [] (not crash) on network/API error                │
│ [ ] 4. Every returned dict passes _validate_schema()              │
│ [ ] 5. source field matches adapter name exactly                  │
│ [ ] 6. All link values are absolute URLs (https://)               │
│ [ ] 7. No HTML tags in any string field                           │
│ [ ] 8. Logs are informative (board name, count, or warning reason)│
└────────────────────────────────────────────────────────────────┘
```

### 3.2 Naukri-Specific Evaluation

| Check | Method | Pass Criteria |
|---|---|---|
| URL slug correctness | `adapter._slugify("Data Scientist")` | Returns `"data-scientist"` |
| Live fetch returns results | `adapter.fetch("data scientist", "bangalore")` | `len(results) >= 1` for a common role/location |
| Selector currency | Compare `selectors.md` date to today | If >7 days old, flag for re-verification |
| Rate limit courtesy | Inspect adapter source for `time.sleep(1)` | Present after the request call |
| Encoding correctness | Fetch a listing with a non-ASCII company name | Company name renders correctly, no mojibake |
| 403/429 handling | Mock 403/429 response | Raises `RuntimeError` with status code in message |
| 0-results handling | Mock 200 response with no matching selectors | Returns `[]`, logs warning referencing `selectors.md` |

**Naukri Evaluation Score:** `(checks passed) / 7`

### 3.3 RemoteOK-Specific Evaluation

| Check | Method | Pass Criteria |
|---|---|---|
| Metadata blob excluded | `adapter.fetch("python", "remote")` | No result has `position` absent or looks like metadata |
| Live fetch returns results | Run with common role e.g. "developer" | `len(results) >= 1` |
| Tag matching works | Job with role keyword only in `tags`, not `title` | Job is included |
| HTML stripped from description | Inspect `description` field of any result | No `<`/`>` characters present |
| Location defaults correctly | Job with empty/null location in raw API | `location == "Remote"` in output |
| Non-200 handling | Mock 500 response | Returns `[]`, logs warning |

**RemoteOK Evaluation Score:** `(checks passed) / 6`

### 3.4 Wellfound-Specific Evaluation

| Check | Method | Pass Criteria |
|---|---|---|
| EnvironmentError on missing key | Instantiate with `FIRECRAWL_API_KEY` unset | Raises `EnvironmentError` mentioning `.env.example` |
| Live fetch returns results OR graceful empty | `adapter.fetch("data scientist", "remote")` | `len(results) >= 0`, no exception |
| Extract schema correctness | Inspect code for required schema fields | `title`, `company`, `link` marked required |
| Quota error distinctly logged | Mock Firecrawl exception with "quota" in message | Warning log contains "quota" |
| Location defaults correctly | Job with missing location in extract result | `location == "Remote"` |

**Wellfound Evaluation Score:** `(checks passed) / 5`

### 3.5 Indeed-Specific Evaluation

| Check | Method | Pass Criteria |
|---|---|---|
| EnvironmentError on missing key | Instantiate with `FIRECRAWL_API_KEY` unset | Raises `EnvironmentError` mentioning `.env.example` |
| URL targets `in.indeed.com` | `adapter._build_url("data scientist", "bangalore")` | URL contains `in.indeed.com` |
| Wait action present | Inspect code for Firecrawl `actions` param | Contains `{"type": "wait", "milliseconds": 2000}` (or higher) |
| Live fetch returns results OR graceful empty | `adapter.fetch("data scientist", "bangalore")` | `len(results) >= 0`, no exception |
| Relative links normalized | `adapter._absolute_link("/pagead/clk?...")` | Returns `https://in.indeed.com/pagead/clk?...` |
| Cloudflare challenge detected | Mock response with Cloudflare markdown markers | Warning log mentions "Cloudflare" |
| Publisher API fallback exists | Inspect code for `_fetch_via_publisher_api` method | Method exists, even if not called by default |
| Post-call sleep present | Inspect code for `time.sleep(2)` after scrape | Present |

**Indeed Evaluation Score:** `(checks passed) / 8`

### 3.6 Per-Adapter Evaluation Summary Table (Fill During Phase 6)

| Adapter | Score | Live Results? | Notes |
|---|---|---|---|
| Naukri | __ / 7 | Y / N / Pivot used | |
| RemoteOK | __ / 6 | Y / N | |
| Wellfound | __ / 5 | Y / N / Pivot used | |
| Indeed | __ / 8 | Y / N / Pivot used | |

**Minimum bar for Phase 6 → Phase 7 transition:** At least 2 adapters with live results AND all 4 adapters scoring ≥80% on their checklist (live results not required if pivot documented).

---

## 4. Data Quality Evaluation

### 4.1 Field-Level Quality Metrics

For the final `jobs.csv` (post-filter, post-dedupe), compute the following metrics per field:

| Field | Metric | Target | Critical Threshold |
|---|---|---|---|
| `source` | % rows with valid value (one of 4 board names) | 100% | <100% = P0 bug |
| `title` | % rows non-empty | 100% | <100% = P0 bug |
| `title` | % rows containing HTML markers (`<`, `&amp;`, etc.) | 0% | >0% = P1 bug |
| `company` | % rows non-empty | 100% | <100% = P0 bug |
| `location` | % rows non-empty | 100% | <100% = P0 bug |
| `location` | % rows equal to `'Remote'` (sanity — should be >0% if RemoteOK/Wellfound active) | >0% (if those boards active) | N/A |
| `link` | % rows starting with `https://` | 100% | <100% = P0 bug |
| `link` | % rows that are unique (no duplicate URLs) | ≥95% | <90% = investigate dedupe |
| `posted_at` | % rows non-empty (informational — not all boards provide this) | report only | N/A |
| `description` | % rows non-empty | report only (varies by board mix) | N/A |
| `description` | % rows containing HTML markers | 0% | >0% = P1 bug |
| `description` | Max length observed | ≤503 (500 + "...") | >503 = truncation bug |

### 4.2 Row-Level Quality Metrics

| Metric | Target | Notes |
|---|---|---|
| Total rows (post-dedupe, pre-limit) | ≥50 | Sprint 1 primary success criterion |
| Distinct `source` values represented | ≥2 (target 3-4) | Fewer indicates adapter failures |
| Duplicate `(company, title)` pairs remaining | 0 | dedupe() should guarantee this |
| Rows where `location` doesn't match query AND isn't `'Remote'` | 0 | filter_by_location() should guarantee this |
| Rows where neither `title` nor `description` contains a role keyword | 0 | filter_by_role() should guarantee this |

### 4.3 Data Quality Evaluation Script

```python
# evaluate_data_quality.py
import csv
import re
import sys
from collections import Counter

HTML_MARKER_PATTERN = re.compile(r'<[a-zA-Z/][^>]*>|&[a-z]+;')
VALID_SOURCES = {"naukri", "remoteok", "wellfound", "indeed"}

def evaluate(csv_path: str, query_role: str, query_location: str) -> dict:
    with open(csv_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    n = len(rows)
    if n == 0:
        return {"total_rows": 0, "status": "EMPTY — no rows to evaluate"}

    report = {"total_rows": n}

    # Source validity
    sources = Counter(r["source"] for r in rows)
    report["source_distribution"] = dict(sources)
    report["invalid_sources"] = sum(
        1 for r in rows if r["source"] not in VALID_SOURCES
    )

    # Required field completeness
    for field in ["title", "company", "location", "link"]:
        empty = sum(1 for r in rows if not r.get(field, "").strip())
        report[f"{field}_empty_count"] = empty
        report[f"{field}_completeness_pct"] = round(100 * (n - empty) / n, 1)

    # HTML markers
    for field in ["title", "company", "description"]:
        with_html = sum(
            1 for r in rows if HTML_MARKER_PATTERN.search(r.get(field, ""))
        )
        report[f"{field}_html_marker_count"] = with_html

    # Link format
    invalid_links = sum(
        1 for r in rows if not r.get("link", "").startswith("https://")
    )
    report["invalid_link_count"] = invalid_links

    # Link uniqueness
    links = [r["link"] for r in rows]
    report["unique_link_pct"] = round(100 * len(set(links)) / n, 1)

    # Duplicate (company, title) pairs
    pairs = [(r["company"].strip().lower(), r["title"].strip().lower()) for r in rows]
    pair_counts = Counter(pairs)
    duplicates = sum(c - 1 for c in pair_counts.values() if c > 1)
    report["duplicate_company_title_pairs"] = duplicates

    # Role/location relevance (sanity re-check)
    role_keywords = query_role.lower().split()
    loc_query = query_location.lower()
    role_mismatches = 0
    location_mismatches = 0
    for r in rows:
        haystack = (r.get("title", "") + " " + r.get("description", "")).lower()
        if not any(kw in haystack for kw in role_keywords):
            role_mismatches += 1
        loc = r.get("location", "").lower()
        if loc_query not in loc and loc != "remote":
            location_mismatches += 1
    report["role_mismatches"] = role_mismatches
    report["location_mismatches"] = location_mismatches

    # posted_at / description fill rates (informational)
    report["posted_at_fill_pct"] = round(
        100 * sum(1 for r in rows if r.get("posted_at", "").strip()) / n, 1
    )
    report["description_fill_pct"] = round(
        100 * sum(1 for r in rows if r.get("description", "").strip()) / n, 1
    )

    # Description length check
    max_desc_len = max((len(r.get("description", "")) for r in rows), default=0)
    report["max_description_length"] = max_desc_len

    return report


def print_report(report: dict):
    print("=" * 60)
    print("DATA QUALITY EVALUATION REPORT")
    print("=" * 60)
    for key, value in report.items():
        print(f"{key:35s}: {value}")
    print("=" * 60)

    # Pass/fail summary
    failures = []
    if report.get("total_rows", 0) < 50:
        failures.append(f"total_rows ({report.get('total_rows')}) < 50")
    if report.get("invalid_sources", 1) > 0:
        failures.append(f"invalid_sources = {report.get('invalid_sources')}")
    for field in ["title", "company", "location", "link"]:
        if report.get(f"{field}_completeness_pct", 0) < 100:
            failures.append(f"{field}_completeness_pct < 100%")
    for field in ["title", "company", "description"]:
        if report.get(f"{field}_html_marker_count", 0) > 0:
            failures.append(f"{field}_html_marker_count > 0")
    if report.get("invalid_link_count", 1) > 0:
        failures.append(f"invalid_link_count = {report.get('invalid_link_count')}")
    if report.get("duplicate_company_title_pairs", 1) > 0:
        failures.append(f"duplicate_company_title_pairs = {report.get('duplicate_company_title_pairs')}")
    if report.get("role_mismatches", 1) > 0:
        failures.append(f"role_mismatches = {report.get('role_mismatches')}")
    if report.get("location_mismatches", 1) > 0:
        failures.append(f"location_mismatches = {report.get('location_mismatches')}")
    if report.get("max_description_length", 0) > 503:
        failures.append(f"max_description_length = {report.get('max_description_length')} > 503")

    print()
    if not failures:
        print("RESULT: PASS — all data quality checks satisfied")
    else:
        print(f"RESULT: {len(failures)} CHECK(S) FAILED")
        for f in failures:
            print(f"  - {f}")

    return len(failures) == 0


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "jobs.csv"
    role = sys.argv[2] if len(sys.argv) > 2 else "data scientist"
    location = sys.argv[3] if len(sys.argv) > 3 else "bangalore"

    report = evaluate(csv_path, role, location)
    passed = print_report(report)
    sys.exit(0 if passed else 1)
```

### 4.4 Running the Data Quality Evaluation

```bash
python evaluate_data_quality.py jobs.csv "data scientist" "bangalore"
```

Expected output (example with a healthy dataset):
```
============================================================
DATA QUALITY EVALUATION REPORT
============================================================
total_rows                        : 67
source_distribution                : {'naukri': 22, 'remoteok': 15, 'wellfound': 12, 'indeed': 18}
invalid_sources                    : 0
title_empty_count                  : 0
title_completeness_pct             : 100.0
company_empty_count                : 0
company_completeness_pct           : 100.0
location_empty_count                : 0
location_completeness_pct          : 100.0
link_empty_count                    : 0
link_completeness_pct               : 100.0
title_html_marker_count             : 0
company_html_marker_count           : 0
description_html_marker_count       : 0
invalid_link_count                  : 0
unique_link_pct                     : 98.5
duplicate_company_title_pairs       : 0
role_mismatches                     : 0
location_mismatches                 : 0
posted_at_fill_pct                  : 71.6
description_fill_pct                : 88.1
max_description_length              : 503
============================================================

RESULT: PASS — all data quality checks satisfied
```

### 4.5 Data Quality Gate

```
[ ] Script exits with code 0 (all checks passed)
[ ] total_rows >= 50
[ ] All four required fields at 100% completeness
[ ] Zero HTML markers in any field
[ ] Zero invalid links
[ ] Zero duplicate (company, title) pairs
[ ] Zero role/location mismatches
```

**This gate runs at the end of Phase 6**, before proceeding to Phase 7 (Polish, Push & Demo). A failing gate here means the public Sheet/repo would showcase flawed data — fix before shipping.

---

## 5. Pipeline-Level (End-to-End) Evaluation

### 5.1 End-to-End Test Scenarios

| Scenario | Command | Expected Outcome |
|---|---|---|
| Happy path, all boards | `--role "data scientist" --location "bangalore" --boards all --output jobs.csv --sheet <URL>` | ≥50 rows, all 4 sources represented (or documented pivots), Sheet populated |
| Single board | `--role "python" --location "remote" --boards remoteok --output rok.csv` | Only `source=remoteok` rows |
| Unknown board mixed in | `--role "x" --location "y" --boards naukri,foo --output x.csv` | Warning logged for "foo", naukri still runs |
| Zero-limit | `--role "x" --location "y" --limit 0 --output x.csv` | Header-only CSV, 0 data rows |
| No `--sheet` flag | `--role "x" --location "y" --output x.csv` | CSV written, no Sheets call attempted, no error |
| Invalid `--sheet` URL | `--role "x" --location "y" --output x.csv --sheet "not-a-url"` | CSV written successfully; Sheets write fails with caught warning, pipeline still exits 0 |
| All adapters fail | (simulate via invalid FIRECRAWL key + Naukri 403 mock + RemoteOK down) | Empty `all_jobs`, pipeline completes, header-only CSV, warning about 0 results with broadening suggestion |
| Very broad role | `--role "engineer" --location "remote" --boards all --output broad.csv` | Should comfortably exceed 50 rows — useful as a fallback demo query |

### 5.2 End-to-End Evaluation Script

```python
# evaluate_pipeline.py
import subprocess
import csv
import time
import sys

SCENARIOS = [
    {
        "name": "happy_path_all_boards",
        "args": ["--role", "data scientist", "--location", "bangalore",
                 "--boards", "all", "--output", "eval_happy.csv"],
        "min_rows": 50,
        "expect_zero_exit": True,
    },
    {
        "name": "single_board_remoteok",
        "args": ["--role", "python developer", "--location", "remote",
                 "--boards", "remoteok", "--output", "eval_single.csv"],
        "min_rows": 1,
        "expect_zero_exit": True,
        "expect_only_source": "remoteok",
    },
    {
        "name": "zero_limit",
        "args": ["--role", "data scientist", "--location", "bangalore",
                 "--limit", "0", "--boards", "all", "--output", "eval_zero.csv"],
        "min_rows": 0,
        "max_rows": 0,
        "expect_zero_exit": True,
    },
    {
        "name": "unknown_board_mixed",
        "args": ["--role", "data scientist", "--location", "bangalore",
                 "--boards", "naukri,foo", "--output", "eval_unknown.csv"],
        "min_rows": 0,  # naukri may or may not return results; just check it doesn't crash
        "expect_zero_exit": True,
        "expect_log_contains": "Unknown board 'foo'",
    },
]


def run_scenario(scenario: dict) -> dict:
    start = time.time()
    result = subprocess.run(
        ["python", "gleaner.py"] + scenario["args"],
        capture_output=True, text=True, timeout=180
    )
    elapsed = time.time() - start

    outcome = {"name": scenario["name"], "elapsed_seconds": round(elapsed, 1)}
    outcome["exit_code"] = result.returncode
    outcome["exit_code_ok"] = (
        (result.returncode == 0) == scenario.get("expect_zero_exit", True)
    )

    output_path = None
    for i, arg in enumerate(scenario["args"]):
        if arg == "--output":
            output_path = scenario["args"][i + 1]
    outcome["output_path"] = output_path

    if output_path:
        try:
            with open(output_path, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            outcome["row_count"] = len(rows)
            outcome["min_rows_ok"] = len(rows) >= scenario.get("min_rows", 0)
            if "max_rows" in scenario:
                outcome["max_rows_ok"] = len(rows) <= scenario["max_rows"]
            if "expect_only_source" in scenario:
                sources = {r["source"] for r in rows}
                outcome["source_check_ok"] = sources <= {scenario["expect_only_source"]}
        except FileNotFoundError:
            outcome["row_count"] = None
            outcome["min_rows_ok"] = False

    if "expect_log_contains" in scenario:
        outcome["log_check_ok"] = scenario["expect_log_contains"] in (result.stdout + result.stderr)

    return outcome


def main():
    results = [run_scenario(s) for s in SCENARIOS]

    print("=" * 70)
    print("PIPELINE-LEVEL EVALUATION")
    print("=" * 70)

    all_pass = True
    for r in results:
        checks = {k: v for k, v in r.items() if k.endswith("_ok")}
        passed = all(checks.values()) if checks else True
        status = "PASS" if passed else "FAIL"
        all_pass &= passed
        print(f"\n[{status}] {r['name']}  ({r['elapsed_seconds']}s)")
        for k, v in r.items():
            print(f"    {k}: {v}")

    print("\n" + "=" * 70)
    print(f"OVERALL: {'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
```

### 5.3 Pipeline-Level Gate

```
[ ] happy_path_all_boards: exit 0, >=50 rows
[ ] single_board_remoteok: exit 0, only source=remoteok present
[ ] zero_limit: exit 0, 0 data rows (header only)
[ ] unknown_board_mixed: exit 0, "Unknown board 'foo'" logged, naukri still attempted
[ ] All elapsed times reported and reviewed against Section 7 (Performance)
```

---

## 6. Resilience & Fallback Evaluation

### 6.1 Resilience Test Matrix

This evaluates the system's behavior when each adapter individually fails — verifying error isolation (ARCHITECTURE.md Section 8.2).

| Failure Injected | How to Simulate | Expected Pipeline Behavior |
|---|---|---|
| Naukri returns 403 | Mock `requests.get` to return 403 for naukri URL only | Pipeline logs warning for naukri, continues; other 3 boards' results present in output |
| RemoteOK API down (500) | Mock 500 response | Pipeline logs warning, continues with other 3 boards |
| Wellfound — missing `FIRECRAWL_API_KEY` | Unset env var, run with `--boards wellfound,remoteok` | wellfound logged as ERROR (EnvironmentError) and skipped; remoteok still runs |
| Indeed — Cloudflare block | Mock Firecrawl response with Cloudflare markdown markers | Pipeline logs "Cloudflare" warning, continues with other boards |
| Google Sheets — bad URL | `--sheet "not-a-valid-sheet-url"` | CSV written successfully; Sheets warning logged; exit code 0 |
| Google Sheets — 403 (not shared) | Mock gspread 403 on a validly-formatted URL | CSV written successfully; warning includes service account email; exit code 0 |
| ALL adapters fail simultaneously | Combine all of the above | Pipeline completes; header-only CSV written; "0 jobs" warning with broadening suggestion; exit code 0 (not a crash) |

### 6.2 Resilience Evaluation Script (pytest-based)

```python
# tests/test_resilience.py
import subprocess
import csv
import os
from unittest.mock import patch
import pytest


def test_naukri_403_does_not_block_other_boards(monkeypatch):
    """Simulates Naukri 403 — pipeline should still produce results
    from other boards if they're functional."""
    # This is an integration-style test; in CI, mock at the requests level
    # for naukri specifically while allowing other adapters through.
    pass  # implementation depends on test harness mocking strategy


def test_missing_firecrawl_key_skips_only_firecrawl_adapters(monkeypatch, tmp_path):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    output = tmp_path / "out.csv"

    result = subprocess.run(
        ["python", "gleaner.py", "--role", "python", "--location", "remote",
         "--boards", "wellfound,remoteok", "--output", str(output)],
        capture_output=True, text=True
    )

    assert result.returncode == 0
    assert "wellfound" in result.stderr.lower() or "wellfound" in result.stdout.lower()
    assert "skipped" in (result.stdout + result.stderr).lower()
    # CSV should still exist (RemoteOK ran)
    assert output.exists()


def test_invalid_sheet_url_does_not_block_csv(tmp_path):
    output = tmp_path / "out.csv"

    result = subprocess.run(
        ["python", "gleaner.py", "--role", "python", "--location", "remote",
         "--boards", "remoteok", "--output", str(output),
         "--sheet", "https://docs.google.com/spreadsheets/d/INVALID_ID_XXXX"],
        capture_output=True, text=True
    )

    assert result.returncode == 0
    assert output.exists()
    assert "Google Sheets" in (result.stdout + result.stderr)


def test_all_adapters_fail_produces_valid_empty_csv(tmp_path, monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    output = tmp_path / "out.csv"

    # Use boards that will fail without proper setup
    result = subprocess.run(
        ["python", "gleaner.py", "--role", "zzzznonexistentrole",
         "--location", "zzzznonexistentlocation",
         "--boards", "wellfound,indeed", "--output", str(output)],
        capture_output=True, text=True
    )

    assert result.returncode == 0  # must not crash
    assert output.exists()
    with open(output, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 0
    assert "0 jobs" in (result.stdout + result.stderr) or "broadening" in (result.stdout + result.stderr).lower()
```

### 6.3 Resilience Gate

```
[ ] Single-adapter failure (any of the 4) does not produce non-zero exit code
[ ] Single-adapter failure does not prevent CSV from being written
[ ] Missing Firecrawl key skips ONLY Wellfound/Indeed, not Naukri/RemoteOK
[ ] Invalid Sheet URL does not prevent CSV from being written
[ ] All-adapters-fail scenario produces valid header-only CSV + actionable warning
[ ] No scenario produces a Python traceback in stdout/stderr (all exceptions caught
    and logged via the logging module, not printed raw)
```

---

## 7. Performance Evaluation

### 7.1 Per-Adapter Latency Budget

| Adapter | Expected Latency (single fetch) | Acceptable Range | Flag If |
|---|---|---|---|
| Naukri | 1-3s (request + 1s sleep + parse) | <5s | >8s |
| RemoteOK | <1s (single API call, no sleep) | <2s | >5s |
| Wellfound | 3-8s (Firecrawl rendering) | <15s | >25s |
| Indeed | 4-8s (2s wait + processing + 2s sleep) | <15s | >25s |

### 7.2 Full Pipeline Latency Budget

```
Sequential execution (ADR-002):
  Naukri:     ~2s
  RemoteOK:   ~1s
  Wellfound:  ~5s
  Indeed:     ~6s
  ─────────────────
  Fetch total: ~14s

Filter pipeline (dedupe, role, location): <0.1s for <1000 rows
  — negligible, pure in-memory operations

CSV write: <0.1s for <1000 rows

Sheets write: 1-3s (network round trip to Sheets API)

─────────────────────────────────────────
TOTAL EXPECTED: ~15-20 seconds end to end
ACCEPTABLE RANGE: <30 seconds
FLAG IF: >45 seconds (investigate which adapter is slow)
```

### 7.3 Performance Measurement Script

```python
# evaluate_performance.py
import time
import sys
from dotenv import load_dotenv

load_dotenv()

from boards.naukri import NaukriAdapter
from boards.remoteok import RemoteOKAdapter
from boards.wellfound import WellfoundAdapter
from boards.indeed import IndeedAdapter
from filters import dedupe, filter_by_role, filter_by_location
from writers import write_csv

ADAPTERS = {
    "naukri": NaukriAdapter,
    "remoteok": RemoteOKAdapter,
    "wellfound": WellfoundAdapter,
    "indeed": IndeedAdapter,
}

BUDGETS = {
    "naukri": 5.0,
    "remoteok": 2.0,
    "wellfound": 15.0,
    "indeed": 15.0,
}


def measure_adapter(name, cls, role, location):
    try:
        adapter = cls()
    except EnvironmentError as e:
        return {"name": name, "status": "SKIPPED (env)", "elapsed": None, "count": None}

    start = time.time()
    try:
        results = adapter.fetch(role, location)
        elapsed = time.time() - start
        return {"name": name, "status": "OK", "elapsed": round(elapsed, 2),
                "count": len(results)}
    except Exception as e:
        elapsed = time.time() - start
        return {"name": name, "status": f"ERROR: {e}", "elapsed": round(elapsed, 2),
                "count": None}


def main(role="data scientist", location="bangalore"):
    print("=" * 60)
    print("PERFORMANCE EVALUATION")
    print(f"Query: role='{role}', location='{location}'")
    print("=" * 60)

    all_results = []
    total_fetch_time = 0.0
    all_jobs = []

    for name, cls in ADAPTERS.items():
        m = measure_adapter(name, cls, role, location)
        all_results.append(m)
        budget = BUDGETS[name]
        status_flag = ""
        if m["elapsed"] is not None:
            total_fetch_time += m["elapsed"]
            if m["elapsed"] > budget * 1.5:
                status_flag = " ⚠ FLAG (>1.5x budget)"
            elif m["elapsed"] > budget:
                status_flag = " ⚠ over budget"
        print(f"  {name:12s} status={m['status']:20s} "
              f"elapsed={m['elapsed']}s (budget {budget}s){status_flag} "
              f"count={m['count']}")

    print(f"\n  Total fetch time: {total_fetch_time:.2f}s")

    # Filter/write timing
    t0 = time.time()
    role_filtered = filter_by_role(all_jobs, role)
    loc_filtered = filter_by_location(role_filtered, location)
    deduped = dedupe(loc_filtered)
    filter_time = time.time() - t0
    print(f"  Filter pipeline time: {filter_time*1000:.1f}ms")

    t0 = time.time()
    write_csv(deduped, "perf_eval.csv")
    write_time = time.time() - t0
    print(f"  CSV write time: {write_time*1000:.1f}ms")

    total = total_fetch_time + filter_time + write_time
    print(f"\n  TOTAL (excluding Sheets): {total:.2f}s")

    if total > 45:
        print("  RESULT: FLAG — total time exceeds 45s threshold")
        return 1
    elif total > 30:
        print("  RESULT: WARN — total time exceeds 30s acceptable range")
        return 0
    else:
        print("  RESULT: PASS")
        return 0


if __name__ == "__main__":
    role = sys.argv[1] if len(sys.argv) > 1 else "data scientist"
    location = sys.argv[2] if len(sys.argv) > 2 else "bangalore"
    sys.exit(main(role, location))
```

### 7.4 Performance Gate

```
[ ] Naukri fetch <5s (flag if >8s)
[ ] RemoteOK fetch <2s (flag if >5s)
[ ] Wellfound fetch <15s (flag if >25s)
[ ] Indeed fetch <15s (flag if >25s)
[ ] Filter pipeline <100ms for typical row counts (<1000 rows)
[ ] CSV write <100ms for typical row counts
[ ] Total pipeline (excluding Sheets) <30s
```

**Note:** Performance failures here are almost always Firecrawl-side latency (Wellfound/Indeed), not code inefficiency. If Wellfound/Indeed consistently exceed budget, this is informational for demo planning (don't be surprised by the wait), not a code bug to fix under time pressure.

---

## 8. Security Evaluation

### 8.1 Security Checklist (Maps to EDGE_CASE_PLAN.md Section 12)

| Check | Command | Pass Criteria |
|---|---|---|
| `.env` not tracked by git | `git ls-files \| grep -x ".env"` | Empty output |
| `.env` is gitignored | `git check-ignore -v .env` | Shows matching `.gitignore` rule |
| Credentials directory gitignored | `git check-ignore -v credentials/service_account.json` | Shows matching rule |
| No hardcoded Firecrawl keys | `grep -rn "fc-[a-zA-Z0-9]" --include="*.py" .` | No matches |
| No hardcoded Google credentials | `grep -rn "private_key" --include="*.py" .` | No matches |
| No `locals()`/`vars()` dumps | `grep -rn "locals()\|vars()" --include="*.py" .` | No matches (or only in test files with justification) |
| `.env.example` has no real values | `cat .env.example` | All values empty or placeholder text |
| Error messages don't echo secrets | Run `tests/test_security.py` | All pass |
| Service account has minimal scope | Manual review of Google Cloud IAM | Service account has no project-level roles |

### 8.2 Security Evaluation Script

```bash
#!/bin/bash
# evaluate_security.sh
set -e

echo "============================================================"
echo "SECURITY EVALUATION"
echo "============================================================"

FAIL=0

# Check 1: .env not tracked
if git ls-files | grep -qx ".env"; then
    echo "[FAIL] .env is tracked by git!"
    FAIL=1
else
    echo "[PASS] .env is not tracked"
fi

# Check 2: .env gitignored
if git check-ignore -q .env; then
    echo "[PASS] .env is gitignored"
else
    echo "[FAIL] .env is NOT gitignored"
    FAIL=1
fi

# Check 3: credentials gitignored
if [ -f "credentials/service_account.json" ]; then
    if git check-ignore -q credentials/service_account.json; then
        echo "[PASS] credentials/service_account.json is gitignored"
    else
        echo "[FAIL] credentials/service_account.json is NOT gitignored"
        FAIL=1
    fi
else
    echo "[SKIP] credentials/service_account.json does not exist (OK)"
fi

# Check 4: no hardcoded Firecrawl keys
if grep -rn "fc-[a-zA-Z0-9]\{20,\}" --include="*.py" . 2>/dev/null; then
    echo "[FAIL] Found hardcoded Firecrawl-style API key in source"
    FAIL=1
else
    echo "[PASS] No hardcoded Firecrawl keys found"
fi

# Check 5: no hardcoded Google private keys
if grep -rn "private_key" --include="*.py" . 2>/dev/null; then
    echo "[FAIL] Found 'private_key' string in Python source"
    FAIL=1
else
    echo "[PASS] No hardcoded Google private keys found"
fi

# Check 6: no locals()/vars() dumps
if grep -rn "locals()\|vars()" --include="*.py" . 2>/dev/null | grep -v "tests/"; then
    echo "[FAIL] Found locals()/vars() usage outside tests/"
    FAIL=1
else
    echo "[PASS] No locals()/vars() dumps in production code"
fi

# Check 7: .env.example has no real-looking values
if grep -E "^FIRECRAWL_API_KEY=fc-[a-zA-Z0-9]" .env.example 2>/dev/null; then
    echo "[FAIL] .env.example appears to contain a real Firecrawl key"
    FAIL=1
else
    echo "[PASS] .env.example contains no real Firecrawl key"
fi

echo "============================================================"
if [ $FAIL -eq 0 ]; then
    echo "RESULT: ALL SECURITY CHECKS PASSED"
    exit 0
else
    echo "RESULT: SECURITY CHECKS FAILED — DO NOT PUSH"
    exit 1
fi
```

### 8.3 Security Gate (HARD GATE — Cannot Be Skipped)

```
[ ] evaluate_security.sh exits 0
[ ] Manual review: GitHub repo (after push) does not show .env or
    credentials/*.json in file listing (verify in incognito browser)
[ ] Manual review: git log --all --full-history -- .env returns nothing
[ ] tests/test_security.py passes (no secret echoing in error messages)
```

This gate is identical to IMPLEMENTATION_PLAN.md Phase 7.2 — this document provides the automatable script version of that manual checklist.

---

## 9. Code Quality Evaluation

### 9.1 Static Analysis

```bash
pip install ruff mypy

# Linting
ruff check . --select E,F,I,UP

# Type checking (informational — full strict mode not required for sprint)
mypy --ignore-missing-imports boards/ filters.py writers.py gleaner.py
```

| Check | Tool | Target | Notes |
|---|---|---|---|
| No unused imports | `ruff check --select F401` | 0 violations | |
| No undefined names | `ruff check --select F821` | 0 violations | Critical — indicates real bugs |
| Import ordering | `ruff check --select I` | 0 violations | Cosmetic, nice-to-have |
| Line length | `ruff check --select E501` | <20 violations | Soft limit; not blocking |
| Type hints present on public functions | `mypy` informational pass | No hard requirement | Document gaps for Sprint 2 |

### 9.2 Docstring Coverage

```bash
pip install interrogate
interrogate -v boards/ filters.py writers.py gleaner.py
```

| Module | Target Docstring Coverage |
|---|---|
| `boards/base.py` | 100% (this is the contract — must be documented) |
| `filters.py` | 100% (three small functions, no excuse) |
| `writers.py` | 100% |
| Adapters | ≥80% (public methods at minimum) |
| `gleaner.py` | ≥70% (main orchestration functions) |

### 9.3 Code Quality Gate

```
[ ] ruff check --select F821 (undefined names) == 0 violations
[ ] ruff check --select F401 (unused imports) == 0 violations
[ ] interrogate shows 100% on base.py and filters.py
[ ] No function in filters.py or writers.py exceeds 30 lines
    (long functions here indicate accidental complexity creep)
```

**This gate is advisory, not blocking for Sprint 1.** Run it, document results, but do not let linting consume time budget that belongs to functional phases. Address F821 violations immediately if found (these are real bugs); defer style issues.

---

## 10. Artifact & Demo Evaluation

This section evaluates the four Sprint 1 deliverables as a stranger (recruiter, hiring manager, cohort peer) would encounter them.

### 10.1 GitHub Repository Evaluation

| Check | How to Verify | Pass Criteria |
|---|---|---|
| Repo is public | Open repo URL in incognito browser | Loads without login prompt |
| README renders correctly | View repo homepage | README displays with proper Markdown formatting (headers, code blocks) |
| README has working setup instructions | Follow README from a clean clone | A new user can `pip install`, configure `.env`, and run within 10 minutes |
| No secrets visible | Browse file tree, check `.env`, `credentials/` | Neither appears (or only `.gitignore`-respecting placeholders) |
| Code is browsable and organized | Navigate to `boards/` | Four adapter files visible, each <200 lines, readable |
| Commit message is descriptive | `git log --oneline -1` | Not "wip" or "fix" — should be "Sprint 1 — The Gleaner" or similar |
| `selectors.md` present and dated | Open file | Contains "Last verified: <date>" |
| `requirements.txt` is complete | `pip install -r requirements.txt` in fresh venv | No `ModuleNotFoundError` when running `gleaner.py --help` |

**Repo Evaluation Score:** `(checks passed) / 8`

### 10.2 Google Sheet Evaluation

| Check | How to Verify | Pass Criteria |
|---|---|---|
| Sheet is public (anyone-with-link) | Open Sheet URL in incognito browser | Loads without sign-in prompt |
| ≥50 rows present | Count rows in Sheet | `>= 50` (excluding header) |
| Header row present and correct | Row 1 | Matches `CANONICAL_FIELDS` order exactly |
| No empty required-field cells | Spot-check `title`, `company`, `location`, `link` columns | No blank cells in these columns |
| Links are clickable | Click a few `link` cells | Opens the job posting (or at least a valid URL, even if posting expired) |
| Multiple `source` values present | Check `source` column for variety | ≥2 distinct values (ideally 3-4) |
| Sheet title is descriptive | Check Sheet name (not "Untitled spreadsheet") | Named something like "The Gleaner — Job Listings" |

**Sheet Evaluation Score:** `(checks passed) / 7`

### 10.3 Demo Clip Evaluation

| Check | How to Verify | Pass Criteria |
|---|---|---|
| Duration | Play clip, check length | 60-90 seconds |
| Terminal run visible | Watch clip | Shows `python gleaner.py ...` command and live output |
| Per-board fetch counts visible | Watch clip | Console output shows at least 2-3 "fetched N listings" lines |
| Filter pipeline counts visible | Watch clip | Shows decreasing counts (role filter → location filter → dedupe) |
| Sheet refresh shown | Watch clip | Browser tab switches to Sheet, shows populated rows |
| Repo URL shown | Watch clip | GitHub repo visible (URL bar or page content) |
| Audio/captions clear (if present) | Watch with sound | Understandable narration or captions |

**Demo Evaluation Score:** `(checks passed) / 7`

### 10.4 LinkedIn Post Evaluation

| Check | Pass Criteria |
|---|---|
| Hook line present | First line grabs attention, not generic |
| Technical substance | At least 3 specific technical details (adapter pattern, board count, tech stack) mentioned |
| Demo clip attached/linked | Video embedded or linked |
| Repo + Sheet links present | Both URLs included (in post or first comment) |
| Hashtags present | `#Gleaner` at minimum |
| No typos in technical terms | "Firecrawl", "BeautifulSoup", "gspread" etc. spelled correctly |

**LinkedIn Evaluation Score:** `(checks passed) / 6`

### 10.5 Combined Artifact Score

```
Total Artifact Score = (Repo + Sheet + Demo + LinkedIn) / (8 + 7 + 7 + 6)
                     = (Repo + Sheet + Demo + LinkedIn) / 28
```

| Total Score | Interpretation |
|---|---|
| ≥90% (25.2/28) | Portfolio-ready — confidently shareable with recruiters |
| 75-89% (21-25) | Solid — minor polish recommended before heavy promotion |
| 60-74% (17-20) | Functional but needs work before wide sharing — prioritize gaps |
| <60% (<17) | Not ready — address P0/P1 gaps from missing checks first |

---

## 11. Automated Evaluation Script

A single entry point that runs all automatable evaluations and produces a consolidated report.

```python
# run_evaluation.py
"""
Master evaluation runner for The Gleaner.
Runs: unit tests w/ coverage, data quality, pipeline scenarios,
security checks, and performance benchmarks.
Produces a single pass/fail summary.
"""
import subprocess
import sys
import os

CHECKS = []


def run(name, cmd, cwd=None):
    print(f"\n{'='*70}\nRUNNING: {name}\n{'='*70}")
    result = subprocess.run(cmd, shell=True, cwd=cwd)
    passed = result.returncode == 0
    CHECKS.append((name, passed))
    return passed


def main():
    # 1. Unit tests with coverage
    run("Unit Tests + Coverage", "pytest tests/ --cov=. --cov-report=term-missing")

    # 2. Security checks
    run("Security Checks", "bash evaluate_security.sh")

    # 3. Pipeline scenarios (requires live network — may be slow)
    if os.environ.get("SKIP_LIVE_EVAL") != "1":
        run("Pipeline Scenarios", "python evaluate_pipeline.py")

        # 4. Data quality (on the happy-path output)
        if os.path.exists("eval_happy.csv"):
            run("Data Quality", 'python evaluate_data_quality.py eval_happy.csv "data scientist" "bangalore"')

        # 5. Performance
        run("Performance", "python evaluate_performance.py")
    else:
        print("\n[SKIPPED] Live network evaluations (SKIP_LIVE_EVAL=1)")

    # Summary
    print(f"\n\n{'='*70}\nEVALUATION SUMMARY\n{'='*70}")
    all_pass = True
    for name, passed in CHECKS:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        all_pass &= passed

    print(f"\n{'OVERALL: PASS' if all_pass else 'OVERALL: FAIL'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
```

```bash
# Full run (requires live network + valid credentials)
python run_evaluation.py

# Fast run (unit tests + security only, skip live network calls)
SKIP_LIVE_EVAL=1 python run_evaluation.py
```

---

## 12. Scoring Rubric & Go/No-Go Matrix

### 12.1 Sprint 1 Go/No-Go Decision Matrix

This is the final decision framework at minute 120 (or whenever Phase 7 concludes).

| Dimension | Weight | Score (0-3) | Weighted |
|---|---|---|---|
| Test coverage gate (Section 2.4) | 15% | __ | __ |
| Adapter functional checklists (Section 3.6) | 20% | __ | __ |
| Data quality gate (Section 4.5) | 25% | __ | __ |
| Resilience gate (Section 6.3) | 15% | __ | __ |
| Security gate (Section 8.3) | 15% | __ | __ |
| Artifact score (Section 10.5) | 10% | __ | __ |

**Score scale per dimension:**
- `0` = Failed / not attempted
- `1` = Partial — gate not met, pivot/workaround documented
- `2` = Met with minor gaps
- `3` = Fully met

**Weighted total = Σ(weight × score) / 3** → produces a 0-100% readiness score.

### 12.2 Go/No-Go Thresholds

| Weighted Score | Decision |
|---|---|
| ≥85% | **GO** — ship all four artifacts as planned |
| 70-84% | **GO WITH CAVEATS** — ship, but document specific gaps prominently in README "Known Limitations"; create Sprint 1.5 follow-up tickets |
| 50-69% | **CONDITIONAL GO** — ship CSV + repo only; defer Sheet/demo until gaps closed (use Appendix B contingency from IMPLEMENTATION_PLAN.md) |
| <50% | **NO-GO** — do not submit for badge; the security gate alone scoring 0 is an automatic NO-GO regardless of total |

### 12.3 Non-Negotiable Floor (Independent of Weighted Score)

Regardless of the weighted total, these MUST be true:

```
[ ] Security gate (Section 8.3) == fully passed (score 3)
    — A security score <3 is an automatic NO-GO for public push,
    even if every other dimension scores perfectly.

[ ] At least 1 adapter returns live, schema-valid results
    — A pipeline with zero working adapters has nothing to evaluate
    and nothing to demo.

[ ] write_csv() produces a valid CSV in all tested scenarios
    — This is the floor output format; if this fails, nothing ships.
```

---

## 13. Post-Sprint Continuous Evaluation

The evaluation does not end at minute 120. The following cadence keeps the system trustworthy as a portfolio piece over time.

### 13.1 Weekly Drift Check

```bash
# Run weekly — same query, compare results over time
python gleaner.py --role "data scientist" --location "bangalore" \
  --output weekly_check_$(date +%Y%m%d).csv --boards all

python evaluate_data_quality.py weekly_check_$(date +%Y%m%d).csv "data scientist" "bangalore"
```

**What to watch for:**

| Signal | Likely Cause | Action |
|---|---|---|
| Naukri results suddenly 0 | Selector drift (sites change weekly) | Re-run Step 1.1 from IMPLEMENTATION_PLAN.md, update `selectors.md` |
| Total row count trending down over weeks | Could be selector drift on multiple boards, or seasonal job market variation | Compare per-board counts; investigate the board with the steepest drop |
| Indeed/Wellfound suddenly 0 with "Cloudflare"/"quota" warnings | Firecrawl quota reset timing, or increased bot-detection aggressiveness | Check Firecrawl dashboard; consider Publisher API activation for Indeed |
| `description_fill_pct` dropping for a board | Source site changed its listing page structure | Inspect that board's extraction/selectors |

### 13.2 Regression Test Suite Maintenance

Each time `selectors.md` is updated (Naukri selector drift), add a regression entry:

```markdown
# selectors.md — Change Log

## 2026-06-14 — Initial selectors
...

## 2026-07-02 — Naukri changed job card class from .jobTuple to .srp-jobtuple-wrapper
Updated CARD_SELECTOR in boards/naukri.py accordingly.
Regression test added: tests/test_naukri.py::test_handles_srp_jobtuple_wrapper
```

### 13.3 Sprint 2 Readiness Check

Before starting Sprint 2 (The Resume Shapeshifter), re-run the full evaluation suite to confirm Gleaner's output is still a reliable input:

```bash
python run_evaluation.py
```

```
[ ] All gates from Sprint 1 still pass (no silent regressions)
[ ] jobs.csv schema unchanged (Sprint 2 will depend on this contract)
[ ] At least 50 rows producible on a fresh run with current selectors
```

---

## 14. CONDUCTOR Readiness Evaluation

This section evaluates Gleaner's readiness to serve as CONDUCTOR's data-acquisition component (see ARCHITECTURE.md Section 13).

### 14.1 CONDUCTOR Contract Compliance Checklist

| Requirement | Status | Evaluation Method |
|---|---|---|
| JSON output format implemented (`--format json`) | Not yet (Sprint 2+ per PROBLEM_STATEMENT backlog) | `python gleaner.py --format json --output jobs.json` produces valid JSON matching ARCHITECTURE.md Section 13.1 schema |
| `run_id` and `timestamp` populated | Not yet | JSON output contains valid UUID and ISO 8601 timestamp |
| `stats` block accurately reflects filter pipeline counts | Not yet | `stats.raw_fetched >= stats.after_role_filter >= ... >= stats.final` |
| `relevance_score: null` present on all jobs | Not yet | Every job object has the key, value `null` |
| Schema stability — no breaking changes since last CONDUCTOR design review | N/A (first review) | Diff `CANONICAL_FIELDS` against CONDUCTOR_CONTRACT.md when it exists |

### 14.2 CONDUCTOR Readiness Score

```
CONDUCTOR Readiness = (requirements met) / (total requirements)
```

**Current status (Sprint 1):** 0/5 — JSON output format is explicitly a Sprint 2+ backlog item (PROBLEM_STATEMENT.md Section 10.4). This is expected and not a Sprint 1 failure; it's tracked here so the gap is visible and intentional, not forgotten.

**Sprint 2 trigger:** When Sprint 2 (Resume Shapeshifter) begins consuming Gleaner output, re-run this checklist. If Sprint 2 needs JSON output, HAR-style tickets for `--format json` should be created and run through this same EVALUATION_PLAN.md framework (Sections 2-9 apply equally to new code).

---

## 15. Evaluation Report Template

Use this template to record the Sprint 1 evaluation outcome. Save as `EVALUATION_REPORT_<date>.md`.

```markdown
# Evaluation Report — The Gleaner Sprint 1
Date: <date>
Evaluator: <name>

## Summary
Overall Go/No-Go: <GO / GO WITH CAVEATS / CONDITIONAL GO / NO-GO>
Weighted Score: <XX%>

## Test Coverage
Total coverage: <XX%>
filters.py: <XX%> (target 100%)
boards/base.py: <XX%> (target 100%)
[... per module ...]

## Adapter Scores
Naukri:    <X/7>  — Live results: <Y/N/Pivot>
RemoteOK:  <X/6>  — Live results: <Y/N>
Wellfound: <X/5>  — Live results: <Y/N/Pivot>
Indeed:    <X/8>  — Live results: <Y/N/Pivot>

## Data Quality (jobs.csv)
Total rows: <N> (target >=50)
[paste evaluate_data_quality.py output]

## Resilience
[ ] / [x] for each of 6 resilience gate items

## Performance
Total pipeline time: <X.X>s (target <30s)
[per-adapter breakdown]

## Security
[ ] / [x] for each of 4 security gate items
evaluate_security.sh exit code: <0/1>

## Artifacts
Repo score: <X/8>
Sheet score: <X/7>
Demo score: <X/7>
LinkedIn score: <X/6>

## Known Gaps / Pivots Invoked
- <e.g., "Indeed adapter implemented but Firecrawl quota limited live
  results during sprint; Publisher API fallback documented but not
  exercised">

## Action Items for Sprint 1.5 / Sprint 2
- <e.g., "Activate Indeed Publisher API fallback and re-test">
- <e.g., "Increase Wellfound test coverage from 71% to 75% target">

## CONDUCTOR Readiness
<X/5> — JSON output format pending (tracked, expected at this stage)
```

---

## Appendix — Quick Reference: All Gates at a Glance

```
┌──────────────────────────────────────────────────────────────────┐
│ GATE                          │ SECTION │ BLOCKING?               │
├──────────────────────────────────────────────────────────────────┤
│ Test Coverage Gate            │ 2.4     │ Soft (document gaps)    │
│ Adapter Functional Checklists │ 3.6     │ Soft (pivots allowed)   │
│ Data Quality Gate             │ 4.5     │ HARD before Phase 7     │
│ Pipeline-Level Gate           │ 5.3     │ HARD before Phase 7     │
│ Resilience Gate                │ 6.3     │ HARD before Phase 7     │
│ Performance Gate               │ 7.4     │ Soft (informational)    │
│ Security Gate                  │ 8.3     │ HARD — cannot push w/o  │
│ Code Quality Gate               │ 9.3     │ Soft (advisory)         │
│ Artifact Score                  │ 10.5    │ Soft (drives polish)    │
│ Non-Negotiable Floor             │ 12.3    │ HARD — overrides all    │
└──────────────────────────────────────────────────────────────────┘
```

**The four HARD gates (Data Quality, Pipeline-Level, Resilience, Security) are the minimum bar for Phase 7 to begin and for the public push to occur. Soft gates inform the artifact polish but do not block shipping.**
