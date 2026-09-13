"""Distil scenario output into the compact summary the website renders.

This is the seam between the model repo and avigreen.in. The site does not read
the full scenario documents -- they are large and mostly of interest to someone
auditing a result -- it reads one small artefact produced here.

Keeping it as a committed script rather than an ad-hoc snippet matters for the
obvious reason: the numbers on a public page should be traceable to a command
anyone can re-run, not to something typed once into a shell.

    python scripts/export_web_summary.py out/ ../avigreen/src/data/model-results.json

Round two puts this behind a scheduled GitHub Action so the site's figures
refresh whenever the model or its inputs change.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Scenario documents that are sweeps rather than single runs.
SKIP_SUFFIXES = ("-sweep.json",)


def summarise_crop(crop: dict) -> dict:
    """Three yields that are easy to conflate, so all three are named.

    `under_array` is what grows beneath the modules. `open_field` is the same
    crop grown in the open -- the comparator for any claim about shade.
    `baseline` is what the land actually produces today, which is zero for a
    crop the array makes newly possible. Reporting a shade claim against the
    baseline instead of the open field overstates it enormously.
    """
    return {
        "crop": crop["crop"],
        "season": crop["season"],
        "transmission": crop["light_transmission"],
        "yield_t_ha": crop["under_array"]["yield_t_ha"],
        "open_field_t_ha": crop["open_field"]["yield_t_ha"],
        "baseline_t_ha": crop["baseline_yield_t_ha"],
        "grown_today": crop["grown_in_baseline"],
        "water_saved_mm": crop["water"]["demand_reduction_mm"],
        "heat_factor_open": crop["open_field"]["factors"]["heat"],
        "heat_factor_under": crop["under_array"]["factors"]["heat"],
        "transpiration_open": crop["water"]["open_field"]["relative_transpiration"],
        "transpiration_under": crop["water"]["under_array"]["relative_transpiration"],
    }


def summarise_scenario(document: dict) -> dict:
    first_year = document["years"][0]
    spread = document["across_years"]
    economics = document["economics"]

    return {
        "scenario": document["scenario"],
        "name": document["site"]["name"],
        "district": document["site"]["district"],
        "zone": document["site"]["agroclimatic_zone"],
        "lat": document["site"]["latitude"],
        "lon": document["site"]["longitude"],
        "area_ha": document["site"]["area_ha"],
        "dc_capacity_kw": document["array"]["dc_capacity_kw"],
        "gcr": document["array"]["gcr"],
        "ler": spread["land_equivalent_ratio"]["mean"],
        "annual_gwh": round(spread["annual_kwh"]["mean"] / 1e6, 3),
        "specific_yield": first_year["energy"]["specific_yield_kwh_per_kwp"],
        "bifacial_gain_percent": first_year["energy"]["bifacial_gain_percent"],
        "crop_margin_inr": round(spread["crop_margin_inr"]["mean"]),
        "food_change_percent": first_year["system_comparison"]["food_change_percent"],
        "breakeven_tariff": economics["breakeven_tariff_inr_per_kwh"],
        "tariff_gap": economics["tariff_gap_inr_per_kwh"],
        "irr_percent": economics["irr_percent"],
        "crops": [summarise_crop(crop) for crop in first_year["crops"]],
    }


def build(results_dir: Path) -> dict:
    documents = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(results_dir.glob("*.json"))
        if not path.name.endswith(SKIP_SUFFIXES)
    ]
    if not documents:
        raise SystemExit(f"no scenario output found in {results_dir}")

    sites = [summarise_scenario(document) for document in documents]
    breakeven = [site["breakeven_tariff"] for site in sites]
    ratios = [site["ler"] for site in sites if site["ler"] is not None]

    tariff = documents[0]["economics"]["breakeven_tariff_inr_per_kwh"] - documents[0][
        "economics"
    ]["tariff_gap_inr_per_kwh"]

    return {
        "generated_at": max(document["generated_at"] for document in documents),
        "provenance": documents[0]["provenance"],
        "headline": {
            "mskvy_tariff": round(tariff, 3),
            "breakeven_min": min(breakeven),
            "breakeven_max": max(breakeven),
            "gap_min": round(min(breakeven) - tariff, 3),
            "gap_max": round(max(breakeven) - tariff, 3),
            "ler_min": min(ratios),
            "ler_max": max(ratios),
            "sites": len(sites),
            "weather_years": "-".join(str(y) for y in documents[0]["weather_years"]),
        },
        "sites": sites,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results_dir", type=Path, help="directory of scenario JSON")
    parser.add_argument("destination", type=Path, help="summary file to write")
    args = parser.parse_args(argv)

    summary = build(args.results_dir)
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(
        f"{len(summary['sites'])} scenarios -> {args.destination}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
