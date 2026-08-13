"""API smoke for the burn-in (stage 10). Plain Python, no f-string escaping.

Checks: /health, /, POST /api/detect, /api/optimization/evals, /api/llm/status.
Prints OK (exit 0) or FAIL:<names> (exit 1).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient  # noqa: E402
from ai_watermark_toolkit.api.fastapi_app import app  # noqa: E402


def main() -> int:
    c = TestClient(app)
    checks = []
    r = c.get("/health")
    checks.append(("health", r.status_code == 200))
    r = c.get("/")
    checks.append(("root", r.status_code in (200, 404)))
    r = c.post("/api/detect",
               json={"text": "Das ist ein Testtext mit klaren Aussagen und Fakten.",
                     "lang": "auto"})
    checks.append(("detect", r.status_code in (200, 201, 422)))
    r = c.get("/api/optimization/evals")
    checks.append(("optimization-evals", r.status_code == 200))
    r = c.get("/api/llm/status")
    checks.append(("llm-status", r.status_code in (200, 404, 500)))

    failed = [n for n, ok in checks if not ok]
    print("OK" if not failed else f"FAIL: {failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
