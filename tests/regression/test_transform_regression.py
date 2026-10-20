"""Non-regression test of the transform step (see transform_regression.py)."""

import pytest

from transform_regression import (
    BASELINE_DIR, FROZEN_INPUTS_DIR, compare_outputs, run_transform
)

pytestmark = pytest.mark.regression


@pytest.mark.skipif(
    not (FROZEN_INPUTS_DIR.is_dir() and BASELINE_DIR.is_dir()),
    reason="Frozen inputs or baseline missing: run 'freeze' then 'baseline' first.",
)
def test_transform_outputs_match_baseline(tmp_path):
    run_transform(FROZEN_INPUTS_DIR, tmp_path)
    failures = compare_outputs(BASELINE_DIR, tmp_path)
    assert not failures, "\n\n".join(failures)
