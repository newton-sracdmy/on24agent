"""Keeps a channel's "typing…" indicator visible while the AI reply is being generated.

Meta hides the indicator on its own after ~20s (Messenger/Instagram) or ~25s (WhatsApp),
or as soon as a reply is sent, so we re-send it periodically until the reply is ready.
"""

import asyncio
from typing import Awaitable, Callable

REFRESH_INTERVAL_SECONDS = 15.0
MAX_TYPING_SECONDS = 90.0


def start_typing(send_indicator: Callable[[], Awaitable[None]]) -> asyncio.Task:
    """Send the indicator now and keep refreshing it in the background; stop with stop_typing()."""

    async def _loop() -> None:
        elapsed = 0.0
        while elapsed < MAX_TYPING_SECONDS:
            await send_indicator()
            await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
            elapsed += REFRESH_INTERVAL_SECONDS

    return asyncio.create_task(_loop())


async def stop_typing(task: asyncio.Task) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
