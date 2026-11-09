import { ClaimFormFields } from "./ClaimFormFields";
import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  CheckCheck,
  ChevronRight,
  ClipboardList,
  Files,
  FolderOpen,
  Layers3,
  LayoutDashboard,
  LogOut,
  Plus,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { Account, Claim, label, money, request, statuses } from "./api";
import { CaseFile } from "./CaseFile";
import "./style.css";

export function Brand() {
  return (
    <div className="brand">
      <span className="mark">
        <Layers3 size={22} />
      </span>
      ClaimPilot <small>AI</small>
    </div>
  );
}
export function Badge({ value }: { value: string }) {
  return (
    <span className={"badge " + value}>
      <i />
      {label(value)}
    </span>
  );
}
export function Modal({
  title,
  close,
  children,
}: {
  title: string;
  close: () => void;
  children: React.ReactNode;
}) {
  return (
    <dialog
      open
      aria-modal="true"
      onKeyDown={(e) => e.key === "Escape" && close()}
    >
      <div className="modalHeader">
        <h2>{title}</h2>
        <button aria-label="Close dialog" onClick={close}>
          <X size={18} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
function Auth({ done }: { done: (a: Account) => void }) {
  const [register, setRegister] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const body = Object.fromEntries(new FormData(e.currentTarget));
    try {
      if (register) await request("/auth/register", "POST", body);
      const r = await request<{ access_token: string; user: Account }>(
        "/auth/login",
        "POST",
        body,
      );
      sessionStorage.setItem("token", r.access_token);
      done(r.user);
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth">
      <section className="cover">
        <Brand />
        <div className="coverTitle">
          <div className="line" />
          <h1>
            Claims
            <br />
            <em>workspace.</em>
          </h1>
        </div>
        <div className="paperstack" aria-hidden="true">
          <div />
          <div />
          <div>
            <Files size={48} />
            <i />
            <i />
            <i />
          </div>
        </div>
        <footer>
          <ShieldCheck size={17} /> Insurance claims operations
        </footer>
      </section>
      <section className="entry">
        <form onSubmit={submit}>
          <div className="symbol">
            <ShieldCheck />
          </div>
          <h1>{register ? "Create account" : "Welcome back"}</h1>
          <p>
            {register
              ? "Create a claims handler account."
              : "Sign in to your claims workspace."}
          </p>
          <label>
            Email address
            <input autoComplete="email" name="email" type="email" required />
          </label>
          <label>
            Password
            <input
              autoComplete={register ? "new-password" : "current-password"}
              name="password"
              type="password"
              minLength={10}
              maxLength={128}
              required
            />
          </label>
          {error && <p role="alert">{error}</p>}
          <button className="primary" disabled={busy}>
            {busy ? "Please wait…" : register ? "Create account" : "Sign in"}
            <ArrowRight size={16} />
          </button>
          <button
            className="link"
            type="button"
            onClick={() => {
              setRegister(!register);
              setError("");
            }}
          >
            {register ? "Already registered? Sign in" : "Create an account"}
          </button>
        </form>
      </section>
    </main>
  );
}
function App() {
  const [user, setUser] = useState<Account | null>(null),
    [view, setView] = useState("Overview"),
    [selected, select] = useState(""),
    [claims, setClaims] = useState<Claim[]>([]),
    [docs, setDocs] = useState(0),
    [error, setError] = useState(""),
    [create, setCreate] = useState(false),
    [q, setQ] = useState(""),
    [status, setStatus] = useState(""),
    [sort, setSort] = useState("newest"),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    if (sessionStorage.token)
      request<Account>("/auth/me")
        .then(setUser)
        .catch(() => sessionStorage.removeItem("token"));
  }, []);
  async function refresh() {
    const session = sessionStorage.getItem("token");
    const [list, metrics] = await Promise.all([
      request<Claim[]>("/claims"),
      request<{ documents_processing: number }>("/dashboard"),
    ]);
    if (session !== sessionStorage.getItem("token")) return;
    setClaims(list);
    setDocs(metrics.documents_processing);
  }
  useEffect(() => {
    if (!user) return;
    const update = () => refresh().catch((e) => setError(e.message));
    update();
    const timer = setInterval(update, 5000);
    return () => clearInterval(timer);
  }, [user]);
  if (!user) return <Auth done={setUser} />;
  const navigate = (v: string) => {
    setView(v);
    select("");
    setQ("");
    setStatus("");
    setError("");
  };
  const filtered = claims
    .filter(
      (c) =>
        (!status || status === c.status) &&
        [c.id, c.claim_number, c.policy_number, c.claimant_name]
          .join(" ")
          .toLowerCase()
          .includes(q.toLowerCase()),
    )
    .sort((a, b) =>
      sort === "amount"
        ? Number(b.claim_amount) - Number(a.claim_amount)
        : sort === "oldest"
          ? a.created_at.localeCompare(b.created_at)
          : b.created_at.localeCompare(a.created_at),
    );
  const list = view === "Overview" ? filtered.slice(0, 6) : filtered;
  const metrics = [
    { label: "Total claims", value: claims.length, icon: FolderOpen },
    {
      label: "Awaiting review",
      value: claims.filter((c) =>
        ["NEEDS_REVIEW", "READY_FOR_REVIEW"].includes(c.status),
      ).length,
      icon: ClipboardList,
    },
    { label: "Processing files", value: docs, icon: Activity },
    {
      label: "Completed reviews",
      value: claims.filter((c) => c.status === "COMPLETED").length,
      icon: CheckCheck,
    },
  ];
  async function newClaim(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    try {
      const c = await request<Claim>(
        "/claims",
        "POST",
        Object.fromEntries(new FormData(e.currentTarget)),
      );
      await refresh();
      setCreate(false);
      select(c.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="shell">
      <aside>
        <Brand />
        <nav>
          {[
            { name: "Overview", icon: LayoutDashboard },
            { name: "Claims", icon: FolderOpen },
            ...(user.role === "admin"
              ? [{ name: "Users", icon: SlidersHorizontal }]
              : []),
          ].map((n) => (
            <button
              key={n.name}
              className={n.name === view ? "active" : ""}
              onClick={() => navigate(n.name)}
            >
              <n.icon size={18} />
              {n.name}
            </button>
          ))}
        </nav>
        <div className="profile">
          <strong>{user.email.slice(0, 1).toUpperCase()}</strong>
          <span>
            {user.email}
            <small>{label(user.role)}</small>
          </span>
          <button
            aria-label="Sign out"
            onClick={async () => {
              try {
                await request("/auth/logout", "POST");
                sessionStorage.removeItem("token");
                  setClaims([]);
                  setDocs(0);
                  setError("");
                setUser(null);
                select("");
                setView("Overview");
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            <LogOut size={16} />
          </button>
        </div>
      </aside>
      <main className="workspace">
        <header>
          Workspace <ChevronRight size={14} /> {view}
          {selected && (
            <>
              {" "}
              <ChevronRight size={14} /> Claim file
            </>
          )}
        </header>
        <div className="content">
          {error && <p role="alert">{error}</p>}
          {selected ? (
            <>
              <button className="link" onClick={async () => {try {await refresh();select("")}catch(e){setError((e as Error).message)}}}>
                <ArrowLeft size={15} /> Back to {view.toLowerCase()}
              </button>
              <CaseFile
                key={selected}
                id={selected}
                user={user}
                back={() => {
                  select("");
                  refresh();
                }}
              />
            </>
          ) : view === "Users" ? (
            <Users />
          ) : (
            <>
              <div className="heading">
                <div>
                  <p className="eyebrow">Claims operations</p>
                  <h1>
                    {view === "Overview"
                      ? "Workspace overview"
                      : "Claims register"}
                  </h1>
                </div>
                {user.role !== "reviewer" && (
                  <button className="primary" onClick={() => setCreate(true)}>
                    <Plus size={17} />
                    New claim
                  </button>
                )}
              </div>
              {view === "Overview" && (
                <div className="metrics">
                  {metrics.map((m) => (
                    <div className="metric" key={m.label}>
                      <m.icon size={18} />
                      <strong>{m.value}</strong>
                      <span>{m.label}</span>
                    </div>
                  ))}
                </div>
              )}
              <section className="panel">
                <div className="panelhead">
                  <h2>
                    {view === "Overview" ? "Recent claims" : "All claims"}
                  </h2>
                  {view === "Overview" ? (
                    <button className="link" onClick={() => navigate("Claims")}>
                      View all <ArrowRight size={15} />
                    </button>
                  ) : (
                    <span>{filtered.length} results</span>
                  )}
                </div>
                {view === "Claims" && (
                  <div className="filters">
                    <label className="search">
                      <Search size={16} />
                      <input
                        placeholder="Search claims or policies"
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                      />
                    </label>
                    <select
                      aria-label="Status"
                      value={status}
                      onChange={(e) => setStatus(e.target.value)}
                    >
                      <option value="">All statuses</option>
                      {statuses.map((s) => (
                        <option key={s} value={s}>
                          {label(s)}
                        </option>
                      ))}
                    </select>
                    <select
                      aria-label="Sort"
                      value={sort}
                      onChange={(e) => setSort(e.target.value)}
                    >
                      <option value="newest">Newest first</option>
                      <option value="oldest">Oldest first</option>
                      <option value="amount">Highest amount</option>
                    </select>
                  </div>
                )}
                <div className="scroll">
                  <table>
                    <thead>
                      <tr>
                        {[
                          "Claim / Policy",
                          "Claimant",
                          "Amount",
                          "Status",
                          "",
                        ].map((s) => (
                          <th key={s}>{s}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {list.map((c) => (
                        <tr key={c.id}>
                          <td>
                            <button
                              className="link"
                              onClick={() => select(c.id)}
                            >
                              {c.claim_number}
                            </button>
                            <small>{c.policy_number}</small>
                          </td>
                          <td>{c.claimant_name}</td>
                          <td>{money(c)}</td>
                          <td>
                            <Badge value={c.status} />
                          </td>
                          <td>
                            <button
                              aria-label={"Open " + c.claim_number}
                              onClick={() => select(c.id)}
                            >
                              <ChevronRight size={16} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!list.length && (
                  <div className="empty">
                    <Files />
                    <h3>
                      {q || status ? "No matching claims" : "No claims yet"}
                    </h3>
                    <p>
                      {q || status
                        ? "Try another search or status."
                        : user.role === "reviewer"
                          ? "Assigned claims will appear here."
                          : "Create a claim to start a case file."}
                    </p>
                  </div>
                )}
              </section>
            </>
          )}
        </div>
      </main>
      {create && (
        <Modal title="New claim" close={() => setCreate(false)}>
          <form onSubmit={newClaim}>
            <ClaimFormFields />
            {error && <p role="alert">{error}</p>}
            <button className="primary" disabled={busy}>
              Create claim <ArrowRight size={16} />
            </button>
          </form>
        </Modal>
      )}
    </div>
  );
}

function Users() {
  const [rule, setRule] = useState("conditional");
  const [users, set] = useState<Account[]>([]),
    [error, err] = useState("");
  useEffect(() => {
    request<Account[]>("/users")
      .then(set)
      .catch((e) => err(e.message));
    request<{ police_report: string }>("/settings")
      .then((r) => setRule(r.police_report))
      .catch((e) => err(e.message));
  }, []);
  return (
    <section className="panel">
      <h2>User management</h2>
      <label className="item">
        Police report requirement
        <select
          value={rule}
          onChange={async (e) => {
            try {
              const value = e.target.value;
              await request("/settings", "PUT", { police_report: value });
              setRule(value);
            } catch (e) {
              err((e as Error).message);
            }
          }}
        >
          {["conditional", "required", "optional"].map((s) => (
            <option key={s} value={s}>
              {label(s)}
            </option>
          ))}
        </select>
      </label>
      {error && <p role="alert">{error}</p>}
      {users.map((u) => (
        <div className="item" key={u.id}>
          {u.email}
          <select
            value={u.role}
            onChange={async (e) => {
              try {
                const changed = await request<Account>(
                  "/users/" + u.id,
                  "PATCH",
                  { role: e.target.value },
                );
                set(users.map((v) => (v.id === u.id ? changed : v)));
              } catch (e) {
                err((e as Error).message);
              }
            }}
          >
            {["handler", "reviewer", "admin"].map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </div>
      ))}
    </section>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
