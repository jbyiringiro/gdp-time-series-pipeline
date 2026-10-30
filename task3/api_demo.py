"""
Task 3 - API Endpoints for CRUD and Time-Series Queries

Full CRUD operations (POST, GET, PUT, DELETE) for both MySQL and MongoDB
databases created in Task 2.  Each database exposes:
  - POST   /api/{db}/records          - Create a record
  - GET    /api/{db}/records           - Read all records for a country
  - GET    /api/{db}/records/latest    - Read the latest record
  - GET    /api/{db}/records/range     - Read records in a date range
  - PUT    /api/{db}/records/{id}      - Update a record
  - DELETE /api/{db}/records/{id}      - Delete a record
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import mysql.connector
from bson import ObjectId
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from mysql.connector import errorcode
from pydantic import BaseModel, Field
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

# Settings come from the .env file in the project root (copy .env.example to .env)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


# App

app = FastAPI(
    title="Global Economy Indicators API",
    description="CRUD and time-series query endpoints for MySQL and MongoDB",
    version="2.0.0",
)

# Database connection settings (match task2 scripts)

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DB", "global_economy_db"),
}
# A socket is only used when one is set (some Linux setups); otherwise TCP works on every OS
if os.getenv("MYSQL_SOCKET"):
    MYSQL_CONFIG["unix_socket"] = os.getenv("MYSQL_SOCKET")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB = os.getenv("MONGO_DB", "global_economy_db")
MONGO_COLLECTION = "economic_records"


# Pydantic schemas

class EconomicRecordCreate(BaseModel):
    """Body schema for creating a new economic record."""
    country_name: str = Field(..., example="United States")
    currency: str = Field("US Dollar", example="US Dollar")
    year: int = Field(..., example=2022)
    population: Optional[float] = None
    per_capita_gni: Optional[float] = None
    gdp: Optional[float] = None
    gni_usd: Optional[float] = None
    exports: Optional[float] = None
    imports: Optional[float] = None
    final_consumption_expenditure: Optional[float] = None
    government_consumption: Optional[float] = None
    household_consumption: Optional[float] = None
    gross_capital_formation: Optional[float] = None
    gross_fixed_capital_formation: Optional[float] = None
    changes_in_inventories: Optional[float] = None
    total_value_added: Optional[float] = None
    agriculture: Optional[float] = None
    manufacturing: Optional[float] = None
    construction: Optional[float] = None
    wholesale_retail: Optional[float] = None
    transport_storage_communication: Optional[float] = None
    other_activities: Optional[float] = None
    mining_manufacturing_utilities: Optional[float] = None
    ama_exchange_rate: Optional[float] = None
    imf_exchange_rate: Optional[float] = None


class EconomicRecordUpdate(BaseModel):
    """Body schema for updating an existing record (partial)."""
    population: Optional[float] = None
    per_capita_gni: Optional[float] = None
    gdp: Optional[float] = None
    gni_usd: Optional[float] = None
    exports: Optional[float] = None
    imports: Optional[float] = None
    final_consumption_expenditure: Optional[float] = None
    government_consumption: Optional[float] = None
    household_consumption: Optional[float] = None
    gross_capital_formation: Optional[float] = None
    gross_fixed_capital_formation: Optional[float] = None
    ama_exchange_rate: Optional[float] = None
    imf_exchange_rate: Optional[float] = None


# Database helpers

def _get_mysql():
    """Return a MySQL connection (raises 503 on failure)."""
    try:
        return mysql.connector.connect(**MYSQL_CONFIG)
    except mysql.connector.Error as err:
        raise HTTPException(status_code=503, detail=f"MySQL connection failed: {err}")


def _get_mongo():
    """Return the MongoDB collection (raises 503 on failure)."""
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()
        return client[MONGO_DB][MONGO_COLLECTION]
    except Exception as err:
        raise HTTPException(status_code=503, detail=f"MongoDB connection failed: {err}")


def _get_or_create_country(cursor, name: str, currency: str = ""):
    """Look up a country_id in MySQL, creating the row if needed."""
    cursor.execute(
        "SELECT country_id FROM countries WHERE country_name = %s", (name,)
    )
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("SELECT COALESCE(MAX(country_id), 0) + 1 FROM countries")
    new_id = cursor.fetchone()[0]
    cursor.execute(
        "INSERT INTO countries (country_id, country_name, currency) VALUES (%s, %s, %s)",
        (new_id, name, currency),
    )
    return new_id


def _parse_date(value: str, name: str):
    """Parse a complete YYYY-MM-DD date; '2015', '2015-6-1' or '2015-02-30' are rejected."""
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {name} '{value}'. Use a complete date in YYYY-MM-DD format",
        )


def _years_in_range(start_date: str, end_date: str):
    """Validate both dates first, then convert them into the years stored in the databases.

    The records are annual: each one covers a whole calendar year and is dated
    1 January of that year. A year is returned when it overlaps the range, so
    2015-12-30 to 2015-12-31 returns the 2015 record (dated 2015-01-01).
    """
    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date")
    if end < start:
        raise HTTPException(
            status_code=400, detail="end_date must not be before start_date"
        )
    return start.year, end.year


def _update_message(modified: int) -> str:
    return "Record updated" if modified else "No changes: the record already has these values"


# SQL query used by several GET endpoints
_SQL_SELECT = """
    SELECT c.country_name  AS Country,
           ei.year          AS Year,
           ei.population    AS Population,
           ei.per_capita_gni AS Per_capita_GNI,
           ei.gdp           AS GDP,
           ei.gni_usd       AS GNI_USD,
           ei.exports        AS Exports,
           ei.imports        AS Imports,
           ei.final_consumption_expenditure AS Final_consumption_expenditure,
           er.ama_exchange_rate             AS AMA_exchange_rate,
           er.imf_based_exchange_rate       AS IMF_exchange_rate,
           ei.id             AS record_id,
           CONCAT(ei.year, '-01-01') AS Date
    FROM economic_indicators ei
    JOIN countries c        ON ei.country_id = c.country_id
    LEFT JOIN exchange_rates er
           ON ei.country_id = er.country_id AND ei.year = er.year
"""


def _flatten_mongo(doc: dict) -> dict:
    """Convert a nested MongoDB document into a flat API-friendly dict."""
    ei = doc.get("economic_indicators", {})
    demo = doc.get("demographics", {})
    trade = doc.get("trade", {})
    exr = doc.get("exchange_rates", {})
    return {
        "id": str(doc["_id"]),
        "Country": doc.get("country_name"),
        "Year": doc.get("year"),
        "Date": f"{doc['year']}-01-01" if doc.get("year") else None,
        "Population": demo.get("population"),
        "Per_capita_GNI": demo.get("per_capita_gni"),
        "GDP": ei.get("gdp"),
        "GNI_USD": ei.get("gni_usd"),
        "Exports": ei.get("exports"),
        "Imports": ei.get("imports"),
        "Final_consumption_expenditure": ei.get("final_consumption_expenditure"),
        "AMA_exchange_rate": exr.get("ama_exchange_rate") or trade.get("ama_exchange_rate"),
        "IMF_exchange_rate": exr.get("imf_based_exchange_rate") or trade.get("imf_exchange_rate"),
    }


# Health check

@app.get("/health")
def health_check():
    return {"status": "ok"}


# ═════════════════════════════════════════════════════════
#  SQL (MySQL) CRUD ENDPOINTS
# ═════════════════════════════════════════════════════════


# ---- CREATE --------------------------------------------------------
@app.post("/api/sql/records", status_code=201)
def sql_create_record(record: EconomicRecordCreate):
    """Insert a new economic record into MySQL."""
    conn = _get_mysql()
    cursor = conn.cursor()
    try:
        country_id = _get_or_create_country(
            cursor, record.country_name, record.currency
        )

        cursor.execute(
            """
            INSERT INTO economic_indicators
                (country_id, year, population, per_capita_gni, gdp, gni_usd,
                 exports, imports, final_consumption_expenditure,
                 government_consumption, household_consumption,
                 gross_capital_formation, gross_fixed_capital_formation,
                 changes_in_inventories, total_value_added,
                 agriculture, manufacturing, construction,
                 wholesale_retail, transport_storage_communication,
                 other_activities, mining_manufacturing_utilities)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                country_id, record.year, record.population,
                record.per_capita_gni, record.gdp, record.gni_usd,
                record.exports, record.imports,
                record.final_consumption_expenditure,
                record.government_consumption, record.household_consumption,
                record.gross_capital_formation,
                record.gross_fixed_capital_formation,
                record.changes_in_inventories, record.total_value_added,
                record.agriculture, record.manufacturing, record.construction,
                record.wholesale_retail, record.transport_storage_communication,
                record.other_activities, record.mining_manufacturing_utilities,
            ),
        )
        # save the new id now: the exchange-rate insert below changes lastrowid
        record_id = cursor.lastrowid

        # insert exchange rates when provided
        if record.ama_exchange_rate is not None or record.imf_exchange_rate is not None:
            cursor.execute(
                """
                INSERT INTO exchange_rates
                    (country_id, year, ama_exchange_rate, imf_based_exchange_rate)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    ama_exchange_rate      = VALUES(ama_exchange_rate),
                    imf_based_exchange_rate = VALUES(imf_based_exchange_rate)
                """,
                (country_id, record.year,
                 record.ama_exchange_rate, record.imf_exchange_rate),
            )

        conn.commit()
        return {
            "message": "Record created",
            "id": record_id,
            "country": record.country_name,
            "year": record.year,
        }
    except mysql.connector.Error as err:
        conn.rollback()
        # economic_indicators has a unique key on (country_id, year)
        if err.errno == errorcode.ER_DUP_ENTRY:
            raise HTTPException(
                status_code=409,
                detail=f"A record for {record.country_name} {record.year} already exists",
            )
        raise HTTPException(status_code=400, detail=str(err))
    finally:
        cursor.close()
        conn.close()


# ---- READ: all records for a country ------------------------------
@app.get("/api/sql/records")
def sql_get_records(
    country: str = Query(..., description="Country name, e.g. United States"),
):
    """Get all economic records for a country from MySQL."""
    conn = _get_mysql()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            _SQL_SELECT + " WHERE LOWER(c.country_name) = LOWER(%s) ORDER BY ei.year",
            (country.strip(),),
        )
        rows = cursor.fetchall()
        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No records found for country: {country}",
            )
        return {"country": country, "count": len(rows), "data": rows}
    finally:
        cursor.close()
        conn.close()


# ---- READ: latest record ------------------------------------------
@app.get("/api/sql/records/latest")
def sql_get_latest(
    country: str = Query(..., description="Country name, e.g. United States"),
):
    """Get the most recent record for a country from MySQL."""
    conn = _get_mysql()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            _SQL_SELECT
            + " WHERE LOWER(c.country_name) = LOWER(%s) ORDER BY ei.year DESC LIMIT 1",
            (country.strip(),),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"No records found for country: {country}",
            )
        return {"country": country, "data": row}
    finally:
        cursor.close()
        conn.close()


# ---- READ: records by date range -----------------------------------
@app.get("/api/sql/records/range")
def sql_get_range(
    country: str = Query(..., description="Country name, e.g. United States"),
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
):
    """Get records within a date range from MySQL. Records are annual: every year that overlaps the range is returned."""
    start_year, end_year = _years_in_range(start_date, end_date)

    conn = _get_mysql()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            _SQL_SELECT
            + " WHERE LOWER(c.country_name) = LOWER(%s)"
            "   AND ei.year BETWEEN %s AND %s"
            " ORDER BY ei.year",
            (country.strip(), start_year, end_year),
        )
        rows = cursor.fetchall()
        if not rows:
            raise HTTPException(
                status_code=404,
                detail="No records in the specified date range",
            )
        return {
            "country": country,
            "start_date": start_date,
            "end_date": end_date,
            "count": len(rows),
            "data": rows,
        }
    finally:
        cursor.close()
        conn.close()


# ---- UPDATE --------------------------------------------------------
@app.put("/api/sql/records/{record_id}")
def sql_update_record(record_id: int, updates: EconomicRecordUpdate):
    """Update an existing economic record in MySQL."""
    update_dict = updates.model_dump(exclude_none=True)
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")

    conn = _get_mysql()
    cursor = conn.cursor()
    try:
        # Check that the record exists before updating it: MySQL reports 0 changed
        # rows both for a missing id and for an update that changes nothing
        cursor.execute(
            "SELECT country_id, year FROM economic_indicators WHERE id = %s",
            (record_id,),
        )
        ref = cursor.fetchone()
        if not ref:
            raise HTTPException(
                status_code=404, detail=f"Record {record_id} not found"
            )
        country_id, year = ref
        modified = 0

        # fields that live in economic_indicators
        ei_fields = [
            "population", "per_capita_gni", "gdp", "gni_usd", "exports", "imports",
            "final_consumption_expenditure", "government_consumption",
            "household_consumption", "gross_capital_formation",
            "gross_fixed_capital_formation",
        ]
        ei_updates = {k: v for k, v in update_dict.items() if k in ei_fields}
        if ei_updates:
            ei_sets = ", ".join(f"{column} = %s" for column in ei_updates)
            cursor.execute(
                f"UPDATE economic_indicators SET {ei_sets} WHERE id = %s",
                [*ei_updates.values(), record_id],
            )
            modified += cursor.rowcount

        # fields that live in exchange_rates. The year may have no exchange-rate
        # row yet, so insert one, or update only the given rates if it has
        er_columns = {
            "ama_exchange_rate": "ama_exchange_rate",
            "imf_exchange_rate": "imf_based_exchange_rate",
        }
        er_updates = {er_columns[k]: v for k, v in update_dict.items() if k in er_columns}
        if er_updates:
            columns = ", ".join(er_updates)
            placeholders = ", ".join(["%s"] * len(er_updates))
            er_sets = ", ".join(f"{column} = VALUES({column})" for column in er_updates)
            cursor.execute(
                f"INSERT INTO exchange_rates (country_id, year, {columns}) "
                f"VALUES (%s, %s, {placeholders}) "
                f"ON DUPLICATE KEY UPDATE {er_sets}",
                [country_id, year, *er_updates.values()],
            )
            # rowcount: 1 = row inserted, 2 = row updated, 0 = values unchanged
            modified += cursor.rowcount

        conn.commit()
        modified = int(modified > 0)
        return {"message": _update_message(modified), "id": record_id, "modified": modified}
    except mysql.connector.Error as err:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(err))
    finally:
        cursor.close()
        conn.close()


# ---- DELETE --------------------------------------------------------
@app.delete("/api/sql/records/{record_id}")
def sql_delete_record(record_id: int):
    """Delete an economic record from MySQL."""
    conn = _get_mysql()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT country_id, year FROM economic_indicators WHERE id = %s",
            (record_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=404, detail=f"Record {record_id} not found"
            )

        country_id, year = row
        # remove matching exchange_rates row first
        cursor.execute(
            "DELETE FROM exchange_rates WHERE country_id = %s AND year = %s",
            (country_id, year),
        )
        cursor.execute(
            "DELETE FROM economic_indicators WHERE id = %s", (record_id,)
        )
        conn.commit()
        return {"message": "Record deleted", "id": record_id}
    except mysql.connector.Error as err:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(err))
    finally:
        cursor.close()
        conn.close()


# ═════════════════════════════════════════════════════════
#  MongoDB CRUD ENDPOINTS
# ═════════════════════════════════════════════════════════

def _mongo_country_regex(name: str):
    """Case-insensitive exact-match regex filter for country_name."""
    return {"$regex": f"^{re.escape(name.strip())}$", "$options": "i"}


# ---- CREATE --------------------------------------------------------
@app.post("/api/mongodb/records", status_code=201)
def mongo_create_record(record: EconomicRecordCreate):
    """Insert a new economic record into MongoDB."""
    collection = _get_mongo()
    doc = {
        "country_name": record.country_name,
        "currency": record.currency,
        "year": record.year,
        "exchange_rates": {
            "ama_exchange_rate": record.ama_exchange_rate,
            "imf_based_exchange_rate": record.imf_exchange_rate,
        },
        "demographics": {
            "population": record.population,
            "per_capita_gni": record.per_capita_gni,
        },
        "economic_indicators": {
            "gdp": record.gdp,
            "gni_usd": record.gni_usd,
            "exports": record.exports,
            "imports": record.imports,
            "final_consumption_expenditure": record.final_consumption_expenditure,
            "government_consumption": record.government_consumption,
            "household_consumption": record.household_consumption,
            "gross_capital_formation": record.gross_capital_formation,
            "gross_fixed_capital_formation": record.gross_fixed_capital_formation,
            "changes_in_inventories": record.changes_in_inventories,
        },
        "sector_breakdown": {
            "agriculture": record.agriculture,
            "manufacturing": record.manufacturing,
            "construction": record.construction,
            "wholesale_retail": record.wholesale_retail,
            "transport_storage_communication": record.transport_storage_communication,
            "other_activities": record.other_activities,
            "mining_manufacturing_utilities": record.mining_manufacturing_utilities,
            "total_value_added": record.total_value_added,
        },
    }
    # One record per country and year. The unique index rejects exact duplicates;
    # this check also catches the same country written in a different case
    duplicate = collection.find_one({
        "country_name": _mongo_country_regex(record.country_name),
        "year": record.year,
    })
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail=f"A record for {record.country_name} {record.year} already exists",
        )
    try:
        result = collection.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail=f"A record for {record.country_name} {record.year} already exists",
        )
    return {
        "message": "Record created",
        "id": str(result.inserted_id),
        "country": record.country_name,
        "year": record.year,
    }


# ---- READ: all records for a country ------------------------------
@app.get("/api/mongodb/records")
def mongo_get_records(
    country: str = Query(..., description="Country name, e.g. United States"),
):
    """Get all economic records for a country from MongoDB."""
    collection = _get_mongo()
    docs = list(
        collection.find({"country_name": _mongo_country_regex(country)})
        .sort("year", 1)
    )
    if not docs:
        raise HTTPException(
            status_code=404,
            detail=f"No records found for country: {country}",
        )
    return {
        "country": country,
        "count": len(docs),
        "data": [_flatten_mongo(d) for d in docs],
    }


# ---- READ: latest record ------------------------------------------
@app.get("/api/mongodb/records/latest")
def mongo_get_latest(
    country: str = Query(..., description="Country name, e.g. United States"),
):
    """Get the most recent record for a country from MongoDB."""
    collection = _get_mongo()
    doc = collection.find_one(
        {"country_name": _mongo_country_regex(country)},
        sort=[("year", -1)],
    )
    if not doc:
        raise HTTPException(
            status_code=404,
            detail=f"No records found for country: {country}",
        )
    return {"country": country, "data": _flatten_mongo(doc)}


# ---- READ: records by date range -----------------------------------
@app.get("/api/mongodb/records/range")
def mongo_get_range(
    country: str = Query(..., description="Country name, e.g. United States"),
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
):
    """Get records within a date range from MongoDB. Records are annual: every year that overlaps the range is returned."""
    start_year, end_year = _years_in_range(start_date, end_date)

    collection = _get_mongo()
    docs = list(
        collection.find({
            "country_name": _mongo_country_regex(country),
            "year": {"$gte": start_year, "$lte": end_year},
        }).sort("year", 1)
    )
    if not docs:
        raise HTTPException(
            status_code=404,
            detail="No records in the specified date range",
        )
    return {
        "country": country,
        "start_date": start_date,
        "end_date": end_date,
        "count": len(docs),
        "data": [_flatten_mongo(d) for d in docs],
    }


# ---- UPDATE --------------------------------------------------------
@app.put("/api/mongodb/records/{record_id}")
def mongo_update_record(record_id: str, updates: EconomicRecordUpdate):
    """Update an existing economic record in MongoDB."""
    collection = _get_mongo()

    try:
        obj_id = ObjectId(record_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid record ID format")

    update_dict = updates.model_dump(exclude_none=True)
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")

    # map flat field names to the nested MongoDB document paths
    field_map = {
        "population": "demographics.population",
        "per_capita_gni": "demographics.per_capita_gni",
        "gdp": "economic_indicators.gdp",
        "gni_usd": "economic_indicators.gni_usd",
        "exports": "economic_indicators.exports",
        "imports": "economic_indicators.imports",
        "final_consumption_expenditure": "economic_indicators.final_consumption_expenditure",
        "government_consumption": "economic_indicators.government_consumption",
        "household_consumption": "economic_indicators.household_consumption",
        "gross_capital_formation": "economic_indicators.gross_capital_formation",
        "gross_fixed_capital_formation": "economic_indicators.gross_fixed_capital_formation",
        "ama_exchange_rate": "exchange_rates.ama_exchange_rate",
        "imf_exchange_rate": "exchange_rates.imf_based_exchange_rate",
    }
    mongo_set = {field_map.get(k, k): v for k, v in update_dict.items()}

    result = collection.update_one({"_id": obj_id}, {"$set": mongo_set})
    # matched_count says whether the record exists, modified_count whether anything changed
    if result.matched_count == 0:
        raise HTTPException(
            status_code=404, detail=f"Record {record_id} not found"
        )
    return {
        "message": _update_message(result.modified_count),
        "id": record_id,
        "modified": result.modified_count,
    }


# ---- DELETE --------------------------------------------------------
@app.delete("/api/mongodb/records/{record_id}")
def mongo_delete_record(record_id: str):
    """Delete an economic record from MongoDB."""
    collection = _get_mongo()

    try:
        obj_id = ObjectId(record_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid record ID format")

    result = collection.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404, detail=f"Record {record_id} not found"
        )
    return {"message": "Record deleted", "id": record_id}
