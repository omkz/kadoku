"use client";

import {useCallback, useEffect, useRef, useState, type FormEvent} from "react";
import {api, dollars} from "@/lib/api";
import {authClient} from "@/lib/auth-client";

type Section = "overview" | "products" | "orders" | "customers" | "settings";
type Access = "checking" | "allowed" | "denied" | "signed-out" | "error";

type Overview = {
  products_total: number;
  products_active: number;
  products_out_of_stock: number;
  orders_total: number;
  buyers_total: number;
  orders_paid: number;
  awaiting_fulfillment: number;
  sandbox_paid_minor: number;
};
type AdminProduct = {
  id: string;
  name: string;
  description: string;
  category: string;
  price_minor: number;
  currency: string;
  stock: number;
  active: boolean;
  emoji: string;
  interests: string[];
  occasions: string[];
  styles: string[];
  image_url: string | null;
  sku: string | null;
  demo_only: boolean;
};
type AdminOrder = {
  id: string;
  product_id: string;
  product_name: string;
  price_minor: number;
  currency: string;
  status: string;
  fulfillment_status: string;
  buyer_ref: string;
  created_at: string;
};
type AdminOrderDetail = AdminOrder & {
  shipping_address: Record<string,string|null>|null;
  tracking_carrier: string|null;
  tracking_number: string|null;
  shipped_at: string|null;
  delivered_at: string|null;
  history: {from_status:string;to_status:string;actor_ref:string;note:string|null;created_at:string}[];
};
const nextFulfillment: Record<string,string> = {
  unfulfilled:"processing", processing:"shipped", shipped:"delivered",
};
type AdminCustomer = {
  buyer_ref: string;
  orders_total: number;
  paid_orders: number;
  sandbox_paid_minor: number;
  latest_order_at: string;
};
type Page<T> = {items: T[]; total: number; page: number; page_size: number};
type ProductForm = {
  name: string;
  description: string;
  category: string;
  price: string;
  stock: string;
  emoji: string;
  active: boolean;
  sku: string;
  imageUrl: string;
  interests: string;
  occasions: string;
  styles: string;
};

const DEFAULT_PAGE_SIZE = 20;
const emptyForm: ProductForm = {
  name: "", description: "", category: "", price: "", stock: "10",
  emoji: "🎁", active: true, sku: "", imageUrl: "", interests: "", occasions: "", styles: "",
};
const sections: {id:Section;label:string;symbol:string}[] = [
  {id:"overview", label:"Overview", symbol:"◫"},
  {id:"products", label:"Products", symbol:"▦"},
  {id:"orders", label:"Orders", symbol:"▤"},
  {id:"customers", label:"Customers", symbol:"♙"},
  {id:"settings", label:"Settings", symbol:"⚙"},
];

function dateLabel(value: string) {
  return new Intl.DateTimeFormat("en-US", {dateStyle:"medium"}).format(new Date(value));
}
function orderStatus(status: string) {
  return status.replaceAll("_", " ");
}
function pageRange(total: number, page: number, size: number) {
  return total === 0 ? "0" : `${(page - 1) * size + 1}–${Math.min(page * size, total)}`;
}
function splitTags(value: string) {
  return value.split(",").map(tag=>tag.trim()).filter(Boolean);
}

export default function AdminDashboard() {
  const {data:session, isPending} = authClient.useSession();
  const [access, setAccess] = useState<Access>("checking");
  const [accessError, setAccessError] = useState("");
  const [section, setSection] = useState<Section>("overview");
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const productsRequest = useRef(0);
  const ordersRequest = useRef(0);
  const customersRequest = useRef(0);
  const [overview, setOverview] = useState<Overview|null>(null);
  const [overviewBusy, setOverviewBusy] = useState(false);
  const [overviewError, setOverviewError] = useState("");
  const [products, setProducts] = useState<Page<AdminProduct>|null>(null);
  const [productBusy, setProductBusy] = useState(false);
  const [productError, setProductError] = useState("");
  const [filterInput, setFilterInput] = useState("");
  const [search, setSearch] = useState("");
  const [activeFilter, setActiveFilter] = useState("all");
  const [productPage, setProductPage] = useState(1);
  const [orders, setOrders] = useState<Page<AdminOrder>|null>(null);
  const [ordersBusy, setOrdersBusy] = useState(false);
  const [ordersError, setOrdersError] = useState("");
  const [orderStatusFilter, setOrderStatusFilter] = useState("");
  const [fulfillmentFilter, setFulfillmentFilter] = useState("");
  const [selectedOrder, setSelectedOrder] = useState<AdminOrderDetail|null>(null);
  const [orderDetailBusy, setOrderDetailBusy] = useState(false);
  const [orderDetailError, setOrderDetailError] = useState("");
  const [transitionBusy, setTransitionBusy] = useState(false);
  const [transitionError, setTransitionError] = useState("");
  const [trackingCarrier, setTrackingCarrier] = useState("");
  const [trackingNumber, setTrackingNumber] = useState("");
  const [fulfillmentNote, setFulfillmentNote] = useState("");
  const [ordersPage, setOrdersPage] = useState(1);
  const [customers, setCustomers] = useState<Page<AdminCustomer>|null>(null);
  const [customersPage, setCustomersPage] = useState(1);
  const [customersBusy, setCustomersBusy] = useState(false);
  const [customersError, setCustomersError] = useState("");
  const [editing, setEditing] = useState<"new"|string|null>(null);
  const [form, setForm] = useState<ProductForm>({...emptyForm});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  const loadOverview = useCallback(async () => {
    setOverviewBusy(true);
    setOverviewError("");
    try {
      setOverview(await api<Overview>("/admin/overview"));
    } catch (error) {
      setOverviewError(error instanceof Error ? error.message : "Could not load overview.");
    } finally {
      setOverviewBusy(false);
    }
  }, []);

  useEffect(() => {
    if (isPending) return;
    if (!session?.user) {
      setAccess("signed-out");
      setOverview(null);
      return;
    }
    let cancelled = false;
    setAccess("checking");
    setAccessError("");
    api<Overview>("/admin/overview").then(result => {
      if (cancelled) return;
      setOverview(result);
      setAccess("allowed");
    }).catch(error => {
      if (cancelled) return;
      const message = error instanceof Error ? error.message : "Could not check administrator access.";
      setAccess(message.includes("Administrator access required") ? "denied" : "error");
      setAccessError(message);
    });
    return () => { cancelled = true; };
  }, [isPending, session?.user?.id]);

  const loadProducts = useCallback(async () => {
    const requestId = ++productsRequest.current;
    setProductBusy(true);
    setProductError("");
    const params = new URLSearchParams({
      page: String(productPage), page_size: String(pageSize),
    });
    if (search) params.set("search", search);
    if (activeFilter !== "all") params.set("active", activeFilter);
    try {
      const result = await api<Page<AdminProduct>>("/admin/products?" + params.toString());
      if (requestId === productsRequest.current) setProducts(result);
    } catch (error) {
      if (requestId === productsRequest.current) setProductError(error instanceof Error ? error.message : "Could not load products.");
    } finally {
      if (requestId === productsRequest.current) setProductBusy(false);
    }
  }, [productPage, search, activeFilter, pageSize]);

  const loadOrders = useCallback(async () => {
    const requestId = ++ordersRequest.current;
    setOrdersBusy(true);
    setOrdersError("");
    const params = new URLSearchParams({
      page: String(ordersPage), page_size: String(pageSize),
    });
    if (orderStatusFilter) params.set("status", orderStatusFilter);
    if (fulfillmentFilter) params.set("fulfillment", fulfillmentFilter);
    try {
      const result = await api<Page<AdminOrder>>("/admin/orders?" + params.toString());
      if (requestId === ordersRequest.current) setOrders(result);
    } catch (error) {
      if (requestId === ordersRequest.current) setOrdersError(error instanceof Error ? error.message : "Could not load orders.");
    } finally {
      if (requestId === ordersRequest.current) setOrdersBusy(false);
    }
  }, [ordersPage, orderStatusFilter, fulfillmentFilter, pageSize]);

  const loadCustomers = useCallback(async () => {
    const requestId = ++customersRequest.current;
    setCustomersBusy(true);
    setCustomersError("");
    const params = new URLSearchParams({
      page: String(customersPage), page_size: String(pageSize),
    });
    try {
      const result = await api<Page<AdminCustomer>>("/admin/customers?" + params.toString());
      if (requestId === customersRequest.current) setCustomers(result);
    } catch (error) {
      if (requestId === customersRequest.current) setCustomersError(error instanceof Error ? error.message : "Could not load customers.");
    } finally {
      if (requestId === customersRequest.current) setCustomersBusy(false);
    }
  }, [customersPage, pageSize]);

  useEffect(() => {
    if (access === "allowed" && section === "products") void loadProducts();
  }, [access, section, loadProducts]);

  useEffect(() => {
    if (access === "allowed" && section === "orders") void loadOrders();
  }, [access, section, loadOrders]);

  useEffect(() => {
    if (access === "allowed" && section === "customers") void loadCustomers();
  }, [access, section, loadCustomers]);

  function changePageSize(value: number) {
    setPageSize(value);
    setProductPage(1);
    setOrdersPage(1);
    setCustomersPage(1);
  }

  const pageSizeControl = <label className="admin-page-size">Rows per page
    <select aria-label="Rows per page" value={pageSize} onChange={e=>changePageSize(Number(e.target.value))}>
      <option value={10}>10</option>
      <option value={20}>20</option>
      <option value={50}>50</option>
    </select>
  </label>;

  async function openOrder(orderId: string) {
    setOrderDetailBusy(true);
    setOrderDetailError("");
    setTransitionError("");
    setSelectedOrder(null);
    try {
      setSelectedOrder(await api<AdminOrderDetail>("/admin/orders/" + encodeURIComponent(orderId)));
    } catch (error) {
      setOrderDetailError(error instanceof Error ? error.message : "Could not load order.");
    } finally {
      setOrderDetailBusy(false);
    }
  }

  async function advanceFulfillment() {
    if (!selectedOrder || transitionBusy) return;
    const target = nextFulfillment[selectedOrder.fulfillment_status];
    if (!target || selectedOrder.status !== "paid") return;
    setTransitionBusy(true);
    setTransitionError("");
    try {
      const updated = await api<AdminOrderDetail>(
        "/admin/orders/" + encodeURIComponent(selectedOrder.id) + "/fulfillment",
        "POST", {
          expected_status:selectedOrder.fulfillment_status, to_status:target,
          ...(target==="shipped" ? {tracking_carrier:trackingCarrier.trim(),tracking_number:trackingNumber.trim()} : {}),
          note:fulfillmentNote.trim() || null,
        },
      );
      setSelectedOrder(updated);
      setFulfillmentNote("");
      setTrackingCarrier("");
      setTrackingNumber("");
      await Promise.all([loadOrders(),loadOverview()]);
    } catch (error) {
      setTransitionError(error instanceof Error ? error.message : "Could not update fulfillment.");
    } finally {
      setTransitionBusy(false);
    }
  }

  function openEditor(product?: AdminProduct) {
    if (!product) {
      setEditing("new");
      setForm({...emptyForm});
    } else {
      setEditing(product.id);
      setForm({
        name: product.name, description: product.description,
        category: product.category, price: (product.price_minor/100).toFixed(2),
        stock: String(product.stock), active: product.active, emoji: product.emoji,
        sku: product.sku ?? "", imageUrl: product.image_url ?? "",
        interests: product.interests.join(", "),
        occasions: product.occasions.join(", "), styles: product.styles.join(", "),
      });
    }
    setSaveError("");
  }

  async function saveProduct(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing || saving) return;
    const price = form.price.trim();
    const stock = Number(form.stock);
    if (!/^\d+(\.\d{1,2})?$/.test(price) || Number(price) <= 0 ||
        Number(price) > 100000 || !Number.isSafeInteger(stock) || stock < 0 || stock > 1000000) {
      setSaveError("Enter a valid USD price (max two decimals) and non-negative integer stock.");
      return;
    }
    const payload = {
      name: form.name.trim(), description: form.description.trim(),
      category: form.category.trim(), price_minor: Math.round(Number(price) * 100),
      stock, active: form.active, emoji: form.emoji.trim(),
      sku:form.sku.trim() || null, image_url:form.imageUrl.trim() || null,
      interests: splitTags(form.interests), occasions: splitTags(form.occasions),
      styles: splitTags(form.styles),
    };
    setSaving(true);
    setSaveError("");
    try {
      if (editing === "new") {
        await api<AdminProduct>("/admin/products", "POST", payload);
      } else {
        await api<AdminProduct>("/admin/products/" + encodeURIComponent(editing), "PATCH", payload);
      }
      setEditing(null);
      await Promise.all([loadProducts(), loadOverview()]);
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "Could not save product.");
    } finally {
      setSaving(false);
    }
  }

  if (isPending || access === "checking") {
    return <main className="admin-gate"><h1>Kadoku admin</h1><p role="status">Checking administrator access…</p></main>;
  }
  if (access !== "allowed") {
    return <main className="admin-gate">
      <span className="admin-gate-symbol">✦</span>
      <h1>{access === "signed-out" ? "Sign in required" : access === "denied" ? "Access restricted" : "Unable to load admin"}</h1>
      <p>{access === "signed-out"
        ? "Sign in to Kadoku with your administrator account, then return to this page."
        : access === "denied" ? "This account is not authorized to manage Kadoku."
        : accessError || "The administrator API is unavailable."}</p>
      <a className="admin-primary-link" href="/">Return to Kadoku</a>
      {access === "error" && <button className="admin-link-button" onClick={()=>window.location.reload()}>Try again</button>}
    </main>;
  }

  return <div className="admin-page">
    <aside className="admin-sidebar">
      <a className="admin-logo" href="/"><span>✦</span> kadoku<span className="admin-logo-dot">.</span></a>
      <p className="admin-sidebar-label">STORE MANAGEMENT</p>
      <nav aria-label="Admin dashboard">
        {sections.map(item=><button type="button" key={item.id}
          className={"admin-nav-button " + (section===item.id ? "is-active" : "")}
          aria-current={section===item.id ? "page" : undefined}
          onClick={()=>{setSection(item.id);setEditing(null);setSelectedOrder(null);}}>
          <span aria-hidden="true">{item.symbol}</span>{item.label}
        </button>)}
      </nav>
      <div className="admin-sidebar-bottom">
        <div className="admin-account"><span>Signed in as</span><strong>{session?.user?.email}</strong></div>
        <a href="/">← View storefront</a>
      </div>
    </aside>
    <main className="admin-main">
      <div className="admin-topline"><span>KADOKU / ADMIN</span><span className="admin-env">Test payments: PayPal Sandbox</span></div>
      {section==="overview" && <>
        <div className="admin-section-heading"><div><p className="admin-overline">THE BIG PICTURE</p><h1>Overview</h1><p>Catalog, payment and order-processing activity in one place.</p></div>
          <button type="button" className="admin-outline" onClick={()=>void loadOverview()} disabled={overviewBusy}>↻ Refresh</button>
        </div>
        {overviewError && <p className="admin-error" role="alert">{overviewError}</p>}
        {overviewBusy && <p className="admin-muted" role="status">Refreshing overview…</p>}
        {overview && <div className="admin-stat-grid">
          <div className="admin-stat"><span>Products</span><strong>{overview.products_total}</strong><small>{overview.products_active} active · {overview.products_out_of_stock} out of stock</small></div>
          <div className="admin-stat"><span>Awaiting processing</span><strong>{overview.awaiting_fulfillment}</strong><small>Paid, not yet processed</small></div>
          <div className="admin-stat"><span>Orders</span><strong>{overview.orders_total}</strong><small>{overview.orders_paid} marked paid</small></div>
          <div className="admin-stat"><span>Sandbox captured amount</span><strong>{dollars(overview.sandbox_paid_minor)}</strong><small>Test payments, not revenue</small></div>
        </div>}
        <div className="admin-info">
          <div className="admin-info-icon">✳</div>
          <div><h2>Operational workspace · Sandbox phase</h2><p>Manage catalog content and track order processing independently from payment. Test captures are not revenue, and no real stock fulfillment, shipping integrations or live payments are enabled yet.</p></div>
        </div>
      </>}
      {section==="products" && <>
        <div className="admin-section-heading"><div><p className="admin-overline">CATALOG MANAGEMENT</p><h1>Products</h1><p>Manage catalog listings, SKUs, prices, stock and product images.</p></div>
          <button className="admin-primary" type="button" onClick={()=>openEditor()}>+ Add product</button>
        </div>
        {editing && <section className="admin-editor" aria-label={editing==="new"?"New product":"Edit product"}>
          <div className="admin-editor-head"><h2>{editing==="new"?"New product":"Edit product"}</h2><button type="button" className="admin-outline" onClick={()=>setEditing(null)}>Close</button></div>
          <form onSubmit={saveProduct}>
            <div className="admin-form-grid">
              <label className="admin-field">Product name<input required maxLength={160} value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></label>
              <label className="admin-field">Category<input required maxLength={64} value={form.category} onChange={e=>setForm({...form,category:e.target.value})}/></label>
              <label className="admin-field admin-field-wide">Description<textarea required maxLength={2000} rows={3} value={form.description} onChange={e=>setForm({...form,description:e.target.value})}/></label>
              <label className="admin-field">USD price<input required inputMode="decimal" placeholder="59.00" value={form.price} onChange={e=>setForm({...form,price:e.target.value})}/></label>
              <label className="admin-field">Stock<input required inputMode="numeric" type="number" min="0" step="1" value={form.stock} onChange={e=>setForm({...form,stock:e.target.value})}/></label>
              <label className="admin-field">SKU (optional)<input maxLength={64} placeholder="GIFT-001" value={form.sku} onChange={e=>setForm({...form,sku:e.target.value})}/></label>
              <label className="admin-field">Product image path<input placeholder="/products/item.webp" value={form.imageUrl} onChange={e=>setForm({...form,imageUrl:e.target.value})}/></label>
              {/^\/products\/[A-Za-z0-9_-]+\.(webp|png|jpg|jpeg)$/.test(form.imageUrl) && <div className="admin-field admin-field-wide"><span>Image preview</span><img className="admin-media-preview" src={form.imageUrl} alt="Product preview"/></div>}
              <label className="admin-field">Emoji<input required maxLength={12} value={form.emoji} onChange={e=>setForm({...form,emoji:e.target.value})}/></label>
              <label className="admin-field">Interests (comma-separated)<input value={form.interests} onChange={e=>setForm({...form,interests:e.target.value})} placeholder="coffee, reading"/></label>
              <label className="admin-field">Occasions (comma-separated)<input value={form.occasions} onChange={e=>setForm({...form,occasions:e.target.value})} placeholder="birthday, thank_you"/></label>
              <label className="admin-field">Styles (comma-separated)<input value={form.styles} onChange={e=>setForm({...form,styles:e.target.value})} placeholder="personal, practical"/></label>
            </div>
            <label className="admin-check"><input type="checkbox" checked={form.active} onChange={e=>setForm({...form,active:e.target.checked})}/> Active (visible if in stock)</label>
            <p className="admin-help">Use an existing first-party image at /products/filename.webp (upload/storage is a separate integration). New listings stay test-only until sourcing and live-commerce checks are complete. Unpublish to remove a listing from recommendations without deleting order history.</p>
            {saveError && <p className="admin-error" role="alert">{saveError}</p>}
            <div className="admin-editor-actions"><button type="button" className="admin-outline" onClick={()=>setEditing(null)}>Cancel</button><button type="submit" className="admin-primary" disabled={saving}>{saving?"Saving…":"Save product"}</button></div>
          </form>
        </section>}
        <div className="admin-panel">
          <form className="admin-toolbar" onSubmit={event=>{event.preventDefault();setProductPage(1);setSearch(filterInput.trim());}}>
            <input aria-label="Search product name or category" placeholder="Search products or categories…" value={filterInput} maxLength={120} onChange={e=>setFilterInput(e.target.value)}/>
            <button type="submit" className="admin-outline">Search</button>
            <select aria-label="Product status" value={activeFilter} onChange={e=>{setActiveFilter(e.target.value);setProductPage(1);}}>
              <option value="all">All products</option><option value="true">Active</option><option value="false">Inactive</option>
            </select>
            <button type="button" className="admin-outline" onClick={()=>void loadProducts()} disabled={productBusy}>↻</button>
          </form>
          {productError && <p className="admin-error" role="alert">{productError}</p>}
          {productBusy && <p className="admin-loading" role="status">Loading products…</p>}
          {products && <><div className="admin-table-scroll"><table className="admin-table">
            <thead><tr><th>Product</th><th>SKU</th><th>Category</th><th>Price</th><th>Stock</th><th>Status</th><th>Action</th></tr></thead>
            <tbody>{products.items.map(product=><tr key={product.id}>
              <td><div className="admin-product-name"><span className="admin-emoji">{product.image_url ? <img className="admin-product-thumb" src={product.image_url} alt="" /> : product.emoji}</span><span><strong>{product.name}</strong><small>{product.demo_only?"Test listing":"Verified listing"}</small></span></div></td>
              <td className="admin-mono">{product.sku || "—"}</td><td>{product.category}</td><td className="admin-no-wrap">{dollars(product.price_minor)}</td><td>{product.stock}</td>
              <td><span className={"admin-pill " + (!product.active?"is-inactive":product.stock===0?"is-warning":"is-active")}>{!product.active?"Unpublished":product.stock===0?"Out of stock":"Published"}</span></td>
              <td><button type="button" className="admin-link-button" onClick={()=>openEditor(product)}>Edit</button></td>
            </tr>)}</tbody>
          </table></div>
          {products.items.length===0 && <p className="admin-empty">No products match your filters.</p>}
          <div className="admin-pagination"><span>Showing {pageRange(products.total,productPage,pageSize)} of {products.total} products · Page {productPage} of {Math.max(1,Math.ceil(products.total/pageSize))}</span><div>{pageSizeControl}
            <button type="button" className="admin-outline" disabled={productPage===1||productBusy} onClick={()=>setProductPage(p=>p-1)}>Previous</button>
            <button type="button" className="admin-outline" disabled={productPage*pageSize>=products.total||productBusy} onClick={()=>setProductPage(p=>p+1)}>Next</button>
          </div></div></>}
        </div>
      </>}
      {section==="orders" && <>
        <div className="admin-section-heading"><div><p className="admin-overline">PAYMENTS & ORDERS</p><h1>Orders</h1><p>Review payments, shipping details and fulfillment progress.</p></div>
          <button type="button" className="admin-outline" onClick={()=>void loadOrders()} disabled={ordersBusy}>↻ Refresh</button>
        </div>
        {orderDetailBusy && <p role="status" className="admin-loading">Loading order details…</p>}
        {orderDetailError && <p role="alert" className="admin-error">{orderDetailError}</p>}
        {selectedOrder && <section className="admin-editor" aria-label="Order details">
          <div className="admin-editor-head"><h2>Order {selectedOrder.id.slice(0,8)}…</h2><button type="button" className="admin-outline" onClick={()=>setSelectedOrder(null)}>Close</button></div>
          <div className="admin-order-detail-grid">
            <div><h3>Payment</h3><p>{orderStatus(selectedOrder.status)} · {dollars(selectedOrder.price_minor)}</p><p className="admin-muted">Customer: {selectedOrder.buyer_ref}</p></div>
            <div><h3>Fulfillment</h3><p>{orderStatus(selectedOrder.fulfillment_status)}</p>
              {selectedOrder.tracking_carrier && <p className="admin-muted">{selectedOrder.tracking_carrier} · {selectedOrder.tracking_number}</p>}
            </div>
            <div className="admin-order-shipping"><h3>Shipping address · private</h3>
              {selectedOrder.shipping_address
                ? <address>{["full_name","address_line_1","address_line_2","city","region","postal_code","country"].map(key=>selectedOrder.shipping_address?.[key]).filter(Boolean).join(", ")}</address>
                : <p className="admin-muted">No shipping address recorded.</p>}
              {selectedOrder.shipping_address?.phone_number && <p className="admin-muted">Phone: {selectedOrder.shipping_address.phone_country_code} {selectedOrder.shipping_address.phone_number}</p>}
            </div>
          </div>
          {selectedOrder.status==="paid" && nextFulfillment[selectedOrder.fulfillment_status] && <>
            <h3 className="admin-action-heading">Next step: {orderStatus(nextFulfillment[selectedOrder.fulfillment_status])}</h3>
            {nextFulfillment[selectedOrder.fulfillment_status]==="shipped" && <div className="admin-form-grid">
              <label className="admin-field">Carrier<input maxLength={80} value={trackingCarrier} onChange={e=>setTrackingCarrier(e.target.value)} placeholder="Courier name"/></label>
              <label className="admin-field">Tracking number<input maxLength={120} value={trackingNumber} onChange={e=>setTrackingNumber(e.target.value)}/></label>
            </div>}
            <label className="admin-field admin-note-field">Internal note (optional)<textarea maxLength={500} rows={2} value={fulfillmentNote} onChange={e=>setFulfillmentNote(e.target.value)}/></label>
            {transitionError && <p className="admin-error" role="alert">{transitionError}</p>}
            <div className="admin-editor-actions"><button type="button" className="admin-primary" disabled={transitionBusy} onClick={()=>void advanceFulfillment()}>{transitionBusy?"Updating…":"Mark "+orderStatus(nextFulfillment[selectedOrder.fulfillment_status])}</button></div>
          </>}
          {selectedOrder.status!=="paid" && <p className="admin-disclaimer">This order cannot be processed until payment is captured. Payment status cannot be overridden here.</p>}
          <div className="admin-history"><h3>Activity history</h3>
            {selectedOrder.history.length===0 ? <p className="admin-muted">No fulfillment actions yet.</p>
            : <ol>{selectedOrder.history.map((entry,index)=><li key={index}><strong>{orderStatus(entry.from_status)} → {orderStatus(entry.to_status)}</strong> · {dateLabel(entry.created_at)} · {entry.actor_ref}{entry.note && <p>{entry.note}</p>}</li>)}</ol>}
          </div>
        </section>}
        <div className="admin-panel">
          <div className="admin-toolbar"><label className="admin-small-label" htmlFor="admin-order-status">Payment status</label>
            <select id="admin-order-status" value={orderStatusFilter} onChange={e=>{setOrderStatusFilter(e.target.value);setOrdersPage(1);}}>
              <option value="">All statuses</option><option value="pending">Pending</option>
              <option value="approval_pending">Approval pending</option><option value="paid">Paid</option><option value="cancelled">Cancelled</option>
            </select>
            <label className="admin-small-label" htmlFor="admin-fulfillment">Fulfillment</label>
            <select id="admin-fulfillment" value={fulfillmentFilter} onChange={e=>{setFulfillmentFilter(e.target.value);setOrdersPage(1);}}>
              <option value="">All</option><option value="unfulfilled">Unfulfilled</option>
              <option value="processing">Processing</option><option value="shipped">Shipped</option>
              <option value="delivered">Delivered</option>
            </select>
          </div>
          {ordersError && <p className="admin-error" role="alert">{ordersError}</p>}
          {ordersBusy && <p className="admin-loading" role="status">Loading orders…</p>}
          {orders && <><div className="admin-table-scroll"><table className="admin-table">
            <thead><tr><th>Date</th><th>Product</th><th>Order</th><th>Buyer ref</th><th>Amount</th><th>Payment</th><th>Fulfillment</th><th></th></tr></thead>
            <tbody>{orders.items.map(order=><tr key={order.id}>
              <td className="admin-no-wrap">{dateLabel(order.created_at)}</td>
              <td><strong>{order.product_name}</strong></td>
              <td className="admin-mono" title={order.id}>{order.id.slice(0,8)}…</td>
              <td className="admin-no-wrap">{order.buyer_ref}</td>
              <td className="admin-no-wrap">{dollars(order.price_minor)}</td>
              <td><span className={"admin-pill "+(order.status==="paid"?"is-active":order.status==="cancelled"?"is-inactive":"is-warning")}>{orderStatus(order.status)}</span></td>
              <td><span className={"admin-pill "+(order.fulfillment_status==="delivered"?"is-active":order.fulfillment_status==="unfulfilled"?"is-inactive":"is-warning")}>{orderStatus(order.fulfillment_status)}</span></td>
              <td><button type="button" className="admin-link-button" onClick={()=>void openOrder(order.id)}>Details</button></td>
            </tr>)}</tbody>
          </table></div>
          {orders.items.length===0 && <p className="admin-empty">No orders found for this status.</p>}
          <div className="admin-pagination"><span>Showing {pageRange(orders.total,ordersPage,pageSize)} of {orders.total} orders · Page {ordersPage} of {Math.max(1,Math.ceil(orders.total/pageSize))}</span><div>{pageSizeControl}
            <button className="admin-outline" type="button" disabled={ordersPage===1||ordersBusy} onClick={()=>setOrdersPage(p=>p-1)}>Previous</button>
            <button className="admin-outline" type="button" disabled={ordersPage*pageSize>=orders.total||ordersBusy} onClick={()=>setOrdersPage(p=>p+1)}>Next</button>
          </div></div></>}
        </div>
        <p className="admin-disclaimer">Payment status is controlled by PayPal capture, not by staff actions. Fulfillment changes are logged separately. Sandbox orders are for workflow testing only—no real shipment is initiated.</p>
      </>}
      {section==="customers" && <>
        <div className="admin-section-heading"><div><p className="admin-overline">BUYER ACTIVITY</p><h1>Customers</h1><p>Signed-in buyers with order history. Registered users without orders are not included.</p></div>
          <button type="button" className="admin-outline" onClick={()=>void loadCustomers()} disabled={customersBusy}>↻ Refresh</button>
        </div>
        <div className="admin-panel">
          {customersError && <p className="admin-error" role="alert">{customersError}</p>}
          {customersBusy && <p className="admin-loading" role="status">Loading buyer activity…</p>}
          {customers && <><div className="admin-table-scroll"><table className="admin-table">
            <thead><tr><th>Buyer ref</th><th>Orders</th><th>Paid</th><th>Sandbox captured</th><th>Last order</th></tr></thead>
            <tbody>{customers.items.map(buyer=><tr key={buyer.buyer_ref}>
              <td className="admin-mono">{buyer.buyer_ref}</td>
              <td>{buyer.orders_total}</td><td>{buyer.paid_orders}</td>
              <td className="admin-no-wrap">{dollars(buyer.sandbox_paid_minor)}</td>
              <td className="admin-no-wrap">{dateLabel(buyer.latest_order_at)}</td>
            </tr>)}</tbody>
          </table></div>
          {customers.items.length===0 && <p className="admin-empty">No signed-in buyers with orders yet.</p>}
          <div className="admin-pagination"><span>Showing {pageRange(customers.total,customersPage,pageSize)} of {customers.total} buyers · Page {customersPage} of {Math.max(1,Math.ceil(customers.total/pageSize))}</span><div>{pageSizeControl}
            <button type="button" className="admin-outline" disabled={customersPage===1||customersBusy} onClick={()=>setCustomersPage(p=>p-1)}>Previous</button>
            <button type="button" className="admin-outline" disabled={customersPage*pageSize>=customers.total||customersBusy} onClick={()=>setCustomersPage(p=>p+1)}>Next</button>
          </div></div></>}
        </div>
        <p className="admin-disclaimer">Guest checkout records cannot be reliably assigned to an individual customer. This view deliberately omits emails, addresses and PayPal identifiers.</p>
      </>}
      {section==="settings" && <>
        <div className="admin-section-heading"><div><p className="admin-overline">STORE CONFIGURATION</p><h1>Settings</h1><p>Environment, access control and catalog policy.</p></div></div>
        <div className="admin-settings-grid">
          <div className="admin-panel admin-settings-card"><h2>Administrator account</h2><p>{session?.user?.email}</p><small>Admin access is configured server-side using verified Better Auth user IDs in ADMIN_USER_IDS.</small></div>
          <div className="admin-panel admin-settings-card"><h2>Payment environment</h2><p>PayPal Sandbox only</p><small>Test payments are not revenue. Payment mode, provider keys and captures cannot be edited here.</small></div>
          <div className="admin-panel admin-settings-card"><h2>Catalog policy</h2><p>USD · demo-only products</p><small>Products can be activated or deactivated under Products. Fulfillment tracking is available for tests, but real stock reservation and shipping are not enabled.</small></div>
        </div>
        <p className="admin-disclaimer">These are read-only operational notes, not editable production settings.</p>
      </>}
    </main>
  </div>;
}
