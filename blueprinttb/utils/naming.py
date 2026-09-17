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
    """Return the standard .bta.xlsx filename encoding status and version.

    New saves always suggest .bta.xlsx (the app was formerly ATBWorkup,
    using .atbr.xlsx) -- files with the old extension are still fully
    readable, see importer/package.py and PACKAGE_EXTENSIONS below."""
    safe_client = re.sub(r'[\\/:*?"<>|]', "-", client_name.strip())
    slug = STATUS_SLUGS.get(status, status)
    safe_slug = re.sub(r'[\\/:*?"<>|]', "-", slug)
    return f"{tax_year} {safe_client} {safe_slug} V{version:02d}.bta.xlsx"


# Recognized review-package extensions, newest first -- used by every "Open"
# file dialog and by has_package_extension() below so old .atbr.xlsx files
# (from when this app was named ATBWorkup) stay fully openable going forward.
PACKAGE_EXTENSIONS = (".bta.xlsx", ".atbr.xlsx")


def has_package_extension(name: str) -> bool:
    name = name.lower()
    return any(name.endswith(ext) for ext in PACKAGE_EXTENSIONS)


def with_package_extension(name: str) -> str:
    """Ensure `name` ends in a recognized package extension, defaulting to
    the current .bta.xlsx when it has neither -- used when a user types a
    Save As filename without an extension, or with only '.xlsx'."""
    if has_package_extension(name):
        return name
    if name.lower().endswith(".xlsx"):
        return name[: -len(".xlsx")] + ".bta.xlsx"
    return name + ".bta.xlsx"


def temp_working_path(job_id: str) -> Path:
    """Return the path for the ephemeral SQLite working file in the system temp dir."""
    from blueprinttb.constants import APP_NAME
    d = Path(tempfile.gettempdir()) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{job_id}.btaw"
