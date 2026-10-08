"""RecordReplay cassettes: recorded responses keyed by (prompt_file, prompt_sha256, sha256(variables)).

Editing a prompt changes its sha256, so its cassettes stop matching on purpose: re-record them. A cassette holds one
response per attempt, so a recorded validation retry replays too. Cassettes hold model output, not the rendered
prompt, so they carry no more source text than the response itself.
"""
import json
from pathlib import Path

from .providers import ProviderResponse


class CassetteMissing(LookupError):
    pass


class CassetteStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def path(self, prompt_file: str, prompt_sha256: str, variables_sha256: str) -> Path:
        return self.directory / prompt_file / f"{prompt_sha256[:16]}_{variables_sha256[:16]}.json"

    def load(self, prompt_file: str, prompt_sha256: str, variables_sha256: str, attempt: int) -> ProviderResponse:
        path = self.path(prompt_file, prompt_sha256, variables_sha256)
        if not path.exists():
            raise CassetteMissing(f"no cassette for {prompt_file} (prompt {prompt_sha256[:12]}, variables "
                                  f"{variables_sha256[:12]}); record it with RS_LLM_MODE=record")
        data = json.loads(path.read_text())
        if data["prompt_sha256"] != prompt_sha256 or data["variables_sha256"] != variables_sha256:
            raise CassetteMissing(f"{path} belongs to a different prompt or variables")
        if attempt >= len(data["responses"]):
            raise CassetteMissing(f"{path} has no recorded response for attempt {attempt + 1}")
        return ProviderResponse(**data["responses"][attempt])

    def save(self, prompt_file: str, prompt_sha256: str, variables_sha256: str, attempt: int,
             response: ProviderResponse) -> None:
        path = self.path(prompt_file, prompt_sha256, variables_sha256)
        data = {"prompt_file": prompt_file, "prompt_sha256": prompt_sha256, "variables_sha256": variables_sha256,
                "responses": []}
        if attempt > 0 and path.exists():
            data = json.loads(path.read_text())
        data["responses"] = data["responses"][:attempt] + [response.__dict__]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
