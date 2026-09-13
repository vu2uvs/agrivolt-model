"""Command line entry point.

    agrivolt run scenarios/roha-konkan.yaml
    agrivolt run scenarios/roha-konkan.yaml --out out/roha.json
    agrivolt sweep scenarios/roha-konkan.yaml --pitch 4:16:1
    agrivolt crops

The `run` output is the deliverable: one JSON document per scenario, complete
enough that someone can audit the result without reading the code.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from . import crop as crop_model
from . import scenario as scenario_module


def _emit(document: dict, out: Path | None) -> None:
    text = json.dumps(document, indent=2)
    if out is None:
        print(text)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}", file=sys.stderr)


def _parse_range(spec: str) -> list[float]:
    """Parse a `start:stop:step` sweep range, stop inclusive."""
    try:
        start, stop, step = (float(part) for part in spec.split(":"))
    except ValueError:
        raise SystemExit(f"could not parse range {spec!r}; expected start:stop:step")
    if step <= 0:
        raise SystemExit("sweep step must be positive")

    values, current = [], start
    while current <= stop + 1e-9:
        values.append(round(current, 6))
        current += step
    return values


def command_run(args: argparse.Namespace) -> int:
    _emit(scenario_module.run(args.scenario), args.out)
    return 0


def command_sweep(args: argparse.Namespace) -> int:
    """Re-run a scenario across a range of row pitches.

    Pitch is the agrivoltaic design dial: widen it and the crop gets light but
    the parcel carries less capacity. The point of the sweep is that the
    trade-off is not monotonic in money, so the optimum is worth finding rather
    than guessing.
    """
    base = scenario_module.load(args.scenario)
    results = []

    for pitch in _parse_range(args.pitch):
        if pitch < base["array"].collector_width:
            continue
        candidate = replace(base["array"], pitch=pitch)
        document = scenario_module.run(args.scenario, array=candidate)
        results.append(
            {
                "pitch_m": pitch,
                "gcr": document["array"]["gcr"],
                "light_transmission": document["years"][0]["crops"][0]["light_transmission"],
                "annual_kwh": document["across_years"]["annual_kwh"]["mean"],
                "crop_margin_inr": document["across_years"]["crop_margin_inr"]["mean"],
                "land_equivalent_ratio": document["across_years"]["land_equivalent_ratio"]["mean"],
                "npv_inr_crore": document["economics"]["npv_inr_crore"],
                "irr_percent": document["economics"]["irr_percent"],
            }
        )

    if not results:
        raise SystemExit("sweep range produced no valid geometries")

    _emit(
        {
            "scenario": base["name"],
            "swept": "pitch_m",
            "optima": _optima(results),
            "results": results,
        },
        args.out,
    )
    return 0


def _optima(results: list[dict]) -> dict:
    """Best pitch under each objective, with the degenerate cases called out.

    Three objectives, because they disagree and the disagreement is the finding:

      * NPV rewards whatever makes the most money
      * IRR rewards capital efficiency
      * LER rewards land productivity, and is biased towards dense arrays
        because the energy term grows faster than the crop term shrinks

    Two failure modes get flagged rather than quietly reported as answers. An
    optimum sitting on the edge of the swept range means the objective is
    monotonic over that range and the real optimum is outside it. And when every
    NPV is negative, maximising NPV collapses into minimising capacity -- the
    model is saying the project does not work at this tariff, not that a very
    sparse array is a good design.
    """
    ranked = {
        "npv_inr_crore": max(results, key=lambda row: row["npv_inr_crore"]),
        "irr_percent": max(results, key=lambda row: row["irr_percent"] or -999),
        "land_equivalent_ratio": max(
            results, key=lambda row: row["land_equivalent_ratio"] or 0
        ),
    }

    edges = {results[0]["pitch_m"], results[-1]["pitch_m"]}
    warnings = [
        f"The {objective} optimum sits at the edge of the swept range "
        f"({best['pitch_m']} m). Widen the range: the true optimum is outside it."
        for objective, best in ranked.items()
        if best["pitch_m"] in edges
    ]

    if all(row["npv_inr_crore"] < 0 for row in results):
        warnings.append(
            "Every geometry in this range has negative NPV, so maximising NPV "
            "degenerates into minimising installed capacity. Read this as the "
            "project not clearing its hurdle rate at the configured tariff, not "
            "as a recommendation to build a very sparse array."
        )

    return {"by_objective": ranked, "warnings": warnings}


def command_crops(args: argparse.Namespace) -> int:
    for key, crop in sorted(crop_model.load_crops().items()):
        print(
            f"{key:18s} {crop.season:7s} {crop.stages.total:3d} d  "
            f"shade_sensitivity={crop.shade_sensitivity:.2f}  "
            f"ref_yield={crop.reference_yield_t_ha:5.2f} t/ha"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agrivolt",
        description="Agrivoltaic yield, generation and revenue modelling for Maharashtra",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="run one scenario")
    run_parser.add_argument("scenario", type=Path)
    run_parser.add_argument("--out", type=Path, help="write JSON here instead of stdout")
    run_parser.set_defaults(handler=command_run)

    sweep_parser = subparsers.add_parser("sweep", help="sweep row pitch across a range")
    sweep_parser.add_argument("scenario", type=Path)
    sweep_parser.add_argument(
        "--pitch", default="4:16:1", help="start:stop:step in metres, stop inclusive"
    )
    sweep_parser.add_argument("--out", type=Path)
    sweep_parser.set_defaults(handler=command_sweep)

    crops_parser = subparsers.add_parser("crops", help="list the crop library")
    crops_parser.set_defaults(handler=command_crops)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
