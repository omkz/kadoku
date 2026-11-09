"""Sandbox-only PayPal Orders v2 with explicit buyer redirect and server capture."""
from __future__ import annotations
import httpx
from fastapi import HTTPException
from app.core.config import get_settings


class PayPalClient:
    def __init__(self):
        settings = get_settings()
        if settings.paypal_mode != "sandbox":
            raise HTTPException(503, "Live payments are disabled until shipping, tax, and fulfillment are implemented")
        if not settings.paypal_client_id or not settings.paypal_client_secret:
            raise HTTPException(503, "PayPal Sandbox is not configured")
        self.settings = settings
        self.base = "https://api-m.sandbox.paypal.com"

    async def _token(self, client: httpx.AsyncClient) -> str:
        r = await client.post(
            self.base + "/v1/oauth2/token", data={"grant_type": "client_credentials"},
            auth=(self.settings.paypal_client_id, self.settings.paypal_client_secret),
        )
        r.raise_for_status()
        return r.json()["access_token"]

    async def _post(self, path: str, payload: dict, request_id: str | None = None) -> dict:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                token = await self._token(client)
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                if request_id:
                    headers["PayPal-Request-Id"] = request_id
                r = await client.post(self.base + path, json=payload, headers=headers)
                r.raise_for_status()
                return r.json()
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise HTTPException(502, "PayPal Sandbox request failed") from exc

    async def create_order(self, local_id: str, amount_minor: int) -> dict:
        url = self.settings.frontend_url.rstrip("/")
        return await self._post("/v2/checkout/orders", {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": local_id,
                "custom_id": local_id,
                "amount": {"currency_code": "USD", "value": f"{amount_minor/100:.2f}"},
            }],
            "payment_source": {"paypal": {"experience_context": {
                "return_url": f"{url}/checkout/return?order_id={local_id}",
                "cancel_url": f"{url}/?payment=cancelled",
                "user_action": "PAY_NOW", "shipping_preference": "NO_SHIPPING",
            }}},
        }, request_id="create-"+local_id)

    async def capture_order(self, paypal_id: str, local_id: str) -> dict:
        return await self._post(f"/v2/checkout/orders/{paypal_id}/capture", {}, request_id="capture-"+local_id)

    async def verify_webhook(self, headers: dict, event: dict) -> bool:
        if not self.settings.paypal_webhook_id:
            raise HTTPException(503, "PayPal webhook ID is not configured")
        body = {
            "auth_algo": headers.get("paypal-auth-algo"),
            "cert_url": headers.get("paypal-cert-url"),
            "transmission_id": headers.get("paypal-transmission-id"),
            "transmission_sig": headers.get("paypal-transmission-sig"),
            "transmission_time": headers.get("paypal-transmission-time"),
            "webhook_id": self.settings.paypal_webhook_id,
            "webhook_event": event,
        }
        result = await self._post("/v1/notifications/verify-webhook-signature", body)
        return result.get("verification_status") == "SUCCESS"
