"use client";
import {useEffect, useRef, useState} from "react";
import Link from "next/link";
import {api} from "@/lib/api";

type Result = {status: string; order_id: string};

export default function PaymentReturn() {
  const [status, setStatus] = useState<"loading"|"paid"|"error">("loading");
  const [detail, setDetail] = useState("Confirming your PayPal Sandbox payment…");
  const [retry, setRetry] = useState(0);
  // React Strict Mode replays effects in development. Never send concurrent
  // capture requests just because the return component mounted twice.
  const inFlight = useRef(false);

  useEffect(() => {
    if (inFlight.current) return;
    const params = new URLSearchParams(window.location.search);
    const orderId = params.get("order_id");
    const paypalOrderId = params.get("token");
    if (!orderId || !paypalOrderId) {
      setStatus("error");
      setDetail("Payment reference is missing. The payment has not been confirmed.");
      return;
    }

    inFlight.current = true;
    setStatus("loading");
    setDetail("Checking your PayPal Sandbox payment…");
    void api<Result>("/checkout/paypal/capture", "POST", {
      order_id: orderId,
      paypal_order_id: paypalOrderId,
    })
      .then(result => {
        if (result.status !== "paid" || result.order_id !== orderId) {
          throw new Error("PayPal did not confirm the expected order.");
        }
        setStatus("paid");
        setDetail("Your PayPal Sandbox payment was captured. This was a test transaction; no gift will be shipped.");
      })
      .catch(err => {
        setStatus("error");
        setDetail(err instanceof Error ? err.message : "We could not confirm the payment. Try again.");
        inFlight.current = false;
      });
  }, [retry]);

  return <main className="return-screen" aria-live="polite">
    <div>{status==="loading" ? "⌛" : status==="paid" ? "✓" : "!"}</div>
    <h1>{status==="loading" ? "Confirming payment" : status==="paid" ? "Sandbox payment complete" : "Payment not confirmed"}</h1>
    <p>{detail}</p>
    {status==="error" && <button className="primary-action" onClick={()=>setRetry(value=>value+1)}>Try confirming again</button>}
    <Link href="/">Back to Kadoku</Link>
  </main>;
}
