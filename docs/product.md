# Kadoku — Product Requirements v0.3

**Positioning:** Your AI Gift Concierge. A conversation-first gift-shopping experience powered by a shop-owned curated catalog, built for the long term; PayPal AI Hackathon is an early demonstration opportunity.

## User problem

People struggle to decide what gift to buy, spend too much time browsing, and sometimes forget important birthdays or other occasions.

## Product experience

1. The homepage starts with a text/voice request, not a catalog.
2. Kadoku understands recipient interests, occasion, constraints, and budget.
3. It selects **up to three** suitable gifts from the in-house catalog, with **one top pick**.
4. Gifts appear in a horizontal carousel immediately below the chat conversation.
5. The customer selects an item and can add a personal note.
6. The customer explicitly approves payment using PayPal.
7. Signed-in customers can save recipient profiles and birthdays for future gifting.
8. Proactive reminders, richer memories, and full gift history are planned follow-on features.

## Commerce boundaries

Products are sourced from Kadoku's own curated catalog. No Channel3 dependency is required. Affiliate products may be considered later, but third-party catalog links do **not** imply Kadoku can process the retailer's payment or fulfill the order.

## Technical decisions

- Next.js (TypeScript) frontend, mobile-first PWA.
- FastAPI (Python) backend, traditional four-layer architecture.
- PostgreSQL + SQLAlchemy + Alembic.
- Better Auth with optional Google OAuth, signed JWKS-verifiable JWT for Python API.
- LiteLLM is optional/configurable; grounded in-house product ranking remains independent of the LLM.
- One free recommendation request for each guest per day as a starting quota policy; authenticated users have a larger daily quota.
- PayPal Orders API for checkout, with server-side payment verification and webhook verification.
- Product images and supplier fulfillment need genuine data before launch.

## Quality objectives

- No invented prices or products in recommendations.
- No unavailable/out-of-budget items in recommendations.
- Minimal number of questions before showing products.
- Sensitive recipient profiles are accessible only to the owner.
- No payment is captured without buyer approval.
- All payments are sandbox-only until real stock, taxes, shipping, returns, privacy, and compliance are in place.

## MVP acceptance

- Start in guest mode without registering.
- A guest receives at most three recommendations based on a text query.
- A second guest recommendation hits the configured server quota.
- A logged-in user can save a recipient and recurring birthday.
- PayPal test buyer can approve and capture a sandbox order when credentials are configured.
- API regression tests pass and the frontend can be built after its dependencies are installed.
