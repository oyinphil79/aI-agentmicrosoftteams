"""Outlook channel: triage an inbound email to the helpdesk mailbox and draft a reply.

Triggered by a Graph change notification (subscription on /users/{helpdesk}/mailFolders/inbox/messages)
or by the Teams/Outlook agent channel. Email bodies are UNTRUSTED: they pass through the same
Prompt Shields as chat messages before any agent sees them.
"""

from __future__ import annotations

import html
import re

from ..models import UserContext
from ..orchestrator import Orchestrator


def _strip_html(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", s)).strip()


def triage_email(orch: Orchestrator, sender: UserContext, subject: str, body_html: str) -> dict:
    question = f"{subject}. {_strip_html(body_html)}"[:2000]
    r = orch.ask(question, sender)
    if r.blocked:
        reply = "Your message was flagged by our safety filters and forwarded to a human agent."
    elif r.pending_action:
        reply = r.text.replace("Shall I submit it?", "Reply YES to this email or open Teams to approve it.")
    else:
        reply = r.text
    cites = "".join(f"<li><a href='{html.escape(c.source)}'>{html.escape(c.title)}</a></li>" for c in r.citations)
    body = f"<p>Hi {html.escape(sender.display_name.split()[0])},</p><p>{html.escape(reply)}</p>"
    if cites:
        body += f"<p>Sources:</p><ul>{cites}</ul>"
    body += "<p><i>Drafted by Ops Copilot (AI). A human reviews before high-impact actions.</i></p>"
    orch.graph.send_mail(sender, sender.email, f"RE: {subject}", body)
    return {"agent": r.agent, "blocked": r.blocked, "needs_approval": bool(r.pending_action), "html": body}
