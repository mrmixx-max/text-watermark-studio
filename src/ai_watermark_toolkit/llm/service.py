from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime, timezone

LLM_CFG = Path(__file__).resolve().parents[3] / 'data' / 'local_llm.json'

DEFAULT_CFG = {
    'provider': 'llama.cpp-openai-compatible',
    'model_family': 'mradermacher/EuroLLM-9B-Instruct-2512-GGUF',
    'model_variant': 'Q4_K_M',
    'server_base_url': 'http://127.0.0.1:8080/v1',
    'chat_endpoint': '/chat/completions',
    'health_ui': 'http://127.0.0.1:8080',
    'download_hint': 'llama-server -hf mradermacher/EuroLLM-9B-Instruct-2512-GGUF:Q4_K_M',
    'installed': False,
    'updated_at': None,
}

class LocalLLMService:
    def __init__(self, path: Path | None = None):
        self.path = path or LLM_CFG
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(DEFAULT_CFG, indent=2), encoding='utf-8')

    def load(self):
        return json.loads(self.path.read_text(encoding='utf-8'))

    def save(self, cfg: dict):
        cfg['updated_at'] = datetime.now(timezone.utc).isoformat()
        self.path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
        return cfg

    def configure(self, server_base_url: str | None = None, model_variant: str | None = None, installed: bool | None = None):
        cfg = self.load()
        if server_base_url:
            cfg['server_base_url'] = server_base_url.rstrip('/')
        if model_variant:
            cfg['model_variant'] = model_variant
            cfg['download_hint'] = f'llama-server -hf mradermacher/EuroLLM-9B-Instruct-2512-GGUF:{model_variant}'
        if installed is not None:
            cfg['installed'] = installed
        return self.save(cfg)

    def status(self):
        cfg = self.load()
        cfg['effective_base_url'] = os.getenv('LOCAL_LLM_BASE_URL', cfg['server_base_url'])
        return cfg
