"""The SDK preserves workspace-only chat instructions on write and read."""

from sdks.python.src.honcho.api_types import ChatConfiguration, WorkspaceConfiguration
from sdks.python.src.honcho.client import Honcho


async def test_workspace_chat_instructions_roundtrip(
    client_fixture: tuple[Honcho, str],
) -> None:
    client, mode = client_fixture
    configuration = WorkspaceConfiguration(
        chat=ChatConfiguration(instructions="No preamble. Enter the creative voice.")
    )
    if mode == "async":
        await client.aio.set_configuration(configuration)
        actual = await client.aio.get_configuration()
    else:
        client.set_configuration(configuration)
        actual = client.get_configuration()
    assert actual.chat is not None
    assert actual.chat.instructions == "No preamble. Enter the creative voice."
