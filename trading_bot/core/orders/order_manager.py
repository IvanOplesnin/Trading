import asyncio
import dataclasses
import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

import tinkoff.invest as ti
from grpc.aio import AioRpcError
from tinkoff.invest.utils import quotation_to_decimal, decimal_to_quotation

from trading_bot.core.orders.order_listener import OrderListener
from trading_bot.tinkoff_client.client import TinkoffClient


class OrderEventType(Enum):
    UNKNOWN = 0,
    FILLED = 1,
    PARTIAL = 2,
    CANCELED = 3,
    REJECTED = 4,
    NEW = 5


@dataclass
class OrderEvent:
    order_id: str
    event_type: OrderEventType
    filled_qty: int
    avg_price: Decimal


class ReplaceLock:
    def __init__(self):
        self._replace_lock: dict[str, asyncio.Lock] = {}

    def get_lock(self, order_id: str):
        return self._replace_lock.setdefault(order_id, asyncio.Lock())

    def release(self, order_id: str):
        if order_id in self._replace_lock:
            self._replace_lock.pop(order_id)


class OrderManager:

    def __init__(self, client: TinkoffClient):
        self._client = client
        self._replace_lock = ReplaceLock()

        self._listeners: dict[str, OrderListener] = {}
        self._poll_tasks = {}

        self._meta_request: dict[str, ti.PostOrderRequest] = {}

    async def place_order(
            self, req: ti.PostOrderRequest,
            listener: OrderListener
    ) -> str:
        resp: ti.PostOrderResponse = await self._client.post_order(req)
        order_id = resp.order_id
        self._listeners[order_id] = listener
        new_task = asyncio.create_task(self._watch_order(order_id))
        self._poll_tasks[order_id] = new_task
        new_task.add_done_callback(lambda _: self._poll_tasks.pop(order_id, None))
        self._meta_request[order_id] = req
        return order_id

    async def replace_order(
            self,
            old_id: str,
            new_price: Decimal,
            new_quantity: int
    ):
        new_id = None
        old_req = self._meta_request.get(old_id)
        if not old_req:
            raise ValueError("Unknown order id")
        lock = self._replace_lock.get_lock(old_id)
        try:
            s = await self._client.get_status_order(old_id)
            if (s.execution_report_status
                    == ti.OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_FILL):
                return
            async with (lock):
                watcher: asyncio.Task = self._poll_tasks.pop(old_id, None)
                cancel_res = await self._client.cancel_order(old_id)

                if cancel_res:
                    new_req = dataclasses.replace(
                        old_req,
                        quantity=new_quantity,
                        price=decimal_to_quotation(new_price),
                        order_id=str(uuid.uuid4())
                    )
                    listener = self._listeners.get(old_id)
                    new_id = await self.place_order(new_req, listener)
                    self._listeners.pop(old_id, None)
                    self._meta_request.pop(old_id, None)
        except AioRpcError:
            if watcher:
                self._poll_tasks[old_id] = watcher
            raise

        finally:
            self._replace_lock.release(old_id)

        if new_id is None:
            raise RuntimeError("replace_order finished without new_id")
        return new_id

    async def cancel_all(self):
        for task in self._poll_tasks.values():
            task.cancel()

        self._poll_tasks.clear()

    async def cancel_order(self, order_id: str):
        try:
            await self._client.cancel_order(order_id)
        except AioRpcError:
            raise
        self._listeners.pop(order_id, None)
        self._poll_tasks.pop(order_id, None)

    # Не публичные методы _______________________________________________________________________
    async def _watch_order(self, order_id: str, delay: float = 4.0):
        try:
            while True:
                state = await self._client.get_status_order(order_id)
                event = self._translate_state(state)
                if event:
                    await self._broadcast(event)
                    if event.event_type in {
                        OrderEventType.FILLED,
                        OrderEventType.CANCELED,
                        OrderEventType.REJECTED
                    }:
                        break
                await asyncio.sleep(delay)
        finally:
            self._listeners.pop(order_id, None)
            self._poll_tasks.pop(order_id, None)

    async def _broadcast(self, event: OrderEvent):
        listener = self._listeners.get(event.order_id)
        await listener.on_order(event)

    @staticmethod
    def _translate_state(state: ti.OrderState) -> OrderEvent | None:
        m = {
            ti.OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_PARTIALLYFILL:
                OrderEventType.PARTIAL,
            ti.OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_FILL:
                OrderEventType.FILLED,
            ti.OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_CANCELLED:
                OrderEventType.CANCELED,
            ti.OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_REJECTED:
                OrderEventType.REJECTED
        }
        ev_type = m.get(state.execution_report_status, OrderEventType.UNKNOWN)
        if not ev_type:
            return None

        return OrderEvent(
            order_id=state.order_id,
            event_type=ev_type,
            filled_qty=state.lots_executed,
            avg_price=quotation_to_decimal(state.average_position_price)
        )
