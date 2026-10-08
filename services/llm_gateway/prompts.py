"""Prompt files (prompts/*.md): load, validate on boot, render. See prompts/README.md for the format.

No prompt text lives in Python: the gateway's own wording (preamble, validation retry) is in prompts/_*.md too.
"""
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jinja2
import jinja2.meta
import yaml

from ir_core.llm_models import LLM_OUTPUT_MODELS

PREAMBLE, RETRY = "_preamble", "_validation_retry"
PARTIALS = {PREAMBLE: set(), RETRY: {"validation_error"}}  # gateway-owned partials and their variables
ALLOWED_KEYS = {"name", "module", "output_model", "variables", "temperature", "model", "description"}
FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.S)
# An opening or closing <data>/<source> tag inside a value would let source text escape its delimiters.
DELIMITER_TAG = re.compile(r"<(/?)(data|source)\b", re.I)


class PromptConfigError(Exception):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("invalid prompt files:\n  " + "\n  ".join(problems))


class PromptVariablesError(ValueError):
    pass


def _finalize(value: Any) -> str:
    """Every {{ value }}: strings as-is, anything else as JSON; delimiter tags inside values are neutralised."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return DELIMITER_TAG.sub(r"&lt;\1\2", text)


ENV = jinja2.Environment(undefined=jinja2.StrictUndefined, autoescape=False, keep_trailing_newline=True,
                         finalize=_finalize)


@dataclass(frozen=True)
class Prompt:
    name: str
    path: Path
    sha256: str  # of the file content: logged with every call and part of the cassette key
    mtime_ns: int
    module: str
    output_model: str | None
    variables: tuple[str, ...]
    temperature: float
    model: str | None
    body: str
    template: jinja2.Template

    def render(self, variables: dict[str, Any]) -> str:
        missing = [v for v in self.variables if v not in variables]
        extra = sorted(set(variables) - set(self.variables))
        if missing or extra:
            raise PromptVariablesError(f"{self.name}: missing variables {missing}, unexpected variables {extra} "
                                       f"(declared: {list(self.variables)})")
        return self.template.render(**variables)


def parse_prompt(path: Path) -> Prompt:
    """Parse and validate one file; raises PromptConfigError naming every problem in it."""
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    problems: list[str] = []
    m = FRONT_MATTER.match(text)
    if not m:
        raise PromptConfigError([f"{path.name}: missing '---' front matter"])
    try:
        fm = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        raise PromptConfigError([f"{path.name}: front matter is not YAML: {e}"]) from None
    if not isinstance(fm, dict):
        raise PromptConfigError([f"{path.name}: front matter must be a mapping"])
    name, body = path.stem, m.group(2)

    if fm.get("name") != name:
        problems.append(f"{path.name}: name '{fm.get('name')}' must equal the file name '{name}'")
    if not fm.get("module"):
        problems.append(f"{path.name}: module is required")
    if unknown := sorted(set(fm) - ALLOWED_KEYS):
        problems.append(f"{path.name}: unknown front matter keys {unknown}")
    variables = fm.get("variables") or []
    if not isinstance(variables, list) or not all(isinstance(v, str) for v in variables):
        problems.append(f"{path.name}: variables must be a list of names")
        variables = []
    elif len(set(variables)) != len(variables):
        problems.append(f"{path.name}: variables are listed twice")

    if name in PARTIALS:
        if set(variables) != PARTIALS[name]:
            problems.append(f"{path.name}: gateway partial must declare variables {sorted(PARTIALS[name])}")
    else:
        if fm.get("output_model") not in LLM_OUTPUT_MODELS:
            problems.append(f"{path.name}: output_model '{fm.get('output_model')}' is not a model in "
                            f"ir_core.llm_models")
        if not isinstance(fm.get("temperature", 0), int | float) or not 0 <= fm.get("temperature", 0) <= 1:
            problems.append(f"{path.name}: temperature must be a number in [0, 1]")
        if "model" in fm and not isinstance(fm["model"], str):
            problems.append(f"{path.name}: model must be a string")

    template = None
    try:
        template = ENV.from_string(body)
        used = jinja2.meta.find_undeclared_variables(ENV.parse(body))
        if undeclared := sorted(used - set(variables)):
            problems.append(f"{path.name}: template uses undeclared variables {undeclared}")
        if unused := sorted(set(variables) - used):
            problems.append(f"{path.name}: declared variables never rendered {unused} (the model would not see them)")
    except jinja2.TemplateSyntaxError as e:
        problems.append(f"{path.name}: template does not compile: line {e.lineno}: {e.message}")
    if problems:
        raise PromptConfigError(problems)
    return Prompt(name=name, path=path, sha256=hashlib.sha256(raw).hexdigest(), mtime_ns=path.stat().st_mtime_ns,
                  module=str(fm["module"]), output_model=fm.get("output_model"), variables=tuple(variables),
                  temperature=float(fm.get("temperature", 0)), model=fm.get("model"), body=body, template=template)


class PromptRegistry:
    """All prompts, validated together at start-up. With `reload=True` (dev), an edited file is re-read on use."""

    def __init__(self, directory: Path, *, reload: bool = False):
        self.directory, self.reload = directory, reload
        self._prompts: dict[str, Prompt] = {}
        problems: list[str] = []
        for path in sorted(directory.glob("*.md")):
            if path.name == "README.md":
                continue
            try:
                self._prompts[path.stem] = parse_prompt(path)
            except PromptConfigError as e:
                problems += e.problems
        problems += [f"{p}.md: missing (the gateway needs it)" for p in PARTIALS if p not in self._prompts
                     and not any(x.startswith(f"{p}.md") for x in problems)]
        if problems:
            raise PromptConfigError(problems)

    def names(self) -> list[str]:
        return sorted(n for n in self._prompts if n not in PARTIALS)

    def get(self, name: str) -> Prompt:
        if name not in self._prompts:
            raise KeyError(f"no prompt file prompts/{name}.md")
        prompt = self._prompts[name]
        if self.reload and prompt.path.stat().st_mtime_ns != prompt.mtime_ns:
            prompt = self._prompts[name] = parse_prompt(prompt.path)
        return prompt
