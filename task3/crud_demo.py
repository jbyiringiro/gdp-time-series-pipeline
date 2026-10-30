"""
Task 3 - CRUD demonstration for both databases

Runs a complete POST -> GET -> PUT -> GET -> DELETE -> GET sequence against
the running API, for MySQL and then MongoDB, followed by the error cases:
an update that changes nothing, nonexistent IDs, invalid date ranges and a
duplicate record. Each step prints the request, the HTTP status and the
response, and checks that the status (and the returned values) are the ones
expected. Everything printed is also saved to report/crud_demo_output.txt.

The test record is the United States in 2030, a year that is not in the
dataset, and it is deleted again by the sequence itself.

Usage (with the API running):
    python task3/crud_demo.py                            # API_URL in .env, else http://localhost:8000
    python task3/crud_demo.py --api http://localhost:8001
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
OUTPUT_PATH = BASE_DIR / "report" / "crud_demo_output.txt"

COUNTRY = "United States"
TEST_YEAR = 2030
RANGE = {"country": COUNTRY, "start_date": f"{TEST_YEAR}-01-01", "end_date": f"{TEST_YEAR}-12-31"}
NEW_RECORD = {
    "country_name": COUNTRY,
    "currency": "US Dollar",
    "year": TEST_YEAR,
    "population": 355_000_000,
    "gdp": 30_000_000_000_000,
    "final_consumption_expenditure": 24_000_000_000_000,
}
UPDATE = {"gdp": 31_000_000_000_000, "ama_exchange_rate": 1.0, "imf_exchange_rate": 1.0}

# The id field in a GET response, and an id that does not exist, for each database
ID_FIELD = {"sql": "record_id", "mongodb": "id"}
MISSING_ID = {"sql": "999999", "mongodb": "000000000000000000000000"}

lines = []
results = []


def log(text: str = ""):
    print(text)
    lines.append(text)


def short(body) -> str:
    """The response on one line, without long lists of records."""
    if isinstance(body, dict) and isinstance(body.get("data"), list):
        body = {**body, "data": body["data"][:1]}
    return json.dumps(body, default=str)


def step(label: str, method: str, url: str, expected: int, params=None, body=None, checks=None):
    """Send one request, print it with its response, and record whether it matched expectations."""
    response = requests.request(method, url, params=params, json=body, timeout=30)
    try:
        payload = response.json()
    except ValueError:
        payload = response.text

    query = ("?" + "&".join(f"{k}={v}" for k, v in params.items())) if params else ""
    log(f"{label}")
    log(f"  {method} {urlparse(url).path}{query}")
    if body is not None:
        log(f"  body: {json.dumps(body)}")
    passed = response.status_code == expected
    log(f"  -> {response.status_code} (expected {expected})  {'PASS' if passed else 'FAIL'}")
    log(f"  {short(payload)}")
    results.append(passed)

    for description, ok in (checks(payload) if checks and passed else []):
        log(f"  check: {description}  {'PASS' if ok else 'FAIL'}")
        results.append(ok)
    log()
    return payload


def run_sequence(api: str, db: str):
    records = f"{api}/api/{db}/records"
    id_field = ID_FIELD[db]
    name = "MySQL" if db == "sql" else "MongoDB"
    log("=" * 70)
    log(f"{name}: POST -> GET -> PUT -> GET -> DELETE -> GET")
    log("=" * 70)

    created = step(f"[{name} 1] Create a record for {COUNTRY} {TEST_YEAR}",
                   "POST", records, 201, body=NEW_RECORD)
    record_id = str(created.get("id")) if isinstance(created, dict) else None
    if not record_id:
        log("  Stopping: the record was not created.")
        return

    try:
        def created_checks(payload):
            row = payload["data"][0]
            return [(f"the record read back has the id POST returned ({record_id})", str(row[id_field]) == record_id),
                    ("GDP is the value sent", row["GDP"] == NEW_RECORD["gdp"])]

        step(f"[{name} 2] Read it back", "GET", f"{records}/range", 200, params=RANGE, checks=created_checks)

        step(f"[{name} 3] Update GDP and add exchange rates (the record has none yet)",
             "PUT", f"{records}/{record_id}", 200, body=UPDATE,
             checks=lambda payload: [("the response says 1 record was modified", payload.get("modified") == 1)])

        def updated_checks(payload):
            row = payload["data"][0]
            return [("GDP has the new value", row["GDP"] == UPDATE["gdp"]),
                    ("the exchange rates were saved", row["AMA_exchange_rate"] == 1.0 and row["IMF_exchange_rate"] == 1.0)]

        step(f"[{name} 4] Read it again", "GET", f"{records}/range", 200, params=RANGE, checks=updated_checks)

        step(f"[{name} 5] Send the same update again (changes nothing, the record still exists)",
             "PUT", f"{records}/{record_id}", 200, body=UPDATE,
             checks=lambda payload: [("the response says 0 records were modified", payload.get("modified") == 0)])

        step(f"[{name} 6] Delete the record", "DELETE", f"{records}/{record_id}", 200)
        record_id = None
        step(f"[{name} 7] Read it again: the record is gone", "GET", f"{records}/range", 404, params=RANGE)
    finally:
        # Remove the test record if the sequence stopped before deleting it
        if record_id:
            requests.delete(f"{records}/{record_id}", timeout=30)
            log(f"  Cleanup: deleted test record {record_id}")


def run_error_cases(api: str, db: str):
    records = f"{api}/api/{db}/records"
    name = "MySQL" if db == "sql" else "MongoDB"
    missing = MISSING_ID[db]
    log("=" * 70)
    log(f"{name}: error cases")
    log("=" * 70)

    step(f"[{name} E1] Update a record that does not exist", "PUT", f"{records}/{missing}", 404, body={"gdp": 1.0})
    step(f"[{name} E2] Update only the exchange rate of a record that does not exist",
         "PUT", f"{records}/{missing}", 404, body={"ama_exchange_rate": 1.0})
    step(f"[{name} E3] Delete a record that does not exist", "DELETE", f"{records}/{missing}", 404)
    step(f"[{name} E4] Date range with an incomplete date (year only)", "GET", f"{records}/range", 400,
         params={"country": COUNTRY, "start_date": "2015", "end_date": "2021-12-31"})
    step(f"[{name} E5] Date range with a date that does not exist (30 February)", "GET", f"{records}/range", 400,
         params={"country": COUNTRY, "start_date": "2015-02-30", "end_date": "2021-12-31"})
    step(f"[{name} E6] Date range that ends before it starts", "GET", f"{records}/range", 400,
         params={"country": COUNTRY, "start_date": "2021-01-01", "end_date": "2015-12-31"})
    step(f"[{name} E7] Create a second record for {COUNTRY} 2021 (already in the database)",
         "POST", records, 409, body={**NEW_RECORD, "year": 2021})
    if db == "mongodb":
        step(f"[{name} E8] Update with an id that is not a valid MongoDB id",
             "PUT", f"{records}/not-an-id", 400, body={"gdp": 1.0})


def parse_args():
    parser = argparse.ArgumentParser(description="Task 3: CRUD demonstration for MySQL and MongoDB")
    parser.add_argument("--api", default=os.getenv("API_URL", "http://localhost:8000"),
                        help="Base URL of the Task 3 API (default: API_URL in .env, else http://localhost:8000)")
    return parser.parse_args()


def main():
    api = parse_args().api.rstrip("/")
    try:
        requests.get(f"{api}/health", timeout=10).raise_for_status()
    except requests.RequestException as err:
        sys.exit(f"Could not reach the API at {api}. Is it running? "
                 f"(uvicorn task3.api_demo:app --port 8000)\n  {err}")

    log(f"CRUD demonstration against {api}\n")
    for db in ["sql", "mongodb"]:
        run_sequence(api, db)
        run_error_cases(api, db)

    log(f"{sum(results)} of {len(results)} checks passed")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"Saved to {OUTPUT_PATH}")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
