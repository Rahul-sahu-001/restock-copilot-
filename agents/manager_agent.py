"""Manager agent: the ONLY agent the user talks to (via ASI:One / Agentverse chat).
It speaks Chat Protocol and coordinates planner -> price -> order agents."""
import json
import time
from datetime import datetime, timezone
from uuid import uuid4

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSession,
    TextContent,
    chat_protocol_spec,
)

import config
from logic import best_deals, detect_intent, format_summary
from models import DemoPay, OrderRequest, OrderUpdate, PlanRequest, PlanResponse, PriceRequest, PriceResponse

agent = Agent(
    name="restock-copilot",
    seed=config.seed_for("manager"),
    port=config.PORTS["manager"],
    mailbox=True,
    publish_agent_details=True,
)
chat_proto = Protocol(spec=chat_protocol_spec)

PLANNER = config.address_for("planner")
PRICE = config.address_for("price")
ORDER = config.address_for("order")


# ------------------------------------------------------------ small helpers
def _save(ctx: Context, rid: str, data: dict):
    ctx.storage.set(f"req:{rid}", json.dumps(data))


def _load(ctx: Context, rid: str):
    raw = ctx.storage.get(f"req:{rid}")
    return json.loads(raw) if raw else None


def _latest_for(ctx: Context, user: str):
    rid = ctx.storage.get(f"latest:{user}")
    return (rid, _load(ctx, rid)) if rid else (None, None)


def _track(ctx: Context, rid: str):
    ids = json.loads(ctx.storage.get("active") or "[]")
    ids.append(rid)
    ctx.storage.set("active", json.dumps(ids[-50:]))


async def say(ctx: Context, to: str, text: str, end: bool = False):
    content = [TextContent(type="text", text=text)]
    if end:
        content.append(EndSession(type="end-session"))
    await ctx.send(to, ChatMessage(timestamp=datetime.now(timezone.utc), msg_id=uuid4(), content=content))


async def fail(ctx: Context, rid: str, req: dict, why: str):
    req["stage"] = "failed"
    _save(ctx, rid, req)
    await say(ctx, req["user"], f"⚠️ {why}\nकृपया थोड़ी देर बाद दोबारा कोशिश करें।")


# -------------------------------------------------------------- chat (user)
@chat_proto.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id))
    text = " ".join(c.text for c in msg.content if isinstance(c, TextContent)).strip()
    if not text:
        return

    rid, req = _latest_for(ctx, sender)
    stage = req["stage"] if req else None
    intent = detect_intent(text, stage)

    if intent == "cancel":
        req["stage"] = "cancelled"
        _save(ctx, rid, req)
        await say(ctx, sender, "ठीक है, order रद्द कर दिया। नया plan चाहिए तो पूछिए।")

    elif intent == "confirm":
        req.update(stage="ordering", started=time.time())
        _save(ctx, rid, req)
        await say(ctx, sender, "👍 Order तैयार कर रहा हूँ और payment request भेज रहा हूँ…")
        await ctx.send(
            ORDER,
            OrderRequest(request_id=rid, user_address=sender, order_json=json.dumps(req["lines"]), total_inr=req["total"]),
        )

    elif intent == "pay":
        await say(ctx, sender, "(Demo) payment simulate कर रहा हूँ…")
        await ctx.send(ORDER, DemoPay(request_id=rid))

    else:  # restock
        rid = str(uuid4())
        req = {"user": sender, "stage": "planning", "started": time.time()}
        _save(ctx, rid, req)
        ctx.storage.set(f"latest:{sender}", rid)
        _track(ctx, rid)
        await say(ctx, sender, "🔍 आपकी बिक्री और रेट देख रहा हूँ — मेरे planner और price agents काम पर हैं…")
        await ctx.send(PLANNER, PlanRequest(request_id=rid))


@chat_proto.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


# ------------------------------------------------------ replies from workers
@agent.on_message(model=PlanResponse)
async def on_plan(ctx: Context, sender: str, msg: PlanResponse):
    req = _load(ctx, msg.request_id)
    if not req or req["stage"] != "planning":
        return
    if msg.error:
        return await fail(ctx, msg.request_id, req, f"Planner agent में दिक्कत: {msg.error}")
    shop, _, note = msg.note.partition("|")
    items = [i for i, q in msg.needs.items() if q > 0]
    if not items:
        req["stage"] = "done"
        _save(ctx, msg.request_id, req)
        return await say(ctx, req["user"], "✅ अभी आपका stock पर्याप्त है, कुछ मँगाने की ज़रूरत नहीं।")
    req.update(stage="pricing", needs=msg.needs, units=msg.units, shop=shop, note=note, started=time.time())
    _save(ctx, msg.request_id, req)
    await ctx.send(PRICE, PriceRequest(request_id=msg.request_id, items=items))


@agent.on_message(model=PriceResponse)
async def on_price(ctx: Context, sender: str, msg: PriceResponse):
    req = _load(ctx, msg.request_id)
    if not req or req["stage"] != "pricing":
        return
    lines, total, missing = best_deals(req["needs"], req["units"], msg.prices)
    if not lines:
        return await fail(ctx, msg.request_id, req, "किसी भी item का रेट नहीं मिला।")
    req.update(stage="await_confirm", lines=lines, total=total)
    _save(ctx, msg.request_id, req)
    await say(ctx, req["user"], format_summary(req.get("shop", "दुकान"), lines, total, missing, msg.errors, req.get("note", "")))


@agent.on_message(model=OrderUpdate)
async def on_order_update(ctx: Context, sender: str, msg: OrderUpdate):
    req = _load(ctx, msg.request_id)
    if not req:
        return
    if msg.status == "payment_requested":
        req["stage"] = "awaiting_payment"
        _save(ctx, msg.request_id, req)
        await say(ctx, req["user"], msg.text)
    elif msg.status == "paid":
        req["stage"] = "done"
        _save(ctx, msg.request_id, req)
        await say(ctx, req["user"], msg.text, end=True)
    else:
        await fail(ctx, msg.request_id, req, msg.text or "Order में दिक्कत आई।")


# ------------------------------------------------- timeout / error handling
@agent.on_interval(period=5.0)
async def sweep_timeouts(ctx: Context):
    for rid in json.loads(ctx.storage.get("active") or "[]"):
        req = _load(ctx, rid)
        if req and req["stage"] in ("planning", "pricing", "ordering"):
            if time.time() - req["started"] > config.TIMEOUT_SECONDS:
                await fail(ctx, rid, req, f"'{req['stage']}' वाले agent ने समय पर जवाब नहीं दिया।")


@agent.on_event("startup")
async def hello(ctx: Context):
    ctx.logger.info(f"Manager address: {ctx.agent.address}")


agent.include(chat_proto, publish_manifest=True)

if __name__ == "__main__":
    agent.run()
