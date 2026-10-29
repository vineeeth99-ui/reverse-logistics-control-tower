
"""Local Qwen LLM service using Ollama.

No API key or external LLM service is required.
Python 3.9 compatible.
"""

import json
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen3.5:4b"

# Keep Qwen loaded between requests.
KEEP_ALIVE = "10m"

# Allow more room for complete answers while keeping responses concise.
NUM_PREDICT = 384
NUM_CTX = 4096
TEMPERATURE = 0.2

logger = logging.getLogger(__name__)


def generate_response(prompt, system_prompt=None, timeout=120):
    """Generate a response from the local Qwen model."""

    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Prompt must be a non-empty string.")

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "keep_alive": KEEP_ALIVE,
        "options": {
            "temperature": TEMPERATURE,
            "num_predict": NUM_PREDICT,
            "num_ctx": NUM_CTX,
        },
    }

    if system_prompt:
        payload["system"] = system_prompt

    request = Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started_at = time.perf_counter()

    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(
            "Ollama returned HTTP error {}: {}".format(exc.code, details)
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            "Cannot connect to Ollama. Make sure Ollama is running."
        ) from exc

    elapsed_seconds = time.perf_counter() - started_at
    answer = result.get("response", "").strip()

    load_seconds = result.get("load_duration", 0) / 1_000_000_000
    prompt_seconds = result.get("prompt_eval_duration", 0) / 1_000_000_000
    generation_seconds = result.get("eval_duration", 0) / 1_000_000_000
    generated_tokens = result.get("eval_count", 0)
    done_reason = result.get("done_reason", "unknown")

    tokens_per_second = (
        generated_tokens / generation_seconds
        if generation_seconds > 0
        else 0
    )

    logger.info(
        "Ollama timing: total=%.2fs load=%.2fs prompt=%.2fs "
        "generation=%.2fs tokens=%s tokens_per_second=%.1f "
        "done_reason=%s",
        elapsed_seconds,
        load_seconds,
        prompt_seconds,
        generation_seconds,
        generated_tokens,
        tokens_per_second,
        done_reason,
    )

    if not answer:
        raise RuntimeError(
            "Qwen returned an empty visible answer (done_reason={!r}, "
            "generated_tokens={}). Check Ollama and model compatibility."
            .format(done_reason, generated_tokens)
        )

    if done_reason == "length":
        logger.warning(
            "Qwen reached the output token limit; the answer may be incomplete."
        )

    return answer
