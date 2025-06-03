import dataclasses
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from tinkoff import invest as ti
from tinkoff.invest.utils import quotation_to_decimal, decimal_to_quotation

from trading_bot.config.config import Config
from trading_bot.core.base_state import BaseState
from trading_bot.core.base_strategy import BaseStrategy
from trading_bot.core.orders.order_listener import OrderListener
from trading_bot.core.orders.order_manager import OrderEvent, OrderEventType
from trading_bot.core.utils import calc_point_price, create_order_id


@dataclass(repr=True)
class DonchianData:
    breakout_long_20: Decimal
    breakout_short_20: Decimal
    breakout_long_10: Decimal
    breakout_short_10: Decimal
    average_true_range: Decimal


class WaitingBreakoutState(BaseState, OrderListener):

    def __init__(self, context: 'DonchianStrategy'):
        OrderListener.__init__(self)
        self.context: 'DonchianStrategy' = context

        self._params: Optional[ti.PostOrderRequest] = None
        self._order_id: Optional[str] = None

        self._fill_quantity: int = 0
        self._execute_lots: int = 0

    async def new_price(
            self, *,
            price: ti.LastPrice,
            context: 'DonchianStrategy'
    ):
        if self._order_id is not None:
            if new_pr := self._check_replace_order(price=price):
                new_quantity = self._execute_lots - self._fill_quantity
                if new_quantity != 0:
                    new_id = await self.order_manager.replace_order(
                        old_id=self._order_id,
                        new_price=new_pr,
                        new_quantity=new_quantity
                    )
                    self._order_id = new_id
                    self._params = dataclasses.replace(
                        self._params,
                        price=decimal_to_quotation(new_pr),
                        quantity=new_quantity
                    )

        if direction := self._check_breakout(price=price, data=context.data):
            params_order = self._get_params_order(direction=direction, context=context)
            order_id = await self.order_manager.place_order(req=params_order, listener=self)
            if order_id:
                self._order_id = order_id
                self._params = params_order
                self._execute_lots = params_order.quantity

    async def order_handler(self, *, order_event: OrderEvent):
        if order_event.order_id == self._order_id:
            ev_type = order_event.event_type
            if ev_type == OrderEventType.FILLED:
                self._to_position_state()
            elif ev_type == OrderEventType.PARTIAL:
                self._fill_quantity = order_event.filled_qty

    # Не публичные методы __________________________________________________________________

    def _to_position_state(self):
        self.context.state = PositionState(context=self.context)
        self.context.units = 1
        self.context.quantity = self._fill_quantity
        self.context.direction = self._params.direction
        self.context.next_entry_price = self.context.state._calc_next_entry_price()
        self.context.next_stop_loss = self.context.state._calc_next_stop_loss()

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

    def _check_replace_order(self, price: ti.LastPrice) -> Optional[Decimal]:
        pr = quotation_to_decimal(price.price)
        old_pr = quotation_to_decimal(self._params.price)
        direct = self._params.direction

        if (direct == ti.OrderDirection.ORDER_DIRECTION_BUY and
                pr >= old_pr + (self.context.data.average_true_range * Decimal(0.5))):
            return old_pr + (self.context.data.average_true_range * Decimal(0.5))
        elif (direct == ti.OrderDirection.ORDER_DIRECTION_SELL and
              pr <= old_pr - (self.context.data.average_true_range * Decimal(0.5))):
            return old_pr - (self.context.data.average_true_range * Decimal(0.5))


class DonchianStrategy(BaseStrategy):

    def __init__(self, instrument: ti.Future):
        self.data: DonchianData = None
        self.size_portfolio: Decimal = Config().size_portfolio
        self.instrument: ti.Future = instrument
        self.state: BaseState = WaitingBreakoutState(context=self)

        self.quantity: int = 0
        self.units: int = 0
        self.direction: Optional[ti.OrderDirection] = None
        self.next_entry_price: Optional[Decimal] = None
        self.next_stop_loss: Optional[Decimal] = None

    async def new_price(self, price: ti.LastPrice):
        await self.state.new_price(context=self, price=price)
