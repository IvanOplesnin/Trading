import uuid
from decimal import Decimal

import tinkoff.invest
from tinkoff.invest.utils import quotation_to_decimal


def calc_point_price(instrument: tinkoff.invest.Future):
    min_price_increment = quotation_to_decimal(instrument.min_price_increment)
    min_price_increment_amount = quotation_to_decimal(instrument.min_price_increment_amount)

    return (Decimal(1) / min_price_increment) * min_price_increment_amount


def create_order_id() -> str:
    return str(uuid.uuid4())
