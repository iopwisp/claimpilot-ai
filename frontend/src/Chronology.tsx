import { useState } from "react";
import { CalendarDays, Download, ExternalLink } from "lucide-react";
import { DatedEvent, Evidence, Report, label } from "./api";
import { downloadText } from "./exportReport";
import "./chronology.css";

export function compareDays(start: string, end: string, windowDays: number) {
  const days =
    (Date.parse(end + "T00:00:00Z") - Date.parse(start + "T00:00:00Z")) /
    86400000;
  return {
    days,
    outcome:
      days < 0
        ? "Before incident"
        : days <= windowDays
          ? "Within window"
          : "Outside window",
  };
}

export function Chronology({
  report,
  run,
  open,
}: {
  report: Report;
  run: string;
  open: (id: string, page: number, quote: string) => void;
}) {
  const { events, scope, truncated } = report.chronology;
  const candidates = events.filter((e) => e.kind !== "incident" && e.date);
  const [selection, select] = useState("");
  const [windowText, setWindow] = useState("7");
  const [kind, filter] = useState("");
  const key = (e: DatedEvent) => e.kind + "/" + e.date;
  const target =
    candidates.find((e) => key(e) === selection) ||
    candidates.find((e) => e.kind === "notice") ||
    candidates[0];
  const recordDate = report.overview.incident_date;
  const anchors = new Map<string, Evidence[]>([[recordDate, []]]);
  for (const e of events)
    if (e.kind === "incident" && e.date) anchors.set(e.date, e.sources);
  const names = new Map(report.documents.map((d) => [d.id, d.filename]));
  const citation = (s: Evidence) =>
    (names.get(s.document_id) || s.document_id) + " · p. " + s.page;
  function sources(list: Evidence[]) {
    return list.map((s, i) => (
      <button
        key={i}
        className="link"
        title={s.quote}
        onClick={() => open(s.document_id, s.page, s.quote)}
      >
        {citation(s)} <ExternalLink size={13} />
      </button>
    ));
  }
  const valid = /^\d{1,5}$/.test(windowText) && Number(windowText) <= 36500;
  const comparisons =
    target?.date && valid
      ? [...anchors.keys()].sort().map((start) => ({
          start,
          ...compareDays(start, target.date!, Number(windowText)),
        }))
      : [];
  const diverges = new Set(comparisons.map((c) => c.outcome)).size > 1;
  const lengths = comparisons.map((c) => c.days);
  const firstSplit = Math.min(...lengths);
  const lastSplit = Math.max(...lengths) - 1;
  const splitNote =
    firstSplit >= 0 && firstSplit <= lastSplit
      ? firstSplit === lastSplit
        ? "Only a " +
          firstSplit +
          "-day window puts these incident dates on different sides of the cutoff."
        : "Windows of " +
          firstSplit +
          "–" +
          lastSplit +
          " days put these incident dates on different sides of the cutoff."
      : "";
  const limited = truncated
    ? "Citation limit reached. Additional dates may exist."
    : "";
  const scopeNote =
    scope === "extracted_incidents"
      ? "This older run contains extracted incident dates only."
      : "";
  const describe = (s: Evidence) => citation(s) + " — " + s.quote;
  function exportComparison() {
    if (!target) return;
    const lines = [
      "CLAIMPILOT · INTERVAL COMPARISON",
      report.overview.claim_number,
      "Analysis " + run,
      "Scenario window: " +
        windowText +
        " calendar days (inclusive). Incident day is day zero.",
      "Endpoint: " + label(target.kind) + " · " + target.date,
      ...target.sources.map(describe),
      ...comparisons.flatMap((c) => [
        "",
        "Incident " + c.start + " · " + c.days + " days · " + c.outcome,
        ...(c.start === recordDate ? ["Claim record at analysis"] : []),
        ...(anchors.get(c.start) || []).map(describe),
      ]),
      "",
      "User-selected comparison window. Coverage and policy deadlines require human review.",
      splitNote,
      scopeNote,
      limited,
    ];
    downloadText(
      report.overview.claim_number + "-interval.txt",
      lines.join("\n").trimEnd() + "\n",
    );
  }
  return (
    <section className="chronology" aria-label="Case chronology">
      <div className="chronoTitle">
        <CalendarDays aria-hidden="true" />
        <div>
          <h2>Case chronology</h2>
          <p>
            Trace dated events to their pages and compare the time elapsed from
            each reported incident date.
          </p>
        </div>
      </div>
      {(scopeNote || limited) && (
        <p className="note">{[scopeNote, limited].filter(Boolean).join(" ")}</p>
      )}
      <div className="chronoGrid">
        <section className="panel interval">
          <h3>Compare incident dates</h3>
          {target ? (
            <>
              <label>
                Compare up to
                <select
                  value={key(target)}
                  onChange={(e) => select(e.target.value)}
                >
                  {candidates.map((e) => (
                    <option key={key(e)} value={key(e)}>
                      {label(e.kind)} · {e.date}
                    </option>
                  ))}
                </select>
              </label>
              <div className="chronoRefs">{sources(target.sources)}</div>
              <label>
                Window in calendar days
                <input
                  type="number"
                  min="0"
                  max="36500"
                  step="1"
                  value={windowText}
                  onChange={(e) => setWindow(e.target.value)}
                />
              </label>
              <small>
                Scenario setting. The incident date is day zero. The last day is
                included.
              </small>
              {!valid && (
                <p role="alert">Enter a whole number from 0 to 36500.</p>
              )}
              <div aria-live="polite">
                {(splitNote || diverges) && (
                  <div className="chronoAlert">
                    <p>
                      {splitNote ||
                        "The choice of incident date changes the result."}
                    </p>
                    {splitNote && !diverges && firstSplit <= 36500 && (
                      <button
                        className="link"
                        onClick={() => setWindow(String(firstSplit))}
                      >
                        Test {firstSplit}-day window
                      </button>
                    )}
                  </div>
                )}
                {comparisons.map((c) => (
                  <div className="clockRow" key={c.start}>
                    <div>
                      <small>Incident · {c.start}</small>
                      <b>
                        {Math.abs(c.days)}{" "}
                        {Math.abs(c.days) === 1 ? "day" : "days"}{" "}
                        {c.days < 0 ? "before" : "elapsed"}
                      </b>
                    </div>
                    <span
                      className={
                        c.outcome === "Within window" ? "inWindow" : "outWindow"
                      }
                    >
                      {c.outcome}
                    </span>
                    <div className="chronoRefs">
                      {c.start === recordDate && <small>Claim record</small>}
                      {sources(anchors.get(c.start) || [])}
                    </div>
                  </div>
                ))}
              </div>
              <button disabled={!valid} onClick={exportComparison}>
                <Download size={15} />
                Export comparison
              </button>
            </>
          ) : (
            <p>
              A dated notice, inspection, invoice, treatment or policy boundary
              is needed to compare intervals.
            </p>
          )}
        </section>
        <section className="panel">
          <div className="panelhead">
            <h3>Document timeline</h3>
            <select
              aria-label="Filter event type"
              value={kind}
              onChange={(e) => filter(e.target.value)}
            >
              <option value="">All event types</option>
              {[...new Set(events.map((e) => e.kind))].sort().map((k) => (
                <option key={k} value={k}>
                  {label(k)}
                </option>
              ))}
            </select>
          </div>
          {!events.length && (
            <p>No supported date labels were found in this run.</p>
          )}
          <ol className="dateTrack">
            {events
              .filter((e) => !kind || kind === e.kind)
              .map((e) => (
                <li key={e.kind + "/" + e.value}>
                  <small>{e.date || "Date needs review"}</small>
                  <b>
                    {label(e.kind)}
                    {!e.date && " · " + e.value}
                  </b>
                  <div className="chronoRefs">{sources(e.sources)}</div>
                </li>
              ))}
          </ol>
        </section>
      </div>
    </section>
  );
}
