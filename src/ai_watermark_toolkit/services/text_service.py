from __future__ import annotations

from ..pipeline import detect_text, run_pipeline
from ..transform.clean import clean_text
from ..transform.dilute import dilute_text


class TextService:
    def detect(self, text: str, lang: str = 'auto') -> dict:
        return detect_text(text, lang=lang)

    def clean(self, text: str, nfkc: bool = False, fold_confusables: bool = False) -> dict:
        return clean_text(text, nfkc=nfkc, fold_confusables=fold_confusables).to_dict()

    def dilute(self, text: str, intensity: str = 'standard') -> dict:
        return dilute_text(text, intensity=intensity).to_dict()

    def pipeline(self, text: str, lang: str = 'auto', intensity: str = 'standard', nfkc: bool = False, fold_confusables: bool = False, rewrite_mode: str | None = None, aggressive: bool = False) -> dict:
        out, report = run_pipeline(text, lang=lang, intensity=intensity, nfkc=nfkc, fold_confusables=fold_confusables, rewrite_mode=rewrite_mode, aggressive=aggressive)
        return {'text': out, 'report': report}
