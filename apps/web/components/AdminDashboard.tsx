"use client";

import {useCallback, useEffect, useState, type FormEvent} from "react";
import {api, dollars} from "@/lib/api";
import {authClient} from "@/lib/auth-client";

type Section = "overview" | "products" | "orders";
type Access = "checking" | "allowed" | "denied" | "signed-out" | "error";

type Overview = {
  products_total: number;
  products_active: number;
  products_out_of_stock: number;
  orders_total: number;
  orders_paid: number;
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
  demo_only: boolean;
};
type AdminOrder = {
  id: string;
  product_id: string;
  product_name: string;
  price_minor: number;
  currency: string;
  status: string;
  buyer_ref: string;
  created_at: string;
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
  interests: string;
  occasions: string;
  styles: string;
};

const PAGE_SIZE = 20;
const emptyForm: ProductForm = {
  name: "", description: "", category: "", price: "", stock: "10",
  emoji: "🎁", active: true, interests: "", occasions: "", styles: "",
};
const sections: {id:Section;label:string;symbol:string}[] = [
  {id:"overview", label:"Overview", symbol:"◫"},
  {id:"products", label:"Products", symbol:"▦"},
  {id:"orders", label:"Orders", symbol:"▤"},
];

function dateLabel(value: string) {
  return new Intl.DateTimeFormat("en-US", {dateStyle:"medium"}).format(new Date(value));
}
function orderStatus(status: string) {
  return status.replaceAll("_", " ");
}
function splitTags(value: string) {
  return value.split(",").map(tag=>tag.trim()).filter(Boolean);
}

export default function AdminDashboard() {
  const {data:session, isPending} = authClient.useSession();
  const [access, setAccess] = useState<Access>("checking");
  const [accessError, setAccessError] = useState("");
  const [section, setSection] = useState<Section>("overview");
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
  const [ordersPage, setOrdersPage] = useState(1);
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
    setProductBusy(true);
    setProductError("");
    const params = new URLSearchParams({
      page: String(productPage), page_size: String(PAGE_SIZE),
    });
    if (search) params.set("search", search);
    if (activeFilter !== "all") params.set("active", activeFilter);
    try {
      setProducts(await api<Page<AdminProduct>>("/admin/products?" + params.toString()));
    } catch (error) {
      setProductError(error instanceof Error ? error.message : "Could not load products.");
    } finally {
      setProductBusy(false);
    }
  }, [productPage, search, activeFilter]);

  const loadOrders = useCallback(async () => {
    setOrdersBusy(true);
    setOrdersError("");
    const params = new URLSearchParams({
      page: String(ordersPage), page_size: String(PAGE_SIZE),
    });
    if (orderStatusFilter) params.set("status", orderStatusFilter);
    try {
      setOrders(await api<Page<AdminOrder>>("/admin/orders?" + params.toString()));
    } catch (error) {
      setOrdersError(error instanceof Error ? error.message : "Could not load orders.");
    } finally {
      setOrdersBusy(false);
    }
  }, [ordersPage, orderStatusFilter]);

  useEffect(() => {
    if (access === "allowed" && section === "products") void loadProducts();
  }, [access, section, loadProducts]);

  useEffect(() => {
    if (access === "allowed" && section === "orders") void loadOrders();
  }, [access, section, loadOrders]);

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
          onClick={()=>{setSection(item.id);setEditing(null);}}>
          <span aria-hidden="true">{item.symbol}</span>{item.label}
        </button>)}
      </nav>
      <div className="admin-sidebar-bottom">
        <div className="admin-account"><span>Signed in as</span><strong>{session?.user?.email}</strong></div>
        <a href="/">← View storefront</a>
      </div>
    </aside>
    <main className="admin-main">
      <div className="admin-topline"><span>KADOKU / ADMIN</span><span className="admin-env">Demo catalog · PayPal Sandbox</span></div>
      {section==="overview" && <>
        <div className="admin-section-heading"><div><p className="admin-overline">THE BIG PICTURE</p><h1>Overview</h1><p>Store operations at a glance. No live sales or fulfillment.</p></div>
          <button type="button" className="admin-outline" onClick={()=>void loadOverview()} disabled={overviewBusy}>↻ Refresh</button>
        </div>
        {overviewError && <p className="admin-error" role="alert">{overviewError}</p>}
        {overviewBusy && <p className="admin-muted" role="status">Refreshing overview…</p>}
        {overview && <div className="admin-stat-grid">
          <div className="admin-stat"><span>Products</span><strong>{overview.products_total}</strong><small>{overview.products_active} active</small></div>
          <div className="admin-stat"><span>Out of stock</span><strong>{overview.products_out_of_stock}</strong><small>All products</small></div>
          <div className="admin-stat"><span>Sandbox orders</span><strong>{overview.orders_total}</strong><small>{overview.orders_paid} marked paid</small></div>
          <div className="admin-stat"><span>Sandbox captured amount</span><strong>{dollars(overview.sandbox_paid_minor)}</strong><small>Test payments, not revenue</small></div>
        </div>}
        <div className="admin-info">
          <div className="admin-info-icon">✳</div>
          <div><h2>Demo-only operations</h2><p>All new products are marked demo-only. Order statuses come from the payment workflow; this dashboard cannot approve, capture, refund, or fulfill payments.</p></div>
        </div>
      </>}
      {section==="products" && <>
        <div className="admin-section-heading"><div><p className="admin-overline">CATALOG MANAGEMENT</p><h1>Products</h1><p>Add, edit, activate, or deactivate demo products.</p></div>
          <button className="admin-primary" type="button" onClick={()=>openEditor()}>+ Add product</button>
        </div>
        {editing && <section className="admin-editor" aria-label={editing==="new"?"New product":"Edit product"}>
          <div className="admin-editor-head"><h2>{editing==="new"?"New demo product":"Edit demo product"}</h2><button type="button" className="admin-outline" onClick={()=>setEditing(null)}>Close</button></div>
          <form onSubmit={saveProduct}>
            <div className="admin-form-grid">
              <label className="admin-field">Product name<input required maxLength={160} value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></label>
              <label className="admin-field">Category<input required maxLength={64} value={form.category} onChange={e=>setForm({...form,category:e.target.value})}/></label>
              <label className="admin-field admin-field-wide">Description<textarea required maxLength={2000} rows={3} value={form.description} onChange={e=>setForm({...form,description:e.target.value})}/></label>
              <label className="admin-field">USD price<input required inputMode="decimal" placeholder="59.00" value={form.price} onChange={e=>setForm({...form,price:e.target.value})}/></label>
              <label className="admin-field">Stock<input required inputMode="numeric" type="number" min="0" step="1" value={form.stock} onChange={e=>setForm({...form,stock:e.target.value})}/></label>
              <label className="admin-field">Emoji<input required maxLength={12} value={form.emoji} onChange={e=>setForm({...form,emoji:e.target.value})}/></label>
              <label className="admin-field">Interests (comma-separated)<input value={form.interests} onChange={e=>setForm({...form,interests:e.target.value})} placeholder="coffee, reading"/></label>
              <label className="admin-field">Occasions (comma-separated)<input value={form.occasions} onChange={e=>setForm({...form,occasions:e.target.value})} placeholder="birthday, thank_you"/></label>
              <label className="admin-field">Styles (comma-separated)<input value={form.styles} onChange={e=>setForm({...form,styles:e.target.value})} placeholder="personal, practical"/></label>
            </div>
            <label className="admin-check"><input type="checkbox" checked={form.active} onChange={e=>setForm({...form,active:e.target.checked})}/> Active (visible if in stock)</label>
            <p className="admin-help">New items are always USD demo products. Existing product images are preserved. Uncheck Active to remove a product from recommendations without deleting its order history.</p>
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
            <thead><tr><th>Product</th><th>Category</th><th>Price</th><th>Stock</th><th>Status</th><th>Action</th></tr></thead>
            <tbody>{products.items.map(product=><tr key={product.id}>
              <td><div className="admin-product-name"><span className="admin-emoji">{product.emoji}</span><span><strong>{product.name}</strong><small>{product.demo_only?"Demo product":"Catalog item"}</small></span></div></td>
              <td>{product.category}</td><td className="admin-no-wrap">{dollars(product.price_minor)}</td><td>{product.stock}</td>
              <td><span className={"admin-pill " + (!product.active?"is-inactive":product.stock===0?"is-warning":"is-active")}>{!product.active?"Inactive":product.stock===0?"Out of stock":"Active"}</span></td>
              <td><button type="button" className="admin-link-button" onClick={()=>openEditor(product)}>Edit</button></td>
            </tr>)}</tbody>
          </table></div>
          {products.items.length===0 && <p className="admin-empty">No products match your filters.</p>}
          <div className="admin-pagination"><span>{products.total} products · Page {productPage} of {Math.max(1,Math.ceil(products.total/PAGE_SIZE))}</span><div>
            <button type="button" className="admin-outline" disabled={productPage===1||productBusy} onClick={()=>setProductPage(p=>p-1)}>Previous</button>
            <button type="button" className="admin-outline" disabled={productPage*PAGE_SIZE>=products.total||productBusy} onClick={()=>setProductPage(p=>p+1)}>Next</button>
          </div></div></>}
        </div>
      </>}
      {section==="orders" && <>
        <div className="admin-section-heading"><div><p className="admin-overline">PAYMENTS & ORDERS</p><h1>Orders</h1><p>Read-only PayPal Sandbox order history across all shoppers.</p></div>
          <button type="button" className="admin-outline" onClick={()=>void loadOrders()} disabled={ordersBusy}>↻ Refresh</button>
        </div>
        <div className="admin-panel">
          <div className="admin-toolbar"><label className="admin-small-label" htmlFor="admin-order-status">Payment status</label>
            <select id="admin-order-status" value={orderStatusFilter} onChange={e=>{setOrderStatusFilter(e.target.value);setOrdersPage(1);}}>
              <option value="">All statuses</option><option value="pending">Pending</option>
              <option value="approval_pending">Approval pending</option><option value="paid">Paid</option><option value="cancelled">Cancelled</option>
            </select>
          </div>
          {ordersError && <p className="admin-error" role="alert">{ordersError}</p>}
          {ordersBusy && <p className="admin-loading" role="status">Loading orders…</p>}
          {orders && <><div className="admin-table-scroll"><table className="admin-table">
            <thead><tr><th>Date</th><th>Product</th><th>Order</th><th>Buyer ref</th><th>Amount</th><th>Status</th></tr></thead>
            <tbody>{orders.items.map(order=><tr key={order.id}>
              <td className="admin-no-wrap">{dateLabel(order.created_at)}</td>
              <td><strong>{order.product_name}</strong></td>
              <td className="admin-mono" title={order.id}>{order.id.slice(0,8)}…</td>
              <td className="admin-no-wrap">{order.buyer_ref}</td>
              <td className="admin-no-wrap">{dollars(order.price_minor)}</td>
              <td><span className={"admin-pill "+(order.status==="paid"?"is-active":order.status==="cancelled"?"is-inactive":"is-warning")}>{orderStatus(order.status)}</span></td>
            </tr>)}</tbody>
          </table></div>
          {orders.items.length===0 && <p className="admin-empty">No orders found for this status.</p>}
          <div className="admin-pagination"><span>{orders.total} orders · Page {ordersPage} of {Math.max(1,Math.ceil(orders.total/PAGE_SIZE))}</span><div>
            <button className="admin-outline" type="button" disabled={ordersPage===1||ordersBusy} onClick={()=>setOrdersPage(p=>p-1)}>Previous</button>
            <button className="admin-outline" type="button" disabled={ordersPage*PAGE_SIZE>=orders.total||ordersBusy} onClick={()=>setOrdersPage(p=>p+1)}>Next</button>
          </div></div></>}
        </div>
        <p className="admin-disclaimer">Payment status is maintained by PayPal capture and verified webhooks. Changing it manually is deliberately unsupported.</p>
      </>}
    </main>
  </div>;
}
