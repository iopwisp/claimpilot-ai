import { Claim, Doc, ReviewResult, label, money } from "./api";

export function formatReport(
  claim: Claim,
  docs: Doc[],
  result: ReviewResult,
): string {
  const { report, review } = result;
  if (!report || !review)
    throw new Error("Run analysis before exporting a report.");
  const lines = [
    "CLAIMPILOT · CLAIM REVIEW",
    claim.claim_number,
    "",
    claim.claimant_name + " · " + claim.policy_number,
    "Claim amount: " + money(claim),
    "Incident date: " + claim.incident_date,
    claim.incident_description,
    "Review status: " + label(result.status),
    "Analysis: " + result.job_id,
    "Model: " +
      result.model +
      " · Prompt: " +
      result.prompt_version +
      " · " +
      result.analyzed_at,
  ];
  function section(title: string, items: string[], empty: string) {
    lines.push("", title, ...(items.length ? items : [empty]));
  }
  section(
    "DOCUMENTS",
    docs.map((d) => d.filename + " · " + label(d.kind)),
    "No documents.",
  );
  section(
    "VERIFIED AND EXTRACTED FIELDS",
    review.fields.map(
      (f) =>
        label(f.name) +
        ": " +
        (f.corrected || f.value) +
        " [" +
        label(f.review) +
        "]" +
        (f.corrected ? " (extracted: " + f.value + ")" : "") +
        "\n  " +
        f.filename +
        ", p. " +
        f.page +
        " — " +
        f.quote,
    ),
    "No sourced fields.",
  );
  section(
    "POLICY EVIDENCE",
    [
      report.policy.answer,
      ...report.policy.evidence.map(
        (e) =>
          (docs.find((d) => d.id === e.document_id)?.filename ||
            e.document_id) +
          ", p. " +
          e.page +
          " — " +
          e.quote,
      ),
    ],
    "Insufficient evidence.",
  );
  section(
    "CURRENT FINDINGS",
    review.current_issues.map(
      (i) =>
        label(i.type) +
        " — " +
        i.description +
        i.values
          .map(
            (f) =>
              "\n  " +
              (f.filename || "Claim record") +
              (f.page ? ", p. " + f.page : "") +
              (f.value ? ": " + (f.corrected || f.value) : ""),
          )
          .join(""),
    ),
    "No open findings.",
  );
  section(
    "RESOLVED BY CORRECTION",
    review.resolved_issues.map((i) => label(i.type) + " — " + i.description),
    "No resolved findings.",
  );
  section(
    "REQUIRED MATERIALS",
    report.required_items.map((i) => i.name + " — " + label(i.status)),
    "None.",
  );
  section(
    "RECOMMENDATIONS AT ANALYSIS",
    report.recommendations.map(
      (r) =>
        r.text +
        (review.actions.some(
          (a) =>
            a.action === "review.reject_recommendation" && a.entity_id === r.id,
        )
          ? " [Rejected by reviewer]"
          : ""),
    ),
    "None.",
  );
  section(
    "REVIEW HISTORY",
    review.actions.map(
      (a) =>
        a.created_at +
        " · " +
        a.action +
        (a.details.value ? " — " + a.details.value : ""),
    ),
    "Awaiting human review.",
  );
  return lines.join("\n") + "\n";
}

export function downloadReport(
  claim: Claim,
  docs: Doc[],
  result: ReviewResult,
) {
  const url = URL.createObjectURL(
    new Blob([formatReport(claim, docs, result)], {
      type: "text/plain;charset=utf-8",
    }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = claim.claim_number + "-review.txt";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
