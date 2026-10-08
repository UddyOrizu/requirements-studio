"""The two worked examples as render inputs: IR without stories, gaps, questions, sign-offs and header text."""
import copy
from dataclasses import dataclass

from tests.conftest import KYC, SAMPLES, load


@dataclass
class Sample:
    name: str
    ir: dict  # as stored, with stories
    gaps: list
    questions: list
    dor: dict
    as_is: dict | None
    origin: str  # markdown header text (M0/M12 supplies it in the product)
    feature_description: str
    markdown_file: str
    feature_file: str

    def base(self) -> dict:
        ir = copy.deepcopy(self.ir)
        ir.pop("stories", None)
        return ir


def onboarding() -> Sample:
    # The stored stories were derived before any question was routed, so questions are empty here.
    return Sample("onboarding", load(SAMPLES / "ir_client_onboarding.json"),
                  load(SAMPLES / "gaps_client_onboarding.json"), [], load(SAMPLES / "dor_report.json"), None,
                  "IR version 3 (document-led path, mid-review, polish off)",
                  "Rendered by M7 from IR version 3. Scenarios map 1:1 to acceptance criteria.",
                  "stories_client_onboarding.md", "features/client_onboarding.feature")


def kyc() -> Sample:
    return Sample("client_kyc", load(KYC / "ir_client_kyc_to_be.json"), load(KYC / "gaps_client_kyc.json"),
                  load(KYC / "intake_session_kyc.json")["parked_questions"], load(KYC / "dor_report_kyc.json"),
                  load(KYC / "ir_client_kyc_as_is.json"),
                  "the to-be process (v12), produced from a one-line idea: as-is interview, AI improvements, "
                  "refinement (polish off)",
                  "Rendered by M7 from the to-be process v12. One scenario per acceptance criterion.",
                  "client_kyc/stories_client_kyc.md", "client_kyc/features/client_kyc.feature")


SAMPLES_ALL = [onboarding, kyc]
