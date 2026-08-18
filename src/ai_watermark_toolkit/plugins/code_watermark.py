"""Code watermark detector — AI-generated code marker detection.

Detects statistical and stylistic markers associated with AI coding assistants
(GitHub Copilot, CodeLlama, Claude Code, ChatGPT). Detection is heuristic:
AI-generated code tends to exhibit:
  - Uniform, high-density docstrings and inline comments
  - Boilerplate "this function does X" comments above every function
  - Specific generation artifacts (TODO: implement, placeholder returns)
  - Absence of personal coding idiosyncrasies (abbreviated vars, dead code)

Honest limits:
  - No detector is definitive; this is a probabilistic signal.
  - Clean code written by humans with good comment discipline scores high.
  - Obfuscated/minified AI code scores low (markers are stripped).
  - embed() is not applicable (we detect, we don't generate AI code).
"""
from __future__ import annotations

import re

from .base import DetectorPlugin

# Patterns that correlate with AI-generated code.
_AI_COMMENT_PATTERNS = [
    # "This function/method/class does X"
    re.compile(r"(This|Here(?:'s|s)|The)\s+(function|method|class|module|code)\s+(will|does|is|returns|handles|performs|creates|initializes|processes|calculates|implements)", re.IGNORECASE),
    # "# Returns" / "# Args" / "# Raises" doc-comment sections
    re.compile(r"#\s*(Returns|Args|Raises|Yields|Note(?:s)?|Example(?:s)?)\s*[:\-]", re.IGNORECASE),
    # Step-by-step numbered comments
    re.compile(r"#\s*Step\s+\d+", re.IGNORECASE),
    # "TODO: Implement" / "TODO: Add"
    re.compile(r"#\s*TODO\s*:\s*(implement|add|fix|update|complete|refactor)", re.IGNORECASE),
    # "Initialize" / "Set up" / "Configure" comments
    re.compile(r"#\s*(Initialize|Set up|Configure|Create|Define|Declare|Import|Validate|Check|Handle|Parse|Format|Convert|Extract)\s", re.IGNORECASE),
    # "# type:" inline annotations (often AI-suggested)
    re.compile(r"#\s*type:\s*\w", re.IGNORECASE),
]

# Boilerplate comment markers that suggest templated generation
_BOILERPLATE_PATTERNS = [
    re.compile(r"#\s*(Your|Insert|Add|Write|Define)\s+(code|logic|implementation|function|method|class)\s+(here|below|above)", re.IGNORECASE),
    re.compile(r"#\s*\.\.\..*(implement|todo|fixme)", re.IGNORECASE),
    re.compile(r"#\s*PLEASE\s+(NOTE|SEE|IMPLEMENT|ADD)", re.IGNORECASE),
    re.compile(r"#\s*REPLACE\s+(THIS|ME)", re.IGNORECASE),
]

# Function-above-comment density: AI tends to comment EVERY function
_FN_DEF_RE = re.compile(r"^\s*(def\s+\w+|class\s+\w+|function\s+\w+|public\s+|private\s+|protected\s+|static\s+)", re.MULTILINE)
_COMMENT_LINE_RE = re.compile(r"^\s*(#|//|/\*|\*|<!--)", re.MULTILINE)
_DOCSTRING_RE = re.compile(r'(\"\"\"|\'\'\')')


class CodeWatermarkPlugin(DetectorPlugin):
    """Detect AI-generated code markers in source text.

    Returns a score in [0.0, 1.0] indicating the density of AI-associated
    stylistic markers. Higher score = more markers found.
    """

    name = "code_watermark"

    def detect(self, text: str, key_meta: dict) -> dict:
        """Analyze source code text for AI-generation markers.

        key_meta keys used:
          - language: optional hint (python, javascript, etc.) — unused for now
            but reserved for language-specific tuning.
        """
        if not text or not text.strip():
            return {"score": 0.0, "plugin": self.name, "notes": ["empty_input"]}

        lines = text.splitlines()
        total_lines = len(lines)
        if total_lines == 0:
            return {"score": 0.0, "plugin": self.name, "notes": ["empty_input"]}

        notes: list[str] = []
        ai_hits = 0
        boilerplate_hits = 0

        # Count AI-comment pattern hits
        for pat in _AI_COMMENT_PATTERNS:
            matches = pat.findall(text)
            ai_hits += len(matches)
            if matches:
                notes.append(f"ai_pattern_{pat.pattern[:30].strip()}_hits={len(matches)}")

        # Count boilerplate pattern hits
        for pat in _BOILERPLATE_PATTERNS:
            matches = pat.findall(text)
            boilerplate_hits += len(matches)
            if matches:
                notes.append(f"boilerplate_{pat.pattern[:30].strip()}_hits={len(matches)}")

        # Compute comment density
        comment_lines = sum(1 for line in lines if _COMMENT_LINE_RE.match(line))
        comment_density = comment_lines / total_lines if total_lines > 0 else 0.0

        # Docstring ratio (triple-quoted blocks / total lines)
        docstring_count = len(_DOCSTRING_RE.findall(text))
        docstring_density = docstring_count / total_lines if total_lines > 0 else 0.0

        # Function count
        fn_count = len(_FN_DEF_RE.findall(text))

        # Score composition
        # Base score from AI pattern density (patterns per 10 lines)
        pattern_score = min(ai_hits / max(total_lines / 10, 1), 1.0)
        # Boilerplate bonus (stronger signal)
        boilerplate_score = min(boilerplate_hits * 0.15, 0.4)
        # Comment density bonus (very high density = AI-like)
        density_bonus = 0.0
        if comment_density > 0.4:
            density_bonus = min((comment_density - 0.4) * 0.5, 0.2)
        # Docstring density bonus
        docstring_bonus = 0.0
        if docstring_density > 0.05:
            docstring_bonus = min((docstring_density - 0.05) * 2.0, 0.2)

        score = min(pattern_score + boilerplate_score + density_bonus + docstring_bonus, 1.0)

        # Threshold notes
        if score >= 0.7:
            notes.append("high_confidence_ai_markers")
        elif score >= 0.4:
            notes.append("moderate_ai_markers")
        elif score >= 0.2:
            notes.append("mild_ai_markers")
        else:
            notes.append("low_ai_markers")

        notes.append(f"stats:lines={total_lines},comments={comment_lines},functions={fn_count},ai_hits={ai_hits},boilerplate={boilerplate_hits}")

        return {
            "score": round(score, 4),
            "plugin": self.name,
            "notes": notes,
            "details": {
                "comment_density": round(comment_density, 4),
                "docstring_density": round(docstring_density, 4),
                "ai_pattern_hits": ai_hits,
                "boilerplate_hits": boilerplate_hits,
                "function_count": fn_count,
            },
        }

    def clean(self, text: str) -> str:
        """Remove AI-generated comments while preserving functional code.

        Strategy:
          - Remove single-line comments that match AI patterns
          - Remove boilerplate placeholder comments
          - Preserve docstrings and type annotations
          - Preserve inline comments that don't match AI patterns
        """
        if not text:
            return text

        lines = text.splitlines()
        cleaned_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            # Check if the entire line is a comment
            if stripped.startswith(("#", "//")):
                is_ai_comment = any(p.search(stripped) for p in _AI_COMMENT_PATTERNS)
                is_boilerplate = any(p.search(stripped) for p in _BOILERPLATE_PATTERNS)
                if is_ai_comment or is_boilerplate:
                    continue  # drop the line
            cleaned_lines.append(line)

        return "\n".join(cleaned_lines)

    def embed(self, text: str, watermark: str) -> str:
        """Not applicable — we detect AI code, we don't generate it."""
        raise NotImplementedError("embed not supported by code_watermark plugin")
