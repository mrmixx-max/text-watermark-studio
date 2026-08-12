from __future__ import annotations

from .families.unicode_zero_width import FamilyPlugin as UnicodeZeroWidth
from .families.lexical_choice import FamilyPlugin as LexicalChoice
from .families.syntactic_pattern import FamilyPlugin as SyntacticPattern
from .families.format_layout import FamilyPlugin as FormatLayout
from .families.sampling_bias import FamilyPlugin as SamplingBias
from .families.semantic_structure import FamilyPlugin as SemanticStructure
from .families.localized_provenance import FamilyPlugin as LocalizedProvenance
from .families.training_time import FamilyPlugin as TrainingTime


def get_family_plugins():
    items = [
        UnicodeZeroWidth(), LexicalChoice(), SyntacticPattern(), FormatLayout(),
        SamplingBias(), SemanticStructure(), LocalizedProvenance(), TrainingTime(),
    ]
    return {item.slug: item for item in items}
