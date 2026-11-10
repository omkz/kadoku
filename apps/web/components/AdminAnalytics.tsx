"use client";

import {useCallback, useEffect, useMemo, useState} from "react";
import {AgStudio, AgStudioProvider, createWidgets} from "ag-studio-react";
import CheckoutPulseWidget from "./CheckoutPulseWidget";
import {
  AgStudioAiModule,
  createAiHarness,
  type AgAiHarnessSetup,
  type AgAiPromptStarter,
  type AgBaseRegistry,
  type AgBaseWidgetDefinition,
  type AgDataSourcesDefinition,
  type AgFieldDefinition,
  type AgDefaultWidgetDefinition,
  type AgWidgetsConfig,
  type AgReportState,
  type AgStudioStateUpdatedEvent,
  studioTheme,
} from "ag-studio";
import {api, dollars} from "@/lib/api";
import {createKadokuStudioAdapter} from "@/lib/studio-agent-adapter";

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

type CheckoutPulseDef = AgBaseWidgetDefinition<"checkout-pulse", {type:"checkout-pulse";dataMapping:{}}, any, unknown>;
interface KadokuRegistry extends AgBaseRegistry {
  widgets:readonly (AgDefaultWidgetDefinition | CheckoutPulseDef)[];
}

// v2 contained a catalog grid mapping that referenced nullable fields and
// numeric columns without supported aggregations. Migrate the mapping on load.
const STUDIO_PROMPTS:AgAiPromptStarter[] = [
  {
    label:"Chart paid gift categories",
    prompt:"Add a bar chart ranking gift categories by Sandbox paid orders. Use product_performance, group by category and sum paid_orders. All data is test-only.",
  },
  {
    label:"Explore inventory",
    prompt:"Create a chart of total available stock by category from the catalog source.",
  },
  {
    label:"Explain payments",
    prompt:"Explain the payment status breakdown in the current data. These are PayPal Sandbox test orders, not real revenue.",
  },
];
const STUDIO_ADAPTER = createKadokuStudioAdapter();
const STORAGE_KEY = "kadoku-admin-ag-studio-layout-v3";
const PREVIOUS_STORAGE_KEY = "kadoku-admin-ag-studio-layout-v2";

const CATALOG_GRID_COLUMNS = [
  {id:"catalog.product_id"},
  {id:"catalog.product_name"},
  {id:"catalog.category"},
  {id:"catalog.price_usd",aggregation:"avg"},
  {id:"catalog.stock",aggregation:"sum"},
] as const;

const CATALOG_FIELDS:AgFieldDefinition[] = [
  {id:"product_id",name:"Product ID",format:"textFormat",notBlank:true},
  {id:"product_name",name:"Product",format:"textFormat",notBlank:true},
  {id:"category",name:"Category",format:"textFormat"},
  {id:"sku",name:"SKU",format:"textFormat"},
  {id:"price_usd",name:"Price (USD)",format:"currencyFormat"},
  {id:"stock",name:"Available stock",format:"integerFormat"},
  {id:"active",name:"Published",format:"booleanFormat"},
  {id:"demo_only",name:"Demo only",format:"booleanFormat"},
];

/** Studio's documented pre-built report state. No fake values or placeholder rows. */
const DEFAULT_REPORT:AgReportState<KadokuRegistry> = {
  pages:[{
    id:"commerce",
    widgets:{
      "checkout-health":{
        type:"checkout-pulse", dataMapping:{},
      },
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
          cols:[...CATALOG_GRID_COLUMNS],
        },
        format:{title:{enabled:true,text:"Catalog & available stock"}},
      },
    },
    widgetLayout:{
      "checkout-health":{xTrack:0,yTrack:0,xSpan:24,ySpan:14},
      "product-performance":{xTrack:0,yTrack:14,xSpan:12,ySpan:18},
      "daily-payments":{xTrack:12,yTrack:14,xSpan:12,ySpan:18},
      "payment-status":{xTrack:0,yTrack:32,xSpan:9,ySpan:17},
      "catalog-stock":{xTrack:9,yTrack:32,xSpan:15,ySpan:17},
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

function validStoredState(value:unknown):value is AgReportState<KadokuRegistry> {
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
  const [initialState,setInitialState]=useState<AgReportState<KadokuRegistry>>(DEFAULT_REPORT);
  const [stateReady,setStateReady]=useState(false);
  const [layoutNotice,setLayoutNotice]=useState("");
  const [agentEnabled,setAgentEnabled]=useState(false);
  const [agentStatus,setAgentStatus]=useState<"checking"|"ready"|"disabled"|"error">("checking");

  // This is a server decision, not an exposed NEXT_PUBLIC key or a UI toggle.
  useEffect(()=>{
    let cancelled=false;
    api<{enabled:boolean}>("/admin/analytics/agent/status").then(status=>{
      if(cancelled)return;
      setAgentEnabled(status.enabled);
      setAgentStatus(status.enabled?"ready":"disabled");
      if(status.enabled)setMode("edit");
    }).catch(()=>{
      if(!cancelled)setAgentStatus("error");
    });
    return ()=>{cancelled=true;};
  },[]);

  // Saved layouts contain only chart/widget state. Data remains in the
  // admin-protected API and is not persisted in browser storage.
  useEffect(()=>{
    try {
      const current=window.localStorage.getItem(STORAGE_KEY);
      const legacy=!current && window.localStorage.getItem(PREVIOUS_STORAGE_KEY);
      const saved=current || legacy;
      if(saved){
        const parsed:unknown=JSON.parse(saved);
        if(validStoredState(parsed)){
          // Repair the v2 mapping once; never overwrite edits saved under v3.
          if(legacy){
            for(const page of parsed.pages){
              const widgets=page.widgets as Record<string,unknown>|undefined;
              const grid=widgets?.["catalog-stock"] as
                {type?:string;dataMapping?:{cols?:unknown}}|undefined;
              if(grid?.type==="grid"){
                grid.dataMapping={...grid.dataMapping,cols:[...CATALOG_GRID_COLUMNS]};
              }
            }
          }
          setInitialState(parsed);
          if(legacy){
            window.localStorage.setItem(STORAGE_KEY,JSON.stringify(parsed));
            window.localStorage.removeItem(PREVIOUS_STORAGE_KEY);
          }
        }
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

  const data=useMemo<AgDataSourcesDefinition<KadokuRegistry>|undefined>(()=>{
    if(!report) return undefined;
    return {sources:[
      {id:"catalog",name:"Catalog",data:report.catalog,fields:CATALOG_FIELDS},
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
    try {
      window.localStorage.removeItem(STORAGE_KEY);
      window.localStorage.removeItem(PREVIOUS_STORAGE_KEY);
    } catch {}
    setInitialState(DEFAULT_REPORT);
    setRemountKey(index=>index+1);
    setLayoutNotice("Default layout restored");
  },[]);

  const ai=useMemo<AgAiHarnessSetup>(()=>({api:studioApi})=>
    createAiHarness(studioApi,{
      adapter:STUDIO_ADAPTER,
      promptStarters:STUDIO_PROMPTS,
    }),[]);

  const widgets=useMemo<AgWidgetsConfig<KadokuRegistry>>(()=>createWidgets<KadokuRegistry>({
    additionalTypes:[{
      id:"checkout-pulse",
      label:"Kadoku Checkout Health",
      form:params=>params.createDefaults({dataMappingItems:[]}),
      comp:CheckoutPulseWidget,
      defaultSize:{width:550,height:240},
      minSize:{width:320,height:170},
    }],
    menu:[{label:"Kadoku",widgetIds:["checkout-pulse"]}],
  }),[]);

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
      {agentStatus==="ready" && <div className="admin-agent-status">
        <strong>AI Analyst enabled</strong>
        <span>Open the AI chat panel inside AG Studio. Try “Chart paid gift categories”.
        The AI uses Studio tools to change this dashboard; requests go through the protected Kadoku API.</span>
      </div>}
      {agentStatus==="disabled" && <p className="admin-agent-hint">
        AI Analyst is off. To enable it locally, set STUDIO_AGENT_ENABLED=true
        and STUDIO_AGENT_MODEL=gemini/gemini-2.5-flash in apps/api/.env,
        supply GEMINI_API_KEY, then restart FastAPI.
      </p>}
      {agentStatus==="error" && <p className="admin-agent-hint">
        Could not check AI Analyst availability. The analytics dashboard remains usable.
      </p>}
      {layoutNotice && <p className="admin-layout-notice" role="status">{layoutNotice}</p>}
      <div className="admin-studio-canvas" data-ag-theme-mode="light">
        <AgStudioProvider modules={[AgStudioAiModule]}>
          <AgStudio<KadokuRegistry> key={remountKey+(agentEnabled?1000:0)}
            data={data} mode={mode} ai={agentEnabled?ai:undefined}
            initialState={initialState} widgets={widgets}
            context={{checkoutPulse:summary}} theme={KADOKU_THEME}
            onStateUpdated={onStateUpdated}/>
        </AgStudioProvider>
      </div>
      <p className="admin-disclaimer">This report uses aggregated internal test-order data. No customer identities, delivery addresses, PayPal IDs or secrets are sent to the visualization engine. Recommendation exposure and conversion events are not yet tracked.</p>
    </div>}
  </section>;
}
