import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from parkinsense.synthetic import signals as S  # noqa: E402


@pytest.fixture
def synth():
    return S
