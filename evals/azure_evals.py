"""Model-graded evaluation with Azure AI Evaluation SDK, logged to the Foundry project.

Runs the real (azure-mode) pipeline over golden.jsonl, then scores groundedness, relevance and
intent resolution with an LLM judge; results appear under Evaluations in the Foundry portal.

    OPS_COPILOT_MODE=azure python evals/azure_evals.py

Also see the Foundry AI Red Teaming Agent (azure-ai-evaluation[redteam]) for automated
adversarial scans: python evals/azure_evals.py --redteam
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def build_dataset(path: Path) -> Path:
    from ops_copilot.models import UserContext
    from ops_copilot.orchestrator import Orchestrator

    orch = Orchestrator()
    user = UserContext("eval", "Eval User", "alex@contoso.com", ("all-employees",))
    rows = []
    for line in (ROOT / "evals" / "golden.jsonl").read_text().splitlines():
        case = json.loads(line)
        r = orch.ask(case["query"], user)
        rows.append({"query": case["query"], "response": r.text,
                     "context": "\n".join(r.grounding) or "(no retrieved context)"})
    path.write_text("\n".join(json.dumps(r) for r in rows))
    return path


def run_quality() -> None:  # pragma: no cover - needs Azure
    from azure.ai.evaluation import (
        GroundednessEvaluator,
        IntentResolutionEvaluator,
        RelevanceEvaluator,
        evaluate,
    )
    from azure.identity import DefaultAzureCredential

    model_config = {"azure_endpoint": os.environ["AZURE_OPENAI_ENDPOINT"],
                    "azure_deployment": os.environ.get("AZURE_OPENAI_JUDGE_DEPLOYMENT", "gpt-4.1")}
    cred = DefaultAzureCredential()
    data = build_dataset(ROOT / "evals" / "results" / "azure_dataset.jsonl")
    result = evaluate(
        data=str(data),
        evaluators={
            "groundedness": GroundednessEvaluator(model_config, credential=cred),
            "relevance": RelevanceEvaluator(model_config, credential=cred),
            "intent_resolution": IntentResolutionEvaluator(model_config, credential=cred),
        },
        azure_ai_project=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        evaluation_name="ops-copilot-golden",
    )
    print(json.dumps(result["metrics"], indent=2))


def run_redteam() -> None:  # pragma: no cover - needs Azure
    import asyncio

    from azure.ai.evaluation.red_team import AttackStrategy, RedTeam, RiskCategory
    from azure.identity import DefaultAzureCredential

    from ops_copilot.models import UserContext
    from ops_copilot.orchestrator import Orchestrator

    orch, user = Orchestrator(), UserContext("rt", "Red Team", "alex@contoso.com")

    def target(query: str) -> str:
        return orch.ask(query, user).text

    rt = RedTeam(azure_ai_project=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=DefaultAzureCredential(),
                 risk_categories=[RiskCategory.Violence, RiskCategory.HateUnfairness, RiskCategory.SelfHarm,
                                  RiskCategory.Sexual], num_objectives=5)
    asyncio.run(rt.scan(target=target, scan_name="ops-copilot-redteam",
                        attack_strategies=[AttackStrategy.EASY, AttackStrategy.MODERATE, AttackStrategy.Jailbreak]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--redteam", action="store_true")
    (ROOT / "evals" / "results").mkdir(parents=True, exist_ok=True)
    run_redteam() if ap.parse_args().redteam else run_quality()
