import asyncio
from typing import Any

import tinkoff.invest as ti

import trading_bot.tinkoff_client.client as tc
from trading_bot.tinkoff_client.client import StreamMarketData


class StreamManager:
    def __init__(self, client: tc.TinkoffClient):
        self._stream_market_data: tc.StreamMarketData = StreamMarketData(client._api)

        self.map_context: dict[str, Any] = {}  # TODO: вместо Any добавить context
        self.map_task: dict[str, asyncio.Task] = {}

    async def _listen_market_data(self):
        while True:
            response = await self._stream_market_data.request_queue.get()
            self.handler(response)

    def handler(self, response: ti.MarketDataResponse):
        if response.last_price:
            context = self.map_context.get(response.last_price.instrument_uid)
            if context:
                task = asyncio.create_task(context.new_price(response.last_price))

    async def get_last_price(self, instrument_uid: str):
        if self.map_context.get(instrument_uid):
            return await self.map_context[instrument_uid].get()
