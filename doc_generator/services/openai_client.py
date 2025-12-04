# generator/services/openai_client.py
import time
import logging
import os
from typing import Any

from django.conf import settings

# openai v1+ client
try:
    from openai import OpenAI
except Exception as exc:
    OpenAI = None

logger = logging.getLogger(__name__)


def _make_json_serializable(obj: Any):
    """
    Try to convert OpenAI SDK objects to plain Python structures suitable for JSONField.
    Strategy:
      1) If object has to_dict(), call it.
      2) If object is dict-like, return dict(obj).
      3) If object is list/tuple, attempt to convert elements recursively.
      4) Otherwise return str(obj) as a last resort.
    """
    # guard against None or basic types
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    # to_dict() if available on SDK objects
    try:
        if hasattr(obj, "to_dict") and callable(getattr(obj, "to_dict")):
            return obj.to_dict()
    except Exception:
        pass

    # dict-like
    try:
        if isinstance(obj, dict):
            return {k: _make_json_serializable(v) for k, v in obj.items()}
    except Exception:
        pass

    # list/tuple
    if isinstance(obj, (list, tuple)):
        return [_make_json_serializable(x) for x in obj]

    # try dict() conversion
    try:
        d = dict(obj)
        return {k: _make_json_serializable(v) for k, v in d.items()}
    except Exception:
        pass

    # fallback to string
    try:
        return str(obj)
    except Exception:
        return {"__unserializable__": repr(obj)}


class OpenAIClient:
    """
    Wrapper for OpenAI >=1.0.0 python client.

    Usage:
        client = OpenAIClient()
        result = client.generate(prompt, max_tokens=800)
        # result: dict with keys 'text', 'tokens', 'model', 'latency', 'raw' (serializable)
    """

    def __init__(self, api_key: str | None = None, default_model: str | None = None):
        if OpenAI is None:
            raise RuntimeError("openai package (>=1.0.0) not available. Install with: pip install openai>=1.0.0")

        self.api_key = api_key or getattr(settings, "OPENAI_API_KEY", None) or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set in Django settings or environment variables")

        # instantiate client
        self.client = OpenAI(api_key=self.api_key)
        self.default_model = default_model or getattr(settings, "OPENAI_DEFAULT_MODEL", "gpt-4o-mini")

    def generate(self, prompt: str, max_tokens: int = 800, temperature: float = 0.2, model: str | None = None, n_retries: int = 2):
        """
        Generate text for a given prompt.

        Returns:
          {
            "text": str,
            "tokens": int|None,
            "model": str,
            "latency": float (ms),
            "raw": dict  # JSON-serializable raw response (or fallback string)
          }
        """
        model = model or self.default_model

        messages = [
            {"role": "system", "content": "You are an ISO/IEC 27001 policy writer. Use formal corporate tone."},
            {"role": "user", "content": prompt},
        ]

        attempt = 0
        while True:
            attempt += 1
            try:
                start = time.time()
                # v1+ client call
                resp = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                latency = (time.time() - start) * 1000.0

                # Convert raw response to serializable structure
                try:
                    raw_serializable = _make_json_serializable(resp)
                except Exception:
                    raw_serializable = {"__raw_str__": str(resp)}

                # Extract text from response safely
                text = ""
                try:
                    # many SDK responses provide choices as an attribute
                    choices = getattr(resp, "choices", None)
                    if choices and len(choices) > 0:
                        choice0 = choices[0]
                        # prefer .message.content if present
                        if hasattr(choice0, "message") and getattr(choice0.message, "content", None) is not None:
                            text = choice0.message.content
                        else:
                            # fallback: some variants use .text
                            text = getattr(choice0, "text", "") or ""
                    else:
                        # try dict access on the serializable fallback
                        if isinstance(raw_serializable, dict):
                            text = raw_serializable.get("choices", [{}])[0].get("message", {}).get("content", "") or raw_serializable.get("choices", [{}])[0].get("text", "") or ""
                except Exception:
                    text = ""

                # Extract token usage if available
                tokens = None
                try:
                    usage = getattr(resp, "usage", None)
                    if usage is None and isinstance(raw_serializable, dict):
                        usage = raw_serializable.get("usage")
                    if usage:
                        # usage may be attr or dict
                        if isinstance(usage, dict):
                            tokens = int(usage.get("total_tokens")) if usage.get("total_tokens") is not None else None
                        else:
                            tokens = int(getattr(usage, "total_tokens", None))
                except Exception:
                    tokens = None

                return {
                    "text": text,
                    "tokens": tokens,
                    "model": model,
                    "latency": latency,
                    "raw": raw_serializable,
                }

            except Exception as exc:
                logger.exception("OpenAI generate attempt %s failed: %s", attempt, exc)
                if attempt > n_retries:
                    # re-raise so caller can handle/display error
                    raise
                # small backoff then retry
                time.sleep(1.0 * attempt)

