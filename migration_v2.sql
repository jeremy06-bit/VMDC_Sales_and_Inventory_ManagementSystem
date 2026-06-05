-- ============================================================
--  VMDC Motor Parts — Database Migration v2
--  Adds: stock_in, stock_in_items, stock_adjustments (extended),
--        stock_update_requests, approval_logs
-- ============================================================

-- 1. Stock In / Delivery Header table
CREATE TABLE IF NOT EXISTS stock_in (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number      TEXT    NOT NULL,
    supplier_name       TEXT    NOT NULL,
    delivery_date       TEXT    NOT NULL,
    remarks             TEXT,
    recorded_by         INTEGER NOT NULL,
    status              TEXT    NOT NULL DEFAULT 'pending'
                            CHECK(status IN ('pending','approved','rejected')),
    created_at          TEXT    DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (recorded_by) REFERENCES users(id)
);

-- 2. Stock In line items (one row per product per delivery)
CREATE TABLE IF NOT EXISTS stock_in_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_in_id     INTEGER NOT NULL,
    product_id      INTEGER NOT NULL,
    qty_delivered   INTEGER NOT NULL,
    cost_price      REAL    NOT NULL DEFAULT 0,
    selling_price   REAL    NOT NULL DEFAULT 0,
    FOREIGN KEY (stock_in_id) REFERENCES stock_in(id),
    FOREIGN KEY (product_id)  REFERENCES products(id)
);

-- 3. Extend stock_adjustments with extra columns (safe ALTER — skips if column exists)
--    Run these individually; SQLite does not support multi-column ALTER in one statement.

-- 4. Stock Update Requests (approval workflow)
CREATE TABLE IF NOT EXISTS stock_update_requests (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    request_type        TEXT    NOT NULL
                            CHECK(request_type IN ('stock_in','stock_adjustment','inventory_update')),
    stock_in_id         INTEGER,               -- linked delivery (if type = stock_in)
    product_id          INTEGER NOT NULL,
    product_name        TEXT    NOT NULL,
    old_quantity        INTEGER NOT NULL DEFAULT 0,
    requested_quantity  INTEGER NOT NULL,
    quantity_difference INTEGER NOT NULL,
    reason              TEXT,
    requested_by        INTEGER NOT NULL,
    request_date        TEXT    DEFAULT (datetime('now','localtime')),
    status              TEXT    NOT NULL DEFAULT 'pending'
                            CHECK(status IN ('pending','approved','rejected')),
    approved_by         INTEGER,
    approval_date       TEXT,
    rejection_reason    TEXT,
    FOREIGN KEY (product_id)    REFERENCES products(id),
    FOREIGN KEY (requested_by)  REFERENCES users(id),
    FOREIGN KEY (approved_by)   REFERENCES users(id),
    FOREIGN KEY (stock_in_id)   REFERENCES stock_in(id)
);

-- 5. Approval audit log
CREATE TABLE IF NOT EXISTS approval_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id      INTEGER NOT NULL,
    action          TEXT    NOT NULL CHECK(action IN ('submitted','approved','rejected')),
    action_by       INTEGER NOT NULL,
    old_quantity    INTEGER,
    new_quantity    INTEGER,
    notes           TEXT,
    created_at      TEXT    DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (request_id) REFERENCES stock_update_requests(id),
    FOREIGN KEY (action_by)  REFERENCES users(id)
);
