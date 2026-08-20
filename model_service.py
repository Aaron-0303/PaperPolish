import os
from pathlib import Path
from threading import Lock

import torch
from fastapi import FastAPI, HTTPException
from huggingface_hub import snapshot_download
from pydantic import BaseModel, Field
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = os.getenv("MODEL_ID", "tencent/Hy-MT2-7B")
MODEL_DIR = Path(os.getenv("MODEL_DIR", "/models/Hy-MT2-7B"))
DTYPE = os.getenv("MODEL_DTYPE", "bfloat16").lower()
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "4096"))

app = FastAPI(title="PaperPolish Hy-MT2 Service", version="0.1.0")

_tokenizer = None
_model = None
_load_lock = Lock()
_generate_lock = Lock()


class TranslateRequest(BaseModel):
    source_text: str = Field(min_length=1)
    target_lang: str = Field(min_length=1)
    background_text: str = ""


def _torch_dtype():
    if DTYPE == "float16":
        return torch.float16
    if DTYPE == "float32":
        return torch.float32
    return torch.bfloat16


def ensure_model_files():
    config_file = MODEL_DIR / "config.json"
    if config_file.exists():
        return

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=MODEL_ID,
        local_dir=str(MODEL_DIR),
        local_dir_use_symlinks=False,
        resume_download=True,
    )


def load_model():
    global _tokenizer, _model
    if _model is not None and _tokenizer is not None:
        return

    with _load_lock:
        if _model is not None and _tokenizer is not None:
            return

        ensure_model_files()
        _tokenizer = AutoTokenizer.from_pretrained(
            str(MODEL_DIR),
            trust_remote_code=True,
        )
        _model = AutoModelForCausalLM.from_pretrained(
            str(MODEL_DIR),
            dtype=_torch_dtype(),
            device_map="auto",
            trust_remote_code=True,
        )
        _model.eval()


def build_prompt(source_text: str, target_lang: str, background_text: str = "") -> str:
    if background_text.strip():
        return (
            "[Background Information]\n"
            f"{background_text.strip()}\n\n"
            f"Please translate the following text into {target_lang}, "
            "taking the provided background information into consideration.\n\n"
            "[Source Text]\n"
            f"{source_text.strip()}"
        )

    return (
        f"Please translate the following text into {target_lang}. "
        "Only output the translation and do not add explanations.\n\n"
        f"{source_text.strip()}"
    )


def generate_translation(source_text: str, target_lang: str, background_text: str = "") -> str:
    load_model()
    prompt = build_prompt(source_text, target_lang, background_text)
    messages = [{"role": "user", "content": prompt}]

    inputs = _tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_tensors="pt",
    ).to(_model.device)

    with _generate_lock, torch.inference_mode():
        output = _model.generate(
            inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=True,
            temperature=0.7,
            top_p=0.6,
            top_k=20,
            repetition_penalty=1.05,
            pad_token_id=_tokenizer.pad_token_id,
            eos_token_id=_tokenizer.eos_token_id,
        )

    generated = output[0, inputs.shape[-1] :]
    return _tokenizer.decode(generated, skip_special_tokens=True).strip()


@app.on_event("startup")
def startup_load_model():
    load_model()


@app.get("/health")
def health():
    loaded = _model is not None and _tokenizer is not None
    gpu = None
    if torch.cuda.is_available():
        gpu = {
            "name": torch.cuda.get_device_name(0),
            "allocated_mb": round(torch.cuda.memory_allocated(0) / 1024 / 1024, 1),
            "reserved_mb": round(torch.cuda.memory_reserved(0) / 1024 / 1024, 1),
            "total_mb": round(torch.cuda.get_device_properties(0).total_memory / 1024 / 1024, 1),
        }
    return {
        "status": "ok" if loaded else "loading",
        "loaded": loaded,
        "model_id": MODEL_ID,
        "model_dir": str(MODEL_DIR),
        "gpu": gpu,
    }


@app.post("/translate")
def translate(req: TranslateRequest):
    try:
        result = generate_translation(req.source_text, req.target_lang, req.background_text)
        return {"result": result}
    except torch.cuda.OutOfMemoryError as exc:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        raise HTTPException(status_code=503, detail="GPU 显存不足，无法完成本次翻译。") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
