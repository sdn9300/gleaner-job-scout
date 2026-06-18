import logging
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

from .base import BoardAdapter

logger = logging.getLogger(__name__)


class NaukriAdapter(BoardAdapter):
    """Adapter for scraping Naukri.com job listings using static HTML parsing.

    The adapter builds a URL based on role and location, fetches the page with a
    realistic ``User-Agent`` header, parses job cards using selectors defined in
    ``selectors.md`` and returns a list of canonical job dictionaries.
    """

    def _slugify(self, text: str) -> str:
        """Convert a free‑form string into a URL‑friendly slug.

        The implementation lower‑cases the text, strips surrounding whitespace
        and replaces any sequence of whitespace characters with a single hyphen.
        """
        return "-".join(text.strip().lower().split())

    def _build_url(self, role: str, location: str) -> str:
        """Construct the Naukri search URL for the given role and location.

        Example::

            role="data scientist", location="bangalore"
            -> https://www.naukri.com/data-scientist-jobs-in-bangalore
        """
        role_slug = self._slugify(role)
        loc_slug = self._slugify(location)
        return f"https://www.naukri.com/{role_slug}-jobs-in-{loc_slug}"

    def fetch(self, role: str, location: str) -> list[dict]:
        """Fetch job listings from Naukri.com.

        Returns a list of dictionaries each adhering to the canonical schema
        defined in :class:`BoardAdapter`.  Any job that fails schema validation
        is skipped with a warning.
        """
        url = self._build_url(role, location)
        logger.info("Fetching Naukri jobs from %s", url)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            raise RuntimeError(f"Naukri request failed with status {response.status_code}: {url}")
        # Be polite – avoid hammering the site.
        time.sleep(1)
        soup = BeautifulSoup(response.text, "lxml")
        # Selectors based on selectors.md (may need adjustments in the future).
        container_selector = ".srp-jobtuple-wrapper"
        title_selector = "a.title"
        company_selector = "a.comp-name"
        location_selector = ".loc-wrap.locWdth"
        posted_selector = ".job-post-day"
        cards = soup.select(container_selector)
        if not cards:
            logger.warning("No job cards found on Naukri page – selectors may be outdated.")
            return []
        jobs: list[dict] = []
        for idx, card in enumerate(cards, start=1):
            try:
                title_el = card.select_one(title_selector)
                company_el = card.select_one(company_selector)
                location_el = card.select_one(location_selector)
                posted_el = card.select_one(posted_selector)
                if not (title_el and company_el and location_el):
                    raise ValueError("Missing required element(s) in job card")
                title = title_el.get_text(strip=True)
                link = title_el.get("href", "").strip()
                if link.startswith("/"):
                    link = f"https://www.naukri.com{link}"
                company = company_el.get_text(strip=True)
                job_location = location_el.get_text(strip=True)
                posted_at = posted_el.get_text(strip=True) if posted_el else ""
                raw_job = {
                    "source": "naukri",
                    "title": title,
                    "company": company,
                    "location": job_location,
                    "link": link,
                    "posted_at": posted_at,
                    "description": "",
                }
                validated = self._validate_schema(raw_job)
                jobs.append(validated)
            except Exception as exc:
                logger.warning("Skipping malformed Naukri card %d: %s", idx, exc)
                continue
        return jobs
