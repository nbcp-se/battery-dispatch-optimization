from datetime import datetime, timedelta

import pytest

from battery_dispatch import Battery, Period, optimise


def periods(market1, market2):
    start = datetime(2018, 1, 1)
    return [Period(start + timedelta(minutes=30 * period_index), price, market2[period_index // 2])
            for period_index, price in enumerate(market1)]


def check_dispatch(battery, rows):
    stored = 0
    for period_index, row in enumerate(rows):
        charge = row.market1_charge_mw + row.market2_charge_mw
        discharge = row.market1_discharge_mw + row.market2_discharge_mw
        assert -1e-7 <= charge <= battery.charge_mw + 1e-7
        assert -1e-7 <= discharge <= battery.discharge_mw + 1e-7
        assert charge < 1e-7 or discharge < 1e-7
        stored += 0.5 * (charge * (1 - battery.charge_loss)
                         - discharge / (1 - battery.discharge_loss))
        assert row.stored_mwh == pytest.approx(stored, abs=1e-7)
        assert -1e-7 <= stored <= battery.capacity_mwh + 1e-7
        assert row.profit_gbp == pytest.approx(0.5 * (
            (row.market1_discharge_mw - row.market1_charge_mw) * row.market1_price
            + (row.market2_discharge_mw - row.market2_charge_mw) * row.market2_price
        ))
        if period_index % 2:
            assert row.market2_charge_mw == pytest.approx(rows[period_index - 1].market2_charge_mw)
            assert row.market2_discharge_mw == pytest.approx(rows[period_index - 1].market2_discharge_mw)
    assert stored == pytest.approx(0, abs=1e-7)


@pytest.mark.parametrize("market1,market2,expected", [
    ([10, 10, 100, 100], [10, 100], 90),
    ([10, 10, 20, 20], [20, 100], 90),  # Buy in Market 1, sell in Market 2.
    ([50, 50, 50, 50], [50, 50], 0),
    ([-20, -20, 10, 10], [-20, 10], 30),
    ([0, 0], [100], 0),  # Cannot buy in one market and sell in the other at once.
    ([0, 100], [60], 100),  # Hourly discharge cannot start halfway through the hour.
])
def test_known_profits(market1, market2, expected):
    battery = Battery(2, 2, 1, 0, 0)
    rows = optimise(battery, periods(market1, market2))
    assert sum(row.profit_gbp for row in rows) == pytest.approx(expected)
    check_dispatch(battery, rows)


def test_losses_use_imports_and_exports_at_the_grid():
    battery = Battery(2, 2, 4, 0.05, 0.05)
    rows = optimise(battery, periods([10, 10, 100, 100], [10, 100]))
    # Import 2 MWh, store 1.9 MWh, export 1.805 MWh.
    assert sum(row.profit_gbp for row in rows) == pytest.approx(160.5)
    check_dispatch(battery, rows)


def test_negative_prices_do_not_allow_simultaneous_charging_and_discharging():
    battery = Battery(2, 2, 4, 0.05, 0.05)
    rows = optimise(battery, periods([-100] * 4, [-100] * 2))
    check_dispatch(battery, rows)
    assert sum(row.profit_gbp for row in rows) == pytest.approx(19.5)


@pytest.mark.parametrize("prices", [[], periods([1], [1]),
    [Period(datetime(2018, 1, 1), 1, 1), Period(datetime(2018, 1, 1, 1), 1, 1)],
    periods([float('nan'), 1], [1]),
    [Period(datetime(2018, 1, 1), 1, 1), Period(datetime(2018, 1, 1, 0, 30), 1, 2)]])
def test_invalid_periods(prices):
    with pytest.raises(ValueError):
        optimise(Battery(2, 2, 4, 0.05, 0.05), prices)


@pytest.mark.parametrize("values", [(0, 2, 4, 0, 0), (2, -2, 4, 0, 0),
    (2, 2, float('inf'), 0, 0), (2, 2, 4, -0.1, 0), (2, 2, 4, 0, 1)])
def test_invalid_battery(values):
    with pytest.raises(ValueError):
        Battery(*values)
