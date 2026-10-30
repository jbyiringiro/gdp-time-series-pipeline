# Task 3 — CRUD & Time-Series Query API

Full CRUD (POST, GET, PUT, DELETE) endpoints for **both MySQL and MongoDB** databases created in Task 2.

## Prerequisites

Follow the Quick Start in the [main README](../README.md): install `requirements.txt`, create `.env` from `.env.example`, then load both databases:

```bash
python task2/mysql_setup.py
python task2/mongodb_setup.py
```

The API reads its MySQL and MongoDB settings from `.env` (`MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DB`, `MONGO_URI`, `MONGO_DB`).

## Run API

From the project folder:

```bash
uvicorn task3.api_demo:app --reload --port 8000
```

Interactive docs are available at `http://localhost:8000/docs`.

## Endpoints

### Health

- `GET /health`

### SQL (MySQL) — CRUD

| Method   | Endpoint                       | Description                        |
|----------|--------------------------------|------------------------------------|
| `POST`   | `/api/sql/records`             | Create a new economic record       |
| `GET`    | `/api/sql/records?country=...` | Get all records for a country      |
| `GET`    | `/api/sql/records/latest?country=...` | Get latest record           |
| `GET`    | `/api/sql/records/range?country=...&start_date=...&end_date=...` | Records by date range |
| `PUT`    | `/api/sql/records/{record_id}` | Update an existing record          |
| `DELETE` | `/api/sql/records/{record_id}` | Delete a record                    |

### MongoDB — CRUD

| Method   | Endpoint                           | Description                        |
|----------|------------------------------------|------------------------------------|
| `POST`   | `/api/mongodb/records`             | Create a new economic record       |
| `GET`    | `/api/mongodb/records?country=...` | Get all records for a country      |
| `GET`    | `/api/mongodb/records/latest?country=...` | Get latest record           |
| `GET`    | `/api/mongodb/records/range?country=...&start_date=...&end_date=...` | Records by date range |
| `PUT`    | `/api/mongodb/records/{record_id}` | Update an existing record          |
| `DELETE` | `/api/mongodb/records/{record_id}` | Delete a record                    |

## Example Requests

**Create a record (SQL):**
```bash
curl -X POST http://localhost:8000/api/sql/records \
  -H "Content-Type: application/json" \
  -d '{"country_name": "United States", "year": 2023, "gdp": 25000000, "population": 335000000}'
```

**Get latest record (MongoDB):**
```bash
curl "http://localhost:8000/api/mongodb/records/latest?country=United%20States"
```

**Get records by date range (SQL):**
```bash
curl "http://localhost:8000/api/sql/records/range?country=United%20States&start_date=2015-01-01&end_date=2021-12-31"
```

**Update a record (SQL):**
```bash
curl -X PUT http://localhost:8000/api/sql/records/42 \
  -H "Content-Type: application/json" \
  -d '{"gdp": 26000000}'
```

**Delete a record (MongoDB):**
```bash
curl -X DELETE http://localhost:8000/api/mongodb/records/64a1b2c3d4e5f6a7b8c9d0e1
```

All endpoints return JSON. Date values are formatted as `YYYY-MM-DD`.

## Responses and Error Codes

| Status | When |
|--------|------|
| `201` | `POST` created the record; the response contains its `id` |
| `200` | The record was read, updated or deleted. `PUT` returns `"modified": 1` when values changed and `"modified": 0` when the record already had them |
| `400` | `start_date` / `end_date` are not complete `YYYY-MM-DD` dates (e.g. `2015` or `2015-02-30`), `end_date` is before `start_date`, the body has no fields to update, or a MongoDB id is not valid |
| `404` | The record id does not exist, or no records match the country or date range |
| `409` | A record for that country and year already exists (MySQL: unique key on `country_id, year`; MongoDB: unique index on `country_name, year`) |
| `503` | MySQL or MongoDB is not reachable |

The existence of a record is checked before it is updated, so an update that changes nothing still returns `200`, and an update of a missing record returns `404`. When a MySQL record has no exchange-rate row for its year, updating its exchange rates creates that row.

## CRUD Demonstration

With the API running, `crud_demo.py` runs the complete sequence **POST → GET → PUT → GET → DELETE → GET** on both databases, then the error cases (unchanged update, nonexistent ids, invalid date ranges, duplicate record):

```bash
python task3/crud_demo.py                            # API_URL in .env, else http://localhost:8000
python task3/crud_demo.py --api http://localhost:8001
```

Each step prints the request, the status code and the response, and checks the result (for example, that the id returned by `POST` is the id read back by `GET`). The test record is the United States in 2030, which is not in the dataset, and the sequence deletes it again. The output of the last run, with all 41 checks passed, is in [report/crud_demo_output.txt](../report/crud_demo_output.txt).
