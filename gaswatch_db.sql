-- GasWatch | Metro Manila gasoline monitoring
-- Import into XAMPP/phpMyAdmin after creating the database, or run: mysql -u root -p < gaswatch_db.sql
CREATE DATABASE IF NOT EXISTS gaswatch_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE gaswatch_db;

-- D1 One administrator only. Public visitors do not need accounts.
CREATE TABLE IF NOT EXISTS users (
 user_id INT AUTO_INCREMENT PRIMARY KEY,
 username VARCHAR(80) NOT NULL UNIQUE,
 password VARCHAR(255) NOT NULL,
 role ENUM('admin','user') NOT NULL DEFAULT 'admin',
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- D2 Gas stations. City is a filter only; no address, map, or coordinates.
CREATE TABLE IF NOT EXISTS gas_stations (
 station_id INT AUTO_INCREMENT PRIMARY KEY,
 station_name VARCHAR(100) NOT NULL,
 brand VARCHAR(50) NOT NULL,
 city VARCHAR(100) NOT NULL,
 status ENUM('active','inactive') NOT NULL DEFAULT 'active',
 INDEX idx_station_city(city),
 INDEX idx_station_brand(brand)
) ENGINE=InnoDB;

-- D3 Fuel types
CREATE TABLE IF NOT EXISTS fuel_types (
 fuel_id INT AUTO_INCREMENT PRIMARY KEY,
 fuel_name VARCHAR(50) NOT NULL UNIQUE,
 description VARCHAR(255) NULL
) ENGINE=InnoDB;

-- D4 Current, station-specific fuel prices
CREATE TABLE IF NOT EXISTS fuel_prices (
 price_id INT AUTO_INCREMENT PRIMARY KEY,
 station_id INT NOT NULL,
 fuel_id INT NOT NULL,
 price_per_liter DECIMAL(10,2) NOT NULL,
 CONSTRAINT chk_current_nonnegative CHECK (price_per_liter >= 0),
 updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_by INT NOT NULL,
 CONSTRAINT uq_current_station_fuel UNIQUE(station_id, fuel_id),
 CONSTRAINT fk_current_station FOREIGN KEY (station_id) REFERENCES gas_stations(station_id),
 CONSTRAINT fk_current_fuel FOREIGN KEY (fuel_id) REFERENCES fuel_types(fuel_id),
 CONSTRAINT fk_current_editor FOREIGN KEY (updated_by) REFERENCES users(user_id)
) ENGINE=InnoDB;

-- D5 Immutable station-price history
CREATE TABLE IF NOT EXISTS price_history (
 history_id INT AUTO_INCREMENT PRIMARY KEY,
 station_id INT NOT NULL,
 fuel_id INT NOT NULL,
 price_per_liter DECIMAL(10,2) NOT NULL,
 CONSTRAINT chk_history_nonnegative CHECK (price_per_liter >= 0),
 recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 recorded_by INT NOT NULL,
 CONSTRAINT fk_history_station FOREIGN KEY (station_id) REFERENCES gas_stations(station_id),
 CONSTRAINT fk_history_fuel FOREIGN KEY (fuel_id) REFERENCES fuel_types(fuel_id),
 CONSTRAINT fk_history_editor FOREIGN KEY (recorded_by) REFERENCES users(user_id),
 INDEX idx_station_fuel_time(station_id, fuel_id, recorded_at)
) ENGINE=InnoDB;

-- Supporting tables: DOE PDF monitors city/brand-level RANGES, not identifiable station prices.
CREATE TABLE IF NOT EXISTS pdf_import_batches (
 import_id INT AUTO_INCREMENT PRIMARY KEY,
 source_filename VARCHAR(255) NOT NULL,
 file_sha256 CHAR(64) NOT NULL,
 week_start DATE NOT NULL,
 week_end DATE NOT NULL,
 uploaded_by INT NOT NULL,
 imported_rows INT NOT NULL DEFAULT 0,
 imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT fk_import_user FOREIGN KEY (uploaded_by) REFERENCES users(user_id),
 INDEX idx_import_week(week_start,week_end)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS regional_prices (
 regional_id INT AUTO_INCREMENT PRIMARY KEY,
 import_id INT NOT NULL,
 week_start DATE NOT NULL,
 week_end DATE NOT NULL,
 city VARCHAR(100) NOT NULL,
 brand VARCHAR(50) NOT NULL,
 fuel_id INT NOT NULL,
 min_price DECIMAL(10,2) NOT NULL,
 max_price DECIMAL(10,2) NOT NULL,
 common_price DECIMAL(10,2) NULL,
 CONSTRAINT chk_regional_range CHECK (min_price >= 0 AND max_price >= min_price),
 CONSTRAINT chk_regional_common CHECK (common_price IS NULL OR (common_price >= min_price AND common_price <= max_price)),
 updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 UNIQUE KEY uq_region_week(week_start, week_end, city, brand, fuel_id),
 CONSTRAINT fk_region_batch FOREIGN KEY(import_id) REFERENCES pdf_import_batches(import_id),
 CONSTRAINT fk_region_fuel FOREIGN KEY(fuel_id) REFERENCES fuel_types(fuel_id),
 INDEX idx_region_city_fuel(city, fuel_id, week_start),
 INDEX idx_region_brand(brand)
) ENGINE=InnoDB;

INSERT INTO fuel_types (fuel_name, description) VALUES
 ('RON 100','Gasoline, research octane number 100'),
 ('RON 97','Gasoline, research octane number 97'),
 ('RON 95','Gasoline, research octane number 95'),
 ('RON 91','Gasoline, research octane number 91'),
 ('DIESEL','Diesel fuel'),
 ('DIESEL PLUS','Premium diesel'),
 ('KEROSENE','Kerosene')
ON DUPLICATE KEY UPDATE fuel_name=VALUES(fuel_name);

-- Upgrade legacy GasWatch installations: remove the old map/address columns safely.
-- This intentionally removes those fields; run a database backup first if retaining old addresses matters.
SET @ddl = (SELECT IF(COUNT(*)>0, 'ALTER TABLE gas_stations DROP COLUMN latitude', 'SELECT 1')
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='gas_stations' AND COLUMN_NAME='latitude');
PREPARE gaswatch_upgrade FROM @ddl;
EXECUTE gaswatch_upgrade;
DEALLOCATE PREPARE gaswatch_upgrade;
SET @ddl = (SELECT IF(COUNT(*)>0, 'ALTER TABLE gas_stations DROP COLUMN longitude', 'SELECT 1')
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='gas_stations' AND COLUMN_NAME='longitude');
PREPARE gaswatch_upgrade FROM @ddl;
EXECUTE gaswatch_upgrade;
DEALLOCATE PREPARE gaswatch_upgrade;
SET @ddl = (SELECT IF(COUNT(*)>0, 'ALTER TABLE gas_stations DROP COLUMN address', 'SELECT 1')
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='gas_stations' AND COLUMN_NAME='address');
PREPARE gaswatch_upgrade FROM @ddl;
EXECUTE gaswatch_upgrade;
DEALLOCATE PREPARE gaswatch_upgrade;

-- Default account (only supported sign-in): admin / admin123.
-- Password is stored hashed, never in plaintext. Change ADMIN_PASSWORD in .env for deployment.
INSERT INTO users (username,password,role) VALUES ('admin','pbkdf2:sha256:600000$93f4279ab418863a63042f23$5a9b5273e6dd7f4f46257245a073d129efaacd9e8ffe3d6aa284791ca9e98e18','admin')
ON DUPLICATE KEY UPDATE password=VALUES(password), role='admin';
