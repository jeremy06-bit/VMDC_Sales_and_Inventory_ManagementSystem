"""
VMDC Sample Data Seeder
Run this once from the project root:  python seed_sample_data.py
Populates the database with realistic sample data matching all product
categories, service types, mechanics, and table structure.
"""

import sqlite3
import os
import random
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "vmdc_database.db")

# ── Constants matching the application ───────────────────────────────────────

PRODUCT_CATEGORIES = [
    "Engine Parts",
    "Electrical Parts",
    "Brake System",
    "Tires and Lubricants",
    "Accessories",
    "After Market Parts",
    "Exhaust Parts",
]

SERVICE_TYPES = [
    "Product Installation",
    "Oil Change Service",
    "Brake Adjustment",
    "Tire Replacement",
    "Basic Motorcycle Check-up",
    "Customer Assistance",
]

MECHANICS = [
    "Mechanic 1 — Jose Reyes",
    "Mechanic 2 — Ramon Cruz",
    "Mechanic 3 — Danilo Santos",
    "Mechanic 4 — Eduardo Flores",
    "Mechanic 5 — Rodrigo Lim",
    "Mechanic 6 — Armando Bautista",
    "Mechanic 7 — Fernando Garcia",
]

EXPENSE_CATEGORIES = [
    "Electricity", "Water", "Rent", "Staff Salary", "Supplies", "Miscellaneous"
]

# ── Sample Products ───────────────────────────────────────────────────────────

PRODUCTS = [
    # Engine Parts
    {"code": "EP001", "name": "Piston Ring Set (Honda Click)",  "category": "Engine Parts",       "unit": "set",  "cost": 280,  "price": 380,  "stock": 25, "threshold": 5},
    {"code": "EP002", "name": "Gasket Set (Yamaha Mio)",        "category": "Engine Parts",       "unit": "set",  "cost": 180,  "price": 250,  "stock": 20, "threshold": 5},
    {"code": "EP003", "name": "Crankshaft Bearing",             "category": "Engine Parts",       "unit": "pc",   "cost": 120,  "price": 175,  "stock": 30, "threshold": 8},
    {"code": "EP004", "name": "Camshaft Chain",                 "category": "Engine Parts",       "unit": "pc",   "cost": 200,  "price": 290,  "stock": 18, "threshold": 5},
    {"code": "EP005", "name": "Valve Stem Seal",                "category": "Engine Parts",       "unit": "set",  "cost": 80,   "price": 120,  "stock": 40, "threshold": 10},
    {"code": "EP006", "name": "Engine Oil Filter",              "category": "Engine Parts",       "unit": "pc",   "cost": 60,   "price": 95,   "stock": 50, "threshold": 10},

    # Electrical Parts
    {"code": "EL001", "name": "Motorcycle Battery 12V 5Ah",     "category": "Electrical Parts",   "unit": "pc",   "cost": 550,  "price": 780,  "stock": 15, "threshold": 3},
    {"code": "EL002", "name": "Spark Plug (NGK CR7HSA)",        "category": "Electrical Parts",   "unit": "pc",   "cost": 65,   "price": 95,   "stock": 60, "threshold": 10},
    {"code": "EL003", "name": "CDI Unit (Honda Wave)",          "category": "Electrical Parts",   "unit": "pc",   "cost": 320,  "price": 480,  "stock": 10, "threshold": 3},
    {"code": "EL004", "name": "Headlight Bulb H4 35/35W",       "category": "Electrical Parts",   "unit": "pc",   "cost": 45,   "price": 75,   "stock": 45, "threshold": 10},
    {"code": "EL005", "name": "Turn Signal Bulb Set",           "category": "Electrical Parts",   "unit": "set",  "cost": 35,   "price": 60,   "stock": 40, "threshold": 10},
    {"code": "EL006", "name": "Voltage Regulator Rectifier",    "category": "Electrical Parts",   "unit": "pc",   "cost": 280,  "price": 420,  "stock": 12, "threshold": 3},
    {"code": "EL007", "name": "Horn (12V Loud)",                "category": "Electrical Parts",   "unit": "pc",   "cost": 90,   "price": 140,  "stock": 20, "threshold": 5},

    # Brake System
    {"code": "BR001", "name": "Front Brake Pad Set",            "category": "Brake System",       "unit": "set",  "cost": 150,  "price": 220,  "stock": 30, "threshold": 8},
    {"code": "BR002", "name": "Rear Brake Shoe Set",            "category": "Brake System",       "unit": "set",  "cost": 110,  "price": 170,  "stock": 25, "threshold": 8},
    {"code": "BR003", "name": "Brake Cable (Front)",            "category": "Brake System",       "unit": "pc",   "cost": 70,   "price": 110,  "stock": 20, "threshold": 5},
    {"code": "BR004", "name": "Brake Cable (Rear)",             "category": "Brake System",       "unit": "pc",   "cost": 75,   "price": 115,  "stock": 20, "threshold": 5},
    {"code": "BR005", "name": "Brake Disc Rotor 220mm",         "category": "Brake System",       "unit": "pc",   "cost": 380,  "price": 560,  "stock": 10, "threshold": 3},
    {"code": "BR006", "name": "Master Cylinder Rebuild Kit",    "category": "Brake System",       "unit": "set",  "cost": 180,  "price": 270,  "stock": 12, "threshold": 3},

    # Tires and Lubricants
    {"code": "TL001", "name": "Motorcycle Tire 70/90-17",       "category": "Tires and Lubricants","unit": "pc",   "cost": 580,  "price": 780,  "stock": 20, "threshold": 5},
    {"code": "TL002", "name": "Motorcycle Tire 80/90-17",       "category": "Tires and Lubricants","unit": "pc",   "cost": 620,  "price": 850,  "stock": 18, "threshold": 5},
    {"code": "TL003", "name": "Engine Oil 4T 800ml (Motul)",    "category": "Tires and Lubricants","unit": "btl",  "cost": 180,  "price": 260,  "stock": 40, "threshold": 10},
    {"code": "TL004", "name": "Gear Oil 90W 120ml",             "category": "Tires and Lubricants","unit": "btl",  "cost": 55,   "price": 85,   "stock": 50, "threshold": 10},
    {"code": "TL005", "name": "Chain Lubricant Spray",          "category": "Tires and Lubricants","unit": "can",  "cost": 110,  "price": 160,  "stock": 25, "threshold": 5},
    {"code": "TL006", "name": "Tire Inner Tube 17\"",            "category": "Tires and Lubricants","unit": "pc",   "cost": 95,   "price": 145,  "stock": 30, "threshold": 8},

    # Accessories
    {"code": "AC001", "name": "Side Mirror (Universal)",        "category": "Accessories",        "unit": "pair", "cost": 120,  "price": 185,  "stock": 15, "threshold": 5},
    {"code": "AC002", "name": "Handlebar Grip Set",             "category": "Accessories",        "unit": "set",  "cost": 65,   "price": 100,  "stock": 20, "threshold": 5},
    {"code": "AC003", "name": "Phone Holder (Bike Mount)",      "category": "Accessories",        "unit": "pc",   "cost": 80,   "price": 130,  "stock": 18, "threshold": 5},
    {"code": "AC004", "name": "Windshield (Honda Click 125)",   "category": "Accessories",        "unit": "pc",   "cost": 280,  "price": 420,  "stock": 10, "threshold": 3},
    {"code": "AC005", "name": "Luggage Rack Carrier",           "category": "Accessories",        "unit": "pc",   "cost": 350,  "price": 520,  "stock": 8,  "threshold": 3},
    {"code": "AC006", "name": "Helmet Lock",                    "category": "Accessories",        "unit": "pc",   "cost": 90,   "price": 140,  "stock": 15, "threshold": 5},

    # After Market Parts
    {"code": "AM001", "name": "Racing Camshaft (Yamaha Mio)",   "category": "After Market Parts", "unit": "pc",   "cost": 750,  "price": 1100, "stock": 8,  "threshold": 2},
    {"code": "AM002", "name": "Big Bore Kit 62mm",              "category": "After Market Parts", "unit": "set",  "cost": 1200, "price": 1750, "stock": 5,  "threshold": 2},
    {"code": "AM003", "name": "High Flow Air Filter",           "category": "After Market Parts", "unit": "pc",   "cost": 280,  "price": 420,  "stock": 12, "threshold": 3},
    {"code": "AM004", "name": "Performance Carburetor Jet Kit", "category": "After Market Parts", "unit": "set",  "cost": 180,  "price": 270,  "stock": 15, "threshold": 5},
    {"code": "AM005", "name": "Adjustable Suspension Spring",   "category": "After Market Parts", "unit": "pc",   "cost": 320,  "price": 480,  "stock": 10, "threshold": 3},

    # Exhaust Parts
    {"code": "EX001", "name": "Exhaust Muffler (Honda Click)",  "category": "Exhaust Parts",      "unit": "pc",   "cost": 680,  "price": 980,  "stock": 8,  "threshold": 2},
    {"code": "EX002", "name": "Exhaust Header Pipe",            "category": "Exhaust Parts",      "unit": "pc",   "cost": 420,  "price": 620,  "stock": 10, "threshold": 3},
    {"code": "EX003", "name": "Exhaust Gasket Set",             "category": "Exhaust Parts",      "unit": "set",  "cost": 80,   "price": 125,  "stock": 25, "threshold": 5},
    {"code": "EX004", "name": "Muffler Clamp 38mm",             "category": "Exhaust Parts",      "unit": "pc",   "cost": 45,   "price": 75,   "stock": 30, "threshold": 8},
    {"code": "EX005", "name": "Catalytic Converter (Scooter)",  "category": "Exhaust Parts",      "unit": "pc",   "cost": 580,  "price": 850,  "stock": 6,  "threshold": 2},
]

# ── Sample Customers ──────────────────────────────────────────────────────────

CUSTOMERS = [
    {"name": "Juan dela Cruz",       "phone": "09171234567", "plate": "ABC-123", "model": "Honda Click 125i"},
    {"name": "Maria Santos",         "phone": "09182345678", "plate": "XYZ-456", "model": "Yamaha Mio Soul GT"},
    {"name": "Roberto Reyes",        "phone": "09193456789", "plate": "DEF-789", "model": "Honda Beat"},
    {"name": "Lourdes Garcia",       "phone": "09204567890", "plate": "GHI-012", "model": "Suzuki Raider R150"},
    {"name": "Eduardo Fernandez",    "phone": "09215678901", "plate": "JKL-345", "model": "Kawasaki Barako II"},
    {"name": "Rosario Villanueva",   "phone": "09226789012", "plate": "MNO-678", "model": "Honda Wave 125"},
    {"name": "Andres Castillo",      "phone": "09237890123", "plate": "PQR-901", "model": "Yamaha Jupiter MX"},
    {"name": "Cynthia Torres",       "phone": "09248901234", "plate": "STU-234", "model": "Honda TMX 155"},
    {"name": "Florencio Ramos",      "phone": "09259012345", "plate": "VWX-567", "model": "Kawasaki CT100B"},
    {"name": "Teresita Aquino",      "phone": "09260123456", "plate": "YZA-890", "model": "Yamaha Sniper 150"},
    {"name": "Bernardo Mendoza",     "phone": "09271234568", "plate": "BCD-111", "model": "Honda Revo AT"},
    {"name": "Natividad Cruz",       "phone": "09282345679", "plate": "EFG-222", "model": "Suzuki EN125"},
    {"name": "Patricio Flores",      "phone": "09293456780", "plate": "HIJ-333", "model": "Honda XRM 125"},
    {"name": "Consolacion Bautista", "phone": "09304567891", "plate": "KLM-444", "model": "Yamaha Aerox 155"},
    {"name": "Domingo Pascual",      "phone": "09315678902", "plate": "NOP-555", "model": "Honda PCX 150"},
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def rand_dt(days_back=90):
    delta = random.randint(0, days_back)
    dt = datetime.now() - timedelta(days=delta,
                                    hours=random.randint(7, 17),
                                    minutes=random.randint(0, 59))
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def rand_day(days_back=90):
    delta = random.randint(0, days_back)
    return (datetime.now() - timedelta(days=delta)).strftime("%Y-%m-%d")

_counters = {"sale": 1000, "svc": 2000}

def next_txn(kind):
    _counters[kind] += 1
    prefix = "TXN" if kind == "sale" else "SVC"
    return f"{prefix}-{_counters[kind]}"


# ── Seeder ────────────────────────────────────────────────────────────────────

def seed():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    # ── Users ────────────────────────────────────────────────────────────────
    print("Seeding users...")
    cur.execute("SELECT id FROM users WHERE username='cashier1'")
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (username,password,role,full_name) VALUES (?,?,?,?)",
            ("cashier1", "cashier123", "cashier", "Ana Gonzales")
        )
    conn.commit()

    admin_id   = cur.execute("SELECT id FROM users WHERE username='admin'").fetchone()["id"]
    cashier_id = cur.execute("SELECT id FROM users WHERE username='cashier1'").fetchone()["id"]

    # ── Products ─────────────────────────────────────────────────────────────
    print("Seeding products...")
    for p in PRODUCTS:
        cur.execute("SELECT id FROM products WHERE code=?", (p["code"],))
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO products
                    (code, name, category, unit, cost_price, selling_price,
                     current_stock, low_stock_threshold)
                VALUES (?,?,?,?,?,?,?,?)
            """, (p["code"], p["name"], p["category"], p["unit"],
                  p["cost"], p["price"], p["stock"], p["threshold"]))
    conn.commit()

    products     = {r["code"]: dict(r) for r in cur.execute("SELECT * FROM products").fetchall()}
    product_list = list(products.values())

    # ── Customers ────────────────────────────────────────────────────────────
    print("Seeding customers...")
    for c in CUSTOMERS:
        cur.execute("SELECT id FROM customers WHERE phone=?", (c["phone"],))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO customers (name,phone,plate_number,vehicle_model) VALUES (?,?,?,?)",
                (c["name"], c["phone"], c["plate"], c["model"])
            )
    conn.commit()

    customer_ids = [r["id"] for r in cur.execute("SELECT id FROM customers").fetchall()]

    # ── Cash Drawer ──────────────────────────────────────────────────────────
    print("Seeding cash drawer sessions...")
    for i in range(10):
        day     = (datetime.now() - timedelta(days=i * 7)).strftime("%Y-%m-%d")
        opening = round(random.uniform(1000, 5000), 2)
        expected = round(opening + random.uniform(5000, 25000), 2)
        discrepancy = round(random.uniform(-50, 50), 2)
        closing = round(expected + discrepancy, 2)
        cur.execute("""
            INSERT INTO cash_drawer
                (cashier_id, opening_cash, closing_cash, expected_cash, discrepancy,
                 shift_date, opened_at, closed_at, status)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (cashier_id, opening, closing, expected, discrepancy,
              day, f"{day} 08:00:00", f"{day} 18:00:00", "closed"))
    conn.commit()

    # ── Sales Transactions ───────────────────────────────────────────────────
    print("Seeding 40 sales transactions...")
    sale_txn_numbers = []
    for _ in range(40):
        txn_num  = next_txn("sale")
        created  = rand_dt(90)
        cust_id  = random.choice(customer_ids + [None, None])
        cashier  = random.choice([cashier_id, admin_id])
        discount = random.choice([0, 0, 0, 50, 100, 200])

        items    = random.sample(product_list, k=random.randint(1, 4))
        subtotal = 0
        sale_items = []
        for prod in items:
            qty      = random.randint(1, 3)
            price    = prod["selling_price"]
            line_sub = round(qty * price, 2)
            subtotal += line_sub
            sale_items.append((prod["id"], qty, price, line_sub))

        total    = round(subtotal - discount, 2)
        tendered = round(total + random.choice([0, 0, 5, 10, 20, 50, 100]), 2)
        change   = round(tendered - total, 2)
        payment  = random.choice(["cash", "cash", "cash", "gcash"])

        cur.execute("""
            INSERT INTO sales_transactions
                (transaction_number, cashier_id, customer_id, subtotal, discount, total,
                 amount_tendered, change_given, payment_method, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (txn_num, cashier, cust_id, subtotal, discount, total,
              tendered, change, payment, created))
        txn_id = cur.lastrowid
        sale_txn_numbers.append(txn_num)

        for prod_id, qty, price, line_sub in sale_items:
            cur.execute("""
                INSERT INTO sale_items (transaction_id, product_id, quantity, unit_price, subtotal)
                VALUES (?,?,?,?,?)
            """, (txn_id, prod_id, qty, price, line_sub))

    conn.commit()

    # ── Service Transactions ─────────────────────────────────────────────────
    print("Seeding 30 service transactions...")
    statuses = ["completed", "completed", "completed", "in_progress", "pending"]

    desc_map = {
        "Product Installation":       "Installed customer-supplied or shop parts on the motorcycle",
        "Oil Change Service":          "Full engine oil and gear oil change with filter replacement",
        "Brake Adjustment":            "Adjusted and tuned front and rear brake system",
        "Tire Replacement":            "Replaced worn tire and inner tube",
        "Basic Motorcycle Check-up":   "Full inspection: brakes, lights, battery, and engine oil",
        "Customer Assistance":         "Assisted customer in identifying and finding correct parts",
    }

    labor_ranges = {
        "Product Installation":       (50,  300),
        "Oil Change Service":          (50,  150),
        "Brake Adjustment":            (100, 300),
        "Tire Replacement":            (100, 250),
        "Basic Motorcycle Check-up":   (0,   0),
        "Customer Assistance":         (0,   0),
    }

    for _ in range(30):
        svc_num       = next_txn("svc")
        created       = rand_dt(90)
        svc_type      = random.choice(SERVICE_TYPES)
        mechanic_name = random.choice(MECHANICS)
        cust_id       = random.choice(customer_ids + [None])
        status        = random.choice(statuses)

        lo, hi    = labor_ranges[svc_type]
        labor_fee = round(random.uniform(lo, hi), 2) if hi > 0 else 0.0

        # Relevant parts per service type
        parts_used = []
        if svc_type == "Oil Change Service":
            for code in ["TL003", "TL004", "EP006"]:
                p = products.get(code)
                if p:
                    parts_used.append((p["id"], 1, p["selling_price"]))

        elif svc_type == "Tire Replacement":
            tire = products.get(random.choice(["TL001", "TL002"]))
            tube = products.get("TL006")
            if tire: parts_used.append((tire["id"], 1, tire["selling_price"]))
            if tube: parts_used.append((tube["id"], 1, tube["selling_price"]))

        elif svc_type == "Brake Adjustment":
            part = products.get(random.choice(["BR001", "BR002", "BR003", "BR004"]))
            if part: parts_used.append((part["id"], 1, part["selling_price"]))

        elif svc_type == "Product Installation":
            part = random.choice(product_list)
            parts_used.append((part["id"], 1, part["selling_price"]))

        elif svc_type == "Basic Motorcycle Check-up":
            # Sometimes recommend a spark plug or oil filter
            if random.random() < 0.4:
                part = products.get(random.choice(["EL002", "EP006"]))
                if part: parts_used.append((part["id"], 1, part["selling_price"]))

        parts_total = round(sum(qty * price for _, qty, price in parts_used), 2)
        total       = round(labor_fee + parts_total, 2)

        # Link to a past sale transaction ~30% of the time
        linked_sale = random.choice(sale_txn_numbers) if random.random() < 0.3 else None

        cur.execute("""
            INSERT INTO service_transactions
                (transaction_number, mechanic_id, customer_id, service_type, description,
                 labor_fee, parts_total, total, status, mechanic_name, linked_sale_txn, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (svc_num, admin_id, cust_id, svc_type, desc_map[svc_type],
              labor_fee, parts_total, total, status, mechanic_name, linked_sale, created))
        svc_id = cur.lastrowid

        for prod_id, qty, price in parts_used:
            cur.execute("""
                INSERT INTO service_parts (service_id, product_id, quantity, unit_price, subtotal)
                VALUES (?,?,?,?,?)
            """, (svc_id, prod_id, qty, price, round(qty * price, 2)))

    conn.commit()

    # ── Stock Adjustments ────────────────────────────────────────────────────
    print("Seeding stock adjustments...")
    reasons = [
        ("Restocked from supplier",        20),
        ("Restocked from supplier",        30),
        ("Damaged item removed",           -3),
        ("Inventory count correction",      5),
        ("Returned to supplier",           -2),
        ("Initial stock entry",            50),
    ]
    for prod in random.sample(product_list, k=15):
        reason_text, amount = random.choice(reasons)
        cur.execute("""
            INSERT INTO stock_adjustments (product_id, user_id, change_amount, reason, created_at)
            VALUES (?,?,?,?,?)
        """, (prod["id"], admin_id, amount, reason_text, rand_dt(60)))
    conn.commit()

    # ── Expenses ─────────────────────────────────────────────────────────────
    print("Seeding expenses...")
    expense_data = [
        ("Electricity",  "Monthly Meralco bill — April",          3200.00),
        ("Electricity",  "Monthly Meralco bill — March",          3450.00),
        ("Water",        "Monthly water bill — April",              480.00),
        ("Water",        "Monthly water bill — March",              510.00),
        ("Rent",         "Shop monthly rent — April",            12000.00),
        ("Rent",         "Shop monthly rent — March",            12000.00),
        ("Rent",         "Shop monthly rent — February",         12000.00),
        ("Staff Salary", "Mechanic weekly wages (Week 1)",         7000.00),
        ("Staff Salary", "Mechanic weekly wages (Week 2)",         7000.00),
        ("Staff Salary", "Cashier weekly salary (Week 1)",         4500.00),
        ("Staff Salary", "Cashier weekly salary (Week 2)",         4500.00),
        ("Supplies",     "Cleaning materials and shop rags",         350.00),
        ("Supplies",     "Office supplies and receipt pads",         180.00),
        ("Supplies",     "Lubricant and shop consumables",           620.00),
        ("Miscellaneous","Garbage collection fee",                   150.00),
        ("Miscellaneous","Minor shop repairs",                       800.00),
        ("Miscellaneous","Transportation for parts pickup",          300.00),
    ]
    for cat, desc, amount in expense_data:
        day = rand_day(90)
        cur.execute("""
            INSERT INTO expenses (recorded_by, category, description, amount, expense_date, created_at)
            VALUES (?,?,?,?,?,?)
        """, (admin_id, cat, desc, amount, day, f"{day} 09:00:00"))
    conn.commit()
    conn.close()

    # ── Summary ──────────────────────────────────────────────────────────────
    conn2 = sqlite3.connect(DB_PATH)
    tables = ["users", "products", "customers", "sales_transactions", "sale_items",
              "service_transactions", "service_parts", "stock_adjustments",
              "cash_drawer", "expenses"]
    print("\n── Seeding complete! ──────────────────────────────")
    for t in tables:
        n = conn2.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:<30} {n:>4} rows")
    conn2.close()
    print("───────────────────────────────────────────────────")
    print("Place 'data/vmdc_database.db' in your project and run main.py.")


if __name__ == "__main__":
    seed()
