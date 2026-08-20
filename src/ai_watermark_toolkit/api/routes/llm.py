from fastapi import APIRouter, Request
from pydantic import BaseModel, model_validator
from ...llm.service import LocalLLMService, SamplingConfig, SAMPLING_PRESETS, SAMPLING_RANGES, SAMPLING_DESCRIPTIONS
from ..response_utils import respond, checkbox_to_bool

router = APIRouter(prefix="/api/llm", tags=["llm"])
svc = LocalLLMService()


class ConfigureRequest(BaseModel):
    server_base_url: str | None = None
    model_variant: str | None = None
    installed: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data):
        if isinstance(data, dict):
            if "installed" in data:
                data["installed"] = checkbox_to_bool(data.get("installed"))
        return data


class SamplingRequest(BaseModel):
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    repeat_penalty: float | None = None
    seed: int | None = None
    min_p: float | None = None
    typical_p: float | None = None
    mirostat: int | None = None
    mirostat_tau: float | None = None
    mirostat_eta: float | None = None
    max_tokens: int | None = None
    stop: list[str] | None = None
    response_format: str | None = None
    preset: str | None = None


@router.get("/status")
def status(request: Request):
    return respond(request, svc.status())


@router.post("/configure")
def configure(req: ConfigureRequest, request: Request):
    return respond(request, svc.configure(req.server_base_url, req.model_variant, req.installed))


@router.get("/sampling")
def get_sampling(request: Request):
    """Get current sampling configuration and available presets/ranges."""
    cfg = svc.get_sampling_config()
    return respond(
        request,
        {
            "current": {k: v for k, v in cfg.__dict__.items()},
            "presets": SAMPLING_PRESETS,
            "ranges": SAMPLING_RANGES,
            "descriptions": SAMPLING_DESCRIPTIONS,
        },
    )


@router.post("/sampling")
def set_sampling(req: SamplingRequest, request: Request):
    """Update sampling parameters. Optionally apply a preset first."""
    current = svc.get_sampling_config()

    if req.preset and req.preset in SAMPLING_PRESETS:
        # Apply preset as base
        current = SamplingConfig(**SAMPLING_PRESETS[req.preset]["values"])

    # Override with explicitly provided values
    data = req.model_dump(exclude={"preset"}, exclude_none=True)
    for key, val in data.items():
        if hasattr(current, key):
            setattr(current, key, val)

    svc.configure_sampling(current)
    return respond(request, {"sampling": {k: v for k, v in current.__dict__.items()}})
