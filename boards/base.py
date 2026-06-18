from abc import ABC, abstractmethod

class BoardAdapter(ABC):
    """
    Abstract base class for all job board adapters.
    """

    @property
    def name(self) -> str:
        """Dynamic board name derived from class name."""
        return self.__class__.__name__.replace("Adapter", "").lower()

    @abstractmethod
    def fetch(self, role: str, location: str) -> list[dict]:
        """
        Fetches jobs for the given role and location.
        """
        pass

    def _validate_schema(self, job: dict) -> dict:
        """
        Validates the canonical schema. Fills in defaults for optional fields.
        """
        required = {"source", "title", "company", "location", "link"}
        optional = {"posted_at": "", "description": ""}

        # Required fields validation
        for field in required:
            if not job.get(field) or not str(job[field]).strip():
                raise ValueError(f"Required field '{field}' is missing or empty in job.")

        # Populate optional fields
        validated_job = {}
        for key, val in job.items():
            validated_job[key] = str(val).strip() if val is not None else ""

        for field, default in optional.items():
            if field not in validated_job:
                validated_job[field] = default

        return validated_job
