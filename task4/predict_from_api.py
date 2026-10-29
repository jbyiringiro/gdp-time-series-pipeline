"""
Task 4 - Prediction script

  1. Fetches a country's yearly records from the Task 3 API (SQL or MongoDB)
  2. Preprocesses them with the same pipeline as Task 1 (preprocessing.py)
  3. Loads the trained model saved by train_model.py
  4. Estimates GDP for the latest year (or --year) and compares it with the
     actual value, when the API has one, and with the naive baseline

Usage (with the Task 3 API running):
    python task4/predict_from_api.py                       # MongoDB, all years, latest year
    python task4/predict_from_api.py --db sql --start_date 2010-01-01 --end_date 2021-12-31
"""

import argparse
import json
import os
import sys
from pathlib import Path

import joblib
import pandas as pd
import requests
from dotenv import load_dotenv

from preprocessing import INPUT_COLUMNS, MA_WINDOW, TARGET, add_features, clean_records

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")  # API_URL, if set (copy .env.example to .env)
DEFAULT_ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"


def fetch_time_series(api_url: str, country: str, start_date: str | None, end_date: str | None) -> pd.DataFrame:
    """Call the Task 3 API and return its records as a DataFrame."""
    params = {"country": country}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date

    try:
        response = requests.get(api_url, params=params, timeout=30)
    except requests.RequestException as err:
        raise RuntimeError(
            f"Could not reach the API at {api_url}. Is it running? "
            f"(uvicorn task3.api_demo:app --port 8000, or set API_URL in .env)\n  {err}"
        ) from err

    if not response.ok:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(f"API returned HTTP {response.status_code}: {detail}")

    payload = response.json()
    if isinstance(payload, dict) and "data" in payload:
        payload = payload["data"]
    if isinstance(payload, dict):  # the /latest endpoint returns a single record
        payload = [payload]

    records = pd.DataFrame(payload)
    if records.empty:
        raise ValueError("No records returned from API.")
    return records


def load_artifacts(artifacts_dir: Path):
    """Load the trained model, its feature order and its training summary."""
    model_path = artifacts_dir / "model.joblib"
    if not model_path.exists():
        raise FileNotFoundError(f"{model_path} not found. Run: python task4/train_model.py")

    model = joblib.load(model_path)
    with open(artifacts_dir / "feature_order.json", "r", encoding="utf-8") as feature_file:
        feature_order = json.load(feature_file)["feature_order"]

    summary_path = artifacts_dir / "training_summary.json"
    summary = {}
    if summary_path.exists():
        with open(summary_path, "r", encoding="utf-8") as summary_file:
            summary = json.load(summary_file)

    # Guard against a model and config saved by different training runs
    model_features = list(getattr(model, "feature_names_in_", feature_order))
    if model_features != feature_order:
        raise ValueError("model.joblib and feature_order.json do not match. Re-run train_model.py.")
    return model, feature_order, summary


def inputs_filled_for(records: pd.DataFrame, year: int) -> list[str]:
    """Inputs the API did not provide for `year`, so preprocessing had to fill them."""
    if "Year" in records.columns:
        record_years = pd.to_numeric(records["Year"], errors="coerce")
    else:
        record_years = pd.to_datetime(records["Date"], errors="coerce").dt.year
    rows = records[record_years == year]
    if rows.empty:
        return list(INPUT_COLUMNS)
    return [column for column in INPUT_COLUMNS if pd.isna(rows.iloc[-1].get(column))]


def make_prediction(df: pd.DataFrame, model, feature_order: list[str], year: int | None = None) -> dict:
    """Predict GDP for one year using only the features the model was trained on."""
    target_year = int(df.index.max()) if year is None else year
    if target_year not in df.index:
        raise ValueError(f"Year {target_year} is not in the fetched records ({df.index.min()}-{df.index.max()}).")

    features = df.loc[[target_year], feature_order]
    if features.isnull().values.any():
        raise ValueError(
            f"Not enough history to predict {target_year}: the model needs GDP for the {MA_WINDOW} years "
            f"before it. Fetch at least {MA_WINDOW + 1} consecutive years ending in {target_year}."
        )

    return {
        "year": target_year,
        "prediction": float(model.predict(features)[0]),
        "actual": df.at[target_year, TARGET],
        "features": features.iloc[0],
    }


def usd_trillion(value: float) -> str:
    return f"US${value / 1e12:,.2f} trillion"


def print_result(result: dict, country: str, summary: dict):
    year, prediction, actual = result["year"], result["prediction"], result["actual"]
    features = result["features"]

    print(f"\n=== GDP estimate: {country}, {year} ===")
    if summary:
        start, end = summary["trained_on_years"]
        print(f"Model: {summary['model']} trained on {start}-{end} "
              f"(test R2 {summary['test_metrics']['r2']}, MAPE {summary['test_metrics']['mape_pct']}%)")
    print("Inputs:")
    print(f"  {'Population':<42}{features['Population']:>22,.0f}")
    print(f"  {f'GDP_Lag1 (GDP {year - 1})':<42}{usd_trillion(features['GDP_Lag1']):>22}")
    print(f"  {f'GDP_5Year_MA (mean GDP {year - MA_WINDOW}-{year - 1})':<42}{usd_trillion(features['GDP_5Year_MA']):>22}")
    print(f"  {'Final_consumption_expenditure':<42}{usd_trillion(features['Final_consumption_expenditure']):>22}")

    print(f"\nPredicted GDP {year}: {usd_trillion(prediction)}")
    if pd.notna(actual):
        error = (prediction - actual) / actual * 100
        baseline_error = (features["GDP_Lag1"] - actual) / actual * 100
        print(f"Actual GDP {year} (from API): {usd_trillion(actual)} -> model error {error:+.1f}%")
        print(f"Naive baseline (GDP {year - 1}): {usd_trillion(features['GDP_Lag1'])} -> baseline error {baseline_error:+.1f}%")
    else:
        print(f"Actual GDP {year}: not in the API yet, so this is a true estimate of an unknown value.")


def parse_args():
    parser = argparse.ArgumentParser(description="Task 4: fetch from the API, preprocess, load the model, predict GDP")
    parser.add_argument("--db", choices=["mongodb", "sql"], default="mongodb",
                        help="Which database's endpoints to use (default: mongodb)")
    parser.add_argument("--api", default=os.getenv("API_URL", "http://localhost:8000"),
                        help="Base URL of the Task 3 API (default: API_URL in .env, else http://localhost:8000)")
    parser.add_argument("--country", default="United States", help="Country to fetch (default: United States)")
    parser.add_argument("--start_date", default=None, help="Start date YYYY-MM-DD (use with --end_date)")
    parser.add_argument("--end_date", default=None, help="End date YYYY-MM-DD (use with --start_date)")
    parser.add_argument("--year", type=int, default=None, help="Year to estimate (default: latest year fetched)")
    parser.add_argument("--artifacts_dir", type=Path, default=DEFAULT_ARTIFACTS_DIR,
                        help="Folder with model.joblib and its config")
    return parser.parse_args()


def main():
    args = parse_args()

    # Both dates -> the date-range endpoint; no dates -> all of the country's records
    if bool(args.start_date) != bool(args.end_date):
        raise ValueError("Give both --start_date and --end_date, or neither.")
    api_url = f"{args.api.rstrip('/')}/api/{args.db}/records"
    if args.start_date:
        api_url += "/range"

    print(f"[1/4] Fetching records for {args.country} from {api_url}")
    source_df = fetch_time_series(api_url, args.country, args.start_date, args.end_date)
    print(f"      {len(source_df)} records received")

    print("[2/4] Preprocessing (same pipeline as Task 1: interpolation, GDP_Lag1, GDP_5Year_MA)")
    prepared_df = add_features(clean_records(source_df))
    print(f"      Years {prepared_df.index.min()}-{prepared_df.index.max()}, one row per year")

    print("[3/4] Loading the trained model")
    model, feature_order, summary = load_artifacts(args.artifacts_dir)
    print(f"      Features: {feature_order}")

    print("[4/4] Making the prediction")
    result = make_prediction(prepared_df, model, feature_order, args.year)
    filled = inputs_filled_for(source_df, result["year"])
    if filled:
        print(f"      Warning: the API had no {filled} for {result['year']}; values were filled from neighbouring years.")

    print_result(result, args.country, summary)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, FileNotFoundError) as err:
        print(f"\nError: {err}", file=sys.stderr)
        sys.exit(1)
