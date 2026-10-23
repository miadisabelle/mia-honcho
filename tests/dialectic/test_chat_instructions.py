"""Workspace chat guidance reaches every dialectic path without changing recall."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.dialectic.chat import (
    agentic_chat,
    agentic_chat_stream,
    workspace_chat,
    workspace_chat_stream,
)
from src.dialectic.core import DialecticAgent
from src.dialectic.prompts import agent_system_prompt, workspace_agent_system_prompt
from src.dialectic.workspace import WorkspaceDialecticAgent
from src.models import Peer, Session, Workspace
from src.schemas import ChatConfiguration, WorkspaceConfiguration
from src.utils.config_helpers import get_configuration

INSTRUCTIONS = "Enter the requested creative voice directly. No preamble or 'Je vais'."


@pytest.mark.parametrize("workspace_wide", [False, True])
@pytest.mark.parametrize("stream", [False, True])
async def test_all_chat_paths_use_workspace_instructions(
    db_session: AsyncSession,
    sample_data: tuple[Workspace, Peer],
    workspace_wide: bool,
    stream: bool,
) -> None:
    workspace, peer = sample_data
    workspace.configuration = {
        "peer_card": {"use": False},
        "chat": {"instructions": INSTRUCTIONS},
    }
    session = Session(
        workspace_name=workspace.name,
        name="creative-chat",
        configuration={"chat": {"instructions": "SESSION MUST NOT OVERRIDE"}},
    )
    db_session.add(session)
    await db_session.commit()

    prompts: list[str] = []

    async def answer(agent: DialecticAgent, query: str, **_kwargs: object) -> str:
        assert query == "Imagine a name."
        prompts.append(agent.messages[0]["content"])
        return "Le Veilleur"

    async def answer_stream(agent: DialecticAgent, query: str, **kwargs: object):
        yield await answer(agent, query, **kwargs)

    agent_cls = WorkspaceDialecticAgent if workspace_wide else DialecticAgent
    with (
        patch.object(agent_cls, "answer", answer),
        patch.object(agent_cls, "answer_stream", answer_stream),
    ):
        if workspace_wide:
            if stream:
                result = "".join(
                    [
                        chunk
                        async for chunk in workspace_chat_stream(
                            workspace.name, session.name, "Imagine a name."
                        )
                    ]
                )
            else:
                result = await workspace_chat(
                    workspace.name, session.name, "Imagine a name."
                )
        else:
            if stream:
                result = "".join(
                    [
                        chunk
                        async for chunk in agentic_chat_stream(
                            workspace.name,
                            session.name,
                            "Imagine a name.",
                            peer.name,
                            peer.name,
                            session_allowlist=[session.name],
                        )
                    ]
                )
            else:
                result = await agentic_chat(
                    workspace.name,
                    session.name,
                    "Imagine a name.",
                    peer.name,
                    peer.name,
                    session_allowlist=[session.name],
                )

    assert result == "Le Veilleur"
    assert len(prompts) == 1
    assert INSTRUCTIONS in prompts[0]
    assert "SESSION MUST NOT OVERRIDE" not in prompts[0]
    assert "Never present invented identities" in prompts[0]
    assert "requested response schema" in prompts[0]
    assert "change the available tools" in prompts[0]
    assert (
        get_configuration(None, session, workspace).reasoning.custom_instructions
        is None
    )


@pytest.mark.parametrize("instructions", [None, "", "  \n\t"])
def test_unset_or_blank_instructions_preserve_default_prompt(
    instructions: str | None,
) -> None:
    assert agent_system_prompt(
        "p", "p", None, None, chat_instructions=instructions
    ) == agent_system_prompt("p", "p", None, None)
    assert (
        workspace_agent_system_prompt(chat_instructions=instructions)
        == workspace_agent_system_prompt()
    )
    assert "## WORKSPACE CHAT INSTRUCTIONS" not in workspace_agent_system_prompt()


def test_chat_instructions_have_an_independent_size_limit() -> None:
    assert ChatConfiguration(instructions="x" * 10000).instructions
    with pytest.raises(ValidationError):
        WorkspaceConfiguration.model_validate({"chat": {"instructions": "x" * 10001}})


def test_workspace_instructions_roundtrip_and_clear(
    client: TestClient, sample_data: tuple[Workspace, Peer]
) -> None:
    workspace, _ = sample_data
    url = f"/v3/workspaces/{workspace.name}"
    response = client.put(
        url,
        json={"configuration": {"chat": {"instructions": INSTRUCTIONS}}},
    )
    assert response.status_code == 200
    assert response.json()["configuration"]["chat"]["instructions"] == INSTRUCTIONS

    too_long = client.put(
        url, json={"configuration": {"chat": {"instructions": "x" * 10001}}}
    )
    assert too_long.status_code == 422

    cleared = client.put(url, json={"configuration": {"chat": {"instructions": ""}}})
    assert cleared.status_code == 200
    assert cleared.json()["configuration"]["chat"]["instructions"] == ""
