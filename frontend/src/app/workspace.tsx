"use client";

import Image from "next/image";
import Link from "next/link";
import { FormEvent, ReactNode, useCallback, useEffect, useRef, useState } from "react";

type User = { id: string; name: string; email: string; roles: string[] };
type Quote = { symbol: string; name: string; price: string; change: number; sector: string };
type Order = { id: string; symbol: string; side: string; quantity: number; price: string; state: string; created_at: string };
type Position = { id: string; symbol: string; quantity: number; average_price: string; ltp: string; pnl: string };
type Strategy = { id: string; name: string; category: string; risk: string; description: string; state: string; allocation: number; color: string };
type Activity = { id: string; action: string; detail: string; created_at: string };
type Research = { id: string; title: string; category: string; body: string; author: string; disclosure: string };
type Ticket = { id: string; subject: string; status: string; message: string };
type Dashboard = { cash: string; equity: string; invested: string; realized_pnl: string; unrealized_pnl: string; active_strategies: number; killed: boolean; broker_connected: boolean; kyc_status: string; positions: Position[]; recent_orders: Order[] };
const nav = ["Overview", "My strategies", "Broker accounts", "Orders", "Positions", "Trade history", "Performance", "Research", "Subscription", "Activity", "Profile", "Support"];
const symbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "ITC"];
const demoQuotes: Quote[] = symbols.map((symbol, i) => ({ symbol, name: ["Reliance Industries", "Tata Consultancy Services", "HDFC Bank", "Infosys", "ICICI Bank", "ITC Limited"][i], price: ["2952.40", "4125.65", "1728.30", "1892.15", "1254.80", "486.25"][i], change: [0.84, -0.32, 1.12, 0.67, 0.92, -0.41][i], sector: ["Energy", "Technology", "Banking", "Technology", "Banking", "Consumer goods"][i] }));
const demoStrategies: Strategy[] = [
  { id: "momentum", name: "Momentum Compass", category: "Trend following", risk: "Moderate", description: "Explore momentum in a simulated equity basket. Configure your allocation and practice with manual paper orders.", state: "stopped", allocation: 100000, color: "green" },
  { id: "mean-reversion", name: "Mean Reversion", category: "Range trading", risk: "High", description: "A research template for studying price deviations. Build a disciplined approach before putting capital at risk.", state: "stopped", allocation: 100000, color: "blue" },
  { id: "balanced", name: "Balanced Basket", category: "Portfolio", risk: "Moderate", description: "Practice allocating virtual capital across an equity basket. Keep your research and risk controls in one place.", state: "stopped", allocation: 100000, color: "amber" },
];
const money = (v: string | number) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(v));
function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, ReactNode> = {
    Overview: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
    "My strategies": <><path d="m3 17 6-6 4 3 8-10M16 4h5v5"/><path d="M3 5v16h18"/></>,
    "Broker accounts": <><path d="M4 10h16M5 20h14M7 10v7m5-7v7m5-7v7M3 7l9-4 9 4z"/></>,
    Orders: <><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h4"/></>,
    Positions: <><rect x="3" y="7" width="18" height="14" rx="2"/><path d="M8 7V3h8v4M3 12h18m-11 0v3h4v-3"/></>,
    Research: <><path d="M12 5v16M3 4l9 1 9-1v15l-9 2-9-2zM6 9l3 1m6 0 3-1"/></>,
    Profile: <><circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/></>,
    Support: <><path d="M4 13v-2a8 8 0 0 1 16 0v2M4 12H2v6h4v-6zm16 0h2v6h-4v-6zM18 18v3h-6"/></>,
    Activity: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></>,
    search: <><circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/></>,
    arrow: <path d="M5 12h14m-5-5 5 5-5 5"/>,
    plus: <path d="M12 5v14M5 12h14"/>,
    shield: <><path d="m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6z"/><path d="m8 12 3 3 5-6"/></>,
    moon: <path d="M20 14A9 9 0 0 1 10 4a9 9 0 1 0 10 10z"/>,
    close: <path d="m6 6 12 12M6 18 18 6"/>,
    logout: <><path d="M10 4H4v16h6m-1-8h12m-4-4 4 4-4 4"/></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || <><path d="M4 20V10m5 10V4m6 16v-7m5 7V7"/></>}</svg>;
}
async function api<T>(path: string, method = "GET", body?: unknown, headers?: Record<string, string>): Promise<T> {
  const res = await fetch(`/api/v1${path}`, { method, credentials: "same-origin", headers: { "Content-Type": "application/json", ...headers }, body: body === undefined ? undefined : JSON.stringify(body), cache: "no-store" });
  const data = await res.json();
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Please check the form values and try again.");
  return data;
}

export default function Workspace() {
  const modalRef = useRef<HTMLElement>(null);
  const [view, setView] = useState("Overview");
  const [user, setUser] = useState<User | null>(null);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [quotes, setQuotes] = useState<Quote[]>(demoQuotes);
  const [strategies, setStrategies] = useState<Strategy[]>(demoStrategies);
  const [orders, setOrders] = useState<Order[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [research, setResearch] = useState<Research[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [admin, setAdmin] = useState<{ users: User[]; audit: Activity[] } | null>(null);
  const [modal, setModal] = useState<"login" | "register" | "order" | "kill" | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [dark, setDark] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [symbol, setSymbol] = useState("RELIANCE");
  const [side, setSide] = useState("BUY");
  const [quantity, setQuantity] = useState(1);
  const [orderKey, setOrderKey] = useState("");

  useEffect(() => {
    if (!modal) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    modalRef.current?.querySelector<HTMLElement>("input,select,button")?.focus();
    return () => { document.body.style.overflow = previousOverflow; previousFocus?.focus(); };
  }, [modal]);

  const refresh = useCallback(async () => {
    const [d, s, o, p, a, r, t] = await Promise.all([api<Dashboard>("/dashboard"), api<Strategy[]>("/strategies"), api<Order[]>("/orders"), api<Position[]>("/positions"), api<Activity[]>("/activity"), api<Research[]>("/research"), api<Ticket[]>("/support")]);
    setDashboard(d); setStrategies(s); setOrders(o); setPositions(p); setActivity(a); setResearch(r); setTickets(t);
  }, []);
  useEffect(() => {
    let active = true;
    async function init() {
      try {
        const market = await api<{ quotes: Quote[] }>("/market");
        if (active) setQuotes(market.quotes);
      } catch { if (active) setNotice("Preview mode · Start the backend to create an account and save paper trades."); }
      try { const current = await api<User>("/me"); if (active) { setUser(current); await refresh(); } } catch { /* A guest can explore the workspace. */ }
      if (active) setLoading(false);
    }
    void init();
    return () => { active = false; };
  }, [refresh]);

  useEffect(() => {
    if (!user) return;
    let active = true;
    void api<{ theme: "light" | "dark" | "system" }>("/settings/account")
      .then(({ theme }) => {
        if (!active) return;
        setDark(theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches));
      })
      .catch(e => {
        if (active) setNotice(e instanceof Error ? e.message : "Unable to load account preferences.");
      });
    return () => { active = false; };
  }, [user]);

  async function action(fn: () => Promise<unknown>, success: string) {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try { await fn(); await refresh(); setNotice(success); } catch (e) { setError(e instanceof Error ? e.message : "Something went wrong. Try again."); } finally { setBusy(false); }
  }
  function requireAuth(fn: () => void) { if (user) fn(); else setModal("register"); }
  function navigate(next: string) { setView(next); setMobileNav(false); setError(""); }
  function newOrder(s = "RELIANCE") { requireAuth(() => { setSymbol(s); setQuantity(1); setSide("BUY"); setOrderKey(crypto.randomUUID()); setModal("order"); setError(""); }); }
  async function auth(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setBusy(true); setError("");
    const form = new FormData(e.currentTarget);
    try {
      const current = await api<User>(`/auth/${modal === "register" ? "register" : "login"}`, "POST", { email: form.get("email"), password: form.get("password"), ...(modal === "register" ? { name: form.get("name") } : {}) });
      setUser(current); await refresh(); setModal(null); setNotice("Your paper workspace is ready.");
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to sign in"); } finally { setBusy(false); }
  }
  async function logout() {
    setBusy(true); setError("");
    try { await api("/auth/logout", "POST"); setUser(null); setDashboard(null); setOrders([]); setPositions([]); setStrategies(demoStrategies); setActivity([]); setResearch([]); setTickets([]); setAdmin(null); setView("Overview"); setNotice("Signed out."); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to sign out"); }
    finally { setBusy(false); }
  }
  const accountEquity = dashboard?.equity || 1000000;
  const used = Number(dashboard?.invested || 0);
  const selected = quotes.find(q => q.symbol === symbol);
  const filteredQuotes = quotes.filter(q => `${q.symbol} ${q.name}`.toLowerCase().includes(search.toLowerCase()));
  const signedIn = (content: ReactNode) => user ? content : <div className="empty"><span className="empty-icon"><Icon name="shield" size={30}/></span><h3>Make this workspace yours</h3><p>Create a free account to save your strategies, orders and trading journal.</p><button className="primary" onClick={() => setModal("register")}>Create paper account <Icon name="arrow" size={16}/></button></div>;
  const orderTable = (rows: Order[]) => <div className="table-scroll"><table><thead><tr><th>Instrument</th><th>Side</th><th>Quantity</th><th>Simulation price</th><th>Status</th><th>Actions</th></tr></thead><tbody>{rows.map(o => <tr key={o.id}><td><strong>{o.symbol}</strong><small>NSE · Paper</small></td><td className={o.side === "BUY" ? "positive" : "negative"}>{o.side}</td><td>{o.quantity}</td><td>{money(o.price)}</td><td><span className={`badge ${o.state === "filled" ? "green" : "neutral"}`}>{o.state}</span></td><td>{o.state === "pending" ? <div className="inline"><button disabled={busy} className="text-button" onClick={() => void action(() => api(`/orders/${o.id}/fill`, "POST"), "Paper fill confirmed; position updated.")}>Simulate fill</button><button disabled={busy} className="text-button muted" onClick={() => void action(() => api(`/orders/${o.id}/cancel`, "POST"), "Order cancelled.")}>Cancel</button></div> : "—"}</td></tr>)}</tbody></table>{rows.length === 0 && <div className="empty compact"><h3>No orders yet</h3><p>Your paper orders will appear here.</p><button className="secondary" onClick={() => newOrder()}>Create a paper order</button></div>}</div>;

  return <div className={`workspace ${dark ? "dark" : ""}`}>
    <aside className={`sidebar ${mobileNav ? "open" : ""}`}>
      <Link className="brand" href="/" aria-label="GNK Algo home"><span className="logo-crop"><Image src="/brand/gnkalgo.png" width={160} height={90} alt="GNK Algo" priority/></span><span>GNK<span className="brand-accent">ALGO</span><small>INTELLIGENCE IN EVERY TRADE</small></span></Link>
      <div className="workspace-label">YOUR WORKSPACE <span className="tiny-pill">PAPER</span></div>
      <nav aria-label="Main navigation">{nav.map((item, i) => <button key={item} className={`${view === item ? "selected" : ""} ${i === 7 || i === 10 ? "nav-gap" : ""}`} aria-current={view === item ? "page" : undefined} onClick={() => navigate(item)}><Icon name={item}/>{item}{item === "My strategies" && <span className="nav-count">{dashboard?.active_strategies || 0}</span>}</button>)}{user?.roles.some(r => ["admin", "super_admin"].includes(r)) && <button className={view === "Admin" ? "selected" : ""} onClick={() => { navigate("Admin"); void action(async () => setAdmin(await api("/admin/overview")), "Admin overview loaded."); }}><Icon name="shield"/>Administration</button>}</nav>
      <div className="sidebar-bottom"><div className="safe-card"><Icon name="shield"/><strong>Build confidence first.</strong><p>Test your ideas with virtual capital. Your real funds stay untouched.</p><button onClick={() => navigate("Research")}>Explore the playbook <Icon name="arrow" size={15}/></button></div><div className="sidebar-domain"><span className="status-dot"/>gnkalgo.com<span>v0.1 · Paper MVP</span></div></div>
    </aside>
    <div className="app-main">
      <header className="topbar"><button className="icon-button menu-toggle" aria-label="Toggle navigation" onClick={() => setMobileNav(!mobileNav)}>☰</button><div className="breadcrumb">Workspace <span>/</span> <strong>{view}</strong></div><div className="top-actions"><span className="paper-label"><span className="status-dot"/>Paper trading</span><button className="icon-button" aria-label="Toggle light and dark theme" onClick={() => setDark(!dark)}><Icon name="moon"/></button><button className="icon-button" aria-label="View activity" onClick={() => navigate("Activity")}><Icon name="Activity"/></button><span className="top-divider"/>{user ? <><button className="user-menu" onClick={() => navigate("Profile")}><span className="avatar">{user.name.charAt(0).toUpperCase()}</span><span>{user.name}<small>Paper account</small></span></button><button className="icon-button" disabled={busy} onClick={() => void logout()} aria-label="Sign out"><Icon name="logout" size={18}/></button></> : <button className="secondary small" onClick={() => setModal("login")}>Sign in <Icon name="arrow" size={15}/></button>}</div></header>
      <div className="market-strip"><span className="market-caption"><span className="status-dot"/>MARKET SNAPSHOT<small>DEMONSTRATION</small></span>{[{ n: "NIFTY 50", v: "24,834.60", c: "+0.62%" }, { n: "SENSEX", v: "81,765.86", c: "+0.58%" }, { n: "BANK NIFTY", v: "52,108.25", c: "+0.91%" }].map(x => <div className="index" key={x.n}><span>{x.n}</span><strong>{x.v}</strong><span className="positive">↗ {x.c}</span></div>)}</div>
      <main>
        <div className="workspace-portal-links"><Link href="/register">Create account</Link><Link href="/login">Account sign in</Link><Link href="/profile">Account center</Link><Link href="/admin/login">Admin portal</Link></div>
        <div className="page-heading"><div><div className="eyebrow">RESEARCH. REFINE. REPEAT.</div><h1>{view === "Overview" ? `Your edge starts here${user ? `, ${user.name.split(" ")[0]}` : ""}.` : view}</h1><p>{view === "Overview" ? "A clear view of your capital, strategies and next move." : "Your decisions. Your discipline. One focused workspace."}</p></div><div className="inline">{user && <button className="icon-button" aria-label="Refresh workspace" disabled={busy} onClick={() => void action(refresh, "Workspace refreshed.")}>↻</button>}<button className="primary" disabled={busy} onClick={() => newOrder()}><Icon name="plus" size={17}/> New paper order</button></div></div>
        <div aria-live="polite">{notice && <div className="message">{notice}<button aria-label="Dismiss notification" onClick={() => setNotice("")}>×</button></div>}{error && !modal && <div className="message error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError("")}>×</button></div>}</div>
        {loading && <div className="loading" role="status">Loading your workspace…</div>}
        {view === "Overview" && <>
          <div className="overview-grid">
            <section className="capital-card"><div className="card-top"><span>YOUR PAPER PORTFOLIO</span><span className="badge glass">Virtual capital</span></div><p className="capital-label">Total account value</p><div className="capital-value">{money(accountEquity)}</div><div className="capital-meta"><span>Available cash <strong>{money(dashboard?.cash || 1000000)}</strong></span><span>Invested <strong>{money(used)}</strong></span></div><div className="capital-footer"><span><Icon name="shield" size={15}/> {user ? "Your paper account" : "Preview · Create an account to begin"}</span><span>INR</span></div></section>
            <section className="stat-card"><div className="stat-icon green"><Icon name="Performance"/></div><p>Realized P&L</p><strong>{money(dashboard?.realized_pnl || 0)}</strong><small>From confirmed paper fills</small><svg className="stat-spark" viewBox="0 0 200 30" aria-label="No change in demonstration prices"><path d="M0 22H200" stroke="currentColor" strokeWidth="2" strokeDasharray="4 4"/></svg></section>
            <section className="stat-card"><div className="stat-icon blue"><Icon name="My strategies"/></div><p>Active configurations</p><strong>{dashboard?.active_strategies || 0}<span className="stat-unit"> / 3</span></strong><small>Manual paper execution</small><div className="mini-progress">{strategies.map(s => <span key={s.id} className={s.state === "active" ? "on" : ""}/>)}</div></section>
            <section className="stat-card"><div className="stat-icon amber"><Icon name="Positions"/></div><p>Open positions</p><strong>{positions.length}<span className="stat-unit"> instruments</span></strong><small>Unrealized {money(dashboard?.unrealized_pnl || 0)}</small><button className="text-button" onClick={() => navigate("Positions")}>View positions <Icon name="arrow" size={15}/></button></section>
          </div>
          <div className="dashboard-columns"><div className="main-column">
            <section className="panel"><div className="panel-heading"><div><h2>Put your ideas into motion</h2><p>Start with a strategy. Stay in control.</p></div><button className="text-button" onClick={() => navigate("My strategies")}>All strategies <Icon name="arrow" size={16}/></button></div><div className="strategy-preview">{strategies.slice(0, 2).map((s, i) => <div className="strategy-mini" key={s.id}><span className={`strategy-symbol ${s.color}`}><Icon name={i === 0 ? "My strategies" : "Performance"} size={24}/></span><span className="badge neutral">{s.category}</span><h3>{s.name}</h3><p>{s.description}</p><div className="strategy-mini-footer"><span><i className={`risk-dot ${s.risk === "High" ? "amber" : "green"}`}/>{s.risk} risk</span><button className="text-button" onClick={() => navigate("My strategies")}>Explore <Icon name="arrow" size={15}/></button></div></div>)}</div><div className="panel-footnote"><Icon name="shield" size={15}/> Configuration templates. No automated signals or historical return claims.</div></section>
            <section className="panel"><div className="panel-heading"><div><h2>Recent orders</h2><p>Every decision, accounted for.</p></div><button className="text-button" onClick={() => navigate("Orders")}>View all <Icon name="arrow" size={15}/></button></div>{orderTable(orders.slice(0, 4))}</section>
            <section className="learning-banner"><span className="learning-icon"><Icon name="Research" size={30}/></span><div><span className="eyebrow">THE GNK PLAYBOOK</span><h3>A good strategy begins with better questions.</h3><p>Understand position sizing, paper execution and your risk limits.</p></div><button className="secondary" onClick={() => navigate("Research")}>Start learning <Icon name="arrow" size={16}/></button></section>
          </div><aside className="right-column"><section className="panel watchlist"><div className="panel-heading"><h2>Market watch</h2><span className="badge neutral">Demo</span></div><label className="search"><Icon name="search" size={17}/><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search instruments" aria-label="Search watchlist"/><span>⌕</span></label>{filteredQuotes.map(q => <button className="watch-row" key={q.symbol} onClick={() => newOrder(q.symbol)}><span className={`stock-avatar ${q.change > 0 ? "green" : "blue"}`}>{q.symbol.slice(0, 2)}</span><span className="stock-name"><strong>{q.symbol}</strong><small>NSE · {q.sector}</small></span><span className="stock-price"><strong>{money(q.price)}</strong><small className={q.change > 0 ? "positive" : "negative"}>{q.change > 0 ? "+" : ""}{q.change.toFixed(2)}%</small></span></button>)}{filteredQuotes.length === 0 && <p className="empty compact">No instruments match.</p>}<div className="panel-footnote">Fixed sample prices · Not a live market feed</div></section><section className="panel risk-panel"><div className="panel-heading"><h2>Risk guardrails</h2><Icon name="shield"/></div><div className="risk-line"><span>Exposure limit</span><strong>₹5,00,000</strong></div><div className="risk-meter"><span style={{ width: `${Math.min(100, used / 500000 * 100)}%` }}/></div><div className="risk-line"><span>Daily realized loss limit</span><strong>₹10,000</strong></div><div className="risk-line"><span>Live trading</span><span className="badge neutral">Disabled</span></div><button className={dashboard?.killed ? "secondary full" : "danger-outline full"} onClick={() => requireAuth(() => setModal("kill"))}>{dashboard?.killed ? "Resume paper trading" : "Pause all paper trading"}</button><small>Pausing cancels pending orders. Existing positions remain open.</small></section></aside></div>
        </>}
        {view === "My strategies" && <><div className="info-strip"><Icon name="shield"/>Strategy activation saves a paper configuration. Automated execution and backtests are not enabled.</div><div className="strategy-grid">{strategies.map(s => <section className="panel strategy-detail" key={s.id}><span className={`strategy-symbol ${s.color}`}><Icon name="My strategies" size={30}/></span><span className="badge neutral">{s.state}</span><h2>{s.name}</h2><p>{s.description}</p><div className="risk-line"><span>Risk profile</span><strong>{s.risk}</strong></div><label>Virtual allocation (INR)<input type="number" min={1000} max={500000} step={1000} value={s.allocation} onChange={e => setStrategies(strategies.map(x => x.id === s.id ? { ...x, allocation: Number(e.target.value) } : x))}/></label><div className="inline"><button disabled={busy} className="primary" onClick={() => requireAuth(() => void action(() => api(`/strategies/${s.id}`, "PATCH", { state: s.state === "active" ? "paused" : "active", allocation: s.allocation }), "Strategy configuration updated."))}>{s.state === "active" ? "Pause" : "Activate"}</button><button disabled={busy || s.state === "stopped"} className="secondary" onClick={() => requireAuth(() => void action(() => api(`/strategies/${s.id}`, "PATCH", { state: "stopped", allocation: s.allocation }), "Strategy stopped."))}>Stop</button></div></section>)}</div></>}
        {(view === "Orders" || view === "Trade history") && signedIn(<section className="panel"><div className="panel-heading"><div><h2>{view === "Orders" ? "Paper order book" : "Confirmed paper executions"}</h2><p>Submission is separate from a simulated fill. Latest 250 orders.</p></div><span className="badge green">Paper only</span></div>{orderTable(view === "Orders" ? orders : orders.filter(o => o.state === "filled"))}</section>)}
        {view === "Positions" && signedIn(<section className="panel"><div className="panel-heading"><h2>Your open paper positions</h2><span>{positions.length} instruments</span></div><div className="table-scroll"><table><thead><tr><th>Instrument</th><th>Quantity</th><th>Average cost</th><th>Sample price</th><th>Unrealized P&L</th></tr></thead><tbody>{positions.map(p => <tr key={p.id}><td><strong>{p.symbol}</strong></td><td>{p.quantity}</td><td>{money(p.average_price)}</td><td>{money(p.ltp)}</td><td className={Number(p.pnl) >= 0 ? "positive" : "negative"}>{money(p.pnl)}</td></tr>)}</tbody></table>{!positions.length && <div className="empty"><h3>A clean slate.</h3><p>Simulate a buy fill to open your first paper position.</p></div>}</div></section>)}
        {view === "Broker accounts" && signedIn(<section className="panel settings-panel"><div className="panel-heading"><div><h2>GNK Paper broker</h2><p>Your simulation account. No brokerage credentials required.</p></div><span className={`badge ${dashboard?.broker_connected ? "green" : "neutral"}`}>{dashboard?.broker_connected ? "Connected" : "Disconnected"}</span></div><div className="broker-art"><Icon name="Broker accounts" size={48}/></div><h3>Practice with ₹10 lakh in virtual capital.</h3><p>Fixed demonstration quotes. No real money, live orders or broker credentials. Live broker adapters are planned.</p><button className="primary" disabled={busy} onClick={() => void action(() => api("/broker", "POST", { enabled: !dashboard?.broker_connected }), "Paper broker connection updated.")}>{dashboard?.broker_connected ? "Disconnect paper broker" : "Connect paper broker"}</button></section>)}
        {view === "Performance" && signedIn(<section className="panel settings-panel"><div className="panel-heading"><h2>Paper performance</h2><span className="badge neutral">Since account creation</span></div><div className="performance-grid"><div><p>Account equity</p><h2>{money(accountEquity)}</h2></div><div><p>Realized P&L</p><h2>{money(dashboard?.realized_pnl || 0)}</h2></div><div><p>Unrealized P&L</p><h2>{money(dashboard?.unrealized_pnl || 0)}</h2></div></div><h3>Capital allocation</h3><div className="allocation-bar"><span style={{ width: `${used / Number(accountEquity) * 100}%` }}/></div><p>{money(used)} invested · {money(dashboard?.cash || 0)} cash</p><div className="info-strip">Historical equity snapshots, fees, slippage and risk-adjusted returns are not implemented. Fixed sample prices do not represent market performance.</div></section>)}
        {view === "Research" && signedIn(<div className="research-grid">{research.map(r => <article className="panel research-card" key={r.id}><span className="badge green">{r.category}</span><div className="research-art"><Icon name="Research" size={60}/></div><h2>{r.title}</h2><p>{r.body}</p><small>{r.author}</small><div className="panel-footnote">{r.disclosure}</div></article>)}</div>)}
        {view === "Subscription" && signedIn(<section className="panel settings-panel"><span className="badge green">YOUR CURRENT PLAN</span><h2>Room to learn. Space to grow.</h2><p>The paper workspace is free. Payments and paid plans are not available in this release.</p><div className="plan-price">₹0 <small>/ paper workspace</small></div>{["₹10 lakh virtual starting capital", "Manual paper orders and positions", "Three strategy configuration templates", "Educational research and audit history"].map(x => <p key={x} className="plan-feature"><span className="positive">✓</span>{x}</p>)}<span className="badge neutral">Active · No payment details collected</span></section>)}
        {view === "Activity" && signedIn(<section className="panel"><div className="panel-heading"><h2>Your audit trail</h2><span>Latest 100 events</span></div>{activity.map(a => <div className="activity-row" key={a.id}><span className="activity-icon"><Icon name="Activity" size={18}/></span><div><strong>{a.action.replaceAll(".", " ")}</strong><p>{a.detail || "Account event recorded"}</p></div><time>{new Date(a.created_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })} IST</time></div>)}</section>)}
        {view === "Profile" && signedIn(<section className="panel settings-panel"><div className="panel-heading"><div><h2>Profile & onboarding</h2><p>{user?.email}</p></div><span className="badge neutral">{dashboard?.kyc_status.replaceAll("_", " ")}</span></div><form onSubmit={e => { e.preventDefault(); const form = new FormData(e.currentTarget); void action(async () => { await api("/onboarding", "POST", { name: form.get("name"), consent: form.get("consent") === "on" }); setUser(await api<User>("/me")); }, "Profile and simulation consent saved."); }}><label>Your name<input name="name" minLength={2} maxLength={80} defaultValue={user?.name} required/></label><label className="checkbox"><input type="checkbox" name="consent" required/>I understand this workspace uses virtual capital and fixed demonstration prices.</label><button className="primary" disabled={busy}>Save profile & consent</button></form><div className="info-strip">This is profile onboarding, not identity verification. KYC identity checks and document review are not available in this release. Manage your profile, email verification, password, MFA and active sessions in the <Link href="/settings/security">account security center</Link>.</div></section>)}
        {view === "Support" && signedIn(<div className="research-grid"><section className="panel settings-panel"><h2>How can we help?</h2><p>Save a support request for the platform administrator. Email delivery is not connected.</p><form onSubmit={e => { e.preventDefault(); const element = e.currentTarget; const f = new FormData(element); void action(async () => { await api("/support", "POST", { subject: f.get("subject"), message: f.get("message") }); element.reset(); }, "Support request saved."); }}><label>Subject<input name="subject" minLength={5} maxLength={160} required/></label><label>Message<textarea name="message" minLength={10} maxLength={4000} rows={5} required/></label><button className="primary" disabled={busy}>Save request <Icon name="arrow" size={16}/></button></form></section><section className="panel settings-panel"><h2>Your requests</h2>{tickets.length ? tickets.map(t => <div className="ticket" key={t.id}><span className="badge neutral">{t.status}</span><h3>{t.subject}</h3><p>{t.message}</p></div>) : <p>No support requests yet.</p>}</section></div>)}
        {view === "Admin" && signedIn(<section className="panel settings-panel"><h2>Administration</h2><p>Read-only overview for authorized administrators. User and KYC management actions are pending.</p>{admin ? <><h3>Registered users</h3><div className="table-scroll"><table><thead><tr><th>Name</th><th>Email</th><th>ID</th></tr></thead><tbody>{admin.users.map(u => <tr key={u.id}><td>{u.name}</td><td>{u.email}</td><td>{u.id}</td></tr>)}</tbody></table></div><h3>System audit</h3>{admin.audit.map(a => <div className="activity-row" key={a.id}><strong>{a.action}</strong><span>{a.detail}</span></div>)}</> : <p>Loading authorized overview…</p>}</section>)}
        <footer className="app-footer"><span>© {new Date().getFullYear()} GNK Algo <span>·</span> Intelligence behind every trade.</span><span><span className="status-dot"/>Paper simulation · Live trading disabled</span></footer>
      </main>
    </div>
    {modal && <div className="modal-backdrop" onClick={e => { if (e.target === e.currentTarget && !busy) { setModal(null); setError(""); } }}><section ref={modalRef} className="modal" onKeyDown={e => {
      if (e.key === "Escape" && !busy) { setModal(null); setError(""); }
      if (e.key === "Tab") {
        const elements = modalRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input,select,textarea,[tabindex="0"]');
        if (!elements?.length) return;
        const first = elements[0], last = elements[elements.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    }} role="dialog" aria-modal="true" aria-labelledby="modal-title"><button className="modal-close icon-button" disabled={busy} aria-label="Close dialog" onClick={() => { setModal(null); setError(""); }}><Icon name="close"/></button>
      {(modal === "login" || modal === "register") && <><span className="eyebrow">WELCOME TO GNK ALGO</span><h2 id="modal-title">{modal === "register" ? "Build your trading discipline." : "Your workspace awaits."}</h2><p>Paper trading. Real learning. Start with ₹10 lakh in virtual capital.</p><form onSubmit={auth}>{modal === "register" && <label>Name<input name="name" autoComplete="name" minLength={2} maxLength={80} required autoFocus/></label>}<label>Email<input name="email" type="email" autoComplete="email" required autoFocus={modal === "login"}/></label><label>Password<input name="password" type="password" autoComplete={modal === "register" ? "new-password" : "current-password"} minLength={modal === "register" ? 12 : 1} maxLength={128} required/>{modal === "register" && <small>Use at least 12 characters.</small>}</label><button className="primary full" disabled={busy}>{busy ? "Please wait…" : modal === "register" ? "Create paper account" : "Sign in"}<Icon name="arrow" size={16}/></button></form><button className="text-button auth-switch" disabled={busy} onClick={() => { setModal(modal === "register" ? "login" : "register"); setError(""); }}>{modal === "register" ? "Already registered? Sign in" : "New here? Create an account"}</button></>}
      {modal === "order" && <><span className="badge green">PAPER TRADING</span><h2 id="modal-title">Create a paper order</h2><p>Your order stays pending until you simulate its fill. Prices are fixed demonstration values.</p><form onSubmit={e => { e.preventDefault(); void action(async () => { await api("/orders", "POST", { symbol, side, quantity }, { "Idempotency-Key": orderKey }); setModal(null); setView("Orders"); }, "Paper order submitted. Simulate a fill to update your position."); }}><label>Instrument<select value={symbol} onChange={e => { setSymbol(e.target.value); setOrderKey(crypto.randomUUID()); }}>{quotes.map(q => <option key={q.symbol}>{q.symbol}</option>)}</select></label><div className="form-columns"><label>Side<select value={side} onChange={e => { setSide(e.target.value); setOrderKey(crypto.randomUUID()); }}><option>BUY</option><option>SELL</option></select></label><label>Quantity<input type="number" min={1} max={1000} step={1} value={quantity} onChange={e => { setQuantity(Number(e.target.value)); setOrderKey(crypto.randomUUID()); }} required/></label></div><div className="order-estimate"><span>Estimated virtual value</span><strong>{money(Number(selected?.price || 0) * quantity)}</strong></div><button className="primary full" disabled={busy}>{busy ? "Submitting…" : `Submit paper ${side.toLowerCase()}`}<Icon name="arrow" size={17}/></button></form></>}
      {modal === "kill" && <><span className="eyebrow">RISK CONTROL</span><h2 id="modal-title">{dashboard?.killed ? "Resume paper trading?" : "Pause all paper trading?"}</h2><p>{dashboard?.killed ? "You can submit new paper orders again. Paused strategies must be resumed individually." : "This cancels pending orders and pauses active strategy configurations. Existing positions stay open."}</p><button className="primary full" disabled={busy} onClick={() => void action(async () => { await api("/risk/kill-switch", "POST", { enabled: !dashboard?.killed }); setModal(null); }, "Paper trading controls updated.")}>Confirm {dashboard?.killed ? "resume" : "pause"}</button></>}
      {error && <p className="message error" role="alert">{error}</p>}
    </section></div>}
  </div>;
}
