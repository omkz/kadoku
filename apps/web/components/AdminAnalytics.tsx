"use client";

import {useCallback, useEffect, useMemo, useState} from "react";
import {AgStudio} from "ag-studio-react";
import {
  type AgDataSourcesDefinition,
  type AgReportState,
  type AgStudioStateUpdatedEvent,
  studioTheme,
} from "ag-studio";
import {api, dollars} from "@/lib/api";

type Days = 7 | 30 | 90;
type Summary = {
  catalog_products:number;
  active_products:number;
  orders:number;
  paid_orders:number;
  awaiting_fulfillment:number;
  sandbox_captured_minor:number;
};
type AnalyticsPayload = {
  days:number;
  currency:"USD";
  environment:"sandbox";
  generated_at:string;
  summary:Summary;
  catalog:{
    product_id:string; product_name:string; category:string; sku:string|null;
    stock:number; active:boolean; price_usd:number; demo_only:boolean;
  }[];
  product_performance:{
    product_id:string; product_name:string; category:string;
    orders:number; paid_orders:number; approval_pending:number;
    cancelled:number; sandbox_captured_usd:number;
  }[];
  daily_orders:{
    day:string; orders:number; paid_orders:number; sandbox_captured_usd:number;
  }[];
  payment_statuses:{
    payment_status:string; orders:number; sandbox_captured_usd:number;
  }[];
  fulfillment_statuses:{fulfillment_status:string;paid_orders:number}[];
};

const STORAGE_KEY = "kadoku-admin-ag-studio-layout-v1";

/** Studio's documented pre-built report state. No fake values or placeholder rows. */
const DEFAULT_REPORT:AgReportState = {
  pages:[{
    id:"commerce",
    widgets:{
      "product-performance":{
        type:"column-chart-grouped",
        dataMapping:{
          categoryKey:[{id:"product_performance.product_name"}],
          valueKey:[
            {id:"product_performance.paid_orders",aggregation:"sum"},
            {id:"product_performance.orders",aggregation:"sum"},
          ],
        },
        format:{title:{enabled:true,text:"Gift performance · paid vs total orders"}},
      },
      "daily-payments":{
        type:"column-chart-grouped",
        dataMapping:{
          categoryKey:[{id:"daily_orders.day"}],
          valueKey:[
            {id:"daily_orders.paid_orders",aggregation:"sum"},
            {id:"daily_orders.orders",aggregation:"sum"},
          ],
        },
        format:{title:{enabled:true,text:"Daily checkout activity"}},
      },
      "payment-status":{
        type:"bar-chart-grouped",
        dataMapping:{
          categoryKey:[{id:"payment_statuses.payment_status"}],
          valueKey:[{id:"payment_statuses.orders",aggregation:"sum"}],
        },
        format:{title:{enabled:true,text:"Payment statuses · Sandbox"}},
      },
      "catalog-stock":{
        type:"grid",
        dataMapping:{
          cols:[
            {id:"catalog.product_name"},
            {id:"catalog.category"},
            {id:"catalog.sku"},
            {id:"catalog.price_usd"},
            {id:"catalog.stock"},
            {id:"catalog.active"},
          ],
        },
        format:{title:{enabled:true,text:"Catalog & available stock"}},
      },
    },
    widgetLayout:{
      "product-performance":{xTrack:0,yTrack:0,xSpan:12,ySpan:18},
      "daily-payments":{xTrack:12,yTrack:0,xSpan:12,ySpan:18},
      "payment-status":{xTrack:0,yTrack:18,xSpan:9,ySpan:17},
      "catalog-stock":{xTrack:9,yTrack:18,xSpan:15,ySpan:17},
    },
  }],
  selectedPageId:"commerce",
  panels:{filters:{collapsed:true},data:{collapsed:true}},
};

const KADOKU_THEME = studioTheme.withParams({
  backgroundColor:"#FFF9EB",
  foregroundColor:"#352D27",
  accentColor:"#68745C",
  browserColorScheme:"light",
});

function validStoredState(value:unknown):value is AgReportState {
  if (!value || typeof value!=="object") return false;
  const candidate=value as {pages?:unknown;selectedPageId?:unknown};
  return Array.isArray(candidate.pages) && candidate.pages.length>0
    && candidate.pages.length<=20 && typeof candidate.selectedPageId==="string";
}

export default function AdminAnalytics() {
  const [remountKey,setRemountKey]=useState(0);
  const [days,setDays]=useState<Days>(30);
  const [refreshKey,setRefreshKey]=useState(0);
  const [report,setReport]=useState<AnalyticsPayload|null>(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [mode,setMode]=useState<"view"|"edit">("view");
  const [initialState,setInitialState]=useState<AgReportState>(DEFAULT_REPORT);
  const [stateReady,setStateReady]=useState(false);
  const [layoutNotice,setLayoutNotice]=useState("");

  // Saved layouts contain only chart/widget state. Data remains in the
  // admin-protected API and is not persisted in browser storage.
  useEffect(()=>{
    try {
      const saved=window.localStorage.getItem(STORAGE_KEY);
      if(saved){
        const parsed:unknown=JSON.parse(saved);
        if(validStoredState(parsed)) setInitialState(parsed);
      }
    } catch {
      // Browser storage may be disabled; the default report remains usable.
    }
    setStateReady(true);
  },[]);

  useEffect(()=>{
    let cancelled=false;
    setLoading(true);
    setError("");
    api<AnalyticsPayload>("/admin/analytics?days="+days).then(response=>{
      if(!cancelled) setReport(response);
    }).catch(reason=>{
      if(!cancelled) setError(reason instanceof Error?reason.message:"Analytics could not load.");
    }).finally(()=>{
      if(!cancelled) setLoading(false);
    });
    return ()=>{cancelled=true;};
  },[days,refreshKey]);

  const data=useMemo<AgDataSourcesDefinition|undefined>(()=>{
    if(!report) return undefined;
    return {sources:[
      {id:"catalog",data:report.catalog},
      {id:"product_performance",data:report.product_performance},
      {id:"daily_orders",data:report.daily_orders},
      {id:"payment_statuses",data:report.payment_statuses},
      {id:"fulfillment_statuses",data:report.fulfillment_statuses},
    ]};
  },[report]);

  const onStateUpdated=useCallback((event:AgStudioStateUpdatedEvent)=>{
    if(!event.durable) return;
    try {
      window.localStorage.setItem(STORAGE_KEY,JSON.stringify(event.state));
      setLayoutNotice("Layout saved in this browser");
    } catch {
      setLayoutNotice("Browser storage unavailable; layout is not persisted");
    }
  },[]);

  const restoreDefault=useCallback(()=>{
    try {window.localStorage.removeItem(STORAGE_KEY);} catch {}
    setInitialState(DEFAULT_REPORT);
    setRemountKey(index=>index+1);
    setLayoutNotice("Default layout restored");
  },[]);

  const summary=report?.summary;
  const paymentRate=summary && summary.orders>0
    ? Math.round(summary.paid_orders/summary.orders*100):null;

  return <section className="admin-analytics">
    <div className="admin-section-heading">
      <div>
        <p className="admin-overline">KADOKU COMMERCE INTELLIGENCE</p>
        <h1>Analytics</h1>
        <p>Explore gift catalog activity, PayPal Sandbox payments and fulfillment with AG Studio.</p>
      </div>
      <button type="button" className="admin-outline" disabled={loading}
        onClick={()=>setRefreshKey(key=>key+1)}>↻ Refresh data</button>
    </div>

    <div className="admin-analytics-toolbar">
      <label className="admin-small-label" htmlFor="analytics-days">Reporting window</label>
      <select id="analytics-days" value={days} onChange={event=>setDays(Number(event.target.value) as Days)}>
        <option value={7}>Last 7 days</option>
        <option value={30}>Last 30 days</option>
        <option value={90}>Last 90 days</option>
      </select>
      <span className="admin-env">PayPal Sandbox · USD</span>
      {report && <small>As of {new Date(report.generated_at).toLocaleString()}</small>}
    </div>
    {error && <div className="admin-error" role="alert">{error} <button type="button" onClick={()=>setRefreshKey(key=>key+1)}>Retry</button></div>}
    {loading && <p className="admin-loading" role="status">Loading analytics data…</p>}

    {summary && <div className="admin-analytics-stats">
      <div className="admin-stat"><span>Catalog products</span><strong>{summary.catalog_products}</strong><small>{summary.active_products} published</small></div>
      <div className="admin-stat"><span>Checkout orders</span><strong>{summary.orders}</strong><small>{paymentRate===null?"No orders in period":paymentRate+"% paid"}</small></div>
      <div className="admin-stat"><span>Paid · awaiting processing</span><strong>{summary.awaiting_fulfillment}</strong><small>Internal fulfillment tracker</small></div>
      <div className="admin-stat"><span>Sandbox captured</span><strong>{dollars(summary.sandbox_captured_minor)}</strong><small>Test payments, not revenue</small></div>
    </div>}

    {summary && <div className="admin-journey">
      <div><h2>Payment & fulfillment pulse</h2><p>Verified order states, not a recommendation-to-purchase conversion funnel.</p></div>
      <div className="admin-journey-stages">
        <div><span>Checkout orders</span><strong>{summary.orders}</strong></div>
        <span aria-hidden="true">→</span>
        <div><span>Captured</span><strong>{summary.paid_orders}</strong></div>
        <span aria-hidden="true">→</span>
        <div><span>Awaiting processing</span><strong>{summary.awaiting_fulfillment}</strong></div>
      </div>
    </div>}

    {stateReady && data && <div className="admin-studio-wrap">
      <div className="admin-studio-controls">
        <div><strong>AG Studio report builder</strong><small>Charts, grids, cross-filtering and custom layouts · stored in this browser</small></div>
        <div className="admin-studio-buttons">
          <button type="button" className={mode==="view"?"admin-primary":"admin-outline"}
            onClick={()=>setMode("view")}>View</button>
          <button type="button" className={mode==="edit"?"admin-primary":"admin-outline"}
            onClick={()=>setMode("edit")}>Edit layout</button>
          <button type="button" className="admin-outline"
            onClick={restoreDefault}>Reset layout</button>
        </div>
      </div>
      {layoutNotice && <p className="admin-layout-notice" role="status">{layoutNotice}</p>}
      <div className="admin-studio-canvas" data-ag-theme-mode="light">
        <AgStudio key={remountKey} data={data} mode={mode}
          initialState={initialState} theme={KADOKU_THEME}
          onStateUpdated={onStateUpdated}/>
      </div>
      <p className="admin-disclaimer">This report uses aggregated internal test-order data. No customer identities, delivery addresses, PayPal IDs or secrets are sent to the visualization engine. Recommendation exposure and conversion events are not yet tracked.</p>
    </div>}
  </section>;
}
