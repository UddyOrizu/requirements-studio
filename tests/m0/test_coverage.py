"""Coverage and next_slot match the oracle on every replayed KYC IR (CLAUDE.md rule 7)."""
import pytest

from services.intake.coverage import coverage, next_slot
from tests.oracle import R, replayed_irs

IRS = list(replayed_irs())


@pytest.mark.parametrize("label,ir", IRS)
def test_m0_coverage_and_next_slot_match_oracle(label, ir):
    assert coverage(ir) == R.coverage(ir)
    assert next_slot(ir) == R.next_slot(ir)
    for parked in (["C04"], ["C11", "C12"], ["C16"]):
        assert coverage(ir, parked) == R.coverage(ir, parked)
        assert next_slot(ir, parked) == R.next_slot(ir, parked)


def test_m0_c17_only_counts_for_an_as_is():
    as_is = next(ir for label, ir in IRS if label == "as_is@v19")
    to_be = next(ir for label, ir in IRS if label == "to_be@v0")
    assert "C17" in coverage(as_is)["filled"] and coverage(as_is)["percent"] == 1.0
    assert "C17" not in coverage(to_be)["filled"] + coverage(to_be)["unfilled"]
    assert coverage(to_be)["percent"] == 1.0  # normalised over 16 slots
