from __future__ import annotations

import pytest

from pac_poc.agent_poc import (
    AgentDefinition,
    AgentResult,
    AgentResultStatus,
    SimulatedAgentRegistry,
    derive_child_permissions,
)


def test_registry_requires_every_non_main_agent_to_be_explicitly_simulated() -> None:
    registry = SimulatedAgentRegistry(
        [AgentDefinition(key="main_assistant", model_id="qwen3.5:0.8b")]
    )

    assert registry.get("main_assistant").simulated is False
    with pytest.raises(ValueError, match="POC simulations"):
        registry.register(
            AgentDefinition(key="research", model_id="local-test-model", simulated=False)
        )


def test_simulated_agent_registry_routes_without_creating_product_agent_runs() -> None:
    registry = SimulatedAgentRegistry(
        [
            AgentDefinition(key="main_assistant", model_id="qwen3.5:0.8b"),
            AgentDefinition(key="research_sim", model_id="local-test-a", simulated=True),
            AgentDefinition(key="review_sim", model_id="local-test-b", simulated=True),
        ]
    )

    assert registry.keys == ("main_assistant", "research_sim", "review_sim")
    assert registry.product_agent_run_count == 0
    assert registry.get("research_sim").model_id == "local-test-a"


def test_child_permissions_are_intersection_of_parent_and_requested_permissions() -> None:
    permissions = derive_child_permissions(
        parent=frozenset({"memory.read", "file.read_selected"}),
        requested=frozenset({"memory.read", "calendar.write"}),
    )

    assert permissions == frozenset({"memory.read"})


def test_agent_result_requires_known_status_and_safe_summary() -> None:
    result = AgentResult(
        status=AgentResultStatus.PARTIAL,
        summary="已完成本地模拟。",
        warnings=("这是 POC 结果，不是已交付 Agent 功能。",),
        evidence=("fixture:local-case-1",),
    )

    assert result.status is AgentResultStatus.PARTIAL
    assert result.evidence == ("fixture:local-case-1",)
    with pytest.raises(ValueError, match="summary"):
        AgentResult(status=AgentResultStatus.SUCCESS, summary=" ")
