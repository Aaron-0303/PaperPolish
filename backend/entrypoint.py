import json
import os
from pathlib import Path
from threading import Lock
from typing import Literal

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


class RemoteTranslateRequest(BaseModel):
    text: str = Field(min_length=1)
    direction: Literal["en-zh", "zh-en"]
    api_key: str = Field(min_length=1)
    model: str = Field(min_length=1)
    mode: str = "paper"
    terms: list[core.Term] = []
    original_english: str = ""
    style: str = "CVPR/IEEE concise academic style"
    preferences: list[str] = []
    format_type: str = "LaTeX"
    background_text: str = ""


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


# Hy-MT2 already provides a terminology prompt format. Do not replace LaTeX or
# terminology with artificial placeholder tokens; send the source text as-is.
def protect_text_without_placeholders(text: str, terms, direction: str):
    return text, []


def restore_text_without_placeholders(text: str, replacements):
    return text.strip()


def no_placeholder_instruction(source: str) -> str:
    return ""


def official_terminology_lines(terms, direction: str) -> str:
    pairs = [(t.english.strip(), t.chinese.strip()) for t in terms if t.english.strip() and t.chinese.strip()]
    if not pairs:
        return ""
    if direction == "en-zh":
        return "参考下面的翻译：\n" + "\n".join(f"{en} 翻译成 {zh}" for en, zh in pairs) + "\n"
    return "Reference the following translations:\n" + "\n".join(f"{zh} translates to {en}" for en, zh in pairs) + "\n\n"


def remote_models_with_server_key(api_key: str):
    resolved_key = _server_api_key("generic") if api_key == SERVER_API_KEY_SENTINEL else api_key
    return _original_remote_models(resolved_key)


def remote_polish_with_provider(req):
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


def _remote_chat(model: str, api_key: str, prompt: str) -> str:
    provider = _provider_for_model(model)
    target_base = TENCENT_MAAS_API_ROOT if provider == "tencent" else core.REMOTE_API_BASE
    resolved_key = _server_api_key(provider) if api_key == SERVER_API_KEY_SENTINEL else api_key.strip()
    payload = {
        "model": model.strip(),
        "messages": [
            {"role": "system", "content": "You are a rigorous bilingual academic translation assistant. Return only the requested translated text."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": core.MAX_NEW_TOKENS,
        "temperature": 0.2,
        "stream": False,
    }
    try:
        with core.httpx.Client(timeout=120.0) as client:
            response = client.post(f"{target_base}/v1/chat/completions", headers=core.remote_headers(resolved_key), json=payload)
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=f"API 翻译失败: {response.text[:800]}")
        data = response.json()
        choices = data.get("choices") or []
        content = choices[0].get("message", {}).get("content", "") if choices else ""
        if not isinstance(content, str) or not content.strip():
            raise HTTPException(status_code=502, detail="API 返回为空或响应格式不正确。")
        return content.strip()
    except HTTPException:
        raise
    except core.httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="API 翻译请求超时。") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"远程 API 请求失败: {exc}") from exc


def remote_translate(req: RemoteTranslateRequest):
    try:
        translate_req = core.TranslateRequest(
            text=req.text,
            direction=req.direction,
            mode=req.mode,
            terms=req.terms,
            original_english=req.original_english,
            style=req.style,
            preferences=req.preferences,
            format_type=req.format_type,
            background_text=req.background_text,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"翻译参数不正确: {exc}") from exc

    prompt = core.build_prompt(translate_req, req.text.strip())
    return _remote_chat(req.model, req.api_key, prompt)


# Replace the old placeholder layer globally. Existing stored terminology may
# still contain a legacy type field, but the backend intentionally ignores it.
core.protect_text = protect_text_without_placeholders
core.restore_text = restore_text_without_placeholders
core.placeholder_instruction = no_placeholder_instruction
core.terminology_lines = official_terminology_lines
core.generate = _original_generate
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


@app.post("/api/remote/translate")
def api_remote_translate(req: RemoteTranslateRequest):
    return {"result": remote_translate(req), "model": req.model, "engine": "remote", "direction": req.direction}
