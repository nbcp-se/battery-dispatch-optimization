from datetime import datetime, timedelta
from pathlib import Path

import pytest

from battery_dispatch.inputs import _read_market, read_battery, read_periods
from battery_dispatch import optimise
from test_model import check_dispatch


class Sheet:
    title = "Test market"

    def __init__(self, rows):
        self.rows = rows

    def iter_rows(self, **kwargs):
        return iter(self.rows)


def test_excel_timestamp_drift_and_empty_rows():
    hour = datetime(2020, 12, 31, 23)
    result = _read_market(Sheet([(hour - timedelta(milliseconds=6), 10), (None, None)]), 60)
    assert result == {hour: 10}


@pytest.mark.parametrize("rows", [
    [(datetime(2018, 1, 1), None)],
    [(datetime(2018, 1, 1), float('nan'))],
    [(datetime(2018, 1, 1, 0, 5), 10)],
    [(datetime(2018, 1, 1), 10), (datetime(2018, 1, 1), 20)],
])
def test_invalid_market_data(rows):
    with pytest.raises(ValueError):
        _read_market(Sheet(rows), 60)


DATA_DIRECTORY = Path(__file__).resolve().parents[1] / "data"


def test_supplied_week():
    battery = read_battery(DATA_DIRECTORY / "Attachment 1.xlsx")
    prices = read_periods(DATA_DIRECTORY / "Attachment 2.xlsx", datetime(2018, 1, 1), 7)
    assert battery.charge_loss == 0.05
    assert battery.capacity_mwh == 4
    assert len(prices) == 336
    assert prices[0].market1_price == 48.47
    assert prices[0].market2_price == prices[1].market2_price == 51.89
    rows = optimise(battery, prices)
    check_dispatch(battery, rows)
    assert sum(row.profit_gbp for row in rows) > 0


def test_missing_requested_period_is_rejected():
    with pytest.raises(ValueError, match="Missing market data"):
        read_periods(DATA_DIRECTORY / "Attachment 2.xlsx", datetime(2021, 1, 1), 1)


def test_last_day_with_timestamp_drift():
    prices = read_periods(DATA_DIRECTORY / "Attachment 2.xlsx", datetime(2020, 12, 31), 1)
    assert len(prices) == 48
    assert prices[-1].market2_price == pytest.approx(66.235)


def test_supplied_duplicate_timestamps_are_not_silently_resolved():
    with pytest.raises(ValueError, match="Duplicate timestamp"):
        read_periods(DATA_DIRECTORY / "Attachment 2.xlsx", datetime(2018, 3, 25), 1)
