import asyncio
import datetime
from idlelib.window import add_windows_to_menu
from typing import Optional, Any

import tinkoff.invest as ti
import tinkoff.invest.constants as ti_const
from tinkoff.invest.async_services import AsyncServices
from tinkoff.invest.market_data_stream.async_market_data_stream_manager import \
    AsyncMarketDataStreamManager
from tinkoff.invest.schemas import OrderIdType

from trading_bot.config.config import Config
from trading_bot.utils.logger import log


class TinkoffClient:

    def __init__(self, token: str, account_id: str = None):
        self._token = token
        self.account_id = account_id
        self._target = ti_const.INVEST_GRPC_API
        self._client: ti.AsyncClient = ti.AsyncClient(self._token, target=self._target)
        self._api: Optional[AsyncServices] = None

    async def start(self):
        self._api = await self._client.__aenter__()

    async def stop(self):
        await self._client.__aexit__(None, None, None)
        self._api = None

    @log
    async def get_futures_by_ticker(self, ticker: str) -> ti.Future:
        resp = await self._api.instruments.futures()
        for fut in resp.instruments:
            if fut.ticker == ticker:
                return fut

    @log
    async def _get_candles(
            self, instrument_id: str,
            from_datetime: datetime.datetime,
            to_datetime: datetime.datetime,
            interval: ti.CandleInterval
    ) -> list[ti.HistoricCandle]:
        async with ti.AsyncClient(self._token, target=self._target) as client:
            candles: ti.GetCandlesResponse = await client.market_data.get_candles(
                instrument_id=instrument_id,
                from_=from_datetime,
                to=to_datetime,
                interval=interval
            )
            return candles.candles

    @log
    async def get_days_candles_last_two_weeks(self, instrument_id: str) -> list[ti.HistoricCandle]:
        candles = await self._get_candles(
            instrument_id=instrument_id,
            from_datetime=datetime.datetime.now() - datetime.timedelta(days=15),
            to_datetime=datetime.datetime.now(),
            interval=ti.CandleInterval.CANDLE_INTERVAL_DAY
        )
        return candles

    @log
    async def post_order(self, order_params: ti.PostOrderRequest):
        order_response: ti.PostOrderResponse = await self._api.orders.post_order(
            quantity=order_params.quantity,
            price=order_params.price,
            instrument_id=order_params.instrument_id,
            direction=order_params.direction,
            account_id=self.account_id,
            order_type=order_params.order_type,
            order_id=order_params.order_id,
            time_in_force=order_params.time_in_force,
            price_type=order_params.price_type
        )
        return order_response

    async def get_status_order(self, order_id: str) -> ti.OrderState:
        status_order: ti.OrderState = await self._api.orders.get_order_state(
            order_id=order_id,
            account_id=self.account_id,
            price_type=ti.PriceType.PRICE_TYPE_POINT,
            order_id_type=OrderIdType.ORDER_ID_TYPE_EXCHANGE
        )
        return status_order

    async def cancel_order(self, order_id: str):
        return await self._api.orders.cancel_order(
            order_id=order_id,
            account_id=self.account_id,
            order_id_type=OrderIdType.ORDER_ID_TYPE_EXCHANGE
        )

    def __repr__(self):
        return f"TinkoffClientSandbox(TOKEN)"


class StreamMarketData:
    subscribe_type = {
        "last_price": ti.LastPriceInstrument,
        "candles": ti.CandleInstrument
    }

    def __init__(self, api: AsyncServices):
        self._api = api
        self._stream: AsyncMarketDataStreamManager = None
        self._subscriptions: dict[str, Any] = {}

        self.request_queue: asyncio.Queue = asyncio.Queue()

    @log
    async def _start_stream(self):
        if not self._stream:
            self._stream = self._api.create_market_data_stream()
            asyncio.create_task(self._listen_stream())

    @log
    def stop_stream(self):
        if self._stream:
            self._stream.stop()

    async def _listen_stream(self):
        if self._stream:
            async for request in self._stream:
                await self.request_queue.put(request)

    async def subscribe_last_price(self, id_list: list[str]):
        await self._start_stream()
        list_last_price = [
            ti.LastPriceInstrument(instrument_id=instr_id) for instr_id in id_list
        ]

        for instr in list_last_price:
            self._subscriptions[instr.instrument_id] = instr

        self._stream.last_price.subscribe(instruments=list_last_price)

    async def subscribe_candles(self, list_instrument_id: list[str], interval: ti.CandleInterval):
        await self._start_stream()
        list_candle_instrument = [
            ti.CandleInstrument(
                instrument_id=instr_id,
                interval=interval,
            ) for instr_id in list_instrument_id
        ]

        for instr in list_candle_instrument:
            self._subscriptions[instr.instrument_id] = instr

        self._stream.candles.subscribe(instruments=list_candle_instrument)


if __name__ == '__main__':
    async def worker(stream: StreamMarketData):
        while True:
            req = await stream.request_queue.get()
            print(req)


    async def main():
        token = Config().TOKEN
        client = TinkoffClient(token)
        await client.start()
        futures = await client.get_futures_by_ticker("NRK5")
        candles = await client.get_days_candles_last_two_weeks(
            instrument_id=futures.uid
        )
        new_stream = StreamMarketData(client._api)
        await new_stream.subscribe_last_price(id_list=[futures.uid])
        await worker(new_stream)


    asyncio.run(main())
