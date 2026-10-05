"""
Shared Gemini LLM client using the new google.genai SDK.
Single source of truth for all AI calls in the project.
Supports automatic model cascade on quota/404 errors.
"""

import json
import time
from typing import Any, Optional

from config import GEMINI_API_KEY, GEMINI_MODEL

try:
    from google import genai
    from google.genai import types as genai_types
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False


# Model cascade: try preferred model, fall back on quota/404
_MODEL_CASCADE = [
    GEMINI_MODEL,          # from config / .env
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-2.5-flash",
]

# Deduplicate while preserving order
_MODELS = list(dict.fromkeys(_MODEL_CASCADE))


def _make_client() -> Optional[Any]:
    if not _GENAI_AVAILABLE or not GEMINI_API_KEY:
        return None
    return genai.Client(api_key=GEMINI_API_KEY)


_CLIENT = _make_client()


def generate(
    prompt: str,
    system_instruction: Optional[str] = None,
    temperature: float = 0.4,
    response_format: str = "text",   # "text" | "json"
) -> str:
    """
    Calls Gemini with automatic model cascade on quota / 404 errors.
    If response_format=="json", wraps the prompt to request JSON output.
    Returns the response text (already stripped).
    """
    if not _CLIENT:
        return "[AI] GEMINI_API_KEY not configured or google-genai not installed."

    effective_prompt = prompt
    if response_format == "json":
        effective_prompt = (
            prompt
            + "\n\nВАЖНО: Отвечай строго в формате JSON. Никакого текста вне JSON."
        )

    config_kwargs: dict = {"temperature": temperature}
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction

    last_error = ""
    for model_name in _MODELS:
        try:
            time.sleep(1.2)  # Respect free-tier RPM
            response = _CLIENT.models.generate_content(
                model=model_name,
                contents=effective_prompt,
                config=genai_types.GenerateContentConfig(**config_kwargs),
            )
            return (response.text or "").strip()
        except Exception as e:
            err = str(e)
            last_error = err
            if any(code in err for code in ("429", "404", "quota", "RESOURCE_EXHAUSTED", "not found")):
                continue  # Try next model
            return f"[AI] Error: {err}"

    return f"[AI] All models exhausted. Last error: {last_error}"


def generate_json(
    prompt: str,
    system_instruction: Optional[str] = None,
    fallback: Optional[dict] = None,
) -> dict:
    """
    Like generate() but expects JSON response.
    Returns parsed dict, or `fallback` on parse failure.
    """
    raw = generate(prompt, system_instruction=system_instruction, response_format="json")
    # Strip markdown code fences if present
    clean = raw.strip()
    if clean.startswith("```"):
        lines = clean.splitlines()
        clean = "\n".join(lines[1:-1]) if len(lines) > 2 else clean
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return fallback or {"error": "JSON parse failed", "raw": raw[:300]}
