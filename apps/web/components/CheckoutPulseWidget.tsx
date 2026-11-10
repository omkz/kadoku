"use client";

/** A Kadoku-specific AG Studio widget; values come from the admin aggregate API.
 * This widget intentionally describes payment/fulfillment status only, not the
 * recommendation funnel (which needs event instrumentation).
 */
export type CheckoutPulseData = {
  orders:number;
  paid_orders:number;
  awaiting_fulfillment:number;
};

type PulseProps = {
  context?: unknown;
};

function asPulse(context:unknown):CheckoutPulseData {
  if (!context || typeof context !== "object") {
    return {orders:0,paid_orders:0,awaiting_fulfillment:0};
  }
  const value=(context as {checkoutPulse?:CheckoutPulseData}).checkoutPulse;
  return value && Number.isFinite(value.orders) && Number.isFinite(value.paid_orders)
    && Number.isFinite(value.awaiting_fulfillment)
    ? value
    : {orders:0,paid_orders:0,awaiting_fulfillment:0};
}

export default function CheckoutPulseWidget({context}:PulseProps) {
  const values=asPulse(context);
  const rows=[
    {label:"Checkout orders",value:values.orders},
    {label:"Captured payments",value:values.paid_orders},
    {label:"Paid · awaiting processing",value:values.awaiting_fulfillment},
  ];
  const maximum=Math.max(1,values.orders);
  return <div className="kadoku-studio-pulse" aria-label="Checkout and fulfillment status">
    <header><strong>Checkout health</strong><span>PayPal Sandbox · test orders</span></header>
    <div className="kadoku-studio-pulse-rows">
      {rows.map((row,index)=><div className="kadoku-studio-pulse-row" key={row.label}>
        <div className="kadoku-studio-pulse-label"><span>{row.label}</span><strong>{row.value}</strong></div>
        <div className="kadoku-studio-pulse-track" role="img"
          aria-label={row.label+": "+row.value}>
          <div className={"kadoku-studio-pulse-fill shade-"+index}
            style={{width:(row.value/maximum*100)+"%"}}/>
        </div>
      </div>)}
    </div>
    <p>Captured is a subset of orders; awaiting processing is a subset of captured. This is not a recommendation conversion funnel.</p>
  </div>;
}
