# Building a Pipeline for Time Series Data

A time-series pipeline built on the **Global Economy Indicators (1970–2021)** dataset: exploratory analysis and modelling (Task 1), MySQL and MongoDB databases (Task 2), a CRUD and time-series API (Task 3), and a prediction script that uses all of them (Task 4).

## Problem Definition

Estimate the **annual GDP of the United States** (current US$) for year *t* from its GDP history up to year *t*−1 (last year's GDP and the average of the five previous years) plus same-year population and final consumption expenditure. The estimate is a nowcast made at the end of year *t*: by then, consumption is largely known from monthly and quarterly statistics and population from the December estimate, while the first official annual GDP figure only follows in late January. The model, its features and its hyperparameters are chosen by time-ordered validation on 1975–2011; in this revised procedure, the chosen model is then tested once on 2012–2021 (which includes the 2020 COVID-19 shock; an earlier version of the analysis had already examined these years) and must beat the naive forecast "GDP this year = GDP last year".

## Dataset

**Global Economy Indicators**: 10,512 records (one per country per year) across 220 countries, 1970–2021, 26 columns.
Source: [Kaggle: prasad22/global-economy-indicators](https://www.kaggle.com/datasets/prasad22/global-economy-indicators), compiled from the UN Statistics Division's National Accounts Main Aggregates Database.
Target variable: **Gross Domestic Product (GDP)**

Why this dataset and this country:
- The predictors are the actual components of GDP (consumption + investment + exports − imports adds up to US GDP within 0.53% in every year), so they have a known economic link to the target.
- One official source and one accounting method across all years, with only 0.87% of values missing.
- The US is the largest economy in the dataset (24% of world GDP in 2021), has all 52 years with no gaps in the modelled columns, and its exchange rate is 1.0, so its dollar GDP has no currency distortion.

The full report, covering all four tasks, is [report/Group13_Report.pdf](report/Group13_Report.pdf).

---

## Quick Start: run it on your PC

**You need:** Python 3.10 or newer, [MySQL Server 8](https://dev.mysql.com/downloads/mysql/) and [MongoDB Community Server 6+](https://www.mongodb.com/try/download/community), both installed and running.

**Tested with:** Python 3.13.9, MySQL 8.4.8 and MongoDB 8.2.5, with the package versions noted in `requirements.txt`. scikit-learn is pinned to 1.7.2 because the saved model (`task4/artifacts/model.joblib`) was created with that version.

Run every command from the project folder.

### 1. Get the code

On Windows, clone into a short folder (e.g. `C:\projects`); very long paths can break `pip install`.

```bash
git clone https://github.com/jbyiringiro/gdp-time-series-pipeline.git
cd gdp-time-series-pipeline
```

### 2. Create a virtual environment and install everything

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Add your settings

Copy the example settings file, then open `.env` and set `MYSQL_PASSWORD` to your MySQL root password (leave it empty if you have none).

```bash
copy .env.example .env     # Windows
cp .env.example .env       # macOS / Linux
```

`.env` is ignored by git, so your password is never pushed.

### 4. Run the tasks

| Task | Command | What you should see |
|------|---------|---------------------|
| 1. EDA and model | `jupyter notebook Building_a_Pipeline_for_Time_Series_Data.ipynb`, then **Run All** (or open it in VS Code) | 10 figures, saved to `report/figures/`, and the experiment table |
| 2. MySQL | `python task2/mysql_setup.py` | 3 tables created, 10,512 records loaded, 5 query results |
| 2. MongoDB | `python task2/mongodb_setup.py` | 10,512 documents, 2 sample documents, 5 query results |
| 3. API | `uvicorn task3.api_demo:app --port 8000` | API running; try it at http://localhost:8000/docs. **Leave it running** |
| 3. CRUD demo | `python task3/crud_demo.py` (in a second terminal, venv activated) | POST → GET → PUT → GET → DELETE → GET on both databases plus a one-year date range and the error cases: 45 of 45 checks passed, saved to `report/crud_demo_output.txt` |
| 4. Model | `python task4/train_model.py` | Test RMSE US$889bn, MAPE 4.17%, R² 0.824 (same as the notebook) |
| 4. Prediction | `python task4/predict_from_api.py` | The four steps, then the 2021 GDP estimate (model error −5.0%) |
| 4. Prediction (SQL) | `python task4/predict_from_api.py --db sql` | The same result, read from MySQL |

### Troubleshooting

| Problem | Fix |
|---------|-----|
| `Could not connect to MySQL` | Start MySQL, and check `MYSQL_USER` / `MYSQL_PASSWORD` in `.env` |
| `Could not connect to MongoDB` | Start the MongoDB service, and check `MONGO_URI` in `.env` |
| `Could not reach the API` | Start the API (step 4, Task 3) in another terminal |
| Port 8000 already in use | Run `uvicorn task3.api_demo:app --port 8001` and set `API_URL=http://localhost:8001` in `.env` |
| `Activate.ps1 cannot be loaded` (Windows) | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or use `.venv\Scripts\activate.bat` in Command Prompt |
| `uvicorn` / `jupyter` not recognised | Activate the virtual environment first (step 2) |
| Warning about the scikit-learn version when loading the model | Run `python task4/train_model.py` to retrain it with your version |
| `pip install` fails with `WinError 206` / "filename too long" (Windows) | The folder path is too long for Windows. Clone into a short folder such as `C:\projects` and try again |

---

## Project Structure

```
├── Building_a_Pipeline_for_Time_Series_Data.ipynb  # Task 1: EDA, preprocessing, model training
├── data/
│   └── Global Economy Indicators.csv  #   Dataset: 220 countries, 1970–2021
├── requirements.txt                   # Every Python package for all four tasks
├── .env.example                       # Settings template: copy to .env and add your MySQL password
├── report/                            # Outputs
│   ├── Group13_Report.pdf             #   Full report covering all four tasks
│   ├── crud_demo_output.txt           #   Output of task3/crud_demo.py (CRUD on both databases)
│   ├── figures/                       #   Task 1 figures, saved by the notebook when it runs
│   └── screenshots/                   #   Databases, API and prediction script running
├── task2/                             # Task 2: Database design & implementation
│   ├── sql_schema.sql                 #   SQL DDL scripts (3 tables)
│   ├── erd_diagram.png                #   Entity Relationship Diagram
│   ├── mysql_setup.py                 #   MySQL: setup, load data, run queries
│   └── mongodb_setup.py               #   MongoDB: setup, load data, run queries
├── task3/                             # Task 3: API endpoints
│   ├── api_demo.py                    #   FastAPI CRUD + latest + date-range endpoints for both databases
│   ├── crud_demo.py                   #   Runs and checks the full CRUD sequence on both databases
│   └── README.md                      #   Endpoint list and example requests
├── task4/                             # Task 4: End-to-end prediction script
│   ├── predict_from_api.py            #   Fetch API data -> preprocess -> load model -> predict
│   ├── preprocessing.py               #   Task 1 preprocessing, shared by training and prediction
│   ├── train_model.py                 #   Trains and saves the Task 1 model
│   ├── README.md                      #   Task 4 usage instructions
│   └── artifacts/                     #   Model and preprocessing artifacts
│       ├── model.joblib               #   Trained Linear Regression model
│       ├── feature_order.json         #   Feature order expected by the model
│       ├── preprocess_config.json     #   Country, target, lag and moving-average window
│       └── training_summary.json      #   Training years, test metrics and package versions
└── README.md
```

## Task 1 — Exploratory Analysis and Modelling

The notebook covers the dataset checks (time range, frequency, missing values, distributions, stationarity), lag and moving-average features, five analytical questions with figures, and the model experiments. Linear Regression, a tuned Decision Tree and a tuned Random Forest are each tried with five feature sets on three time-ordered validation folds inside 1975–2011, with the naive baseline as reference. The combination with the lowest validation RMSE (Linear Regression with all four features) is then evaluated on the test years 2012–2021, which play no part in the selection. An earlier version of the analysis had already compared models on those years, so the test is not fully independent (see Section 4.8 of the report). It reads `data/Global Economy Indicators.csv`, or downloads it from GitHub when that file is not there (e.g. in Colab). See Section 4 of [report/Group13_Report.pdf](report/Group13_Report.pdf) for the full write-up.

## Task 2 — Database Design & Implementation

Both setup scripts create the database, load all 10,512 records from the CSV, and run 5 queries with their results.

### SQL Schema (3 Normalized Tables)

| Table | Description |
|-------|-------------|
| `countries` | Static country info (id, name, currency) |
| `exchange_rates` | Yearly exchange rates per country (FK → countries) |
| `economic_indicators` | 20 yearly macro metrics per country (FK → countries) |

See `task2/erd_diagram.png` for the full ERD.

### MongoDB Collection Design

Single collection `economic_records` with embedded subdocuments, and a unique index on (`country_name`, `year`) so a country cannot have two records for the same year:
- `exchange_rates` — AMA and IMF rates
- `demographics` — population, GNI per capita
- `economic_indicators` — GDP, exports, imports, consumption, etc.
- `sector_breakdown` — agriculture, manufacturing, construction, etc.

### Queries Performed (5 per database)

| # | Query | MySQL | MongoDB |
|---|-------|-------|---------|
| 1 | Top 10 countries by GDP (2021) | JOIN + ORDER BY | find + sort + limit |
| 2 | US economic indicators by date range (2015–2021) | WHERE BETWEEN | find with $gte/$lte |
| 3 | Average GDP by currency / Records per country | GROUP BY + AVG | $group aggregation |
| 4 | Latest record for a country | ORDER BY year DESC LIMIT 1 | find_one + sort |
| 5 | GDP with exchange rates over decades / Avg GNI by currency | 3-table JOIN | $match + $group |

## Task 3 — API Endpoints

`uvicorn task3.api_demo:app --port 8000` starts a FastAPI service with the same endpoints for both databases (`/api/sql/...` and `/api/mongodb/...`):

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/records` | Create a record |
| `GET` | `/records?country=...` | All records for a country |
| `GET` | `/records/latest?country=...` | Latest record |
| `GET` | `/records/range?country=...&start_date=...&end_date=...` | Records for every year that overlaps the date range |
| `PUT` | `/records/{id}` | Update a record |
| `DELETE` | `/records/{id}` | Delete a record |

The records are annual: each covers a whole year and is dated 1 January, so the date-range endpoint returns every year that overlaps the range (2015-12-30 to 2015-12-31 returns the 2015 record). `python task3/crud_demo.py` demonstrates the full CRUD sequence on both databases, including updates that change nothing, nonexistent ids, invalid date ranges and duplicate records; its output is in [report/crud_demo_output.txt](report/crud_demo_output.txt). See [task3/README.md](task3/README.md) for example requests and the status codes.

## Task 4 — Prediction Script

`task4/predict_from_api.py`:

1. Fetches a country's yearly records from the Task 3 API (MongoDB by default, `--db sql` for MySQL). Only the country the model was trained on is accepted, as recorded in `task4/artifacts/preprocess_config.json`
2. Preprocesses them with the same pipeline as Task 1 (`task4/preprocessing.py`: interpolation, `GDP_Lag1`, `GDP_5Year_MA` built from previous years only, with the window saved in `preprocess_config.json`). Records after the year being estimated, and that year's own GDP, are left out, so no missing value is filled from information that comes later
3. Loads the trained model (`task4/artifacts/model.joblib`, saved by `task4/train_model.py`)
4. Estimates GDP for the latest year and compares it with the actual value and the naive baseline

The output for 2021 (model error −5.0%, baseline error −9.4%) matches the Task 1 results. See [task4/README.md](task4/README.md) for all options and the error handling.
