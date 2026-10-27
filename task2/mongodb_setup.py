# Task 2 - MongoDB Setup
# Setting up MongoDB for our Global Economy Indicators dataset
# Using a single collection with embedded documents instead of separate tables

import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import json

# connection settings come from the .env file in the project root (copy .env.example to .env)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
DB_NAME = os.getenv('MONGO_DB', 'global_economy_db')
COLLECTION_NAME = 'economic_records'
CSV_PATH = BASE_DIR / 'Global Economy Indicators.csv'


# ---- connect and load data ----

print("Connecting to MongoDB...")
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
try:
    client.server_info()
except PyMongoError as err:
    sys.exit(f"Could not connect to MongoDB at {MONGO_URI}: {err}\n"
             "Check that MongoDB is running and that MONGO_URI in .env is correct.")
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

# start fresh
collection.drop()

print("Loading data from CSV...")
df = pd.read_csv(CSV_PATH)
df.columns = df.columns.str.strip()
df['Country'] = df['Country'].str.strip()
df['Currency'] = df['Currency'].str.strip()

# helpers for handling missing values
def safe_float(val):
    return None if pd.isna(val) else float(val)

def safe_int(val):
    return None if pd.isna(val) else int(val)

# building documents - each row becomes one document with nested fields
# this is different from SQL where we split into 3 tables
documents = []
for _, row in df.iterrows():
    doc = {
        "country_id": int(row['CountryID']),
        "country_name": row['Country'],
        "currency": row['Currency'],
        "year": int(row['Year']),
        # grouping exchange rates together
        "exchange_rates": {
            "ama_exchange_rate": safe_float(row['AMA exchange rate']),
            "imf_based_exchange_rate": safe_float(row['IMF based exchange rate']),
        },
        # population and income info
        "demographics": {
            "population": safe_int(row['Population']),
            "per_capita_gni": safe_float(row['Per capita GNI']),
        },
        # main economic numbers
        "economic_indicators": {
            "gdp": safe_float(row['Gross Domestic Product (GDP)']),
            "gni_usd": safe_float(row['Gross National Income(GNI) in USD']),
            "exports": safe_float(row['Exports of goods and services']),
            "imports": safe_float(row['Imports of goods and services']),
            "final_consumption_expenditure": safe_float(row['Final consumption expenditure']),
            "government_consumption": safe_float(row['General government final consumption expenditure']),
            "household_consumption": safe_float(row['Household consumption expenditure (including Non-profit institutions serving households)']),
            "gross_capital_formation": safe_float(row['Gross capital formation']),
            "gross_fixed_capital_formation": safe_float(row['Gross fixed capital formation (including Acquisitions less disposals of valuables)']),
            "changes_in_inventories": safe_float(row['Changes in inventories']),
        },
        # breaking down GDP by sector
        "sector_breakdown": {
            "agriculture": safe_float(row['Agriculture, hunting, forestry, fishing (ISIC A-B)']),
            "manufacturing": safe_float(row['Manufacturing (ISIC D)']),
            "mining_manufacturing_utilities": safe_float(row['Mining, Manufacturing, Utilities (ISIC C-E)']),
            "construction": safe_float(row['Construction (ISIC F)']),
            "transport_storage_communication": safe_float(row['Transport, storage and communication (ISIC I)']),
            "wholesale_retail": safe_float(row['Wholesale, retail trade, restaurants and hotels (ISIC G-H)']),
            "other_activities": safe_float(row['Other Activities (ISIC J-P)']),
            "total_value_added": safe_float(row['Total Value Added']),
        }
    }
    documents.append(doc)

collection.insert_many(documents)
print(f"Inserted {len(documents)} documents.")

# adding indexes so queries run faster
collection.create_index([("country_name", 1), ("year", 1)])
collection.create_index([("year", -1)])
print("Indexes created.\n")


# ---- sample documents ----

print("=" * 60)
print("SAMPLE DOCUMENTS")
print("=" * 60)

# showing first 2 docs so we can see the structure
for doc in collection.find().limit(2):
    doc['_id'] = str(doc['_id'])
    print(json.dumps(doc, indent=2))
    print()


# ---- queries ----

# query 1 - top countries by GDP, similar to what we did in SQL
print("=" * 60)
print("QUERY 1: Top 10 Countries by GDP (2021)")
print("=" * 60)

results = collection.find(
    {"year": 2021, "economic_indicators.gdp": {"$ne": None}},
    {"_id": 0, "country_name": 1, "economic_indicators.gdp": 1}
).sort("economic_indicators.gdp", -1).limit(10)

for doc in results:
    print(f"  {doc['country_name']:<30}  GDP: {doc['economic_indicators']['gdp']:,.0f}")


# query 2 - filtering by date range for the US
print("\n" + "=" * 60)
print("QUERY 2: US Records by Date Range (2015-2021)")
print("=" * 60)

results = collection.find(
    {"country_name": "United States", "year": {"$gte": 2015, "$lte": 2021}},
    {"_id": 0, "year": 1, "economic_indicators.gdp": 1, "economic_indicators.exports": 1, "demographics.population": 1}
).sort("year", 1)

for doc in results:
    print(f"  {doc['year']}  GDP: {doc['economic_indicators']['gdp']:,.0f}  "
          f"Exports: {doc['economic_indicators']['exports']:,.0f}  "
          f"Population: {doc['demographics']['population']:,}")


# query 3 - using aggregation to count how many records each country has
print("\n" + "=" * 60)
print("QUERY 3: Records per Country (Top 10)")
print("=" * 60)

pipeline = [
    {"$group": {"_id": "$country_name", "record_count": {"$sum": 1}}},
    {"$sort": {"record_count": -1}},
    {"$limit": 10}
]

for doc in collection.aggregate(pipeline):
    print(f"  {doc['_id']:<30}  Records: {doc['record_count']}")


# query 4 - getting the latest record for the US
print("\n" + "=" * 60)
print("QUERY 4: Latest Record for United States")
print("=" * 60)

latest = collection.find_one(
    {"country_name": "United States"},
    {"_id": 0},
    sort=[("year", -1)]
)

if latest:
    print(f"  Country: {latest['country_name']}")
    print(f"  Year: {latest['year']}")
    print(f"  GDP: {latest['economic_indicators']['gdp']:,.0f}")
    print(f"  Population: {latest['demographics']['population']:,}")
    print(f"  GNI per Capita: {latest['demographics']['per_capita_gni']:,.0f}")


# query 5 - aggregation to find avg GNI per capita grouped by currency
print("\n" + "=" * 60)
print("QUERY 5: Avg GNI per Capita by Currency (Top 10, 2021)")
print("=" * 60)

pipeline = [
    {"$match": {"year": 2021, "demographics.per_capita_gni": {"$ne": None}}},
    {"$group": {
        "_id": "$currency",
        "avg_gni": {"$avg": "$demographics.per_capita_gni"},
        "num_countries": {"$sum": 1}
    }},
    {"$sort": {"avg_gni": -1}},
    {"$limit": 10}
]

for doc in collection.aggregate(pipeline):
    print(f"  {doc['_id']:<25}  Avg GNI/Capita: {doc['avg_gni']:,.0f}  Countries: {doc['num_countries']}")


client.close()
print("\nAll MongoDB queries completed.")
