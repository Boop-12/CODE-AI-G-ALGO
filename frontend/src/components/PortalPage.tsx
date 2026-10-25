"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, api, json } from "@/lib/api";

type Section = "profile" | "account" | "security" | "brokers";
type User = { name: string; email: string; email_verified: boolean; theme: string; mfa_enabled: boolean };
type Security = {
  mfa_enabled: boolean;
  sessions: { id: string; current: boolean; created_at: string; expires_at: string; ip_address: string | null; user_agent: string | null }[];
  login_history: { id: string; created_at: string; ip_address: string | null; user_agent: string | null }[];
};
type BrokerProvider = {
  id: string; name: string; available: boolean;
  capabilities: { account_summary: boolean; holdings: boolean; positions: boolean; order_status: boolean; order_placement: boolean } | null;
};
type Broker = {
  provider: string; label: string; connected: boolean; status: string; mode: string;
  expires_at: string | null; last_health_check_at: string | null; last_synced_at: string | null;
  last_sync_status: string | null; last_sync_error: string | null;
};
type BrokerSnapshot = {
  provider: string; fetched_at: string; sync_status: string;
  account: { currency: string; account_name?: string | null; available_balance: string; equity?: string };
  holdings: { exchange: string | null; symbol: string | null; quantity: number; average_price: string; last_price: string }[];
  positions: { exchange: string | null; symbol: string | null; quantity: number; unrealized_pnl?: string }[];
  orders: { order_id: string; exchange: string; symbol: string; status: string }[];
};
type MockBrokerSnapshot = {
  synced_at: string; sync_status: string;
  account: { currency: string; cash: string; equity: string; invested: string };
  positions: { exchange: string; symbol: string; quantity: number; unrealized_pnl: string }[];
  orders: { order_id: string; exchange: string; symbol: string; status: string }[];
};

const titles: Record<Section, { title: string; description: string }> = {
  profile: { title: "Personal profile", description: "Keep the name on your workspace up to date." },
  account: { title: "Account preferences", description: "Manage your account status and display preferences." },
  security: { title: "Security", description: "Review sign-in activity and secure your account." },
  brokers: { title: "Broker connections", description: "Manage server-side, read-only production broker connections." },
};

export default function PortalPage({ section }: { section: Section }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [security, setSecurity] = useState<Security | null>(null);
  const [brokers, setBrokers] = useState<Broker[]>([]);
  const [brokerProviders, setBrokerProviders] = useState<BrokerProvider[]>([]);
  const [brokerSnapshot, setBrokerSnapshot] = useState<BrokerSnapshot | null>(null);
  const [snapshotProvider, setSnapshotProvider] = useState("");
  const [mockBrokerSnapshot, setMockBrokerSnapshot] = useState<MockBrokerSnapshot | null>(null);
  const [mfaSecret, setMfaSecret] = useState("");
  const [verificationLink, setVerificationLink] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const current = await api<User>("/profile");
      setUser(current);
      if (section === "security") setSecurity(await api<Security>("/settings/security"));
      if (section === "brokers") {
        const result = await api<{ connections: Broker[]; providers: BrokerProvider[] }>("/settings/brokers");
        setBrokers(result.connections);
        setBrokerProviders(result.providers);
        const params = new URLSearchParams(window.location.search);
        const provider = params.get("provider");
        const state = params.get("connection");
        if (provider && state) {
          setMessage(state === "connected" ? `${provider} account connected.` :
            state === "cancelled" ? `${provider} authorization was cancelled.` :
              `${provider} authorization failed. Check the broker setup and try again.`);
          window.history.replaceState({}, "", window.location.pathname);
        }
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) router.push("/login");
      else setError(err instanceof Error ? err.message : "Unable to load account settings.");
    }
  }, [router, section]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    const values = new FormData(event.currentTarget);
    try {
      if (section === "profile") {
        const updated = await api<User>("/profile", { ...json({ name: values.get("name") }), method: "PATCH" });
        setUser({ ...user!, ...updated });
        setMessage("Profile saved.");
      } else if (section === "account") {
        await api("/settings/account", { ...json({ theme: values.get("theme") }), method: "PATCH" });
        setMessage("Account preferences saved.");
      } else if (section === "security") {
        const result = await api<{ sessions_revoked: number }>("/settings/security/password", { ...json({ current_password: values.get("current_password"), new_password: values.get("new_password") }), method: "PATCH" });
        setMessage(`Password updated. ${result.sessions_revoked} active sessions signed out; sign in again on this device.`);
        await api("/auth/logout", json({}));
        router.push("/login");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save your changes.");
    } finally {
      setBusy(false);
    }
  }

  async function connectBroker(provider: string) {
    setBusy(true);
    setError("");
    try {
      const result = await api<{ authorization_url: string }>(`/broker/${provider}/connect`, json({}));
      window.location.assign(result.authorization_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start broker authorization.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleMockBroker(connected: boolean) {
    setBusy(true);
    setError("");
    try {
      if (connected) await api("/broker/disconnect", json({}));
      else await api("/broker/connect", json({ provider: "mock" }));
      await load();
      setMessage(connected ? "Mock broker disconnected." : "Mock paper broker connected.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update the mock broker.");
    } finally {
      setBusy(false);
    }
  }

  async function syncMockBroker() {
    setBusy(true);
    setError("");
    try {
      const result = await api<MockBrokerSnapshot>("/broker/sync", json({}));
      setMockBrokerSnapshot(result);
      await load();
      setMessage("Mock paper account synchronized.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to synchronize the mock broker.");
    } finally {
      setBusy(false);
    }
  }

  async function checkMockBrokerHealth() {
    setBusy(true);
    setError("");
    try {
      const result = await api<{ status: string }>("/broker/health");
      await load();
      setMessage(`Mock broker health: ${result.status}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to check the mock broker connection.");
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function disconnectBroker(provider: string) {
    setBusy(true);
    setError("");
    try {
      await api(`/broker/${provider}/disconnect`, json({}));
      setBrokerSnapshot(null);
      await load();
      setMessage(`${provider} disconnected. The locally stored token was deleted; revoke the application from your broker account if provider-side revocation is required.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to disconnect the broker.");
    } finally {
      setBusy(false);
    }
  }

  async function syncBroker(provider: string) {
    setBusy(true);
    setError("");
    try {
      const result = await api<BrokerSnapshot>(`/broker/${provider}/sync`, json({}));
      setBrokerSnapshot(result);
      setSnapshotProvider(provider);
      await load();
      setMessage(`${provider} account data synchronized.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to synchronize the broker account.");
    } finally {
      setBusy(false);
    }
  }

  async function checkBrokerHealth(provider: string) {
    setBusy(true);
    setError("");
    try {
      const result = await api<{ status: string }>(`/broker/${provider}/health`);
      await load();
      setMessage(`${provider} broker health: ${result.status}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to check the broker connection.");
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function beginMfa() {
    setError("");
    setMessage("");
    try {
      const result = await api<{ secret: string }>("/auth/mfa/setup", json({}));
      setMfaSecret(result.secret);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start MFA setup.");
    }
  }

  async function verifyMfa(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const code = new FormData(event.currentTarget).get("code");
    try {
      await api("/auth/mfa/verify", json({ code }));
      setMfaSecret("");
      await load();
      setMessage("Multi-factor authentication is enabled.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authenticator code could not be verified.");
    } finally {
      setBusy(false);
    }
  }

  async function disableMfa(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const code = new FormData(event.currentTarget).get("code");
    try {
      await api("/auth/mfa/disable", json({ code }));
      await load();
      setMessage("Multi-factor authentication was disabled. Administrator access now requires completing setup again.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authenticator code could not be verified.");
    } finally {
      setBusy(false);
    }
  }

  async function revokeSession(id: string) {
    setError("");
    try {
      await api(`/settings/security/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
      await load();
      setMessage("Session revoked.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to revoke this session.");
    }
  }

  const info = titles[section];
  return <main className="portal-shell">
    <header className="portal-top"><Link href="/dashboard" className="portal-brand">Gnk<span>Algo</span> Trader</Link><nav aria-label="Account navigation"><Link href="/dashboard">Workspace</Link><Link href="/profile">Profile</Link><Link href="/settings/account">Account</Link><Link href="/settings/security">Security</Link><Link href="/settings/brokers">Brokers</Link></nav></header>
    <div className="portal-content">
      <p className="portal-eyebrow">ACCOUNT CENTER</p><h1>{info.title}</h1><p className="portal-subtitle">{info.description}</p>
      <div aria-live="polite">{message && <p className="portal-success">{message}</p>}{error && <p className="portal-error" role="alert">{error}</p>}</div>
      {section === "profile" && <section className="portal-card">
        <h2>Personal details</h2><p>Your account email is used for sign-in and verification.</p>
        {user && <form className="portal-form" onSubmit={save}><label>Full name<input name="name" defaultValue={user.name} required minLength={2} maxLength={80} /></label><label>Email address<span className="profile-email"><input value={user.email} readOnly /><span className={user.email_verified ? "badge-verified" : "badge-pending"}>{user.email_verified ? "Verified" : "Unverified"}</span></span></label>{!user.email_verified && <button className="portal-secondary" type="button" onClick={async () => { try { const result = await api<{ development_url?: string }>("/auth/resend-verification", json({})); setVerificationLink(result.development_url ?? ""); setMessage(result.development_url ? "Use this development link to verify your email." : "A verification link was sent if email delivery is configured."); } catch (err) { setError(err instanceof Error ? err.message : "Unable to send verification email."); } }}>Send verification link</button>}<button className="portal-primary" disabled={busy}>{busy ? "Saving…" : "Save profile"}</button></form>}
        {verificationLink && <a className="dev-link" href={verificationLink}>Open development verification link</a>}
      </section>}
      {section === "account" && <section className="portal-card"><h2>Display preferences</h2><p>Choose how your workspace looks. The selection is stored on your account.</p>{user && <form className="portal-form" onSubmit={save}><label>Theme<select name="theme" defaultValue={user.theme}><option value="system">Use device setting</option><option value="light">Light</option><option value="dark">Dark</option></select></label><div className="portal-readonly"><span>Account email</span><strong>{user.email}</strong></div><div className="portal-readonly"><span>Email verification</span><strong>{user.email_verified ? "Verified" : "Pending"}</strong></div><button className="portal-primary" disabled={busy}>{busy ? "Saving…" : "Save preferences"}</button></form>}</section>}
      {section === "security" && <div className="portal-stack">
        <section className="portal-card"><div className="portal-card-heading"><div><h2>Password</h2><p>Use a unique password with at least 12 characters.</p></div></div><form className="portal-form" onSubmit={save}><label>Current password<input name="current_password" type="password" autoComplete="current-password" required /></label><label>New password<input name="new_password" type="password" autoComplete="new-password" minLength={12} maxLength={128} required /></label><button className="portal-primary" disabled={busy}>{busy ? "Updating…" : "Update password"}</button></form></section>
        <section className="portal-card"><div className="portal-card-heading"><div><h2>Multi-factor authentication</h2><p>{security?.mfa_enabled ? "Your account is protected with an authenticator app." : "Add an authenticator app for another layer of protection."}</p></div><span className={security?.mfa_enabled ? "badge-verified" : "badge-pending"}>{security?.mfa_enabled ? "Enabled" : "Not enabled"}</span></div>{!security?.mfa_enabled && !mfaSecret && <button className="portal-secondary" onClick={beginMfa}>Set up authenticator</button>}{mfaSecret && <form className="portal-form" onSubmit={verifyMfa}><div className="mfa-secret"><strong>Authenticator setup key</strong><code>{mfaSecret}</code><small>Enter this key in your authenticator app, then confirm a current six-digit code.</small></div><label>Authenticator code<input name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} required /></label><button className="portal-primary" disabled={busy}>{busy ? "Verifying…" : "Verify and enable MFA"}</button></form>}{security?.mfa_enabled && <form className="portal-form" onSubmit={disableMfa}><label>Current authenticator code<input name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} required /></label><button className="portal-secondary" disabled={busy}>{busy ? "Checking…" : "Disable MFA"}</button></form>}</section>
        <section className="portal-card"><h2>Active sessions</h2><p>Sessions use secure, HttpOnly cookies and are not stored in browser storage.</p>{security?.sessions.length ? security.sessions.map(session => <div className="session-row" key={session.id}><div><strong>{session.current ? "This device" : "Signed-in session"}</strong><small>{session.user_agent || "Unknown device"} · {session.ip_address || "IP unavailable"}</small><small>Signed in {new Date(session.created_at).toLocaleString()}</small></div>{session.current ? <span className="current-session">Current</span> : <button className="text-button" onClick={() => void revokeSession(session.id)}>Revoke</button>}</div>) : <p>No active sessions found.</p>}</section>
        <section className="portal-card"><h2>Recent login history</h2>{security?.login_history.length ? security.login_history.map(entry => <div className="session-row" key={entry.id}><div><strong>{new Date(entry.created_at).toLocaleString()}</strong><small>{entry.user_agent || "Unknown device"} · {entry.ip_address || "IP unavailable"}</small></div><span className="current-session">Successful</span></div>) : <p>No recent successful sign-ins found.</p>}</section>
      </div>}
      {section === "brokers" && <div className="portal-stack">
        {brokerProviders.some(provider => provider.id === "mock") ? <div className="portal-stack">
          <section className="portal-card"><h2>Broker connections</h2><p>Only the local mock broker is available. Zerodha, Dhan and FYERS are listed for planning and do not accept credentials or connect to external services. Live order placement is disabled.</p>
            {brokerProviders.map(provider => {
              const connection = brokers.find(item => item.provider === provider.id);
              return <div className="broker-row" key={provider.id}>
                <div><strong>{provider.name}</strong><small>{provider.available ? "NSE/BSE paper simulation · INR · Equities and ETFs" : "Not implemented · No credentials collected"}</small>{connection && <small>Status: {connection.status}{connection.last_health_check_at ? ` · Health checked ${new Date(connection.last_health_check_at).toLocaleString()}` : ""}{connection.last_synced_at ? ` · Last sync ${new Date(connection.last_synced_at).toLocaleString()}` : ""}{connection.last_sync_error ? ` · ${connection.last_sync_error.replaceAll("_", " ")}` : ""}</small>}</div>
                <span className={connection?.connected ? "badge-verified" : "badge-pending"}>{connection?.status || "unavailable"}</span>
                {provider.available && <div className="inline">
                  {connection?.connected && <button className="portal-secondary" disabled={busy} onClick={() => void syncMockBroker()}>{busy ? "Syncing…" : "Sync paper data"}</button>}
                  {connection?.connected && <button className="portal-secondary" disabled={busy} onClick={() => void checkMockBrokerHealth()}>Check health</button>}
                  <button className="portal-secondary" disabled={busy} onClick={() => void toggleMockBroker(Boolean(connection?.connected))}>{connection?.connected ? "Disconnect" : "Connect mock broker"}</button>
                </div>}
              </div>;
            })}
            <p className="portal-readonly">Mock authorization is local and expires after eight hours. No access token or broker credential is sent to or stored in the browser.</p>
          </section>
          {mockBrokerSnapshot && <section className="portal-card"><h2>Last mock synchronization</h2><p>Read-only mirror of this account’s paper ledger · {new Date(mockBrokerSnapshot.synced_at).toLocaleString()}</p><div className="portal-readonly"><span>Cash</span><strong>{mockBrokerSnapshot.account.currency} {mockBrokerSnapshot.account.cash}</strong></div><div className="portal-readonly"><span>Equity</span><strong>{mockBrokerSnapshot.account.currency} {mockBrokerSnapshot.account.equity}</strong></div><div className="portal-readonly"><span>Invested</span><strong>{mockBrokerSnapshot.account.currency} {mockBrokerSnapshot.account.invested}</strong></div><h3>Holdings and positions</h3>{mockBrokerSnapshot.positions.length ? mockBrokerSnapshot.positions.map(item => <div className="session-row" key={`${item.exchange}:${item.symbol}`}><div><strong>{item.exchange}:{item.symbol}</strong><small>{item.quantity} shares · P&amp;L {mockBrokerSnapshot.account.currency} {item.unrealized_pnl}</small></div></div>) : <p>No paper holdings yet.</p>}<h3>Paper order statuses</h3>{mockBrokerSnapshot.orders.slice(0, 10).map(item => <div className="session-row" key={item.order_id}><strong>{item.exchange}:{item.symbol}</strong><span className="current-session">{item.status}</span></div>)}</section>}
        </div> : <div className="portal-stack">
        <section className="portal-card"><h2>Broker connections</h2><p>Production connections are read-only: account balances, holdings, positions, and broker order statuses. This application does not submit live orders. Broker credentials and access tokens stay on the server.</p>
          {brokerProviders.map(provider => {
            const connection = brokers.find(item => item.provider === provider.id);
            return <div className="broker-row" key={provider.id}>
              <div><strong>{provider.name}</strong><small>{provider.available ? "Read-only production account integration · INR" : "Not configured on this server"}</small>{connection && <small>Status: {connection.status}{connection.last_health_check_at ? ` · Health checked ${new Date(connection.last_health_check_at).toLocaleString()}` : ""}{connection.last_synced_at ? ` · Last sync ${new Date(connection.last_synced_at).toLocaleString()}` : ""}{connection.last_sync_error ? ` · ${connection.last_sync_error.replaceAll("_", " ")}` : ""}</small>}</div>
              <span className={connection?.connected ? "badge-verified" : "badge-pending"}>{connection?.status || (provider.available ? "disconnected" : "unavailable")}</span>
              {provider.available && <div className="inline">
                {connection?.connected && <button className="portal-secondary" disabled={busy} onClick={() => void syncBroker(provider.id)}>{busy ? "Syncing…" : "Sync account data"}</button>}
                {connection?.connected && <button className="portal-secondary" disabled={busy} onClick={() => void checkBrokerHealth(provider.id)}>Check health</button>}
                {!connection?.connected && <button className="portal-secondary" disabled={busy} onClick={() => void connectBroker(provider.id)}>{connection?.status === "expired" ? "Reconnect account" : "Connect account"}</button>}
              </div>}
              {!provider.available && connection && connection.status !== "disconnected" && <button className="portal-secondary" disabled={busy} onClick={() => void disconnectBroker(provider.id)}>Delete stored connection</button>}
              {provider.available && connection?.connected && <button className="portal-secondary" disabled={busy} onClick={() => void disconnectBroker(provider.id)}>Disconnect</button>}
            </div>;
          })}
          <p className="portal-readonly">A disconnect deletes the server-stored token. If the provider does not expose a verified revoke endpoint, revoke the app separately from your broker account. Connection availability depends on server-side credentials and provider approval.</p>
        </section>
        {brokerSnapshot && <section className="portal-card"><h2>{snapshotProvider} account snapshot</h2><p>Read-only provider data · {new Date(brokerSnapshot.fetched_at).toLocaleString()}</p>{brokerSnapshot.account.account_name && <div className="portal-readonly"><span>Account</span><strong>{brokerSnapshot.account.account_name}</strong></div>}<div className="portal-readonly"><span>Available balance</span><strong>{brokerSnapshot.account.currency} {brokerSnapshot.account.available_balance}</strong></div>{brokerSnapshot.account.equity && <div className="portal-readonly"><span>Equity</span><strong>{brokerSnapshot.account.currency} {brokerSnapshot.account.equity}</strong></div>}<h3>Holdings</h3>{brokerSnapshot.holdings.length ? brokerSnapshot.holdings.map((item, index) => <div className="session-row" key={`${item.exchange}:${item.symbol}:${index}`}><div><strong>{item.exchange || "Exchange"}:{item.symbol || "Instrument"}</strong><small>{item.quantity} units · average {brokerSnapshot.account.currency} {item.average_price} · last {brokerSnapshot.account.currency} {item.last_price}</small></div></div>) : <p>No holdings reported.</p>}<h3>Positions</h3>{brokerSnapshot.positions.length ? brokerSnapshot.positions.map((item, index) => <div className="session-row" key={`${item.exchange}:${item.symbol}:${index}`}><div><strong>{item.exchange || "Exchange"}:{item.symbol || "Instrument"}</strong><small>{item.quantity} units{item.unrealized_pnl ? ` · P&L ${brokerSnapshot.account.currency} ${item.unrealized_pnl}` : ""}</small></div></div>) : <p>No positions reported.</p>}<h3>Recent order statuses</h3>{brokerSnapshot.orders.slice(0, 10).map(item => <div className="session-row" key={item.order_id}><strong>{item.exchange}:{item.symbol}</strong><span className="current-session">{item.status}</span></div>)}</section>}
        </div>}
      </div>}
    </div>
  </main>;
}
