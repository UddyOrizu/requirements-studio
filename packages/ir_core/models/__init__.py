"""Pydantic v2 models mirroring schemas/*.json. The JSON Schemas are the contract; these are the typed view."""
from pydantic import BaseModel

from .common import dump
from .gap import Gap
from .idea import Idea
from .intake_session import IntakeSession
from .patch import Patch, PatchOp
from .process_ir import ProcessIR
from .question import Question
from .suggestion import Suggestion

# schema file stem (schemas/<name>.schema.json) → root model
MODEL_FOR_SCHEMA: dict[str, type[BaseModel]] = {
    "process-ir": ProcessIR,
    "patch": Patch,
    "gap": Gap,
    "question": Question,
    "idea": Idea,
    "suggestion": Suggestion,
    "intake-session": IntakeSession,
}

__all__ = ["MODEL_FOR_SCHEMA", "Gap", "Idea", "IntakeSession", "Patch", "PatchOp", "ProcessIR", "Question",
           "Suggestion", "dump"]
