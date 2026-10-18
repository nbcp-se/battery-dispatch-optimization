# Battery dispatch

## Approach

I treated the battery as a store of energy: buying adds energy, selling removes it, and both operations lose 5% as described in Attachment 1. I used SciPy's mixed-integer optimiser to choose the amounts bought and sold in each market, maximising sales income minus purchase costs. The model works in half-hour steps, keeps Market 2 comitments unchanged across both halves of each hour, shares the battery limits across the markets, and uses a binary charging/discharging choice to prevent doing both at once. I limited the default run to the first week to keep the exercise small, with an empty battery at both ends and all prices known in advance. Reading the spreadsheets, solving the problem, and writing results are separate so each can be checked independently.

## Setup and run

Requires Python 3.11 or later. Run these commands from the project directory.
The original spreadsheets are included in `data/`.

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[test]"
.venv\Scripts\battery-dispatch.exe
.venv\Scripts\python.exe -m pytest -q
```

Bash:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/battery-dispatch
.venv/bin/python -m pytest -q
```

To select another period or output folder (Windows example):

```powershell
.venv\Scripts\battery-dispatch.exe --start 2018-01-08 --days 7 --output results/second-week
```

`--battery` and `--prices` accept alternative paths to the supplied spreadsheet layouts.
The start is inclusive and the end is exclusive. Runs must cover whole days starting
on a whole hour. The solver stops after 120 seconds and reports an error if it cannot
complete the optimisation; it does not export a partial solution.

## Results

The default run covers 1 January 2018 through 7 January 2018: 336 half-hour periods.
The included `results/summary.json` reports **GBP 1,239.64 trading profit**, with
91.077562 MWh imported, 82.197500 MWh exported, and zero energy remaining.
`results/dispatch.csv` contains prices, charge/discharge power for each market,
stored energy at the end of each interval, and that interval's profit. Running the
default command regenerates both files. Equivalent schedules can have the same
profit; compare totals within a penny rather than expecting identical CSV rows.

## Assumptions and checks

- Power is measured at the grid in MW; half an hour at 2 MW moves 1 MWh.
  Stored energy increases by `imports * 0.95` and decreases by `exports / 0.95`.
  Market 2 appears twice in the CSV, with half its hourly cash flow on each row.
- The battery starts and ends empty. Prices are taken as given and known in advance,
  so the result is a hindsight optimum for the selected period, not a forecast.
- Capacity remains at 4 MWh. Lifetime, degradation, capex and fixed annual costs
  are excluded; the output measures trading profit, not investment return.
- Timestamps are used without a timezone. Offsets of at most one second are rounded
  to the market interval to handle the supplied Excel timestamp drift. Missing
  prices, missing intervals and duplicate timestamps in the selected period fail
  explicitly. For example, the supplied half-hourly sheet repeats 02:00 and 02:30
  on 25 March 2018; periods coOkntaining these records are not supported.
- Tests cover known profits, losses, negative prices, shared power/storage limits,
  hourly commitments, prohibited simultaneous charging/discharging, input validation,
  and the supplied data. The optimiser uses a relative optimality gap of `1e-8`.

Solver API reference: [SciPy `milp`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html).
