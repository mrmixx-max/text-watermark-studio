from __future__ import annotations

from pydantic import BaseModel


class TextRequest(BaseModel):
    text: str
    lang: str = 'auto'
    intensity: str = 'standard'
    nfkc: bool = False
    fold_confusables: bool = False
