import { useState } from "react";
import { ArrowRight, Files } from "lucide-react";
import { Claim, request } from "./api";
import { Modal } from "./shared";

const scenarios = [
  [
    "04-notice-window",
    "Disputed notice window",
    "Compare two incident dates against the same notification receipt.",
  ],
  [
    "01-complete",
    "Complete claim",
    "Check the required materials and find the applicable coverage clause.",
  ],
  [
    "02-date-mismatch",
    "Conflicting incident dates",
    "Compare the claim form with the date in the police report.",
  ],
  [
    "03-missing-evidence",
    "Missing damage evidence",
    "Identify what the handler still needs to request.",
  ],
];

export function Samples({
  close,
  opened,
}: {
  close: () => void;
  opened: (claim: Claim) => void;
}) {
  const [choice, choose] = useState("02-date-mismatch");
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function create() {
    setBusy(true);
    setError("");
    try {
      opened(
        await request<Claim>("/samples", "POST", {
          scenario: choice,
          request_id: key,
        }),
      );
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  return (
    <Modal
      title="Open a sample case"
      close={() => {
        if (!busy) close();
      }}
    >
      <p className="sub">
        Choose a fictional claim. Its PDFs will be processed in your workspace.
      </p>
      <fieldset className="sampleChoices" disabled={busy}>
        <legend className="sr-only">Scenario</legend>
        {scenarios.map(([id, name, description]) => (
          <label key={id}>
            <input
              type="radio"
              name="scenario"
              checked={choice === id}
              onChange={() => {
                choose(id);
                setKey(crypto.randomUUID());
              }}
            />
            <span>
              <strong>{name}</strong>
              <small>{description}</small>
            </span>
          </label>
        ))}
      </fieldset>
      {error && <p role="alert">{error}</p>}
      <div className="actions">
        <button className="primary" disabled={busy} onClick={create}>
          <Files size={16} />
          {busy ? "Importing PDFs…" : "Import sample"}
          <ArrowRight size={16} />
        </button>
      </div>
    </Modal>
  );
}
