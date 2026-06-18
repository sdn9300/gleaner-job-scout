def dedupe(jobs: list[dict]) -> list[dict]:
    """
    Deduplicates a list of jobs based on the lowercase, stripped (company, title) tuple.
    Keeps the first occurrence, maintaining the original order.
    Returns a new list without mutating the input list.
    """
    seen = set()
    deduped_jobs = []
    for job in jobs:
        company = str(job.get("company", "")).strip().lower()
        title = str(job.get("title", "")).strip().lower()
        key = (company, title)
        if key not in seen:
            seen.add(key)
            deduped_jobs.append(job)
    return deduped_jobs

def filter_by_role(jobs: list[dict], role: str) -> list[dict]:
    """
    Filters jobs by checking if any of the whitespace-separated keywords in role
    is present as a substring in the lowercase title or description.
    Returns a new list without mutating the input list.
    """
    keywords = [kw.lower() for kw in role.strip().split() if kw]
    if not keywords:
        return list(jobs)

    filtered_jobs = []
    for job in jobs:
        title = str(job.get("title", "")).lower()
        desc = str(job.get("description", "")).lower()
        combined = f"{title} {desc}"
        if any(kw in combined for kw in keywords):
            filtered_jobs.append(job)
    return filtered_jobs

def filter_by_location(jobs: list[dict], location: str) -> list[dict]:
    """
    Filters jobs by location. Keeps the job if the target location is a substring
    of the job's location (case-insensitive), or if the job's location is 'remote'.
    Returns a new list without mutating the input list.
    """
    target = location.strip().lower()
    if not target:
        return list(jobs)

    filtered_jobs = []
    for job in jobs:
        job_loc = str(job.get("location", "")).strip().lower()
        if target in job_loc or job_loc == "remote":
            filtered_jobs.append(job)
    return filtered_jobs

