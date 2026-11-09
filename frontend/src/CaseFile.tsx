import { useEffect, useState } from "react";
import {
  ArrowRight,
  ExternalLink,
  FileText,
  Play,
  Upload,
  X,
} from "lucide-react";
import {
  Account,
  Claim,
  Coverage,
  Doc,
  Event,
  label,
  money,
  Report,
  request,
} from "./api";
import { Badge, Modal } from "./main";
import { ClaimFormFields } from "./ClaimFormFields";
const kinds = [
  "CLAIM_FORM",
  "INSURANCE_POLICY",
  "MEDICAL_REPORT",
  "POLICE_REPORT",
  "INVOICE",
  "PHOTOGRAPH",
  "OTHER",
];
export function CaseFile({
  id,
  user,
  back,
}: {
  id: string;
  user: Account;
  back: () => void;
}) {
  const base = "/claims/" + id;
  const [claim, setClaim] = useState<Claim>(),
    [docs, setDocs] = useState<Doc[]>([]),
    [report, setReport] = useState<Report | null>(null),
    [events, setEvents] = useState<Event[]>([]),
    [job, setJob] = useState(""),
    [tab, setTab] = useState("Documents"),
    [error, err] = useState(""),
    [busy, setBusy] = useState(false),
    [source, setSource] = useState<{
      url: string;
      id: string;
      page: number;
      count: number;
      quote: string;
      name: string;
    }>(),
    [answer, setAnswer] = useState<Coverage>(),
    [confirmDelete, setDelete] = useState(false),
    [editing, setEditing] = useState(false);
  async function load() {
    const [c, d, r, a] = await Promise.all([
      request<Claim>(base),
      request<Doc[]>(base + "/documents"),
      request<{ report: Report | null; job_id: string }>(base + "/report"),
      request<Event[]>(base + "/audit"),
    ]);
    setClaim(c);
    setDocs(d);
    setReport(r.report);
    setJob(r.job_id);
    setEvents(a);
  }
  useEffect(() => {
    const update = () => load().catch((e) => err(e.message));
    update();
    const t = setInterval(update, 2500);
    return () => clearInterval(t);
  }, [id]);
  useEffect(
    () => () => {
      if (source) URL.revokeObjectURL(source.url.split("#")[0]);
    },
    [source],
  );
  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    err("");
    try {
      await action();
      await load();
    } catch (e) {
      err((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function open(did: string, page = 1, quote = "") {
    try {
      const res = await fetch(
        "/api/v1" + base + "/documents/" + did + "/pages/" + page,
        {
          headers: { Authorization: "Bearer " + sessionStorage.token },
        },
      );
      if (!res.ok) throw Error("Document unavailable");
      setSource({
        url: URL.createObjectURL(await res.blob()),
        id: did,
        page,
        count: docs.find((d) => d.id === did)?.metadata_json.page_count || 1,
        quote,
        name: docs.find((d) => d.id === did)?.filename || "Document",
      });
    } catch (e) {
      err((e as Error).message);
    }
  }
  const review = (action: string, target = "", value = "") =>
    request(base + "/review", "POST", { action, target, value });
  if (!claim) return <p>{error || "Loading claim…"}</p>;
  const edit =
    user.role !== "reviewer" &&
    !["COMPLETED", "PROCESSING"].includes(claim.status);
  const canReview =
    user.role !== "handler" &&
    ["NEEDS_REVIEW", "READY_FOR_REVIEW"].includes(claim.status);
  return (
    <>
      <div className="heading">
        <div>
          <p className="eyebrow">
            {claim.claim_number} · {claim.policy_number}
          </p>
          <h1>{claim.claimant_name}</h1>
        </div>
        <Badge value={claim.status} />
      </div>
      <div className="caseSummary">
        <div>
          <small>Claim amount</small>
          <b>{money(claim)}</b>
        </div>
        <div>
          <small>Incident date</small>
          <b>{claim.incident_date}</b>
        </div>
        <p>{claim.incident_description}</p>
        {edit && <button onClick={() => setEditing(true)}>Edit claim</button>}
      </div>
      {editing && (
        <Modal title="Edit claim" close={() => setEditing(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const values = Object.fromEntries(new FormData(e.currentTarget));
              act(async () => {
                await request(base, "PATCH", values);
                setEditing(false);
              });
            }}
          >
            <ClaimFormFields claim={claim} />
            {error && <p role="alert">{error}</p>}
            <button className="primary" disabled={busy}>
              Save changes
            </button>
          </form>
        </Modal>
      )}
      {error && <p role="alert">{error}</p>}
      {claim.status === "FAILED" && (
        <p role="alert">
          Analysis failed. Check the provider and retry analysis.
        </p>
      )}
      <div className="tabs">
        {["Documents", "Extracted data", "Review report", "Activity"].map(
          (t) => (
            <button
              className={t === tab ? "current" : ""}
              key={t}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ),
        )}
      </div>
      {tab === "Documents" && (
        <section className="panel">
          <div className="panelhead">
            <h2>Uploaded documents</h2>
            {edit && (
              <label className="upload">
                <Upload size={16} />
                Upload files
                <input
                  aria-label="Upload files"
                  type="file"
                  accept=".pdf,.jpg,.jpeg,.png"
                  multiple
                  disabled={busy}
                  onChange={(e) => {
                    const files = Array.from(e.target.files || []);
                    e.target.value = "";
                    act(async () => {
                      for (const file of files) {
                        const data = new FormData();
                        data.append("file", file);
                        await request(base + "/documents", "POST", data);
                      }
                    });
                  }}
                />
              </label>
            )}
          </div>
          {docs.map((d) => (
            <div className="item" key={d.id}>
              <FileText size={18} />
              <button className="link grow" onClick={() => open(d.id)}>
                {d.filename}
              </button>
              {edit && d.status === "READY" ? (
                <select
                  aria-label={"Classification of " + d.filename}
                  value={d.kind}
                  onChange={(e) =>
                    act(() =>
                      request(base + "/documents/" + d.id, "PATCH", {
                        kind: e.target.value,
                      }),
                    )
                  }
                >
                  {kinds.map((k) => (
                    <option key={k} value={k}>
                      {label(k)}
                    </option>
                  ))}
                </select>
              ) : (
                <small>{label(d.kind)}</small>
              )}
              <Badge value={d.status} />
              {edit && d.status === "FAILED" && (
                <button
                  onClick={() =>
                    act(() =>
                      request(base + "/documents/" + d.id + "/retry", "POST"),
                    )
                  }
                >
                  Retry
                </button>
              )}
            </div>
          ))}
          {!docs.length && (
            <p className="sub">
              Upload a PDF, PNG or JPEG. Maximum 20 MB per file and 50 pages per
              PDF.
            </p>
          )}
          <div className="actions">
            {edit && (
              <button
                className="primary"
                disabled={
                  busy || !docs.length || docs.some((d) => d.status !== "READY")
                }
                onClick={() =>
                  act(async () => {
                    await request(base + "/analyze", "POST");
                    setTab("Review report");
                  })
                }
              >
                <Play size={15} />
                Analyze claim
              </button>
            )}
          </div>
        </section>
      )}
      {tab === "Extracted data" && (
        <section className="panel">
          <h2>Extracted fields</h2>
          {!claim.fields?.length && (
            <p className="sub">No verified fields available.</p>
          )}
          {claim.fields?.map((f) => (
            <div className="field" key={f.id}>
              <small>
                {label(f.name)} · {label(f.review)}
              </small>
              <b>{f.corrected || f.value}</b>
              <button
                className="link"
                onClick={() => open(f.document_id, f.page, f.quote)}
              >
                {f.filename} · p. {f.page}
                <ExternalLink size={13} />
              </button>
              {canReview && (
                <form
                  className="inline"
                  onSubmit={(e) => {
                    e.preventDefault();
                    const value = String(
                      new FormData(e.currentTarget).get("value"),
                    );
                    act(() => review("correct_field", f.id, value));
                  }}
                >
                  <input
                    name="value"
                    aria-label={"Correct " + f.name}
                    placeholder="Corrected value"
                    required
                  />
                  <button disabled={busy}>Save correction</button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => act(() => review("accept_field", f.id))}
                  >
                    Accept
                  </button>
                </form>
              )}
            </div>
          ))}
        </section>
      )}
      {tab === "Review report" && (
        <section className="panel report">
          <h2>Review report</h2>
          {!report ? (
            <p className="sub">
              {claim.status === "PROCESSING"
                ? "Analysis in progress…"
                : "Run analysis after the documents are ready."}
            </p>
          ) : (
            <>
              <h3>Policy evidence</h3>
              <p>{report.policy.answer}</p>
              {report.policy.evidence.map((h, i) => (
                <button
                  className="link"
                  key={i}
                  onClick={() => open(h.document_id, h.page, h.quote)}
                >
                  View policy · p. {h.page}
                  <ExternalLink size={14} />
                </button>
              ))}
              <form
                className="inline"
                onSubmit={(e) => {
                  e.preventDefault();
                  const q = new FormData(e.currentTarget).get("q");
                  act(async () =>
                    setAnswer(
                      await request<Coverage>(base + "/policy-search", "POST", {
                        question: q,
                      }),
                    ),
                  );
                }}
              >
                <input
                  name="q"
                  required
                  minLength={3}
                  placeholder="Ask about the uploaded policy"
                />
                <button disabled={busy}>Search policy</button>
              </form>
              {answer && (
                <div className="note">
                  {answer.answer}
                  {answer.evidence.map((s, i) => (
                    <button
                      key={i}
                      className="link"
                      onClick={() => open(s.document_id, s.page, s.quote)}
                    >
                      Source · p. {s.page}
                    </button>
                  ))}
                </div>
              )}
              <h3>Cross-document inconsistencies</h3>
              {report.inconsistencies.length ? (
                report.inconsistencies.map((v, i) => (
                  <div className="note" key={i}>
                    <b>{label(v.type)}</b>
                    <p>{v.description}</p>
                    {v.values.map((f, j) =>
                      f.document_id ? (
                        <button
                          key={j}
                          className="link"
                          onClick={() => open(f.document_id!, f.page, f.quote)}
                        >
                          {f.filename} · p. {f.page} · {f.value}
                        </button>
                      ) : (
                        <small key={j}>{f.value || f.filename}</small>
                      ),
                    )}
                  </div>
                ))
              ) : (
                <p>No discrepancies found.</p>
              )}
              <h3>Required materials</h3>
              {report.required_items.map((r) => (
                <div className="item" key={r.name}>
                  <span className="grow">{r.name}</span>
                  <Badge value={r.status} />
                </div>
              ))}
              <h3>Recommendations</h3>
              {report.recommendations.length === 0 && (
                <p>No additional materials requested.</p>
              )}
              {report.recommendations.map((r) => (
                <div className="item" key={r.id}>
                  <span className="grow">{r.text}</span>
                  {events.some(
                    (a) =>
                      a.action === "review.reject_recommendation" &&
                      a.entity_id === r.id &&
                      a.details.job_id === job,
                  ) ? (
                    <small>Rejected</small>
                  ) : (
                    canReview && (
                      <button
                        disabled={busy}
                        onClick={() =>
                          act(() => review("reject_recommendation", r.id))
                        }
                      >
                        Reject
                      </button>
                    )
                  )}
                </div>
              ))}
              <h3>Human review</h3>
              <p>
                {claim.status === "COMPLETED"
                  ? "Review completed."
                  : "A reviewer must verify the evidence and record corrections."}
              </p>
              {canReview && (
                <>
                  <form
                    className="inline"
                    onSubmit={(e) => {
                      e.preventDefault();
                      const form = e.currentTarget;
                      const value = String(new FormData(form).get("comment"));
                      act(async () => {
                        await review("comment", "", value);
                        form.reset();
                      });
                    }}
                  >
                    <input
                      name="comment"
                      placeholder="Review comment"
                      required
                    />
                    <button disabled={busy}>Add comment</button>
                  </form>
                  <button
                    className="primary"
                    disabled={busy}
                    onClick={() => act(() => review("complete"))}
                  >
                    Complete review <ArrowRight size={16} />
                  </button>
                </>
              )}
            </>
          )}
        </section>
      )}
      {tab === "Activity" && (
        <section className="panel">
          <h2>Audit log</h2>
          {events.map((a, i) => (
            <div key={i} className="item">
              <span className="grow">
                {a.action}
                {a.details.value && <small>{a.details.value}</small>}
              </span>
              <small>{new Date(a.created_at).toLocaleString()}</small>
            </div>
          ))}
        </section>
      )}
      {edit && tab === "Documents" && (
        <section className="panel">
          <h2>Review assignment</h2>
          <form
            className="inline"
            onSubmit={(e) => {
              e.preventDefault();
              const email = new FormData(e.currentTarget).get("email");
              act(() => request(base, "PATCH", { reviewer_email: email }));
            }}
          >
            <input
              type="email"
              name="email"
              placeholder="Reviewer email"
              required
            />
            <button disabled={busy}>Assign reviewer</button>
          </form>
          {claim.status === "DRAFT" && (
            <button
              className="danger"
              onClick={async () => {
                if (!confirmDelete) {
                  setDelete(true);
                  return;
                }
                try {
                  await request(base, "DELETE");
                  back();
                } catch (e) {
                  err((e as Error).message);
                }
              }}
            >
              {confirmDelete ? "Confirm deletion" : "Delete draft"}
            </button>
          )}
        </section>
      )}
      {source && (
        <dialog open className="viewer" aria-label="Source document">
          <div className="modalHeader">
            <b>{source.name}</b>
            <button
              aria-label="Close source"
              onClick={() => setSource(undefined)}
            >
              <X size={16} />
            </button>
          </div>
          {source.quote && <blockquote>{source.quote}</blockquote>}
          <div className="item">
            <button
              disabled={source.page === 1}
              onClick={() => open(source.id, source.page - 1)}
            >
              Previous
            </button>
            <span>
              Page {source.page} of {source.count}
            </span>
            <button
              disabled={source.page >= source.count}
              onClick={() => open(source.id, source.page + 1)}
            >
              Next
            </button>
          </div>
          <img src={source.url} alt={source.name + " · page " + source.page} />
        </dialog>
      )}
    </>
  );
}
