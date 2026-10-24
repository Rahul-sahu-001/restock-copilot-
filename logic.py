"""Pure business logic (no uagents imports) so it is easy to test."""
import json
import math
import re
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HI_NAMES = {
    "rice": "चावल",
    "atta": "आटा",
    "sugar": "चीनी",
    "oil": "तेल",
    "dal": "दाल",
}


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def hi(item: str) -> str:
    return f"{HI_NAMES.get(item, item)} ({item})"


# ---------------------------------------------------------------- planner
def compute_needs(sales: dict, safety: float = 0.10) -> Tuple[Dict[str, float], Dict[str, str], str]:
    """How much of each item to order this week.

    need = avg_weekly_sales * festival_multiplier * (1 + safety) - current_stock,
    rounded UP to the supplier pack size.
    """
    festival = sales.get("upcoming_festival") or {}
    mult = float(festival.get("multiplier", 1.0))
    needs: Dict[str, float] = {}
    units: Dict[str, str] = {}
    for item, d in sales["items"].items():
        target = d["avg_weekly_sales"] * mult * (1 + safety)
        qty = max(0.0, target - d["current_stock"])
        pack = d.get("pack_size", 1) or 1
        qty = math.ceil(qty / pack) * pack if qty > 0 else 0.0
        needs[item] = float(qty)
        units[item] = d.get("unit", "unit")
    note = ""
    if mult != 1.0:
        note = f"{festival.get('name', 'त्योहार')} की वजह से बिक्री ~{round((mult - 1) * 100)}% ज़्यादा मानी गई है।"
    return needs, units, note


# ----------------------------------------------------------------- prices
def _fetch_live(url: str, items: List[str], timeout: float = 3.0) -> Dict[str, Dict[str, float]]:
    """Adapter for a real price API. Adjust the parsing to your API's format."""
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
        data = json.loads(resp.read().decode("utf-8"))
    return {i: data[i] for i in items if i in data}


def fetch_prices(
    items: List[str],
    fallback: dict,
    api_url: Optional[str] = None,
    retries: int = 2,
    force_fail: bool = False,
) -> Tuple[Dict[str, Dict[str, float]], List[str]]:
    """Try the live API (with retries). On failure fall back to cached prices
    and report what happened - the agent must never crash."""
    errors: List[str] = []
    if api_url or force_fail:
        for attempt in range(1, retries + 1):
            try:
                if force_fail:
                    raise RuntimeError("demo: live price API failure")
                prices = _fetch_live(api_url, items)  # type: ignore[arg-type]
                if prices:
                    return prices, errors
                raise ValueError("live API returned no prices")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Live price API fail (try {attempt}/{retries}): {exc}")
                time.sleep(0.2)
        errors.append("पुराने (cached) रेट इस्तेमाल किए गए।")
    cached = fallback.get("prices", {})
    return {i: cached[i] for i in items if i in cached}, errors


# ------------------------------------------------------------- best deal
def best_deals(
    needs: Dict[str, float], units: Dict[str, str], prices: Dict[str, Dict[str, float]]
) -> Tuple[List[dict], float, List[str]]:
    lines: List[dict] = []
    missing: List[str] = []
    total = 0.0
    for item, qty in needs.items():
        if qty <= 0:
            continue
        quotes = prices.get(item) or {}
        if not quotes:
            missing.append(item)
            continue
        supplier, unit_price = min(quotes.items(), key=lambda kv: kv[1])
        line_total = round(qty * unit_price, 2)
        total += line_total
        lines.append(
            {
                "item": item,
                "qty": qty,
                "unit": units.get(item, ""),
                "supplier": supplier,
                "unit_price": unit_price,
                "total": line_total,
            }
        )
    return lines, round(total, 2), missing


def format_summary(shop: str, lines: List[dict], total: float, missing: List[str], errors: List[str], note: str) -> str:
    out = [f"🛒 {shop} के लिए इस हफ़्ते का restock plan"]
    if note:
        out.append(note)
    out.append("")
    for ln in lines:
        out.append(
            f"• {hi(ln['item'])}: {ln['qty']:g} {ln['unit']} × ₹{ln['unit_price']:g} "
            f"= ₹{ln['total']:,.0f} — {ln['supplier']}"
        )
    out.append("")
    out.append(f"कुल: ₹{total:,.0f} (हर item का सबसे सस्ता supplier चुना गया)")
    if missing:
        out.append("⚠️ इनके रेट नहीं मिले: " + ", ".join(hi(m) for m in missing))
    for e in errors:
        out.append(f"⚠️ {e}")
    out.append("")
    out.append('👉 ऑर्डर पक्का करने के लिए "order" लिखें | रद्द करने के लिए "cancel" लिखें')
    return "\n".join(out)


# ----------------------------------------------------------------- intent
_CONFIRM = {"order", "confirm", "yes", "y", "haan", "han", "हाँ", "हां", "ऑर्डर", "ok", "okay"}
_CANCEL = {"cancel", "no", "n", "nahi", "नहीं", "रद्द"}
_PAY = {"pay", "paid", "payment", "भुगतान"}


def detect_intent(text: str, stage: Optional[str]) -> str:
    """restock | confirm | cancel | pay.  Short replies only count as
    confirm/cancel/pay when we are actually waiting for them."""
    words = re.findall(r"[\w\u0900-\u097F]+", text.lower())
    if stage == "await_confirm" and len(words) <= 4:
        if _CANCEL & set(words):
            return "cancel"
        if _CONFIRM & set(words):
            return "confirm"
    if stage == "awaiting_payment" and len(words) <= 4 and _PAY & set(words):
        return "pay"
    return "restock"
