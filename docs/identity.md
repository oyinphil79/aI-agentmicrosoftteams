# Identity, agent identity & permissions

## Identities
| Identity | Type | Used for |
|---|---|---|
| `id-opscopilot-*` | User-assigned managed identity | Bot Service ↔ bot auth, calls to Foundry/OpenAI, Search, Content Safety, Key Vault |
| Agent identities (router, knowledge, it, hr, reviewer) | **Entra Agent ID** (created per agent in the Foundry project) | Distinct audit trail per agent, Conditional Access for agents, per-agent tool/resource scopes |
| Ops Copilot SSO app | Entra app registration | Teams SSO; exchanged **on-behalf-of** for Graph / Search tokens. Uses a federated credential backed by the managed identity — no client secret |
| Search service | System-assigned MI | Integrated vectorizer calls the embedding deployment |
| GitHub Actions | Workload identity federation (OIDC) | CI model-graded evals; no stored secrets |

## Azure RBAC (least privilege) — see `infra/resources.bicep`
| Principal | Role | Scope |
|---|---|---|
| Bot MI | Cognitive Services OpenAI User | AI Services account |
| Bot MI | Cognitive Services User (Prompt Shields) | AI Services account |
| Bot MI | Azure AI User | Foundry project |
| Bot MI | Search Index Data **Reader** | Search service |
| Bot MI | Key Vault Secrets User | Key Vault |
| Search MI | Cognitive Services OpenAI User | AI Services account |
| Developer | OpenAI User, Cognitive Services User, Search Index Data Contributor, Search Service Contributor, Azure AI User | Dev only (`principalId` param) |

## Microsoft Graph (delegated only)
| Scope | Why | Admin consent |
|---|---|---|
| `User.Read` | Signed-in user profile | No |
| `User.ReadBasic.All` | Resolve manager display name/mail | No |
| `Calendars.Read` | `get_upcoming_meetings` | No |
| `Mail.Send` | Outlook reply drafts from the helpdesk flow | Yes (org policy) |

Not granted: any `*.ReadWrite.All` or **application** permissions. If a feature needs one, it gets its own
reviewed app registration.

## Application-level authorization
- **Tool allow-lists per agent** (`safety/tool_policy.py`): the knowledge agent has no tools; HR agent
  cannot create tickets, etc. Enforced in code, not just in prompts.
- **Group-gated tools / documents**: `allowed_groups` on index documents + `TOOL_REQUIRED_GROUPS`.
- **Object-level checks**: users can only read their own tickets (`TicketStore.get`).
- **Card payload re-validation**: Adaptive Card data is client-controlled; `approve()` re-runs authorization.

## Production hardening checklist
- [ ] Private endpoints for AI Services, Search, Key Vault; `publicNetworkAccess: Disabled`
- [ ] Conditional Access policy targeting agent identities
- [ ] Diagnostic settings → Log Analytics for all resources; alert on shield detections
- [ ] Cosmos DB for conversation state (replace `MemoryStorage`)
- [ ] Purview sensitivity labels honoured by the index (exclude Highly Confidential)
