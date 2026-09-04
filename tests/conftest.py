import pytest


SAMPLE_METADATA = {
    "client_name": "ABC Company",
    "entity_name": "ABC Company LLC",
    "tax_year": 2025,
    "entity_type": "1120S",
    "prepared_by": "Test Preparer",
    "reviewer": "Test Reviewer",
    "workpaper_folder": None,  # filled per-test using tmp_path
    "accounting_system": "QuickBooks",
}


@pytest.fixture
def meta(tmp_path):
    m = dict(SAMPLE_METADATA)
    m["workpaper_folder"] = str(tmp_path)
    return m


@pytest.fixture
def atbw_path(tmp_path, meta):
    from atbworkup.models.job import create_workup
    from atbworkup.utils.naming import suggested_filename
    path = tmp_path / suggested_filename(meta["tax_year"], meta["client_name"])
    create_workup(path, meta)
    return path
