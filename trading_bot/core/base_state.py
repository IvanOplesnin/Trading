from abc import ABC, abstractmethod

import tinkoff.invest as ti

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trading_bot.core.order_manager import OrderManager
    from trading_bot.tinkoff_client.client import TinkoffClient


class BaseState(ABC):
    def __init__(self, *, context):
        self.context = context
        self.order_manager: 'OrderManager' = None

    @abstractmethod
    async def new_price(self, *, price: ti.LastPrice, context, client: 'TinkoffClient'):
        pass

    @abstractmethod
    async def order_handler(self, *, orders: list[ti.OrderState]):
        pass
