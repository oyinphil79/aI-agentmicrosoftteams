"""Local chat loop: `python -m ops_copilot.cli` (mock mode needs no Azure)."""

from __future__ import annotations

import argparse
import json

from .cards import answer_card
from .models import UserContext
from .orchestrator import Orchestrator

USERS = {
    "alex": UserContext("u-alex", "Alex Rivera", "alex@contoso.com", ("all-employees", "it-staff")),
    "sam": UserContext("u-sam", "Sam Okafor", "sam@contoso.com", ("all-employees", "hr-staff")),
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("question", nargs="*")
    p.add_argument("--user", choices=USERS, default="alex")
    p.add_argument("--card", action="store_true", help="print the Adaptive Card JSON")
    p.add_argument("--trace", action="store_true")
    args = p.parse_args()
    orch, user = Orchestrator(), USERS[args.user]

    def run(q: str) -> None:
        r = orch.ask(q, user)
        print(f"\n[{r.agent}] {r.text}")
        for c in r.citations:
            print(f"   - {c.title} ({c.source})")
        for n in r.safety_notes:
            print(f"   ! {n}")
        if args.trace:
            print("   trace:", *r.trace, sep="\n     ")
        if args.card:
            print(json.dumps(answer_card(r), indent=2))
        if r.pending_action and input("Approve? [y/N] ").lower().startswith("y"):
            print(f"[{r.agent}] {orch.approve(r.pending_action, user, r.agent).text}")

    if args.question:
        run(" ".join(args.question))
        return
    print(f"Ops Copilot (mode={orch.settings.mode}, user={user.email}). Ctrl-D to quit.")
    try:
        while True:
            run(input("\n> "))
    except EOFError:
        pass


if __name__ == "__main__":
    main()
