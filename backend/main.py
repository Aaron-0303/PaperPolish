import gc
import os
import re
import time
from pathlib import Path
from threading import Lock
from typing import Literal

import httpx
import torch
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from huggingface_hub import snapshot_download
from pydantic import BaseModel, Field
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = os.getenv("MODEL_ID", "tencent/Hy-MT2-7B")
MODEL_DIR = Path(os.getenv("MODEL_DIR", "/models/Hy-MT2-7B"))
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "4096"))
MODEL_DTYPE = os.getenv("MODEL_DTYPE", "bfloat16").lower()
HOST_GPU_INDEX = os.getenv("HOST_GPU_INDEX", os.getenv("NVIDIA_VISIBLE_DEVICES", "0"))
REMOTE_API_BASE = os.getenv("REMOTE_API_BASE", "https://api.gpt.ge").rstrip("/")

_tokenizer = None
_model = None
_model_lock = Lock()
_infer_lock = Lock()
_model_state = "unloaded"
_model_message = "本地权重已就绪，点击后直接加载到 GPU"
_last_error = ""
_last_load_seconds = None

LATEX_PATTERNS = [
    r"\\begin\{[^{}]+\}.*?\\end\{[^{}]+\}", r"\$\$.*?\$\$", r"\\\[.*?\\\]",
    r"\\\(.*?\\\)", r"\$[^$\n]+\$",
    r"\\(?:cite|citep|citet|ref|cref|Cref|eqref|autoref|label)\*?(?:\[[^\]]*\])?\{[^{}]*\}",
]
PLACEHOLDER_PATTERN = re.compile(r"PPPROTECT\d{4}TOKEN")

TranslationMode = Literal[
    "paper", "default", "terminology", "style", "personalization",
    "delimiters", "structured-data-1", "structured-data-2",
]


class Term(BaseModel):
    english: str = ""
    chinese: str = ""
    type: Literal["locked", "preferred"] = "preferred"


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1)
    direction: Literal["en-zh", "zh-en"]
    mode: TranslationMode = "paper"
    terms: list[Term] = []
    original_english: str = ""
    style: str = "CVPR/IEEE concise academic style"
    preferences: list[str] = []
    format_type: str = "LaTeX"
    background_text: str = ""


class RemoteModelsRequest(BaseModel):
    api_key: str = Field(min_length=1)


class RemotePolishRequest(BaseModel):
    text: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    model: str = Field(min_length=1)
    original_english: str = ""
    style: str = "CVPR/IEEE concise academic style"
    terms: list[Term] = []


def torch_dtype():
    return {"float16": torch.float16, "float32": torch.float32}.get(MODEL_DTYPE, torch.bfloat16)


def model_files_ready():
    return (MODEL_DIR / "config.json").exists()


def ensure_model_files():
    if model_files_ready():
        return
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=MODEL_ID, local_dir=str(MODEL_DIR), local_dir_use_symlinks=False)


def model_device():
    if _model is None:
        return "none"
    try:
        return str(next(_model.parameters()).device)
    except Exception:
        return "unknown"


def model_on_gpu():
    return model_device().startswith("cuda")


def load_model_gpu():
    global _tokenizer, _model, _model_state, _model_message, _last_error, _last_load_seconds
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA 不可用，无法加载模型到 GPU。")

    with _model_lock:
        if _model is not None and model_on_gpu():
            _model_state = "gpu_ready"
            _model_message = "模型已在显存中"
            return

        _model_state = "loading_gpu"
        _model_message = "正在加载模型到 GPU"
        _last_error = ""
        started = time.perf_counter()
        try:
            ensure_model_files()
            if _tokenizer is None:
                _tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR), trust_remote_code=True)

            if _model is None:
                _model = AutoModelForCausalLM.from_pretrained(
                    str(MODEL_DIR),
                    dtype=torch_dtype(),
                    trust_remote_code=True,
                    low_cpu_mem_usage=True,
                )

            _model.to("cuda")
            _model.eval()
            _last_load_seconds = round(time.perf_counter() - started, 2)
            _model_state = "gpu_ready"
            _model_message = "模型已在显存中，可以开始翻译"
        except Exception as exc:
            if _model is not None and not model_on_gpu():
                _model_state = "cpu_ready"
                _model_message = "模型位于 CPU 内存，加载到 GPU 失败"
            else:
                _model_state = "error"
                _model_message = "模型加载到 GPU 失败"
            _last_error = str(exc)
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            raise


def offload_model_cpu():
    global _model_state, _model_message, _last_error
    if _model is None or _tokenizer is None:
        raise RuntimeError("模型尚未加载。")

    with _model_lock:
        if not model_on_gpu():
            _model_state = "cpu_ready"
            _model_message = "模型已在 CPU 内存中"
            return
        _model_state = "offloading_cpu"
        _model_message = "正在将模型从显存卸载到内存"
        _last_error = ""
        try:
            with _infer_lock:
                _model.to("cpu")
                _model.eval()
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            _model_state = "cpu_ready"
            _model_message = "模型已卸载到 CPU 内存，GPU 显存已释放"
        except Exception as exc:
            _model_state = "error"
            _model_message = "模型卸载到内存失败"
            _last_error = str(exc)
            raise


def gpu_status():
    if not torch.cuda.is_available():
        return {
            "available": False, "name": None, "allocated_mb": 0, "reserved_mb": 0,
            "used_mb": 0, "free_mb": 0, "total_mb": 0, "host_device": HOST_GPU_INDEX,
        }
    device = torch.cuda.current_device()
    free_bytes, total_bytes = torch.cuda.mem_get_info(device)
    total_mb, free_mb = total_bytes / 1048576, free_bytes / 1048576
    return {
        "available": True,
        "name": torch.cuda.get_device_name(device),
        "device": device,
        "host_device": HOST_GPU_INDEX,
        "allocated_mb": round(torch.cuda.memory_allocated(device) / 1048576, 1),
        "reserved_mb": round(torch.cuda.memory_reserved(device) / 1048576, 1),
        "used_mb": round(total_mb - free_mb, 1),
        "free_mb": round(free_mb, 1),
        "total_mb": round(total_mb, 1),
    }


def model_status():
    return {
        "status": _model_state,
        "message": _model_message,
        "model_loaded": _model is not None,
        "model_ready": _model is not None and model_on_gpu() and _model_state == "gpu_ready",
        "device": model_device(),
        "model": MODEL_ID,
        "model_dir": str(MODEL_DIR),
        "downloaded": model_files_ready(),
        "dtype": MODEL_DTYPE,
        "last_load_seconds": _last_load_seconds,
        "last_error": _last_error,
        "gpu": gpu_status(),
    }


def _placeholder(index: int) -> str:
    return f"PPPROTECT{index:04d}TOKEN"


def protect_text(text: str, terms: list[Term], direction: str):
    replacements = []

    def stash(value, restore=None):
        token = _placeholder(len(replacements))
        replacements.append((token, value if restore is None else restore))
        return token

    combined = "|".join(f"(?:{p})" for p in LATEX_PATTERNS)
    protected = re.sub(combined, lambda m: stash(m.group(0)), text, flags=re.DOTALL)
    locked = sorted([t for t in terms if t.type == "locked"], key=lambda t: max(len(t.english), len(t.chinese)), reverse=True)
    for term in locked:
        english, chinese = term.english.strip(), term.chinese.strip()
        if direction == "en-zh" and english:
            protected = re.sub(re.escape(english), lambda m: stash(m.group(0)), protected, flags=re.I)
        elif direction == "zh-en":
            if chinese and english:
                protected = protected.replace(chinese, stash(chinese, english))
            if english:
                protected = re.sub(re.escape(english), lambda m: stash(m.group(0), english), protected, flags=re.I)
    return protected, replacements


def restore_text(text, replacements):
    for token, value in replacements:
        if token not in text:
            raise ValueError(f"模型未保留受保护占位符 {token}")
        text = text.replace(token, value)

    # Any token left after restoring the real placeholders was hallucinated by the model.
    # Never expose internal PaperPolish placeholders to the user.
    text = PLACEHOLDER_PATTERN.sub("", text)
    return text.strip()


def placeholder_instruction(source: str) -> str:
    if not PLACEHOLDER_PATTERN.search(source):
        return ""
    return (
        "Preserve every placeholder token already present in the source text exactly once and in the same logical position. "
        "Do not alter, translate, duplicate, remove, or invent placeholder tokens.\n\n"
    )


def terminology_lines(terms: list[Term], direction: str) -> str:
    pairs = [(t.english.strip(), t.chinese.strip()) for t in terms if t.english.strip() and t.chinese.strip()]
    if not pairs:
        return ""
    if direction == "en-zh":
        return "参考下面的术语翻译：\n" + "\n".join(f"{en} 翻译为 {zh}" for en, zh in pairs) + "\n\n"
    return "Reference the following terminology translations:\n" + "\n".join(f"{zh} translates to {en}" for en, zh in pairs) + "\n\n"


def build_prompt(req: TranslateRequest, protected: str) -> str:
    target_lang = "Chinese" if req.direction == "en-zh" else "English"
    source = protected
    placeholder_rule = placeholder_instruction(source)

    if req.mode == "default":
        return placeholder_rule + f"Translate the following text into {target_lang}. Note that you should only output the translated result without any additional explanation:\n\n{source}"

    if req.mode == "terminology":
        return placeholder_rule + terminology_lines(req.terms, req.direction) + f"Translate the following text into {target_lang}. Note that you must ONLY output the translated result without any additional explanation:\n\n{source}"

    if req.mode == "style":
        return placeholder_rule + f"Please translate the following text into {target_lang}. Note that the translation style must strictly conform to [{req.style.strip() or 'academic writing'}]:\n\n{source}"

    if req.mode == "personalization":
        prefs = req.preferences or ["Preserve technical meaning", "Use concise academic wording"]
        tasks = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(prefs))
        return placeholder_rule + f"[Source Text]\n{source}\n\n[Translation Tasks]\n{tasks}\n{len(prefs) + 1}. Translate the [Source Text] into {target_lang}."

    if req.mode == "delimiters":
        return placeholder_rule + f"Please accurately translate the following text into {target_lang}.\nYou must retain the exact same number of delimiters in the translation. Strictly do not omit, escape, or translate these symbols, and pay close attention to their placement.\n\n{source}"

    if req.mode == "structured-data-1":
        ft = req.format_type.strip() or "LaTeX"
        return placeholder_rule + f"### Task\nTranslate the user-facing text within the following {ft} data into {target_lang}.\n\n### Strict Rules\n1. Structure Preservation: You MUST preserve the original {ft} data structure, nesting, hierarchy, and indentation exactly as they are.\n2. Selective Translation: Translate ONLY the visible, user-facing text content/values.\n3. Strict Non-Translation: NEVER translate or alter code tags, keys, properties, object names, or variable placeholders. Leave them exactly in their original English/code form.\n\n### Source Data\n{source}"

    background = (req.background_text or req.original_english).strip() or "This text is from a scientific paper."
    if req.mode == "structured-data-2":
        return placeholder_rule + f"[Background Information]\n{background}\n\nPlease translate the following text into {target_lang}, taking the provided background information into consideration.\n\n[Source Text]\n{source}"

    term_hint = terminology_lines(req.terms, req.direction)
    style = req.style.strip() or "CVPR/IEEE concise academic style"
    return placeholder_rule + term_hint + f"[Background Information]\n{background}\n\nPlease translate the following text into {target_lang}, taking the provided background information into consideration. Note that the translation style must strictly conform to [{style}]. Only output the translated result without any additional explanation.\n\n[Source Text]\n{source}"


def generate(prompt: str) -> str:
    if _model is None or _tokenizer is None:
        raise RuntimeError("模型尚未加载，请先在模型管理中加载模型。")
    if not model_on_gpu() or _model_state != "gpu_ready":
        raise RuntimeError("模型当前位于 CPU 内存，请先在模型管理中加载到 GPU。")
    device = model_device()
    inputs = _tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}],
        add_generation_prompt=True,
        return_tensors="pt",
        return_dict=True,
    ).to(device)
    with _infer_lock, torch.inference_mode():
        output = _model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=True,
            temperature=0.7,
            top_p=0.6,
            top_k=20,
            repetition_penalty=1.05,
        )
    generated = output[0, inputs["input_ids"].shape[-1]:]
    return _tokenizer.decode(generated, skip_special_tokens=True).strip()


def remote_headers(api_key: str):
    return {"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"}


def build_remote_polish_prompt(req: RemotePolishRequest, protected: str) -> str:
    original = req.original_english.strip()
    style = req.style.strip() or "CVPR/IEEE concise academic style"
    preferred = [(t.chinese.strip(), t.english.strip()) for t in req.terms if t.chinese.strip() and t.english.strip()]
    term_text = "\n".join(f"- {zh} -> {en}" for zh, en in preferred) or "- None"
    original_block = original if original else "No original English paragraph was provided."
    placeholder_rule = placeholder_instruction(protected)
    return f"""You are an expert academic English editor for computer vision and robotics papers.

Task: Rewrite the edited Chinese paragraph into polished academic English.

Requirements:
1. Preserve the author's intended technical meaning exactly.
2. Use {style}.
3. Be concise, technically precise, and natural. Avoid inflated claims and unnecessary adjectives.
4. Use the original English only as semantic and terminology context; do not blindly copy mistakes from it.
5. Follow the terminology mappings below when applicable.
6. Output only the final English paragraph. Do not add explanations, headings, quotes, or Markdown fences.

{placeholder_rule}Terminology:
{term_text}

Original English context:
{original_block}

Edited Chinese:
{protected}
"""


def remote_models(api_key: str):
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{REMOTE_API_BASE}/v1/models", headers=remote_headers(api_key))
        if response.status_code >= 400:
            detail = response.text[:500]
            raise HTTPException(status_code=response.status_code, detail=f"API 模型列表请求失败: {detail}")
        data = response.json()
        return sorted({item.get("id") for item in data.get("data", []) if isinstance(item, dict) and item.get("id")})
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="API 模型列表请求超时。") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"无法连接远程 API: {exc}") from exc


def remote_polish(req: RemotePolishRequest):
    protected, replacements = protect_text(req.text.strip(), req.terms, "zh-en")
    payload = {
        "model": req.model.strip(),
        "messages": [
            {"role": "system", "content": "You are a rigorous academic English writing assistant. Return only the requested final text."},
            {"role": "user", "content": build_remote_polish_prompt(req, protected)},
        ],
        "max_tokens": MAX_NEW_TOKENS,
        "temperature": 0.2,
        "stream": False,
    }
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(f"{REMOTE_API_BASE}/v1/chat/completions", headers=remote_headers(req.api_key), json=payload)
        if response.status_code >= 400:
            detail = response.text[:800]
            raise HTTPException(status_code=response.status_code, detail=f"API 生成失败: {detail}")
        data = response.json()
        choices = data.get("choices") or []
        content = choices[0].get("message", {}).get("content", "") if choices else ""
        if not isinstance(content, str) or not content.strip():
            raise HTTPException(status_code=502, detail="API 返回为空或响应格式不正确。")
        return restore_text(content.strip(), replacements)
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="API 生成请求超时。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"远程 API 请求失败: {exc}") from exc


app = FastAPI(title="PaperPolish API", version="0.7.2")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"api_status": "ok", **model_status()}


@app.get("/api/model/status")
def get_model_status():
    return model_status()


@app.post("/api/model/load-gpu")
def api_load_model_gpu():
    try:
        load_model_gpu()
        return {"ok": True, **model_status()}
    except torch.cuda.OutOfMemoryError as exc:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        raise HTTPException(status_code=503, detail="GPU 显存不足，Hy-MT2-7B 加载失败。") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"模型加载到 GPU 失败: {exc}") from exc


@app.post("/api/model/offload-cpu")
def api_offload_model_cpu():
    try:
        offload_model_cpu()
        return {"ok": True, **model_status()}
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"模型卸载到内存失败: {exc}") from exc


@app.post("/api/model/load")
def api_load_model_compat():
    return api_load_model_gpu()


@app.post("/api/model/unload")
def api_unload_model_compat():
    return api_offload_model_cpu()


@app.post("/api/remote/models")
def api_remote_models(req: RemoteModelsRequest):
    return {"models": remote_models(req.api_key), "base_url": REMOTE_API_BASE}


@app.post("/api/remote/polish")
def api_remote_polish(req: RemotePolishRequest):
    return {"result": remote_polish(req), "model": req.model, "engine": "remote"}


@app.post("/api/translate")
def translate(req: TranslateRequest):
    if _model is None:
        raise HTTPException(status_code=409, detail="Hy-MT2-7B 尚未加载，请先在模型管理中加载到 GPU。")
    if not model_on_gpu() or _model_state != "gpu_ready":
        raise HTTPException(status_code=409, detail="Hy-MT2-7B 当前位于 CPU 内存，请先在模型管理中加载到 GPU。")
    protected, replacements = protect_text(req.text.strip(), req.terms, req.direction)
    try:
        return {"result": restore_text(generate(build_prompt(req, protected)), replacements), "mode": req.mode}
    except torch.cuda.OutOfMemoryError as exc:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        raise HTTPException(status_code=503, detail="GPU 显存不足，无法完成本次翻译。") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
