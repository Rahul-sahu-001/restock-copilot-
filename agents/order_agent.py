"""Order & Payment agent: creates the order and asks the user to pay
using Fetch.ai's Agent Payment Protocol (this agent is the SELLER)."""
import json
from uuid import uuid4

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.payment import (
    CommitPayment,
    CompletePayment,
    Funds,
    RejectPayment,
    RequestPayment,
    payment_protocol_spec,
)

import config
from models import DemoPay, OrderRequest, OrderUpdate

agent = Agent(
    name="restock-order",
    seed=config.seed_for("order"),
    port=config.PORTS["order"],
    mailbox=True,
)
payment_proto = Protocol(spec=payment_protocol_spec, role="seller")
MANAGER = config.address_for("manager")


def _save(ctx: Context, rid: str, order: dict):
    ctx.storage.set(f"order:{rid}", json.dumps(order))


def _load(ctx: Context, rid: str):
    raw = ctx.storage.get(f"order:{rid}")
    return json.loads(raw) if raw else None


async def _mark_paid(ctx: Context, rid: str, tx: str):
    order = _load(ctx, rid)
    if not order or order["status"] == "paid":
        return
    order["status"] = "paid"
    order["tx"] = tx
    _save(ctx, rid, order)
    lines = json.loads(order["order_json"])
    suppliers = sorted({l["supplier"] for l in lines})
    await ctx.send(
        MANAGER,
        OrderUpdate(
            request_id=rid,
            status="paid",
            text=f"✅ Payment मिल गया (ref {tx[:10]}). Order {', '.join(suppliers)} को भेज दिया गया है।",
        ),
    )


@agent.on_event("startup")
async def hello(ctx: Context):
    ctx.logger.info(f"Order agent address: {ctx.agent.address}")


@agent.on_message(model=OrderRequest)
async def on_order(ctx: Context, sender: str, msg: OrderRequest):
    reference = str(uuid4())
    amount = f"{msg.total_inr / config.INR_PER_USDC:.4f}"
    _save(
        ctx,
        msg.request_id,
        {
            "status": "awaiting_payment",
            "reference": reference,
            "user": msg.user_address,
            "order_json": msg.order_json,
            "total_inr": msg.total_inr,
        },
    )
    ctx.storage.set(f"ref:{reference}", msg.request_id)
    ctx.storage.set(f"user:{msg.user_address}", msg.request_id)
    try:
        await ctx.send(
            msg.user_address,
            RequestPayment(
                accepted_funds=[
                    Funds(currency=config.PAYMENT_CURRENCY, amount=amount, payment_method=config.PAYMENT_METHOD)
                ],
                recipient=str(ctx.agent.address),
                deadline_seconds=300,
                reference=reference,
                description=f"Restock order ₹{msg.total_inr:,.0f}",
                metadata={},
            ),
        )
        text = f"💳 Payment request भेज दी गई: ₹{msg.total_inr:,.0f} (≈ {amount} {config.PAYMENT_CURRENCY})."
        if config.DEMO_MODE:
            text += ' Demo mode: असली payment की जगह "pay" लिखकर test कर सकते हैं।'
        await ctx.send(sender, OrderUpdate(request_id=msg.request_id, status="payment_requested", text=text))
    except Exception as exc:  # noqa: BLE001
        ctx.logger.exception("could not request payment")
        await ctx.send(sender, OrderUpdate(request_id=msg.request_id, status="failed", text=f"Payment request fail: {exc}"))


@payment_proto.on_message(CommitPayment)
async def on_commit(ctx: Context, sender: str, msg: CommitPayment):
    ref = getattr(msg, "reference", None)
    rid = ctx.storage.get(f"ref:{ref}") if ref else None
    rid = rid or ctx.storage.get(f"user:{sender}")
    if not rid:
        ctx.logger.warning("CommitPayment for unknown order")
        return
    tx = str(getattr(msg, "transaction_id", "") or "unknown-tx")
    # TODO (production): verify `tx` on-chain / with Stripe BEFORE completing.
    await ctx.send(sender, CompletePayment(transaction_id=tx))
    await _mark_paid(ctx, rid, tx)


@payment_proto.on_message(RejectPayment)
async def on_reject(ctx: Context, sender: str, msg: RejectPayment):
    rid = ctx.storage.get(f"user:{sender}")
    if rid:
        await ctx.send(MANAGER, OrderUpdate(request_id=rid, status="failed", text="❌ Payment reject हुआ। Order रद्द।"))


@agent.on_message(model=DemoPay)
async def on_demo_pay(ctx: Context, sender: str, msg: DemoPay):
    if config.DEMO_MODE:
        await _mark_paid(ctx, msg.request_id, f"demo-{uuid4().hex[:8]}")


agent.include(payment_proto, publish_manifest=True)

if __name__ == "__main__":
    agent.run()
