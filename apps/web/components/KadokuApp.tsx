"use client";
import {useCallback, useEffect, useRef, useState} from "react";
import {api, dollars, type Gift, type GiftResponse, type Recipient, type Occasion, type OrderSummary, type OrderDetail, type ShippingAddress, type CatalogProduct} from "@/lib/api";
import {authClient} from "@/lib/auth-client";
import Image from "next/image";

type Screen = "home" | "ideas" | "details" | "checkout" | "people" | "orders" | "order-detail";
const checkoutStorageKey = "kadoku_pending_checkout";

/** Show people with the nearest upcoming birthday first; unknown birthdays last. */
function peopleByUpcomingBirthday(people:Recipient[], moments:Occasion[], now=new Date()):Recipient[] {
  const today=Date.UTC(now.getFullYear(),now.getMonth(),now.getDate());
  const nextBirthday=new Map<string,number>();
  for(const moment of moments){
    if(moment.kind!=="birthday" || moment.month<1 || moment.month>12 ||
      moment.day<1 || moment.day>31)continue;
    const thisYear=Date.UTC(now.getFullYear(),moment.month-1,moment.day);
    const next=thisYear<today
      ? Date.UTC(now.getFullYear()+1,moment.month-1,moment.day)
      : thisYear;
    const days=Math.round((next-today)/86_400_000);
    const previous=nextBirthday.get(moment.recipient_id);
    if(previous===undefined || days<previous)nextBirthday.set(moment.recipient_id,days);
  }
  return [...people].sort((a,b)=>{
    const left=nextBirthday.get(a.id) ?? Infinity;
    const right=nextBirthday.get(b.id) ?? Infinity;
    return left-right || a.name.localeCompare(b.name,undefined,{sensitivity:"base"}) ||
      a.id.localeCompare(b.id);
  });
}
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


// This is a demo checkout: country names are free-form, and dial codes remain
// editable so users outside this suggestion list are not blocked.
const dialSuggestions = [
  {country:"Indonesia", dial:"+62"}, {country:"United States", dial:"+1"},
  {country:"United Kingdom", dial:"+44"}, {country:"Netherlands", dial:"+31"},
  {country:"Germany", dial:"+49"}, {country:"France", dial:"+33"},
  {country:"Italy", dial:"+39"}, {country:"Japan", dial:"+81"},
  {country:"Singapore", dial:"+65"}, {country:"Australia", dial:"+61"},
  {country:"India", dial:"+91"}, {country:"Malaysia", dial:"+60"},
  {country:"Philippines", dial:"+63"}, {country:"Thailand", dial:"+66"},
  {country:"South Korea", dial:"+82"}, {country:"China", dial:"+86"},
  {country:"Canada", dial:"+1"}, {country:"Brazil", dial:"+55"},
  {country:"United Arab Emirates", dial:"+971"}, {country:"Saudi Arabia", dial:"+966"},
];
const initialShipping: ShippingAddress = {
  full_name:"", address_line_1:"", address_line_2:null, city:"",
  region:null, postal_code:null, country:"Indonesia",
  phone_country_code:"+62", phone_number:null,
};


/** A consistent, recognizable voice affordance across home and recommendations. */
function MicrophoneIcon() {
  return <svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18"
    fill="none" stroke="currentColor" strokeWidth="1.8"
    strokeLinecap="round" strokeLinejoin="round">
    <rect x="9" y="2" width="6" height="12" rx="3"/>
    <path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/>
  </svg>;
}

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
  const [detailsOrigin, setDetailsOrigin] = useState<"home"|"ideas">("ideas");
  const [featured, setFeatured] = useState<CatalogProduct[]>([]);
  const [featuredStatus, setFeaturedStatus] = useState<"loading"|"ready"|"error">("loading");
  const featuredScroller = useRef<HTMLDivElement|null>(null);
  const featuredScrollPosition = useRef(0);
  const [featuredNav, setFeaturedNav] = useState({left:false,right:false});
  const [giftNote, setGiftNote] = useState("");
  const [shipping, setShipping] = useState<ShippingAddress>({...initialShipping});
  const [selectedRecipient, setSelectedRecipient] = useState("");
  const [recipients, setRecipients] = useState<Recipient[]>([]);
  const [occasions, setOccasions] = useState<Occasion[]>([]);
  const [peopleBusy, setPeopleBusy] = useState(false);
  const [peopleError, setPeopleError] = useState("");
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [selectedOrder, setSelectedOrder] = useState<OrderDetail|null>(null);
  const [requestedOrderId, setRequestedOrderId] = useState<string|null>(null);
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
  const canRefine = (response?.remaining_today ?? 0) > 0;
  const [listening, setListening] = useState(false);
  const recognition = useRef<{stop:()=>void}|null>(null);
  const giftScroller = useRef<HTMLDivElement|null>(null);
  const refineInput = useRef<HTMLInputElement|null>(null);
  const giftScrollPosition = useRef(0);
  const [giftNavigation, setGiftNavigation] = useState({left:false, right:false});

  const loadFeatured = useCallback(async () => {
    setFeaturedStatus("loading");
    try {
      const products = await api<CatalogProduct[]>("/products/featured");
      setFeatured(products);
      setFeaturedStatus("ready");
    } catch {
      setFeatured([]);
      setFeaturedStatus("error");
    }
  }, []);
  useEffect(() => { void loadFeatured(); }, [loadFeatured]);

  const syncFeaturedNavigation = useCallback(() => {
    const el = featuredScroller.current;
    if (!el) return;
    const left = el.scrollLeft > 2;
    const right = el.scrollLeft < el.scrollWidth - el.clientWidth - 2;
    setFeaturedNav(p => p.left===left && p.right===right ? p : {left,right});
  }, []);
  useEffect(() => {
    if (screen !== "home" || featured.length < 2 || !featuredScroller.current) return;
    featuredScroller.current.scrollLeft = featuredScrollPosition.current;
    syncFeaturedNavigation();
    window.addEventListener("resize", syncFeaturedNavigation);
    return () => window.removeEventListener("resize", syncFeaturedNavigation);
  }, [screen,featured,syncFeaturedNavigation]);

  function moveFeatured(direction: -1|1) {
    const el = featuredScroller.current;
    if (!el) return;
    const cards = el.querySelectorAll<HTMLElement>(".featured-card");
    const step = cards.length > 1 ? cards[1].offsetLeft - cards[0].offsetLeft : el.clientWidth;
    el.scrollBy({
      left: direction*step,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    });
  }

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
      const value: {gift?: Gift; giftNote?: string; detailsOrigin?: "home"|"ideas"; createdAt?: number} = JSON.parse(saved);
      if (!value.gift || typeof value.gift.id !== "string" ||
          typeof value.gift.name !== "string" ||
          typeof value.gift.price_minor !== "number" ||
          typeof value.createdAt !== "number" ||
          Date.now() - value.createdAt > 15 * 60 * 1000) return;
      setGift(value.gift);
      setDetailsOrigin(value.detailsOrigin === "home" ? "home" : "ideas");
      setGiftNote(typeof value.giftNote === "string" ? value.giftNote : "");
      setScreen("checkout");
    } catch { /* Invalid saved data is ignored. */ }
  }, [session?.user?.id]);

  async function openOrder(orderId: string) {
    setRequestedOrderId(orderId);
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
        sessionStorage.setItem(checkoutStorageKey, JSON.stringify({gift, giftNote, detailsOrigin, createdAt:Date.now()}));
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
      const address: ShippingAddress = {
        ...shipping,
        full_name:shipping.full_name.trim(),
        address_line_1:shipping.address_line_1.trim(),
        address_line_2:shipping.address_line_2?.trim() || null,
        city:shipping.city.trim(),
        region:shipping.region?.trim() || null,
        postal_code:shipping.postal_code?.trim() || null,
        country:shipping.country.trim(),
        phone_country_code:shipping.phone_number?.trim() ? shipping.phone_country_code?.trim() || null : null,
        phone_number:shipping.phone_number?.trim() || null,
      };
      const result = await api<{approval_url:string;order_id:string}>("/checkout/paypal/orders","POST",{
        product_id:gift.id, shipping_address:address,
      });
      window.location.assign(result.approval_url);
    } catch(e) {setError(e instanceof Error?e.message:"Checkout isn't available.");setBusy(false);}
  }

  function choose(item: Gift, origin: "home"|"ideas" = "ideas") {
    if (gift?.id !== item.id) setGiftNote("");
    setGift(item);
    setDetailsOrigin(origin);
    setScreen("details");
    setError("");
  }
  function chooseFeatured(item: CatalogProduct) {
    choose({
      id:item.id, name:item.name, description:item.description, category:item.category,
      price_minor:item.price_minor, currency:item.currency, emoji:item.emoji,
      image_url:item.image_url, demo_only:item.demo_only,
      label:"Featured gift", reason:item.description,
    }, "home");
  }
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
        <p className="eyebrow">YOUR PERSONAL GIFT COMPANION</p>
        <h1>Make someone’s <span>day.</span></h1>
        <p className="hero-subtitle">Tell me who you’re shopping for, what they love, and your budget.</p>
        <div className="composer">
          <textarea aria-label="Describe who you are shopping for" placeholder="My mom loves gardening. Her birthday is next week. Budget $80…" value={prompt} onChange={e=>setPrompt(e.target.value)} rows={3}/>
          <div className="composer-actions">
            <button aria-label={listening?"Stop listening":"Speak your request"} title="Voice input" className={`voice-button ${listening?"recording":""}`} onClick={speak}>{listening?<span className="voice-stop" aria-hidden="true"/>:<MicrophoneIcon/>}<span>{listening?"Listening…":"Voice"}</span></button>
            <button className="send-button" disabled={busy||!prompt.trim()} onClick={()=>void findGifts()}>{busy?"Finding…":"Find a gift"}<span>↗</span></button>
          </div>
        </div>
        {session?.user && recipients.length>0 && <div className="saved-recipient">
          <label htmlFor="recipient-choice">Shopping for someone you know?</label>
          <select id="recipient-choice" value={selectedRecipient} onChange={e=>setSelectedRecipient(e.target.value)}><option value="">New recipient / anyone</option>{recipients.map(p=><option value={p.id} key={p.id}>{p.name}</option>)}</select>
        </div>}
        <section className="inspiration">
          <h2>Need inspiration?</h2><div className="chips">
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
        <section className="featured-section" aria-labelledby="featured-title">
          <div className="featured-heading">
            <div><h2 id="featured-title">Featured gifts ✦</h2>
              <p>Thoughtful ideas from our demo collection.</p>
            </div>
            {featured.length > 1 && <div className="featured-controls">
              <button type="button" disabled={!featuredNav.left} aria-label="Previous featured gifts"
                onClick={()=>moveFeatured(-1)}>‹</button>
              <button type="button" disabled={!featuredNav.right} aria-label="Next featured gifts"
                onClick={()=>moveFeatured(1)}>›</button>
            </div>}
          </div>
          {featuredStatus==="loading" ? <p className="featured-message" role="status">Loading gift ideas…</p>
            : featuredStatus==="error" ? <div className="featured-message" role="alert">
              Gift ideas couldn't load. <button type="button" onClick={()=>void loadFeatured()}>Try again</button>
            </div> : featured.length ? <div className="featured-scroller" ref={featuredScroller}
              aria-label="Featured gifts" role="region" tabIndex={0}
              onScroll={()=>{featuredScrollPosition.current=featuredScroller.current?.scrollLeft ?? 0;syncFeaturedNavigation();}}>
              {featured.map(item=><button type="button" key={item.id} className="featured-card"
                aria-label={`View ${item.name}, ${dollars(item.price_minor)}`}
                onClick={()=>chooseFeatured(item)}>
                <ProductArt name={item.name} emoji={item.emoji} imageUrl={item.image_url}
                  className="featured-art" sizes="155px"/>
                <span className="featured-name">{item.name}</span>
                <span className="featured-price">{dollars(item.price_minor)} <span aria-hidden="true">↗</span></span>
              </button>)}
            </div> : <p className="featured-message">No gift ideas available right now.</p>}
        </section>
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
          <p>No gifts match all those preferences right now.</p>
          {canRefine
            ? <button type="button" className="primary-action" onClick={()=>refineInput.current?.focus()}>Adjust gift request</button>
            : <button type="button" className="primary-action" onClick={session?.user ? goHome : ()=>{setCheckoutAfterLogin(false);setShowAuth(true);}}>
                {session?.user ? "Back to home" : "Sign in for more ideas"}
              </button>}
        </div>}
        {(response?.recommendations.length||0)>1 &&
          <p className="swipe-note">
            <span className="swipe-mobile">← Swipe to see all {response?.recommendations.length||0} ideas →</span>
            <span className="swipe-desktop">Use the arrows or trackpad to see all {response?.recommendations.length||0} ideas</span>
          </p>}
        <div className="assistant-followup"><span>✦</span><p>Not quite right? Tell me what to change. I remember the details from this chat.</p></div>
        {canRefine && <div className="refine-suggestions">
          <button disabled={busy} onClick={()=>void findGifts("Make it cheaper")}>More affordable</button>
          <button disabled={busy} onClick={()=>void findGifts("Something more personal")}>More personal</button>
        </div>}
        <div className="refine-box"><input ref={refineInput} aria-label="Refine your request" placeholder={canRefine ? "Something more personal, perhaps?" : "Daily recommendation limit reached"} value={prompt} disabled={busy || !canRefine} onChange={e=>setPrompt(e.target.value)} onKeyDown={e=>{if(e.key==="Enter") {e.preventDefault();void findGifts();}}}/><button disabled={busy || !canRefine} onClick={speak} aria-label={listening?"Stop voice input":"Voice input"}><MicrophoneIcon/></button><button disabled={busy || !canRefine} onClick={()=>void findGifts()} aria-label={busy?"Updating recommendations":"Refine recommendations"}>{busy?"…":"↑"}</button></div>
        <p className="demo-note">{response?.notice} {response?.remaining_today===0?"You've used your recommendation quota for today.":`${response?.remaining_today} recommendations left today.`}</p>
      </main>}
      {screen==="details" && gift && <main className="details-screen page-enter">
        <div className="inside-header"><button className="back-button" aria-label={detailsOrigin==="home"?"Back to home":"Back to recommendations"} onClick={()=>setScreen(detailsOrigin)}>←</button><span>Your gift</span><span>✦</span></div>
        <ProductArt name={gift.name} emoji={gift.emoji} imageUrl={gift.image_url} className="detail-art" sizes="(max-width: 520px) 100vw, 420px"/>
        <div className="detail-heading"><div><span className="detail-label">{gift.label}</span><h2>{gift.name}</h2></div><strong>{dollars(gift.price_minor)}</strong></div>
        <div className="why-card"><span>✦</span><div><b>{detailsOrigin==="home"?"About this gift":"Why this gift?"}</b><p>{gift.reason}</p></div></div>
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
        <form className="shipping-form" onSubmit={e=>{e.preventDefault();void startCheckout();}}>
          <h3>Recipient shipping address</h3>
          <p className="demo-note">Demo only — use a fictional address. No gift will be shipped.</p>
          <label className="form-label" htmlFor="ship-name">Full name
            <input id="ship-name" required minLength={2} maxLength={120} autoComplete="shipping name"
              value={shipping.full_name} onChange={e=>setShipping(old=>({...old,full_name:e.target.value}))} placeholder="Recipient's full name"/>
          </label>
          <label className="form-label" htmlFor="ship-address">Address
            <input id="ship-address" required minLength={5} maxLength={200} autoComplete="shipping address-line1"
              value={shipping.address_line_1} onChange={e=>setShipping(old=>({...old,address_line_1:e.target.value}))} placeholder="Street and house number"/>
          </label>
          <label className="form-label" htmlFor="ship-address-2">Address line 2 <small>(optional)</small>
            <input id="ship-address-2" maxLength={200} autoComplete="shipping address-line2"
              value={shipping.address_line_2 ?? ""} onChange={e=>setShipping(old=>({...old,address_line_2:e.target.value}))} placeholder="Apartment, district, extra details"/>
          </label>
          <div className="shipping-grid">
            <label className="form-label" htmlFor="ship-city">City
              <input id="ship-city" required minLength={2} maxLength={100} autoComplete="shipping address-level2"
                value={shipping.city} onChange={e=>setShipping(old=>({...old,city:e.target.value}))}/>
            </label>
            <label className="form-label" htmlFor="ship-region">State / Province <small>(optional)</small>
              <input id="ship-region" maxLength={100} autoComplete="shipping address-level1"
                value={shipping.region ?? ""} onChange={e=>setShipping(old=>({...old,region:e.target.value}))}/>
            </label>
            <label className="form-label" htmlFor="ship-postal">Postal code <small>(optional)</small>
              <input id="ship-postal" maxLength={32} autoComplete="shipping postal-code"
                value={shipping.postal_code ?? ""} onChange={e=>setShipping(old=>({...old,postal_code:e.target.value}))}/>
            </label>
            <label className="form-label" htmlFor="ship-country">Country
              <input id="ship-country" required minLength={2} maxLength={80} list="shipping-country-suggestions" autoComplete="shipping country-name"
                value={shipping.country} onChange={e=>{
                  const country=e.target.value;
                  const match=dialSuggestions.find(item=>item.country.toLowerCase()===country.trim().toLowerCase());
                  setShipping(old=>({...old,country,...(match?{phone_country_code:match.dial}:{})}));
                }}/>
            </label>
          </div>
          <datalist id="shipping-country-suggestions">{dialSuggestions.map(item=><option key={item.country} value={item.country}/>)}</datalist>
          <label className="form-label" htmlFor="ship-phone">Phone number <small>(optional)</small></label>
          <div className="shipping-phone">
            <input aria-label="International dialing code" title="Country calling code" type="tel" inputMode="tel" maxLength={5}
              list="shipping-dial-suggestions" value={shipping.phone_country_code ?? ""} placeholder="+62"
              onChange={e=>setShipping(old=>({...old,phone_country_code:e.target.value}))}/>
            <input id="ship-phone" type="tel" inputMode="tel" autoComplete="shipping tel-national" maxLength={30}
              value={shipping.phone_number ?? ""} placeholder="81234567890"
              onChange={e=>setShipping(old=>({...old,phone_number:e.target.value}))}/>
          </div>
          <datalist id="shipping-dial-suggestions">{[...new Set(dialSuggestions.map(item=>item.dial))].map(dial=><option key={dial} value={dial}/>)}</datalist>
          <div className="sandbox-banner"><b>Sandbox checkout</b><p>This address is saved only for your demo order. Use PayPal Sandbox test accounts; no real payment or fulfillment occurs.</p></div>
          <button type="submit" className="primary-action paypal-action" disabled={busy}>{busy?"Opening PayPal…":"Continue to PayPal Sandbox"} <span>→</span></button>
        </form>
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
          <div><p role="alert" className="auth-error">{ordersError}</p><button type="button" className="text-button" onClick={()=>requestedOrderId && void openOrder(requestedOrderId)} disabled={!requestedOrderId}>Try again</button></div> : selectedOrder ? <>
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
            <div className="shipping-summary">
              <h3>Recipient address</h3>
              {selectedOrder.shipping_address ? <address>
                <strong>{selectedOrder.shipping_address.full_name}</strong>
                <span>{selectedOrder.shipping_address.address_line_1}</span>
                {selectedOrder.shipping_address.address_line_2 && <span>{selectedOrder.shipping_address.address_line_2}</span>}
                <span>{[selectedOrder.shipping_address.city, selectedOrder.shipping_address.region, selectedOrder.shipping_address.postal_code].filter(Boolean).join(", ")}</span>
                <span>{selectedOrder.shipping_address.country}</span>
                {selectedOrder.shipping_address.phone_number && <span>{selectedOrder.shipping_address.phone_country_code} {selectedOrder.shipping_address.phone_number}</span>}
              </address> : <p className="muted">No address recorded for this earlier demo order.</p>}
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
             : recipients.length===0 ? <p className="muted">No saved people yet.</p> : peopleByUpcomingBirthday(recipients,occasions).map(p=>{
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
      {session?.user ? <><p>Signed in as {session.user.email}</p><button className="primary-action" onClick={async()=>{await authClient.signOut();setSelectedRecipient("");setRecipients([]);setOccasions([]);setOrders([]);setSelectedOrder(null);setCheckoutAfterLogin(false);setShipping({...initialShipping});sessionStorage.removeItem(checkoutStorageKey);setShowAuth(false);goHome();}}>Sign out</button></> : <>
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
