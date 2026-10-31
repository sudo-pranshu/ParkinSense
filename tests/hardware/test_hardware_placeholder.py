"""
Hardware-in-the-loop tests. These require a flashed XIAO nRF52840 Sense and are
skipped in CI. The manual procedure is docs/validation/HARDWARE_TEST_PROCEDURE.md;
results must be recorded there by hand -- never marked passed without a device.
"""
import os

import pytest

pytestmark = pytest.mark.hardware


@pytest.mark.skipif(not os.environ.get("PARKINSENSE_DEVICE"), reason="requires a physical device")
def test_live_stream_rate_and_loss():
    pytest.fail("Run docs/validation/HARDWARE_TEST_PROCEDURE.md H1-H3 and record results")
