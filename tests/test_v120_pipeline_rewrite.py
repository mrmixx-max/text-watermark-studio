"""Behavioral tests for structural/backtranslate integration into the pipeline
(2026-08-13).

Contract: run_pipeline gains an optional rewrite phase after dilute. Without
rewrite_mode the behavior is unchanged (rewrite: None). With rewrite_mode the
rewritten text differs and the report carries the rewrite phase. The API route
exposes it.
"""

from ai_watermark_toolkit.pipeline import run_pipeline

TEXT = (
    "The first sentence establishes context. "
    "The second provides the main argument. "
    "The third gives supporting evidence. "
    "The fourth draws the conclusion."
)


class TestPipelineRewrite:
    def test_default_has_no_rewrite_phase(self):
        _out, report = run_pipeline(TEXT)
        assert report["rewrite"] is None
        assert report["after"] is not None

    def test_structural_mode_rewrites(self):
        out, report = run_pipeline(TEXT, rewrite_mode="structural")
        assert report["rewrite"] is not None
        assert report["rewrite"]["mode"] == "structural"
        assert report["rewrite"]["similarity_ratio"] < 1.0
        assert out != TEXT
        assert out.startswith("The first sentence")

    def test_backtranslate_mode_has_phase(self):
        _out, report = run_pipeline(TEXT, rewrite_mode="backtranslate")
        assert report["rewrite"]["mode"] == "backtranslate"
        assert any("No-LLM path" in s for s in report["rewrite"]["change_log"])

    def test_after_detection_runs_on_rewritten(self):
        _, report = run_pipeline(TEXT, rewrite_mode="structural")
        # the 'after' layer input is the rewritten text: hash matches rewrite output
        before_hash = report["before"]["input_hash"]
        after_hash = report["after"]["input_hash"]
        assert before_hash != after_hash  # rewrite changed the analyzed text


class TestPipelineApi:
    def test_api_pipeline_with_rewrite_mode(self):
        from fastapi.testclient import TestClient

        from ai_watermark_toolkit.api.fastapi_app import app

        c = TestClient(app)
        r = c.post("/api/pipeline", json={"text": TEXT, "rewrite_mode": "structural"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["report"]["rewrite"]["mode"] == "structural"
        assert data["text"] != TEXT

    def test_api_pipeline_default_no_rewrite(self):
        from fastapi.testclient import TestClient

        from ai_watermark_toolkit.api.fastapi_app import app

        c = TestClient(app)
        r = c.post("/api/pipeline", json={"text": TEXT})
        assert r.status_code == 200
        assert r.json()["report"]["rewrite"] is None
