from dataclasses import dataclass
from typing import Literal

IssueKind = Literal["schema", "integrity", "forbidden_path", "envelope", "patch_op"]


@dataclass(frozen=True)
class Issue:
    """One validation problem. `path` is a JSON Pointer into the document the issue was found in."""

    kind: IssueKind
    path: str
    message: str
    element_id: str | None = None
    ref_id: str | None = None  # integrity: the id that is missing, rejected or of the wrong kind

    def __str__(self) -> str:
        return self.message


class PatchRejected(Exception):
    """A patch cannot be applied. The Patch Service returns `status_code` with `errors` as the body."""

    status_code = 422

    def __init__(self, errors: list[Issue]):
        self.errors = errors
        super().__init__("; ".join(f"[{e.kind}] {e.path}: {e.message}" for e in errors))
