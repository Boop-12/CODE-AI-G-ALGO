"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, api, json } from "@/lib/api";

type Section = "dashboard" | "users" | "roles" | "audit-logs" | "settings";
type Admin = { name: string; email: string; roles: string[]; mfa_enabled: boolean };
type UserRow = { id: string; name: string; email: string; roles: string[]; is_active: boolean; email_verified: boolean; mfa_enabled: boolean; created_at: string };
type PageResult<T> = { items: T[]; page: number; page_size: number; total: number };
type LogEntry = { id: string; user_id: string; action: string; detail: string; created_at: string };
type Role = { id: string; name: string; users: number };

const links: { section: Section; label: string }[] = [
  { section: "dashboard", label: "Overview" },
  { section: "users", label: "Users" },
  { section: "roles", label: "Roles & permissions" },
  { section: "audit-logs", label: "Audit logs" },
  { section: "settings", label: "Settings" },
];

export default function AdminPage({ section, userId }: { section: Section; userId?: string }) {
  const router = useRouter();
  const [admin, setAdmin] = useState<Admin | null>(null);
  const [users, setUsers] = useState<PageResult<UserRow> | null>(null);
  const [user, setUser] = useState<UserRow | null>(null);
  const [logs, setLogs] = useState<PageResult<LogEntry> | null>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [registrationEnabled, setRegistrationEnabled] = useState("true");
  const [supportEmail, setSupportEmail] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const current = await api<Admin>("/me");
      if (!current.roles.some(role => role === "admin" || role === "super_admin")) {
        setError("Administrator access is required for this portal.");
        return;
      }
      setAdmin(current);
      if (section === "dashboard") {
        const overview = await api<{ users: UserRow[]; audit: LogEntry[] }>("/admin/overview");
        setUsers({ items: overview.users, page: 1, page_size: 100, total: overview.users.length });
        setLogs({ items: overview.audit, page: 1, page_size: 100, total: overview.audit.length });
      } else if (section === "users" && userId) {
        setUser(await api<UserRow>(`/admin/users/${encodeURIComponent(userId)}`));
      } else if (section === "users") {
        setUsers(await api<PageResult<UserRow>>(`/admin/users?q=${encodeURIComponent(query)}&page=${page}&page_size=25`));
      } else if (section === "roles") {
        setRoles(await api<Role[]>("/admin/roles"));
      } else if (section === "audit-logs") {
        setLogs(await api<PageResult<LogEntry>>(`/admin/audit-logs?page=${page}&page_size=50`));
      } else if (section === "settings") {
        const saved = await api<Record<string, string>>("/admin/settings");
        setRegistrationEnabled(saved.registration_enabled ?? "true");
        setSupportEmail(saved.support_email ?? "");
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) router.push("/admin/login");
      else if (err instanceof ApiError && err.status === 403) setError(`${err.message}. Complete MFA setup before opening administrator tools.`);
      else setError(err instanceof Error ? err.message : "Unable to load administrator data.");
    }
  }, [page, query, router, section, userId]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function updateStatus() {
    if (!user) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api<{ is_active: boolean }>(`/admin/users/${encodeURIComponent(user.id)}/status`, { ...json({ is_active: !user.is_active }), method: "PATCH" });
      setUser({ ...user, is_active: updated.is_active });
      setMessage(updated.is_active ? "Account activated." : "Account suspended; active sessions were revoked.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update account status.");
    } finally {
      setBusy(false);
    }
  }

  async function updateRoles(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!user) return;
    const selected = Array.from(new FormData(event.currentTarget).getAll("role")).map(String);
    setBusy(true);
    setError("");
    try {
      const updated = await api<UserRow>(`/admin/users/${encodeURIComponent(user.id)}/roles`, { ...json({ roles: selected }), method: "PATCH" });
      setUser({ ...user, roles: updated.roles });
      setMessage("User roles updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update user roles.");
    } finally {
      setBusy(false);
    }
  }

  async function saveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const update = {
      registration_enabled: String(values.get("registration_enabled")),
      support_email: String(values.get("support_email") || ""),
    };
    setBusy(true);
    setError("");
    try {
      const saved = await api<Record<string, string>>("/admin/settings", { ...json({ settings: update }), method: "PATCH" });
      setRegistrationEnabled(saved.registration_enabled ?? "true");
      setSupportEmail(saved.support_email ?? "");
      setMessage("Administrative settings saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save settings.");
    } finally {
      setBusy(false);
    }
  }

  const isSuperAdmin = admin?.roles.includes("super_admin") ?? false;
  return <main className="admin-shell">
    <aside className="admin-sidebar"><Link href="/admin/dashboard" className="portal-brand">GNK <span>ADMIN</span></Link><p className="admin-caption">ADMINISTRATION</p><nav aria-label="Admin navigation">{links.map(item => <Link key={item.section} className={section === item.section ? "active" : ""} href={`/admin/${item.section}`}>{item.label}</Link>)}</nav><Link className="admin-back" href="/dashboard">← Trader workspace</Link></aside>
    <section className="admin-main"><header className="admin-header"><div><span className="portal-eyebrow">GNKALGO TRADER</span><strong>Administrator portal</strong></div><span className="admin-identity">{admin?.name || "Administrator"}</span></header>
      <div className="admin-content"><div className="admin-title"><div><p className="portal-eyebrow">CONTROL CENTER</p><h1>{userId ? "User details" : links.find(item => item.section === section)?.label}</h1><p className="portal-subtitle">Administrative actions are checked by the API and recorded in the audit trail.</p></div>{userId && <Link href="/admin/users" className="portal-secondary">← All users</Link>}</div>
        <div aria-live="polite">{message && <p className="portal-success">{message}</p>}{error && <div className="portal-error" role="alert">{error}{error.includes("MFA") && <p><Link href="/admin/mfa">Set up authenticator</Link></p>}</div>}</div>
        {section === "dashboard" && <div className="admin-grid"><section className="portal-card"><h2>Accounts</h2><p className="admin-number">{users?.total ?? "—"}</p><Link href="/admin/users">Manage user accounts →</Link></section><section className="portal-card"><h2>Audit events</h2><p className="admin-number">{logs?.total ?? "—"}</p><Link href="/admin/audit-logs">Review activity →</Link></section><section className="portal-card admin-wide"><h2>Latest accounts</h2><UserTable items={users?.items.slice(0, 8) ?? []} /></section></div>}
        {section === "users" && !userId && <section className="portal-card"><form className="admin-search" onSubmit={event => { event.preventDefault(); setPage(1); void load(); }}><label htmlFor="user-search">Search accounts</label><input id="user-search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Name or email address" /><button className="portal-primary">Search</button></form><UserTable items={users?.items ?? []} /><Pagination page={users?.page ?? 1} pageSize={users?.page_size ?? 25} total={users?.total ?? 0} onChange={setPage} /></section>}
        {section === "users" && userId && user && <section className="portal-card"><div className="admin-user-head"><div><h2>{user.name}</h2><p>{user.email}</p></div><span className={user.is_active ? "badge-verified" : "badge-pending"}>{user.is_active ? "Active" : "Suspended"}</span></div><div className="admin-detail-grid"><span>Email verification<strong>{user.email_verified ? "Verified" : "Pending"}</strong></span><span>MFA<strong>{user.mfa_enabled ? "Enabled" : "Not enabled"}</strong></span><span>Created<strong>{new Date(user.created_at).toLocaleDateString()}</strong></span><span>Roles<strong>{user.roles.join(", ") || "No assigned roles"}</strong></span></div>{isSuperAdmin && <div className="admin-actions"><button className={user.is_active ? "danger-button" : "portal-primary"} disabled={busy} onClick={() => void updateStatus()}>{user.is_active ? "Suspend account" : "Activate account"}</button><form className="role-form" onSubmit={updateRoles}><fieldset><legend>Assign roles</legend>{["admin", "super_admin"].map(role => <label key={role}><input type="checkbox" name="role" value={role} defaultChecked={user.roles.includes(role)} />{role.replace("_", " ")}</label>)}</fieldset><button className="portal-secondary" disabled={busy}>Save roles</button></form></div>}{!isSuperAdmin && <p className="auth-disclosure">Only a super administrator can change account status or roles.</p>}</section>}
        {section === "roles" && <section className="portal-card"><h2>Role directory</h2><p>Role assignment and account status changes require a super administrator account.</p><div className="table-scroll"><table><thead><tr><th>Role</th><th>Assigned users</th><th>Permission boundary</th></tr></thead><tbody>{roles.map(role => <tr key={role.id}><td>{role.name}</td><td>{role.users}</td><td>{role.name === "super_admin" ? "Full administration" : role.name === "admin" ? "Read-only admin tools" : "Reserved application role"}</td></tr>)}</tbody></table></div></section>}
        {section === "audit-logs" && <section className="portal-card"><h2>Administrative audit log</h2><p>Recent events from user and administrator account activity.</p><div className="table-scroll"><table><thead><tr><th>Time</th><th>Actor ID</th><th>Action</th><th>Details</th></tr></thead><tbody>{logs?.items.map(log => <tr key={log.id}><td>{new Date(log.created_at).toLocaleString()}</td><td>{log.user_id}</td><td>{log.action}</td><td>{log.detail}</td></tr>)}</tbody></table></div><Pagination page={logs?.page ?? 1} pageSize={logs?.page_size ?? 50} total={logs?.total ?? 0} onChange={setPage} /></section>}
        {section === "settings" && <section className="portal-card"><h2>Platform settings</h2><p>Registration availability is enforced by the API; every setting update is audited.</p><form className="portal-form admin-settings-form" onSubmit={saveSettings}><label>New registrations<select name="registration_enabled" value={registrationEnabled} onChange={event => setRegistrationEnabled(event.target.value)}><option value="true">Enabled</option><option value="false">Disabled</option></select></label><label>Support email<input name="support_email" type="email" value={supportEmail} onChange={event => setSupportEmail(event.target.value)} placeholder="support@example.com" /></label><button className="portal-primary" disabled={busy || !isSuperAdmin}>{busy ? "Saving…" : "Save settings"}</button>{!isSuperAdmin && <small>Settings updates require a super administrator.</small>}</form></section>}
      </div>
    </section>
  </main>;
}

function UserTable({ items }: { items: UserRow[] }) {
  return <div className="table-scroll"><table><thead><tr><th>Name</th><th>Email</th><th>Status</th><th>Roles</th><th>Created</th></tr></thead><tbody>{items.map(user => <tr key={user.id}><td><Link className="table-link" href={`/admin/users/${user.id}`}>{user.name}</Link></td><td>{user.email}</td><td><span className={user.is_active ? "badge-verified" : "badge-pending"}>{user.is_active ? "Active" : "Suspended"}</span></td><td>{user.roles?.join(", ") || "Trader"}</td><td>{user.created_at ? new Date(user.created_at).toLocaleDateString() : "—"}</td></tr>)}{items.length === 0 && <tr><td colSpan={5}>No accounts found.</td></tr>}</tbody></table></div>;
}

function Pagination({ page, pageSize, total, onChange }: { page: number; pageSize: number; total: number; onChange: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return <div className="pagination"><span>{total} records · Page {page} of {pages}</span><button className="portal-secondary" disabled={page <= 1} onClick={() => onChange(page - 1)}>Previous</button><button className="portal-secondary" disabled={page >= pages} onClick={() => onChange(page + 1)}>Next</button></div>;
}
