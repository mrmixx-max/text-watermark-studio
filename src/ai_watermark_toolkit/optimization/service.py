from __future__ import annotations

from typing import Dict, Any, List


class PromptOptimizationService:
    def variants(self, system: str) -> List[Dict[str, Any]]:
        base = system.strip()
        return [
            {
                'variant': 'direct',
                'system_prompt': base,
                'user_template': 'Rewrite this text in {style}:\n\n{text}'
            },
            {
                'variant': 'structured',
                'system_prompt': base + ' Return only the rewritten text.',
                'user_template': 'Rewrite with the following rules: {style}.\nText:\n{text}'
            },
        ]
