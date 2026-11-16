"""Teams / Outlook / M365 Copilot channel host using the Microsoft 365 Agents SDK (Python).

Run locally:  python -m ops_copilot.bot.app   (then use Microsoft 365 Agents Playground / Teams Toolkit)
Hosting:      Azure App Service with a user-assigned managed identity; Azure Bot Service
              authenticates to the bot using that identity (no client secret).

NOTE: the Agents SDK is evolving; the glue here is intentionally thin - all logic is in
handlers.py so swapping SDK versions only touches this file.
"""

from __future__ import annotations

from os import environ

from ..models import UserContext
from ..orchestrator import Orchestrator
from .handlers import handle_card_action, handle_message

ORCH = Orchestrator()
CARD_CONTENT_TYPE = "application/vnd.microsoft.card.adaptive"


def user_from_activity(activity) -> UserContext:
    frm = activity.from_property
    # Groups come from the user's token (groups/app-roles claim) after Teams SSO; default for demo.
    return UserContext(
        user_id=getattr(frm, "aad_object_id", None) or frm.id,
        display_name=frm.name or "Colleague",
        email=(getattr(frm, "properties", None) or {}).get("email", f"{frm.id}@contoso.com"),
    )


def create_app():  # pragma: no cover - requires SDK + runtime config
    from aiohttp.web import Application, Request, Response, run_app
    from microsoft_agents.activity import Activity, Attachment, load_configuration_from_env
    from microsoft_agents.authentication.msal import MsalConnectionManager
    from microsoft_agents.hosting.aiohttp import (
        CloudAdapter,
        jwt_authorization_middleware,
        start_agent_process,
    )
    from microsoft_agents.hosting.core import (
        AgentApplication,
        Authorization,
        MemoryStorage,
        TurnContext,
        TurnState,
    )

    config = load_configuration_from_env(environ)
    storage = MemoryStorage()  # use Cosmos DB / Blob storage in production
    connections = MsalConnectionManager(**config)
    adapter = CloudAdapter(connection_manager=connections)
    authorization = Authorization(storage, connections, **config)
    agent = AgentApplication[TurnState](storage=storage, adapter=adapter, authorization=authorization, **config)

    def card(content: dict):
        return Attachment(content_type=CARD_CONTENT_TYPE, content=content)

    @agent.conversation_update("membersAdded")
    async def on_welcome(context: TurnContext, _state: TurnState):
        await context.send_activity("Hi! I'm Ops Copilot. Ask me about policies, IT issues or your leave balance.")

    @agent.activity("message")
    async def on_message(context: TurnContext, _state: TurnState):
        await context.send_activity(Activity(type="typing"))
        content = handle_message(ORCH, context.activity.text or "", user_from_activity(context.activity))
        await context.send_activity(Activity(type="message", attachments=[card(content)]))

    @agent.activity("invoke")
    async def on_invoke(context: TurnContext, _state: TurnState):
        value = context.activity.value or {}
        action = value.get("action", {})
        content = handle_card_action(ORCH, action.get("verb", ""), action.get("data", {}),
                                     user_from_activity(context.activity))
        # Universal Actions: respond with the card that replaces the one the user clicked.
        await context.send_activity(Activity(type="invokeResponse", value={
            "status": 200, "body": {"statusCode": 200, "type": CARD_CONTENT_TYPE, "value": content}}))

    async def entry(req: Request) -> Response:
        return await start_agent_process(req, req.app["agent_app"], req.app["adapter"])

    app = Application(middlewares=[jwt_authorization_middleware])
    app.router.add_post("/api/messages", entry)
    app["agent_configuration"] = connections.get_default_connection_configuration()
    app["agent_app"], app["adapter"] = agent, adapter
    return app, run_app


if __name__ == "__main__":  # pragma: no cover
    application, run = create_app()
    run(application, host="0.0.0.0", port=int(environ.get("PORT", "3978")))
