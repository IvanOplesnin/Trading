import tinkoff.invest as ti
import tinkoff.invest.constants as ti_const

from .client import (TinkoffClient)


class TinkoffClientSandbox(TinkoffClient):

    def __init__(self, token: str, account_id: str):
        super().__init__(token, account_id)
        self._target = ti_const.INVEST_GRPC_API_SANDBOX
        self._client: ti.AsyncClient = ti.AsyncClient(self._token, target=self._target)
