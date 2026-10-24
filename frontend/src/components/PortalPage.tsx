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
type Broker = { provider: string; label: string; connected: boolean; mode: string };

const titles: Record<Section, { title: string; description: string }> = {
  profile: { title: "Personal profile", description: "Keep the name on your workspace up to date." },
  account: { title: "Account preferences", description: "Manage your account status and display preferences." },
  security: { title: "Security", description: "Review sign-in activity and secure your account." },
  brokers: { title: "Broker connections", description: "Manage the paper-only broker connection for this workspace." },
};

export default function PortalPage({ section }: { section: Section }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [security, setSecurity] = useState<Security | null>(null);
  const [brokers, setBrokers] = useState<Broker[]>([]);
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
      if (section === "brokers") setBrokers((await api<{ connections: Broker[] }>("/settings/brokers")).connections);
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

  async function toggleBroker() {
    if (!brokers[0]) return;
    setBusy(true);
    setError("");
    try {
      await api("/broker", json({ enabled: !brokers[0].connected }));
      await load();
      setMessage("Paper broker connection updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update the paper broker.");
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
      {section === "brokers" && <section className="portal-card"><h2>Available connections</h2><p>Broker credentials and external access tokens are not collected in this paper-trading release.</p>{brokers.map(connection => <div className="broker-row" key={connection.provider}><div><strong>{connection.label}</strong><small>Simulation only · No live orders</small></div><span className={connection.connected ? "badge-verified" : "badge-pending"}>{connection.connected ? "Connected" : "Disconnected"}</span><button className="portal-secondary" disabled={busy} onClick={() => void toggleBroker()}>{connection.connected ? "Disconnect" : "Connect paper broker"}</button></div>)}</section>}
    </div>
  </main>;
}
