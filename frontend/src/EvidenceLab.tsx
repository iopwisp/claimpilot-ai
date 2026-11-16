import { useEffect, useState } from "react";
import { ExternalLink, Layers, RotateCcw } from "lucide-react";
import { Doc, Evidence, label, request } from "./api";
import "./evidenceLab.css";

type Item = { field: string; value: string; sources: Evidence[] };
type Packet = { document_ids: string[]; minimum: boolean };
type Lab = {
  analyzed_at: string;
  documents: Pick<Doc, "id" | "filename" | "kind">[];
  items: Item[];
  packet: Packet;
};
type OpenPage = (id: string, page: number, quote: string) => void;
type Filter = "All" | "Lost" | "Reduced" | "Intact";

export function EvidenceLab({
  base,
  analysis,
  open,
}: {
  base: string;
  analysis: string;
  open: OpenPage;
}) {
  const [lab, setLab] = useState<Lab>();
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!analysis) return;
    let current = true;
    setError("");
    request<Lab>(base + "/analyses/" + analysis + "/evidence-lab")
      .then((result) => {
        if (current) setLab(result);
      })
      .catch((e) => {
        if (current) setError(e.message);
      });
    return () => {
      current = false;
    };
  }, [base, analysis, retry]);
  if (lab)
    return (
      <Simulation
        lab={lab}
        open={open}
        recoveryPath={base + "/analyses/" + analysis + "/evidence-lab/recovery"}
      />
    );
  return (
    <section className="panel">
      <h2>Evidence Lab</h2>
      {error ? (
        <>
          <p role="alert">{error}</p>
          <button onClick={() => setRetry((v) => v + 1)}>Retry</button>
        </>
      ) : (
        <p>
          {analysis
            ? "Loading cited pages…"
            : "Analyze this claim to explore its sources. You can also open a saved run from History."}
        </p>
      )}
    </section>
  );
}

function Simulation({
  lab,
  open,
  recoveryPath,
}: {
  lab: Lab;
  open: OpenPage;
  recoveryPath: string;
}) {
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState<Filter>("All");
  const files = new Map(lab.documents.map((d) => [d.id, d.filename]));
  const packet = new Set(lab.packet.document_ids);
  const reasons = new Map<string, Item[]>();
  const unique = new Map<string, number>();
  const counts = { All: lab.items.length, Lost: 0, Reduced: 0, Intact: 0 };
  const rows = lab.items.map((item, index) => {
    const docs = [...new Set(item.sources.map((s) => s.document_id))];
    if (docs.length === 1) unique.set(docs[0], (unique.get(docs[0]) || 0) + 1);
    const inPacket = docs.filter((id) => packet.has(id));
    if (inPacket.length === 1) {
      const id = inPacket[0];
      if (!reasons.has(id)) reasons.set(id, []);
      reasons.get(id)!.push(item);
    }
    const active = docs.filter((id) => !excluded.has(id)).length;
    const status: Exclude<Filter, "All"> = !active
      ? "Lost"
      : active < docs.length
        ? "Reduced"
        : "Intact";
    counts[status]++;
    return { item, index, active, total: docs.length, status };
  });
  const priority = { Lost: 0, Reduced: 1, Intact: 2 };
  const visible = rows
    .filter((r) => filter === "All" || filter === r.status)
    .sort((a, b) => priority[a.status] - priority[b.status]);
  function toggle(id: string) {
    setExcluded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  return (
    <section className="lab" aria-label="Evidence Lab">
      <div className="labOverview">
        <div className="labIntro">
          <Layers aria-hidden="true" size={24} />
          <div>
            <h2>Evidence Lab</h2>
            <p>
              Switch off a file to see which statements lose their cited pages.
            </p>
          </div>
        </div>
        <div className="labMeter" aria-hidden="true">
          {(["Intact", "Reduced", "Lost"] as const).map((s) => (
            <span
              key={s}
              className={s.toLowerCase()}
              style={{ flexGrow: counts[s] }}
            />
          ))}
        </div>
        <div className="labLegend" aria-live="polite" aria-atomic="true">
          <span>
            <b>{counts.Intact}</b> intact
          </span>
          <span>
            <b>{counts.Reduced}</b> reduced
          </span>
          <span>
            <b>{counts.Lost}</b> lost
          </span>
        </div>
        <small>
          Saved analysis · {new Date(lab.analyzed_at).toLocaleString()}
        </small>
      </div>
      <div className="labGrid">
        <div className="labControls">
          <section className="panel">
            <div className="panelhead">
              <h3>Files in play</h3>
              <button
                className="link"
                disabled={!excluded.size}
                onClick={() => {
                  setExcluded(new Set());
                  setFilter("All");
                }}
              >
                <RotateCcw size={14} /> Reset
              </button>
            </div>
            {lab.documents.map((d) => (
              <label className="labFile" key={d.id}>
                <input
                  type="checkbox"
                  aria-label={"Include " + d.filename}
                  checked={!excluded.has(d.id)}
                  onChange={() => toggle(d.id)}
                />
                <span>
                  <b>{d.filename}</b>
                  <small>
                    {unique.get(d.id)
                      ? "Only file for " +
                        unique.get(d.id) +
                        (unique.get(d.id) === 1 ? " statement" : " statements")
                      : label(d.kind)}
                  </small>
                </span>
              </label>
            ))}
          </section>
          {lab.items.length > 0 && (
            <section className="panel labPacket">
              <h3>
                {lab.packet.minimum
                  ? "Smallest source packet"
                  : "Compact source packet"}
              </h3>
              <p>
                <strong>
                  {packet.size} of {files.size} files
                </strong>{" "}
                retain a citation for every statement below.
              </p>
              {!lab.packet.minimum && (
                <small>Search limit reached. A smaller packet may exist.</small>
              )}
              <details>
                <summary>Why these files?</summary>
                {lab.packet.document_ids.map((id) => (
                  <div key={id}>
                    <b>{files.get(id)}</b>
                    <ul>
                      {(reasons.get(id) || []).map((i, n) => (
                        <li key={n}>
                          {label(i.field)} · {i.value}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </details>
              <button
                onClick={() => {
                  setExcluded(
                    new Set([...files.keys()].filter((id) => !packet.has(id))),
                  );
                  setFilter("All");
                }}
              >
                Try this packet
              </button>
            </section>
          )}
        </div>
        <section className="panel labResults">
          <h3>Statement coverage</h3>
          <p className="sub">
            Original extracted values and cited policy text. File counts include
            copies. Required materials are tracked in the review report.
          </p>
          {counts.Lost > 0 && (
            <Recovery
              key={JSON.stringify([...excluded].sort())}
              path={recoveryPath}
              excluded={excluded}
              files={files}
              lost={rows.filter((r) => r.status === "Lost").map((r) => r.item)}
              restore={(ids) => {
                setExcluded(
                  new Set([...excluded].filter((id) => !ids.includes(id))),
                );
                setFilter("All");
              }}
            />
          )}
          <div className="labFilters" aria-label="Filter statements">
            {(["All", "Lost", "Reduced", "Intact"] as const).map((s) => (
              <button
                key={s}
                aria-pressed={filter === s}
                onClick={() => setFilter(s)}
              >
                {s} {counts[s]}
              </button>
            ))}
          </div>
          {!visible.length && (
            <p>
              {!lab.items.length
                ? "This analysis contains no cited statements."
                : "No statements match this filter."}
            </p>
          )}
          {visible.map(({ item, index, active, total, status }) => (
            <details className="labItem" key={index}>
              <summary>
                <span>
                  <small>{label(item.field)}</small>
                  <b>{item.value}</b>
                </span>
                <span className={"labStatus " + status.toLowerCase()}>
                  {status} · {active}/{total}
                </span>
              </summary>
              <div className="labSources">
                {item.sources.map((s, i) => (
                  <div key={i}>
                    <q>{s.quote}</q>
                    <button
                      className="link"
                      onClick={() => open(s.document_id, s.page, s.quote)}
                    >
                      <ExternalLink size={13} />
                      {files.get(s.document_id)} · p. {s.page}
                      {excluded.has(s.document_id) ? " · Excluded" : ""}
                    </button>
                  </div>
                ))}
              </div>
            </details>
          ))}
        </section>
      </div>
    </section>
  );
}

function Recovery({
  path,
  excluded,
  files,
  lost,
  restore,
}: {
  path: string;
  excluded: Set<string>;
  files: Map<string, string>;
  lost: Item[];
  restore: (ids: string[]) => void;
}) {
  const [packet, setPacket] = useState<Packet>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function findFiles() {
    setBusy(true);
    setError("");
    try {
      setPacket(
        await request<Packet>(path, "POST", { excluded: [...excluded] }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="labRecovery">
      <h4>Recover lost sources</h4>
      {packet ? (
        <>
          <p>
            {packet.minimum
              ? "Fewest files to restore"
              : "Suggested files to restore"}{" "}
            · {packet.document_ids.length}
          </p>
          <ul>
            {packet.document_ids.map((id) => (
              <li key={id}>
                <strong>{files.get(id)}</strong>
                <small>
                  {lost
                    .filter((i) => i.sources.some((s) => s.document_id === id))
                    .map((i) => label(i.field) + " · " + i.value)
                    .join(" / ")}
                </small>
              </li>
            ))}
          </ul>
          <button onClick={() => restore(packet.document_ids)}>
            Restore suggested files
          </button>
        </>
      ) : (
        <button disabled={busy} onClick={findFiles}>
          {busy ? "Finding files…" : "Find files to restore"}
        </button>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
