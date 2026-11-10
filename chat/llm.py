"""Thin wrapper around the chat model so the rest of the app never touches the SDK.

Raises LLMError for every failure (no key, network, auth, rate limit), so callers
only need one except clause and can fall back to showing passages.
"""
import os

from django.conf import settings


class LLMError(Exception):
    pass


def generate(system: str, user: str) -> str:
    if not os.environ.get("OPENAI_API_KEY"):
        raise LLMError("OPENAI_API_KEY is not set")
    from openai import OpenAI

    client = OpenAI(timeout=settings.LLM_TIMEOUT_SECONDS, max_retries=1)
    try:
        resp = client.chat.completions.create(
            model=settings.LLM_MODEL,
            temperature=0.1,
            max_tokens=500,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
    except Exception as exc:  # network, auth, rate limit, bad model name
        raise LLMError(str(exc)) from exc
    return (resp.choices[0].message.content or "").strip()
