"use client";
import {useEffect, useState} from "react";
import Link from "next/link";
import {api} from "@/lib/api";

export default function PaymentReturn() {
  const [status, setStatus] = useState<"loading"|"paid"|"error">("loading");
  const [detail, setDetail] = useState("Confirming your PayPal Sandbox payment…");
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const order_id = params.get("order_id");
    const paypal_order_id = params.get("token");
    if (!order_id || !paypal_order_id) {setStatus("error");setDetail("Payment details are missing.");return;}
    void api<{status:string}>("/checkout/paypal/capture","POST",{order_id,paypal_order_id})
      .then(result=>{setStatus("paid");setDetail(result.status==="paid"?"Your sandbox payment was captured. This was a demo transaction—no real gift will be shipped.":"Payment status unknown.");})
      .catch(err=>{setStatus("error");setDetail(err instanceof Error?err.message:"We could not confirm the payment.");});
  }, []);
  return <main className="return-screen"><div>{status==="loading"?"⌛":status==="paid"?"✓":"!"}</div>
    <h1>{status==="loading"?"Confirming payment":status==="paid"?"Sandbox payment complete":"Payment not confirmed"}</h1>
    <p>{detail}</p><Link href="/">Back to Kadoku</Link></main>;
}
