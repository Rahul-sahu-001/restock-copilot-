"""Messages the 4 agents send each other."""
from typing import Dict, List

from uagents import Model


class PlanRequest(Model):
    request_id: str
    shop_id: str = "demo-shop"


class PlanResponse(Model):
    request_id: str
    needs: Dict[str, float] = {}
    units: Dict[str, str] = {}
    note: str = ""
    error: str = ""


class PriceRequest(Model):
    request_id: str
    items: List[str]


class PriceResponse(Model):
    request_id: str
    prices: Dict[str, Dict[str, float]] = {}
    errors: List[str] = []


class OrderRequest(Model):
    request_id: str
    user_address: str
    order_json: str
    total_inr: float


class OrderUpdate(Model):
    request_id: str
    status: str  # payment_requested | paid | failed
    text: str = ""


class DemoPay(Model):
    """Only used in DEMO_MODE to simulate a payment from chat."""

    request_id: str
