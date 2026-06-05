import datetime
import random
import string


def generate_transaction_number(prefix: str = "TXN") -> str:
    """Generate a unique transaction number like SL-20250510-A3K9"""
    date_part = datetime.datetime.now().strftime("%Y%m%d")
    rand_part = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{prefix}-{date_part}-{rand_part}"


def format_currency(amount: float, symbol: str = "₱") -> str:
    return f"{symbol}{amount:,.2f}"


def get_today() -> str:
    return datetime.date.today().strftime("%Y-%m-%d")


def get_now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")