from __future__ import annotations
from .runtime import RuntimeBundle


class VictorAIBot:
    def __init__(self, runtime: RuntimeBundle):
        self.runtime = runtime

    def start(self) -> None:
        self.runtime.start()

    async def stop(self) -> None:
        await self.runtime.stop()
