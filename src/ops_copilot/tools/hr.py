"""HR REST API client (leave balances). Mock data offline; OpenAPI spec in docs/hr-api.openapi.yaml."""

from __future__ import annotations

from ..models import UserContext

_BALANCES = {"alex@contoso.com": {"annual": 14, "sick": 8}, "sam@contoso.com": {"annual": 21, "sick": 10}}


class MockHrApi:
    def leave_balance(self, user: UserContext) -> dict:
        return {"employee": user.display_name, "unit": "days", **_BALANCES.get(user.email, {"annual": 20, "sick": 10})}
