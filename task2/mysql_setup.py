# Task 2 - MySQL Setup
# This script sets up our MySQL database for the Global Economy Indicators dataset
# It creates 3 tables, loads the CSV data, and runs some queries

import os
import sys
from pathlib import Path

import pandas as pd
import mysql.connector
from dotenv import load_dotenv

# settings come from the .env file in the project root (copy .env.example to .env)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

DB_HOST = os.getenv('MYSQL_HOST', 'localhost')
DB_PORT = int(os.getenv('MYSQL_PORT', '3306'))
DB_USER = os.getenv('MYSQL_USER', 'root')
DB_PASSWORD = os.getenv('MYSQL_PASSWORD', '')
DB_NAME = os.getenv('MYSQL_DB', 'global_economy_db')
CSV_PATH = BASE_DIR / 'data' / 'Global Economy Indicators.csv'


# ---- creating the database and tables ----

print("Creating database and tables...")

try:
    conn = mysql.connector.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD)
except mysql.connector.Error as err:
    sys.exit(f"Could not connect to MySQL at {DB_HOST}:{DB_PORT} as '{DB_USER}': {err}\n"
             "Check that MySQL is running and that MYSQL_USER / MYSQL_PASSWORD in .env are correct.")
cursor = conn.cursor()

cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}`")
cursor.execute(f"USE `{DB_NAME}`")

# first table - just the basic country info like name and currency
cursor.execute("""
    CREATE TABLE IF NOT EXISTS countries (
        country_id INT PRIMARY KEY,
        country_name VARCHAR(100) NOT NULL,
        currency VARCHAR(50)
    )
""")

# second table - exchange rates separated from the main economic data
cursor.execute("""
    CREATE TABLE IF NOT EXISTS exchange_rates (
        id INT AUTO_INCREMENT PRIMARY KEY,
        country_id INT NOT NULL,
        year INT NOT NULL,
        ama_exchange_rate DOUBLE,
        imf_based_exchange_rate DOUBLE,
        FOREIGN KEY (country_id) REFERENCES countries(country_id),
        UNIQUE KEY unique_country_year (country_id, year)
    )
""")

# third table - all the economic indicators (GDP, population, exports etc)
cursor.execute("""
    CREATE TABLE IF NOT EXISTS economic_indicators (
        id INT AUTO_INCREMENT PRIMARY KEY,
        country_id INT NOT NULL,
        year INT NOT NULL,
        population BIGINT,
        per_capita_gni DOUBLE,
        agriculture DOUBLE,
        changes_in_inventories DOUBLE,
        construction DOUBLE,
        exports DOUBLE,
        final_consumption_expenditure DOUBLE,
        government_consumption DOUBLE,
        gross_capital_formation DOUBLE,
        gross_fixed_capital_formation DOUBLE,
        household_consumption DOUBLE,
        imports DOUBLE,
        manufacturing DOUBLE,
        mining_manufacturing_utilities DOUBLE,
        other_activities DOUBLE,
        total_value_added DOUBLE,
        transport_storage_communication DOUBLE,
        wholesale_retail DOUBLE,
        gni_usd DOUBLE,
        gdp DOUBLE,
        FOREIGN KEY (country_id) REFERENCES countries(country_id),
        UNIQUE KEY unique_country_year (country_id, year)
    )
""")

conn.commit()
print("Tables created!\n")


# ---- loading data from the csv ----

print("Loading data from CSV...")

df = pd.read_csv(CSV_PATH)
# cleaning up whitespace in column names and country names
df.columns = df.columns.str.strip()
df['Country'] = df['Country'].str.strip()
df['Currency'] = df['Currency'].str.strip()

# small helper so we dont crash on missing values
def safe_float(val):
    return None if pd.isna(val) else float(val)

# insert countries first since the other tables reference them
countries = df[['CountryID', 'Country', 'Currency']].drop_duplicates(subset='CountryID')
for _, row in countries.iterrows():
    cursor.execute(
        "INSERT IGNORE INTO countries (country_id, country_name, currency) VALUES (%s, %s, %s)",
        (int(row['CountryID']), row['Country'], row['Currency'])
    )

# insert exchange rates
for _, row in df.iterrows():
    cursor.execute(
        "INSERT IGNORE INTO exchange_rates (country_id, year, ama_exchange_rate, imf_based_exchange_rate) VALUES (%s, %s, %s, %s)",
        (int(row['CountryID']), int(row['Year']),
         safe_float(row['AMA exchange rate']),
         safe_float(row['IMF based exchange rate']))
    )

# insert economic indicators - this one has a lot of columns
for _, row in df.iterrows():
    cursor.execute("""
        INSERT IGNORE INTO economic_indicators
        (country_id, year, population, per_capita_gni, agriculture, changes_in_inventories,
         construction, exports, final_consumption_expenditure, government_consumption,
         gross_capital_formation, gross_fixed_capital_formation, household_consumption,
         imports, manufacturing, mining_manufacturing_utilities, other_activities,
         total_value_added, transport_storage_communication, wholesale_retail, gni_usd, gdp)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        int(row['CountryID']),
        int(row['Year']),
        safe_float(row['Population']),
        safe_float(row['Per capita GNI']),
        safe_float(row['Agriculture, hunting, forestry, fishing (ISIC A-B)']),
        safe_float(row['Changes in inventories']),
        safe_float(row['Construction (ISIC F)']),
        safe_float(row['Exports of goods and services']),
        safe_float(row['Final consumption expenditure']),
        safe_float(row['General government final consumption expenditure']),
        safe_float(row['Gross capital formation']),
        safe_float(row['Gross fixed capital formation (including Acquisitions less disposals of valuables)']),
        safe_float(row['Household consumption expenditure (including Non-profit institutions serving households)']),
        safe_float(row['Imports of goods and services']),
        safe_float(row['Manufacturing (ISIC D)']),
        safe_float(row['Mining, Manufacturing, Utilities (ISIC C-E)']),
        safe_float(row['Other Activities (ISIC J-P)']),
        safe_float(row['Total Value Added']),
        safe_float(row['Transport, storage and communication (ISIC I)']),
        safe_float(row['Wholesale, retail trade, restaurants and hotels (ISIC G-H)']),
        safe_float(row['Gross National Income(GNI) in USD']),
        safe_float(row['Gross Domestic Product (GDP)'])
    ))

conn.commit()
print(f"Done! Loaded {len(countries)} countries and {len(df)} records.\n")


# ---- running queries ----

# query 1 - which countries had the highest GDP in the latest year?
print("=" * 60)
print("QUERY 1: Top 10 Countries by GDP (2021)")
print("=" * 60)

cursor.execute("""
    SELECT c.country_name, e.year, e.gdp
    FROM economic_indicators e
    JOIN countries c ON e.country_id = c.country_id
    WHERE e.year = (SELECT MAX(year) FROM economic_indicators)
      AND e.gdp IS NOT NULL
    ORDER BY e.gdp DESC
    LIMIT 10
""")

for row in cursor.fetchall():
    print(f"  {row[0]:<30} {row[1]}   GDP: {row[2]:,.0f}")


# query 2 - how did the US economy look from 2015 to 2021?
print("\n" + "=" * 60)
print("QUERY 2: US Economic Indicators (2015-2021)")
print("=" * 60)

cursor.execute("""
    SELECT c.country_name, e.year, e.gdp, e.exports, e.imports
    FROM economic_indicators e
    JOIN countries c ON e.country_id = c.country_id
    WHERE c.country_name = 'United States'
      AND e.year BETWEEN 2015 AND 2021
    ORDER BY e.year
""")

for row in cursor.fetchall():
    print(f"  {row[0]}  {row[1]}  GDP: {row[2]:,.0f}  Exports: {row[3]:,.0f}  Imports: {row[4]:,.0f}")


# query 3 - grouping countries by currency to see avg GDP
print("\n" + "=" * 60)
print("QUERY 3: Average GDP by Currency (Top 10 in 2021)")
print("=" * 60)

cursor.execute("""
    SELECT c.currency, ROUND(AVG(e.gdp), 0) AS avg_gdp, COUNT(*) AS num_countries
    FROM economic_indicators e
    JOIN countries c ON e.country_id = c.country_id
    WHERE e.year = 2021 AND e.gdp IS NOT NULL
    GROUP BY c.currency
    ORDER BY avg_gdp DESC
    LIMIT 10
""")

for row in cursor.fetchall():
    print(f"  {row[0]:<25}  Avg GDP: {row[1]:,.0f}  Countries: {row[2]}")


# query 4 - getting the most recent record for the US
print("\n" + "=" * 60)
print("QUERY 4: Latest Record for United States")
print("=" * 60)

cursor.execute("""
    SELECT c.country_name, e.year, e.gdp, e.population, e.per_capita_gni
    FROM economic_indicators e
    JOIN countries c ON e.country_id = c.country_id
    WHERE c.country_name = 'United States'
    ORDER BY e.year DESC
    LIMIT 1
""")

row = cursor.fetchone()
print(f"  Country: {row[0]}")
print(f"  Year: {row[1]}")
print(f"  GDP: {row[2]:,.0f}")
print(f"  Population: {row[3]:,}")
print(f"  GNI per Capita: {row[4]:,.0f}")


# query 5 - joining all 3 tables to see GDP alongside exchange rates over time
print("\n" + "=" * 60)
print("QUERY 5: GDP and Exchange Rates (US over decades)")
print("=" * 60)

cursor.execute("""
    SELECT c.country_name, e.year, e.gdp, er.ama_exchange_rate
    FROM economic_indicators e
    JOIN countries c ON e.country_id = c.country_id
    JOIN exchange_rates er ON e.country_id = er.country_id AND e.year = er.year
    WHERE c.country_name = 'United States'
      AND e.year IN (1970, 1980, 1990, 2000, 2010, 2021)
    ORDER BY e.year
""")

for row in cursor.fetchall():
    print(f"  {row[1]}  GDP: {row[2]:,.0f}  Exchange Rate: {row[3]}")


cursor.close()
conn.close()
print("\nAll MySQL queries completed.")
