import argparse
import csv
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .inputs import read_battery, read_periods
from .model import optimise


def main():
    parser = argparse.ArgumentParser(description="Optimise battery dispatch across two markets")
    parser.add_argument("--battery", type=Path, default=Path("data/Attachment 1.xlsx"))
    parser.add_argument("--prices", type=Path, default=Path("data/Attachment 2.xlsx"))
    parser.add_argument("--start", type=datetime.fromisoformat, default=datetime(2018, 1, 1))
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--output", type=Path, default=Path("results"))
    args = parser.parse_args()
    
    try:
        battery = read_battery(args.battery)
        periods = read_periods(args.prices, args.start, args.days)
        dispatch = optimise(battery, periods)
    except (ValueError, KeyError, OSError, RuntimeError) as error:
        parser.exit(1, f"Error: {error}\n")

    args.output.mkdir(parents=True, exist_ok=True)

    with (args.output / "dispatch.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(asdict(dispatch[0])))
        writer.writeheader()
        
        for row in dispatch:
            record = asdict(row)
            record["timestamp"] = row.timestamp.isoformat()
            writer.writerow(record)
    summary = {
        "start": args.start.isoformat(),
        "days": args.days,
        "half_hour_periods": len(dispatch),
        "battery": asdict(battery),
        "initial_stored_mwh": 0.0,
        "final_stored_mwh": dispatch[-1].stored_mwh,
        "trading_profit_gbp": sum(row.profit_gbp for row in dispatch),
        "grid_import_mwh": 0.5 * sum(row.market1_charge_mw + row.market2_charge_mw for row in dispatch),
        "grid_export_mwh": 0.5 * sum(row.market1_discharge_mw + row.market2_discharge_mw for row in dispatch),
        "solver_relative_gap_target": 1e-8,
    }
    
    text = json.dumps(summary, indent=2, allow_nan=False)
    (args.output / "summary.json").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
