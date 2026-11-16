export interface Account {
  id: string;
  email: string;
  role: string;
}
export interface Claim {
  evidence_requests?: EvidenceTask[];
  reviewer_email?: string | null;
  id: string;
  claim_number: string;
  policy_number: string;
  claimant_name: string;
  claim_amount: number | string;
  currency: string;
  status: string;
  incident_date: string;
  incident_description: string;
  created_at: string;
  fields?: Fact[];
}
export interface EvidenceTask {
  id: string;
  item: string;
  status: "OPEN" | "SUBMITTED" | "ACCEPTED" | "WITHDRAWN";
  note: string;
  document_id: string | null;
  version: number;
  analysis_id: string;
}
export function isOutstanding(task: EvidenceTask) {
  return task.status === "OPEN" || task.status === "SUBMITTED";
}
export interface Fact {
  id: string;
  document_id: string;
  filename: string;
  name: string;
  value: string;
  corrected?: string;
  quote: string;
  page: number;
  review: string;
}
export interface Doc {
  metadata_json: {
    page_count?: number;
    classification_requires_review?: boolean;
  };
  id: string;
  filename: string;
  kind: string;
  status: string;
}
export interface Evidence {
  document_id: string;
  page: number;
  quote: string;
}
export interface Coverage {
  answer: string;
  evidence: Evidence[];
}
export interface Report {
  policy: Coverage;
  required_items: { name: string; status: string }[];
  inconsistencies: {
    type: string;
    description: string;
    values: Partial<Fact>[];
  }[];
  recommendations: { id: string; text: string }[];
}
export interface Event {
  action: string;
  entity_id: string;
  created_at: string;
  details: { value?: string; job_id?: string };
}
export interface ReviewResult {
  job_id: string;
  status: string;
  model: string | null;
  analyzed_at?: string;
  prompt_version?: string;
  report: Report | null;
  review?: {
    fields: Fact[];
    reviewed_fields: number;
    current_issues: Report["inconsistencies"];
    resolved_issues: Report["inconsistencies"];
    actions: Event[];
  };
}
export const statuses = [
  "DRAFT",
  "PROCESSING",
  "NEEDS_REVIEW",
  "READY_FOR_REVIEW",
  "COMPLETED",
  "FAILED",
];
export const label = (s: string) =>
  s
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/^./, (v) => v.toUpperCase());
export const money = (c: Claim) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: c.currency,
  }).format(Number(c.claim_amount));
export async function request<T>(
  path: string,
  method = "GET",
  data?: unknown,
): Promise<T> {
  const form = data instanceof FormData;
  const headers: Record<string, string> = {
    "X-ClaimPilot-Request": "browser",
  };
  if (!form && data !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch("/api/v1" + path, {
    method,
    headers,
    body: form ? data : data === undefined ? undefined : JSON.stringify(data),
  });
  const result = await response.json();
  if (response.status === 401 && !path.startsWith("/auth/")) {
    window.dispatchEvent(new Event("claimpilot-session-ended"));
  }
  if (!response.ok)
    throw Error(
      typeof result.detail === "string"
        ? result.detail
        : "Check the entered values (" + response.status + ")",
    );
  return result as T;
}
