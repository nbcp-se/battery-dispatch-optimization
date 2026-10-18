from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix


@dataclass(frozen=True)
class Battery:
    charge_mw: float
    discharge_mw: float
    capacity_mwh: float
    charge_loss: float
    discharge_loss: float

    def __post_init__(self):
        for value in (self.charge_mw, self.discharge_mw, self.capacity_mwh):
            if not isfinite(value) or value <= 0:
                raise ValueError("Battery power and capacity must be finite and positive")

        for loss in (self.charge_loss, self.discharge_loss):
            if not isfinite(loss) or not 0 <= loss < 1:
                raise ValueError("Battery losses must be between 0 (inclusive) and 1")


@dataclass(frozen=True)
class Period:
    timestamp: datetime
    market1_price: float
    market2_price: float


@dataclass(frozen=True)
class Dispatch:
    timestamp: datetime
    market1_price: float
    market2_price: float
    market1_charge_mw: float
    market1_discharge_mw: float
    market2_charge_mw: float
    market2_discharge_mw: float
    stored_mwh: float
    profit_gbp: float


def optimise(battery: Battery, periods: list[Period]) -> list[Dispatch]:
    """Maximise trading profit, starting and ending with an empty battery."""

    if not periods or len(periods) % 2:
        raise ValueError("Provide a non-empty sequence of complete hours")

    start = periods[0].timestamp

    if start.tzinfo is not None or (start.minute, start.second, start.microsecond) != (0, 0, 0):
        raise ValueError("The first period must start on a naive whole hour")
    
    for period_index, period in enumerate(periods):
        if period.timestamp != start + timedelta(minutes=30 * period_index):
            raise ValueError("Periods must be consecutive half hours")

        if not all(isfinite(price) for price in (period.market1_price, period.market2_price)):
            raise ValueError("Market prices must be finite")

        if period_index % 2 and period.market2_price != periods[period_index - 1].market2_price:
            raise ValueError("Market 2 must have one price per hour")

    # Each period has six variables: charg/discharge per market, stored
    # energy at the end., and a binary switch (1 = charging, 0 = discharging)
    period_count = len(periods)
    (
        market1_charge_column,
        market1_discharge_column,
        market2_charge_column,
        market2_discharge_column,
        stored_energy_column,
        charging_mode_column,
    ) = range(6)
    objective = np.zeros((period_count, 6))
    variable_upper_bounds = np.tile(
        [battery.charge_mw, battery.discharge_mw,
         battery.charge_mw, battery.discharge_mw, battery.capacity_mwh, 1],
        (period_count, 1),
    )
    variable_upper_bounds[-1, stored_energy_column] = 0
    integrality = np.zeros((period_count, 6))
    integrality[:, charging_mode_column] = 1

    # Three constraints per half hour and two per hour for Market 2
    constraint_matrix = lil_matrix((4 * period_count, 6 * period_count))
    constraint_lower_bounds = np.full(4 * period_count, -np.inf)
    constraint_upper_bounds = np.zeros(4 * period_count)
    constraint_index = 0

    for period_index, period in enumerate(periods):
        period_offset = 6 * period_index
        objective[period_index, :4] = 0.5 * np.array([
            period.market1_price, -period.market1_price,
            period.market2_price, -period.market2_price,
        ])
        
        # Stored energy = previous energy + imports after losses - withdrawals
        constraint_matrix[constraint_index, period_offset + stored_energy_column] = 1

        if period_index:
            constraint_matrix[constraint_index, period_offset - 6 + stored_energy_column] = -1

        for column in (market1_charge_column, market2_charge_column):
            constraint_matrix[constraint_index, period_offset + column] = -0.5 * (1 - battery.charge_loss)

        for column in (market1_discharge_column, market2_discharge_column):
            constraint_matrix[constraint_index, period_offset + column] = 0.5 / (1 - battery.discharge_loss)

        constraint_lower_bounds[constraint_index] = 0
        constraint_index += 1

        # The markets share the power limits and the charging direction
        constraint_matrix[constraint_index, period_offset + market1_charge_column] = 1
        constraint_matrix[constraint_index, period_offset + market2_charge_column] = 1
        constraint_matrix[constraint_index, period_offset + charging_mode_column] = -battery.charge_mw
        constraint_index += 1
        constraint_matrix[constraint_index, period_offset + market1_discharge_column] = 1
        constraint_matrix[constraint_index, period_offset + market2_discharge_column] = 1
        constraint_matrix[constraint_index, period_offset + charging_mode_column] = battery.discharge_mw
        constraint_upper_bounds[constraint_index] = battery.discharge_mw
        constraint_index += 1

        if period_index % 2:
            for column in (market2_charge_column, market2_discharge_column):
                constraint_matrix[constraint_index, period_offset + column] = 1
                constraint_matrix[constraint_index, period_offset - 6 + column] = -1
                constraint_lower_bounds[constraint_index] = 0
                constraint_index += 1

    solution = milp(
        objective.ravel(),
        integrality=integrality.ravel(),
        bounds=Bounds(np.zeros(6 * period_count), variable_upper_bounds.ravel()),
        constraints=LinearConstraint(
            constraint_matrix.tocsc(), constraint_lower_bounds, constraint_upper_bounds
        ),
        options={"time_limit": 120, "mip_rel_gap": 1e-8},
    )

    if not solution.success:
        raise RuntimeError(f"Optimisation did not finish: {solution.message}")

    dispatch_rows = []
    
    for period, values in zip(periods, solution.x.reshape(period_count, 6)):
        (
            market1_charge_mw,
            market1_discharge_mw,
            market2_charge_mw,
            market2_discharge_mw,
            stored_mwh,
            _charging_mode,
        ) = values
        profit_gbp = 0.5 * (
            (market1_discharge_mw - market1_charge_mw) * period.market1_price
            + (market2_discharge_mw - market2_charge_mw) * period.market2_price
        )
        dispatch_rows.append(Dispatch(
            timestamp=period.timestamp,
            market1_price=period.market1_price,
            market2_price=period.market2_price,
            market1_charge_mw=float(market1_charge_mw),
            market1_discharge_mw=float(market1_discharge_mw),
            market2_charge_mw=float(market2_charge_mw),
            market2_discharge_mw=float(market2_discharge_mw),
            stored_mwh=float(stored_mwh),
            profit_gbp=float(profit_gbp),
        ))
        
    return dispatch_rows
