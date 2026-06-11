"""
multi_provider_llm.py
=====================
Lightweight multi-provider LLM router for Odysseus AI.
Routes inference requests to free external APIs when no local LLM is available,
eliminating the need for 230GB+ RAM to run models locally inside HF Spaces.

Priority order (configurable via env):
  1. Groq          - Ultra-fast LPU inference, free tier (30 RPM)
  2. Cerebras      - Ultra-fast, free tier (30 RPM, 1M TPD)
  3. GitHub Models - Free for GitHub users (10-15 RPM)
  4. HF Router     - 100K credits/month free
  5. Cloudflare AI - 10K neurons/day free
  6. OpenRouter    - Free models available
  7. Local Ollama  - Fallback to local if available

All providers expose an OpenAI-compatible /v1/chat/completions endpoint.
"""

import logging
import os
import time
from typing import Any, Dict, Iterator, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Provider definitions
# ──────────────────────────────────────────────────────────────────────────────
PROVIDERS: List[Dict[str, Any]] = [
    {
        "name": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "default_model": "llama-3.3-70b-versatile",
        "free_models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "qwen3-32b",
            "deepseek-r1-distill-70b",
        ],
        "rate_limit_rpm": 30,
        "context_window": 131072,
        "supports_streaming": True,
    },
    {
        "name": "cerebras",
        "base_url": "https://api.cerebras.ai/v1",
        "api_key_env": "CEREBRAS_API_KEY",
        "default_model": "llama-3.3-70b",
        "free_models": [
            "llama-3.3-70b",
            "llama-3.1-8b",
            "qwen-3-32b",
        ],
        "rate_limit_rpm": 30,
        "context_window": 8192,
        "supports_streaming": True,
    },
    {
        "name": "github_models",
        "base_url": "https://models.github.ai/inference",
        "api_key_env": "GITHUB_TOKEN",
        "default_model": "Meta-Llama-3.3-70B",
        "free_models": [
            "Meta-Llama-3.3-70B",
            "gpt-4o-mini",
            "Mistral-Small-3.1",
            "DeepSeek-R1",
        ],
        "rate_limit_rpm": 15,
        "context_window": 131072,
        "supports_streaming": True,
    },
    {
        "name": "huggingface_router",
        "base_url": "https://router.huggingface.co/v1",
        "api_key_env": "HF_TOKEN",
        "default_model": "meta-llama/Llama-3.1-8B-Instruct",
        "free_models": [
            "meta-llama/Llama-3.1-8B-Instruct",
            "mistralai/Mistral-7B-Instruct-v0.3",
            "Qwen/Qwen2.5-7B-Instruct",
        ],
        "rate_limit_rpm": 10,
        "context_window": 128000,
        "supports_streaming": True,
    },
    {
        "name": "cloudflare_ai",
        "base_url": "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
        "api_key_env": "CLOUDFLARE_API_KEY",
        "account_id_env": "CLOUDFLARE_ACCOUNT_ID",
        "default_model": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
        "free_models": [
            "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
            "@cf/meta/llama-3.1-8b-instruct-fp8-fast",
            "@cf/mistralai/mistral-small-3.1-24b-instruct",
        ],
        "rate_limit_rpm": 20,
        "context_window": 131072,
        "supports_streaming": True,
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# Provider health tracking
# ──────────────────────────────────────────────────────────────────────────────
_provider_health: Dict[str, Dict] = {}


def _get_provider_health(name: str) -> Dict:
    if name not in _provider_health:
        _provider_health[name] = {
            "failures": 0,
            "last_failure": 0.0,
            "cooldown": 30.0,
        }
    return _provider_health[name]


def _is_provider_available(provider: Dict) -> bool:
    """Check if a provider has an API key and is not in cooldown."""
    name = provider["name"]
    api_key_env = provider["api_key_env"]

    # Special handling for Cloudflare (needs account_id too)
    if name == "cloudflare_ai":
        if not os.getenv("CLOUDFLARE_ACCOUNT_ID"):
            return False

    if not os.getenv(api_key_env):
        return False

    health = _get_provider_health(name)
    if health["failures"] >= 3:
        if time.time() - health["last_failure"] < health["cooldown"]:
            return False
        # Reset after cooldown
        health["failures"] = 0

    return True


def _get_api_key(provider: Dict) -> str:
    return os.getenv(provider["api_key_env"], "")


def _get_base_url(provider: Dict) -> str:
    url = provider["base_url"]
    if provider["name"] == "cloudflare_ai":
        account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
        url = url.replace("{account_id}", account_id)
    return url


# ──────────────────────────────────────────────────────────────────────────────
# Core call function
# ──────────────────────────────────────────────────────────────────────────────
def call_provider(
    provider: Dict,
    messages: List[Dict],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    stream: bool = False,
    timeout: float = 60.0,
) -> Any:
    """Make a chat completion call to a specific provider."""
    base_url = _get_base_url(provider)
    api_key = _get_api_key(provider)
    model_name = model or provider["default_model"]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }

    try:
        if stream:
            with httpx.stream(
                "POST",
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        yield line
        else:
            r = httpx.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            r.raise_for_status()
            # Reset failures on success
            _get_provider_health(provider["name"])["failures"] = 0
            return r.json()

    except httpx.HTTPStatusError as e:
        health = _get_provider_health(provider["name"])
        health["failures"] += 1
        health["last_failure"] = time.time()
        logger.warning(
            f"Provider {provider['name']} HTTP error {e.response.status_code}: "
            f"{e.response.text[:200]}"
        )
        raise
    except Exception as e:
        health = _get_provider_health(provider["name"])
        health["failures"] += 1
        health["last_failure"] = time.time()
        logger.warning(f"Provider {provider['name']} error: {e}")
        raise


# ──────────────────────────────────────────────────────────────────────────────
# Auto-routing: try providers in priority order
# ──────────────────────────────────────────────────────────────────────────────
def auto_call(
    messages: List[Dict],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    stream: bool = False,
    preferred_provider: Optional[str] = None,
    timeout: float = 60.0,
) -> Any:
    """
    Auto-route to the best available free provider.
    Falls back through the provider list until one succeeds.
    """
    # Build ordered list
    ordered = list(PROVIDERS)
    if preferred_provider:
        ordered = sorted(
            ordered,
            key=lambda p: (0 if p["name"] == preferred_provider else 1),
        )

    last_error = None
    for provider in ordered:
        if not _is_provider_available(provider):
            logger.debug(f"Skipping provider {provider['name']} (unavailable/no key)")
            continue

        try:
            logger.info(f"Trying provider: {provider['name']}")
            result = call_provider(
                provider=provider,
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
                timeout=timeout,
            )
            return result
        except Exception as e:
            last_error = e
            logger.warning(f"Provider {provider['name']} failed, trying next...")
            continue

    raise RuntimeError(
        f"All external LLM providers failed or have no API keys configured. "
        f"Last error: {last_error}. "
        f"Set at least one of: GROQ_API_KEY, CEREBRAS_API_KEY, GITHUB_TOKEN, HF_TOKEN."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Convenience: get available providers list for UI
# ──────────────────────────────────────────────────────────────────────────────
def get_available_providers() -> List[Dict]:
    """Return list of providers that have API keys configured."""
    available = []
    for p in PROVIDERS:
        if _is_provider_available(p):
            available.append({
                "name": p["name"],
                "default_model": p["default_model"],
                "free_models": p["free_models"],
                "context_window": p["context_window"],
                "rate_limit_rpm": p["rate_limit_rpm"],
            })
    return available


def get_provider_status() -> Dict[str, Any]:
    """Return status of all providers for diagnostics."""
    status = {}
    for p in PROVIDERS:
        key_set = bool(os.getenv(p["api_key_env"]))
        available = _is_provider_available(p)
        health = _get_provider_health(p["name"])
        status[p["name"]] = {
            "api_key_configured": key_set,
            "available": available,
            "failures": health["failures"],
            "last_failure": health["last_failure"],
        }
    return status
