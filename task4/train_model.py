"""
Trains the Task 1 model and saves it for the Task 4 prediction script.

Follows Part C of the Task 1 notebook: United States only, the same
preprocessing and features, a chronological 80/20 split and Linear Regression,
the model and feature set chosen there by time-ordered validation on the
training years. The test results printed here should match the notebook.
The package versions used are saved with the model, because a model saved
with one scikit-learn version may not load the same way in another.

Usage:
    python task4/train_model.py                  # train on 1975-2011, as in Task 1
    python task4/train_model.py --use_all_years  # refit on every year after evaluating
"""

import argparse
import json
import platform
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_percentage_error, mean_squared_error, r2_score

from preprocessing import FEATURES, LAG, MA_WINDOW, TARGET, add_features, clean_records

BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = BASE_DIR / "data" / "Global Economy Indicators.csv"
ARTIFACTS_DIR = BASE_DIR / "task4" / "artifacts"
COUNTRY = "United States"
TRAIN_SHARE = 0.8

# CSV column names -> the field names returned by the Task 3 API
CSV_TO_API = {
    "Gross Domestic Product (GDP)": "GDP",
    "Final consumption expenditure": "Final_consumption_expenditure",
}


def load_country(csv_path: Path, country: str) -> pd.DataFrame:
    """Read the CSV, clean the padded names and keep one country."""
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()
    df["Country"] = df["Country"].str.strip()
    df = df[df["Country"] == country].rename(columns=CSV_TO_API)
    if df.empty:
        raise ValueError(f"No rows for country '{country}' in {csv_path}")
    return df[["Year", "Population", "Final_consumption_expenditure", "GDP"]]


def evaluate(y_true: pd.Series, y_pred) -> dict:
    """RMSE (US$ billion), MAPE (%) and R2, the metrics used in Task 1."""
    return {
        "rmse_usd_billion": round(float(np.sqrt(mean_squared_error(y_true, y_pred))) / 1e9, 2),
        "mape_pct": round(float(mean_absolute_percentage_error(y_true, y_pred)) * 100, 2),
        "r2": round(float(r2_score(y_true, y_pred)), 3),
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Train the Task 1 GDP model and save it for Task 4")
    parser.add_argument(
        "--use_all_years",
        action="store_true",
        help="After evaluating, refit on every year so the model is current for new predictions",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    # Same steps as Task 1: clean, build features, drop the first years without a full history
    data = add_features(clean_records(load_country(CSV_PATH, COUNTRY)))
    data = data.dropna(subset=FEATURES + [TARGET])
    X, y = data[FEATURES], data[TARGET]

    # Chronological split: first 80% of years for training, last 20% for testing
    split = int(len(X) * TRAIN_SHARE)
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train, y_test = y.iloc[:split], y.iloc[split:]

    model = LinearRegression().fit(X_train, y_train)
    test_metrics = evaluate(y_test, model.predict(X_test))
    baseline_metrics = evaluate(y_test, X_test["GDP_Lag1"])

    print(f"Train years: {X_train.index.min()}-{X_train.index.max()} | Test years: {X_test.index.min()}-{X_test.index.max()}")
    print(f"{'Model':<28}{'RMSE (US$ bn)':>15}{'MAPE (%)':>10}{'R2':>8}")
    for name, metrics in [("Naive baseline (last year)", baseline_metrics), ("Linear Regression", test_metrics)]:
        print(f"{name:<28}{metrics['rmse_usd_billion']:>15,.2f}{metrics['mape_pct']:>10.2f}{metrics['r2']:>8.3f}")

    trained_on = (int(X_train.index.min()), int(X_train.index.max()))
    if args.use_all_years:
        model = LinearRegression().fit(X, y)
        trained_on = (int(X.index.min()), int(X.index.max()))
        print(f"Refitted on all years {trained_on[0]}-{trained_on[1]} for new predictions")

    joblib.dump(model, ARTIFACTS_DIR / "model.joblib")
    with open(ARTIFACTS_DIR / "feature_order.json", "w", encoding="utf-8") as feature_file:
        json.dump({"feature_order": FEATURES}, feature_file, indent=2)
    with open(ARTIFACTS_DIR / "preprocess_config.json", "w", encoding="utf-8") as config_file:
        json.dump({"country": COUNTRY, "target": TARGET, "lag": LAG, "moving_average_window": MA_WINDOW}, config_file, indent=2)
    with open(ARTIFACTS_DIR / "training_summary.json", "w", encoding="utf-8") as summary_file:
        json.dump(
            {
                "model": "LinearRegression",
                "selected_by": "lowest time-ordered validation RMSE on the training years (Task 1 notebook, Part C)",
                "trained_on_years": trained_on,
                "test_years": [int(X_test.index.min()), int(X_test.index.max())],
                "test_metrics": test_metrics,
                "naive_baseline_test_metrics": baseline_metrics,
                "versions": {
                    "python": platform.python_version(),
                    "scikit-learn": sklearn.__version__,
                    "pandas": pd.__version__,
                    "numpy": np.__version__,
                },
            },
            summary_file,
            indent=2,
        )

    print(f"Saved model and config to: {ARTIFACTS_DIR}")


if __name__ == "__main__":
    main()
