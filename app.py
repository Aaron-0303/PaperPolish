import os
import re
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)

# Protect common LaTeX constructs from model-side mutation. Longer/more specific
# patterns are intentionally matched before simple commands.
LATEX_PATTERNS = [
    r"\\begin\{[^{}]+\}.*?\\end\{[^{}]+\}",
    r"\$\$.*?\$\$",
    r"\\\[.*?\\\]",
    r"\\\(.*?\\\)",
    r"\$[^$\n]+\$",
    r"\\(?:cite|citep|citet|ref|cref|Cref|eqref|autoref|label)\*?(?:\[[^\]]*\])?\{[^{}]*\}",
]


def llm_config():
    return {
        "base_url": os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        "api_key": os.getenv("LLM_API_KEY", ""),
        "model": os.getenv("LLM_MODEL", "gpt-5.6"),
    }


def build_term_rules(terms):
    if not terms:
        return "No terminology rules are provided."

    lines = []
    for item in terms:
        english = (item.get("english") or "").strip()
        chinese = (item.get("chinese") or "").strip()
        rule_type = (item.get("type") or "preferred").strip()
        if not english and not chinese:
            continue
        lines.append(f"- [{rule_type}] Chinese: {chinese or '-'} | English: {english or '-'}")
    return "\n".join(lines) or "No terminology rules are provided."


def _placeholder(index):
    # Deliberately plain ASCII so most OpenAI-compatible models copy it exactly.
    return f"PPPROTECT{index:04d}TOKEN"


def protect_text(text, terms, mode):
    """Replace protected material with stable placeholders.

    mode="translate": Locked English terms stay exactly English in the Chinese draft.
    mode="rewrite": Locked Chinese terms are restored to their canonical English term;
                    Locked English terms already present are also preserved.
    LaTeX/math/citations are always restored byte-for-byte.
    """
    replacements = []

    def stash(value, restore=None):
        token = _placeholder(len(replacements))
        replacements.append((token, value if restore is None else restore))
        return token

    # Protect LaTeX first so terminology matching never touches content inside math.
    combined = "|".join(f"(?:{pattern})" for pattern in LATEX_PATTERNS)
    protected = re.sub(combined, lambda m: stash(m.group(0)), text, flags=re.DOTALL)

    locked = [item for item in terms if (item.get("type") or "").strip() == "locked"]
    # Longest terms first avoids partial replacement when terms overlap.
    locked.sort(key=lambda item: max(len((item.get("english") or "")), len((item.get("chinese") or ""))), reverse=True)

    for item in locked:
        english = (item.get("english") or "").strip()
        chinese = (item.get("chinese") or "").strip()

        if mode == "translate" and english:
            protected = re.sub(re.escape(english), lambda m: stash(m.group(0)), protected, flags=re.IGNORECASE)
        elif mode == "rewrite":
            if chinese and english:
                protected = protected.replace(chinese, stash(chinese, restore=english))
            if english:
                protected = re.sub(re.escape(english), lambda m: stash(m.group(0), restore=english), protected, flags=re.IGNORECASE)

    return protected, replacements


def restore_text(text, replacements):
    restored = text
    missing = []
    for token, value in replacements:
        if token not in restored:
            missing.append(token)
        restored = restored.replace(token, value)
    if missing:
        raise ValueError("模型未完整保留受保护的术语或 LaTeX 占位符，请重新生成。")
    return restored


def chat_completion(system_prompt, user_prompt):
    config = llm_config()
    if not config["api_key"]:
        raise RuntimeError("LLM_API_KEY is not configured")

    response = requests.post(
        f"{config['base_url']}/chat/completions",
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        },
        json={
            "model": config["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        },
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    return payload["choices"][0]["message"]["content"].strip()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/config")
def config_status():
    config = llm_config()
    return jsonify(
        {
            "configured": bool(config["api_key"]),
            "model": config["model"],
            "base_url": config["base_url"],
        }
    )


@app.post("/api/translate")
def translate():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    terms = data.get("terms") or []
    if not text:
        return jsonify({"error": "English source text is required"}), 400

    protected_text, replacements = protect_text(text, terms, mode="translate")
    system_prompt = """You are a precise academic translator for scientific papers.
Translate English academic prose into faithful, natural Chinese for comprehension and editing.
Do not polish, expand, summarize, or alter the technical meaning.
Strings shaped like PPPROTECT0000TOKEN are immutable placeholders: copy every one exactly and do not translate, delete, duplicate, split, or reorder it.
Respect preferred terminology rules. Return only the Chinese translation, without commentary."""
    user_prompt = f"""Terminology rules:\n{build_term_rules(terms)}\n\nEnglish paragraph:\n{protected_text}"""

    try:
        result = restore_text(chat_completion(system_prompt, user_prompt), replacements)
        return jsonify({"result": result})
    except requests.RequestException as exc:
        return jsonify({"error": f"LLM request failed: {exc}"}), 502
    except (RuntimeError, KeyError, IndexError, TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/rewrite")
def rewrite():
    data = request.get_json(silent=True) or {}
    chinese = (data.get("chinese") or "").strip()
    original = (data.get("original") or "").strip()
    terms = data.get("terms") or []
    style = (data.get("style") or "CVPR/IEEE concise academic style").strip()

    if not chinese:
        return jsonify({"error": "Edited Chinese text is required"}), 400

    protected_chinese, replacements = protect_text(chinese, terms, mode="rewrite")
    protected_original, original_replacements = protect_text(original, terms, mode="rewrite")
    # Keep placeholder namespaces unique when both texts contain protected content.
    if original_replacements:
        offset = len(replacements)
        for old_token, value in original_replacements:
            old_index = int(re.search(r"(\d{4})", old_token).group(1))
            new_token = _placeholder(offset + old_index)
            protected_original = protected_original.replace(old_token, new_token)
            replacements.append((new_token, value))

    system_prompt = """You are an expert academic English editor for computer vision, robotics, SLAM, and machine learning papers.
Rewrite the user's edited Chinese into publication-quality academic English.
The Chinese text is the authoritative intended meaning. The original English is context only and may contain wording problems.
Use concise, technically precise academic prose. Avoid unnecessary adjectives and inflated claims.
Strings shaped like PPPROTECT0000TOKEN are immutable placeholders: copy placeholders from the edited Chinese exactly. Do not translate, delete, duplicate, split, or alter them.
Respect preferred terminology rules and keep terminology consistent.
Return only the final English paragraph, without explanations, bullets, or quotation marks."""
    user_prompt = f"""Target style:\n{style}\n\nTerminology rules:\n{build_term_rules(terms)}\n\nOriginal English for context:\n{protected_original or '(none)'}\n\nEdited Chinese meaning:\n{protected_chinese}"""

    try:
        raw_result = chat_completion(system_prompt, user_prompt)
        # The final response is only required to preserve placeholders belonging to
        # the authoritative Chinese input. Context-only placeholders may be omitted.
        result = restore_text(raw_result, replacements[: len(replacements) - len(original_replacements)] if original_replacements else replacements)
        return jsonify({"result": result})
    except requests.RequestException as exc:
        return jsonify({"error": f"LLM request failed: {exc}"}), 502
    except (RuntimeError, KeyError, IndexError, TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG", "0") == "1")
