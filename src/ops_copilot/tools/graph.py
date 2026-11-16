"""Microsoft Graph + Work IQ access, always as the signed-in user (delegated / on-behalf-of).

Delegated permissions mean the agent can never read more than the user could
read themselves. See docs/permissions.md for the scope matrix.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Protocol

from ..models import UserContext


class GraphClient(Protocol):
    def get_manager(self, user: UserContext) -> dict[str, Any]: ...
    def get_upcoming_meetings(self, user: UserContext, days: int = 1) -> list[dict[str, Any]]: ...
    def send_mail(self, user: UserContext, to: str, subject: str, html_body: str) -> None: ...


class WorkContext(Protocol):
    def search(self, user: UserContext, query: str) -> list[dict[str, str]]: ...


# --------------------------------------------------------------------------- mocks

_DIRECTORY = {
    "alex@contoso.com": {"displayName": "Morgan Lee", "mail": "morgan.lee@contoso.com", "jobTitle": "IT Director"},
    "sam@contoso.com": {"displayName": "Priya Shah", "mail": "priya.shah@contoso.com", "jobTitle": "HR Lead"},
}


class MockGraph:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    def get_manager(self, user: UserContext) -> dict[str, Any]:
        return _DIRECTORY.get(user.email, {"displayName": "Jordan Kim", "mail": "jordan.kim@contoso.com"})

    def get_upcoming_meetings(self, user: UserContext, days: int = 1) -> list[dict[str, Any]]:
        d = (date.today() + timedelta(days=1)).isoformat()
        return [{"subject": "VPN migration stand-up", "start": f"{d}T09:30", "organizer": "Morgan Lee"}]

    def send_mail(self, user: UserContext, to: str, subject: str, html_body: str) -> None:
        self.sent.append({"from": user.email, "to": to, "subject": subject, "body": html_body})


class MockWorkContext:
    def search(self, user: UserContext, query: str) -> list[dict[str, str]]:
        return [{
            "title": "Email: VPN client migration - action required",
            "source": "outlook://message/mock-123",
            "content": "From Morgan Lee: All staff must install GlobalConnect 6 before 1 December. "
                       "The old VPN client stops working on 1 December.",
        }]


# --------------------------------------------------------------------------- real


class OnBehalfOfTokenProvider:
    """Exchanges the user's Teams SSO token for a Graph token (OAuth 2.0 OBO flow).

    In Azure the confidential client authenticates with a federated credential
    backed by the app's managed identity, so no client secret is stored.
    """

    def __init__(self, client_id: str, tenant_id: str, client_assertion_fn):
        import msal

        self._app = msal.ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential={"client_assertion": client_assertion_fn},
        )

    def token(self, user: UserContext, scopes: list[str]) -> str:
        if not user.access_token:
            raise PermissionError("No user token: sign-in (Teams SSO) is required")
        result = self._app.acquire_token_on_behalf_of(user.access_token, scopes)
        if "access_token" not in result:
            raise PermissionError(result.get("error_description", "OBO exchange failed"))
        return result["access_token"]


class RealGraph:
    BASE = "https://graph.microsoft.com/v1.0"

    def __init__(self, tokens: OnBehalfOfTokenProvider):
        import httpx

        self._tokens = tokens
        self._http = httpx.Client(timeout=15)

    def _get(self, user: UserContext, path: str, scopes: list[str], **params) -> dict[str, Any]:
        h = {"Authorization": f"Bearer {self._tokens.token(user, scopes)}"}
        r = self._http.get(f"{self.BASE}{path}", headers=h, params=params)
        r.raise_for_status()
        return r.json()

    def get_manager(self, user: UserContext) -> dict[str, Any]:
        return self._get(user, "/me/manager", ["User.ReadBasic.All"], **{"$select": "displayName,mail,jobTitle"})

    def get_upcoming_meetings(self, user: UserContext, days: int = 1) -> list[dict[str, Any]]:
        start = date.today().isoformat()
        end = (date.today() + timedelta(days=days)).isoformat()
        data = self._get(user, "/me/calendarView", ["Calendars.Read"], startDateTime=start, endDateTime=end,
                         **{"$select": "subject,start,organizer", "$top": "10"})
        return [{"subject": e["subject"], "start": e["start"]["dateTime"],
                 "organizer": e["organizer"]["emailAddress"]["name"]} for e in data.get("value", [])]

    def send_mail(self, user: UserContext, to: str, subject: str, html_body: str) -> None:
        h = {"Authorization": f"Bearer {self._tokens.token(user, ['Mail.Send'])}"}
        r = self._http.post(f"{self.BASE}/me/sendMail", headers=h, json={"message": {
            "subject": subject, "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": to}}]}})
        r.raise_for_status()


class WorkIQContext:
    """Work IQ: the user's work context (mail, meetings, chats, files) via its MCP server.

    Wire this to the Work IQ MCP endpoint your tenant exposes; it is called with the
    user's delegated token so results are permission-trimmed by Microsoft 365.
    """

    def __init__(self, mcp_url: str):
        self._url = mcp_url

    def search(self, user: UserContext, query: str) -> list[dict[str, str]]:  # pragma: no cover - needs tenant
        raise NotImplementedError("Connect to the Work IQ MCP server for your tenant (see docs/runbook.md)")
