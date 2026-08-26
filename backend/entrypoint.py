import os
import re
from threading import Lock

import main as core

TENCENT_MAAS_API_ROOT = os.getenv("TENCENT_MAAS_API_ROOT", "https://tokenhub.tencentmaas.com").rstrip("/")
_REMOTE_ROUTE_LOCK = Lock()
_original_remote_polish = core.remote_polish
_original_generate = core.generate


def _uses_tencent_maas(model: str) -> bool:
    return model.strip().lower().startswith("hy-mt2")


def _placeholder_tokens(text: str) -> list[str]:
    # Preserve source order while removing duplicates.
    return list(dict.fromkeys(re.findall(r"PPPROTECT\d{4}TOKEN", text)))


def generate_with_placeholder_retry(prompt: str) -> str:
    """Retry once with a strict instruction if Hy-MT2 drops protected tokens.

    PaperPolish protects LaTeX and Locked terminology with PPPROTECT tokens.
    Hy-MT2 occasionally omits one during zh-en generation; the normal restore
    step then fails. Detect that before restore and make one deterministic-style
    corrective generation request with the exact required token list.
    """
    result = _original_generate(prompt)
    expected = _placeholder_tokens(prompt)
    if not expected:
        return result

    missing = [token for token in expected if token not in result]
    if not missing:
        return result

    token_list = "\n".join(f"- {token}" for token in expected)
    strict_prompt = f"""CRITICAL FORMAT REQUIREMENT
The source text contains protected placeholder tokens. They are immutable text markers, not words to translate.
You MUST output every token listed below exactly once, character-for-character, and keep each token in the same logical position as in the source sentence.
Do not translate, reformat, split, merge, omit, or invent any placeholder token.
If a placeholder stands for a technical term or LaTeX fragment, leave the placeholder itself untouched; PaperPolish will restore the original value after generation.

Required placeholder tokens:
{token_list}

Return only the final translated text, with no explanation.

ORIGINAL TRANSLATION REQUEST:
{prompt}
"""
    return _original_generate(strict_prompt)


def remote_polish_with_provider(req):
    """Route Hy-MT2 cloud model names to Tencent MaaS; keep other models on the existing API host."""
    target_base = TENCENT_MAAS_API_ROOT if _uses_tencent_maas(req.model) else core.REMOTE_API_BASE
    with _REMOTE_ROUTE_LOCK:
        previous_base = core.REMOTE_API_BASE
        core.REMOTE_API_BASE = target_base
        try:
            return _original_remote_polish(req)
        finally:
            core.REMOTE_API_BASE = previous_base


core.generate = generate_with_placeholder_retry
core.remote_polish = remote_polish_with_provider
app = core.app
