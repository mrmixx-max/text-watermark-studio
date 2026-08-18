from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

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

    # ---- multi-model support ------------------------------------------------

    @staticmethod
    def ollama_base() -> str:
        """Ollama HTTP endpoint (override with OLLAMA_BASE_URL)."""
        import os as _os
        return _os.getenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11434').rstrip('/')

    @staticmethod
    def _validate_url_scheme(url: str) -> None:
        """Reject non-HTTP(S) schemes to prevent SSRF via env var injection."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            raise ValueError(f"ollama_base scheme must be http/https, got: {parsed.scheme}")

    def _ollama(self, path: str, method: str = 'GET', payload: dict | None = None,
                timeout: int = 30):
        import urllib.error
        import urllib.request
        url = f"{self.ollama_base()}{path}"
        self._validate_url_scheme(url)
        data = json.dumps(payload).encode('utf-8') if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310  # scheme validated by _validate_url_scheme
                return resp.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"ollama_{path.lstrip('/').replace('/', '_')}_failed: "
                               f"HTTP {e.code} {e.reason}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"ollama_unreachable: {e.reason}") from e

    def list_models(self) -> list[dict]:
        """All models the local Ollama instance knows (GET /api/tags)."""
        body = json.loads(self._ollama('/api/tags'))
        return body.get('models', [])

    def model_installed(self, model_name: str) -> bool:
        names = {m.get('name', '') for m in self.list_models()}
        # accept exact names and names without the ':latest' suffix
        return model_name in names or f"{model_name}:latest" in names

    def install_model(self, model_name: str, progress=None) -> dict:
        """Pull a model through the Ollama API (POST /api/pull) and point the
        studio config at it. `progress` (optional callable) receives status
        lines from the NDJSON pull stream. Raises RuntimeError when Ollama is
        unreachable or the pull fails."""
        import urllib.request

        def _line_status(line: dict) -> str:
            return line.get('status', '')

        url = f"{self.ollama_base()}/api/pull"
        self._validate_url_scheme(url)
        payload = json.dumps({'name': model_name, 'stream': True}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, method='POST',
                                     headers={'Content-Type': 'application/json'})
        last_status = ''
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:  # nosec B310  # scheme validated by _validate_url_scheme
                for raw in resp:
                    if not raw.strip():
                        continue
                    try:
                        line = json.loads(raw.decode('utf-8').strip())
                    except json.JSONDecodeError:
                        continue
                    if 'error' in line:
                        raise RuntimeError(f"ollama_pull_failed: {line['error']}")
                    st = _line_status(line)
                    if st and st != last_status:
                        last_status = st
                        if progress:
                            progress(st)
                        if line.get('completed') and line.get('total'):
                            pct = int(line['completed'] / line['total'] * 100)
                            if progress:
                                progress(f"{st} {pct}%")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"ollama_pull_failed: HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"ollama_unreachable: {e.reason}") from e

        if not self.model_installed(model_name):
            raise RuntimeError("ollama_pull_failed: model not present after pull")

        cfg = self.load()
        cfg['model_variant'] = model_name
        cfg['model_family'] = model_name
        cfg['download_hint'] = f'ollama pull {model_name}'
        cfg['installed'] = True
        cfg['server_base_url'] = f"{self.ollama_base()}/v1"
        self.save(cfg)
        return {'model': model_name, 'installed': True, 'config': self.status()}

    def use_model(self, model_name: str) -> dict:
        """Point the studio at an already-installed model (no download)."""
        if not self.model_installed(model_name):
            raise ValueError(f"model_not_installed: {model_name}")
        cfg = self.load()
        cfg['model_variant'] = model_name
        cfg['model_family'] = model_name
        cfg['installed'] = True
        self.save(cfg)
        return self.status()
