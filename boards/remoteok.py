import logging
import requests
from bs4 import BeautifulSoup
from .base import BoardAdapter

logger = logging.getLogger(__name__)

class RemoteOKAdapter(BoardAdapter):
    """Adapter for fetching remote job listings from RemoteOK's public JSON API."""

    def fetch(self, role: str, location: str) -> list[dict]:
        """
        Fetches jobs from RemoteOK public JSON API.
        Filters listings using substring match of role keywords on position or tags.
        """
        url = "https://remoteok.com/api"
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; GleanerBot/1.0)"
        }
        
        logger.info("Fetching RemoteOK jobs from %s", url)
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                logger.warning("RemoteOK request failed with status code %d", response.status_code)
                return []
            
            data = response.json()
        except Exception as exc:
            logger.warning("Failed to fetch or parse RemoteOK JSON: %s", exc)
            return []

        if not isinstance(data, list) or len(data) <= 1:
            logger.warning("RemoteOK returned empty or unexpected payload.")
            return []

        # Index [0] is legal/info metadata blob, skip it
        job_listings = data[1:]
        
        # Split target role into lowercase keywords for filtering
        keywords = [kw.lower() for kw in role.strip().split() if kw]
        
        jobs: list[dict] = []
        for idx, job in enumerate(job_listings, start=1):
            try:
                position = job.get("position", "")
                tags = job.get("tags", [])
                
                # RemoteOK is inherently remote. If location is requested, we can still match keywords,
                # but typically RemoteOK is for remote jobs.
                # Check if ANY of the role keywords matches position or tags.
                position_lower = position.lower()
                tags_lower = [t.lower() for t in tags]
                
                match = False
                if not keywords:
                    match = True
                else:
                    for kw in keywords:
                        if kw in position_lower or any(kw in tag for tag in tags_lower):
                            match = True
                            break
                
                if not match:
                    continue
                
                # Clean description of HTML tags using BeautifulSoup
                raw_desc = job.get("description", "")
                if raw_desc:
                    soup = BeautifulSoup(raw_desc, "lxml")
                    description = soup.get_text(separator=" ").strip()
                else:
                    description = ""
                
                raw_job = {
                    "source": "remoteok",
                    "title": position,
                    "company": job.get("company", ""),
                    "location": job.get("location") or "Remote",
                    "link": job.get("url", ""),
                    "posted_at": job.get("date", ""),
                    "description": description
                }
                
                validated = self._validate_schema(raw_job)
                jobs.append(validated)
            except Exception as exc:
                logger.warning("Skipping RemoteOK job card %d: %s", idx, exc)
                continue
                
        return jobs

