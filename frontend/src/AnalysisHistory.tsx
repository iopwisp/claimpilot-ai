import { useEffect, useState } from "react";
import { Fact, Report, request, label } from "./api";

interface Version {
  id: string;
  current: boolean;
  created_at: string;
  model: string;
  prompt_version: string;
}
interface Snapshot {
  report: Report & {
    extracted_fields: Fact[];
    documents: { id: string; filename: string; kind: string }[];
  };
  changes: null | {
    added_documents: { id: string; filename: string }[];
    removed_documents: { id: string; filename: string }[];
    materials: { name: string; before: string | null; after: string | null }[];
    findings: { type: string; field: string; before: number; after: number }[];
    policy_changed: boolean;
  };
}

export function AnalysisHistory({
  base,
  job,
  status,
  open,
}: {
  base: string;
  job: string;
  status: string;
  open: (id: string, page?: number, quote?: string) => void;
}) {
  const [versions, setVersions] = useState<Version[]>([]),
    [selected, select] = useState(""),
    [record, setRecord] = useState<Snapshot>(),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    let live = true;
    request<Version[]>(base + "/analyses")
      .then((list) => {
        if (live) {
          setVersions(list);
          select((old) =>
            list.some((v) => v.id === old) ? old : list[0]?.id || "",
          );
          setLoading(false);
        }
      })
      .catch((e) => {
        if (live) {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => {
      live = false;
    };
  }, [base, job, status]);
  useEffect(() => {
    let live = true;
    setRecord(undefined);
    if (!selected) return;
    setError("");
    request<Snapshot>(base + "/analyses/" + selected)
      .then((value) => {
        if (live) setRecord(value);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [base, selected]);
  const index = versions.findIndex((v) => v.id === selected),
    version = versions[index],
    diff = record?.changes;
  return (
    <section className="panel report">
      <h2>Analysis history</h2>
      {error && <p role="alert">{error}</p>}
      {!versions.length ? (
        <p>
          {loading
            ? "Loading history…"
            : "Completed analyses will appear here."}
        </p>
      ) : (
        <>
          <label>
            Saved analysis
            <select
              value={selected}
              onChange={(e) => {
                setRecord(undefined);
                select(e.target.value);
              }}
            >
              {versions.map((v, i) => (
                <option key={v.id} value={v.id}>
                  Run {versions.length - i} ·{" "}
                  {new Date(v.created_at).toLocaleString()}
                  {v.current ? " · Current" : ""}
                </option>
              ))}
            </select>
          </label>
          {version && (
            <small>
              {version.model} · {version.prompt_version}
            </small>
          )}
          {record && (
            <>
              <h3>
                {diff
                  ? "Changes since run " + (versions.length - index - 1)
                  : "Initial analysis"}
              </h3>
              {diff && (
                <>
                  {diff.added_documents.map((d) => (
                    <button
                      key={d.id}
                      className="link"
                      onClick={() => open(d.id)}
                    >
                      Added document · {d.filename}
                    </button>
                  ))}
                  {diff.removed_documents.map((d) => (
                    <p key={d.id}>Removed document · {d.filename}</p>
                  ))}
                  {diff.materials.map((m) => (
                    <p key={m.name}>
                      {m.name} · {label(m.before || "NOT_LISTED")} →{" "}
                      {label(m.after || "NOT_LISTED")}
                    </p>
                  ))}
                  {diff.findings.map((i) => (
                    <p key={i.type + i.field}>
                      {label(i.type)} · {label(i.field)} · {i.before} →{" "}
                      {i.after}
                    </p>
                  ))}
                  {diff.policy_changed && <p>Policy evidence changed.</p>}
                  {!diff.materials.length &&
                    !diff.findings.length &&
                    !diff.policy_changed && (
                      <p>
                        Checklist statuses, finding counts and policy evidence
                        match the previous run.
                      </p>
                    )}
                </>
              )}
              <h3>Materials at analysis</h3>
              {record.report.required_items.map((m) => (
                <div className="item" key={m.name}>
                  <span className="grow">{m.name}</span>
                  {label(m.status)}
                </div>
              ))}
              <h3>Policy evidence</h3>
              <p>{record.report.policy.answer}</p>
              {record.report.policy.evidence.map((s, i) => (
                <button
                  className="link"
                  key={i}
                  onClick={() => open(s.document_id, s.page, s.quote)}
                >
                  View policy · p. {s.page}
                </button>
              ))}
              <h3>Findings at analysis</h3>
              {record.report.inconsistencies.length ? (
                record.report.inconsistencies.map((f, i) => (
                  <p key={i}>
                    {label(f.type)} · {f.description}
                  </p>
                ))
              ) : (
                <p>No discrepancies found.</p>
              )}
              <details>
                <summary>
                  Source fields ({record.report.extracted_fields.length})
                </summary>
                {record.report.extracted_fields.map((f) => (
                  <div className="field" key={f.id}>
                    <small>{label(f.name)}</small>
                    <b>{f.corrected || f.value}</b>
                    <button
                      className="link"
                      onClick={() => open(f.document_id, f.page, f.quote)}
                    >
                      {f.filename} · p. {f.page}
                    </button>
                  </div>
                ))}
              </details>
            </>
          )}
        </>
      )}
    </section>
  );
}
