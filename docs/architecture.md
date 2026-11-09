# Kadoku architecture — v0.1

- **Backend architectural style:** Traditional Layered Architecture, implemented as one deployable FastAPI service. The Next.js web app is separately deployable.
- **Dependency direction:** HTTP routers → application/business services → repositories → SQLAlchemy → PostgreSQL.
- **External integrations:** PayPal client and LiteLLM use their own adapters. Business services do not have direct knowledge of HTTP request state or provider secrets.
- **User identity:** Better Auth session in Next.js → signed JWT via its JWT plugin → FastAPI validates issuer, audience and JWKS public signing key → private recipient queries filter by `user_id`.
- **Guest identity:** Next.js creates an HttpOnly signed guest cookie and FastAPI validates its HMAC before quota attribution. This is product friction control, not a complete bot defense.
- **Gift selection:** LLM or deterministic parser extracts intent; hard stock/budget/exclusion filtering; weighted metadata ranking; category diversity; up to 3 product cards with grounded reasons.
- **PayPal:** Sandbox only. API creates a local order, then PayPal order, redirects the user to approval, and captures after return. Capture payload must be completed with matching price and currency; webhook events are signature-verified and deduplicated. Full reconciliation and refund automation are future work.
- **Database ownership:** SQLAlchemy/Alembic owns application tables; Better Auth manages its own auth tables.

## Known constraints

This is a first working vertical slice, not a deployed production storefront. Products are example fixtures. The AI recommendation engine has no trained ranking model or real-world supplier data. Future birthday reminder notifications are not yet scheduled. Sales tax, delivery/fulfillment, and production payment processing are intentionally out of scope until these are properly implemented.
