import json

import config
from logic import best_deals, compute_needs, detect_intent, fetch_prices, format_summary, load_json

SALES = load_json(config.DATA_DIR / "sales_history.json")
SUPPLIERS = load_json(config.DATA_DIR / "suppliers.json")


def test_compute_needs_rounds_up_to_pack_size():
    needs, units, note = compute_needs(SALES)
    # rice: 40*1.3*1.1 = 57.2 - 12 stock = 45.2 -> rounded up to pack of 5 = 50
    assert needs["rice"] == 50
    assert units["rice"] == "kg"
    assert "Diwali" in note


def test_no_order_when_stock_is_enough():
    sales = json.loads(json.dumps(SALES))
    sales["items"]["sugar"]["current_stock"] = 100
    needs, _, _ = compute_needs(sales)
    assert needs["sugar"] == 0


def test_best_deals_picks_cheapest_supplier():
    needs = {"rice": 50.0, "oil": 10.0}
    units = {"rice": "kg", "oil": "litre"}
    lines, total, missing = best_deals(needs, units, SUPPLIERS["prices"])
    by_item = {l["item"]: l for l in lines}
    assert by_item["rice"]["supplier"] == "Gupta Traders"
    assert by_item["oil"]["supplier"] == "Kisan Mandi Direct"
    assert total == 50 * 46 + 10 * 126.5
    assert missing == []


def test_missing_prices_are_reported():
    lines, total, missing = best_deals({"jaggery": 5.0}, {"jaggery": "kg"}, {})
    assert lines == [] and total == 0 and missing == ["jaggery"]


def test_price_api_failure_falls_back_to_cache():
    prices, errors = fetch_prices(["rice", "dal"], SUPPLIERS, force_fail=True, retries=2)
    assert "rice" in prices and "dal" in prices  # cached prices still returned
    assert len(errors) >= 2  # failures were reported, not hidden


def test_intent_detection():
    assert detect_intent("order kitna karun", None) == "restock"
    assert detect_intent("order", "await_confirm") == "confirm"
    assert detect_intent("cancel", "await_confirm") == "cancel"
    assert detect_intent("इस हफ़्ते क्या मँगाऊँ?", "await_confirm") == "restock"
    assert detect_intent("pay", "awaiting_payment") == "pay"


def test_summary_mentions_total():
    lines, total, missing = best_deals({"rice": 50.0}, {"rice": "kg"}, SUPPLIERS["prices"])
    text = format_summary("Test", lines, total, missing, [], "")
    assert "₹2,300" in text
