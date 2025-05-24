import asyncio
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from tinkoff import invest as ti
from tinkoff.invest.utils import quotation_to_decimal, decimal_to_quotation

from trading_bot.core.base_state import BaseState
from trading_bot.core.base_strategy import BaseStrategy
from trading_bot.core.orders.order_listener import OrderListener
from trading_bot.core.orders.order_manager import OrderManager
from trading_bot.core.utils import calc_point_price, create_order_id
from trading_bot.tinkoff_client.client import TinkoffClient


@dataclass(repr=True)
class DonchianData:
    breakout_long_20: Decimal
    breakout_short_20: Decimal
    breakout_long_10: Decimal
    breakout_short_10: Decimal
    average_true_range: Decimal


class WaitingBreakoutState(BaseState, OrderListener):

    async def new_price(
            self, *,
            price: ti.LastPrice,
            context: 'DonchianStrategy',
            client: TinkoffClient
    ):
        if self.order_manager is not None:
            price = quotation_to_decimal(price.price)
            await self.order_manager.new_price(price=price, func=self.replace_order)
            return
        if direction := self._check_breakout(price, self.context.data):
            params_order = self._get_params_order(direction, self.context)
            order: ti.Order = await client.post_order(params_order)
            self.order_manager = OrderManager(order, self)
            asyncio.create_task(self.order_manager.start())

    async def order_handler(self, *, orders: list[ti.OrderState]):
        pass

    @staticmethod
    def _check_breakout(
            price: ti.LastPrice,
            data: DonchianData
    ) -> Optional[ti.OrderDirection]:
        price = quotation_to_decimal(price.price)
        if price > data.breakout_long_20 + data.average_true_range / Decimal(2):
            return ti.OrderDirection.ORDER_DIRECTION_BUY
        elif price < data.breakout_short_20 - data.average_true_range / Decimal(2):
            return ti.OrderDirection.ORDER_DIRECTION_SELL

    def _get_params_order(
            self,
            direction: ti.OrderDirection,
            context: 'DonchianStrategy'
    ) -> ti.PostOrderRequest:
        order_params = ti.PostOrderRequest(
            instrument_id=context.instrument.uid,
            quantity=self._calc_quantity(context),
            direction=direction,
            order_id=create_order_id(),
            time_in_force=ti.TimeInForceType.TIME_IN_FORCE_DAY,
            price_type=ti.PriceType.PRICE_TYPE_POINT,
            order_type=ti.OrderType.ORDER_TYPE_LIMIT,
            price=self._calc_price(direction, context)
        )
        return order_params

    @staticmethod
    def _calc_quantity(context: 'DonchianStrategy') -> int:
        size_portfolio = context.size_portfolio
        atr = context.data.average_true_range
        price_per_point = calc_point_price(context.instrument)
        quantity = math.floor(Decimal(0.01) * size_portfolio / atr * price_per_point)
        return quantity

    @staticmethod
    def _calc_price(direction: ti.OrderDirection, context: 'DonchianStrategy') -> Decimal:
        min_price_increment = quotation_to_decimal(context.instrument.min_price_increment)
        if direction == ti.OrderDirection.ORDER_DIRECTION_BUY:
            return context.data.breakout_long_20 + min_price_increment
        elif direction == ti.OrderDirection.ORDER_DIRECTION_SELL:
            return context.data.breakout_short_20 - min_price_increment

    def replace_order(self, price: Decimal, order: ti.PostOrderResponse):
        pass


class DonchianStrategy(BaseStrategy):

    def __init__(self, instrument: ti.Future, size_portfolio: Decimal, client: TinkoffClient):
        self.data: DonchianData = None
        self.size_portfolio: Decimal = size_portfolio  # TODO: показывает от какой цены мы торгуемся.
        self.instrument: ti.Future = instrument
        self.state: BaseState = WaitingBreakoutState(context=self)
        self.account_id: str = client.account_id

        self.quantity: int = 0
        self.units: int = 0
        self.direction: Optional[ti.OrderDirection] = None
        self.next_entry_price: Optional[Decimal] = None
        self.next_stop_loss: Optional[Decimal] = None

        self.client = client

    async def new_price(self, price: ti.LastPrice):
        await self.state.new_price(context=self, price=price)

    async def order_handler(self, order: ti.Order):
        await self.state.order_handler(context=self, order=order)
