# AG Studio Analytics + AI Analyst — acceptance checklist

Scope: PR #25 (`feature/ag-studio-analytics-v1`). The shopper storefront and
existing admin CRUD workflows are outside this feature's change scope.

## Evidence already established

| Test | Evidence / status |
| --- | --- |
| Analytics workspace fits better on desktop | **User-confirmed** after sidebar/full-width layout change |
| Gemini credentials and basic tool calling | **User-confirmed** via `app.studio_diagnostics`: both probes OK |
| AI creates a real chart | **User-confirmed**: “Available Stock by Gift Category” appears in AG Studio |
| AI-created chart survives browser refresh | **User-confirmed** on the same browser |
| Admin authentication + read-only aggregate analytics | Automated API regression suite |
| LiteLLM function-tools workaround | Offline SDK compatibility test; no real provider key in CI |
| Web TypeScript and production build | GitHub workflow (see PR checks for the latest commit) |

The user confirmed **widget creation and persistence**, not yet numerical accuracy
for every category or cross-browser persistence.

## Manual checks before approving merge

1. **Access control**: In a signed-out browser, `/admin` must not show analytics.
   A logged-in non-admin must receive a forbidden response for
   `GET /api/v1/admin/analytics` and `GET /api/v1/admin/analytics/agent/status`.
2. **Date windows**: Switch 7 → 30 → 90 days. Product catalog counts stay
   consistent; the displayed order/activity chart changes only according to
   existing Sandbox records. No invented or live-payment figures.
3. **AI data accuracy**: Compare “Available Stock by Gift Category” against the
   corresponding category + stock aggregations from the Catalog grid. Note that
   `catalog` currently includes *all* products, including inactive/demo entries;
   this is total catalog stock, not necessarily purchasable inventory.
4. **Multi-turn editing**: Start a new AI conversation, request a chart, then ask
   “Change this chart to a horizontal bar chart.” Confirm the existing widget
   changes rather than duplicating or merely claiming success.
5. **Persistence**: Refresh the page. Confirm AI-created widgets stay in place.
   Change reporting window and refresh again; layout remains, while fresh
   aggregate data comes from the server.
6. **Reset safety**: Click Reset layout; cancel the confirmation and verify
   all AI widgets remain. Then (only on a disposable test layout) confirm reset
   and verify default widgets appear.
7. **Responsive and layout**: Collapse/expand sidebar on desktop; check scrolling
   and chart readability at typical laptop and mobile widths. Ensure controls
   remain reachable without a page-level horizontal overflow.
8. **Provider failures**: If Gemini quota is exhausted, verify an actionable
   message appears without keys, addresses or model response bodies in logs.

## Explicitly deferred (not part of PR #25)

- Report layout is stored in **this browser's localStorage**, not synchronized
  across devices and not scoped per admin account on a shared browser.
- Production needs a distributed AI rate/budget limiter and cost monitoring;
  the current 90 calls/hour/admin budget is **per backend process**.
- Recommendation impressions and a true recommendation-to-purchase conversion
  funnel are not recorded. Do not label Sandbox captured payments as revenue.
- Confirm AG Studio licensing for the intended production deployment.
- Optional UX polish: remove stray Markdown labels (for example `svg`) from
  AI-written chart descriptions; not yet confirmed as a widget-title problem.

## Merge gate

Keep PR #25 **draft**. Do not merge until the owner explicitly approves after
the outstanding manual checks and the latest CI checks are green.
