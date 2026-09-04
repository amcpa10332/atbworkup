import re
import tempfile
from pathlib import Path

# Short labels used in the filename slug (keep ≤20 chars, no special chars)
STATUS_SLUGS: dict[str, str] = {
    "Preparation in Progress": "Prep in Progress",
    "Ready for Review":        "Ready for Review",
    "Clear Notes":             "Clear Notes",
    "Notes Cleared":           "Notes Cleared",
    "Ready for Delivery":      "Ready for Delivery",
    "Finalized":               "Final",
}

# Status display colors for the UI pill (background hex, white text)
STATUS_COLORS: dict[str, str] = {
    "Preparation in Progress": "#5A6A8A",
    "Ready for Review":        "#1A2B4C",
    "Clear Notes":             "#B85C00",
    "Notes Cleared":           "#2A6A4A",
    "Ready for Delivery":      "#4A2B7C",
    "Finalized":               "#1A1A1A",
}


def suggested_filename(
    tax_year: int,
    client_name: str,
    status: str = "Preparation in Progress",
    version: int = 1,
) -> str:
    """Return the standard .atbr.xlsx filename encoding status and version."""
    safe_client = re.sub(r'[\\/:*?"<>|]', "-", client_name.strip())
    slug = STATUS_SLUGS.get(status, status)
    safe_slug = re.sub(r'[\\/:*?"<>|]', "-", slug)
    return f"{tax_year} {safe_client} {safe_slug} V{version:02d}.atbr.xlsx"


def temp_atbw_path(job_id: str) -> Path:
    """Return the path for the ephemeral SQLite working file in the system temp dir."""
    d = Path(tempfile.gettempdir()) / "ATBWorkup"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{job_id}.atbw"
