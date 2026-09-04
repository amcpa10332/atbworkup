APP_VERSION = "0.1.0"
APP_NAME = "ATBWorkup"
SCHEMA_VERSION = "1.0"

ENTITY_TYPES = [
    ("1120S",          "1120-S  (S-Corporation)"),
    ("1065",           "1065    (Partnership)"),
    ("1120",           "1120    (C-Corporation)"),
    ("ScheduleC",      "Schedule C  (Sole Proprietorship)"),
    ("990",            "990     (Not-for-Profit)"),
    ("1041",           "1041    (Trust or Estate)"),
    ("TrustAccounting","Trust / Court Accounting"),
    ("Consolidated",   "Consolidated  (Multi-Entity)"),
]

# Entity types that support the Workpapers tab (M-1, M-2, K-1)
WORKPAPER_ENTITY_TYPES = {"1065", "1120S", "1120"}


def get_entity_types() -> list[tuple[str, str]]:
    """
    Return (entity_type_code, display_label) pairs.
    Starts from the built-in list and appends any custom templates
    stored in settings that are not already present.
    """
    try:
        from atbworkup.db.settings import list_templates
        from atbworkup.data.tax_line_seeds import TEMPLATE_DISPLAY_NAMES
        known = {code for code, _ in ENTITY_TYPES}
        extras = []
        for row in list_templates():
            code = row["entity_type"]
            if code not in known:
                known.add(code)
                extras.append((code, row["template_name"] or code))
        return list(ENTITY_TYPES) + extras
    except Exception:
        return list(ENTITY_TYPES)

# Role colors — used consistently across the UI
ROLE_COLORS: dict[str, str] = {
    "preparer": "#C0392B",   # red
    "reviewer": "#1A6BB5",   # blue
    "signer":   "#6B2D8B",   # purple
}

NOTE_TYPE_COLORS: dict[str, str] = {
    "preparer": "#C0392B",   # red
    "reviewer": "#1A6BB5",   # blue
    "delivery": "#6B2D8B",   # purple — signer-facing items
}

STATUSES = [
    "Draft",
    "In Prep",
    "Ready for Review",
    "Reviewer Notes",
    "Cleared for Review",
    "Ready for Final Review",
    "Final",
    "Reopened",
]
