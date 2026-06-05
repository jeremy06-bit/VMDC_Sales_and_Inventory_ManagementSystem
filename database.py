import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "vmdc_database.db")


def _run_pragma_integrity():
    """Quick integrity check on startup — called after init."""
    try:
        conn = sqlite3.connect(DB_PATH)
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        if result and result[0] != "ok":
            print(f"[WARNING] Database integrity check FAILED: {result[0]}")
    except Exception as e:
        print(f"[WARNING] Could not run integrity check: {e}")


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database():
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('owner', 'cashier')),
            full_name TEXT NOT NULL,
            force_pw_change INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            category TEXT,
            unit TEXT DEFAULT 'pc',
            cost_price REAL DEFAULT 0,
            selling_price REAL DEFAULT 0,
            current_stock INTEGER DEFAULT 0,
            low_stock_threshold INTEGER DEFAULT 5,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS sales_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_number TEXT UNIQUE NOT NULL,
            cashier_id INTEGER NOT NULL,
            subtotal REAL NOT NULL,
            discount REAL DEFAULT 0,
            total REAL NOT NULL,
            amount_tendered REAL DEFAULT 0,
            change_given REAL DEFAULT 0,
            payment_method TEXT DEFAULT 'cash',
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            vat REAL DEFAULT 0,
            FOREIGN KEY (cashier_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            subtotal REAL NOT NULL,
            FOREIGN KEY (transaction_id) REFERENCES sales_transactions(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );

        CREATE TABLE IF NOT EXISTS service_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_number TEXT UNIQUE NOT NULL,
            mechanic_id INTEGER NOT NULL,
            service_type TEXT NOT NULL,
            description TEXT,
            labor_fee REAL DEFAULT 0,
            parts_total REAL DEFAULT 0,
            total REAL NOT NULL,
            status TEXT DEFAULT 'completed' CHECK(status IN ('pending', 'in_progress', 'completed')),
            notes TEXT,
            mechanic_name TEXT,
            linked_sale_txn TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (mechanic_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS service_parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            subtotal REAL NOT NULL,
            FOREIGN KEY (service_id) REFERENCES service_transactions(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );

        CREATE TABLE IF NOT EXISTS stock_adjustments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            change_amount INTEGER NOT NULL,
            reason TEXT NOT NULL,
            reference TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (product_id) REFERENCES products(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS cash_drawer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cashier_id INTEGER NOT NULL,
            opening_cash REAL DEFAULT 0,
            closing_cash REAL,
            expected_cash REAL,
            discrepancy REAL,
            shift_date TEXT DEFAULT (date('now','localtime')),
            opened_at TEXT DEFAULT (datetime('now','localtime')),
            closed_at TEXT,
            status TEXT DEFAULT 'open' CHECK(status IN ('open', 'closed')),
            FOREIGN KEY (cashier_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_by INTEGER NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            expense_date TEXT DEFAULT (date('now','localtime')),
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (recorded_by) REFERENCES users(id)
        );

        -- ── Stock In / Delivery ────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS stock_in (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number  TEXT    NOT NULL,
            supplier_name   TEXT    NOT NULL,
            delivery_date   TEXT    NOT NULL,
            remarks         TEXT,
            recorded_by     INTEGER NOT NULL,
            status          TEXT    NOT NULL DEFAULT 'pending'
                                CHECK(status IN ('pending','approved','rejected')),
            created_at      TEXT    DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (recorded_by) REFERENCES users(id)
        );

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

        -- ── Stock Update Requests / Approval Workflow ──────────────────
        CREATE TABLE IF NOT EXISTS stock_update_requests (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            request_type        TEXT    NOT NULL
                                    CHECK(request_type IN ('stock_in','stock_adjustment','inventory_update')),
            stock_in_id         INTEGER,
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
            FOREIGN KEY (product_id)   REFERENCES products(id),
            FOREIGN KEY (requested_by) REFERENCES users(id),
            FOREIGN KEY (approved_by)  REFERENCES users(id),
            FOREIGN KEY (stock_in_id)  REFERENCES stock_in(id)
        );

        -- ── Approval Audit Log ─────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS approval_logs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id   INTEGER NOT NULL,
            action       TEXT    NOT NULL CHECK(action IN ('submitted','approved','rejected')),
            action_by    INTEGER NOT NULL,
            old_quantity INTEGER,
            new_quantity INTEGER,
            notes        TEXT,
            created_at   TEXT    DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (request_id) REFERENCES stock_update_requests(id),
            FOREIGN KEY (action_by)  REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS mechanics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            display_name TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS service_mechanics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL,
            mechanic_id INTEGER,
            mechanic_name TEXT NOT NULL,
            FOREIGN KEY (service_id) REFERENCES service_transactions(id),
            FOREIGN KEY (mechanic_id) REFERENCES mechanics(id)
        );
    """)

    # Migrations for older databases — must run BEFORE the admin INSERT
    users_cols = [r[1] for r in cur.execute("PRAGMA table_info(users)").fetchall()]
    if "force_pw_change" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN force_pw_change INTEGER DEFAULT 0")
        print("Migration: added column force_pw_change to users.")

    # Insert default owner account if not exists
    cur.execute("SELECT id FROM users WHERE username = 'admin'")
    if not cur.fetchone():
        # Import here to avoid circular imports; security module needs DB to exist first
        try:
            from security import hash_password
            hashed_pw = hash_password("Admin@2026")
        except Exception:
            hashed_pw = "Admin@2026"   # fallback until security module is importable
        cur.execute("""
            INSERT INTO users (username, password, role, full_name, force_pw_change)
            VALUES ('admin', ?, 'owner', 'System Administrator', 1)
        """, (hashed_pw,))

    existing_cols = [r[1] for r in cur.execute("PRAGMA table_info(service_transactions)").fetchall()]
    if "mechanic_name" not in existing_cols:
        cur.execute("ALTER TABLE service_transactions ADD COLUMN mechanic_name TEXT")
        print("Migration: added column mechanic_name to service_transactions.")
    if "linked_sale_txn" not in existing_cols:
        cur.execute("ALTER TABLE service_transactions ADD COLUMN linked_sale_txn TEXT")
        print("Migration: added column linked_sale_txn to service_transactions.")

    sales_cols = [r[1] for r in cur.execute("PRAGMA table_info(sales_transactions)").fetchall()]
    if "vat" not in sales_cols:
        cur.execute("ALTER TABLE sales_transactions ADD COLUMN vat REAL DEFAULT 0")
        print("Migration: added column vat to sales_transactions.")

    # ── v2 Migrations: new tables created above via CREATE TABLE IF NOT EXISTS ──
    # The executescript above already creates them; no ALTER needed for fresh DBs.
    # For existing databases, the tables may not exist yet — re-run executescript
    # covers that since CREATE TABLE IF NOT EXISTS is idempotent.

    # Detect old stock_in schema (had product_id baked in as a flat table).
    # If found, drop and recreate both stock_in and stock_in_items with the
    # new header+items design, then re-add stock_update_requests columns.
    stock_in_cols = [r[1] for r in cur.execute("PRAGMA table_info(stock_in)").fetchall()]
    if "product_id" in stock_in_cols:
        print("Migration: old stock_in schema detected — rebuilding to v2 schema...")
        cur.executescript("""
            DROP TABLE IF EXISTS stock_in_items;
            DROP TABLE IF EXISTS stock_in;

            CREATE TABLE stock_in (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_number  TEXT    NOT NULL,
                supplier_name   TEXT    NOT NULL,
                delivery_date   TEXT    NOT NULL,
                remarks         TEXT,
                recorded_by     INTEGER NOT NULL,
                status          TEXT    NOT NULL DEFAULT 'pending'
                                    CHECK(status IN ('pending','approved','rejected')),
                created_at      TEXT    DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (recorded_by) REFERENCES users(id)
            );

            CREATE TABLE stock_in_items (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_in_id     INTEGER NOT NULL,
                product_id      INTEGER NOT NULL,
                qty_delivered   INTEGER NOT NULL,
                cost_price      REAL    NOT NULL DEFAULT 0,
                selling_price   REAL    NOT NULL DEFAULT 0,
                FOREIGN KEY (stock_in_id) REFERENCES stock_in(id),
                FOREIGN KEY (product_id)  REFERENCES products(id)
            );
        """)
        print("Migration: stock_in and stock_in_items rebuilt successfully.")

    # Ensure stock_update_requests has all expected columns
    sur_cols = [r[1] for r in cur.execute("PRAGMA table_info(stock_update_requests)").fetchall()]
    if sur_cols:
        for col, definition in [
            ("rejection_reason",   "TEXT"),
            ("approved_by",        "INTEGER"),
            ("approval_date",      "TEXT"),
        ]:
            if col not in sur_cols:
                cur.execute(f"ALTER TABLE stock_update_requests ADD COLUMN {col} {definition}")
                print(f"Migration: added column {col} to stock_update_requests.")

    print("v2 tables checked (stock_in, stock_in_items, stock_update_requests, approval_logs).")

    # Seed default mechanics if table is empty
    if not cur.execute("SELECT id FROM mechanics LIMIT 1").fetchone():
        default_mechanics = [
            "Mechanic 1 — Jose Reyes",
            "Mechanic 2 — Ramon Cruz",
            "Mechanic 3 — Danilo Santos",
            "Mechanic 4 — Eduardo Flores",
            "Mechanic 5 — Rodrigo Lim",
            "Mechanic 6 — Armando Bautista",
            "Mechanic 7 — Fernando Garcia",
        ]
        for name in default_mechanics:
            cur.execute("INSERT INTO mechanics (display_name) VALUES (?)", (name,))
        print("Seeded default mechanics.")

    conn.commit()
    conn.close()
    print("Database initialized successfully.")

    # Run security migrations and integrity check
    try:
        from security import run_security_migrations, check_database_integrity
        run_security_migrations()
        ok, msg = check_database_integrity()
        if not ok:
            print(f"[WARNING] Database integrity issue detected: {msg}")
            print("[WARNING] Consider restoring from a backup before proceeding.")
    except Exception as e:
        print(f"[WARNING] Security migrations error: {e}")