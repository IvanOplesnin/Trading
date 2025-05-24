from abc import ABC, abstractmethod

import tinkoff.invest as ti


class OrderListener(ABC):
    @abstractmethod
    async def on_order(self, order: ti.PostOrderResponse):
        pass
