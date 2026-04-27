-- ============================================================
-- Bookworm Database Schema
-- ============================================================

-- 1. STORES table
CREATE TABLE IF NOT EXISTS stores (
    store_id    SERIAL PRIMARY KEY,
    store_name  TEXT NOT NULL UNIQUE,
    location    TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Insert a default "Warehouse" store (company-wide general inventory)
INSERT INTO stores (store_name, location)
VALUES ('Warehouse', 'General / Company-wide')
ON CONFLICT (store_name) DO NOTHING;

-- 2. USERS table (for login / auth)
CREATE TABLE IF NOT EXISTS users (
    user_id         SERIAL PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    auth_level      TEXT NOT NULL DEFAULT 'employee'
                    CHECK (auth_level IN ('admin', 'manager', 'employee')),
    store_id        INT REFERENCES stores(store_id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 3. BOOKS table
CREATE TABLE IF NOT EXISTS books (
    isbn_13     TEXT PRIMARY KEY,
    isbn_10     TEXT,
    title       TEXT NOT NULL,
    author      TEXT NOT NULL,
    year        INT,
    edition     INT DEFAULT 1,
    page_count  INT,
    genre       TEXT,
    rating      NUMERIC(3,1) DEFAULT 0.0
                CHECK (rating >= 0 AND rating <= 5),
    publisher   TEXT,
    language    TEXT DEFAULT 'English',
    cover_type  TEXT DEFAULT 'paperback'
                CHECK (cover_type IN ('paperback', 'hardcover', 'ebook')),
    qr_code     TEXT UNIQUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 4. INVENTORY table (per-store stock)
CREATE TABLE IF NOT EXISTS inventory (
    inventory_id    SERIAL PRIMARY KEY,
    isbn_13         TEXT NOT NULL REFERENCES books(isbn_13) ON DELETE CASCADE,
    store_id        INT NOT NULL REFERENCES stores(store_id) ON DELETE CASCADE,
    quantity        INT NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    UNIQUE(isbn_13, store_id)
);

-- 5. PRICING table (per-store pricing with scheduled promotions)
CREATE TABLE IF NOT EXISTS pricing (
    pricing_id          SERIAL PRIMARY KEY,
    isbn_13             TEXT NOT NULL REFERENCES books(isbn_13) ON DELETE CASCADE,
    store_id            INT NOT NULL REFERENCES stores(store_id) ON DELETE CASCADE,
    base_price          NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    discount_percent    NUMERIC(5,2) DEFAULT 0.00
                        CHECK (discount_percent >= 0 AND discount_percent <= 100),
    discount_start      DATE,
    discount_end        DATE,
    promo_type          TEXT DEFAULT 'none'
                        CHECK (promo_type IN ('none', 'bogo', 'buy2get1', 'percentage', 'fixed_amount')),
    promo_value         NUMERIC(10,2) DEFAULT 0.00,
    promo_start         DATE,
    promo_end           DATE,
    UNIQUE(isbn_13, store_id)
);

-- 6. CHECKOUT LOGS table (audit trail for QR checkout scans)
CREATE TABLE IF NOT EXISTS checkout_logs (
    checkout_id  SERIAL PRIMARY KEY,
    isbn_13      TEXT NOT NULL REFERENCES books(isbn_13) ON DELETE CASCADE,
    store_id     INT REFERENCES stores(store_id) ON DELETE SET NULL,
    user_id      INT REFERENCES users(user_id) ON DELETE SET NULL,
    quantity     INT NOT NULL DEFAULT 1 CHECK (quantity > 0),
    scan_value   TEXT,
    checked_out_at TIMESTAMPTZ DEFAULT NOW()
);

-- 7. Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_books_title ON books(title);
CREATE INDEX IF NOT EXISTS idx_books_author ON books(author);
CREATE INDEX IF NOT EXISTS idx_books_genre ON books(genre);
CREATE INDEX IF NOT EXISTS idx_books_year ON books(year);
CREATE INDEX IF NOT EXISTS idx_books_qr_code ON books(qr_code);
CREATE INDEX IF NOT EXISTS idx_inventory_store ON inventory(store_id);
CREATE INDEX IF NOT EXISTS idx_inventory_isbn ON inventory(isbn_13);
CREATE INDEX IF NOT EXISTS idx_pricing_store ON pricing(store_id);
CREATE INDEX IF NOT EXISTS idx_pricing_isbn ON pricing(isbn_13);

-- 8. Create a default admin user (password: admin123 — change in production!)
-- The hash below is bcrypt for 'admin123'
-- You should change this password immediately after first login
INSERT INTO users (username, password_hash, display_name, auth_level, store_id)
VALUES (
    'admin',
    '$2b$12$LJ3m4ys3LkFTSMkLxOzHeOH0v7RqFcNzqW7a4wYqGqyGqGqGqGqGq',
    'System Administrator',
    'admin',
    1
)
ON CONFLICT (username) DO NOTHING;

-- ============================================================
-- Helper view: book inventory with store info
-- ============================================================
CREATE OR REPLACE VIEW book_inventory_view AS
SELECT
    b.isbn_13,
    b.isbn_10,
    b.title,
    b.author,
    b.year,
    b.edition,
    b.page_count,
    b.genre,
    b.rating,
    b.publisher,
    b.language,
    b.cover_type,
    s.store_id,
    s.store_name,
    COALESCE(i.quantity, 0) AS quantity,
    COALESCE(p.base_price, 0) AS base_price,
    COALESCE(p.discount_percent, 0) AS discount_percent,
    p.discount_start,
    p.discount_end,
    COALESCE(p.promo_type, 'none') AS promo_type,
    COALESCE(p.promo_value, 0) AS promo_value,
    p.promo_start,
    p.promo_end
FROM books b
CROSS JOIN stores s
LEFT JOIN inventory i ON i.isbn_13 = b.isbn_13 AND i.store_id = s.store_id
LEFT JOIN pricing p ON p.isbn_13 = b.isbn_13 AND p.store_id = s.store_id;

