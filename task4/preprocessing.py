"""
Preprocessing shared by train_model.py and predict_from_api.py.

It repeats the Task 1 pipeline so the model sees the same kind of data
when it is trained and when it makes a prediction:
  1. one row per year (missing years are added and filled)
  2. missing values filled by linear interpolation, ffill/bfill at the edges
  3. GDP_Lag1 and GDP_5Year_MA built only from previous years, so the GDP
     being predicted never leaks into its own features

For a prediction, only what would be known when estimating that year is used
(see clean_records), so no gap is filled from a later GDP value.
"""

import numpy as np
import pandas as pd

TARGET = "GDP"
INPUT_COLUMNS = ["Population", "Final_consumption_expenditure"]
FEATURES = ["Population", "GDP_Lag1", "GDP_5Year_MA", "Final_consumption_expenditure"]
LAG = 1
MA_WINDOW = 5


def record_years(records: pd.DataFrame) -> pd.Series:
    """The year of each record. The API sends both Year and Date; Date is the fallback."""
    if "Year" in records.columns:
        return pd.to_numeric(records["Year"], errors="coerce")
    if "Date" in records.columns:
        return pd.to_datetime(records["Date"], errors="coerce").dt.year
    raise ValueError("Records need a 'Year' or 'Date' field.")


def clean_records(records: pd.DataFrame, predict_year: int | None = None) -> pd.DataFrame:
    """Index the records by year and fill gaps the same way as Task 1.

    With predict_year, the data are cut to what would be known when estimating
    that year: later years are dropped and that year's GDP is left empty, so
    interpolation can never fill an earlier gap from the GDP being predicted
    or from any year after it.
    """
    df = records.copy()
    df["Year"] = record_years(df)

    missing_columns = [column for column in [TARGET] + INPUT_COLUMNS if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Records are missing the columns: {missing_columns}")

    df = df.dropna(subset=["Year"])
    df["Year"] = df["Year"].astype(int)
    df = df.drop_duplicates(subset="Year", keep="last").set_index("Year").sort_index()
    if predict_year is not None:
        df = df.loc[:predict_year]
        if df.empty:
            raise ValueError(f"No records up to {predict_year}.")

    # Lags assume one row = one year, so add any missing years as empty rows
    df = df.reindex(range(df.index.min(), df.index.max() + 1))
    for column in [TARGET] + INPUT_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    # The GDP being predicted is the unknown, so it cannot help fill other years
    if predict_year is not None and predict_year in df.index:
        df.loc[predict_year, TARGET] = np.nan

    # Inputs: interpolate between known years, ffill/bfill at the start or end (as in Task 1)
    df[INPUT_COLUMNS] = df[INPUT_COLUMNS].interpolate(method="linear").ffill().bfill()

    # Target: only fill gaps between two known years. A year whose GDP is not
    # known yet (the year we want to predict) must stay empty
    df[TARGET] = df[TARGET].interpolate(method="linear", limit_area="inside")
    return df


def add_features(df: pd.DataFrame, ma_window: int = MA_WINDOW) -> pd.DataFrame:
    """Add the lag and moving-average features used by the Task 1 model."""
    df = df.copy()
    df["GDP_Lag1"] = df[TARGET].shift(LAG)

    # shift(1) comes before rolling() so year t only averages the ma_window years before it
    df["GDP_5Year_MA"] = df[TARGET].shift(LAG).rolling(window=ma_window).mean()
    return df
