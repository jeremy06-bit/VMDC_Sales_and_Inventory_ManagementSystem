# VMDC Motor Parts — Transaction Processing System

An offline desktop-based TPS for VMDC Motor Parts, built with Python + CustomTkinter + SQLite.

---

## Requirements
- Windows 10 or Windows 11
- Python 3.11 (already installed)
- VS Code (with Python + Pylance + SQLite Viewer extensions)

---

## First-Time Setup

Open VS Code in this folder, then open the terminal (Ctrl+`):

```bash
# 1. Create virtual environment
python -m venv myvenv

# 2. Activate it (Windows)
myvenv\Scripts\activate

# 3. Install packages
pip install -r requirements.txt

# 4. Run the system
python main.py
```

---

## Default Login

| Username | Password | Role  |
|----------|----------|-------|
| admin    | Admin@2026 | Owner |

**Change the password after first login via User Management.**

---

## Modules Available

| Module           | Owner | Cashier |
|------------------|-------|---------|
| Dashboard        | ✅    | ✅      | 
| Sales            | ✅    | ✅      | 
| Services         | ✅    | ✅      | 
| Inventory        | ✅    | ✅      | 
| Cash Drawer      | ✅    | ✅      | 
| Expenses         | ✅    | ❌      | 
| Reports          | ✅    | ❌      | 
| User Management  | ✅    | ❌      | 
| Backup           | ✅    | ❌      | 

---

## Database

The database is a single file: `data/vmdc_database.db`

It is created automatically on first run. To back it up, go to the **Backup** module in the app.

---

## Project Structure

```
vmdc_system/
├── main.py               # Entry point — run this
├── database.py           # DB setup and connection
├── requirements.txt      # Python packages
├── ui/
│   ├── login_window.py
│   ├── dashboard_window.py
│   ├── sales_window.py
│   ├── inventory_window.py
│   ├── services_window.py
│   ├── customers_window.py
│   ├── reports_window.py
│   ├── backup_window.py
│   ├── cashdrawer_window.py
│   ├── expenses_window.py
│   ├── users_window.py
│   └── other_windows.py  # Services, CashDrawer, Expenses, Users
├── utils/
│   └── helpers.py        # Utility functions
├── data/
│   └── vmdc_database.db  # Auto-created on first run
└── backups/              # Local backup copies
```

---

## Running Daily

```bash
# In VS Code terminal, inside the vmdc_system folder:
venv\Scripts\activate
python main.py
```
