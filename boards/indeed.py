import os
import time
import logging
import urllib.parse
import requests
from dotenv import load_dotenv
from firecrawl import FirecrawlApp
from .base import BoardAdapter

load_dotenv()

logger = logging.getLogger(__name__)

class IndeedAdapter(BoardAdapter):
    """Adapter for fetching Indeed job listings using Firecrawl structured extraction or the Publisher API fallback."""

    def __init__(self):
        super().__init__()
        api_key = os.environ.get("FIRECRAWL_API_KEY")
        if not api_key:
            raise EnvironmentError("FIRECRAWL_API_KEY is not set in the environment.")
        self.app = FirecrawlApp(api_key=api_key)

    def _build_url(self, role: str, location: str) -> str:
        """Construct the Indeed India search URL."""
        encoded_role = urllib.parse.quote_plus(role)
        encoded_loc = urllib.parse.quote_plus(location)
        return f"https://in.indeed.com/jobs?q={encoded_role}&l={encoded_loc}"

    def _absolute_link(self, href: str) -> str:
        """Prepend Indeed base URL if path is relative."""
        if not href:
            return ""
        if href.startswith("/"):
            return f"https://in.indeed.com{href}"
        return href

    def fetch(self, role: str, location: str) -> list[dict]:
        """
        Fetches jobs from Indeed.com using Firecrawl with a 2-second wait action.
        Falls back to the Indeed Publisher Search API if Firecrawl returns 0 or fails.
        """
        url = self._build_url(role, location)
        logger.info("Fetching Indeed jobs via Firecrawl from %s", url)
        
        try:
            response = self.app.v1.scrape_url(url, formats=["extract"], actions=[{"type": "wait", "milliseconds": 2000}], extract={
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
            })
            
            # Rate limit politeness
            time.sleep(2)
            
            jobs_data = response.extract.get("jobs", []) if response.extract else []
            if jobs_data:
                jobs: list[dict] = []
                for idx, job in enumerate(jobs_data, start=1):
                    try:
                        raw_job = {
                            "source": "indeed",
                            "title": job.get("title", ""),
                            "company": job.get("company", ""),
                            "location": job.get("location") or "",
                            "link": self._absolute_link(job.get("link", "")),
                            "posted_at": job.get("posted_at") or "",
                            "description": job.get("description") or ""
                        }
                        validated = self._validate_schema(raw_job)
                        jobs.append(validated)
                    except Exception as exc:
                        logger.warning("Skipping invalid Indeed job %d: %s", idx, exc)
                return jobs
            else:
                logger.warning("Indeed returned 0 results via Firecrawl. Attempting Publisher API fallback.")
        except Exception as exc:
            logger.warning("Firecrawl extraction failed for Indeed: %s. Attempting Publisher API fallback.", exc)

        return self._fetch_via_publisher_api(role, location)

    def _fetch_via_publisher_api(self, role: str, location: str) -> list[dict]:
        """Indeed Publisher Search API fallback."""
        pub_id = os.environ.get("INDEED_PUBLISHER_ID")
        if not pub_id:
            logger.warning("INDEED_PUBLISHER_ID not configured; Publisher API fallback skipped.")
            return []

        url = "http://api.indeed.com/ads/apisearch"
        params = {
            "publisher": pub_id,
            "q": role,
            "l": location,
            "format": "json",
            "v": "2",
            "limit": "25",
            "co": "in"
        }
        
        logger.info("Fetching Indeed jobs via Publisher API")
        try:
            res = requests.get(url, params=params, timeout=15)
            if res.status_code != 200:
                logger.warning("Indeed Publisher API returned status %d", res.status_code)
                return []
            
            results = res.json().get("results", [])
            jobs: list[dict] = []
            for idx, job in enumerate(results, start=1):
                try:
                    raw_job = {
                        "source": "indeed",
                        "title": job.get("jobtitle", ""),
                        "company": job.get("company", ""),
                        "location": job.get("city", ""),
                        "link": job.get("url", ""),
                        "posted_at": job.get("date", ""),
                        "description": job.get("snippet", "")
                    }
                    validated = self._validate_schema(raw_job)
                    jobs.append(validated)
                except Exception as exc:
                    logger.warning("Skipping invalid Indeed Publisher API job %d: %s", idx, exc)
            return jobs
        except Exception as exc:
            logger.error("Indeed Publisher API failed: %s", exc)
            return []

