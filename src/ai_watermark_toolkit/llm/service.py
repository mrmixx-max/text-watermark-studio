from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Any

LLM_CFG = Path(__file__).resolve().parents[3] / "data" / "local_llm.json"

DEFAULT_CFG = {
    "provider": "llama.cpp-openai-compatible",
    "model_family": "mradermacher/EuroLLM-9B-Instruct-2512-GGUF",
    "model_variant": "Q4_K_M",
    "server_base_url": "http://127.0.0.1:8080/v1",
    "chat_endpoint": "/chat/completions",
    "health_ui": "http://127.0.0.1:8080",
    "download_hint": "llama-server -hf mradermacher/EuroLLM-9B-Instruct-2512-GGUF:Q4_K_M",
    "installed": False,
    "updated_at": None,
    "sampling": {
        "temperature": 0.8,
        "top_p": 0.95,
        "top_k": 40,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.1,
        "seed": -1,
        "min_p": 0.05,
        "typical_p": 1.0,
        "mirostat": 0,
        "mirostat_tau": 5.0,
        "mirostat_eta": 0.1,
        "max_tokens": 2048,
        "stop": [],
        "response_format": "text",
    },
}

# Valid ranges for each sampling parameter
SAMPLING_RANGES = {
    "temperature": (0.0, 2.0),
    "top_p": (0.0, 1.0),
    "top_k": (0, 100),
    "frequency_penalty": (-2.0, 2.0),
    "presence_penalty": (-2.0, 2.0),
    "repeat_penalty": (1.0, 2.0),
    "seed": (-1, 2**31 - 1),
    "min_p": (0.0, 1.0),
    "typical_p": (0.0, 1.0),
    "mirostat": (0, 2),
    "mirostat_tau": (0.0, 10.0),
    "mirostat_eta": (0.0, 1.0),
    "max_tokens": (1, 8192),
}

# Human-readable descriptions
SAMPLING_DESCRIPTIONS = {
    "temperature": "Randomness (0=precise, 2=chaotic)",
    "top_p": "Nucleus sampling (0.9=top 90%% tokens)",
    "top_k": "Top-K sampling (40=consider top 40)",
    "frequency_penalty": "Penalize repeated tokens (0=off)",
    "presence_penalty": "Penalize token presence (0=off)",
    "repeat_penalty": "Repetition penalty (1.0=off, 1.5=strong)",
    "seed": "Random seed (-1=random)",
    "min_p": "Minimum token probability (0.0=off)",
    "typical_p": "Typical-p sampling (1.0=off)",
    "mirostat": "Mirostat mode (0=off, 1=v1, 2=v2)",
    "mirostat_tau": "Mirostat target entropy",
    "mirostat_eta": "Mirostat learning rate",
    "max_tokens": "Maximum response tokens",
}

# Interactive presets
SAMPLING_PRESETS = {
    "1": {
        "name": "Conservative",
        "description": "Precise, factual, low randomness",
        "values": {"temperature": 0.3, "top_p": 0.85, "top_k": 20, "repeat_penalty": 1.1, "min_p": 0.05},
    },
    "2": {
        "name": "Balanced",
        "description": "Natural prose, slight variation",
        "values": {"temperature": 0.7, "top_p": 0.9, "top_k": 40, "repeat_penalty": 1.1, "min_p": 0.05},
    },
    "3": {
        "name": "Creative",
        "description": "Diverse, unpredictable (default)",
        "values": {"temperature": 0.9, "top_p": 0.95, "top_k": 60, "repeat_penalty": 1.0, "min_p": 0.02},
    },
    "4": {
        "name": "Chaotic",
        "description": "Highly random, experimental",
        "values": {"temperature": 1.2, "top_p": 1.0, "top_k": 100, "repeat_penalty": 1.0, "min_p": 0.0},
    },
}


@dataclass
class SamplingConfig:
    """LLM sampling parameters for generation.

    Controls randomness, diversity, and repetition in LLM output.
    Maps to both OpenAI-compatible and llama.cpp parameters.
    """

    temperature: float = 0.8
    top_p: float = 0.95
    top_k: int = 40
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    repeat_penalty: float = 1.1
    seed: int = -1
    min_p: float = 0.05
    typical_p: float = 1.0
    mirostat: int = 0
    mirostat_tau: float = 5.0
    mirostat_eta: float = 0.1
    max_tokens: int = 2048
    stop: list[str] = field(default_factory=list)
    response_format: str = "text"

    def clamp(self) -> "SamplingConfig":
        """Clamp all values to valid ranges."""
        for param, (lo, hi) in SAMPLING_RANGES.items():
            val = getattr(self, param)
            if val is not None:
                setattr(self, param, max(lo, min(hi, val)))
        return self

    def to_openai_dict(self) -> dict[str, Any]:
        """Convert to OpenAI-compatible API parameters."""
        params = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "max_tokens": self.max_tokens,
            "seed": self.seed if self.seed > 0 else None,
        }
        if self.stop:
            params["stop"] = self.stop
        return {k: v for k, v in params.items() if v is not None}

    def to_llama_cpp_dict(self) -> dict[str, Any]:
        """Convert to llama.cpp /completion API parameters."""
        params = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "repeat_penalty": self.repeat_penalty,
            "min_p": self.min_p,
            "typical_p": self.typical_p if self.typical_p < 1.0 else None,
            "mirostat": self.mirostat if self.mirostat > 0 else None,
            "mirostat_tau": self.mirostat_tau if self.mirostat > 0 else None,
            "mirostat_eta": self.mirostat_eta if self.mirostat > 0 else None,
            "seed": self.seed if self.seed > 0 else None,
            "n_predict": self.max_tokens,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
        }
        if self.stop:
            params["stop"] = self.stop
        return {k: v for k, v in params.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "SamplingConfig":
        """Create from dict (ignores unknown keys)."""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


def interactive_sampling_config() -> SamplingConfig:
    """Interactive parameter regulator — prompt user to configure sampling."""
    print("\n🎛️  LLM Sampling Parameter Regulator")
    print("=" * 50)

    # Preset selection
    print("\n📋 Presets:")
    for key, preset in SAMPLING_PRESETS.items():
        marker = " ← default" if key == "2" else ""
        print(f"   [{key}] {preset['name']}: {preset['description']}{marker}")
    print("   [5] Custom — set each parameter manually")
    print("   [Enter] Keep current settings")

    while True:
        try:
            choice = input("\nChoose [1-5] (Enter=keep): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return SamplingConfig()

        if not choice:
            return SamplingConfig()
        if choice in SAMPLING_PRESETS:
            return SamplingConfig(**SAMPLING_PRESETS[choice]["values"])
        if choice == "5":
            break
        print("   Invalid choice. Enter 1-5 or Enter.")

    # Custom parameter input
    print("\n🔧 Custom Parameters (Enter=keep default):")
    cfg = SamplingConfig()
    for param, (lo, hi) in SAMPLING_RANGES.items():
        desc = SAMPLING_DESCRIPTIONS.get(param, "")
        current = getattr(cfg, param)
        while True:
            try:
                raw = input(f"   {param} [{lo}-{hi}] ({desc}) = {current}: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return cfg.clamp()
            if not raw:
                break
            try:
                val = type(current)(raw)
                if lo <= val <= hi:
                    setattr(cfg, param, val)
                    break
                print(f"      Must be between {lo} and {hi}")
            except (ValueError, TypeError):
                print(f"      Invalid value for {type(current).__name__}")

    return cfg.clamp()


class LocalLLMService:
    """Service for managing local LLM configuration and sampling parameters."""

    def __init__(self, path: Path | None = None):
        self.path = path or LLM_CFG
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(DEFAULT_CFG, indent=2), encoding="utf-8")

    def load(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, cfg: dict) -> dict:
        cfg["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return cfg

    def configure(
        self, server_base_url: str | None = None, model_variant: str | None = None, installed: bool | None = None
    ) -> dict:
        cfg = self.load()
        if server_base_url:
            cfg["server_base_url"] = server_base_url.rstrip("/")
        if model_variant:
            cfg["model_variant"] = model_variant
            cfg["download_hint"] = f"llama-server -hf mradermacher/EuroLLM-9B-Instruct-2512-GGUF:{model_variant}"
        if installed is not None:
            cfg["installed"] = installed
        return self.save(cfg)

    def configure_sampling(self, sampling: dict | SamplingConfig) -> dict:
        """Update sampling parameters."""
        cfg = self.load()
        if isinstance(sampling, SamplingConfig):
            cfg["sampling"] = asdict(sampling.clamp())
        else:
            cfg["sampling"] = sampling
        return self.save(cfg)

    def get_sampling_config(self) -> SamplingConfig:
        """Get current sampling configuration."""
        cfg = self.load()
        return SamplingConfig.from_dict(cfg.get("sampling", {}))

    def list_models(self) -> list[dict]:
        """List configured models. Returns installed model info from config."""
        cfg = self.load()
        models = []
        variant = cfg.get("model_variant")
        if variant:
            models.append({"name": variant, "installed": cfg.get("installed", False)})
        return models

    def use_model(self, name: str) -> dict:
        """Activate a model by name."""
        return self.configure(model_variant=name)

    def _ollama(self, path: str, method: str = "GET", payload: dict | None = None, timeout: float = 5.0) -> dict:
        """Make a raw HTTP request to the Ollama API."""
        import urllib.request

        cfg = self.load()
        base = cfg.get("server_base_url", "http://localhost:11434")
        url = f"{base}{path}"
        req = urllib.request.Request(url, method=method)
        req.add_header("Content-Type", "application/json")
        if payload:
            req.data = json.dumps(payload).encode("utf-8")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def status(self) -> dict:
        cfg = self.load()
        cfg["effective_base_url"] = os.getenv("LOCAL_LLM_BASE_URL", cfg["server_base_url"])
        return cfg
