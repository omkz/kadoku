import Link from "next/link";

export default function PaymentCancelled() {
  return <main className="return-screen">
    <div aria-hidden="true">↩</div>
    <h1>Checkout cancelled</h1>
    <p>You left PayPal before completing checkout. Kadoku has not confirmed any payment for this order.</p>
    <p>This is a Sandbox demo: no real products will be shipped.</p>
    <Link href="/">Back to Kadoku</Link>
  </main>;
}
