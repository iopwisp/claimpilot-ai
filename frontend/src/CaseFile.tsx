import { useEffect, useState, useRef } from "react";
import { downloadReport } from "./exportReport";
import { EvidenceTasks } from "./EvidenceTasks";
import { AnalysisHistory } from "./AnalysisHistory";
import { isOutstanding } from "./api";
import { ArrowRight, ExternalLink, FileText, Play, Upload } from "lucide-react";
import {
  Account,
  Claim,
  Coverage,
  Doc,
  Event,
  Fact,
  label,
  money,
  ReviewResult,
  request,
} from "./api";
import { Badge, Modal } from "./shared";
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
    [result, setResult] = useState<ReviewResult>(),
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
      fieldId?: string;
      quote: string;
      name: string;
    }>(),
    [answer, setAnswer] = useState<Coverage>(),
    [confirmDelete, setDelete] = useState(false),
    [editing, setEditing] = useState(false);
  async function load() {
    const sequence = ++latest.current;
    const [c, d, r, a] = await Promise.all([
      request<Claim>(base),
      request<Doc[]>(base + "/documents"),
      request<ReviewResult>(base + "/report"),
      request<Event[]>(base + "/audit"),
    ]);
    if (sequence !== latest.current) return;
    setClaim(c);
    setDocs(d);
    setResult(r);
    setJob(r.job_id);
    setEvents(a);
  }
  const latest = useRef(0);
  const report = result?.report;
  const reviewed = result?.review;
  useEffect(() => {
    const update = () => load().catch((e) => err(e.message));
    update();
    const t = setInterval(update, 2500);
    return () => {
      clearInterval(t);
      latest.current++;
    };
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
  async function open(did: string, page = 1, quote = "", fieldId?: string) {
    try {
      const res = await fetch(
        "/api/v1" + base + "/documents/" + did + "/pages/" + page,
        {
          credentials: "same-origin",
        },
      );
      if (!res.ok) throw Error("Document unavailable");
      setSource({
        url: URL.createObjectURL(await res.blob()),
        id: did,
        page,
        count: docs.find((d) => d.id === did)?.metadata_json.page_count || 1,
        fieldId,
        quote,
        name: docs.find((d) => d.id === did)?.filename || "Document",
      });
    } catch (e) {
      err((e as Error).message);
    }
  }
  const review = (action: string, target = "", value = "") =>
    request(base + "/review", "POST", {
      action,
      target,
      value,
      analysis_id: job,
    });
  const inspected = claim?.fields?.find((f) => f.id === source?.fieldId);
  function fieldEditor(f: Fact) {
    return (
      <FieldEditor
        key={f.id}
        f={f}
        busy={busy}
        save={(action, value) => act(() => review(action, f.id, value))}
      />
    );
  }
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
        {[
          "Documents",
          "Extracted data",
          "Review report",
          "History",
          "Activity",
        ].map((t) => (
          <button
            className={t === tab ? "current" : ""}
            key={t}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>
      {tab === "Documents" && (
        <EvidenceTasks
          claim={claim}
          docs={docs}
          role={user.role}
          busy={busy}
          act={act}
          open={open}
        />
      )}
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
              {d.metadata_json.classification_requires_review && (
                <small>Confirm document type</small>
              )}
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
              {f.corrected && <small>Originally extracted: {f.value}</small>}
              <button
                className="link"
                onClick={() => open(f.document_id, f.page, f.quote, f.id)}
              >
                {f.filename} · p. {f.page}
                <ExternalLink size={13} />
              </button>
              {canReview && fieldEditor(f)}
            </div>
          ))}
        </section>
      )}
      {tab === "Review report" && (
        <section className="panel report">
          <div className="panelhead">
            <h2>Review report</h2>
            {result?.review && (
              <button onClick={() => downloadReport(claim, docs, result)}>
                Export report
              </button>
            )}
          </div>
          {!report ? (
            <p className="sub">
              {claim.status === "PROCESSING"
                ? "Analysis in progress…"
                : "Run analysis after the documents are ready."}
            </p>
          ) : (
            <>
              <div className="reviewStats">
                <div>
                  <strong>{reviewed?.current_issues.length}</strong>
                  <small>Open findings</small>
                </div>
                <div>
                  <strong>{reviewed?.resolved_issues.length}</strong>
                  <small>Resolved by correction</small>
                </div>
                <div>
                  <strong>
                    {reviewed?.reviewed_fields} / {reviewed?.fields.length}
                  </strong>
                  <small>Fields reviewed</small>
                </div>
              </div>
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
              {reviewed?.current_issues.length ? (
                reviewed.current_issues.map((v, i) => (
                  <div className="note" key={i}>
                    <b>{label(v.type)}</b>
                    <p>{v.description}</p>
                    {v.values.map((f, j) =>
                      f.document_id ? (
                        <button
                          key={j}
                          className="link"
                          onClick={() =>
                            open(f.document_id!, f.page, f.quote, f.id)
                          }
                        >
                          {f.filename} · p. {f.page} · {f.corrected || f.value}
                        </button>
                      ) : (
                        <small key={j}>{f.value || f.filename}</small>
                      ),
                    )}
                  </div>
                ))
              ) : (
                <p>No open discrepancies.</p>
              )}
              {!!reviewed?.resolved_issues.length && (
                <details className="resolved">
                  <summary>
                    Resolved findings ({reviewed.resolved_issues.length})
                  </summary>
                  {reviewed.resolved_issues.map((v) => (
                    <div key={v.type}>
                      <b>{label(v.type)}</b>
                      <p>{v.description}</p>
                      {v.values
                        .filter((f) => f.document_id)
                        .map((f) => (
                          <button
                            className="link"
                            key={f.id}
                            onClick={() =>
                              open(f.document_id!, f.page, f.quote, f.id)
                            }
                          >
                            {f.filename} · p. {f.page} · {f.value}
                          </button>
                        ))}
                    </div>
                  ))}
                </details>
              )}
              <h3>Required materials</h3>
              {report.required_items.map((r) => (
                <div className="item" key={r.name}>
                  <span className="grow">{r.name}</span>
                  <Badge value={r.status} />
                  {canReview &&
                    r.status !== "PRESENT" &&
                    !claim.evidence_requests?.some(
                      (t) =>
                        t.item === r.name &&
                        (isOutstanding(t) ||
                          (t.status === "ACCEPTED" && t.analysis_id === job)),
                    ) && (
                      <button
                        disabled={busy}
                        onClick={() =>
                          act(async () => {
                            await request(base + "/evidence", "POST", {
                              analysis_id: job,
                              item: r.name,
                            });
                            setTab("Documents");
                          })
                        }
                      >
                        Request material
                      </button>
                    )}
                </div>
              ))}
              <h3>Recommendations at analysis</h3>
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
                  {claim.evidence_requests?.some(isOutstanding) && (
                    <p>
                      Resolve the outstanding evidence requests in Documents to
                      complete this review.
                    </p>
                  )}
                  <button
                    className="primary"
                    disabled={
                      busy || claim.evidence_requests?.some(isOutstanding)
                    }
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
      {tab === "History" && (
        <AnalysisHistory
          base={base}
          job={job}
          status={claim.status}
          open={open}
        />
      )}
      {edit && tab === "Documents" && (
        <section className="panel">
          <h2>Review assignment</h2>
          <p className="sub">
            {claim.reviewer_email
              ? "Assigned to " + claim.reviewer_email
              : "Awaiting reviewer assignment."}
          </p>
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
        <Modal
          title="Source document"
          className="viewer"
          closeLabel="Close source"
          close={() => setSource(undefined)}
        >
          <b>{source.name}</b>
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
          {error && <p role="alert">{error}</p>}
          <div className="inspection">
            <img
              src={source.url}
              alt={source.name + " · page " + source.page}
            />
            {inspected && (
              <section className="inspector">
                <h3>{label(inspected.name)}</h3>
                <small>Extracted value</small>
                <p>{inspected.value}</p>
                {inspected.corrected && (
                  <>
                    <small>Reviewed value</small>
                    <b>{inspected.corrected}</b>
                  </>
                )}
                <Badge value={inspected.review} />
                {canReview && fieldEditor(inspected)}
              </section>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}

function FieldEditor({
  f,
  busy,
  save,
}: {
  f: Fact;
  busy: boolean;
  save: (action: string, value: string) => void;
}) {
  return (
    <form
      className="inline"
      onSubmit={(e) => {
        e.preventDefault();
        const value = String(new FormData(e.currentTarget).get("value"));
        save("correct_field", value);
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
        onClick={() => save("accept_field", "")}
      >
        Accept
      </button>
    </form>
  );
}
