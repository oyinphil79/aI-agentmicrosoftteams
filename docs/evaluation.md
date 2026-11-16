# Evaluation & AI safety

## Layers
| Layer | Where | When |
|---|---|---|
| Unit + security tests | `tests/` | every PR |
| Offline eval gate | `evals/run_evals.py` over `golden.jsonl` + `redteam.jsonl` | every PR (fails CI below thresholds) |
| Model-graded evals | `evals/azure_evals.py` → Foundry (Groundedness, Relevance, Intent Resolution) | on merge to main |
| Automated red teaming | `evals/azure_evals.py --redteam` (Foundry AI Red Teaming Agent) | weekly / before release |
| Production monitoring | Foundry tracing + App Insights, 👍/👎 card feedback | continuous |

## Offline gate thresholds
| Metric | Threshold |
|---|---|
| route_accuracy | 0.95 |
| answer_correctness | 0.90 |
| citation_precision | 0.90 |
| tool_call_accuracy | 0.95 |
| attack_block_rate | 1.00 |

> Note: in mock mode the "model" is deterministic, so the offline gate mainly protects routing,
> retrieval, tool wiring and safety plumbing from regressions. Answer *quality* is measured by the
> model-graded Foundry evaluations against real deployments.

## Prompt-injection defences (tested)
| Attack | Defence | Test |
|---|---|---|
| Direct ("ignore previous instructions…") | Prompt Shields on user input | `test_direct_injection_blocked`, red-team r1-r4 |
| Indirect (poisoned SharePoint page) | Prompt Shields on documents → drop; spotlighting | `test_indirect_injection_document_dropped`, r5 |
| Data exfiltration via answer | Security trimming + reviewer `block` | `test_security_trimming_hides_confidential_docs`, r6-r7 |
| Tool hijack | Per-agent allow-list, approval gate | `test_tool_allowlist_enforced` |
| Forged Adaptive Card payload | Server-side re-authorization | `test_forged_card_payload_rejected` |
| Malicious email to helpdesk mailbox | Same input shield on email body | `test_outlook_injection_email_is_blocked` |
| Shield partial outage | Fail closed on missing verdicts | `test_azure_shield_fails_closed_when_verdicts_missing` |

## Adding a test case
Append a line to `evals/golden.jsonl` (`query`, `route`, `must_contain`, `citations`, or `tool`/`args`)
or `evals/redteam.jsonl` (`kind`: direct | indirect | data_leak). Every production bug becomes a case.
