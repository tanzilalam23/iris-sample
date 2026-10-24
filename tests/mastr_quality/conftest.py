from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def units_xml():
    return FIXTURES / "mastr_units_sample.xml"


@pytest.fixture
def storage_xml():
    return FIXTURES / "mastr_storage_sample.xml"


@pytest.fixture
def state_json():
    return FIXTURES / "current_state_sample.json"
