# Admin analytics and AI Analyst

Kadoku uses [AG Studio](https://www.ag-grid.com/) inside the authenticated `/admin → Analytics` page. The API provides aggregated Sandbox order, catalog, stock, and fulfillment data from `GET /api/v1/admin/analytics?days=30` (7, 30, or 90 days).

The dashboard includes charts, a catalog/stock grid, and a Checkout Health widget. Use **Edit layout** to rearrange widgets; **Reset layout** restores defaults. Layouts are saved in the browser, not the database.

AG Studio requires an appropriate licence for production use.

## AI Analyst setup

The AI Analyst uses AG Studio's agent tools and a server-side LiteLLM adapter. It can add charts through natural-language requests. The shopper model (`AI_MODEL`) is independent of the admin model (`STUDIO_AGENT_MODEL`).

For Gemini gift discovery and Nebius-backed admin analytics, add the following values to **`apps/api/.env`**:

```dotenv
AI_MODEL=gemini/gemini-2.5-flash
GEMINI_API_KEY=your-Gemini-key

STUDIO_AGENT_ENABLED=true
STUDIO_AGENT_MODEL=nebius/zai-org/GLM-5.3-Flash
NEBIUS_API_KEY=your-Nebius-Token-Factory-key
STUDIO_AGENT_MIN_INTERVAL_SECONDS=0
```

Restart FastAPI, sign in as an admin, open Analytics → Edit layout → AI chat, and ask **"Chart paid gift categories"**.

Use model IDs available to your provider account. Nebius Token Factory traffic is routed to `https://api.tokenfactory.nebius.com/v1`. Provider usage can consume paid credits. Never expose keys in the frontend or logs.

Other supported options:
- **Gemini admin model:** `STUDIO_AGENT_MODEL=gemini/gemini-2.5-flash`; reuses the Gemini key. For a 5 RPM quota, `STUDIO_AGENT_MIN_INTERVAL_SECONDS=15` spaces requests from one API worker, but does not increase daily quota.
- **Groq:** `STUDIO_AGENT_MODEL=groq/openai/gpt-oss-120b` with `GROQ_API_KEY`. Large AG Studio tool schemas may exceed available token quotas.
- **Fallback:** If `STUDIO_AGENT_MODEL` is empty, the admin agent uses `AI_MODEL`.

AG Studio can create or update dashboard widgets through its browser tool calls; the agent cannot charge PayPal or change catalog/fulfillment records.

## Diagnostics

```bash
cd apps/api
uv run python -m app.studio_diagnostics
```

This performs two small real provider requests (text and tool calling) and consumes provider quota. It reports status and exception classes without printing keys.

- **Text fails:** Check network, key, model access, quota, and LiteLLM.
- **Text passes, tools fail:** Check function-calling support and schema compatibility.
- **Both pass, Studio fails:** Inspect browser tool-call history and the size of AG Studio's tool schemas. Start a new AI chat if an old conversation has invalid tool calls.

Do not enable full prompt/response logging with personal data or credentials. The Nebius chart workflow was demonstrated manually, while CI uses mocked provider calls.

## Boundaries

The dashboard uses aggregated test data, not real sales. Admin JWT authorization and an opt-in flag protect the AI route. The in-process limit of 90 turns/hour/admin is only a development safeguard; production requires persistent rate limits, model budgets, provider access policies, and licence review.

The analytics dataset excludes customer account data, addresses, shipping records, raw payments, and PayPal identifiers.
