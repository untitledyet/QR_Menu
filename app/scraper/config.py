"""Configuration for the menu scraper."""
import os
import ssl
import certifi

# Fix macOS Homebrew Python SSL certificate issue (must be set before any HTTPS calls)
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


# ── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Model tiers (override via env when needed).
# Reasoning-heavy vision + parsing → flagship model.
# Simple classification/translation → flagship (fast enough) unless env overrides.
# Embeddings → text-embedding-3-large for best semantic quality.
OPENAI_MODEL_VISION   = os.environ.get("OPENAI_MODEL_VISION",   "gpt-5.4")
OPENAI_MODEL_REASON   = os.environ.get("OPENAI_MODEL_REASON",   "gpt-5.4")
OPENAI_MODEL_FAST     = os.environ.get("OPENAI_MODEL_FAST",     "gpt-5.4")
OPENAI_MODEL_EMBED    = os.environ.get("OPENAI_MODEL_EMBED",    "text-embedding-3-large")
OPENAI_MODEL_IMAGE_GEN = os.environ.get("OPENAI_MODEL_IMAGE_GEN", "gpt-image-1")

# Back-compat: some callers still reference the old names.
OPENAI_MODEL      = OPENAI_MODEL_VISION
OPENAI_MODEL_MINI = OPENAI_MODEL_FAST

# ── Playwright ────────────────────────────────────────────────────────────────
HEADLESS = _env_bool("SCRAPER_HEADLESS", True)
SLOW_MO  = int(os.environ.get("SCRAPER_SLOW_MO", "0"))

# ── Output paths ──────────────────────────────────────────────────────────────
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scraper_output")
PHOTOS_DIR = os.path.join(OUTPUT_DIR, "photos")

# ── HTTP timeouts for LLM calls ───────────────────────────────────────────────
LLM_TIMEOUT_CONNECT = float(os.environ.get("LLM_TIMEOUT_CONNECT", "10"))
LLM_TIMEOUT_READ    = float(os.environ.get("LLM_TIMEOUT_READ",    "240"))
LLM_TIMEOUT_WRITE   = float(os.environ.get("LLM_TIMEOUT_WRITE",   "60"))
LLM_TIMEOUT_POOL    = float(os.environ.get("LLM_TIMEOUT_POOL",    "10"))

# ── Image pipeline ────────────────────────────────────────────────────────────
# Max dimension fed to vision model. Anything larger gets downscaled before base64.
VISION_MAX_PX = int(os.environ.get("VISION_MAX_PX", "2000"))

# ── Retry policy for LLM calls ────────────────────────────────────────────────
LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "2"))
