"""
VMDC Motor Parts — Cash Drawer / Shift Session Module
======================================================
Full POS-style cash session workflow:

  1. Open Drawer  → creates a cash_drawer session (CS-YYYYMMDD-NNN)
  2. Transactions → sales & services link to the active session
  3. Cash Movements → Cash In / Cash Out recorded mid-shift
  4. Close Drawer → actual count vs expected, variance report

DB additions handled via _migrate() on first load:
  • cash_drawer.session_id column
  • cash_movements table
  • sales_transactions.session_id column (nullable FK)
  • service_transactions.session_id column (nullable FK)
"""

import customtkinter as ctk
from tkinter import ttk
from datetime import datetime
from database import get_connection
from security import log_cash_drawer, log_audit
from ui.theme import (
    BG_DARK, BG_CARD, BG_CARD_ALT, BG_INPUT, BG_HOVER, BORDER,
    ACCENT, ACCENT_HOVER, ACCENT_LIGHT, ACCENT_SUBTLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    SUCCESS, SUCCESS_HOVER, DANGER, DANGER_HOVER,
    WARNING, INFO,
    style_treeview, insert_with_stripes, Paginator,
    create_dialog_entry, create_dialog_button, style_dialog,
    create_option_menu,
    msg_info, msg_warning, msg_error, msg_success, msg_question,
)


# ─────────────────────────────────────────────────────────────
#  DB Migration — run once on import
# ─────────────────────────────────────────────────────────────

def _migrate():
    conn = get_connection()
    cur = conn.cursor()

    # 1. cash_drawer.session_id
    cd_cols = [r[1] for r in cur.execute("PRAGMA table_info(cash_drawer)").fetchall()]
    if "session_id" not in cd_cols:
        cur.execute("ALTER TABLE cash_drawer ADD COLUMN session_id TEXT")
        # Back-fill existing rows with a placeholder session id
        cur.execute("""
            UPDATE cash_drawer SET session_id = 'CS-' || shift_date || '-' ||
            printf('%03d', id) WHERE session_id IS NULL
        """)
        print("Migration: added session_id to cash_drawer.")

    if "notes" not in cd_cols:
        cur.execute("ALTER TABLE cash_drawer ADD COLUMN notes TEXT")
        print("Migration: added notes to cash_drawer.")

    # 2. cash_movements table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cash_movements (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id   INTEGER NOT NULL,
            move_type    TEXT    NOT NULL CHECK(move_type IN ('cash_in','cash_out')),
            amount       REAL    NOT NULL,
            reason       TEXT    NOT NULL,
            recorded_by  INTEGER NOT NULL,
            created_at   TEXT    DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (session_id)  REFERENCES cash_drawer(id),
            FOREIGN KEY (recorded_by) REFERENCES users(id)
        )
    """)

    # 3. session_id on sales_transactions
    st_cols = [r[1] for r in cur.execute("PRAGMA table_info(sales_transactions)").fetchall()]
    if "session_id" not in st_cols:
        cur.execute("ALTER TABLE sales_transactions ADD COLUMN session_id INTEGER REFERENCES cash_drawer(id)")
        print("Migration: added session_id to sales_transactions.")

    # 4. session_id on service_transactions
    sv_cols = [r[1] for r in cur.execute("PRAGMA table_info(service_transactions)").fetchall()]
    if "session_id" not in sv_cols:
        cur.execute("ALTER TABLE service_transactions ADD COLUMN session_id INTEGER REFERENCES cash_drawer(id)")
        print("Migration: added session_id to service_transactions.")

    conn.commit()
    conn.close()


_migrate()


# ─────────────────────────────────────────────────────────────
#  Session ID generator
# ─────────────────────────────────────────────────────────────

def _generate_session_id() -> str:
    today = datetime.now().strftime("%Y%m%d")
    conn  = get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM cash_drawer WHERE shift_date = date('now','localtime')"
    ).fetchone()[0]
    conn.close()
    return f"CS-{today}-{count + 1:03d}"


def get_active_session(user_id: int):
    """Return the open cash_drawer row for this user, or None."""
    conn = get_connection()
    row  = conn.execute("""
        SELECT cd.*, u.full_name
        FROM cash_drawer cd
        JOIN users u ON u.id = cd.cashier_id
        WHERE cd.cashier_id = ? AND cd.status = 'open'
        ORDER BY cd.opened_at DESC LIMIT 1
    """, (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_any_active_session():
    """Return any open session (used to block a second simultaneous open session)."""
    conn = get_connection()
    row  = conn.execute("""
        SELECT cd.*, u.full_name
        FROM cash_drawer cd
        JOIN users u ON u.id = cd.cashier_id
        WHERE cd.status = 'open'
        ORDER BY cd.opened_at DESC LIMIT 1
    """).fetchone()
    conn.close()
    return dict(row) if row else None


# ─────────────────────────────────────────────────────────────
#  Main Frame
# ─────────────────────────────────────────────────────────────

class CashDrawerFrame(ctk.CTkFrame):
    def __init__(self, master, user: dict):
        super().__init__(master, fg_color="transparent")
        self.user = user
        self._build_ui()
        self._refresh()

    # ── Layout ───────────────────────────────────────────────

    def _build_ui(self):
        # Page header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            header, text="Cash Drawer  /  Shift Sessions",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")
        ctk.CTkButton(
            header, text="🔄  Refresh", height=34, width=110,
            fg_color=BG_CARD, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY, corner_radius=8,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self._refresh,
        ).pack(side="right")

        # ── Status Banner ────────────────────────────────────
        self.banner = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14,
                                    border_width=1, border_color=BORDER)
        self.banner.pack(fill="x", pady=(0, 10))
        self._banner_inner = ctk.CTkFrame(self.banner, fg_color="transparent")
        self._banner_inner.pack(fill="x", padx=20, pady=14)

        # ── Action Buttons Row ───────────────────────────────
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 10))

        self.open_btn = ctk.CTkButton(
            btn_row, text="🔓  Open Cash Drawer", height=44,
            fg_color=SUCCESS, hover_color=SUCCESS_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            corner_radius=10, command=self._open_drawer,
        )
        self.open_btn.pack(side="left", padx=(0, 8))

        self.cashin_btn = ctk.CTkButton(
            btn_row, text="💵  Cash In", height=44, width=130,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            corner_radius=10, command=lambda: self._add_movement("cash_in"),
        )
        self.cashin_btn.pack(side="left", padx=(0, 8))

        self.cashout_btn = ctk.CTkButton(
            btn_row, text="💸  Cash Out", height=44, width=130,
            fg_color=WARNING, hover_color="#9A7525",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            corner_radius=10, command=lambda: self._add_movement("cash_out"),
        )
        self.cashout_btn.pack(side="left", padx=(0, 8))

        self.close_btn = ctk.CTkButton(
            btn_row, text="🔒  Close Shift", height=44,
            fg_color=DANGER, hover_color=DANGER_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            corner_radius=10, command=self._close_drawer,
        )
        self.close_btn.pack(side="left")

        # ── Tab Bar ──────────────────────────────────────────
        tab_bar = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=10,
                                border_width=1, border_color=BORDER)
        tab_bar.pack(fill="x", pady=(0, 8))
        inner = ctk.CTkFrame(tab_bar, fg_color="transparent")
        inner.pack(padx=8, pady=6, anchor="w")

        self._tab_btns = {}
        for label, key in [
            ("📊  Session Summary", "summary"),
            ("📋  Transactions", "transactions"),
            ("💰  Cash Movements", "movements"),
            ("🕓  History", "history"),
        ]:
            btn = ctk.CTkButton(
                inner, text=label, height=34, width=175,
                fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
                text_color=TEXT_PRIMARY, corner_radius=8,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                command=lambda k=key: self._show_tab(k),
            )
            btn.pack(side="left", padx=(0, 6))
            self._tab_btns[key] = btn

        # Content area
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.pack(fill="both", expand=True)

    # ── Refresh ───────────────────────────────────────────────

    def _refresh(self):
        self._session = get_active_session(self.user["id"])
        self._rebuild_banner()
        self._update_buttons()
        self._show_tab(getattr(self, "_active_tab", "summary"))

    def _rebuild_banner(self):
        for w in self._banner_inner.winfo_children():
            w.destroy()

        s = self._session
        if s:
            # Green open banner
            ctk.CTkFrame(self.banner, fg_color=SUCCESS, height=4,
                          corner_radius=0).place(relx=0, rely=0, relwidth=1)
            left = ctk.CTkFrame(self._banner_inner, fg_color="transparent")
            left.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(
                left,
                text=f"🟢  SHIFT OPEN  —  {s['session_id']}",
                font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
                text_color=SUCCESS,
            ).pack(anchor="w")
            ctk.CTkLabel(
                left,
                text=f"Cashier: {s['full_name']}   |   Opened: {s['opened_at']}   |   Opening Cash: ₱{s['opening_cash']:,.2f}",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=TEXT_SECONDARY,
            ).pack(anchor="w", pady=(2, 0))
        else:
            ctk.CTkFrame(self.banner, fg_color=DANGER, height=4,
                          corner_radius=0).place(relx=0, rely=0, relwidth=1)
            ctk.CTkLabel(
                self._banner_inner,
                text="🔴  No active shift.  Open the cash drawer to begin accepting transactions.",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=TEXT_SECONDARY,
            ).pack(anchor="w")

    def _update_buttons(self):
        has = bool(self._session)
        self.open_btn.configure(state="disabled" if has else "normal")
        self.cashin_btn.configure(state="normal" if has else "disabled")
        self.cashout_btn.configure(state="normal" if has else "disabled")
        self.close_btn.configure(state="normal" if has else "disabled")

    # ── Tabs ─────────────────────────────────────────────────

    def _show_tab(self, key: str):
        self._active_tab = key
        for k, btn in self._tab_btns.items():
            btn.configure(fg_color=ACCENT if k == key else BG_CARD_ALT,
                           text_color="white" if k == key else TEXT_PRIMARY)
        for w in self._content.winfo_children():
            w.destroy()

        if key == "summary":
            SessionSummaryTab(self._content, self._session, self.user).pack(fill="both", expand=True)
        elif key == "transactions":
            TransactionsTab(self._content, self._session, self.user).pack(fill="both", expand=True)
        elif key == "movements":
            CashMovementsTab(self._content, self._session, self.user).pack(fill="both", expand=True)
        else:
            HistoryTab(self._content, self.user).pack(fill="both", expand=True)

    # ── Actions ──────────────────────────────────────────────

    def _open_drawer(self):
        # Block if any session is already open (even by another user)
        any_open = get_any_active_session()
        if any_open:
            msg_warning(
                self, "Session Already Open",
                f"A shift is already open by {any_open['full_name']} "
                f"({any_open['session_id']}).\n"
                "Close it before opening a new one.",
            )
            return
        OpenDrawerDialog(self, self.user, self._refresh)

    def _add_movement(self, move_type: str):
        if not self._session:
            msg_warning(self, "No Active Session", "Open the cash drawer first.")
            return
        CashMovementDialog(self, self._session, self.user, move_type, self._refresh)

    def _close_drawer(self):
        if not self._session:
            msg_warning(self, "No Active Session", "No open session found.")
            return
        CloseDrawerDialog(self, self._session, self.user, self._refresh)


# ─────────────────────────────────────────────────────────────
#  Tab — Session Summary
# ─────────────────────────────────────────────────────────────

class SessionSummaryTab(ctk.CTkFrame):
    def __init__(self, master, session, user):
        super().__init__(master, fg_color="transparent")
        self.session = session
        self.user    = user
        self._build()

    def _build(self):
        if not self.session:
            ctk.CTkLabel(
                self,
                text="No active session.  Open the cash drawer to start a shift.",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=TEXT_MUTED,
            ).pack(expand=True)
            return

        s  = self.session
        sid = s["id"]
        conn = get_connection()

        # Sales totals
        sales_row = conn.execute("""
            SELECT COUNT(*) as cnt, COALESCE(SUM(total),0) as total
            FROM sales_transactions WHERE session_id=?
        """, (sid,)).fetchone()

        # Service totals
        svc_row = conn.execute("""
            SELECT COUNT(*) as cnt, COALESCE(SUM(total),0) as total
            FROM service_transactions WHERE session_id=?
        """, (sid,)).fetchone()

        # Cash movements
        mov = conn.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN move_type='cash_in'  THEN amount ELSE 0 END),0) as total_in,
                COALESCE(SUM(CASE WHEN move_type='cash_out' THEN amount ELSE 0 END),0) as total_out
            FROM cash_movements WHERE session_id=?
        """, (sid,)).fetchone()
        conn.close()

        opening    = s["opening_cash"]
        sales_tot  = sales_row["total"]  if sales_row  else 0.0
        svc_tot    = svc_row["total"]    if svc_row    else 0.0
        cash_in    = mov["total_in"]     if mov        else 0.0
        cash_out   = mov["total_out"]    if mov        else 0.0
        expected   = opening + sales_tot + svc_tot + cash_in - cash_out

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # ── Session Info card ────────────────────────────────
        info_card = ctk.CTkFrame(scroll, fg_color=BG_CARD, corner_radius=12,
                                  border_width=1, border_color=BORDER)
        info_card.pack(fill="x", pady=(0, 10))
        ctk.CTkFrame(info_card, fg_color=ACCENT, height=3, corner_radius=0).pack(fill="x")

        hdr = ctk.CTkFrame(info_card, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(10, 2))
        ctk.CTkLabel(hdr, text="🗂️",
                     font=ctk.CTkFont(size=14), text_color=ACCENT).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(hdr, text="Session Information",
                     font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(side="left")

        grid = ctk.CTkFrame(info_card, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=(4, 14))
        for i in range(4):
            grid.columnconfigure(i, weight=1)

        fields = [
            ("Session ID",  s["session_id"]),
            ("Cashier",     s["full_name"]),
            ("Opened At",   s["opened_at"]),
            ("Status",      "🟢  Open"),
        ]
        for idx, (lbl, val) in enumerate(fields):
            col = idx * 2
            ctk.CTkLabel(grid, text=lbl,
                         font=ctk.CTkFont(family="Segoe UI", size=10),
                         text_color=TEXT_MUTED, anchor="w").grid(row=0, column=col, sticky="w", padx=(0, 4))
            ctk.CTkLabel(grid, text=val,
                         font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                         text_color=TEXT_PRIMARY, anchor="w").grid(row=1, column=col, sticky="w", padx=(0, 20))

        # ── Stat cards row ───────────────────────────────────
        stats_row = ctk.CTkFrame(scroll, fg_color="transparent")
        stats_row.pack(fill="x", pady=(0, 10))
        for i in range(5):
            stats_row.columnconfigure(i, weight=1)

        def _stat(parent, col, icon, label, value, color):
            card = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=12,
                                 border_width=1, border_color=BORDER)
            card.grid(row=0, column=col, sticky="nsew",
                      padx=(0, 8) if col < 4 else 0)
            ctk.CTkFrame(card, fg_color=color, height=3, corner_radius=0).pack(fill="x")
            ctk.CTkLabel(card, text=icon, font=ctk.CTkFont(size=18),
                          text_color=color).pack(pady=(10, 2))
            ctk.CTkLabel(card, text=value,
                          font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
                          text_color=color).pack()
            ctk.CTkLabel(card, text=label,
                          font=ctk.CTkFont(family="Segoe UI", size=10),
                          text_color=TEXT_MUTED).pack(pady=(2, 10))

        _stat(stats_row, 0, "💵", "Opening Cash",    f"₱{opening:,.2f}",   ACCENT)
        _stat(stats_row, 1, "🛒", "Product Sales",   f"₱{sales_tot:,.2f}", SUCCESS)
        _stat(stats_row, 2, "🔧", "Service Revenue", f"₱{svc_tot:,.2f}",   INFO)
        _stat(stats_row, 3, "💸", "Net Cash Moves",  f"₱{cash_in - cash_out:,.2f}",
              SUCCESS if cash_in >= cash_out else DANGER)
        _stat(stats_row, 4, "💰", "Expected Cash",   f"₱{expected:,.2f}",  WARNING)

        # ── Breakdown card ───────────────────────────────────
        brk_card = ctk.CTkFrame(scroll, fg_color=BG_CARD, corner_radius=12,
                                 border_width=1, border_color=BORDER)
        brk_card.pack(fill="x", pady=(0, 10))
        ctk.CTkFrame(brk_card, fg_color=SUCCESS, height=3, corner_radius=0).pack(fill="x")

        hdr2 = ctk.CTkFrame(brk_card, fg_color="transparent")
        hdr2.pack(fill="x", padx=16, pady=(10, 2))
        ctk.CTkLabel(hdr2, text="📈",
                     font=ctk.CTkFont(size=14), text_color=SUCCESS).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(hdr2, text="Cash Flow Breakdown",
                     font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(side="left")

        lines = [
            ("Opening Cash Float",              f"₱{opening:,.2f}",            TEXT_PRIMARY),
            (f"+ Product Sales  ({sales_row['cnt']} txns)",  f"₱{sales_tot:,.2f}",   SUCCESS),
            (f"+ Service Revenue  ({svc_row['cnt']} txns)",  f"₱{svc_tot:,.2f}",     INFO),
            ("+ Cash In",                       f"₱{cash_in:,.2f}",            SUCCESS),
            ("− Cash Out",                      f"₱{cash_out:,.2f}",           DANGER),
            ("= Expected Cash in Drawer",       f"₱{expected:,.2f}",           WARNING),
        ]
        for label, val, color in lines:
            row = ctk.CTkFrame(brk_card, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=1)
            ctk.CTkLabel(row, text=label,
                         font=ctk.CTkFont(family="Segoe UI", size=12),
                         text_color=TEXT_SECONDARY, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=val,
                         font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                         text_color=color, anchor="e").pack(side="right")
        # divider above total
        ctk.CTkFrame(brk_card, fg_color=BORDER, height=1).pack(fill="x", padx=16, pady=4)
        bot = ctk.CTkFrame(brk_card, fg_color=BG_CARD_ALT, corner_radius=8)
        bot.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkLabel(bot, text="Expected in Drawer",
                     font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                     text_color=TEXT_PRIMARY, anchor="w").pack(side="left", padx=12, pady=10)
        ctk.CTkLabel(bot, text=f"₱{expected:,.2f}",
                     font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
                     text_color=WARNING, anchor="e").pack(side="right", padx=12, pady=10)


# ─────────────────────────────────────────────────────────────
#  Tab — Transactions
# ─────────────────────────────────────────────────────────────

class TransactionsTab(ctk.CTkFrame):
    def __init__(self, master, session, user):
        super().__init__(master, fg_color="transparent")
        self.session = session
        self.user    = user
        self._build()

    def _build(self):
        if not self.session:
            ctk.CTkLabel(
                self,
                text="No active session.  Transactions will appear here once a shift is open.",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=TEXT_MUTED,
            ).pack(expand=True)
            return

        sid = self.session["id"]
        conn = get_connection()

        # Gather sales
        sales = conn.execute("""
            SELECT 'Product Sale' as type, transaction_number, total,
                   payment_method, created_at
            FROM sales_transactions WHERE session_id=?
            ORDER BY created_at DESC
        """, (sid,)).fetchall()

        # Gather services
        svcs = conn.execute("""
            SELECT 'Service' as type, transaction_number, total,
                   'cash' as payment_method, created_at
            FROM service_transactions WHERE session_id=?
            ORDER BY created_at DESC
        """, (sid,)).fetchall()
        conn.close()

        rows = sorted(
            [dict(r) for r in sales] + [dict(r) for r in svcs],
            key=lambda r: r["created_at"],
            reverse=True,
        )

        # Info label
        total_amt = sum(r["total"] for r in rows)
        ctk.CTkLabel(
            self,
            text=f"{len(rows)} transaction{'s' if len(rows) != 1 else ''}  —  Total: ₱{total_amt:,.2f}",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_SECONDARY, anchor="w",
        ).pack(anchor="w", pady=(0, 6))

        card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=12,
                             border_width=1, border_color=BORDER)
        card.pack(fill="both", expand=True)

        cols   = ("time", "txn", "type", "amount", "method")
        hdrs   = {"time": "Time", "txn": "Transaction #", "type": "Type",
                   "amount": "Amount", "method": "Payment"}
        widths = {"time": 140, "txn": 150, "type": 120, "amount": 110, "method": 100}

        tree = ttk.Treeview(card, columns=cols, show="headings", height=16)
        for col in cols:
            tree.heading(col, text=hdrs[col])
            tree.column(col, width=widths[col],
                         anchor="e" if col == "amount" else "w")

        sb = ttk.Scrollbar(card, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        style_treeview(tree)
        tree.tag_configure("service", foreground=INFO)
        tree.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        sb.pack(side="right", fill="y", pady=6)

        for i, row in enumerate(rows):
            tag = "service" if row["type"] == "Service" else ("evenrow" if i % 2 == 0 else "oddrow")
            tree.insert("", "end", tags=(tag,), values=(
                row["created_at"][11:19],
                row["transaction_number"],
                row["type"],
                f"₱{row['total']:,.2f}",
                (row["payment_method"] or "cash").title(),
            ))


# ─────────────────────────────────────────────────────────────
#  Tab — Cash Movements
# ─────────────────────────────────────────────────────────────

class CashMovementsTab(ctk.CTkFrame):
    def __init__(self, master, session, user):
        super().__init__(master, fg_color="transparent")
        self.session = session
        self.user    = user
        self._build()

    def _build(self):
        if not self.session:
            ctk.CTkLabel(
                self,
                text="No active session.  Cash movements will appear here once a shift is open.",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=TEXT_MUTED,
            ).pack(expand=True)
            return

        sid = self.session["id"]
        conn = get_connection()
        rows = conn.execute("""
            SELECT cm.*, u.full_name
            FROM cash_movements cm
            JOIN users u ON u.id = cm.recorded_by
            WHERE cm.session_id=?
            ORDER BY cm.created_at DESC
        """, (sid,)).fetchall()
        rows = [dict(r) for r in rows]

        totals = conn.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN move_type='cash_in'  THEN amount ELSE 0 END),0) as total_in,
                COALESCE(SUM(CASE WHEN move_type='cash_out' THEN amount ELSE 0 END),0) as total_out
            FROM cash_movements WHERE session_id=?
        """, (sid,)).fetchone()
        conn.close()

        # Totals row
        tot_row = ctk.CTkFrame(self, fg_color="transparent")
        tot_row.pack(fill="x", pady=(0, 8))
        tot_row.columnconfigure(0, weight=1)
        tot_row.columnconfigure(1, weight=1)

        for col, label, amt, color in [
            (0, "Total Cash In",  totals["total_in"],  SUCCESS),
            (1, "Total Cash Out", totals["total_out"], DANGER),
        ]:
            c = ctk.CTkFrame(tot_row, fg_color=BG_CARD, corner_radius=10,
                              border_width=1, border_color=BORDER)
            c.grid(row=0, column=col, sticky="nsew", padx=(0, 6) if col == 0 else 0)
            ctk.CTkFrame(c, fg_color=color, height=3, corner_radius=0).pack(fill="x")
            ctk.CTkLabel(c, text=label,
                          font=ctk.CTkFont(family="Segoe UI", size=11),
                          text_color=TEXT_MUTED).pack(pady=(8, 2))
            ctk.CTkLabel(c, text=f"₱{amt:,.2f}",
                          font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
                          text_color=color).pack(pady=(0, 8))

        # Table
        card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=12,
                             border_width=1, border_color=BORDER)
        card.pack(fill="both", expand=True)

        cols   = ("time", "type", "amount", "reason", "recorded_by")
        hdrs   = {"time": "Time", "type": "Type", "amount": "Amount",
                   "reason": "Reason", "recorded_by": "Recorded By"}
        widths = {"time": 140, "type": 100, "amount": 110, "reason": 260, "recorded_by": 130}

        tree = ttk.Treeview(card, columns=cols, show="headings", height=12)
        for col in cols:
            tree.heading(col, text=hdrs[col])
            tree.column(col, width=widths[col],
                         anchor="e" if col == "amount" else "w")

        sb = ttk.Scrollbar(card, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        style_treeview(tree)
        tree.tag_configure("cash_in",  foreground=SUCCESS)
        tree.tag_configure("cash_out", foreground=DANGER)
        tree.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        sb.pack(side="right", fill="y", pady=6)

        for i, row in enumerate(rows):
            tag = row["move_type"]
            tree.insert("", "end", tags=(tag,), values=(
                row["created_at"][11:19] if len(row["created_at"]) > 10 else row["created_at"],
                "💵 Cash In" if row["move_type"] == "cash_in" else "💸 Cash Out",
                f"₱{row['amount']:,.2f}",
                row["reason"],
                row["full_name"],
            ))

        if not rows:
            ctk.CTkLabel(
                self,
                text="No cash movements recorded this session.",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=TEXT_MUTED,
            ).pack(pady=8)


# ─────────────────────────────────────────────────────────────
#  Tab — History
# ─────────────────────────────────────────────────────────────

class HistoryTab(ctk.CTkFrame):
    def __init__(self, master, user):
        super().__init__(master, fg_color="transparent")
        self.user = user
        self._build()
        self._load()

    def _build(self):
        # Search row
        search_card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=10,
                                    border_width=1, border_color=BORDER)
        search_card.pack(fill="x", pady=(0, 8))
        inner = ctk.CTkFrame(search_card, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=8)

        self.search_var = ctk.StringVar()
        self.search_var.trace("w", lambda *_: self._load())
        ctk.CTkEntry(
            inner, textvariable=self.search_var,
            placeholder_text="🔍  Search by cashier, session ID...",
            height=36, fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=12), corner_radius=8,
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.status_var = ctk.StringVar(value="All")
        create_option_menu(
            inner, values=["All", "Open", "Closed"],
            variable=self.status_var, width=120,
            command=lambda *_: self._load(),
        ).pack(side="right")

        # Table
        card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=12,
                             border_width=1, border_color=BORDER)
        card.pack(fill="both", expand=True)

        cols   = ("session_id", "cashier", "date", "opened_at", "closed_at",
                   "opening", "closing", "expected", "variance", "status")
        hdrs   = {
            "session_id": "Session ID", "cashier": "Cashier",
            "date": "Date", "opened_at": "Opened", "closed_at": "Closed",
            "opening": "Opening", "closing": "Closing",
            "expected": "Expected", "variance": "Variance", "status": "Status",
        }
        widths = {
            "session_id": 145, "cashier": 130, "date": 90,
            "opened_at": 80, "closed_at": 80,
            "opening": 90, "closing": 90, "expected": 90, "variance": 90, "status": 70,
        }

        self.tree = ttk.Treeview(card, columns=cols, show="headings", height=14)
        for col in cols:
            self.tree.heading(col, text=hdrs[col])
            anchor = "e" if col in ("opening","closing","expected","variance") else "w"
            self.tree.column(col, width=widths[col], anchor=anchor)

        sb = ttk.Scrollbar(card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        style_treeview(self.tree)
        self.tree.tag_configure("open",     foreground=SUCCESS)
        self.tree.tag_configure("over",     foreground=SUCCESS)
        self.tree.tag_configure("short",    foreground=DANGER)
        self.tree.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        sb.pack(side="right", fill="y", pady=6)

        # Details button
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", pady=6)
        ctk.CTkButton(
            btn_row, text="📋  View Session Details", height=34, width=180,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color="white", corner_radius=8,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._view_details,
        ).pack(side="left")

    def _load(self):
        q      = f"%{self.search_var.get()}%"
        status = self.status_var.get().lower()

        conn   = get_connection()
        query  = """
            SELECT cd.*, u.full_name
            FROM cash_drawer cd
            JOIN users u ON u.id = cd.cashier_id
            WHERE (u.full_name LIKE ? OR cd.session_id LIKE ?)
        """
        params: list = [q, q]
        if status != "all":
            query += " AND cd.status = ?"
            params.append(status)
        query += " ORDER BY cd.opened_at DESC"
        rows = conn.execute(query, params).fetchall()
        conn.close()

        for c in self.tree.get_children():
            self.tree.delete(c)

        for row in rows:
            var = row["discrepancy"]
            if row["status"] == "open":
                tag = "open"
            elif var is None:
                tag = "evenrow"
            elif var > 0:
                tag = "over"
            elif var < 0:
                tag = "short"
            else:
                tag = "evenrow"

            self.tree.insert("", "end", iid=str(row["id"]), tags=(tag,), values=(
                row["session_id"] or "—",
                row["full_name"],
                row["shift_date"],
                row["opened_at"][11:16] if row["opened_at"] else "—",
                row["closed_at"][11:16] if row["closed_at"] else "—",
                f"₱{row['opening_cash']:,.2f}",
                f"₱{row['closing_cash']:,.2f}" if row["closing_cash"] is not None else "—",
                f"₱{row['expected_cash']:,.2f}" if row["expected_cash"] is not None else "—",
                (f"{'+'if var>=0 else ''}₱{var:,.2f}" if var is not None else "—"),
                row["status"].title(),
            ))

    def _view_details(self):
        sel = self.tree.selection()
        if not sel:
            msg_warning(self, "Select", "Please select a session to view.")
            return
        SessionDetailDialog(self, int(sel[0]))


# ─────────────────────────────────────────────────────────────
#  Dialog — Open Drawer
# ─────────────────────────────────────────────────────────────

class OpenDrawerDialog(ctk.CTkToplevel):
    def __init__(self, master, user: dict, callback):
        super().__init__(master)
        self.user     = user
        self.callback = callback
        style_dialog(self, "Open Cash Drawer", 460, 500)
        self._build()

    def _build(self):
        session_id = _generate_session_id()

        # Scrollable body so nothing ever gets clipped
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=24, pady=(16, 8))

        ctk.CTkLabel(
            scroll, text="🔓  Open Cash Drawer",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkLabel(
            scroll,
            text="Enter the starting cash float for this shift.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", pady=(0, 12))

        # Session ID (read-only display)
        ctk.CTkLabel(scroll, text="Session ID", anchor="w",
                     font=ctk.CTkFont(family="Segoe UI", size=12),
                     text_color=TEXT_SECONDARY).pack(fill="x", pady=(0, 3))
        sid_frame = ctk.CTkFrame(scroll, fg_color=BG_CARD_ALT, corner_radius=8,
                                  border_width=1, border_color=BORDER, height=38)
        sid_frame.pack(fill="x")
        sid_frame.pack_propagate(False)
        ctk.CTkLabel(sid_frame, text=session_id,
                     font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                     text_color=ACCENT, anchor="w").place(relx=0.03, rely=0.5, anchor="w")

        # Cashier (read-only)
        ctk.CTkLabel(scroll, text="Cashier", anchor="w",
                     font=ctk.CTkFont(family="Segoe UI", size=12),
                     text_color=TEXT_SECONDARY).pack(fill="x", pady=(10, 3))
        cf = ctk.CTkFrame(scroll, fg_color=BG_CARD_ALT, corner_radius=8,
                           border_width=1, border_color=BORDER, height=38)
        cf.pack(fill="x")
        cf.pack_propagate(False)
        ctk.CTkLabel(cf, text=self.user["full_name"],
                     font=ctk.CTkFont(family="Segoe UI", size=13),
                     text_color=TEXT_PRIMARY, anchor="w").place(relx=0.03, rely=0.5, anchor="w")

        # Opening float
        self.float_entry = create_dialog_entry(scroll, "Opening Cash Float  (\u20b1) *", "1000.00")
        self.float_entry.focus()

        # Notes
        self.notes_entry = create_dialog_entry(scroll, "Notes  (optional)", "")

        # Buttons pinned outside scroll so they are always visible
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=(0, 16))
        ctk.CTkButton(
            btn_row, text="Cancel", height=44, width=100,
            fg_color=BG_CARD, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_SECONDARY, corner_radius=10,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self.destroy,
        ).pack(side="left")
        ctk.CTkButton(
            btn_row,
            text="\U0001f513  Open Drawer",
            height=44, fg_color=SUCCESS, hover_color=SUCCESS_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            corner_radius=10, command=lambda: self._confirm(session_id),
        ).pack(side="right", fill="x", expand=True, padx=(10, 0))

    def _confirm(self, session_id: str):
        try:
            amount = float(self.float_entry.get().strip() or 0)
        except ValueError:
            msg_warning(self, "Invalid", "Enter a valid cash amount.")
            return
        notes = self.notes_entry.get().strip()
        conn  = get_connection()
        conn.execute("""
            INSERT INTO cash_drawer (session_id, cashier_id, opening_cash, notes)
            VALUES (?, ?, ?, ?)
        """, (session_id, self.user["id"], amount, notes or None))
        conn.commit()
        conn.close()
        log_cash_drawer(self.user["id"], self.user["username"], "OPEN_DRAWER",
                        session_ref=session_id, opening_cash=amount,
                        opened_at=datetime.now().isoformat(timespec="seconds"))
        log_audit(self.user["id"], self.user["username"], "CashDrawer", "OPEN_DRAWER",
                  new_value={"session": session_id, "opening_cash": amount})
        # Grab top-level reference before destroying this dialog
        top = self.master.winfo_toplevel()
        self.callback()
        self.destroy()
        # Navigate straight to Sales — shift has started
        if hasattr(top, "show_module"):
            top.show_module("sales")


# ─────────────────────────────────────────────────────────────
#  Dialog — Cash Movement (Cash In / Cash Out)
# ─────────────────────────────────────────────────────────────

class CashMovementDialog(ctk.CTkToplevel):
    def __init__(self, master, session: dict, user: dict, move_type: str, callback):
        super().__init__(master)
        self.session   = session
        self.user      = user
        self.move_type = move_type
        self.callback  = callback
        label  = "Cash In" if move_type == "cash_in" else "Cash Out"
        style_dialog(self, label, 420, 320)
        self._build(label)

    def _build(self, label: str):
        is_in = self.move_type == "cash_in"
        color = SUCCESS if is_in else DANGER
        icon  = "💵" if is_in else "💸"

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=28, pady=20)

        ctk.CTkLabel(
            form, text=f"{icon}  {label}",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=color,
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkLabel(
            form,
            text=f"Session: {self.session['session_id']}",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", pady=(0, 16))

        self.amount_entry = create_dialog_entry(form, "Amount  (₱) *", "")
        self.amount_entry.focus()
        self.reason_entry = create_dialog_entry(
            form,
            "Reason *",
            "Supplies Purchase" if not is_in else "Additional Float",
        )

        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.pack(fill="x", pady=(14, 0))
        ctk.CTkButton(
            btn_row, text="Cancel", height=44, width=100,
            fg_color=BG_CARD, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_SECONDARY, corner_radius=10,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self.destroy,
        ).pack(side="left")
        ctk.CTkButton(
            btn_row, text=f"{icon}  Record {label}", height=44,
            fg_color=color, hover_color=SUCCESS_HOVER if is_in else DANGER_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            corner_radius=10, command=self._save,
        ).pack(side="right", fill="x", expand=True, padx=(10, 0))

    def _save(self):
        reason = self.reason_entry.get().strip()
        if not reason:
            msg_warning(self, "Required", "Please enter a reason.")
            return
        try:
            amount = float(self.amount_entry.get().strip())
            if amount <= 0:
                raise ValueError
        except ValueError:
            msg_warning(self, "Invalid", "Enter a valid positive amount.")
            return

        conn = get_connection()
        conn.execute("""
            INSERT INTO cash_movements (session_id, move_type, amount, reason, recorded_by)
            VALUES (?, ?, ?, ?, ?)
        """, (self.session["id"], self.move_type, amount, reason, self.user["id"]))
        conn.commit()
        conn.close()
        label = "Cash In" if self.move_type == "cash_in" else "Cash Out"
        msg_success(self, "Recorded", f"{label} of ₱{amount:,.2f} recorded.")
        self.callback()
        self.destroy()


# ─────────────────────────────────────────────────────────────
#  Dialog — Close Drawer
# ─────────────────────────────────────────────────────────────

class CloseDrawerDialog(ctk.CTkToplevel):
    def __init__(self, master, session: dict, user: dict, callback):
        super().__init__(master)
        self.session  = session
        self.user     = user
        self.callback = callback
        style_dialog(self, "Close Shift", 480, 520)
        self._build()

    def _build(self):
        s   = self.session
        sid = s["id"]
        conn = get_connection()

        sales_total = conn.execute(
            "SELECT COALESCE(SUM(total),0) FROM sales_transactions WHERE session_id=?", (sid,)
        ).fetchone()[0]
        svc_total = conn.execute(
            "SELECT COALESCE(SUM(total),0) FROM service_transactions WHERE session_id=?", (sid,)
        ).fetchone()[0]
        mov = conn.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN move_type='cash_in'  THEN amount ELSE 0 END),0) as total_in,
                COALESCE(SUM(CASE WHEN move_type='cash_out' THEN amount ELSE 0 END),0) as total_out
            FROM cash_movements WHERE session_id=?
        """, (sid,)).fetchone()
        conn.close()

        cash_in  = mov["total_in"]
        cash_out = mov["total_out"]
        self._expected = s["opening_cash"] + sales_total + svc_total + cash_in - cash_out

        form = ctk.CTkScrollableFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=28, pady=20)

        ctk.CTkLabel(
            form, text="🔒  Close Shift",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=DANGER,
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            form, text=f"Session: {s['session_id']}",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", pady=(0, 14))

        # Summary card
        summary = ctk.CTkFrame(form, fg_color=BG_CARD_ALT, corner_radius=10,
                                border_width=1, border_color=BORDER)
        summary.pack(fill="x", pady=(0, 14))

        lines = [
            ("Opening Float",    f"₱{s['opening_cash']:,.2f}"),
            ("Product Sales",    f"₱{sales_total:,.2f}"),
            ("Service Revenue",  f"₱{svc_total:,.2f}"),
            ("+ Cash In",        f"₱{cash_in:,.2f}"),
            ("− Cash Out",       f"₱{cash_out:,.2f}"),
            ("Expected in Drawer", f"₱{self._expected:,.2f}"),
        ]
        for label, val in lines:
            row = ctk.CTkFrame(summary, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=1)
            ctk.CTkLabel(row, text=label,
                         font=ctk.CTkFont(family="Segoe UI", size=11),
                         text_color=TEXT_SECONDARY, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=val,
                         font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                         text_color=TEXT_PRIMARY, anchor="e").pack(side="right")
        ctk.CTkFrame(summary, fg_color=BORDER, height=1).pack(fill="x", padx=12, pady=4)
        exp_row = ctk.CTkFrame(summary, fg_color="transparent")
        exp_row.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(exp_row, text="Expected Cash",
                     font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                     text_color=TEXT_PRIMARY, anchor="w").pack(side="left")
        ctk.CTkLabel(exp_row, text=f"₱{self._expected:,.2f}",
                     font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                     text_color=WARNING, anchor="e").pack(side="right")

        # Actual count
        self.actual_entry = create_dialog_entry(
            form, "Actual Cash Count  (₱) *  — physically count the drawer", ""
        )
        self.actual_entry.focus()

        # Variance preview (updates live)
        self._variance_var = ctk.StringVar(value="Variance: enter actual count above")
        ctk.CTkLabel(
            form, textvariable=self._variance_var,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_MUTED, anchor="w",
        ).pack(anchor="w", pady=(4, 0))
        self.actual_entry.bind("<KeyRelease>", self._update_variance)

        # Notes
        self.notes_entry = create_dialog_entry(form, "Closing Notes  (optional)", "")

        # Buttons
        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.pack(fill="x", pady=(14, 0))
        ctk.CTkButton(
            btn_row, text="Cancel", height=44, width=100,
            fg_color=BG_CARD, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_SECONDARY, corner_radius=10,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self.destroy,
        ).pack(side="left")
        ctk.CTkButton(
            btn_row, text="🔒  Close Shift & Save", height=44,
            fg_color=DANGER, hover_color=DANGER_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            corner_radius=10, command=self._confirm,
        ).pack(side="right", fill="x", expand=True, padx=(10, 0))

    def _update_variance(self, _=None):
        try:
            actual   = float(self.actual_entry.get().strip())
            variance = actual - self._expected
            sign     = "+" if variance >= 0 else ""
            color    = SUCCESS if variance >= 0 else DANGER
            self._variance_var.set(
                f"Variance: {sign}₱{variance:,.2f}  "
                f"({'OVER' if variance > 0 else 'SHORT' if variance < 0 else 'BALANCED'})"
            )
        except ValueError:
            self._variance_var.set("Variance: enter actual count above")

    def _confirm(self):
        try:
            actual = float(self.actual_entry.get().strip())
        except ValueError:
            msg_warning(self, "Required", "Enter the actual cash count.")
            return

        variance = actual - self._expected
        notes    = self.notes_entry.get().strip()

        sign = "+" if variance >= 0 else ""
        status_msg = "OVER" if variance > 0 else "SHORT" if variance < 0 else "BALANCED"

        if not msg_question(
            self, "Confirm Close Shift",
            f"Close shift {self.session['session_id']}?\n\n"
            f"Expected:  ₱{self._expected:,.2f}\n"
            f"Actual:    ₱{actual:,.2f}\n"
            f"Variance:  {sign}₱{variance:,.2f}  ({status_msg})\n\n"
            "This action cannot be undone.",
        ):
            return

        conn = get_connection()
        conn.execute("""
            UPDATE cash_drawer
            SET closing_cash=?, expected_cash=?, discrepancy=?,
                closed_at=datetime('now','localtime'), status='closed',
                notes=COALESCE(notes||' | ', '') || ?
            WHERE id=?
        """, (actual, self._expected, variance,
              f"Closed by {self.user['full_name']}" + (f" — {notes}" if notes else ""),
              self.session["id"]))
        conn.commit()
        conn.close()

        log_cash_drawer(self.user["id"], self.user["username"], "CLOSE_DRAWER",
                        session_ref=self.session.get("session_id"),
                        opening_cash=self.session.get("opening_cash"),
                        closing_cash=actual,
                        expected_cash=self._expected,
                        actual_cash=actual,
                        difference=variance,
                        opened_at=self.session.get("opened_at"),
                        closed_at=datetime.now().isoformat(timespec="seconds"))
        log_audit(self.user["id"], self.user["username"], "CashDrawer", "CLOSE_DRAWER",
                  record_id=self.session["id"],
                  new_value={"expected": self._expected, "actual": actual, "variance": variance})

        if abs(variance) < 0.01:
            msg_success(self, "Shift Closed", f"Session closed. Drawer is BALANCED. ✅")
        elif variance > 0:
            msg_info(self, "Shift Closed — OVER",
                     f"Variance: +₱{variance:,.2f} OVER ⚠️\n"
                     f"Expected ₱{self._expected:,.2f}, counted ₱{actual:,.2f}.")
        else:
            msg_warning(self, "Shift Closed — SHORT",
                        f"Variance: ₱{variance:,.2f} SHORT ❗\n"
                        f"Expected ₱{self._expected:,.2f}, counted ₱{actual:,.2f}.")

        self.callback()
        self.destroy()


# ─────────────────────────────────────────────────────────────
#  Dialog — Session Detail (History)
# ─────────────────────────────────────────────────────────────

class SessionDetailDialog(ctk.CTkToplevel):
    def __init__(self, master, session_db_id: int):
        super().__init__(master)
        self.session_db_id = session_db_id
        style_dialog(self, "Session Details", 700, 560)
        self._build()

    def _build(self):
        conn = get_connection()
        s = dict(conn.execute("""
            SELECT cd.*, u.full_name
            FROM cash_drawer cd
            JOIN users u ON u.id = cd.cashier_id
            WHERE cd.id=?
        """, (self.session_db_id,)).fetchone())

        sales_row = conn.execute("""
            SELECT COUNT(*) as cnt, COALESCE(SUM(total),0) as total
            FROM sales_transactions WHERE session_id=?
        """, (self.session_db_id,)).fetchone()

        svc_row = conn.execute("""
            SELECT COUNT(*) as cnt, COALESCE(SUM(total),0) as total
            FROM service_transactions WHERE session_id=?
        """, (self.session_db_id,)).fetchone()

        movements = conn.execute("""
            SELECT cm.*, u.full_name
            FROM cash_movements cm
            JOIN users u ON u.id = cm.recorded_by
            WHERE cm.session_id=?
            ORDER BY cm.created_at
        """, (self.session_db_id,)).fetchall()
        conn.close()

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=16)

        # Header
        ctk.CTkLabel(
            body,
            text=f"Session: {s['session_id']}   —   {s['full_name']}",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w")
        status_color = SUCCESS if s["status"] == "open" else DANGER
        ctk.CTkLabel(
            body,
            text=f"Status: {s['status'].title()}   |   Date: {s['shift_date']}   |   "
                 f"Opened: {s['opened_at']}   |   "
                 f"Closed: {s['closed_at'] or '—'}",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=status_color,
        ).pack(anchor="w", pady=(2, 12))

        # Financials grid
        fin_card = ctk.CTkFrame(body, fg_color=BG_CARD_ALT, corner_radius=10,
                                 border_width=1, border_color=BORDER)
        fin_card.pack(fill="x", pady=(0, 10))

        rows_data = [
            ("Opening Cash",       f"₱{s['opening_cash']:,.2f}"),
            ("Product Sales",      f"₱{sales_row['total']:,.2f}  ({sales_row['cnt']} txns)"),
            ("Service Revenue",    f"₱{svc_row['total']:,.2f}  ({svc_row['cnt']} txns)"),
            ("Expected Cash",      f"₱{s['expected_cash']:,.2f}" if s["expected_cash"] is not None else "—"),
            ("Actual Cash Count",  f"₱{s['closing_cash']:,.2f}"  if s["closing_cash"]  is not None else "—"),
            ("Variance",           (
                f"{'+'if s['discrepancy']>=0 else ''}₱{s['discrepancy']:,.2f}"
                if s["discrepancy"] is not None else "—"
            )),
        ]
        for lbl, val in rows_data:
            r = ctk.CTkFrame(fin_card, fg_color="transparent")
            r.pack(fill="x", padx=12, pady=2)
            ctk.CTkLabel(r, text=lbl,
                         font=ctk.CTkFont(family="Segoe UI", size=12),
                         text_color=TEXT_SECONDARY, anchor="w").pack(side="left")
            var_color = TEXT_PRIMARY
            if lbl == "Variance" and s["discrepancy"] is not None:
                var_color = SUCCESS if s["discrepancy"] >= 0 else DANGER
            ctk.CTkLabel(r, text=val,
                         font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                         text_color=var_color, anchor="e").pack(side="right")

        # Cash movements mini-table
        ctk.CTkLabel(
            body, text="Cash Movements",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", pady=(8, 4))

        mv_card = ctk.CTkFrame(body, fg_color=BG_CARD, corner_radius=10,
                                border_width=1, border_color=BORDER)
        mv_card.pack(fill="x")

        if movements:
            cols = ("time", "type", "amount", "reason", "by")
            tree = ttk.Treeview(mv_card, columns=cols, show="headings", height=min(len(movements), 6))
            for col, hdr, w in [
                ("time", "Time", 120), ("type", "Type", 90), ("amount", "Amount", 90),
                ("reason", "Reason", 220), ("by", "Recorded By", 120),
            ]:
                tree.heading(col, text=hdr)
                tree.column(col, width=w, anchor="e" if col == "amount" else "w")
            style_treeview(tree)
            tree.tag_configure("cash_in",  foreground=SUCCESS)
            tree.tag_configure("cash_out", foreground=DANGER)
            tree.pack(fill="x", padx=6, pady=6)
            for m in movements:
                tag = m["move_type"]
                tree.insert("", "end", tags=(tag,), values=(
                    m["created_at"][11:19] if len(m["created_at"]) > 10 else m["created_at"],
                    "Cash In" if m["move_type"] == "cash_in" else "Cash Out",
                    f"₱{m['amount']:,.2f}",
                    m["reason"],
                    m["full_name"],
                ))
        else:
            ctk.CTkLabel(mv_card, text="No cash movements recorded.",
                         font=ctk.CTkFont(family="Segoe UI", size=12),
                         text_color=TEXT_MUTED).pack(pady=10)

        if s.get("notes"):
            ctk.CTkLabel(
                body,
                text=f"Notes: {s['notes']}",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=TEXT_MUTED, wraplength=620, justify="left", anchor="w",
            ).pack(anchor="w", pady=(10, 0))

        ctk.CTkButton(
            self, text="Close", height=38, width=120,
            fg_color=BG_CARD, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_SECONDARY, corner_radius=8,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self.destroy,
        ).pack(pady=(0, 12))