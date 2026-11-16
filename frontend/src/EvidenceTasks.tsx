import { useState } from "react";
import { Claim, Doc, EvidenceTask, isOutstanding, request } from "./api";
import { Badge } from "./shared";

interface Props {
  claim: Claim;
  docs: Doc[];
  role: string;
  busy: boolean;
  open: (id: string) => void;
  act: (operation: () => Promise<unknown>) => Promise<void>;
}

export function EvidenceTasks(props: Props) {
  if (!props.claim.evidence_requests?.length) return null;
  return (
    <section className="panel">
      <h2>Evidence requests</h2>
      {props.claim.evidence_requests.map((task) => (
        <EvidenceRow
          key={task.id + "-" + task.version}
          {...props}
          task={task}
        />
      ))}
    </section>
  );
}

function EvidenceRow({
  claim,
  docs,
  role,
  busy,
  open,
  act,
  task,
}: Props & { task: EvidenceTask }) {
  const [documentId, choose] = useState(""),
    [reason, write] = useState("");
  const linked = docs.find((d) => d.id === task.document_id);
  const editable =
    isOutstanding(task) && !["COMPLETED", "PROCESSING"].includes(claim.status);
  const reviewer = editable && role !== "handler";
  const handler = editable && role !== "reviewer" && task.status === "OPEN";
  function change(action: string) {
    return act(() =>
      request("/claims/" + claim.id + "/evidence/" + task.id, "POST", {
        action,
        version: task.version,
        note: reason,
        document_id: documentId || null,
      }),
    );
  }
  return (
    <div className="field">
      <div className="inline">
        <b>{task.item}</b>
        <Badge value={task.status} />
      </div>
      {task.note && <p>{task.note}</p>}
      {linked && (
        <button className="link" onClick={() => open(linked.id)}>
          View {linked.filename}
        </button>
      )}
      {handler && (
        <form
          className="inline"
          onSubmit={(e) => {
            e.preventDefault();
            change("submit");
          }}
        >
          <select
            aria-label={"Document for " + task.item}
            value={documentId}
            required
            onChange={(e) => choose(e.target.value)}
          >
            <option value="">Choose a processed document</option>
            {docs
              .filter((d) => d.status === "READY")
              .map((d) => (
                <option key={d.id} value={d.id}>
                  {d.filename}
                </option>
              ))}
          </select>
          <button disabled={busy || !documentId}>Submit document</button>
        </form>
      )}
      {reviewer && (
        <div className="inline">
          {task.status === "SUBMITTED" && (
            <button disabled={busy} onClick={() => change("accept")}>
              Accept evidence
            </button>
          )}
          <input
            aria-label="Reason for return or withdrawal"
            placeholder="Reason for return or withdrawal"
            maxLength={2000}
            value={reason}
            onChange={(e) => write(e.target.value)}
          />
          {task.status === "SUBMITTED" && (
            <button
              disabled={busy || !reason.trim()}
              onClick={() => change("return")}
            >
              Return to handler
            </button>
          )}
          <button
            disabled={busy || !reason.trim()}
            onClick={() => change("withdraw")}
          >
            Withdraw request
          </button>
        </div>
      )}
    </div>
  );
}
