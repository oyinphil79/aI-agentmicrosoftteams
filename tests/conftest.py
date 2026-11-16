import pytest

from ops_copilot.config import Settings
from ops_copilot.models import UserContext
from ops_copilot.orchestrator import Orchestrator


@pytest.fixture
def orch():
    return Orchestrator(Settings(mode="mock"))


@pytest.fixture
def alex():
    return UserContext("u-alex", "Alex Rivera", "alex@contoso.com", ("all-employees", "it-staff"))


@pytest.fixture
def sam_hr():
    return UserContext("u-sam", "Sam Okafor", "sam@contoso.com", ("all-employees", "hr-staff"))
