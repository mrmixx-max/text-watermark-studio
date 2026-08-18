"""P0-3 (Rest): Ensemble-Heuristik ehrlich — Heuristik-Zähler (Kommas,
'furthermore') können nie ein Wasserzeichen-Signal behaupten; Demo-Keys
werden aus der API-Ensemble ausgeschlossen.

Der Runde-4-Review fand: text.count(',')*0.01 + count('furthermore')*0.08
gewichten echte KGW-Statistik mit und erzeugten Verdicts auf öffentlich
bekannten Demo-Secrets. Der Registry-Teil (seed_demo) ist bereits getestet;
hier wird die Verdict-/Expositions-Seite abgedeckt.
"""

from ai_watermark_toolkit.forensics.ensemble import ensemble_detect, score_segment
from ai_watermark_toolkit.forensics.kgw import mark_greenlist
from ai_watermark_toolkit.forensics.frequent_vocab import FREQUENT_VOCAB

KEY = "demo-kgw-secret-0001"

COMMA_TEXT = (
    "apples, oranges, pears, bananas, grapes, plums, cherries, "
    "peaches, melons, berries, lemons, limes, figs, dates, "
    "kiwis, mangoes, papayas, apricots, quinces, nectarines, "
    "guavas, lychees, coconuts, olives, raisins, currants, "
    "gooseberries, cranberries, mulberries, loganberries, "
    "boysenberries, elderberries, huckleberries, blueberries, "
    "raspberries, blackberries, strawberries, gooseberries, "
    "currants, raisins, figs, dates, plums, peaches, melons, "
    "berries, lemons, limes, kiwis, mangoes, papayas, apricots, "
    "quinces, nectarines, guavas, lychees, coconuts, olives."
)

FURTHERMORE_TEXT = (
    "Furthermore, the system remains stable. Furthermore, "
    "the results are consistent. Furthermore, the metrics "
    "improve. Furthermore, the tests pass. Furthermore, "
    "the code is clean. Furthermore, the design is sound. "
    "Furthermore, the review succeeds. Furthermore, the "
    "deployment runs. Furthermore, the users agree. "
    "Furthermore, the data supports it."
)


def _marked() -> str:
    return mark_greenlist(
        "Local AI models are crucial for maintaining user privacy and ensuring "
        "secure interactions with data processing. This reduces the amount of "
        "personal information shared with third parties. On-device processing "
        "keeps sensitive details under your control. The result is a lower risk "
        "of breaches and stronger protection. People gain more confidence when "
        "their data stays local and private systems keep everything on device "
        "without sending anything to remote servers.",
        KEY,
        vocab=FREQUENT_VOCAB,
        seed=0,
    )["text"]


class TestHeuristicNeverClaimsWatermark:
    def test_comma_heuristic_is_hints_only(self):
        keys = [{"key_id": "demo-green-1", "family": "greenlist_bias", "is_demo": True}]
        r = ensemble_detect(COMMA_TEXT, keys)
        assert r["verdict"] == "heuristic_hints_only", r
        assert r["heuristic_score"] is not None
        assert r["kgw_score"] is None

    def test_furthermore_heuristic_is_hints_only(self):
        keys = [
            {
                "key_id": "demo-semantic-1",
                "family": "semantic_pattern",
                "trigger_phrase": "furthermore",
                "is_demo": True,
            }
        ]
        r = ensemble_detect(FURTHERMORE_TEXT, keys)
        assert r["verdict"] == "heuristic_hints_only", r
        # Der Score bleibt als Beobachtung sichtbar, aber der Verdict lügt nicht.
        assert r["heuristic_score"] is not None and r["heuristic_score"] > 0.0

    def test_heuristic_components_exposed(self):
        seg = score_segment(COMMA_TEXT, {"family": "greenlist_bias"})
        assert "heuristic_components" in seg
        assert "comma_bias" in seg["heuristic_components"]
        seg2 = score_segment(FURTHERMORE_TEXT, {"family": "semantic_pattern"})
        assert "furthermore_bias" in seg2["heuristic_components"]

    def test_kgw_mark_still_detected(self):
        keys = [{"key_id": "demo-kgw-1", "family": "kgw", "secret": KEY, "gamma": 0.25, "is_demo": True}]
        r = ensemble_detect(_marked(), keys)
        assert r["verdict"] == "strong_consistent_signal", r
        assert r["kgw_score"] is not None and r["kgw_score"] > 0.7

    def test_kgw_plus_heuristic_kgw_wins(self):
        keys = [
            {"key_id": "demo-kgw-1", "family": "kgw", "secret": KEY, "gamma": 0.25, "is_demo": True},
            {
                "key_id": "demo-semantic-1",
                "family": "semantic_pattern",
                "trigger_phrase": "furthermore",
                "is_demo": True,
            },
        ]
        r = ensemble_detect(_marked(), keys)
        assert r["verdict"] == "strong_consistent_signal", r


class TestExcludeDemo:
    def test_exclude_demo_filters_keys(self):
        keys = [
            {"key_id": "demo-kgw-1", "family": "kgw", "secret": KEY, "gamma": 0.25, "is_demo": True},
            {"key_id": "real-1", "family": "kgw", "secret": "real-secret", "gamma": 0.25},
        ]
        r = ensemble_detect(_marked(), keys, exclude_demo=True)
        assert r["excluded_demo_keys"] == 1
        ids = [k["key_id"] for k in r["per_key"]]
        assert "demo-kgw-1" not in ids
        assert "real-1" in ids

    def test_per_key_marks_is_demo(self):
        keys = [{"key_id": "demo-kgw-1", "family": "kgw", "secret": KEY, "gamma": 0.25, "is_demo": True}]
        r = ensemble_detect(_marked(), keys)
        assert r["per_key"][0]["is_demo"] is True


class TestApiExcludesDemo:
    def test_api_detect_never_watermark_on_heuristic_text(self, monkeypatch):
        from fastapi.testclient import TestClient
        from types import SimpleNamespace
        import ai_watermark_toolkit.api.middleware.auth as auth_mod
        import ai_watermark_toolkit.api.routes.forensics as route_mod
        import ai_watermark_toolkit.api.fastapi_app as app_mod

        monkeypatch.setattr(auth_mod, "settings", SimpleNamespace(api_key="test-secret"))
        monkeypatch.setattr(route_mod, "keys", KeyRegistryStub())
        import ai_watermark_toolkit.core.config as cfg_mod

        cfg_mod.settings = SimpleNamespace(
            api_key="test-secret",
            app_env="development",
            cors_origins="*",
            app_name="t",
            log_level="INFO",
            rate_limit_requests=1000,
            rate_limit_window_sec=60,
            redis_url="redis://localhost:6379/0",
        )
        app_mod.settings = cfg_mod.settings
        import importlib

        importlib.reload(app_mod)
        client = TestClient(app_mod.app)
        r = client.post("/api/forensics/detect", json={"text": FURTHERMORE_TEXT}, headers={"X-API-Key": "test-secret"})
        assert r.status_code == 200, r.text
        body = r.json()
        # Der Text enthält nur Demo-Keys (semantic_pattern) — die API schließt
        # Demo-Keys aus: kein Wasserzeichen-Fehlalarm aus 'furthermore'.
        assert body.get("verdict") != "watermark_detected"
        assert body.get("verdict") != "weak_or_mixed_signal"


class KeyRegistryStub:
    def list_keys(self):
        return [
            {
                "key_id": "demo-semantic-1",
                "family": "semantic_pattern",
                "trigger_phrase": "furthermore",
                "is_demo": True,
            },
        ]
