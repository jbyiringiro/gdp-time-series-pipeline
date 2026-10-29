# Task 4 — Prediction Script

`predict_from_api.py` brings the previous tasks together:

1. **Fetches** a country's yearly records from the Task 3 API (SQL or MongoDB endpoints)
2. **Preprocesses** them with the same pipeline as Task 1 (`preprocessing.py`)
3. **Loads** the trained model saved by `train_model.py`
4. **Predicts** GDP for the latest year (or `--year`) and compares it with the actual value, when the API has one, and with the naive baseline "GDP this year = GDP last year"

## Files

| File | Purpose |
|------|---------|
| `preprocessing.py` | Cleaning and feature engineering shared by training and prediction, so both use exactly the Task 1 steps |
| `train_model.py` | Trains the Task 1 model (Linear Regression, United States, chronological 80/20 split) and saves it |
| `predict_from_api.py` | The Task 4 script: API → preprocessing → model → prediction |
| `artifacts/model.joblib` | Trained Linear Regression model |
| `artifacts/feature_order.json` | Feature names in the order the model expects |
| `artifacts/preprocess_config.json` | Country, target, lag and moving-average window |
| `artifacts/training_summary.json` | Training years and test metrics |

## How it matches Task 1

| Step | Task 1 notebook | Task 4 (`preprocessing.py`) |
|------|-----------------|-----------------------------|
| Frequency | One row per year | Missing years are added as rows, so `shift(1)` always means "previous year" |
| Missing values | Linear interpolation, ffill/bfill at the edges | Same for `Population` and `Final_consumption_expenditure`; GDP is only interpolated *between* known years, so a year whose GDP is unknown stays empty and can be predicted |
| Lag feature | `GDP_Lag1` = GDP of the previous year | Same |
| Moving average | `GDP_5Year_MA` = mean of the 5 previous years (`shift(1)` before `rolling(5)`) | Same, so the GDP being predicted never leaks into its own features |
| Features | `Population`, `GDP_Lag1`, `GDP_5Year_MA`, `Final consumption expenditure` | Same four |
| Model | Linear Regression, trained 1975–2011, tested 2012–2021 | Same; `train_model.py` reproduces the notebook's test results (RMSE US$889bn, MAPE 4.17%, R² 0.82) |

## Setup

First follow the Quick Start in the [main README](../README.md) (install `requirements.txt`, create `.env`, load the databases, start the API). Then:

```bash
# Train and save the model (prints the same test metrics as the Task 1 notebook)
python task4/train_model.py
```

## Run

With the Task 3 API running:

```bash
# MongoDB, all US records, estimate the latest year (2021)
python task4/predict_from_api.py

# MongoDB, records 2010-2021 only (uses the date-range endpoint)
python task4/predict_from_api.py --start_date 2010-01-01 --end_date 2021-12-31

# MySQL, estimate a chosen year
python task4/predict_from_api.py --db sql --year 2015
```

Example output (`--start_date 2010-01-01 --end_date 2021-12-31`):

```
[1/4] Fetching records for United States from http://localhost:8000/api/mongodb/records/range
      12 records received
[2/4] Preprocessing (same pipeline as Task 1: interpolation, GDP_Lag1, GDP_5Year_MA)
      Years 2010-2021, one row per year
[3/4] Loading the trained model
      Features: ['Population', 'GDP_Lag1', 'GDP_5Year_MA', 'Final_consumption_expenditure']
[4/4] Making the prediction

=== GDP estimate: United States, 2021 ===
Model: LinearRegression trained on 1975-2011 (test R2 0.824, MAPE 4.17%)
Inputs:
  Population                                           336,997,624
  GDP_Lag1 (GDP 2020)                            US$21.10 trillion
  GDP_5Year_MA (mean GDP 2016-2020)              US$20.24 trillion
  Final_consumption_expenditure                  US$19.30 trillion

Predicted GDP 2021: US$22.14 trillion
Actual GDP 2021 (from API): US$23.30 trillion -> model error -5.0%
Naive baseline (GDP 2020): US$21.10 trillion -> baseline error -9.4%
```

The errors (−5.0% for the model, −9.4% for the baseline) are the same as the 2021 column of the Task 1 per-year error table, which confirms the API → preprocessing → model path reproduces Task 1.

### Options

| Argument | Default | Description |
|----------|---------|-------------|
| `--db` | `mongodb` | `mongodb` or `sql`: which database's endpoints to use |
| `--api` | `API_URL` in `.env`, else `http://localhost:8000` | Base URL of the Task 3 API |
| `--country` | `United States` | Country to fetch |
| `--start_date`, `--end_date` | none | `YYYY-MM-DD`, give both or neither; with them the script uses the `/range` endpoint, without them it fetches all records |
| `--year` | latest year fetched | Year to estimate |
| `--artifacts_dir` | `task4/artifacts` | Folder with the model and its config |

### Estimating a year that is not in the data yet

Create a record for the new year through the Task 3 API with its `population` and `final_consumption_expenditure` but no `gdp` (e.g. `POST /api/mongodb/records`), then run the script. Preprocessing leaves that year's GDP empty and the script predicts it. For predictions beyond 2021, retrain first with `python task4/train_model.py --use_all_years`, which refits the model on every year up to 2021 after evaluating it.

### Error handling

The script exits with a clear message (exit code 1) when:

- the API is not running or returns an error (e.g. unknown country, database down);
- only one of `--start_date` / `--end_date` is given;
- fewer than 6 consecutive years are fetched (the 5-year moving average needs 5 previous years);
- the requested `--year` is not in the fetched records;
- the model has not been trained yet, or the model and `feature_order.json` come from different training runs.

If the API has no population or consumption value for the year being estimated, the script fills it from neighbouring years (as in Task 1) and prints a warning.
