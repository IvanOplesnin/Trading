from abc import ABC, abstractmethod

import tinkoff.invest as ti

from trading_bot.core.orders.order_manager import OrderManager


class OrderListener(ABC):
    def __init__(self):
        self._order_manager: OrderManager = None

    @abstractmethod
    async def on_order(self, order: ti.PostOrderResponse):
        pass
