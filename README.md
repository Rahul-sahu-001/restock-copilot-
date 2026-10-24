# Restock Copilot 🛒

AI agent team that helps small shopkeepers (kirana stores) decide **what to order, from whom, and at what price** — then places the order and collects payment. Chat with it on ASI:One.

## Agents
| Agent | Job |
|---|---|
| **restock-copilot (Manager)** | Talks to the user (Chat Protocol), coordinates the others |
| **restock-planner** | Decides how much to order (sales history + festival demand) |
| **restock-price** | Fetches supplier prices (live API with retries, cached fallback) |
| **restock-order** | Creates the order and requests payment (Agent Payment Protocol) |

## Try asking
- "इस हफ़्ते क्या मँगाऊँ?"
- then "order" to confirm, "cancel" to cancel

## Features
- Multi-agent collaboration over uAgents messages
- Payment Protocol (seller side) with a commission/subscription monetization model
- Reliability: retries, cached-price fallback, timeouts, graceful error messages
- Runs on Agentverse via mailbox, discoverable through ASI:One

## Run locally
```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # then edit SEED_PREFIX
python run_all.py
```
Connect each agent's mailbox on Agentverse using the Inspector link printed in its log.
