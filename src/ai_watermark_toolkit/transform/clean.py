from __future__ import annotations

from dataclasses import dataclass, asdict
from ..sanitize_unicode import sanitize
from ..strip_markup import strip_markup


@dataclass
class CleanResult:
    text: str
    unicode_removed: int
    confusable_folds: int
    comments_removed: int
    hidden_spans_removed: int

    def to_dict(self) -> dict:
        return asdict(self)


def clean_text(text: str, *, nfkc: bool = False, fold_confusables: bool = False) -> CleanResult:
    markup = strip_markup(text)
    uni = sanitize(markup.text, nfkc=nfkc, fold_confusables=fold_confusables)
    return CleanResult(
        text=uni.text,
        unicode_removed=len(uni.findings),
        confusable_folds=uni.confusable_folds,
        comments_removed=markup.removed_comments,
        hidden_spans_removed=markup.removed_hidden_spans,
    )
