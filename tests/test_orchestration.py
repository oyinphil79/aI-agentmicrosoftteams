import pytest


@pytest.mark.parametrize("q,route", [
    ("What is the hotel limit in London?", "knowledge"),
    ("My laptop screen is broken", "it"),
    ("What is the status of INC1000?", "it"),
    ("How many vacation days do I have left?", "hr"),
    ("Who is my manager?", "hr"),
    ("How do I reset my password?", "knowledge"),
])
def test_routing(orch, alex, q, route):
    assert orch.ask(q, alex).agent == route


def test_knowledge_answer_is_grounded_and_cited(orch, alex):
    r = orch.ask("What is the hotel limit in London?", alex)
    assert "260 USD" in r.text
    assert [c.title for c in r.citations] == ["Travel Policy"]
    assert not any("groundedness" in n for n in r.safety_notes)


def test_unknown_topic_refuses_without_citations(orch, alex):
    r = orch.ask("What is the policy on pet insurance?", alex)
    assert "won't guess" in r.text and r.citations == []


def test_hr_tool_calling(orch, alex):
    assert "14 days" in orch.ask("How many vacation days do I have?", alex).text


def test_ticket_requires_approval_then_executes(orch, alex):
    r = orch.ask("My VPN keeps disconnecting and I can't work", alex)
    assert r.pending_action and r.pending_action.tool == "create_ticket"
    assert r.pending_action.arguments["priority"] == "high"
    assert orch.tickets.list_for(alex.email)[-1]["title"] != r.pending_action.arguments["title"]  # not yet created
    done = orch.approve(r.pending_action, alex)
    assert done.text.startswith("Ticket INC")


def test_users_cannot_see_other_users_tickets(orch, sam_hr):
    assert "No ticket" in orch.ask("What is the status of INC1000?", sam_hr).text
