import os
import re
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

MODEL_BASE_URL = os.getenv("MODEL_BASE_URL", "http://model:8000/v1").rstrip("/")
MODEL_NAME = os.getenv("MODEL_NAME", "/models/Hy-MT2-7B")
REQUEST_TIMEOUT = float(os.getenv("MODEL_TIMEOUT", "300"))

app = FastAPI(title="PaperPolish API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


async def vllm_chat(prompt: str) -> str:
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "top_p": 0.6,
        "top_k": 20,
        "repetition_penalty": 1.05,
        "max_tokens": 4096,
    }
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.post(f"{MODEL_BASE_URL}/chat/completions", json=payload)
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Hy-MT2 服务错误: {response.text[:500]}")
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


@app.get("/api/health")
async def health():
    model_ok = False
    detail = "offline"
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(f"{MODEL_BASE_URL}/models")
        model_ok = response.is_success
        detail = "ready" if model_ok else f"http-{response.status_code}"
    except httpx.HTTPError:
        pass
    return {"status": "ok", "model_ready": model_ok, "model": MODEL_NAME, "model_status": detail}


@app.post("/api/translate")
async def translate(req: TranslateRequest):
    protected, replacements = protect_text(req.text.strip(), req.terms, req.direction)
    prompt = build_prompt(req, protected)
    try:
        result = restore_text(await vllm_chat(prompt), replacements)
        return {"result": result}
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
