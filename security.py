"""
VMDC Security Module
====================
Provides:
  - Password hashing (PBKDF2-HMAC-SHA256, bcrypt-compatible API)
  - Password policy enforcement
  - Account lockout
  - Login / audit logging
  - Session inactivity timeout
  - Role-based access control
  - Database integrity check
  - Encrypted backups
"""

import hashlib
import hmac
import os
import re
import json
import datetime
import socket
import platform
from database import get_connection

# ── Try bcrypt first, fall back to PBKDF2 ──────────────────────────────────────
try:
    import bcrypt as _bcrypt
    _USE_BCRYPT = True
except ImportError:
    _USE_BCRYPT = False

# ── Constants ──────────────────────────────────────────────────────────────────
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES     = 15
SESSION_TIMEOUT_MIN = 30

WEAK_DEFAULTS = {"admin", "owner", "123456", "password", "12345678", "vmdc"}

# ── Password hashing ───────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Return a hashed password string."""
    if _USE_BCRYPT:
        return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()
    # PBKDF2-HMAC-SHA256: format  pbkdf2$<hex-salt>$<hex-hash>
    salt = os.urandom(32)
    key  = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt, 390_000)
    return "pbkdf2$" + salt.hex() + "$" + key.hex()


def verify_password(plain: str, stored: str) -> bool:
    """Verify plain text against stored hash. Returns True on match."""
    try:
        if stored.startswith("pbkdf2$"):
            _, salt_hex, key_hex = stored.split("$")
            salt = bytes.fromhex(salt_hex)
            key  = bytes.fromhex(key_hex)
            check = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt, 390_000)
            return hmac.compare_digest(check, key)
        if _USE_BCRYPT:
            return _bcrypt.checkpw(plain.encode(), stored.encode())
        # Legacy plain-text fallback (pre-migration)
        return False
    except Exception:
        return False


def is_plain_text(stored: str) -> bool:
    """Return True if the stored value is NOT a known hash prefix."""
    return not (stored.startswith("pbkdf2$") or stored.startswith("$2b$") or stored.startswith("$2a$"))


# ── Password policy ────────────────────────────────────────────────────────────

def validate_password_policy(password: str):
    """
    Raise ValueError with a descriptive message if policy is not met.
    Policy: min 8 chars, uppercase, lowercase, digit, special char.
    """
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one number.")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?`~]", password):
        raise ValueError("Password must contain at least one special character.")


# ── Migrations ─────────────────────────────────────────────────────────────────

def run_security_migrations():
    """Create / alter tables for all security features."""
    conn = get_connection()
    cur  = conn.cursor()

    # users: lockout + audit columns
    user_cols = [r[1] for r in cur.execute("PRAGMA table_info(users)").fetchall()]
    for col, defn in [
        ("failed_attempts",  "INTEGER DEFAULT 0"),
        ("locked_until",     "TEXT"),
        ("last_login",       "TEXT"),
        ("last_failed_login","TEXT"),
        ("force_pw_change",  "INTEGER DEFAULT 0"),
    ]:
        if col not in user_cols:
            cur.execute(f"ALTER TABLE users ADD COLUMN {col} {defn}")
            print(f"Security migration: added users.{col}")

    # login_logs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS login_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            username    TEXT,
            action      TEXT,
            ip_address  TEXT,
            device_name TEXT,
            created_at  TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # audit_logs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            username   TEXT,
            module     TEXT,
            action     TEXT,
            record_id  TEXT,
            old_value  TEXT,
            new_value  TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # cash_drawer_logs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cash_drawer_logs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER,
            username      TEXT,
            action        TEXT,
            opening_cash  REAL,
            closing_cash  REAL,
            expected_cash REAL,
            actual_cash   REAL,
            difference    REAL,
            opened_at     TEXT,
            closed_at     TEXT,
            session_ref   TEXT,
            created_at    TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    conn.commit()
    conn.close()
    print("Security migrations complete.")


# ── Login helpers ──────────────────────────────────────────────────────────────

def _get_device_info():
    try:
        return f"{platform.node()} ({platform.system()})"
    except Exception:
        return "unknown"


def _get_ip():
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


def log_login_event(user_id, username, action):
    """Log a login-related event. Actions: LOGIN_SUCCESS, LOGIN_FAILED, ACCOUNT_LOCKED, LOGOUT, SESSION_TIMEOUT."""
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO login_logs (user_id, username, action, ip_address, device_name) VALUES (?,?,?,?,?)",
            (user_id, username, action, _get_ip(), _get_device_info())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[security] log_login_event error: {e}")


def log_audit(user_id, username, module, action, record_id=None, old_value=None, new_value=None):
    """Write an entry to audit_logs. Never logs password values."""
    # Scrub password fields
    def _scrub(val):
        if val is None:
            return None
        if isinstance(val, dict):
            val = {k: "***" if "password" in k.lower() else v for k, v in val.items()}
            return json.dumps(val)
        return str(val)

    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO audit_logs (user_id, username, module, action, record_id, old_value, new_value)
               VALUES (?,?,?,?,?,?,?)""",
            (user_id, username, module, action, str(record_id) if record_id else None,
             _scrub(old_value), _scrub(new_value))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[security] log_audit error: {e}")


def log_cash_drawer(user_id, username, action, session_ref=None,
                    opening_cash=None, closing_cash=None,
                    expected_cash=None, actual_cash=None, difference=None,
                    opened_at=None, closed_at=None):
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO cash_drawer_logs
               (user_id, username, action, opening_cash, closing_cash, expected_cash,
                actual_cash, difference, opened_at, closed_at, session_ref)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, username, action, opening_cash, closing_cash,
             expected_cash, actual_cash, difference, opened_at, closed_at, session_ref)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[security] log_cash_drawer error: {e}")


# ── Authentication ─────────────────────────────────────────────────────────────

def authenticate(username: str, password: str):
    """
    Verify credentials with lockout and legacy migration.
    Returns (user_dict, None) on success or (None, error_message) on failure.
    """
    conn = get_connection()
    row  = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()

    if not row:
        log_login_event(None, username, "LOGIN_FAILED")
        return None, "Invalid username or password."

    user = dict(row)

    # Check lockout
    if user.get("locked_until"):
        locked_until = datetime.datetime.fromisoformat(user["locked_until"])
        if datetime.datetime.now() < locked_until:
            remaining = int((locked_until - datetime.datetime.now()).total_seconds() / 60) + 1
            log_login_event(user["id"], username, "ACCOUNT_LOCKED")
            return None, f"Account temporarily locked.\nTry again in {remaining} minute(s)."
        # Lock expired — clear it
        conn = get_connection()
        conn.execute("UPDATE users SET locked_until=NULL, failed_attempts=0 WHERE id=?", (user["id"],))
        conn.commit()
        conn.close()
        user["locked_until"] = None
        user["failed_attempts"] = 0

    stored = user["password"]
    matched = False

    if is_plain_text(stored):
        # Legacy plain-text check
        if stored == password:
            matched = True
            # Migrate to hash immediately
            new_hash = hash_password(password)
            conn = get_connection()
            conn.execute("UPDATE users SET password=? WHERE id=?", (new_hash, user["id"]))
            conn.commit()
            conn.close()
            print(f"[security] Migrated password for user '{username}' to hash.")
    else:
        matched = verify_password(password, stored)

    if not matched:
        # Increment failed attempts
        new_count = (user.get("failed_attempts") or 0) + 1
        now_str   = datetime.datetime.now().isoformat(timespec="seconds")
        locked_until = None
        if new_count >= MAX_FAILED_ATTEMPTS:
            locked_until = (datetime.datetime.now() +
                            datetime.timedelta(minutes=LOCKOUT_MINUTES)).isoformat(timespec="seconds")

        conn = get_connection()
        conn.execute(
            "UPDATE users SET failed_attempts=?, last_failed_login=?, locked_until=? WHERE id=?",
            (new_count, now_str, locked_until, user["id"])
        )
        conn.commit()
        conn.close()

        log_login_event(user["id"], username, "LOGIN_FAILED")

        if locked_until:
            log_login_event(user["id"], username, "ACCOUNT_LOCKED")
            return None, f"Account locked after {MAX_FAILED_ATTEMPTS} failed attempts.\nTry again in {LOCKOUT_MINUTES} minutes."

        remaining = MAX_FAILED_ATTEMPTS - new_count
        return None, f"Invalid username or password.\n{remaining} attempt(s) remaining."

    # Success — reset lockout counters
    now_str = datetime.datetime.now().isoformat(timespec="seconds")
    conn = get_connection()
    conn.execute(
        "UPDATE users SET failed_attempts=0, locked_until=NULL, last_login=? WHERE id=?",
        (now_str, user["id"])
    )
    conn.commit()
    conn.close()

    log_login_event(user["id"], username, "LOGIN_SUCCESS")

    # Refresh user dict after updates
    conn = get_connection()
    user = dict(conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone())
    conn.close()
    return user, None


# ── Role-based access ──────────────────────────────────────────────────────────

def require_role(current_user: dict, role: str, action: str = "perform this action"):
    """Raise PermissionError if current_user does not have the required role."""
    if current_user.get("role") != role:
        raise PermissionError(f"Only {role}s can {action}.")


def check_role(current_user: dict, role: str) -> bool:
    return current_user.get("role") == role


# ── Default account check ──────────────────────────────────────────────────────

def check_force_password_change(user: dict) -> bool:
    """Return True if the user must change their password on first login."""
    if user.get("force_pw_change"):
        return True
    # Also flag if stored password is a known weak default
    stored = user.get("password", "")
    if is_plain_text(stored) and stored.lower() in WEAK_DEFAULTS:
        return True
    return False


def set_force_password_change(user_id: int, flag: bool = True):
    conn = get_connection()
    conn.execute("UPDATE users SET force_pw_change=? WHERE id=?", (1 if flag else 0, user_id))
    conn.commit()
    conn.close()


# ── Database integrity ─────────────────────────────────────────────────────────

def check_database_integrity() -> tuple[bool, str]:
    """Run PRAGMA integrity_check. Returns (ok: bool, message: str)."""
    try:
        conn = get_connection()
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        ok = result and result[0] == "ok"
        msg = result[0] if result else "No result"
        if not ok:
            log_audit(None, "system", "Database", "INTEGRITY_CHECK_FAILED",
                      old_value=None, new_value=msg)
        return ok, msg
    except Exception as e:
        return False, str(e)


# ── Encrypted backup ───────────────────────────────────────────────────────────

def create_encrypted_backup(db_path: str, dest_path: str) -> str:
    """
    Encrypt the database file with Fernet. Saves <dest_path>.enc and <dest_path>.key.
    Returns the key file path.
    """
    from cryptography.fernet import Fernet
    key     = Fernet.generate_key()
    f       = Fernet(key)
    key_path = dest_path + ".key"

    with open(db_path, "rb") as fp:
        data = fp.read()

    encrypted = f.encrypt(data)

    with open(dest_path, "wb") as fp:
        fp.write(encrypted)

    with open(key_path, "wb") as fp:
        fp.write(key)

    return key_path


def restore_encrypted_backup(enc_path: str, key_path: str, db_path: str):
    """Decrypt and restore a backup. Raises on failure."""
    from cryptography.fernet import Fernet

    with open(key_path, "rb") as fp:
        key = fp.read()
    f = Fernet(key)

    with open(enc_path, "rb") as fp:
        encrypted = fp.read()

    data = f.decrypt(encrypted)

    with open(db_path, "wb") as fp:
        fp.write(data)
