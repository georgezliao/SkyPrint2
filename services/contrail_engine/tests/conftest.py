import json
from pathlib import Path

import pytest


@pytest.fixture
def sample_flight():
    fixture_path = Path(__file__).parent / "fixtures" / "sample_flight.json"
    return json.loads(fixture_path.read_text())
