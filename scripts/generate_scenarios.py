#!/usr/bin/env python3
"""Materialize the synthetic scenario catalog as XML fixtures."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scenario_suite import (  # noqa: E402
    ALTERYX_SCENARIOS,
    TABLEAU_SCENARIOS,
    write_alteryx_scenario,
    write_tableau_scenario,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic Tableau and Alteryx scenario fixtures.")
    parser.add_argument("--output", type=Path, default=Path("generated_scenarios"))
    args = parser.parse_args()

    tableau_dir = args.output / "tableau"
    alteryx_dir = args.output / "alteryx"
    for scenario in TABLEAU_SCENARIOS:
        write_tableau_scenario(scenario, tableau_dir / f"{scenario.scenario_id.lower()}_{_slug(scenario.name)}.twb")
    for scenario in ALTERYX_SCENARIOS:
        write_alteryx_scenario(scenario, alteryx_dir / f"{scenario.scenario_id.lower()}_{_slug(scenario.name)}.yxmd")

    print(f"Generated {len(TABLEAU_SCENARIOS)} Tableau scenarios in {tableau_dir}")
    print(f"Generated {len(ALTERYX_SCENARIOS)} Alteryx scenarios in {alteryx_dir}")
    return 0


def _slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")


if __name__ == "__main__":
    raise SystemExit(main())
