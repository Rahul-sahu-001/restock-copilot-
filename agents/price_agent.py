"""Price agent: fetches supplier prices (live API with retries, cached fallback)."""
from uagents import Agent, Context

import config
from logic import fetch_prices, load_json
from models import PriceRequest, PriceResponse

agent = Agent(
    name="restock-price",
    seed=config.seed_for("price"),
    port=config.PORTS["price"],
    mailbox=True,
)


@agent.on_event("startup")
async def hello(ctx: Context):
    ctx.logger.info(f"Price agent address: {ctx.agent.address}")


@agent.on_message(model=PriceRequest)
async def on_price(ctx: Context, sender: str, msg: PriceRequest):
    try:
        fallback = load_json(config.DATA_DIR / "suppliers.json")
        prices, errors = fetch_prices(
            msg.items,
            fallback,
            api_url=config.PRICE_API_URL or None,
            force_fail=config.DEMO_FAIL_PRICE_API,
        )
        await ctx.send(sender, PriceResponse(request_id=msg.request_id, prices=prices, errors=errors))
    except Exception as exc:  # noqa: BLE001
        ctx.logger.exception("price agent failed")
        await ctx.send(sender, PriceResponse(request_id=msg.request_id, errors=[f"Price agent error: {exc}"]))


if __name__ == "__main__":
    agent.run()
