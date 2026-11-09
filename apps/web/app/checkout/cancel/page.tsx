"use client";
import {useEffect, useRef, useState} from "react";
import Link from "next/link";
import {api} from "@/lib/api";

export default function PaymentCancelled() {
  const [state, setState] = useState<"loading"|"cancelled"|"error">("loading");
  const [message, setMessage] = useState("Recording your cancelled Sandbox checkout…");
  const [retry, setRetry] = useState(0);
  const inFlight = useRef(false);

  useEffect(() => {
    if (inFlight.current) return;
    const orderId = new URLSearchParams(window.location.search).get("order_id");
    if (!orderId) {
      setState("error");
      setMessage("Missing order reference. Check My Orders for the current status.");
      return;
    }
    inFlight.current = true;
    setState("loading");
    void api<{status:string; order_id:string}>(`/orders/${orderId}/cancel`, "POST")
      .then(result => {
        if (result.status !== "cancelled" || result.order_id !== orderId) {
          throw new Error("Could not verify that the checkout was cancelled.");
        }
        setState("cancelled");
        setMessage("Your Sandbox checkout was cancelled. No payment was captured for this order.");
      })
      .catch(error => {
        setState("error");
        setMessage(error instanceof Error ? error.message : "Unable to record the cancellation.");
        inFlight.current = false;
      });
  }, [retry]);

  return <main className="return-screen" aria-live="polite">
    <div aria-hidden="true">{state==="loading" ? "⌛" : state==="cancelled" ? "↩" : "!"}</div>
    <h1>{state==="loading" ? "Updating your order" : state==="cancelled" ? "Checkout cancelled" : "Cancellation not confirmed"}</h1>
    <p>{message}</p>
    <p>This is a PayPal Sandbox demo. No real products will be shipped.</p>
    {state==="error" && <button className="primary-action" onClick={()=>setRetry(value=>value+1)}>Try again</button>}
    <p><Link href="/?view=orders">View My Orders</Link></p>
    <Link href="/">Back to Kadoku</Link>
  </main>;
}
