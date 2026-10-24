"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { ApiError, api, json } from "@/lib/api";

export default function AdminMfaPage() {
  const router = useRouter();
  const [secret, setSecret] = useState("");
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<{ roles: string[]; mfa_enabled: boolean }>("/me")
      .then(user => {
        if (!user.roles.some(role => role === "admin" || role === "super_admin")) {
          setError("Administrator access is required.");
          return;
        }
        if (user.mfa_enabled) {
          router.push("/admin/dashboard");
          return;
        }
        setReady(true);
      })
      .catch(err => {
        if (err instanceof ApiError && err.status === 401) router.push("/admin/login");
        else setError(err instanceof Error ? err.message : "Unable to start MFA setup.");
      });
  }, [router]);

  async function beginSetup() {
    setBusy(true);
    setError("");
    try {
      const result = await api<{ secret: string }>("/auth/mfa/setup", json({}));
      setSecret(result.secret);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start MFA setup.");
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const code = new FormData(event.currentTarget).get("code");
    try {
      await api("/auth/mfa/verify", json({ code }));
      router.push("/admin/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authenticator code could not be verified.");
    } finally {
      setBusy(false);
    }
  }

  return <main className="auth-shell"><section className="auth-panel auth-panel-centered">
    <Link href="/admin/login" className="auth-brand"><span className="admin-brand-icon">GA</span><span><strong>GnkAlgo Trader</strong><small>Administrator security setup</small></span></Link>
    <div className="auth-content"><span className="portal-eyebrow">REQUIRED FOR ADMINISTRATORS</span><h1>Set up multi-factor authentication</h1><p className="auth-description">Add the setup key to your authenticator app, then enter its current six-digit code. Admin APIs remain unavailable until MFA is verified.</p>
      {error && <p className="portal-error" role="alert">{error}</p>}
      {ready && !secret && <button className="portal-primary" disabled={busy} onClick={() => void beginSetup()}>{busy ? "Preparing…" : "Generate authenticator setup key"}</button>}
      {secret && <form className="portal-form" onSubmit={submit}><div className="mfa-secret"><strong>Authenticator setup key</strong><code>{secret}</code><small>This key is shown once. Store it in your authenticator app.</small></div><label>Six-digit code<input name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} required /></label><button className="portal-primary" disabled={busy}>{busy ? "Verifying…" : "Verify and continue"}</button></form>}
      <p className="auth-disclosure">Secret values are encrypted at rest with the server-side application key.</p>
    </div>
  </section></main>;
}
