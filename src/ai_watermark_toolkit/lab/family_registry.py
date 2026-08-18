from __future__ import annotations

from .models import FamilySpec

FAMILIES = [
    FamilySpec('unicode_zero_width', 'Unicode / Zero-Width', 'existing_text', 'invisible', 'fragile', 'private_or_public', ['raw_text_access'], 'Covers zero-width and Unicode-layer embeddings.'),
    FamilySpec('lexical_choice', 'Lexical Choice', 'existing_text', 'subtle', 'fragile_to_medium', 'heuristic', ['language_model_or_rules'], 'Encodes bits or provenance through synonym and token choice.'),
    FamilySpec('syntactic_pattern', 'Syntactic Pattern', 'existing_text', 'subtle', 'medium', 'heuristic', ['parser_or_rules'], 'Uses sentence structure or transformation rules.'),
    FamilySpec('format_layout', 'Format / Layout', 'existing_text', 'visible_or_invisible', 'fragile', 'public', ['document_or_markup_layer'], 'Whitespace, layout, markup and rendering channel markers.'),
    FamilySpec('sampling_bias', 'Sampling / Logit Bias (post-hoc rewrite + experimental generation-time sampler)', 'generation_or_edit', 'invisible', 'medium', 'keyed', ['decoder_control', 'key_material'], 'Green-list/red-list KGW: post-hoc text rewrite (standard) plus an experimental generation-time logit bias via a deterministic synthetic sampler (green_rate ~0.88 at bias=2.0, gamma=0.5; real Ollama generator shows no native bias — audit 2026-08-13).'),
    FamilySpec('semantic_structure', 'Semantic / Structure', 'generation_or_edit', 'subtle', 'medium_to_high', 'family_specific', ['semantic_parser_or_model'], 'Meaning-preserving but structured patterns for provenance.'),
    FamilySpec('localized_provenance', 'Localized Provenance', 'generation_time', 'invisible', 'medium_to_high', 'family_specific', ['localized_detector'], 'Section- or span-level watermark localization.'),
    FamilySpec('training_time', 'Training-Time / Ownership', 'model_level', 'invisible', 'varies', 'whitebox_or_specialized', ['model_or_training_access'], 'Backdoor-style or ownership-oriented provenance signals.'),
]


def list_families():
    return [f.to_dict() for f in FAMILIES]
