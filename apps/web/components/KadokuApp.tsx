"use client";
import {useCallback, useEffect, useRef, useState} from "react";
import {api, dollars, type Gift, type GiftResponse, type Recipient, type Occasion, type OrderSummary, type OrderDetail} from "@/lib/api";
import {authClient} from "@/lib/auth-client";
import Image from "next/image";

type Screen = "home" | "ideas" | "details" | "checkout" | "people" | "orders" | "order-detail";
const checkoutStorageKey = "kadoku_pending_checkout";
function statusLabel(status: string) {
  if (status === "paid") return "Paid";
  if (status === "approval_pending") return "Awaiting payment";
  if (status === "pending") return "Pending";
  if (status === "cancelled") return "Cancelled";
  return status.replaceAll("_", " ");
}
const samplePrompts = [
  {emoji:"🎂", label:"Birthday", prompt:"I need a birthday gift for my mom. She loves gardening and tea. Budget $100."},
  {emoji:"💜", label:"Anniversary", prompt:"I'm looking for an anniversary gift for my partner. They love art and cozy evenings. Budget $80."},
  {emoji:"✨", label:"Just because", prompt:"I want to surprise my best friend who loves books and coffee. Budget $50."},
];

const DEFAULT_PRODUCT_IMAGE = "/products/default.webp";

/** Catalog photo → branded illustration → emoji, including when an image fails to load. */
function ProductArt({name, emoji, imageUrl, className, sizes}: {
  name: string;
  emoji: string;
  imageUrl: string | null;
  className: string;
  sizes: string;
}) {
  const [failedImageUrl, setFailedImageUrl] = useState<string|null>(null);
  const [defaultFailed, setDefaultFailed] = useState(false);
  useEffect(() => {
    setFailedImageUrl(null);
    setDefaultFailed(false);
  }, [imageUrl]);

  const hasProductImage = !!imageUrl && failedImageUrl !== imageUrl;
  const src = imageUrl && failedImageUrl !== imageUrl ? imageUrl : DEFAULT_PRODUCT_IMAGE;
  return <div className={className}>
    {!defaultFailed
      ? <Image
          key={src}
          src={src}
          alt={hasProductImage
            ? `AI-generated concept illustration of ${name}`
            : `Illustrative Kadoku gift box; product photo unavailable for ${name}`}
          fill
          sizes={sizes}
          className="product-art-image"
          onError={() => {
            if (hasProductImage) setFailedImageUrl(imageUrl);
            else setDefaultFailed(true);
          }}
        />
      : <span aria-hidden="true">{emoji}</span>}
  </div>;
}

export default function KadokuApp() {
  const {data: session} = authClient.useSession();
  const [screen, setScreen] = useState<Screen>("home");
  const [prompt, setPrompt] = useState("");
  const [conversation, setConversation] = useState<{text:string;summary:string}[]>([]);
  const [response, setResponse] = useState<GiftResponse|null>(null);
  const [gift, setGift] = useState<Gift|null>(null);
  const [giftNote, setGiftNote] = useState("");
  const [selectedRecipient, setSelectedRecipient] = useState("");
  const [recipients, setRecipients] = useState<Recipient[]>([]);
  const [occasions, setOccasions] = useState<Occasion[]>([]);
  const [peopleBusy, setPeopleBusy] = useState(false);
  const [peopleError, setPeopleError] = useState("");
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [selectedOrder, setSelectedOrder] = useState<OrderDetail|null>(null);
  const [ordersBusy, setOrdersBusy] = useState(false);
  const [ordersError, setOrdersError] = useState("");
  const [checkoutAfterLogin, setCheckoutAfterLogin] = useState(false);
  const [newPerson, setNewPerson] = useState("");
  const [personInterests, setPersonInterests] = useState("");
  const [birthday, setBirthday] = useState("");
  const [showAuth, setShowAuth] = useState(false);
  const googleEnabled = process.env.NEXT_PUBLIC_GOOGLE_OAUTH_ENABLED === "true";
  const [register, setRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authName, setAuthName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const recognition = useRef<{stop:()=>void}|null>(null);
  const giftScroller = useRef<HTMLDivElement|null>(null);
  const refineInput = useRef<HTMLInputElement|null>(null);
  const giftScrollPosition = useRef(0);
  const [giftNavigation, setGiftNavigation] = useState({left:false, right:false});

  const syncGiftNavigation = useCallback(() => {
    const scroller = giftScroller.current;
    if (!scroller) return;
    const left = scroller.scrollLeft > 2;
    const right = scroller.scrollLeft < scroller.scrollWidth - scroller.clientWidth - 2;
    setGiftNavigation(previous =>
      previous.left === left && previous.right === right ? previous : {left, right}
    );
  }, []);

  // A new recommendation set starts at its first card; returning from gift
  // details restores the previous position instead of jumping to the start.
  useEffect(() => { giftScrollPosition.current = 0; }, [response?.recommendations]);
  useEffect(() => {
    if (screen !== "ideas" || !giftScroller.current) return;
    const scroller = giftScroller.current;
    scroller.scrollLeft = giftScrollPosition.current;
    syncGiftNavigation();
    window.addEventListener("resize", syncGiftNavigation);
    return () => window.removeEventListener("resize", syncGiftNavigation);
  }, [screen, response?.recommendations, syncGiftNavigation]);

  function moveGiftCarousel(direction: -1|1) {
    const scroller = giftScroller.current;
    if (!scroller) return;
    const cards = scroller.querySelectorAll<HTMLElement>(".gift-card");
    const step = cards.length > 1
      ? cards[1].offsetLeft - cards[0].offsetLeft
      : scroller.clientWidth;
    scroller.scrollBy({
      left: direction * step,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    });
  }

  const loadPeople = useCallback(async () => {
    if (!session?.user?.id) {
      setRecipients([]);setOccasions([]);setPeopleError("");setPeopleBusy(false);
      return;
    }
    setPeopleBusy(true);
    setPeopleError("");
    try {
      const [people, events] = await Promise.all([api<Recipient[]>("/recipients"), api<Occasion[]>("/occasions")]);
      setRecipients(people);setOccasions(events);
    } catch {
      // Do not present a failed request as an empty saved-recipient list.
      setRecipients([]);setOccasions([]);
      setPeopleError("Could not load saved people. Please try again.");
    } finally {
      setPeopleBusy(false);
    }
  }, [session?.user?.id]);
  useEffect(() => { void loadPeople(); }, [loadPeople]);

  const loadOrders = useCallback(async () => {
    setOrdersBusy(true);
    setOrdersError("");
    try {
      setOrders(await api<OrderSummary[]>("/orders"));
    } catch (e) {
      setOrders([]);
      setOrdersError(e instanceof Error ? e.message : "Could not load orders.");
    } finally {
      setOrdersBusy(false);
    }
  }, []);
  useEffect(() => {
    if (screen === "orders" && session?.user?.id) void loadOrders();
  }, [screen, session?.user?.id, loadOrders]);
  useEffect(() => {
    if (!session?.user?.id) return;
    // Recover the selected gift after a full-page Google OAuth redirect.
    // Short-lived tab storage holds no credentials or payment data.
    const saved = sessionStorage.getItem(checkoutStorageKey);
    if (!saved) return;
    sessionStorage.removeItem(checkoutStorageKey);
    try {
      const value: {gift?: Gift; giftNote?: string; createdAt?: number} = JSON.parse(saved);
      if (!value.gift || typeof value.gift.id !== "string" ||
          typeof value.gift.name !== "string" ||
          typeof value.gift.price_minor !== "number" ||
          typeof value.createdAt !== "number" ||
          Date.now() - value.createdAt > 15 * 60 * 1000) return;
      setGift(value.gift);
      setGiftNote(typeof value.giftNote === "string" ? value.giftNote : "");
      setScreen("checkout");
    } catch { /* Invalid saved data is ignored. */ }
  }, [session?.user?.id]);

  async function openOrder(orderId: string) {
    setScreen("order-detail");
    setSelectedOrder(null);
    setOrdersError("");
    setOrdersBusy(true);
    try {
      setSelectedOrder(await api<OrderDetail>(`/orders/${orderId}`));
    } catch (e) {
      setOrdersError(e instanceof Error ? e.message : "Could not load order.");
    } finally {
      setOrdersBusy(false);
    }
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const oauthError = params.get("error");
    if (params.get("view") === "orders") {
      setScreen("orders");
      params.delete("view");
      window.history.replaceState(null, "", window.location.pathname + (params.toString() ? `?${params.toString()}` : "") + window.location.hash);
    }
    if (oauthError) {
      const messages: Record<string, string> = {
        access_denied: "Google sign-in was cancelled.",
        email_not_verified: "Your Google email must be verified before signing in.",
        unable_to_link_account: "This Google account could not be linked. Try your existing sign-in method.",
      };
      setError(messages[oauthError] || "Google sign-in was unsuccessful. Please try again.");
      setShowAuth(true);
      params.delete("error");
      const query = params.toString();
      window.history.replaceState(null, "", window.location.pathname + (query ? `?${query}` : "") + window.location.hash);
    }
  }, []);
  useEffect(() => {
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") void navigator.serviceWorker.register("/sw.js").catch(() => {});
  }, []);

  function speak() {
    setError("");
    type SpeechResult = {results: ArrayLike<ArrayLike<{transcript:string}>>};
    type Speech = {lang:string;interimResults:boolean;onresult:((e:SpeechResult)=>void)|null;onend:(()=>void)|null;onerror:((e:{error:string})=>void)|null;start:()=>void;stop:()=>void};
    const w = window as typeof window & {SpeechRecognition?:new()=>Speech; webkitSpeechRecognition?:new()=>Speech};
    const Constructor = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!Constructor) {setError("Voice input isn't supported in this browser. You can type instead.");return;}
    if (listening) {recognition.current?.stop();return;}
    const r = new Constructor(); r.lang = navigator.language || "en-US";r.interimResults=false;
    r.onresult = event => setPrompt(old => (old ? old.trim()+" " : "") + event.results[0][0].transcript);
    r.onend = () => setListening(false);
    r.onerror = event => {setListening(false);setError(`Microphone: ${event.error}`);};
    recognition.current = r;
    try {r.start();setListening(true);} catch {setError("Couldn't start microphone.");}
  }

  async function findGifts(override?: string) {
    if (busy) return;
    const message = (override ?? prompt).trim();
    const refining = screen === "ideas" && !!response?.context;
    if (message.length < (refining ? 2 : 10)) {
      setError(refining ? "Tell me what you'd like to change." : "Tell me a little more about the recipient (at least 10 characters).");
      return;
    }
    setBusy(true);setError("");
    try {
      if (!session?.user) {
        const guest = await fetch("/api/guest",{credentials:"same-origin"});
        if (!guest.ok) throw new Error("Guest sessions are not configured.");
      }
      const result = await api<GiftResponse>("/gifts/recommendations", "POST", {
        prompt: message,
        ...(selectedRecipient ? {recipient_id:selectedRecipient} : {}),
        ...(refining ? {context: response!.context} : {}),
      });
      setResponse(result);
      const turn = {text:message, summary:result.summary};
      setConversation(refining ? [...conversation,turn].slice(-5) : [turn]);
      setPrompt("");
      setScreen("ideas");
    } catch (e) {setError(e instanceof Error?e.message:"Something went wrong.");}
    finally {setBusy(false);}
  }

  async function savePerson() {
    if (!newPerson.trim()) {setError("Please enter a name.");return;}
    setBusy(true);setError("");
    try {
      const person = await api<Recipient>("/recipients", "POST", {
        name:newPerson.trim(), relationship:null,
        interests:personInterests.split(",").map(s=>s.trim().toLowerCase()).filter(Boolean), avoids:[], usual_budget_minor:null,
      });
      if (birthday) {
        const [year,month,day] = birthday.split("-").map(Number);
        await api("/occasions", "POST", {recipient_id:person.id,kind:"birthday",month,day,year:null,reminder_enabled:false});
      }
      setNewPerson("");setPersonInterests("");setBirthday("");await loadPeople();setSelectedRecipient(person.id);
    } catch(e) {setError(e instanceof Error?e.message:"Couldn't save this person.");}
    finally {setBusy(false);}
  }

  async function login() {
    setBusy(true);setError("");
    try {
      const result = register
        ? await authClient.signUp.email({email,password,name:authName||email.split("@")[0]})
        : await authClient.signIn.email({email,password});
      if (result.error) throw new Error(result.error.message || "Authentication failed");
      setShowAuth(false);setPassword("");
      if (checkoutAfterLogin && gift) {
        setCheckoutAfterLogin(false);
        setScreen("checkout");
      }
    } catch(e) {setError(e instanceof Error?e.message:"Authentication failed");}
    finally {setBusy(false);}
  }

  async function signInWithGoogle() {
    setBusy(true);setError("");
    try {
      if (checkoutAfterLogin && gift) {
        sessionStorage.setItem(checkoutStorageKey, JSON.stringify({gift, giftNote, createdAt:Date.now()}));
      }
      const result = await authClient.signIn.social({
        provider: "google", callbackURL: "/", errorCallbackURL: "/",
      });
      if (result.error) throw new Error(result.error.message || "Google sign-in failed");
      // Better Auth redirects the browser to Google on success.
    } catch (e) {
      sessionStorage.removeItem(checkoutStorageKey);
      setError(e instanceof Error ? e.message : "Google sign-in failed");
    } finally {setBusy(false);}
  }

  function continueToCheckout() {
    if (!gift) return;
    if (!session?.user) {
      setCheckoutAfterLogin(true);
      setError("");
      setShowAuth(true);
      return;
    }
    setScreen("checkout");
  }

  async function startCheckout() {
    if (!gift) return;
    if (!session?.user) {
      setCheckoutAfterLogin(true);
      setShowAuth(true);
      return;
    }
    setBusy(true);setError("");
    try {
      const result = await api<{approval_url:string;order_id:string}>("/checkout/paypal/orders","POST",{product_id:gift.id});
      window.location.assign(result.approval_url);
    } catch(e) {setError(e instanceof Error?e.message:"Checkout isn't available.");setBusy(false);}
  }

  function choose(item: Gift) {setGift(item);setScreen("details");setError("");}
  function setExample(value: string) {setPrompt(value);setConversation([]);setResponse(null);setSelectedRecipient("");setScreen("home");setError("");}
  function goHome() {setScreen("home");setPrompt("");setConversation([]);setResponse(null);setSelectedRecipient("");setError("");}

  return <div className="site-shell">
    <div className="desktop-ambient ambient-left"/><div className="desktop-ambient ambient-right"/>
    <div className="app-frame">
      <header className="topbar">
        <button className="brand" onClick={goHome} aria-label="Kadoku home"><span className="brand-mark">✦</span> kadoku<span className="brand-dot">.</span></button>
        <div className="header-right">
          <span className="header-tag">your gifting companion</span>
          {session?.user ? <button className="mini-avatar" aria-label="My people" onClick={()=>setScreen("people")}>{session.user.name?.slice(0,1).toUpperCase()||"U"}</button>
            : <button className="text-button" onClick={()=>setShowAuth(true)}>Sign in</button>}
        </div>
      </header>
      {screen==="home" && <main className="home-screen page-enter">
        <div className="hero-icon"><span>🎁</span><i>✦</i></div>
        <p className="eyebrow">A LITTLE THOUGHT GOES A LONG WAY</p>
        <h1>Make someone’s <span>day.</span></h1>
        <p className="hero-subtitle">Tell me about someone special. I’ll help you find a gift they’ll love.</p>
        <div className="composer">
          <textarea aria-label="Describe who you are shopping for" placeholder="My mom loves gardening, and her birthday is next week…" value={prompt} onChange={e=>setPrompt(e.target.value)} rows={3}/>
          <div className="composer-actions">
            <button aria-label={listening?"Stop listening":"Speak your request"} title="Voice input" className={`voice-button ${listening?"recording":""}`} onClick={speak}>{listening?"◼":"♬"}<span>{listening?"Listening…":"Voice"}</span></button>
            <button className="send-button" disabled={busy||!prompt.trim()} onClick={()=>void findGifts()}>{busy?"Finding…":"Find a gift"}<span>↗</span></button>
          </div>
        </div>
        {session?.user && recipients.length>0 && <div className="saved-recipient">
          <label htmlFor="recipient-choice">Shopping for someone you know?</label>
          <select id="recipient-choice" value={selectedRecipient} onChange={e=>setSelectedRecipient(e.target.value)}><option value="">New recipient / anyone</option>{recipients.map(p=><option value={p.id} key={p.id}>{p.name}</option>)}</select>
        </div>}
        <section className="inspiration">
          <h2>Not sure where to start?</h2><div className="chips">
            {samplePrompts.map(s=><button className="chip" key={s.label} onClick={()=>setExample(s.prompt)}>{s.emoji} {s.label}</button>)}
          </div>
        </section>
        {session?.user && occasions.length>0 && <section className="upcoming">
          <div className="section-head"><h2>Saved moments</h2><button onClick={()=>setScreen("people")}>View all ↗</button></div>
          {occasions.slice(0,2).map(o=>{
            const person=recipients.find(p=>p.id===o.recipient_id);
            return <button key={o.id} className="occasion-row" onClick={()=>{setSelectedRecipient(o.recipient_id);setPrompt(`Help me choose a ${o.kind} gift for ${person?.name||"someone special"}. Their interests are ${(person?.interests||[]).join(", ")}.`);}}>
              <span className="occasion-date">{new Date(2000,o.month-1,o.day).toLocaleString("en-US",{month:"short"})}<strong>{o.day}</strong></span>
              <span><b>{person?.name||"Someone"}'s {o.kind}</b><small>{person?.interests.join(" · ")||"Your special occasion"}</small></span><span>↗</span>
            </button>;
          })}
        </section>}
        <div className="home-secondary"><span>♡</span> Real thoughtfulness. Less guesswork.</div>
      </main>}
      {screen==="ideas" && <main className="chat-screen page-enter">
        <div className="inside-header"><button className="back-button" onClick={goHome}>←</button><span>Finding your perfect gift</span><span className="small-sparkle">✦</span></div>
        {conversation.slice(0,-1).map((turn,index)=><div key={index} className="previous-chat-turn">
          <div className="user-bubble">{turn.text}</div>
          <p className="previous-assistant-reply">✦ Kadoku · {turn.summary}</p>
        </div>)}
        <div className="user-bubble">{conversation[conversation.length-1]?.text}</div>
        <div className="assistant-note"><span className="ai-sparkle">✦</span><div><b>Kadoku</b><p>{response?.summary||"I found a few thoughtful ideas."} {(response?.recommendations.length||0)>0?"Here’s the one I’d pick.":""}</p></div></div>
        {busy && <p className="gift-loading" role="status" aria-live="polite">Updating gift ideas…</p>}
        {(response?.recommendations.length ?? 0) > 0 ? <div className="gift-carousel">
          <div ref={giftScroller} className="gift-scroller" aria-label="Gift recommendations"
               onScroll={() => {
                 giftScrollPosition.current = giftScroller.current?.scrollLeft ?? 0;
                 syncGiftNavigation();
               }}>
            {(response?.recommendations||[]).map((item,index)=><article className="gift-card" key={item.id}>
              <ProductArt name={item.name} emoji={item.emoji} imageUrl={item.image_url} className={`gift-art art-${index%3}`} sizes="(max-width: 520px) 70vw, 258px"/>
              <div className="gift-meta"><span className={index===0?"top-pick":"alternate"}>{index===0?"✦ ":""}{item.label}</span><b>{dollars(item.price_minor)}</b></div>
              <h3>{item.name}</h3><p>{item.reason}</p>
              <button className="gift-choose" onClick={()=>choose(item)}>Choose this gift <span>↗</span></button>
            </article>)}
          </div>
          {giftNavigation.left && <button type="button" className="gift-carousel-arrow gift-carousel-prev"
            aria-label="Previous gift" onClick={()=>moveGiftCarousel(-1)}>‹</button>}
          {giftNavigation.right && <button type="button" className="gift-carousel-arrow gift-carousel-next"
            aria-label="Next gift" onClick={()=>moveGiftCarousel(1)}>›</button>}
        </div> : <div className="empty-profile gift-empty" role="status">
          <p>No gifts match all those preferences right now. Try adjusting your budget or restrictions.</p>
          <button type="button" className="primary-action" onClick={()=>refineInput.current?.focus()}>Adjust gift request</button>
        </div>}
        {(response?.recommendations.length||0)>1 &&
          <p className="swipe-note">
            <span className="swipe-mobile">← Swipe to see all {response?.recommendations.length||0} ideas →</span>
            <span className="swipe-desktop">Use the arrows or trackpad to see all {response?.recommendations.length||0} ideas</span>
          </p>}
        <div className="assistant-followup"><span>✦</span><p>Not quite right? Tell me what to change. I remember the details from this chat.</p></div>
        {(response?.remaining_today ?? 0) > 0 && <div className="refine-suggestions">
          <button disabled={busy} onClick={()=>void findGifts("Make it cheaper")}>More affordable</button>
          <button disabled={busy} onClick={()=>void findGifts("Something more personal")}>More personal</button>
        </div>}
        <div className="refine-box"><input ref={refineInput} aria-label="Refine your request" placeholder="Something more personal, perhaps?" value={prompt} disabled={busy} onChange={e=>setPrompt(e.target.value)} onKeyDown={e=>{if(e.key==="Enter") {e.preventDefault();void findGifts();}}}/><button disabled={busy} onClick={speak} aria-label="Voice input">♬</button><button disabled={busy} onClick={()=>void findGifts()} aria-label={busy?"Updating recommendations":"Refine recommendations"}>{busy?"…":"↑"}</button></div>
        <p className="demo-note">{response?.notice} {response?.remaining_today===0?"You've used your recommendation quota for today.":`${response?.remaining_today} recommendations left today.`}</p>
      </main>}
      {screen==="details" && gift && <main className="details-screen page-enter">
        <div className="inside-header"><button className="back-button" onClick={()=>setScreen("ideas")}>←</button><span>Your gift</span><span>✦</span></div>
        <ProductArt name={gift.name} emoji={gift.emoji} imageUrl={gift.image_url} className="detail-art" sizes="(max-width: 520px) 100vw, 420px"/>
        <div className="detail-heading"><div><span className="detail-label">{gift.label}</span><h2>{gift.name}</h2></div><strong>{dollars(gift.price_minor)}</strong></div>
        <div className="why-card"><span>✦</span><div><b>Why this gift?</b><p>{gift.reason}</p></div></div>
        <label className="form-label" htmlFor="gift-note">Add a personal message <small>(optional)</small></label>
        <textarea id="gift-note" className="note-input" rows={3} placeholder="Happy birthday! I hope this makes you smile…" value={giftNote} onChange={e=>setGiftNote(e.target.value)}/>
        <p className="demo-note">Gift messages are for the on-screen experience only; supplier fulfillment is not connected.</p>
        <button className="primary-action" onClick={continueToCheckout}>Continue to checkout <span>→</span></button>
      </main>}
      {screen==="checkout" && gift && <main className="checkout-screen page-enter">
        <div className="inside-header"><button className="back-button" onClick={()=>setScreen("details")}>←</button><span>Checkout</span><span>⌑</span></div>
        <h2>Almost ready to <em>make their day.</em></h2>
        <p className="checkout-subtitle">Review your gift before continuing to PayPal.</p>
        <div className="order-card"><h3>Order summary</h3><div className="order-product"><span className="small-art">{gift.emoji}</span><div><b>{gift.name}</b><small>Quantity · 1</small></div><strong>{dollars(gift.price_minor)}</strong></div><div className="order-total"><span>Demo subtotal</span><strong>{dollars(gift.price_minor)}</strong></div></div>
        {giftNote && <div className="gift-message-preview"><b>Your gift message</b><p>“{giftNote}”</p></div>}
        <div className="sandbox-banner"><b>Sandbox checkout</b><p>Sample products have no real stock or shipping. Only use PayPal Sandbox test accounts. No real fulfillment occurs.</p></div>
        {!session?.user && <p className="demo-note">Sign in to place your order and see it in My Orders.</p>}
        <button className="primary-action paypal-action" disabled={busy} onClick={session?.user ? startCheckout : continueToCheckout}>{busy?"Opening PayPal…":session?.user?"Continue to PayPal Sandbox":"Sign in to checkout"} <span>→</span></button>
      </main>}
      {screen==="orders" && <main className="people-screen page-enter">
        <div className="inside-header"><button className="back-button" onClick={goHome} aria-label="Back to home">←</button><span>My Orders</span><span>⌑</span></div>
        <h2>My <em>Orders.</em></h2>
        <p>Track your PayPal Sandbox purchases. These are demo orders; no gifts will be shipped.</p>
        {!session?.user ? <div className="empty-profile">
          <div>⌑</div><p>Sign in to see your orders and continue checkout.</p>
          <button className="primary-action" onClick={()=>{setCheckoutAfterLogin(false);setShowAuth(true);}}>Sign in</button>
        </div> : ordersBusy ? <p className="muted" role="status">Loading orders…</p> : ordersError ?
          <div><p role="alert" className="auth-error">{ordersError}</p><button className="text-button" onClick={()=>void loadOrders()}>Try again</button></div> :
          orders.length===0 ? <div className="empty-profile"><p>No orders yet. Start by finding a gift.</p><button className="primary-action" onClick={goHome}>Find a gift</button></div> :
          <div className="orders-list">
            {orders.map(order=><button key={order.id} className="order-row" onClick={()=>void openOrder(order.id)}>
              <span className="small-art" aria-hidden="true">{order.product_emoji}</span>
              <span className="order-row-details">
                <strong>{order.product_name}</strong>
                <small>{new Date(order.created_at).toLocaleDateString()} · {order.id.slice(0,8)}</small>
                <small className={order.status==="paid"?"order-paid":""}>{statusLabel(order.status)}</small>
              </span>
              <span className="order-row-price">{dollars(order.price_minor)} <span aria-hidden="true">›</span></span>
            </button>)}
          </div>}
      </main>}
      {screen==="order-detail" && <main className="checkout-screen page-enter">
        <div className="inside-header"><button className="back-button" onClick={()=>setScreen("orders")} aria-label="Back to My Orders">←</button><span>Order details</span><span>⌑</span></div>
        {!session?.user ? <div className="empty-profile"><p>Sign in to view this order.</p><button className="primary-action" onClick={()=>setShowAuth(true)}>Sign in</button></div> :
          ordersBusy ? <p className="muted" role="status">Loading order…</p> : ordersError ?
          <p role="alert" className="auth-error">{ordersError}</p> : selectedOrder ? <>
            <h2>{selectedOrder.product_name}</h2>
            <div className="order-card">
              <div className="order-product"><span className="small-art">{selectedOrder.product_emoji}</span>
                <div><b>{selectedOrder.product_name}</b><small>Quantity · 1</small></div>
                <strong>{dollars(selectedOrder.price_minor)}</strong>
              </div>
              <div className="order-total"><span>Payment status</span><strong>{statusLabel(selectedOrder.status)}</strong></div>
            </div>
            <div className="order-facts">
              <div><span>Order ID</span><code>{selectedOrder.id}</code></div>
              <div><span>Date</span><strong>{new Date(selectedOrder.created_at).toLocaleString()}</strong></div>
              <div><span>PayPal Sandbox order</span><code>{selectedOrder.paypal_order_id ?? "Not created"}</code></div>
              {selectedOrder.paypal_capture_id && <div><span>Capture ID</span><code>{selectedOrder.paypal_capture_id}</code></div>}
            </div>
            <div className="sandbox-banner"><b>Demo transaction</b><p>This order uses PayPal Sandbox. No real products will be shipped.</p></div>
          </> : <p className="muted">Order not found.</p>}
      </main>}
      {screen==="people" && <main className="people-screen page-enter">
        <div className="inside-header"><button className="back-button" onClick={goHome}>←</button><span>My people</span><span>♡</span></div>
        <h2>Remember the <em>little things.</em></h2>
        <p>Save someone you care about, and let Kadoku remember their interests and birthday.</p>
        {!session?.user ? <div className="empty-profile"><div>♡</div><p>Sign in to save the people who matter to you.</p><button className="primary-action" onClick={()=>setShowAuth(true)}>Sign in</button></div> : <>
          <div className="add-person"><h3>Add someone special</h3>
            <label className="form-label">Name<input value={newPerson} onChange={e=>setNewPerson(e.target.value)} placeholder="Mom, Sarah, Alex…"/></label>
            <label className="form-label">Interests <small>(comma-separated)</small><input value={personInterests} onChange={e=>setPersonInterests(e.target.value)} placeholder="gardening, coffee, books"/></label>
            <label className="form-label">Birthday <small>(optional, year won't be saved)</small><input type="date" value={birthday} onChange={e=>setBirthday(e.target.value)}/></label>
            <button className="primary-action" disabled={busy} onClick={savePerson}>Save recipient →</button>
          </div>
          <h3 className="people-heading">Saved people</h3>
          {peopleBusy ? <p className="muted" role="status">Loading saved people…</p>
             : peopleError ? <div><p role="alert" className="auth-error">{peopleError}</p><button type="button" className="text-button" onClick={()=>void loadPeople()}>Try again</button></div>
             : recipients.length===0 ? <p className="muted">No saved people yet.</p> : recipients.map(p=>{
            const birthday=occasions.find(o=>o.recipient_id===p.id && o.kind==="birthday");
            return <div className="person-card" key={p.id}><span className="person-avatar">{p.name[0].toUpperCase()}</span><div><b>{p.name}</b><p>{p.interests.join(" · ")||"No interests yet"}{birthday?` · Birthday ${birthday.month}/${birthday.day}`:""}</p></div><button onClick={()=>{setSelectedRecipient(p.id);setPrompt(`I need a thoughtful gift for ${p.name}, who loves ${p.interests.join(", ")||"meaningful surprises"}. Budget $100.`);setScreen("home");}}>Find gift ↗</button></div>;
          })}
        </>}
      </main>}
      {!showAuth && error && <div className="error-banner" role="alert">{error}<button onClick={()=>setError("")}>×</button></div>}
      <nav className="bottom-nav" aria-label="Main navigation"><button className={screen==="home"?"active":""} onClick={goHome}><span>⌂</span>Home</button><button className={screen==="orders"||screen==="order-detail"?"active":""} onClick={()=>{setScreen("orders");setError("");}}><span>⌑</span>My Orders</button><button className={screen==="people"?"active":""} onClick={()=>{setScreen("people");setError("");}}><span>♡</span>My people</button><button onClick={()=>setShowAuth(true)}><span>☻</span>{session?.user?"Account":"Sign in"}</button></nav>
    </div>
    {showAuth && <div className="modal-backdrop" onClick={()=>{setShowAuth(false);setCheckoutAfterLogin(false);}}><div className="auth-modal" role="dialog" aria-modal="true" aria-label="Account" onClick={e=>e.stopPropagation()}>
      <div className="modal-top"><h2>{session?.user?"Your account":register?"Create an account":"Welcome back"}</h2><button onClick={()=>{setShowAuth(false);setCheckoutAfterLogin(false);}} aria-label="Close">×</button></div>
      {showAuth && error && <p role="alert" className="auth-error">{error}</p>}
      {session?.user ? <><p>Signed in as {session.user.email}</p><button className="primary-action" onClick={async()=>{await authClient.signOut();setSelectedRecipient("");setRecipients([]);setOccasions([]);setOrders([]);setSelectedOrder(null);setCheckoutAfterLogin(false);sessionStorage.removeItem(checkoutStorageKey);setShowAuth(false);goHome();}}>Sign out</button></> : <>
        <p>{checkoutAfterLogin ? "Sign in to continue checkout. Your chosen gift will be kept." : "Save recipients, view orders, and get more daily recommendations."}</p>
        {register && <label className="form-label">Your name<input value={authName} onChange={e=>setAuthName(e.target.value)} autoComplete="name"/></label>}
        <label className="form-label">Email<input type="email" value={email} onChange={e=>setEmail(e.target.value)} autoComplete="email"/></label>
        <label className="form-label">Password<input type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete={register?"new-password":"current-password"}/></label>
        <button className="primary-action" disabled={busy||!email||password.length<8} onClick={login}>{busy?"Please wait…":register?"Create account":"Sign in"}</button>
        {googleEnabled && <button className="google-button" disabled={busy} onClick={signInWithGoogle}>Continue with Google</button>}
        <button className="switch-auth" onClick={()=>{setRegister(!register);setError("");}}>{register?"Already have an account? Sign in":"New here? Create an account"}</button>
      </>}
    </div></div>}
  </div>;
}
