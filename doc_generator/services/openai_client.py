import time
import openai
from django.conf import settings


class OpenAIClient:
    """
    Wrapper around OpenAI ChatCompletion API.
    Handles sending prompts and retrieving structured results.
    """

    def __init__(self):
        openai.api_key = settings.OPENAI_API_KEY

    def generate(self, prompt: str, max_tokens=1200, temperature=0.2, model="gpt-4o-mini"):
        start = time.time()

        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )

        latency = (time.time() - start) * 1000  # ms

        return {
            "text": response["choices"][0]["message"]["content"],
            "tokens": response["usage"]["total_tokens"],
            "latency": latency,
            "model": model,
        }

