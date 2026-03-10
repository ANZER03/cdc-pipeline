-- seed-postgres.sql
-- Rebuilds the Nexus application schema in nexus_db, seeds reference data,
-- and creates the CDC publication expected by Debezium.

\connect nexus_db

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DROP PUBLICATION IF EXISTS nexus_cdc_pub;
DROP PUBLICATION IF EXISTS ebap_publication;

DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS cart_items CASCADE;
DROP TABLE IF EXISTS user_events CASCADE;
DROP TABLE IF EXISTS sessions CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS city_region_mapping CASCADE;
DROP TABLE IF EXISTS country_region_mapping CASCADE;

CREATE TABLE users (
    id              BIGSERIAL PRIMARY KEY,
    username        VARCHAR(100) NOT NULL,
    display_name    VARCHAR(200) NOT NULL,
    email           VARCHAR(255) UNIQUE NOT NULL,
    country_code    CHAR(2),
    city            VARCHAR(100),
    region_name     VARCHAR(100),
    platform        VARCHAR(50),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE products (
    id              BIGSERIAL PRIMARY KEY,
    name            VARCHAR(500) NOT NULL,
    category        VARCHAR(100),
    price           DECIMAL(10, 2) NOT NULL,
    merchant_region VARCHAR(100),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE orders (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT REFERENCES users(id),
    total_amount        DECIMAL(10, 2) NOT NULL,
    currency            CHAR(3) DEFAULT 'USD',
    status              VARCHAR(20) NOT NULL,
    region_name         VARCHAR(100),
    user_display_name   VARCHAR(200),
    platform            VARCHAR(50),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE order_items (
    id              BIGSERIAL PRIMARY KEY,
    order_id        BIGINT REFERENCES orders(id),
    product_id      BIGINT REFERENCES products(id),
    quantity        INTEGER NOT NULL DEFAULT 1,
    unit_price      DECIMAL(10, 2) NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE cart_items (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT REFERENCES users(id),
    product_id      BIGINT REFERENCES products(id),
    quantity        INTEGER NOT NULL DEFAULT 1,
    added_at        TIMESTAMPTZ DEFAULT NOW(),
    removed_at      TIMESTAMPTZ
);

CREATE TABLE user_events (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT REFERENCES users(id),
    event_type          VARCHAR(50) NOT NULL,
    page_url            TEXT,
    referrer_url        TEXT,
    user_agent          TEXT,
    ip_address          INET,
    session_id          UUID,
    metadata            JSONB,
    user_display_name   VARCHAR(200),
    region_name         VARCHAR(100),
    city                VARCHAR(100),
    country_code        CHAR(2),
    platform            VARCHAR(50),
    amount              DOUBLE PRECISION,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         BIGINT REFERENCES users(id),
    started_at      TIMESTAMPTZ NOT NULL,
    ended_at        TIMESTAMPTZ,
    platform        VARCHAR(50),
    country_code    CHAR(2),
    city            VARCHAR(100),
    region_name     VARCHAR(100),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE country_region_mapping (
    country_code    CHAR(2) NOT NULL PRIMARY KEY,
    region_name     VARCHAR(100) NOT NULL,
    longitude       DOUBLE PRECISION NOT NULL,
    latitude        DOUBLE PRECISION NOT NULL
);

CREATE TABLE city_region_mapping (
    id              BIGSERIAL PRIMARY KEY,
    country_code    CHAR(2) NOT NULL,
    city_pattern    VARCHAR(200) NOT NULL,
    region_name     VARCHAR(100) NOT NULL,
    longitude       DOUBLE PRECISION NOT NULL,
    latitude        DOUBLE PRECISION NOT NULL
);

CREATE INDEX idx_city_region_country ON city_region_mapping(country_code);

ALTER TABLE users REPLICA IDENTITY FULL;
ALTER TABLE products REPLICA IDENTITY FULL;
ALTER TABLE orders REPLICA IDENTITY FULL;
ALTER TABLE order_items REPLICA IDENTITY FULL;
ALTER TABLE cart_items REPLICA IDENTITY FULL;
ALTER TABLE user_events REPLICA IDENTITY FULL;
ALTER TABLE sessions REPLICA IDENTITY FULL;

INSERT INTO country_region_mapping (country_code, region_name, longitude, latitude) VALUES
    ('CA', 'North America (East)', -74, 40),
    ('GB', 'Western Europe', 2, 48),
    ('FR', 'Western Europe', 2, 48),
    ('DE', 'Western Europe', 2, 48),
    ('NL', 'Western Europe', 2, 48),
    ('IT', 'Western Europe', 2, 48),
    ('ES', 'Western Europe', 2, 48),
    ('JP', 'Japan', 139, 35),
    ('SG', 'Southeast Asia', 103, 1),
    ('MY', 'Southeast Asia', 103, 1),
    ('ID', 'Southeast Asia', 103, 1),
    ('VN', 'Southeast Asia', 103, 1),
    ('TH', 'Southeast Asia', 103, 1),
    ('PH', 'Southeast Asia', 103, 1),
    ('AU', 'Australia', 151, -33),
    ('NZ', 'Australia', 151, -33),
    ('BR', 'Brazil', -46, -23),
    ('AR', 'Brazil', -46, -23),
    ('CL', 'Brazil', -46, -23),
    ('IN', 'India', 77, 28),
    ('BD', 'India', 77, 28),
    ('PK', 'India', 77, 28),
    ('ZA', 'South Africa', 18, -33),
    ('KE', 'South Africa', 18, -33),
    ('NG', 'South Africa', 18, -33);

INSERT INTO city_region_mapping (id, country_code, city_pattern, region_name, longitude, latitude) VALUES
    (1, 'US', 'New York', 'North America (East)', -74, 40),
    (2, 'US', 'Boston', 'North America (East)', -74, 40),
    (3, 'US', 'Washington', 'North America (East)', -74, 40),
    (4, 'US', 'Atlanta', 'North America (East)', -74, 40),
    (5, 'US', 'Chicago', 'North America (East)', -74, 40),
    (6, 'US', 'Miami', 'North America (East)', -74, 40),
    (7, 'US', 'Los Angeles', 'North America (West)', -122, 37),
    (8, 'US', 'San Francisco', 'North America (West)', -122, 37),
    (9, 'US', 'Seattle', 'North America (West)', -122, 37),
    (10, 'US', 'Portland', 'North America (West)', -122, 37),
    (11, 'US', 'Denver', 'North America (West)', -122, 37),
    (12, 'US', 'Phoenix', 'North America (West)', -122, 37),
    (13, 'CA', 'Toronto', 'North America (East)', -74, 40),
    (14, 'CA', 'Vancouver', 'North America (West)', -122, 37);

INSERT INTO users (id, username, display_name, email, country_code, city, region_name, platform) VALUES
    (1, 'user-0001', 'Alex Mercer', 'alex.mercer@nexus.test', 'US', 'New York', 'North America (East)', 'Desktop'),
    (2, 'user-0002', 'Jordan Lee', 'jordan.lee@nexus.test', 'US', 'Boston', 'North America (East)', 'Mobile'),
    (3, 'user-0003', 'Casey Nguyen', 'casey.nguyen@nexus.test', 'US', 'Washington', 'North America (East)', 'iOS'),
    (4, 'user-0004', 'Sasha Patel', 'sasha.patel@nexus.test', 'US', 'Atlanta', 'North America (East)', 'Android'),
    (5, 'user-0005', 'Taylor Brooks', 'taylor.brooks@nexus.test', 'CA', 'Toronto', 'North America (East)', 'Desktop'),
    (6, 'user-0006', 'Jamie Carter', 'jamie.carter@nexus.test', 'US', 'Miami', 'North America (East)', 'Mobile'),
    (7, 'user-0007', 'Morgan Diaz', 'morgan.diaz@nexus.test', 'US', 'Los Angeles', 'North America (West)', 'Desktop'),
    (8, 'user-0008', 'Riley Chen', 'riley.chen@nexus.test', 'US', 'San Francisco', 'North America (West)', 'iOS'),
    (9, 'user-0009', 'Avery Kim', 'avery.kim@nexus.test', 'US', 'Seattle', 'North America (West)', 'Android'),
    (10, 'user-0010', 'Quinn Lopez', 'quinn.lopez@nexus.test', 'US', 'Portland', 'North America (West)', 'Mobile'),
    (11, 'user-0011', 'Parker Singh', 'parker.singh@nexus.test', 'US', 'Denver', 'North America (West)', 'Desktop'),
    (12, 'user-0012', 'Skyler Reed', 'skyler.reed@nexus.test', 'CA', 'Vancouver', 'North America (West)', 'iOS'),
    (13, 'user-0013', 'Harper Jones', 'harper.jones@nexus.test', 'GB', 'London', 'Western Europe', 'Desktop'),
    (14, 'user-0014', 'Rowan Schmidt', 'rowan.schmidt@nexus.test', 'DE', 'Berlin', 'Western Europe', 'Android'),
    (15, 'user-0015', 'Finley Martin', 'finley.martin@nexus.test', 'FR', 'Paris', 'Western Europe', 'Mobile'),
    (16, 'user-0016', 'Dakota Rossi', 'dakota.rossi@nexus.test', 'IT', 'Milan', 'Western Europe', 'Desktop'),
    (17, 'user-0017', 'Emerson Garcia', 'emerson.garcia@nexus.test', 'ES', 'Madrid', 'Western Europe', 'iOS'),
    (18, 'user-0018', 'Cameron Dubois', 'cameron.dubois@nexus.test', 'NL', 'Amsterdam', 'Western Europe', 'Mobile'),
    (19, 'user-0019', 'Yuki Tanaka', 'yuki.tanaka@nexus.test', 'JP', 'Tokyo', 'Japan', 'Mobile'),
    (20, 'user-0020', 'Haru Sato', 'haru.sato@nexus.test', 'JP', 'Osaka', 'Japan', 'iOS'),
    (21, 'user-0021', 'Ren Kobayashi', 'ren.kobayashi@nexus.test', 'JP', 'Yokohama', 'Japan', 'Desktop'),
    (22, 'user-0022', 'Mei Nakamura', 'mei.nakamura@nexus.test', 'JP', 'Nagoya', 'Japan', 'Android'),
    (23, 'user-0023', 'Sora Ito', 'sora.ito@nexus.test', 'JP', 'Sapporo', 'Japan', 'Mobile'),
    (24, 'user-0024', 'Wei Lim', 'wei.lim@nexus.test', 'SG', 'Singapore', 'Southeast Asia', 'Mobile'),
    (25, 'user-0025', 'Nur Aisyah', 'nur.aisyah@nexus.test', 'MY', 'Kuala Lumpur', 'Southeast Asia', 'Android'),
    (26, 'user-0026', 'Arif Rahman', 'arif.rahman@nexus.test', 'ID', 'Jakarta', 'Southeast Asia', 'Mobile'),
    (27, 'user-0027', 'Minh Tran', 'minh.tran@nexus.test', 'VN', 'Ho Chi Minh City', 'Southeast Asia', 'Desktop'),
    (28, 'user-0028', 'Pim Chaiwat', 'pim.chaiwat@nexus.test', 'TH', 'Bangkok', 'Southeast Asia', 'iOS'),
    (29, 'user-0029', 'Lian Santos', 'lian.santos@nexus.test', 'PH', 'Manila', 'Southeast Asia', 'Android'),
    (30, 'user-0030', 'Olivia Brown', 'olivia.brown@nexus.test', 'AU', 'Sydney', 'Australia', 'Mobile'),
    (31, 'user-0031', 'Noah Wilson', 'noah.wilson@nexus.test', 'AU', 'Melbourne', 'Australia', 'Desktop'),
    (32, 'user-0032', 'Chloe Evans', 'chloe.evans@nexus.test', 'AU', 'Brisbane', 'Australia', 'iOS'),
    (33, 'user-0033', 'Liam Taylor', 'liam.taylor@nexus.test', 'NZ', 'Auckland', 'Australia', 'Desktop'),
    (34, 'user-0034', 'Mia Harris', 'mia.harris@nexus.test', 'AU', 'Perth', 'Australia', 'Android'),
    (35, 'user-0035', 'Rafael Silva', 'rafael.silva@nexus.test', 'BR', 'Sao Paulo', 'Brazil', 'Mobile'),
    (36, 'user-0036', 'Beatriz Costa', 'beatriz.costa@nexus.test', 'BR', 'Rio de Janeiro', 'Brazil', 'Desktop'),
    (37, 'user-0037', 'Lucas Pereira', 'lucas.pereira@nexus.test', 'BR', 'Curitiba', 'Brazil', 'Android'),
    (38, 'user-0038', 'Sofia Almeida', 'sofia.almeida@nexus.test', 'AR', 'Buenos Aires', 'Brazil', 'Mobile'),
    (39, 'user-0039', 'Gabriel Rocha', 'gabriel.rocha@nexus.test', 'CL', 'Santiago', 'Brazil', 'iOS'),
    (40, 'user-0040', 'Aarav Sharma', 'aarav.sharma@nexus.test', 'IN', 'Delhi', 'India', 'Mobile'),
    (41, 'user-0041', 'Diya Mehta', 'diya.mehta@nexus.test', 'IN', 'Mumbai', 'India', 'Android'),
    (42, 'user-0042', 'Vivaan Rao', 'vivaan.rao@nexus.test', 'IN', 'Bengaluru', 'India', 'Desktop'),
    (43, 'user-0043', 'Anaya Kapoor', 'anaya.kapoor@nexus.test', 'IN', 'Hyderabad', 'India', 'iOS'),
    (44, 'user-0044', 'Ishaan Gupta', 'ishaan.gupta@nexus.test', 'IN', 'Pune', 'India', 'Mobile'),
    (45, 'user-0045', 'Priya Nair', 'priya.nair@nexus.test', 'BD', 'Dhaka', 'India', 'Android'),
    (46, 'user-0046', 'Thabo Nkosi', 'thabo.nkosi@nexus.test', 'ZA', 'Johannesburg', 'South Africa', 'Mobile'),
    (47, 'user-0047', 'Amina Dlamini', 'amina.dlamini@nexus.test', 'ZA', 'Cape Town', 'South Africa', 'Desktop'),
    (48, 'user-0048', 'Kagiso Mokoena', 'kagiso.mokoena@nexus.test', 'KE', 'Nairobi', 'South Africa', 'Android'),
    (49, 'user-0049', 'Lerato Naidoo', 'lerato.naidoo@nexus.test', 'NG', 'Lagos', 'South Africa', 'Mobile'),
    (50, 'user-0050', 'Zola Khumalo', 'zola.khumalo@nexus.test', 'ZA', 'Durban', 'South Africa', 'iOS');

INSERT INTO products (id, name, category, price, merchant_region) VALUES
    (1, 'Aurora Laptop 14', 'Electronics', 1299.00, 'North America (West)'),
    (2, 'Meridian Phone X', 'Electronics', 899.00, 'Japan'),
    (3, 'Pulse Noise-Canceling Headphones', 'Electronics', 199.00, 'Western Europe'),
    (4, 'Summit Running Shoes', 'Sports', 120.00, 'North America (East)'),
    (5, 'Terra Explorer Backpack', 'Outdoors', 89.00, 'Australia'),
    (6, 'Loom Performance Jacket', 'Fashion', 149.00, 'Western Europe'),
    (7, 'Nova Smartwatch', 'Electronics', 249.00, 'India'),
    (8, 'Cedar Coffee Maker', 'Home', 79.00, 'Brazil'),
    (9, 'Atlas Desk Lamp', 'Home', 45.00, 'North America (East)'),
    (10, 'Harbor Everyday Hoodie', 'Fashion', 65.00, 'Western Europe'),
    (11, 'Solstice Sunglasses', 'Fashion', 55.00, 'Australia'),
    (12, 'Drift Gaming Mouse', 'Electronics', 59.00, 'North America (West)'),
    (13, 'Ember Skincare Set', 'Beauty', 72.00, 'Japan'),
    (14, 'Orchard Tea Sampler', 'Grocery', 28.00, 'India'),
    (15, 'Cascade Water Bottle', 'Sports', 22.00, 'South Africa'),
    (16, 'Skyline 4K Monitor', 'Electronics', 329.00, 'North America (East)'),
    (17, 'Voyager Carry-On', 'Travel', 199.00, 'Southeast Asia'),
    (18, 'Prism Wireless Speaker', 'Electronics', 149.00, 'Brazil'),
    (19, 'Meadow Candle Pack', 'Home', 34.00, 'Western Europe'),
    (20, 'Helix Yoga Mat', 'Sports', 38.00, 'India'),
    (21, 'Origin Denim Jeans', 'Fashion', 84.00, 'Brazil'),
    (22, 'Quartz Kitchen Knife', 'Home', 64.00, 'Japan'),
    (23, 'Nimbus Tablet Pro', 'Electronics', 499.00, 'Southeast Asia'),
    (24, 'Basil Olive Oil Set', 'Grocery', 31.00, 'Western Europe'),
    (25, 'Aero Bike Helmet', 'Sports', 95.00, 'Australia');

INSERT INTO orders (id, user_id, total_amount, currency, status, region_name, user_display_name, platform, created_at, updated_at) VALUES
    (1, 1, 142.00, 'USD', 'completed', 'North America (East)', 'Alex Mercer', 'Desktop', '2026-03-07 08:14:00+00', '2026-03-07 08:19:00+00'),
    (2, 7, 958.00, 'USD', 'pending', 'North America (West)', 'Morgan Diaz', 'Desktop', '2026-03-07 08:18:00+00', '2026-03-07 08:18:00+00'),
    (3, 13, 277.00, 'USD', 'completed', 'Western Europe', 'Harper Jones', 'Desktop', '2026-03-07 08:24:00+00', '2026-03-07 08:30:00+00'),
    (4, 19, 64.00, 'USD', 'failed', 'Japan', 'Yuki Tanaka', 'Mobile', '2026-03-07 08:29:00+00', '2026-03-07 08:31:00+00'),
    (5, 24, 321.00, 'USD', 'completed', 'Southeast Asia', 'Wei Lim', 'Mobile', '2026-03-07 08:34:00+00', '2026-03-07 08:38:00+00'),
    (6, 30, 117.00, 'USD', 'completed', 'Australia', 'Olivia Brown', 'Mobile', '2026-03-07 08:39:00+00', '2026-03-07 08:43:00+00'),
    (7, 35, 177.00, 'USD', 'refunded', 'Brazil', 'Rafael Silva', 'Mobile', '2026-03-07 08:42:00+00', '2026-03-07 09:05:00+00'),
    (8, 40, 985.00, 'USD', 'completed', 'India', 'Aarav Sharma', 'Mobile', '2026-03-07 08:47:00+00', '2026-03-07 08:55:00+00'),
    (9, 46, 88.40, 'USD', 'completed', 'South Africa', 'Thabo Nkosi', 'Mobile', '2026-03-07 08:52:00+00', '2026-03-07 08:58:00+00'),
    (10, 5, 59.90, 'USD', 'pending', 'North America (East)', 'Taylor Brooks', 'Desktop', '2026-03-07 08:56:00+00', '2026-03-07 08:56:00+00'),
    (11, 11, 475.00, 'USD', 'completed', 'North America (West)', 'Parker Singh', 'Desktop', '2026-03-07 09:00:00+00', '2026-03-07 09:07:00+00'),
    (12, 17, 29.99, 'USD', 'failed', 'Western Europe', 'Emerson Garcia', 'iOS', '2026-03-07 09:04:00+00', '2026-03-07 09:06:00+00'),
    (13, 22, 520.00, 'USD', 'completed', 'Japan', 'Mei Nakamura', 'Android', '2026-03-07 09:08:00+00', '2026-03-07 09:12:00+00'),
    (14, 28, 73.50, 'USD', 'completed', 'Southeast Asia', 'Pim Chaiwat', 'iOS', '2026-03-07 09:11:00+00', '2026-03-07 09:15:00+00'),
    (15, 43, 142.00, 'USD', 'completed', 'India', 'Anaya Kapoor', 'iOS', '2026-03-07 09:16:00+00', '2026-03-07 09:20:00+00'),
    (16, 49, 210.00, 'USD', 'completed', 'South Africa', 'Lerato Naidoo', 'Mobile', '2026-03-07 09:22:00+00', '2026-03-07 09:27:00+00'),
    (17, 38, 67.89, 'USD', 'completed', 'Brazil', 'Sofia Almeida', 'Mobile', '2026-03-07 09:28:00+00', '2026-03-07 09:31:00+00');

INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, created_at) VALUES
    (1, 1, 4, 1, 120.00, '2026-03-07 08:14:00+00'),
    (2, 1, 15, 1, 22.00, '2026-03-07 08:14:10+00'),
    (3, 2, 2, 1, 899.00, '2026-03-07 08:18:00+00'),
    (4, 2, 12, 1, 59.00, '2026-03-07 08:18:10+00'),
    (5, 3, 6, 1, 149.00, '2026-03-07 08:24:00+00'),
    (6, 3, 22, 2, 64.00, '2026-03-07 08:24:10+00'),
    (7, 4, 22, 1, 64.00, '2026-03-07 08:29:00+00'),
    (8, 5, 7, 1, 249.00, '2026-03-07 08:34:00+00'),
    (9, 5, 13, 1, 72.00, '2026-03-07 08:34:10+00'),
    (10, 6, 25, 1, 95.00, '2026-03-07 08:39:00+00'),
    (11, 6, 15, 1, 22.00, '2026-03-07 08:39:10+00'),
    (12, 7, 18, 1, 149.00, '2026-03-07 08:42:00+00'),
    (13, 7, 14, 1, 28.00, '2026-03-07 08:42:10+00'),
    (14, 8, 2, 1, 899.00, '2026-03-07 08:47:00+00'),
    (15, 8, 22, 1, 64.00, '2026-03-07 08:47:10+00'),
    (16, 8, 15, 1, 22.00, '2026-03-07 08:47:20+00'),
    (17, 9, 11, 1, 55.00, '2026-03-07 08:52:00+00'),
    (18, 9, 19, 1, 33.40, '2026-03-07 08:52:10+00'),
    (19, 10, 12, 1, 59.90, '2026-03-07 08:56:00+00'),
    (20, 11, 16, 1, 329.00, '2026-03-07 09:00:00+00'),
    (21, 11, 3, 1, 146.00, '2026-03-07 09:00:10+00'),
    (22, 12, 14, 1, 29.99, '2026-03-07 09:04:00+00'),
    (23, 13, 23, 1, 499.00, '2026-03-07 09:08:00+00'),
    (24, 13, 24, 1, 21.00, '2026-03-07 09:08:10+00'),
    (25, 14, 8, 1, 45.50, '2026-03-07 09:11:00+00'),
    (26, 14, 24, 1, 28.00, '2026-03-07 09:11:10+00'),
    (27, 15, 6, 1, 104.00, '2026-03-07 09:16:00+00'),
    (28, 15, 20, 1, 38.00, '2026-03-07 09:16:10+00'),
    (29, 16, 17, 1, 188.00, '2026-03-07 09:22:00+00'),
    (30, 16, 15, 1, 22.00, '2026-03-07 09:22:10+00'),
    (31, 17, 24, 1, 31.89, '2026-03-07 09:28:00+00'),
    (32, 17, 15, 1, 36.00, '2026-03-07 09:28:10+00');

INSERT INTO cart_items (id, user_id, product_id, quantity, added_at, removed_at) VALUES
    (1, 2, 7, 1, '2026-03-07 08:05:00+00', NULL),
    (2, 5, 12, 1, '2026-03-07 08:20:00+00', '2026-03-07 08:55:00+00'),
    (3, 7, 2, 1, '2026-03-07 08:17:00+00', NULL),
    (4, 13, 19, 2, '2026-03-07 08:22:00+00', NULL),
    (5, 19, 22, 1, '2026-03-07 08:27:00+00', NULL),
    (6, 24, 13, 1, '2026-03-07 08:32:00+00', '2026-03-07 08:38:00+00'),
    (7, 28, 8, 1, '2026-03-07 09:09:00+00', NULL),
    (8, 30, 25, 1, '2026-03-07 08:37:00+00', '2026-03-07 08:43:00+00'),
    (9, 35, 18, 1, '2026-03-07 08:40:00+00', NULL),
    (10, 40, 23, 1, '2026-03-07 08:45:00+00', NULL),
    (11, 43, 6, 1, '2026-03-07 09:14:00+00', NULL),
    (12, 49, 17, 1, '2026-03-07 09:19:00+00', '2026-03-07 09:27:00+00');

INSERT INTO sessions (id, user_id, started_at, ended_at, platform, country_code, city, region_name, is_active, created_at) VALUES
    ('00000000-0000-4000-8000-000000000001', 1, '2026-03-07 08:00:00+00', '2026-03-07 08:45:00+00', 'Desktop', 'US', 'New York', 'North America (East)', FALSE, '2026-03-07 08:00:00+00'),
    ('00000000-0000-4000-8000-000000000002', 2, '2026-03-07 08:10:00+00', NULL, 'Mobile', 'US', 'Boston', 'North America (East)', TRUE, '2026-03-07 08:10:00+00'),
    ('00000000-0000-4000-8000-000000000003', 5, '2026-03-07 08:15:00+00', '2026-03-07 09:05:00+00', 'Desktop', 'CA', 'Toronto', 'North America (East)', FALSE, '2026-03-07 08:15:00+00'),
    ('00000000-0000-4000-8000-000000000004', 7, '2026-03-07 07:50:00+00', NULL, 'Desktop', 'US', 'Los Angeles', 'North America (West)', TRUE, '2026-03-07 07:50:00+00'),
    ('00000000-0000-4000-8000-000000000005', 8, '2026-03-07 08:20:00+00', '2026-03-07 08:58:00+00', 'iOS', 'US', 'San Francisco', 'North America (West)', FALSE, '2026-03-07 08:20:00+00'),
    ('00000000-0000-4000-8000-000000000006', 11, '2026-03-07 08:25:00+00', NULL, 'Desktop', 'US', 'Denver', 'North America (West)', TRUE, '2026-03-07 08:25:00+00'),
    ('00000000-0000-4000-8000-000000000007', 13, '2026-03-07 08:00:00+00', '2026-03-07 08:44:00+00', 'Desktop', 'GB', 'London', 'Western Europe', FALSE, '2026-03-07 08:00:00+00'),
    ('00000000-0000-4000-8000-000000000008', 15, '2026-03-07 08:30:00+00', NULL, 'Mobile', 'FR', 'Paris', 'Western Europe', TRUE, '2026-03-07 08:30:00+00'),
    ('00000000-0000-4000-8000-000000000009', 18, '2026-03-07 08:40:00+00', '2026-03-07 09:02:00+00', 'Mobile', 'NL', 'Amsterdam', 'Western Europe', FALSE, '2026-03-07 08:40:00+00'),
    ('00000000-0000-4000-8000-000000000010', 19, '2026-03-07 08:05:00+00', NULL, 'Mobile', 'JP', 'Tokyo', 'Japan', TRUE, '2026-03-07 08:05:00+00'),
    ('00000000-0000-4000-8000-000000000011', 20, '2026-03-07 08:50:00+00', '2026-03-07 09:10:00+00', 'iOS', 'JP', 'Osaka', 'Japan', FALSE, '2026-03-07 08:50:00+00'),
    ('00000000-0000-4000-8000-000000000012', 24, '2026-03-07 08:12:00+00', NULL, 'Mobile', 'SG', 'Singapore', 'Southeast Asia', TRUE, '2026-03-07 08:12:00+00'),
    ('00000000-0000-4000-8000-000000000013', 26, '2026-03-07 08:45:00+00', '2026-03-07 09:01:00+00', 'Mobile', 'ID', 'Jakarta', 'Southeast Asia', FALSE, '2026-03-07 08:45:00+00'),
    ('00000000-0000-4000-8000-000000000014', 28, '2026-03-07 08:55:00+00', NULL, 'iOS', 'TH', 'Bangkok', 'Southeast Asia', TRUE, '2026-03-07 08:55:00+00'),
    ('00000000-0000-4000-8000-000000000015', 30, '2026-03-07 07:40:00+00', '2026-03-07 08:50:00+00', 'Mobile', 'AU', 'Sydney', 'Australia', FALSE, '2026-03-07 07:40:00+00'),
    ('00000000-0000-4000-8000-000000000016', 32, '2026-03-07 08:35:00+00', NULL, 'iOS', 'AU', 'Brisbane', 'Australia', TRUE, '2026-03-07 08:35:00+00'),
    ('00000000-0000-4000-8000-000000000017', 35, '2026-03-07 08:02:00+00', '2026-03-07 08:48:00+00', 'Mobile', 'BR', 'Sao Paulo', 'Brazil', FALSE, '2026-03-07 08:02:00+00'),
    ('00000000-0000-4000-8000-000000000018', 38, '2026-03-07 09:00:00+00', NULL, 'Mobile', 'AR', 'Buenos Aires', 'Brazil', TRUE, '2026-03-07 09:00:00+00'),
    ('00000000-0000-4000-8000-000000000019', 40, '2026-03-07 08:18:00+00', '2026-03-07 09:06:00+00', 'Mobile', 'IN', 'Delhi', 'India', FALSE, '2026-03-07 08:18:00+00'),
    ('00000000-0000-4000-8000-000000000020', 42, '2026-03-07 08:33:00+00', NULL, 'Desktop', 'IN', 'Bengaluru', 'India', TRUE, '2026-03-07 08:33:00+00'),
    ('00000000-0000-4000-8000-000000000021', 43, '2026-03-07 08:42:00+00', NULL, 'iOS', 'IN', 'Hyderabad', 'India', TRUE, '2026-03-07 08:42:00+00'),
    ('00000000-0000-4000-8000-000000000022', 46, '2026-03-07 07:58:00+00', '2026-03-07 08:41:00+00', 'Mobile', 'ZA', 'Johannesburg', 'South Africa', FALSE, '2026-03-07 07:58:00+00'),
    ('00000000-0000-4000-8000-000000000023', 47, '2026-03-07 08:28:00+00', NULL, 'Desktop', 'ZA', 'Cape Town', 'South Africa', TRUE, '2026-03-07 08:28:00+00'),
    ('00000000-0000-4000-8000-000000000024', 49, '2026-03-07 08:48:00+00', NULL, 'Mobile', 'NG', 'Lagos', 'South Africa', TRUE, '2026-03-07 08:48:00+00');

INSERT INTO user_events (id, user_id, event_type, page_url, referrer_url, user_agent, ip_address, session_id, metadata, user_display_name, region_name, city, country_code, platform, amount, created_at) VALUES
    (1, 1, 'login', '/login', 'https://nexus.test/', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)', '203.0.113.1', '00000000-0000-4000-8000-000000000001', '{"auth":"password"}'::jsonb, 'Alex Mercer', 'North America (East)', 'New York', 'US', 'Desktop', NULL, '2026-03-07 08:00:05+00'),
    (2, 1, 'page_view', '/products/4', '/home', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)', '203.0.113.1', '00000000-0000-4000-8000-000000000001', '{"product_id":4}'::jsonb, 'Alex Mercer', 'North America (East)', 'New York', 'US', 'Desktop', NULL, '2026-03-07 08:04:00+00'),
    (3, 1, 'add_to_cart', '/cart', '/products/4', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)', '203.0.113.1', '00000000-0000-4000-8000-000000000001', '{"product_id":4,"quantity":1}'::jsonb, 'Alex Mercer', 'North America (East)', 'New York', 'US', 'Desktop', NULL, '2026-03-07 08:11:00+00'),
    (4, 1, 'checkout_complete', '/checkout/confirmation', '/checkout', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)', '203.0.113.1', '00000000-0000-4000-8000-000000000001', '{"order_id":1}'::jsonb, 'Alex Mercer', 'North America (East)', 'New York', 'US', 'Desktop', 142.00, '2026-03-07 08:19:00+00'),
    (5, 2, 'login', '/login', 'https://nexus.test/', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)', '203.0.113.2', '00000000-0000-4000-8000-000000000002', '{"auth":"password"}'::jsonb, 'Jordan Lee', 'North America (East)', 'Boston', 'US', 'Mobile', NULL, '2026-03-07 08:10:15+00'),
    (6, 2, 'search', '/search', '/home', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)', '203.0.113.2', '00000000-0000-4000-8000-000000000002', '{"query":"smartwatch"}'::jsonb, 'Jordan Lee', 'North America (East)', 'Boston', 'US', 'Mobile', NULL, '2026-03-07 08:16:00+00'),
    (7, 5, 'page_view', '/products/12', '/home', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', '203.0.113.5', '00000000-0000-4000-8000-000000000003', '{"product_id":12}'::jsonb, 'Taylor Brooks', 'North America (East)', 'Toronto', 'CA', 'Desktop', NULL, '2026-03-07 08:21:00+00'),
    (8, 5, 'add_to_cart', '/cart', '/products/12', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', '203.0.113.5', '00000000-0000-4000-8000-000000000003', '{"product_id":12,"quantity":1}'::jsonb, 'Taylor Brooks', 'North America (East)', 'Toronto', 'CA', 'Desktop', NULL, '2026-03-07 08:23:00+00'),
    (9, 7, 'login', '/login', 'https://nexus.test/', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', '203.0.113.7', '00000000-0000-4000-8000-000000000004', '{"auth":"google"}'::jsonb, 'Morgan Diaz', 'North America (West)', 'Los Angeles', 'US', 'Desktop', NULL, '2026-03-07 07:50:20+00'),
    (10, 7, 'page_view', '/products/2', '/home', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', '203.0.113.7', '00000000-0000-4000-8000-000000000004', '{"product_id":2}'::jsonb, 'Morgan Diaz', 'North America (West)', 'Los Angeles', 'US', 'Desktop', NULL, '2026-03-07 08:12:00+00'),
    (11, 7, 'checkout_start', '/checkout', '/cart', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', '203.0.113.7', '00000000-0000-4000-8000-000000000004', '{"cart_value":958.0}'::jsonb, 'Morgan Diaz', 'North America (West)', 'Los Angeles', 'US', 'Desktop', NULL, '2026-03-07 08:18:15+00'),
    (12, 8, 'page_view', '/products/12', '/campaign/spring', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)', '203.0.113.8', '00000000-0000-4000-8000-000000000005', '{"product_id":12}'::jsonb, 'Riley Chen', 'North America (West)', 'San Francisco', 'US', 'iOS', NULL, '2026-03-07 08:32:00+00'),
    (13, 11, 'checkout_complete', '/checkout/confirmation', '/checkout', 'Mozilla/5.0 (X11; Linux x86_64)', '203.0.113.11', '00000000-0000-4000-8000-000000000006', '{"order_id":11}'::jsonb, 'Parker Singh', 'North America (West)', 'Denver', 'US', 'Desktop', 475.00, '2026-03-07 09:07:00+00'),
    (14, 13, 'login', '/login', 'https://nexus.test/', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', '203.0.113.13', '00000000-0000-4000-8000-000000000007', '{"auth":"password"}'::jsonb, 'Harper Jones', 'Western Europe', 'London', 'GB', 'Desktop', NULL, '2026-03-07 08:00:30+00'),
    (15, 13, 'page_view', '/collections/spring', '/home', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', '203.0.113.13', '00000000-0000-4000-8000-000000000007', '{"collection":"spring"}'::jsonb, 'Harper Jones', 'Western Europe', 'London', 'GB', 'Desktop', NULL, '2026-03-07 08:10:00+00'),
    (16, 13, 'checkout_complete', '/checkout/confirmation', '/checkout', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', '203.0.113.13', '00000000-0000-4000-8000-000000000007', '{"order_id":3}'::jsonb, 'Harper Jones', 'Western Europe', 'London', 'GB', 'Desktop', 277.00, '2026-03-07 08:30:00+00'),
    (17, 15, 'search', '/search', '/home', 'Mozilla/5.0 (Linux; Android 15)', '203.0.113.15', '00000000-0000-4000-8000-000000000008', '{"query":"performance jacket"}'::jsonb, 'Finley Martin', 'Western Europe', 'Paris', 'FR', 'Mobile', NULL, '2026-03-07 08:35:00+00'),
    (18, 18, 'logout', '/logout', '/account', 'Mozilla/5.0 (Linux; Android 15)', '203.0.113.18', '00000000-0000-4000-8000-000000000009', '{"reason":"manual"}'::jsonb, 'Cameron Dubois', 'Western Europe', 'Amsterdam', 'NL', 'Mobile', NULL, '2026-03-07 09:02:00+00'),
    (19, 19, 'login', '/login', 'https://nexus.test/', 'Mozilla/5.0 (Linux; Android 15)', '203.0.113.19', '00000000-0000-4000-8000-000000000010', '{"auth":"password"}'::jsonb, 'Yuki Tanaka', 'Japan', 'Tokyo', 'JP', 'Mobile', NULL, '2026-03-07 08:05:10+00'),
    (20, 19, 'error', '/checkout', '/cart', 'Mozilla/5.0 (Linux; Android 15)', '203.0.113.19', '00000000-0000-4000-8000-000000000010', '{"code":"PAYMENT_TIMEOUT","severity":"warning"}'::jsonb, 'Yuki Tanaka', 'Japan', 'Tokyo', 'JP', 'Mobile', NULL, '2026-03-07 08:31:00+00'),
    (21, 20, 'page_view', '/products/13', '/home', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)', '203.0.113.20', '00000000-0000-4000-8000-000000000011', '{"product_id":13}'::jsonb, 'Haru Sato', 'Japan', 'Osaka', 'JP', 'iOS', NULL, '2026-03-07 08:56:00+00'),
    (22, 22, 'checkout_complete', '/checkout/confirmation', '/checkout', 'Mozilla/5.0 (Linux; Android 15)', '203.0.113.22', NULL, '{"order_id":13}'::jsonb, 'Mei Nakamura', 'Japan', 'Nagoya', 'JP', 'Android', 520.00, '2026-03-07 09:12:00+00'),
    (23, 24, 'login', '/login', 'https://nexus.test/', 'Mozilla/5.0 (Linux; Android 15)', '203.0.113.24', '00000000-0000-4000-8000-000000000012', '{"auth":"otp"}'::jsonb, 'Wei Lim', 'Southeast Asia', 'Singapore', 'SG', 'Mobile', NULL, '2026-03-07 08:12:10+00'),
    (24, 24, 'add_to_cart', '/cart', '/products/7', 'Mozilla/5.0 (Linux; Android 15)', '203.0.113.24', '00000000-0000-4000-8000-000000000012', '{"product_id":7,"quantity":1}'::jsonb, 'Wei Lim', 'Southeast Asia', 'Singapore', 'SG', 'Mobile', NULL, '2026-03-07 08:32:00+00'),
    (25, 24, 'checkout_complete', '/checkout/confirmation', '/checkout', 'Mozilla/5.0 (Linux; Android 15)', '203.0.113.24', '00000000-0000-4000-8000-000000000012', '{"order_id":5}'::jsonb, 'Wei Lim', 'Southeast Asia', 'Singapore', 'SG', 'Mobile', 321.00, '2026-03-07 08:38:00+00'),
    (26, 26, 'click', '/promo/summer', '/home', 'Mozilla/5.0 (Linux; Android 15)', '203.0.113.26', '00000000-0000-4000-8000-000000000013', '{"campaign":"summer-promo"}'::jsonb, 'Arif Rahman', 'Southeast Asia', 'Jakarta', 'ID', 'Mobile', NULL, '2026-03-07 08:49:00+00'),
    (27, 28, 'page_view', '/products/8', '/home', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)', '203.0.113.28', '00000000-0000-4000-8000-000000000014', '{"product_id":8}'::jsonb, 'Pim Chaiwat', 'Southeast Asia', 'Bangkok', 'TH', 'iOS', NULL, '2026-03-07 09:02:00+00'),
    (28, 28, 'checkout_complete', '/checkout/confirmation', '/checkout', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)', '203.0.113.28', '00000000-0000-4000-8000-000000000014', '{"order_id":14}'::jsonb, 'Pim Chaiwat', 'Southeast Asia', 'Bangkok', 'TH', 'iOS', 73.50, '2026-03-07 09:15:00+00'),
    (29, 30, 'login', '/login', 'https://nexus.test/', 'Mozilla/5.0 (Linux; Android 15)', '203.0.113.30', '00000000-0000-4000-8000-000000000015', '{"auth":"password"}'::jsonb, 'Olivia Brown', 'Australia', 'Sydney', 'AU', 'Mobile', NULL, '2026-03-07 07:40:20+00'),
    (30, 30, 'checkout_complete', '/checkout/confirmation', '/checkout', 'Mozilla/5.0 (Linux; Android 15)', '203.0.113.30', '00000000-0000-4000-8000-000000000015', '{"order_id":6}'::jsonb, 'Olivia Brown', 'Australia', 'Sydney', 'AU', 'Mobile', 117.00, '2026-03-07 08:43:00+00'),
    (31, 35, 'add_to_cart', '/cart', '/products/18', 'Mozilla/5.0 (Linux; Android 15)', '203.0.113.35', '00000000-0000-4000-8000-000000000017', '{"product_id":18,"quantity":1}'::jsonb, 'Rafael Silva', 'Brazil', 'Sao Paulo', 'BR', 'Mobile', NULL, '2026-03-07 08:40:30+00'),
    (32, 35, 'checkout_complete', '/checkout/confirmation', '/checkout', 'Mozilla/5.0 (Linux; Android 15)', '203.0.113.35', '00000000-0000-4000-8000-000000000017', '{"order_id":7}'::jsonb, 'Rafael Silva', 'Brazil', 'Sao Paulo', 'BR', 'Mobile', 177.00, '2026-03-07 08:44:00+00'),
    (33, 38, 'page_view', '/products/24', '/home', 'Mozilla/5.0 (Linux; Android 15)', '203.0.113.38', '00000000-0000-4000-8000-000000000018', '{"product_id":24}'::jsonb, 'Sofia Almeida', 'Brazil', 'Buenos Aires', 'AR', 'Mobile', NULL, '2026-03-07 09:03:00+00'),
    (34, 38, 'checkout_complete', '/checkout/confirmation', '/checkout', 'Mozilla/5.0 (Linux; Android 15)', '203.0.113.38', '00000000-0000-4000-8000-000000000018', '{"order_id":17}'::jsonb, 'Sofia Almeida', 'Brazil', 'Buenos Aires', 'AR', 'Mobile', 67.89, '2026-03-07 09:31:00+00'),
    (35, 40, 'login', '/login', 'https://nexus.test/', 'Mozilla/5.0 (Linux; Android 15)', '203.0.113.40', '00000000-0000-4000-8000-000000000019', '{"auth":"password"}'::jsonb, 'Aarav Sharma', 'India', 'Delhi', 'IN', 'Mobile', NULL, '2026-03-07 08:18:10+00'),
    (36, 40, 'search', '/search', '/home', 'Mozilla/5.0 (Linux; Android 15)', '203.0.113.40', '00000000-0000-4000-8000-000000000019', '{"query":"4k monitor"}'::jsonb, 'Aarav Sharma', 'India', 'Delhi', 'IN', 'Mobile', NULL, '2026-03-07 08:40:00+00'),
    (37, 40, 'checkout_complete', '/checkout/confirmation', '/checkout', 'Mozilla/5.0 (Linux; Android 15)', '203.0.113.40', '00000000-0000-4000-8000-000000000019', '{"order_id":8}'::jsonb, 'Aarav Sharma', 'India', 'Delhi', 'IN', 'Mobile', 985.00, '2026-03-07 08:55:00+00'),
    (38, 43, 'checkout_complete', '/checkout/confirmation', '/checkout', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)', '203.0.113.43', '00000000-0000-4000-8000-000000000021', '{"order_id":15}'::jsonb, 'Anaya Kapoor', 'India', 'Hyderabad', 'IN', 'iOS', 142.00, '2026-03-07 09:20:00+00'),
    (39, 46, 'page_view', '/products/15', '/home', 'Mozilla/5.0 (Linux; Android 15)', '203.0.113.46', '00000000-0000-4000-8000-000000000022', '{"product_id":15}'::jsonb, 'Thabo Nkosi', 'South Africa', 'Johannesburg', 'ZA', 'Mobile', NULL, '2026-03-07 08:15:00+00'),
    (40, 49, 'checkout_complete', '/checkout/confirmation', '/checkout', 'Mozilla/5.0 (Linux; Android 15)', '203.0.113.49', '00000000-0000-4000-8000-000000000024', '{"order_id":16}'::jsonb, 'Lerato Naidoo', 'South Africa', 'Lagos', 'NG', 'Mobile', 210.00, '2026-03-07 09:27:00+00');

SELECT setval(pg_get_serial_sequence('users', 'id'), COALESCE(MAX(id), 1), TRUE) FROM users;
SELECT setval(pg_get_serial_sequence('products', 'id'), COALESCE(MAX(id), 1), TRUE) FROM products;
SELECT setval(pg_get_serial_sequence('orders', 'id'), COALESCE(MAX(id), 1), TRUE) FROM orders;
SELECT setval(pg_get_serial_sequence('order_items', 'id'), COALESCE(MAX(id), 1), TRUE) FROM order_items;
SELECT setval(pg_get_serial_sequence('cart_items', 'id'), COALESCE(MAX(id), 1), TRUE) FROM cart_items;
SELECT setval(pg_get_serial_sequence('user_events', 'id'), COALESCE(MAX(id), 1), TRUE) FROM user_events;
SELECT setval(pg_get_serial_sequence('city_region_mapping', 'id'), COALESCE(MAX(id), 1), TRUE) FROM city_region_mapping;

CREATE PUBLICATION nexus_cdc_pub FOR TABLE
    users,
    products,
    orders,
    order_items,
    cart_items,
    user_events,
    sessions;
