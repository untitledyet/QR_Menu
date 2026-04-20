"""Configuration for the menu scraper."""
import os
import ssl
import certifi

# Fix macOS Homebrew Python SSL certificate issue (must be set before any HTTPS calls)
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = "gpt-5.4"
OPENAI_MODEL_MINI = "gpt-4o-mini"
# Output folder lives inside the scraper package directory
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scraper_output")
PHOTOS_DIR = os.path.join(OUTPUT_DIR, "photos")
HEADLESS = False
SLOW_MO = 100
