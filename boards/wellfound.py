import os
import logging
import urllib.parse
from dotenv import load_dotenv
from firecrawl import FirecrawlApp
from bs4 import BeautifulSoup
from .base import BoardAdapter

load_dotenv()

logger = logging.getLogger(__name__)

class WellfoundAdapter(BoardAdapter):
    """Adapter for fetching Wellfound job listings via Firecrawl structured extraction."""

    def __init__(self):
        super().__init__()
        api_key = os.environ.get("FIRECRAWL_API_KEY")
        if not api_key:
            raise EnvironmentError("FIRECRAWL_API_KEY is not set in the environment.")
        self.app = FirecrawlApp(api_key=api_key)

    def fetch(self, role: str, location: str) -> list[dict]:
        """
        Fetches job listings from Wellfound using Firecrawl's extract API.
        Falls back to WeWorkRemotely (WWR) RSS feed if Firecrawl fails or returns 0.
        """
        encoded_role = urllib.parse.quote_plus(role)
        encoded_loc = urllib.parse.quote_plus(location)
        url = f"https://wellfound.com/jobs?role={encoded_role}&location={encoded_loc}"
        
        logger.info("Fetching Wellfound jobs via Firecrawl from %s", url)
        
        try:
            response = self.app.v1.scrape_url(url, formats=["extract"], extract={
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
            })
            
            # response is a V1ScrapeResponse object. Its extract field holds the JSON dict or it has a dict layout.
            # We can check extract property.
            jobs_data = response.extract.get("jobs", []) if response.extract else []
            if jobs_data:
                jobs: list[dict] = []
                for idx, job in enumerate(jobs_data, start=1):
                    try:
                        raw_job = {
                            "source": "wellfound",
                            "title": job.get("title", ""),
                            "company": job.get("company", ""),
                            "location": job.get("location") or "Remote",
                            "link": job.get("link", ""),
                            "posted_at": "",
                            "description": ""
                        }
                        validated = self._validate_schema(raw_job)
                        jobs.append(validated)
                    except Exception as exc:
                        logger.warning("Skipping invalid Wellfound job %d: %s", idx, exc)
                return jobs
            else:
                logger.warning("Wellfound returned 0 results via Firecrawl. Initiating WWR RSS fallback.")
        except Exception as exc:
            logger.warning("Firecrawl extraction failed for Wellfound: %s. Initiating WWR RSS fallback.", exc)

        return self._fetch_wwr_fallback(role)

    def _fetch_wwr_fallback(self, role: str) -> list[dict]:
        """Fallback to WeWorkRemotely RSS feed to extract remote program/tech roles matching target keyword."""
        logger.info("Executing WeWorkRemotely RSS feed fallback for role: %s", role)
        try:
            import feedparser
        except ImportError:
            logger.warning("feedparser is not installed; WWR RSS fallback cannot proceed.")
            return []

        feed_url = "https://weworkremotely.com/categories/remote-programming-jobs.rss"
        try:
            feed = feedparser.parse(feed_url)
            jobs: list[dict] = []
            keywords = [kw.lower() for kw in role.strip().split() if kw]
            
            for entry in feed.entries:
                title = entry.title
                company = entry.get("author", "Unknown")
                desc = entry.get("summary", "")
                
                # Check for match in title or summary
                match = False
                if not keywords:
                    match = True
                else:
                    text_to_search = f"{title} {desc}".lower()
                    if any(kw in text_to_search for kw in keywords):
                        match = True
                
                if not match:
                    continue
                
                # Strip HTML from summary/description
                soup = BeautifulSoup(desc, "lxml")
                cleaned_desc = soup.get_text(separator=" ").strip()
                
                raw_job = {
                    "source": "wellfound",
                    "title": title,
                    "company": company,
                    "location": "Remote",
                    "link": entry.link,
                    "posted_at": entry.get("published", ""),
                    "description": cleaned_desc
                }
                
                try:
                    validated = self._validate_schema(raw_job)
                    jobs.append(validated)
                except Exception as exc:
                    logger.warning("Skipping invalid WWR job: %s", exc)
            return jobs
        except Exception as exc:
            logger.error("WWR RSS fallback failed: %s", exc)
            return []

