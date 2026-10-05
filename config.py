import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
CACHE_DIR = DATA_DIR / "cache"

DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# DefiLlama Endpoints (Free, no API key required)
DEFILLAMA_PROTOCOLS_URL = "https://api.llama.fi/protocols"
DEFILLAMA_FEES_URL = "https://api.llama.fi/overview/fees"
DEFILLAMA_CHAINS_URL = "https://api.llama.fi/v2/chains"

# CoinGecko Endpoints
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
COINGECKO_TRENDING_URL = "https://api.coingecko.com/api/v3/search/trending"

# Cache TTL in seconds (default: 4 hours)
CACHE_TTL = int(os.getenv("CACHE_TTL_HOURS", "4")) * 3600
