"""Planner agent: decides HOW MUCH to order (sales history + festival boost)."""
from uagents import Agent, Context

import config
from logic import compute_needs, load_json
from models import PlanRequest, PlanResponse

agent = Agent(
    name="restock-planner",
    seed=config.seed_for("planner"),
    port=config.PORTS["planner"],
    mailbox=True,
)


@agent.on_event("startup")
async def hello(ctx: Context):
    ctx.logger.info(f"Planner address: {ctx.agent.address}")


@agent.on_message(model=PlanRequest)
async def on_plan(ctx: Context, sender: str, msg: PlanRequest):
    try:
        sales = load_json(config.DATA_DIR / "sales_history.json")
        needs, units, note = compute_needs(sales)
        note = f"{sales.get('shop_name', 'दुकान')}|{note}"  # manager splits on '|'
        await ctx.send(sender, PlanResponse(request_id=msg.request_id, needs=needs, units=units, note=note))
    except Exception as exc:  # never crash - report the error instead
        ctx.logger.exception("planner failed")
        await ctx.send(sender, PlanResponse(request_id=msg.request_id, error=str(exc)))


if __name__ == "__main__":
    agent.run()
