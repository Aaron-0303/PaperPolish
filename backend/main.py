import os
import re
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

app = FastAPI(title="PaperPolish API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_tokenizer = None
_model = None
_model_lock = Lock()
_infer_lock = Lock()

LATEX_PATTERNS = [
    r"\\begin\{[^{}]+\}.*?\\end\{[^{}]+\}",
    r"\$\$.*?\$\$",
    r"\\\[.*?\\\]",
    r"\\\(.*?\\\)",
    r"\$[^$\n]+\$",
    r"\\(?:cite|citep|citet|ref|cref|Cref|eqref|autoref|label)\*?(?:\[[^\]]*\])?\{[^{}]*\}",
]


class Term(BaseModel):
    english: str = ""
    chinese: str = ""
    type: Literal["locked", "preferred"] = "preferred"


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1)
    direction: Literal["en-zh", "zh-en"]
    terms: list[Term] = []
    original_english: str = ""
    style: str = "CVPR/IEEE concise academic style"


def torch_dtype():
    if MODEL_DTYPE == "float16":
        return torch.float16
    if MODEL_DTYPE == "float32":
        return torch.float32
    return torch.bfloat16


def ensure_model_files():
    if (MODEL_DIR / "config.json").exists():
        return
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=MODEL_ID,
        local_dir=str(MODEL_DIR),
        local_dir_use_symlinks=False,
    )


def load_model():
    global _tokenizer, _model
    if _model is not None:
        return
    with _model_lock:
        if _model is not None:
            return
        ensure_model_files()
        _tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR), trust_remote_code=True)
        _model = AutoModelForCausalLM.from_pretrained(
            str(MODEL_DIR),
            dtype=torch_dtype(),
            device_map="auto",
            trust_remote_code=True,
        )
        _model.eval()


def _placeholder(index: int) -> str:
    return f"PPPROTECT{index:04d}TOKEN"


def protect_text(text: str, terms: list[Term], direction: str):
    replacements: list[tuple[str, str]] = []

    def stash(value: str, restore: str | None = None):
        token = _placeholder(len(replacements))
        replacements.append((token, value if restore is None else restore))
        return token

    combined = "|".join(f"(?:{pattern})" for pattern in LATEX_PATTERNS)
    protected = re.sub(combined, lambda m: stash(m.group(0)), text, flags=re.DOTALL)

    locked = [t for t in terms if t.type == "locked"]
    locked.sort(key=lambda t: max(len(t.english), len(t.chinese)), reverse=True)

    for term in locked:
        english = term.english.strip()
        chinese = term.chinese.strip()
        if direction == "en-zh" and english:
            protected = re.sub(re.escape(english), lambda m: stash(m.group(0)), protected, flags=re.I)
        elif direction == "zh-en":
            if chinese and english:
                protected = protected.replace(chinese, stash(chinese, english))
            if english:
                protected = re.sub(re.escape(english), lambda m: stash(m.group(0), english), protected, flags=re.I)

    return protected, replacements


def restore_text(text: str, replacements: list[tuple[str, str]]) -> str:
    restored = text
    for token, value in replacements:
        if token not in restored:
            raise ValueError(f"模型未保留受保护占位符 {token}")
        restored = restored.replace(token, value)
    return restored


def terminology_prompt(terms: list[Term]) -> str:
    pairs = []
    for term in terms:
        if term.english.strip() and term.chinese.strip():
            pairs.append(f"{term.english.strip()} translates to {term.chinese.strip()}")
    if not pairs:
        return ""
    return "Reference the following translations:\n" + "\n".join(pairs) + "\n\n"


def build_prompt(req: TranslateRequest, protected: str) -> str:
    term_hint = terminology_prompt(req.terms)
    immutable = (
        "Strings shaped like PPPROTECT0000TOKEN are immutable delimiters. "
        "Retain every delimiter exactly, without omission, translation, escaping, duplication, or reordering.\n\n"
    )

    if req.direction == "en-zh":
        return (
            immutable
            + term_hint
            + "Translate the following text into Chinese. Note that you must ONLY output the translated result without any additional explanation:\n"
            + protected
        )

    background = req.original_english.strip()
    style = req.style.strip() or "concise academic English"
    return (
        immutable
        + term_hint
        + "[Background Information]\n"
        + (background or "This text is from a scientific paper.")
        + "\n\n"
        + "Please translate the following text into English, taking the provided background information into consideration. "
        + f"The translation style must strictly conform to [{style}]. "
        + "Only output the translated result without any additional explanation.\n\n"
        + "[Source Text]\n"
        + protected
    )


def generate(prompt: str) -> str:
    load_model()
    messages = [{"role": "user", "content": prompt}]
    inputs = _tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_tensors="pt",
        return_dict=True,
    ).to(_model.device)

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


@app.on_event("startup")
def startup():
    load_model()


@app.get("/api/health")
def health():
    gpu = None
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        gpu = {
            "name": torch.cuda.get_device_name(0),
            "allocated_mb": round(torch.cuda.memory_allocated(0) / 1024 / 1024, 1),
            "reserved_mb": round(torch.cuda.memory_reserved(0) / 1024 / 1024, 1),
            "total_mb": round(props.total_memory / 1024 / 1024, 1),
        }
    return {
        "status": "ok",
        "model_ready": _model is not None,
        "model": MODEL_ID,
        "model_dir": str(MODEL_DIR),
        "gpu": gpu,
    }


@app.post("/api/translate")
def translate(req: TranslateRequest):
    protected, replacements = protect_text(req.text.strip(), req.terms, req.direction)
    prompt = build_prompt(req, protected)
    try:
        result = restore_text(generate(prompt), replacements)
        return {"result": result}
    except torch.cuda.OutOfMemoryError as exc:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        raise HTTPException(status_code=503, detail="GPU 显存不足，无法完成本次翻译。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
