# Evaluation report

Provider: local-rules-v1. Prompt: 2026-11-v1. Cases: 50.

| Metric | Observed |
|---|---:|
| structured_extraction_exact_match | 100.00% |
| document_classification_macro_f1 | 100.00% |
| retrieval_recall_at_5 | 100.00% |
| structured_output_validity | 100.00% |
| source_citation_correctness | 100.00% |
| insufficient_evidence_accuracy | 100.00% |

issues_match: 50/50 cases.  
missing_match: 50/50 cases.  
policy_citation_match: 50/50 cases.  

Synthetic English vehicle cases use labelled PDF fields and five document classes. These measurements describe this fixture distribution only. OCR, photographs, free-form prose and production traffic require separate evaluation.
