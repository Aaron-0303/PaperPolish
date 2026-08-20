import gc
import os
import re
import time
from pathlib import Path
from threading import Lock
from typing import Literal

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

app = FastAPI(title="PaperPolish API", version="0.5.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

_tokenizer = None
_model = None
_model_lock = Lock()
_infer_lock = Lock()
_model_state = "unloaded"
_last_error = ""
_last_load_seconds = None

LATEX_PATTERNS = [
    r"\\begin\{[^{}]+\}.*?\\end\{[^{}]+\}", r"\$\$.*?\$\$", r"\\\[.*?\\\]",
    r"\\\(.*?\\\)", r"\$[^$\n]+\$",
    r"\\(?:cite|citep|citet|ref|cref|Cref|eqref|autoref|label)\*?(?:\[[^\]]*\])?\{[^{}]*\}",
]

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


def torch_dtype():
    return {"float16": torch.float16, "float32": torch.float32}.get(MODEL_DTYPE, torch.bfloat16)

def model_files_ready():
    return (MODEL_DIR / "config.json").exists()

def ensure_model_files():
    if model_files_ready(): return
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=MODEL_ID, local_dir=str(MODEL_DIR), local_dir_use_symlinks=False)

def load_model():
    global _tokenizer, _model, _model_state, _last_error, _last_load_seconds
    if _model is not None: return
    with _model_lock:
        if _model is not None: return
        if _model_state == "loading": raise RuntimeError("模型正在加载，请稍后刷新状态。")
        _model_state, _last_error = "loading", ""
        started = time.perf_counter()
        try:
            ensure_model_files()
            _tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR), trust_remote_code=True)
            _model = AutoModelForCausalLM.from_pretrained(str(MODEL_DIR), dtype=torch_dtype(), device_map="auto", trust_remote_code=True)
            _model.eval()
            _last_load_seconds = round(time.perf_counter() - started, 2)
            _model_state = "loaded"
        except Exception as exc:
            _tokenizer = _model = None
            _model_state, _last_error = "error", str(exc)
            if torch.cuda.is_available(): torch.cuda.empty_cache()
            raise

def unload_model():
    global _tokenizer, _model, _model_state, _last_error
    with _model_lock:
        if _model_state == "loading": raise RuntimeError("模型正在加载，当前不能卸载。")
        with _infer_lock:
            _model = _tokenizer = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            _model_state, _last_error = "unloaded", ""

def gpu_status():
    if not torch.cuda.is_available():
        return {"available": False, "name": None, "allocated_mb": 0, "reserved_mb": 0, "used_mb": 0, "free_mb": 0, "total_mb": 0, "host_device": HOST_GPU_INDEX}
    device = torch.cuda.current_device()
    free_bytes, total_bytes = torch.cuda.mem_get_info(device)
    total_mb, free_mb = total_bytes / 1048576, free_bytes / 1048576
    return {
        "available": True,
        "name": torch.cuda.get_device_name(device),
        "device": device,
        "host_device": HOST_GPU_INDEX,
        "allocated_mb": round(torch.cuda.memory_allocated(device)/1048576,1),
        "reserved_mb": round(torch.cuda.memory_reserved(device)/1048576,1),
        "used_mb": round(total_mb-free_mb,1),
        "free_mb": round(free_mb,1),
        "total_mb": round(total_mb,1),
    }

def model_status():
    return {"status": _model_state, "model_ready": _model is not None, "model": MODEL_ID, "model_dir": str(MODEL_DIR), "downloaded": model_files_ready(), "dtype": MODEL_DTYPE, "last_load_seconds": _last_load_seconds, "last_error": _last_error, "gpu": gpu_status()}

def _placeholder(index:int)->str: return f"PPPROTECT{index:04d}TOKEN"

def protect_text(text:str, terms:list[Term], direction:str):
    replacements=[]
    def stash(value, restore=None):
        token=_placeholder(len(replacements)); replacements.append((token, value if restore is None else restore)); return token
    combined="|".join(f"(?:{p})" for p in LATEX_PATTERNS)
    protected=re.sub(combined, lambda m: stash(m.group(0)), text, flags=re.DOTALL)
    locked=sorted([t for t in terms if t.type=="locked"], key=lambda t:max(len(t.english),len(t.chinese)), reverse=True)
    for term in locked:
        english, chinese=term.english.strip(), term.chinese.strip()
        if direction=="en-zh" and english:
            protected=re.sub(re.escape(english), lambda m:stash(m.group(0)), protected, flags=re.I)
        elif direction=="zh-en":
            if chinese and english: protected=protected.replace(chinese, stash(chinese, english))
            if english: protected=re.sub(re.escape(english), lambda m:stash(m.group(0), english), protected, flags=re.I)
    return protected,replacements

def restore_text(text,replacements):
    for token,value in replacements:
        if token not in text: raise ValueError(f"模型未保留受保护占位符 {token}")
        text=text.replace(token,value)
    return text

def terminology_lines(terms:list[Term], chinese_prompt:bool=False)->str:
    pairs=[(t.english.strip(),t.chinese.strip()) for t in terms if t.english.strip() and t.chinese.strip()]
    if not pairs: return ""
    if chinese_prompt:
        return "参考下面的翻译：\n" + "\n".join(f"{en} 翻译成 {zh}" for en,zh in pairs) + "\n\n"
    return "Reference the following translations:\n" + "\n".join(f"{zh} translates to {en}" for en,zh in pairs) + "\n\n"

def build_prompt(req:TranslateRequest, protected:str)->str:
    target_lang = "Chinese" if req.direction=="en-zh" else "English"
    source = protected

    if req.mode == "default":
        return f"Translate the following text into {target_lang}. Note that you should only output the translated result without any additional explanation:\n\n{source}"

    if req.mode == "terminology":
        return terminology_lines(req.terms, chinese_prompt=False) + f"Translate the following text into {target_lang}. Note that you must ONLY output the translated result without any additional explanation:\n\n{source}"

    if req.mode == "style":
        return f"Please translate the following text into {target_lang}. Note that the translation style must strictly conform to [{req.style.strip() or 'academic writing'}]:\n\n{source}"

    if req.mode == "personalization":
        prefs = req.preferences or ["Preserve technical meaning", "Use concise academic wording"]
        tasks = "\n".join(f"{i+1}. {p}" for i,p in enumerate(prefs))
        return f"[Source Text]\n{source}\n\n[Translation Tasks]\n{tasks}\n{len(prefs)+1}. Translate the [Source Text] into {target_lang}."

    if req.mode == "delimiters":
        return f"Please accurately translate the following text into {target_lang}.\nYou must retain the exact same number of delimiters in the translation. Strictly do not omit, escape, or translate these symbols, and pay close attention to their placement.\n\n{source}"

    if req.mode == "structured-data-1":
        ft=req.format_type.strip() or "LaTeX"
        return f"### Task\nTranslate the user-facing text within the following {ft} data into {target_lang}.\n\n### Strict Rules\n1. Structure Preservation: You MUST preserve the original {ft} data structure, nesting, hierarchy, and indentation exactly as they are.\n2. Selective Translation: Translate ONLY the visible, user-facing text content/values.\n3. Strict Non-Translation: NEVER translate or alter code tags, keys, properties, object names, or variable placeholders. Leave them exactly in their original English/code form.\n\n### Source Data\n{source}"

    background=(req.background_text or req.original_english).strip() or "This text is from a scientific paper."
    if req.mode == "structured-data-2":
        return f"[Background Information]\n{background}\n\nPlease translate the following text into {target_lang}, taking the provided background information into consideration.\n\n[Source Text]\n{source}"

    term_hint=terminology_lines(req.terms, chinese_prompt=False)
    style=req.style.strip() or "CVPR/IEEE concise academic style"
    delimiter_rule=("Strings shaped like PPPROTECT0000TOKEN are immutable delimiters. You must retain the exact same number of delimiters in the translation. Strictly do not omit, escape, translate, duplicate, or reorder them.\n\n")
    return delimiter_rule + term_hint + f"[Background Information]\n{background}\n\nPlease translate the following text into {target_lang}, taking the provided background information into consideration. Note that the translation style must strictly conform to [{style}]. Only output the translated result without any additional explanation.\n\n[Source Text]\n{source}"

def generate(prompt:str)->str:
    if _model is None or _tokenizer is None: raise RuntimeError("模型尚未加载，请先在模型管理中点击“加载模型”。")
    inputs=_tokenizer.apply_chat_template([{"role":"user","content":prompt}], add_generation_prompt=True, return_tensors="pt", return_dict=True).to(_model.device)
    with _infer_lock, torch.inference_mode():
        output=_model.generate(**inputs,max_new_tokens=MAX_NEW_TOKENS,do_sample=True,temperature=0.7,top_p=0.6,top_k=20,repetition_penalty=1.05)
    generated=output[0,inputs["input_ids"].shape[-1]:]
    return _tokenizer.decode(generated,skip_special_tokens=True).strip()

@app.get("/api/health")
def health(): return {"status":"ok",**model_status()}
@app.get("/api/model/status")
def get_model_status(): return model_status()
@app.post("/api/model/load")
def api_load_model():
    try: load_model(); return {"ok":True,**model_status()}
    except torch.cuda.OutOfMemoryError as exc:
        if torch.cuda.is_available(): torch.cuda.empty_cache()
        raise HTTPException(status_code=503,detail="GPU 显存不足，Hy-MT2-7B 加载失败。") from exc
    except Exception as exc: raise HTTPException(status_code=500,detail=f"模型加载失败: {exc}") from exc
@app.post("/api/model/unload")
def api_unload_model():
    try: unload_model(); return {"ok":True,**model_status()}
    except RuntimeError as exc: raise HTTPException(status_code=409,detail=str(exc)) from exc
@app.post("/api/translate")
def translate(req:TranslateRequest):
    if _model is None: raise HTTPException(status_code=409,detail="Hy-MT2-7B 尚未加载，请先在模型管理中加载模型。")
    protected,replacements=protect_text(req.text.strip(),req.terms,req.direction)
    try: return {"result":restore_text(generate(build_prompt(req,protected)),replacements),"mode":req.mode}
    except torch.cuda.OutOfMemoryError as exc:
        if torch.cuda.is_available(): torch.cuda.empty_cache()
        raise HTTPException(status_code=503,detail="GPU 显存不足，无法完成本次翻译。") from exc
    except RuntimeError as exc: raise HTTPException(status_code=409,detail=str(exc)) from exc
    except ValueError as exc: raise HTTPException(status_code=502,detail=str(exc)) from exc
