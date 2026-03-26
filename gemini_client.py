"""
Gemini Client — centralized wrapper for Google Gemini API calls.

Provides text generation (with optional structured JSON output) and
embedding functionality used by all modules in Echo CRM.
"""

import logging
import asyncio
import time
from typing import Any

from google import genai
from google.genai import types
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

import config

logger = logging.getLogger(__name__)

class UsageTracker:
    """Tracks Gemini API token usage and estimated cost locally."""
    
    # Pricing for gemini-3.1-flash-lite-preview ($/1M tokens)
    COST_PER_1M_INPUT = 0.25
    COST_PER_1M_OUTPUT = 1.50

    def __init__(self):
        self.usage_file = config.GEMINI_USAGE_FILE
        self._input_tokens = 0
        self._output_tokens = 0
        self._load()

    def _load(self):
        if self.usage_file.exists():
            try:
                import json
                with open(self.usage_file, "r") as f:
                    data = json.load(f)
                    self._input_tokens = data.get("input_tokens", 0)
                    self._output_tokens = data.get("output_tokens", 0)
            except Exception as e:
                logger.error(f"Failed to load usage data: {e}")

    def _save(self):
        import json
        try:
            with open(self.usage_file, "w") as f:
                json.dump({
                    "input_tokens": self._input_tokens,
                    "output_tokens": self._output_tokens,
                    "estimated_cost_usd": self.get_estimated_cost(),
                    "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save usage data: {e}")

    def update(self, input_tokens: int, output_tokens: int):
        """Update token counts and save to disk."""
        self._input_tokens += input_tokens
        self._output_tokens += output_tokens
        self._save()

    def get_estimated_cost(self) -> float:
        """Calculate total estimated cost in USD."""
        input_cost = (self._input_tokens / 1_000_000) * self.COST_PER_1M_INPUT
        output_cost = (self._output_tokens / 1_000_000) * self.COST_PER_1M_OUTPUT
        return input_cost + output_cost

def log_retry(retry_state):
    """Log when a retry is happening with appropriate context."""
    exception = retry_state.outcome.exception()
    msg = str(exception).lower()
    
    if "429" in msg or "resource_exhausted" in msg:
        status = "Rate Limit Hit"
    elif "503" in msg or "service_unavailable" in msg:
        status = "Service Unavailable (503)"
    else:
        status = "Error"

    logger.warning(
        f"  ⚠️ Gemini {status}. Waiting {retry_state.next_action.sleep:.1f}s "
        f"before attempt {retry_state.attempt_number}/5..."
    )

class RateLimiter:
    """Simple async rate limiter targeting Requests Per Minute (RPM)."""
    
    def __init__(self, rpm: float):
        self.delay = 60.0 / rpm
        self.last_call = 0.0
        self.lock = asyncio.Lock()

    async def wait(self):
        """Wait until it's safe to make another request."""
        async with self.lock:
            now = time.time()
            elapsed = now - self.last_call
            if elapsed < self.delay:
                sleep_time = self.delay - elapsed
                await asyncio.sleep(sleep_time)
            self.last_call = time.time()

def is_retryable(exception):
    """Check if the exception is a 429 (Rate Limit)."""
    msg = str(exception).lower()
    return "429" in msg or "resource_exhausted" in msg

class GeminiClient:
    """Single-responsibility wrapper around the Google GenAI SDK."""

    def __init__(self):
        # Target configured RPM (e.g. 15 for 3.1 Flash Lite)
        self._limiter = RateLimiter(rpm=config.GEMINI_RPM)
        self._tracker = UsageTracker()

        if not config.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. "
                "Get a free key at https://aistudio.google.com/apikey "
                "and set it as an environment variable."
            )
        self._client = genai.Client(api_key=config.GEMINI_API_KEY)
        self._model = config.GEMINI_MODEL
        self._embed_model = config.GEMINI_EMBED_MODEL

    def _check_budget(self):
        """Check if we have exceeded our specified budget."""
        cost = self._tracker.get_estimated_cost()
        if cost >= config.GEMINI_MAX_SPEND:
            msg = f"❌ Budget Exceeded! Estimated Spend: ${cost:.4f} / Limit: ${config.GEMINI_MAX_SPEND:.2f}"
            logger.error(msg)
            raise RuntimeError(msg)

    def _update_usage(self, response: Any):
        """Extract usage metadata and update the tracker."""
        try:
            usage = getattr(response, "usage_metadata", None)
            if usage:
                self._tracker.update(
                    input_tokens=usage.prompt_token_count or 0,
                    output_tokens=usage.candidates_token_count or 0
                )
        except Exception as e:
            logger.debug(f"Failed to update usage: {e}")

    # ------------------------------------------------------------------
    # Text generation
    # ------------------------------------------------------------------

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(Exception),
        before_sleep=log_retry,
        retry_error_callback=lambda state: "", # Return empty on final failure
    )
    def generate(
        self,
        prompt: str,
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.3,
        max_output_tokens: int = 8192,
    ) -> str:
        """Synchronous text generation with retries."""
        self._check_budget()
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                pass
            else:
                asyncio.run(self._limiter.wait())
        except RuntimeError:
            time.sleep(1.0) # Assume 60 RPM if no loop

        gen_config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

        if json_schema is not None:
            gen_config.response_mime_type = "application/json"
            gen_config.response_schema = json_schema

        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=gen_config,
        )
        self._update_usage(response)
        logger.info(f"  ✅ Gemini API Success ({len(response.text or '')} chars)")
        return response.text or ""

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(Exception),
        before_sleep=log_retry,
    )
    async def generate_async(
        self,
        prompt: str,
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.1,
        max_output_tokens: int = 8192,
    ) -> str:
        """Async text generation with retries and rate limiting."""
        self._check_budget()
        await self._limiter.wait()
        
        gen_config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

        if json_schema is not None:
            gen_config.response_mime_type = "application/json"
            gen_config.response_schema = json_schema

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
            config=gen_config,
        )
        self._update_usage(response)
        logger.info(f"  ✅ Gemini Async API Success ({len(response.text or '')} chars)")
        return response.text or ""

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(Exception),
    )
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings with retries."""
        if not texts:
            return []

        response = self._client.models.embed_content(
            model=self._embed_model,
            contents=texts,
        )
        # Usage tracking for embeddings could be added here if needed
        return [e.values for e in response.embeddings]
