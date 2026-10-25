"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api, json } from "@/lib/api";

type Mode = "login" | "register" | "forgot-password" | "reset-password" | "verify-email" | "admin-login";
type AuthResult = { roles: string[]; mfa_enabled?: boolean; development_verification_url?: string; verification_sent?: boolean };

const copy: Record<Mode, { eyebrow: string; title: string; description: string; submit: string }> = {
  login: { eyebrow: "WELCOME BACK", title: "Sign in to your workspace", description: "Your paper portfolio and trading research are ready when you are.", submit: "Sign in" },
  register: { eyebrow: "START PRACTICING", title: "Create your account", description: "Build confidence with a paper-trading workspace. No real funds are used.", submit: "Create account" },
  "forgot-password": { eyebrow: "ACCOUNT RECOVERY", title: "Reset your password", description: "Enter your account email and weâ€™ll send a secure reset link.", submit: "Send reset link" },
  "reset-password": { eyebrow: "ACCOUNT RECOVERY", title: "Choose a new password", description: "Use at least 12 characters. Reset links expire after 30 minutes.", submit: "Save new password" },
  "verify-email": { eyebrow: "EMAIL VERIFICATION", title: "Verify your email", description: "Confirm your email address to keep your account details current.", submit: "Verify email" },
  "admin-login": { eyebrow: "SECURE ADMINISTRATION", title: "Administrator sign in", description: "Administrator accounts require an authenticator code after MFA is enabled.", submit: "Continue to admin portal" },
};

export default function AuthPage({ mode }: { mode: Mode }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [link, setLink] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [verified, setVerified] = useState(false);
  const details = copy[mode];

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    const values = new FormData(event.currentTarget);
    const actionToken = new URLSearchParams(window.location.hash.slice(1)).get("token")
      ?? new URLSearchParams(window.location.search).get("token") ?? "";
    try {
      if (mode === "login" || mode === "admin-login") {
        const user = await api<AuthResult>("/auth/login", json({
          email: values.get("email"),
          password: values.get("password"),
          mfa_code: values.get("mfa_code") || undefined,
        }));
        if (mode === "admin-login") {
          if (!user.roles?.some(role => role === "admin" || role === "super_admin")) throw new Error("Administrator access is required.");
          router.push(user.mfa_enabled ? "/admin/dashboard" : "/admin/mfa");
        } else {
          router.push("/dashboard");
        }
      } else if (mode === "register") {
        const result = await api<AuthResult & { development_verification_url?: string }>("/auth/register", json({
          name: values.get("name"),
          email: values.get("email"),
          password: values.get("password"),
        }));
        setLink(result.development_verification_url ?? "");
        setNotice(result.verification_sent ? "Your account is ready. Check your inbox to verify your email." : "Your account is ready, but email delivery is unavailable. Configure SMTP to deliver verification messages.");
      } else if (mode === "forgot-password") {
        const result = await api<{ development_url?: string }>("/auth/forgot-password", json({ email: values.get("email") }));
        setLink(result.development_url ?? "");
        setNotice("If an account matches that email, a password reset link has been sent.");
      } else if (mode === "reset-password") {
        if (!actionToken) throw new Error("The reset link is missing or invalid.");
        await api("/auth/reset-password", json({ token: actionToken, new_password: values.get("password") }));
        setNotice("Password updated. You can now sign in with your new password.");
      } else if (mode === "verify-email") {
        if (!actionToken) throw new Error("The verification link is missing or invalid.");
        await api("/auth/verify-email", json({ token: actionToken }));
        setVerified(true);
        setNotice("Email verified. Your account is ready.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "The request could not be completed.");
    } finally {
      setBusy(false);
    }
  }

  const needsEmail = ["login", "register", "forgot-password", "admin-login"].includes(mode);
  const needsPassword = ["login", "register", "reset-password", "admin-login"].includes(mode);

  return <main className="auth-shell">
    <div className="auth-art" aria-hidden="true">
      <Image src="/brand/gnkalgo.png" alt="" fill priority sizes="(max-width: 900px) 0px, 58vw" />
      <div className="auth-art-overlay"><span className="auth-mark">GNK<span>ALGO</span></span><p>Intelligence behind every trade.</p></div>
    </div>
    <section className="auth-panel">
      <Link href="/" className="auth-brand" aria-label="GnkAlgo Trader home">
        <Image src="/brand/gnkalgo.png" alt="GnkAlgo Trader" width={46} height={46} priority />
        <span><strong>GnkAlgo Trader</strong><small>Intelligence Behind Every Trade</small></span>
      </Link>
      <div className="auth-content">
        <span className="portal-eyebrow">{details.eyebrow}</span>
        <h1>{details.title}</h1>
        <p className="auth-description">{details.description}</p>
        {mode === "verify-email" && verified ? <div className="auth-success" role="status">{notice}</div> : null}
        {notice && mode !== "verify-email" && <div className="auth-success" role="status">{notice}</div>}
        {link && <a className="dev-link" href={link}>Open development-only email link</a>}
        {!notice || mode === "login" || mode === "admin-login" ? <form className="portal-form" onSubmit={submit}>
          {mode === "register" && <label>Full name<input name="name" required minLength={2} maxLength={80} autoComplete="name" placeholder="Your name" /></label>}
          {needsEmail && <label>Email address<input name="email" type="email" required autoComplete="email" placeholder="you@example.com" /></label>}
          {needsPassword && <label>{mode === "reset-password" ? "New password" : "Password"}
            <span className="password-control"><input name="password" type={showPassword ? "text" : "password"} required minLength={mode === "login" || mode === "admin-login" ? 1 : 12} maxLength={128} autoComplete={mode === "login" || mode === "admin-login" ? "current-password" : "new-password"} placeholder={mode === "login" || mode === "admin-login" ? "Your password" : "At least 12 characters"} /><button type="button" className="text-button" onClick={() => setShowPassword(value => !value)} aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? "Hide" : "Show"}</button></span>
          </label>}
          {mode === "register" && <label>Confirm password<input name="confirm_password" type={showPassword ? "text" : "password"} required minLength={12} maxLength={128} autoComplete="new-password" onInput={event => { const input = event.currentTarget; input.setCustomValidity(input.value === (input.form?.elements.namedItem("password") as HTMLInputElement | null)?.value ? "" : "Passwords do not match"); }} placeholder="Repeat your password" /></label>}
          {(mode === "login" || mode === "admin-login") && <label>Authenticator code (if enabled) <input name="mfa_code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} placeholder="6-digit code" /></label>}
          {mode === "reset-password" && <label>Confirm new password<input name="confirm_password" type={showPassword ? "text" : "password"} required minLength={12} maxLength={128} autoComplete="new-password" onInput={event => { const input = event.currentTarget; input.setCustomValidity(input.value === (input.form?.elements.namedItem("password") as HTMLInputElement | null)?.value ? "" : "Passwords do not match"); }} placeholder="Repeat your password" /></label>}
          {error && <p className="portal-error" role="alert">{error}</p>}
          <button className="portal-primary" type="submit" disabled={busy || (mode === "verify-email" && verified)}>{busy ? <><span className="spinner" /> Workingâ€¦</> : details.submit}</button>
        </form> : null}
        {error && mode === "verify-email" && <p className="portal-error" role="alert">{error}</p>}
        <div className="auth-links">
          {mode === "login" && <><Link href="/forgot-password">Forgot password?</Link><span>New to GNK Algo? <Link href="/register">Create an account</Link></span></>}
          {mode === "register" && <span>Already have an account? <Link href="/login">Sign in</Link></span>}
          {(mode === "forgot-password" || mode === "reset-password") && <Link href="/login">Back to sign in</Link>}
          {mode === "admin-login" && <Link href="/login">Trader sign in</Link>}
          {mode === "verify-email" && <Link href="/dashboard">Continue to your workspace</Link>}
        </div>
        <p className="auth-disclosure">Paper trading only. Quotes are illustrative and no live orders are placed.</p>
      </div>
    </section>
  </main>;
}
