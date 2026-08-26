import json
import os
import re
from pathlib import Path
from threading import Lock

from fastapi import HTTPException
from pydantic import BaseModel, Field

import main as core

TENCENT_MAAS_API_ROOT = os.getenv("TENCENT_MAAS_API_ROOT", "https://tokenhub.tencentmaas.com").rstrip("/")
PROVIDER_SECRETS_FILE = Path(os.getenv("PROVIDER_SECRETS_FILE", "/data/provider-secrets.json"))
SERVER_API_KEY_SENTINEL = "__SERVER__"
_REMOTE_ROUTE_LOCK = Lock()
_SECRETS_LOCK = Lock()
_original_remote_polish = core.remote_polish
_original_remote_models = core.remote_models
_original_generate = core.generate


class ProviderKeyRequest(BaseModel):
    api_key: str = Field(min_length=1)


def _uses_tencent_maas(model: str) -> bool:
    return model.strip().lower().startswith("hy-mt2")


def _provider_for_model(model: str) -> str:
    return "tencent" if _uses_tencent_maas(model) else "generic"


def _read_provider_keys() -> dict[str, str]:
    with _SECRETS_LOCK:
        if not PROVIDER_SECRETS_FILE.exists():
            return {}
        try:
            data = json.loads(PROVIDER_SECRETS_FILE.read_text(encoding="utf-8"))
            return {k: v for k, v in data.items() if k in {"generic", "tencent"} and isinstance(v, str)}
        except Exception:
            return {}


def _write_provider_keys(data: dict[str, str]):
    with _SECRETS_LOCK:
        PROVIDER_SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = PROVIDER_SECRETS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(PROVIDER_SECRETS_FILE)
        os.chmod(PROVIDER_SECRETS_FILE, 0o600)


def _server_api_key(provider: str) -> str:
    key = _read_provider_keys().get(provider, "").strip()
    if not key:
        label = "腾讯云 Hy-MT2 Pro" if provider == "tencent" else "通用 OpenAI API"
        raise HTTPException(status_code=409, detail=f"{label} 尚未在服务器保存 API Key。")
    return key


def _placeholder_tokens(text: str) -> list[str]:
    # Preserve source order while removing duplicates.
    return list(dict.fromkeys(re.findall(r"PPPROTECT\d{4}TOKEN", text)))


def generate_with_placeholder_retry(prompt: str) -> str:
    """Retry once with a strict instruction if Hy-MT2 drops protected tokens."""
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


def remote_models_with_server_key(api_key: str):
    resolved_key = _server_api_key("generic") if api_key == SERVER_API_KEY_SENTINEL else api_key
    return _original_remote_models(resolved_key)


def remote_polish_with_provider(req):
    """Use a different server-stored API key for each remote provider."""
    provider = _provider_for_model(req.model)
    target_base = TENCENT_MAAS_API_ROOT if provider == "tencent" else core.REMOTE_API_BASE
    if req.api_key == SERVER_API_KEY_SENTINEL:
        req.api_key = _server_api_key(provider)

    with _REMOTE_ROUTE_LOCK:
        previous_base = core.REMOTE_API_BASE
        core.REMOTE_API_BASE = target_base
        try:
            return _original_remote_polish(req)
        finally:
            core.REMOTE_API_BASE = previous_base


core.generate = generate_with_placeholder_retry
core.remote_models = remote_models_with_server_key
core.remote_polish = remote_polish_with_provider
app = core.app


@app.get("/api/provider-keys/status")
def provider_key_status():
    keys = _read_provider_keys()
    return {
        "generic": {"configured": bool(keys.get("generic", "").strip())},
        "tencent": {"configured": bool(keys.get("tencent", "").strip())},
    }


@app.post("/api/provider-keys/{provider}")
def save_provider_key(provider: str, req: ProviderKeyRequest):
    if provider not in {"generic", "tencent"}:
        raise HTTPException(status_code=404, detail="未知 API 提供商。")
    keys = _read_provider_keys()
    keys[provider] = req.api_key.strip()
    _write_provider_keys(keys)
    return {"ok": True, "provider": provider, "configured": True}


@app.delete("/api/provider-keys/{provider}")
def delete_provider_key(provider: str):
    if provider not in {"generic", "tencent"}:
        raise HTTPException(status_code=404, detail="未知 API 提供商。")
    keys = _read_provider_keys()
    keys.pop(provider, None)
    _write_provider_keys(keys)
    return {"ok": True, "provider": provider, "configured": False}
