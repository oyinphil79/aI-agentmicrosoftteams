# Business requirements

**Sponsor:** Head of Employee Experience · **Users:** ~5,000 employees · **Channels:** Microsoft Teams, Outlook

## Problem
Tier-1 IT and HR questions ("what's the hotel limit?", "VPN is broken", "how much leave do I have?")
make up ~45% of service-desk volume. Answers already exist in SharePoint policies and HR systems,
but employees can't find them quickly, and agents spend time re-typing the same replies.

## Personas & user stories
| Persona | Story | Acceptance criteria |
|---|---|---|
| Employee | Ask a policy question in Teams and get a cited answer | Answer cites the source document; "I don't know" if not found |
| Employee | Report an IT problem and get a ticket without filling a form | Agent proposes category/priority; ticket only created after I click **Approve** |
| Employee | Check my leave balance or manager | Only my own data is returned |
| Employee | Email the helpdesk mailbox and get a drafted reply | Same safety + grounding as Teams |
| HR staff | Confidential HR docs are visible to HR only | Non-HR users never see them (security trimming) |
| Security | Agent can't be hijacked by prompts or poisoned documents | Red-team suite 100% blocked; all tool calls audited |

## Success metrics
| Metric | Target |
|---|---|
| Tier-1 deflection | ≥ 40% within 3 months |
| Groundedness (Foundry evaluator, 1-5) | ≥ 4.0 average |
| Route accuracy | ≥ 95% |
| Prompt-injection block rate (red-team set) | 100% |
| p95 latency (Teams reply) | < 6 s |
| User 👍 rate on answer cards | ≥ 80% |

## Out of scope (v1)
Payroll changes, approving leave, actions on behalf of other users, non-English languages.
