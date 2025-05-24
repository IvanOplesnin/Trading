from abc import ABC, abstractmethod

import tinkoff.invest as ti


class BaseStrategy(ABC):

    @abstractmethod
    async def new_price(self, price: ti.LastPrice):
        pass
