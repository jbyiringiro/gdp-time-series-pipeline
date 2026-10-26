-- ============================================================
-- Global Economy Indicators - Relational Database Schema
-- Database: global_economy_db
-- ============================================================

CREATE DATABASE IF NOT EXISTS global_economy_db;
USE global_economy_db;

-- ============================================================
-- Table 1: countries
-- Stores static country information (normalized from the dataset)
-- ============================================================
CREATE TABLE IF NOT EXISTS countries (
    country_id INT PRIMARY KEY,
    country_name VARCHAR(100) NOT NULL,
    currency VARCHAR(50)
);

-- ============================================================
-- Table 2: exchange_rates
-- Stores yearly exchange rate data per country
-- Separated from economic indicators because exchange rates
-- are financial/monetary data, distinct from real economy metrics
-- ============================================================
CREATE TABLE IF NOT EXISTS exchange_rates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    country_id INT NOT NULL,
    year INT NOT NULL,
    ama_exchange_rate DOUBLE,
    imf_based_exchange_rate DOUBLE,
    FOREIGN KEY (country_id) REFERENCES countries(country_id),
    UNIQUE KEY unique_country_year (country_id, year)
);

-- ============================================================
-- Table 3: economic_indicators
-- Stores all yearly macroeconomic indicators per country
-- This is the core time-series data table
-- ============================================================
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
);

-- ============================================================
-- Indexes for query performance on time-series operations
-- ============================================================
CREATE INDEX idx_economic_year ON economic_indicators(year);
CREATE INDEX idx_economic_country_year ON economic_indicators(country_id, year);
CREATE INDEX idx_exchange_year ON exchange_rates(year);
