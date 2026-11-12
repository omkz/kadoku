# AG Studio analytics

The admin Analytics page uses AG Studio with aggregated catalog, inventory, order, and fulfillment data from `GET /api/v1/admin/analytics?days=30` (7/30/90 days). Use **Edit layout** to rearrange widgets and **Reset layout** to restore defaults. AG Studio requires an appropriate production licence.

## AI Analyst

AG Studio AI Analyst creates dashboard charts from natural-language prompts through a server-side LiteLLM adapter. Set these in `apps/api/.env`:

```dotenv
# Gift Concierge
AI_MODEL=gemini/gemini-2.5-flash
GEMINI_API_KEY=your-Gemini-key

# Admin AI Analyst
STUDIO_AGENT_ENABLED=true
STUDIO_AGENT_MODEL=nebius/zai-org/GLM-5.3-Flash
NEBIUS_API_KEY=your-Nebius-key
STUDIO_AGENT_MIN_INTERVAL_SECONDS=0
```

Restart FastAPI, then open **/admin → Analytics → Edit layout → AI chat** and try `Chart paid gift categories`.

`AI_MODEL` and `STUDIO_AGENT_MODEL` are independent; the admin model falls back to `AI_MODEL` when unset. The admin agent also supports Gemini or Groq models that provide tool calling. For low Gemini RPM limits, set `STUDIO_AGENT_MIN_INTERVAL_SECONDS=15` (per worker; not a daily-quota fix).

Provider keys remain server-side. Nebius requests use `https://api.tokenfactory.nebius.com/v1` and may consume credits.

## Troubleshooting

```bash
cd apps/api
uv run python -m app.studio_diagnostics
```

Runs two small live calls (text and tool use). If text fails, check provider credentials, access, and quota. If only tools fail, check function-calling support. If both pass, start a fresh Studio chat and inspect tool-call history.

The agent can update dashboard widgets, not PayPal payments or order fulfillment. It operates on aggregated data; the route requires admin authentication. Production still needs persistent rate limits, spending controls, and licence review.
