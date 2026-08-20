import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)


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

    system_prompt = """You are a precise academic translator for scientific papers.
Translate English academic prose into faithful, natural Chinese for comprehension and editing.
Do not polish, expand, summarize, or alter the technical meaning.
Preserve LaTeX commands, math expressions, equation environments, citation commands, reference commands, variable names, acronyms, and symbols exactly as written.
Respect locked/preferred terminology rules. Return only the Chinese translation, without commentary."""
    user_prompt = f"""Terminology rules:\n{build_term_rules(terms)}\n\nEnglish paragraph:\n{text}"""

    try:
        result = chat_completion(system_prompt, user_prompt)
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

    system_prompt = """You are an expert academic English editor for computer vision, robotics, SLAM, and machine learning papers.
Rewrite the user's edited Chinese into publication-quality academic English.
The Chinese text is the authoritative intended meaning. The original English is context only and may contain wording problems.
Use concise, technically precise academic prose. Avoid unnecessary adjectives and inflated claims.
Preserve LaTeX commands, math expressions, equation environments, citation commands, reference commands, variable names, acronyms, and symbols exactly.
Respect locked/preferred terminology rules and keep terminology consistent.
Return only the final English paragraph, without explanations, bullets, or quotation marks."""
    user_prompt = f"""Target style:\n{style}\n\nTerminology rules:\n{build_term_rules(terms)}\n\nOriginal English for context:\n{original or '(none)'}\n\nEdited Chinese meaning:\n{chinese}"""

    try:
        result = chat_completion(system_prompt, user_prompt)
        return jsonify({"result": result})
    except requests.RequestException as exc:
        return jsonify({"error": f"LLM request failed: {exc}"}), 502
    except (RuntimeError, KeyError, IndexError, TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG", "0") == "1")
