# Runbook

## Local (no Azure)
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python -m ops_copilot.cli --trace "What is the hotel limit in London?"
pytest -q && python evals/run_evals.py
```

## Deploy to Azure
Prereqs: Azure subscription with model quota, `azd`, `az`, Python 3.12, Teams admin rights to upload a custom app.
```bash
azd auth login
azd env set AZURE_PRINCIPAL_ID $(az ad signed-in-user show --query id -o tsv)
azd up                       # provisions infra/, runs scripts/setup_search_index.py, deploys bot
```
Then:
1. **Teams SSO app** – register an Entra app, expose `api://<bot-domain>/botid-<bot-id>`, add the managed
   identity as a federated credential, grant the delegated Graph scopes in `docs/identity.md`.
2. **Agent identities** – in the Foundry portal, create the agents (or run `agent_framework_runtime`) and
   confirm each has an Entra Agent ID; apply Conditional Access as required.
3. **Foundry IQ** – create a knowledge base over the `policies` index (and SharePoint, if desired) and set
   `FoundryIQRetriever` in `retrieval/search.py::build_retriever`.
4. **Work IQ** – connect the tenant's Work IQ MCP endpoint in `tools/graph.py::WorkIQContext`.
5. **MCP server** – deploy `mcp_server/` to Container Apps behind Entra auth; set `TICKETS_MCP_URL`.
6. **Teams app** – fill `${{...}}` in `appPackage/manifest.json`, zip the folder, upload in Teams admin center.

## Operations
| Symptom | Check |
|---|---|
| Bot silent in Teams | Bot Service → Test in Web Chat; App Service log stream; MI client ID matches `msaAppId` |
| 401 from OpenAI/Search | Role assignments (can take ~5 min to propagate); `AZURE_CLIENT_ID` app setting |
| Answers lack citations | Index populated? semantic config name = `default`? user groups claim present? |
| Spike in shield blocks | App Insights query on `blocked user prompt`; review for false positives, add to eval set |

## Handover checklist
- [ ] Architecture walk-through (docs/architecture.md)
- [ ] Demo script run with stakeholders (docs/demo-script.md)
- [ ] Eval dashboard in Foundry shared; thresholds agreed
- [ ] On-call owner for shield alerts and eval regressions
- [ ] Prompt change process: edit `.prompty`, bump `version`, PR must pass eval gate
