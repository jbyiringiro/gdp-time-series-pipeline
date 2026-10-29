"""
Preprocessing shared by train_model.py and predict_from_api.py.

It repeats the Task 1 pipeline so the model sees the same kind of data
when it is trained and when it makes a prediction:
  1. one row per year (missing years are added and filled)
  2. missing values filled by linear interpolation, ffill/bfill at the edges
  3. GDP_Lag1 and GDP_5Year_MA built only from previous years, so the GDP
     being predicted never leaks into its own features
"""

import pandas as pd

TARGET = "GDP"
INPUT_COLUMNS = ["Population", "Final_consumption_expenditure"]
FEATURES = ["Population", "GDP_Lag1", "GDP_5Year_MA", "Final_consumption_expenditure"]
MA_WINDOW = 5


def clean_records(records: pd.DataFrame) -> pd.DataFrame:
    """Index the records by year and fill gaps the same way as Task 1."""
    df = records.copy()

    # The API sends both Year and Date; fall back to Date if Year is missing
    if "Year" not in df.columns:
        if "Date" not in df.columns:
            raise ValueError("Records need a 'Year' or 'Date' field.")
        df["Year"] = pd.to_datetime(df["Date"], errors="coerce").dt.year

    missing_columns = [column for column in [TARGET] + INPUT_COLUMNS if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Records are missing the columns: {missing_columns}")

    df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
    df = df.dropna(subset=["Year"])
    df["Year"] = df["Year"].astype(int)
    df = df.drop_duplicates(subset="Year", keep="last").set_index("Year").sort_index()

    # Lags assume one row = one year, so add any missing years as empty rows
    df = df.reindex(range(df.index.min(), df.index.max() + 1))
    for column in [TARGET] + INPUT_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    # Inputs: interpolate between known years, ffill/bfill at the start or end (as in Task 1)
    df[INPUT_COLUMNS] = df[INPUT_COLUMNS].interpolate(method="linear").ffill().bfill()

    # Target: only fill gaps between two known years. A year whose GDP is not
    # known yet (the year we want to predict) must stay empty
    df[TARGET] = df[TARGET].interpolate(method="linear", limit_area="inside")
    return df


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add the lag and moving-average features used by the Task 1 model."""
    df = df.copy()
    df["GDP_Lag1"] = df[TARGET].shift(1)

    # shift(1) comes before rolling() so year t only averages years t-5 to t-1
    df["GDP_5Year_MA"] = df[TARGET].shift(1).rolling(window=MA_WINDOW).mean()
    return df
