"""S1 LLM gateway. Modules call `gateway.complete_json("<prompt file name>", variables, OutputModel)`."""
from pathlib import Path

from services.common.settings import Settings

from .cassettes import CassetteMissing, CassetteStore
from .gateway import LLMCallRecord, LLMGateway, LLMOutputInvalid
from .prompts import PromptConfigError, PromptRegistry, PromptVariablesError
from .providers import Provider, ProviderError, ProviderResponse

REPO = Path(__file__).resolve().parents[2]


def build_gateway(settings: Settings, *, provider: Provider | None = None, sessionmaker=None) -> LLMGateway:
    """Load and validate every prompt (a bad prompt file stops start-up) and configure the mode."""
    prompts = PromptRegistry(Path(settings.prompt_dir or REPO / "prompts"), reload=settings.env == "dev")
    cassettes = CassetteStore(Path(settings.llm_cassette_dir or REPO / "tests" / "cassettes"))
    return LLMGateway(prompts, mode=settings.llm_mode, default_model=settings.llm_model, provider=provider,
                      cassettes=cassettes, sessionmaker=sessionmaker)


__all__ = ["CassetteMissing", "CassetteStore", "LLMCallRecord", "LLMGateway", "LLMOutputInvalid", "PromptConfigError",
           "PromptRegistry", "PromptVariablesError", "Provider", "ProviderError", "ProviderResponse", "build_gateway"]
