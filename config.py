"""Central settings + agent addresses (derived from seeds, so no copy-paste needed)."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv optional
    pass

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

SEED_PREFIX = os.getenv("SEED_PREFIX", "change-this-secret-prefix")
PORTS = {"manager": 8000, "planner": 8001, "price": 8002, "order": 8003}

DEMO_MODE = os.getenv("DEMO_MODE", "1") == "1"
DEMO_FAIL_PRICE_API = os.getenv("DEMO_FAIL_PRICE_API", "0") == "1"
PRICE_API_URL = os.getenv("PRICE_API_URL", "").strip()

PAYMENT_CURRENCY = os.getenv("PAYMENT_CURRENCY", "USDC")
PAYMENT_METHOD = os.getenv("PAYMENT_METHOD", "skyfire")
INR_PER_USDC = float(os.getenv("INR_PER_USDC", "85"))

TIMEOUT_SECONDS = 25  # how long manager waits for a worker agent


def seed_for(name: str) -> str:
    return f"{SEED_PREFIX}-{name}"


def address_for(name: str) -> str:
    """Address of an agent. Same seed -> same address, so every process agrees."""
    override = os.getenv(f"{name.upper()}_ADDRESS")
    if override:
        return override
    from uagents.crypto import Identity

    return Identity.from_seed(seed_for(name), 0).address
