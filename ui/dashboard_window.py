import customtkinter as ctk
import datetime
from ui.theme import (
    BG_DARK, BG_CARD, BG_CARD_ALT, BG_INPUT, BG_HOVER, BORDER,
    ACCENT, ACCENT_HOVER, ACCENT_LIGHT, ACCENT_SUBTLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    SUCCESS, DANGER, INFO, WARNING,
    SIDEBAR_BG, SIDEBAR_ACTIVE, SIDEBAR_HOVER,
    style_treeview, insert_with_stripes, create_stat_card,
    msg_info, msg_warning, msg_error, msg_success, msg_question
)
from security import log_login_event, SESSION_TIMEOUT_MIN


# ── Navigation structure ────────────────────────────────────────────────────
_NAV_GROUPS = [
    ("OVERVIEW", [
        ("Dashboard",       "dashboard",   "🏠"),
    ]),
    ("TRANSACTIONS", [
        ("Sales",           "sales",       "💰"),
        ("Services",        "services",    "🔧"),
    ]),
    ("INVENTORY", [
        ("Inventory",        "inventory",  "📦"),
        ("Stock In",         "stock_in",   "📥"),
        ("Stock Adjustment", "stock_adj",  "⚖️"),
    ]),
    ("MANAGEMENT", [
        ("Approvals",       "approvals",   "✅"),
        ("Cash Drawer",     "cash_drawer", "🗄"),
        ("Expenses",        "expenses",    "📋"),
        ("Reports",         "reports",     "📊"),
        ("User Management", "users",       "👤"),
        ("Backup",          "backup",      "💾"),
    ]),
]

_ALLOWED = {
    "owner":   {"dashboard","sales","services","inventory","stock_in","stock_adj",
                "approvals","cash_drawer","expenses","reports","users","backup"},
    "cashier": {"dashboard","sales","services","inventory","stock_in","stock_adj","cash_drawer"},
}

_MODULE_LABELS = {
    "dashboard": "Dashboard",    "sales": "Sales",
    "services":  "Services",     "inventory": "Inventory",
    "stock_in":  "Stock In",     "stock_adj": "Stock Adjustment",
    "approvals": "Approvals",    "cash_drawer": "Cash Drawer",
    "expenses":  "Expenses",     "reports": "Reports",
    "users":     "User Management", "backup": "Backup",
}


class DashboardWindow(ctk.CTkToplevel):
    def __init__(self, master, user: dict):
        super().__init__(master)
        self.master   = master
        self.user     = user
        self.current_frame = None

        self.title(f"VMDC Motor Parts — {user['full_name']} ({user['role'].title()})")
        self.geometry("1280x750")
        self.minsize(1080, 680)
        self.configure(fg_color=BG_DARK)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.update_idletasks()
        x = (self.winfo_screenwidth()  // 2) - (1280 // 2)
        y = (self.winfo_screenheight() // 2) - (750  // 2)
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

        self._build_ui()
        self.show_module("dashboard")

        # Session inactivity timeout
        self._last_activity = datetime.datetime.now()
        self._timeout_ms    = SESSION_TIMEOUT_MIN * 60 * 1000
        self.bind_all("<Motion>",   self._reset_activity)
        self.bind_all("<KeyPress>", self._reset_activity)
        self.bind_all("<Button>",   self._reset_activity)
        self._check_session_timeout()

    # ── Layout skeleton ────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()

        # Right side: page area
        self.content_area = ctk.CTkFrame(self, fg_color=BG_DARK, corner_radius=0)
        self.content_area.grid(row=0, column=1, sticky="nsew")
        self.content_area.grid_rowconfigure(0, weight=1)
        self.content_area.grid_columnconfigure(0, weight=1)

        # Container where each module frame is placed
        self._page_area = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self._page_area.grid(row=0, column=0, sticky="nsew")

    # ── Sidebar ────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=256, fg_color=SIDEBAR_BG, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(1, weight=1)
        self.sidebar.grid_columnconfigure(0, weight=1)

        # ── Logo ──────────────────────────────────────────────
        logo_frame = ctk.CTkFrame(self.sidebar, fg_color=BG_DARK,
                                   corner_radius=0, height=88)
        logo_frame.grid(row=0, column=0, sticky="ew")
        logo_frame.grid_propagate(False)

        logo_inner = ctk.CTkFrame(logo_frame, fg_color="transparent")
        logo_inner.place(relx=0.5, rely=0.5, anchor="center")

        icon_box = ctk.CTkFrame(logo_inner, fg_color=ACCENT,
                                 width=40, height=40, corner_radius=10)
        icon_box.pack(side="left", padx=(0, 10))
        icon_box.pack_propagate(False)
        ctk.CTkLabel(icon_box, text="⚙", font=ctk.CTkFont(size=22),
                     text_color="white").pack(expand=True)

        logo_text = ctk.CTkFrame(logo_inner, fg_color="transparent")
        logo_text.pack(side="left")
        ctk.CTkLabel(logo_text, text="VMDC",
                     font=ctk.CTkFont(family="Segoe UI", size=19, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(anchor="w")
        ctk.CTkLabel(logo_text, text="Motor Parts System",
                     font=ctk.CTkFont(family="Segoe UI", size=9),
                     text_color=TEXT_MUTED).pack(anchor="w")

        # Accent stripe at bottom of logo area
        ctk.CTkFrame(self.sidebar, fg_color=ACCENT, height=2,
                     corner_radius=0).grid(row=0, column=0, sticky="sew")

        # ── Scrollable nav ────────────────────────────────────
        nav_scroll = ctk.CTkScrollableFrame(
            self.sidebar, fg_color=SIDEBAR_BG, corner_radius=0,
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=ACCENT_LIGHT,
        )
        nav_scroll.grid(row=1, column=0, sticky="nsew")

        # User card
        self._build_user_card(nav_scroll)

        # Grouped navigation
        allowed = _ALLOWED.get(self.user["role"], set())
        self.nav_buttons = {}

        for group_label, items in _NAV_GROUPS:
            visible = [(l, k, i) for l, k, i in items if k in allowed]
            if not visible:
                continue
            # Group label + separator
            grp = ctk.CTkFrame(nav_scroll, fg_color="transparent")
            grp.pack(fill="x", padx=12, pady=(10, 2))
            ctk.CTkFrame(grp, fg_color=BORDER, height=1).pack(fill="x", pady=(0, 5))
            ctk.CTkLabel(grp, text=group_label,
                         font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
                         text_color=TEXT_MUTED, anchor="w").pack(fill="x", padx=2)

            for label, key, icon in visible:
                btn = ctk.CTkButton(
                    nav_scroll,
                    text=f"  {icon}   {label}",
                    anchor="w", height=40,
                    fg_color="transparent", hover_color=SIDEBAR_HOVER,
                    text_color=TEXT_SECONDARY,
                    font=ctk.CTkFont(family="Segoe UI", size=12),
                    corner_radius=8,
                    command=lambda k=key: self.show_module(k),
                )
                btn.pack(fill="x", padx=8, pady=1)
                self.nav_buttons[key] = btn

        ctk.CTkFrame(nav_scroll, fg_color="transparent", height=8).pack()

        # ── Logout (pinned bottom) ────────────────────────────
        logout_row = ctk.CTkFrame(self.sidebar, fg_color=SIDEBAR_BG, corner_radius=0)
        logout_row.grid(row=2, column=0, sticky="ew")

        ctk.CTkFrame(logout_row, fg_color=BORDER, height=1).pack(fill="x", padx=12)
        ctk.CTkButton(
            logout_row, text="  🚪   Logout", anchor="w",
            height=44, fg_color="transparent", hover_color="#F0DCDC",
            text_color=DANGER,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            corner_radius=8, command=self.logout,
        ).pack(fill="x", padx=8, pady=(6, 10))

    def _build_user_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=10,
                             border_width=1, border_color=BORDER)
        card.pack(fill="x", padx=12, pady=(12, 4))

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=10)

        # Avatar
        initials = "".join(w[0].upper() for w in self.user["full_name"].split()[:2])
        avatar = ctk.CTkFrame(inner, fg_color=ACCENT, width=38, height=38, corner_radius=8)
        avatar.pack(side="left", padx=(0, 10))
        avatar.pack_propagate(False)
        ctk.CTkLabel(avatar, text=initials,
                     font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                     text_color="white").pack(expand=True)

        # Name + role
        info = ctk.CTkFrame(inner, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(info, text=self.user["full_name"],
                     font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                     text_color=TEXT_PRIMARY, anchor="w").pack(fill="x")
        ctk.CTkLabel(info, text=self.user["role"].title(),
                     font=ctk.CTkFont(family="Segoe UI", size=10),
                     text_color=TEXT_MUTED, anchor="w").pack(fill="x")

    # ── Module routing ─────────────────────────────────────────────────────

    def show_module(self, key: str):
        # Highlight active nav button
        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.configure(
                    fg_color=SIDEBAR_ACTIVE, text_color=ACCENT,
                    font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                )
            else:
                btn.configure(
                    fg_color="transparent", text_color=TEXT_SECONDARY,
                    font=ctk.CTkFont(family="Segoe UI", size=12),
                )

        # Swap content
        if self.current_frame:
            self.current_frame.destroy()

        frame = ctk.CTkFrame(self._page_area, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=24, pady=(10, 12))
        self.current_frame = frame

        if key == "dashboard":
            self._show_dashboard(frame)
        elif key == "sales":
            from ui.sales_window import SalesFrame
            SalesFrame(frame, self.user).pack(fill="both", expand=True)
        elif key == "inventory":
            from ui.inventory_window import InventoryFrame
            InventoryFrame(frame, self.user).pack(fill="both", expand=True)
        elif key == "stock_in":
            from ui.stockin_window import StockInFrame
            StockInFrame(frame, self.user).pack(fill="both", expand=True)
        elif key == "stock_adj":
            from ui.stock_adjustment_window import StockAdjustmentFrame
            StockAdjustmentFrame(frame, self.user).pack(fill="both", expand=True)
        elif key == "approvals":
            from ui.approval_management_window import ApprovalManagementFrame
            ApprovalManagementFrame(frame, self.user).pack(fill="both", expand=True)
        elif key == "services":
            from ui.services_window import ServicesFrame
            ServicesFrame(frame, self.user).pack(fill="both", expand=True)
        elif key == "reports":
            from ui.reports_window import ReportsFrame
            ReportsFrame(frame, self.user).pack(fill="both", expand=True)
        elif key == "backup":
            from ui.backup_window import BackupFrame
            BackupFrame(frame, self.user).pack(fill="both", expand=True)
        elif key == "cash_drawer":
            from ui.cashdrawer_window import CashDrawerFrame
            CashDrawerFrame(frame, self.user).pack(fill="both", expand=True)
        elif key == "expenses":
            from ui.expenses_window import ExpensesFrame
            ExpensesFrame(frame, self.user).pack(fill="both", expand=True)
        elif key == "users":
            from ui.users_window import UsersFrame
            UsersFrame(frame, self.user).pack(fill="both", expand=True)
        else:
            ctk.CTkLabel(frame, text=f"{key.title()} module coming soon.",
                         font=ctk.CTkFont(size=14),
                         text_color=TEXT_SECONDARY).pack(pady=40)

    # ── Dashboard view ─────────────────────────────────────────────────────

    def _show_dashboard(self, frame):
        from database import get_connection
        from tkinter import ttk

        conn = get_connection()
        total_products    = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        low_stock         = conn.execute(
            "SELECT COUNT(*) FROM products WHERE current_stock <= low_stock_threshold"
        ).fetchone()[0]
        today_sales       = conn.execute(
            "SELECT COALESCE(SUM(total),0) FROM sales_transactions "
            "WHERE date(created_at)=date('now','localtime')"
        ).fetchone()[0]
        today_txn         = conn.execute(
            "SELECT COUNT(*) FROM sales_transactions "
            "WHERE date(created_at)=date('now','localtime')"
        ).fetchone()[0]
        pending_approvals = conn.execute(
            "SELECT COUNT(*) FROM stock_update_requests WHERE status='pending'"
        ).fetchone()[0]
        pending_stockin   = conn.execute(
            "SELECT COUNT(*) FROM stock_in WHERE status='pending'"
        ).fetchone()[0]
        conn.close()

        # ── Greeting header ───────────────────────────────────
        now    = datetime.datetime.now()
        hour   = now.hour
        if hour < 12:
            greeting = "Good morning"
        elif hour < 17:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"

        first_name = self.user["full_name"].split()[0]

        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.pack(fill="x", pady=(0, 8))

        left_hdr = ctk.CTkFrame(hdr, fg_color="transparent")
        left_hdr.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            left_hdr,
            text=f"{greeting}, {first_name}! 👋",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=TEXT_PRIMARY, anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            left_hdr,
            text=f"Here's your business overview for {now.strftime('%B %d, %Y')}",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_MUTED, anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        ctk.CTkButton(
            hdr, text="↻  Refresh", width=100, height=32,
            fg_color=BG_CARD, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=8,
            command=lambda: self.show_module("dashboard"),
        ).pack(side="right")

        # ── Pending approvals banner (owner only) ─────────────
        total_pending = pending_approvals + pending_stockin
        if self.user["role"] == "owner" and total_pending > 0:
            banner = ctk.CTkFrame(frame, fg_color="#FFF3CD", corner_radius=10,
                                   border_width=1, border_color=WARNING)
            banner.pack(fill="x", pady=(0, 12))

            bi = ctk.CTkFrame(banner, fg_color="transparent")
            bi.pack(fill="x", padx=14, pady=10)

            # Warning circle icon
            ic = ctk.CTkFrame(bi, fg_color=WARNING, width=28, height=28, corner_radius=14)
            ic.pack(side="left", padx=(0, 10))
            ic.pack_propagate(False)
            ctk.CTkLabel(ic, text="!", font=ctk.CTkFont(size=14, weight="bold"),
                         text_color="white").pack(expand=True)

            msg_col = ctk.CTkFrame(bi, fg_color="transparent")
            msg_col.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(
                msg_col, text="Pending Approvals Require Your Attention",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color="#7A5200", anchor="w",
            ).pack(anchor="w")
            detail_parts = []
            if pending_approvals > 0:
                detail_parts.append(
                    f"{pending_approvals} stock request{'s' if pending_approvals != 1 else ''}"
                )
            if pending_stockin > 0:
                detail_parts.append(
                    f"{pending_stockin} stock-in deliver{'ies' if pending_stockin != 1 else 'y'}"
                )
            ctk.CTkLabel(
                msg_col, text="  •  ".join(detail_parts),
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color="#8A6A00", anchor="w",
            ).pack(anchor="w", pady=(2, 0))

            ctk.CTkButton(
                bi, text="Review Now →", height=30, width=124,
                fg_color=WARNING, hover_color="#C8860A",
                text_color="white", corner_radius=8,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                command=lambda: self.show_module("approvals"),
            ).pack(side="right")

        # ── Stat cards ────────────────────────────────────────
        cards_frame = ctk.CTkFrame(frame, fg_color="transparent")
        cards_frame.pack(fill="x", pady=(0, 8))

        stats = [
            ("Today's Sales",    f"₱{today_sales:,.2f}", ACCENT,  "💰"),
            ("Transactions",     str(today_txn),          SUCCESS, "🧾"),
            ("Total Products",   str(total_products),     INFO,    "📦"),
            ("Low Stock Alerts", str(low_stock),
             DANGER if low_stock > 0 else TEXT_MUTED, "⚠️"),
        ]
        if self.user["role"] == "owner":
            stats.append((
                "Pending Approvals", str(total_pending),
                WARNING if total_pending > 0 else TEXT_MUTED, "📋",
            ))

        for i, (label, value, color, icon) in enumerate(stats):
            card = self._stat_card(cards_frame, label, value, color, icon)
            card.grid(row=0, column=i, padx=(0 if i == 0 else 8), sticky="nsew")
            cards_frame.grid_columnconfigure(i, weight=1)

        # ── Quick actions (owner only) ────────────────────────
        if self.user["role"] == "owner":
            qa = ctk.CTkFrame(frame, fg_color=BG_CARD, corner_radius=12,
                               border_width=1, border_color=BORDER)
            qa.pack(fill="x", pady=(0, 8))

            qa_inner = ctk.CTkFrame(qa, fg_color="transparent")
            qa_inner.pack(fill="x", padx=14, pady=7)

            ctk.CTkLabel(
                qa_inner, text="QUICK ACTIONS",
                font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
                text_color=TEXT_MUTED,
            ).pack(side="left", padx=(0, 14))

            for lbl, key in [
                ("💰  New Sale",  "sales"),
                ("📥  Stock In",  "stock_in"),
                ("📊  Reports",   "reports"),
                ("👤  Users",     "users"),
            ]:
                ctk.CTkButton(
                    qa_inner, text=lbl, height=30, width=112,
                    fg_color=ACCENT_SUBTLE, hover_color=SIDEBAR_ACTIVE,
                    border_width=1, border_color=BORDER,
                    text_color=TEXT_SECONDARY,
                    font=ctk.CTkFont(family="Segoe UI", size=11),
                    corner_radius=8,
                    command=lambda k=key: self.show_module(k),
                ).pack(side="left", padx=(0, 6))

        # ── Recent Transactions (full width) ────────────────
        bottom = ctk.CTkFrame(frame, fg_color="transparent")
        bottom.pack(fill="both", expand=True)
        bottom.columnconfigure(0, weight=1)
        bottom.rowconfigure(0, weight=1)

        left_col = ctk.CTkFrame(bottom, fg_color="transparent")
        left_col.grid(row=0, column=0, sticky="nsew")
        left_col.rowconfigure(1, weight=1)
        left_col.columnconfigure(0, weight=1)

        sec_l = ctk.CTkFrame(left_col, fg_color="transparent")
        sec_l.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(
            sec_l, text="Recent Transactions",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")
        ctk.CTkLabel(
            sec_l, text="Today",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
        ).pack(side="left", padx=(8, 0))


        tbl_frame = ctk.CTkFrame(left_col, fg_color=BG_CARD, corner_radius=12,
                                  border_width=1, border_color=BORDER)
        tbl_frame.grid(row=1, column=0, sticky="nsew")

        cols    = ("txn", "cashier", "total", "date")
        headers = ["Transaction #", "Cashier", "Total", "Date/Time"]
        tree = ttk.Treeview(tbl_frame, columns=cols, show="headings", height=12)
        for col, h in zip(cols, headers):
            tree.heading(col, text=h)
            tree.column(col, width=160)
        tree.column("total", anchor="e", width=100)
        tree.column("date",  anchor="center", width=130)
        style_treeview(tree)
        tree.pack(fill="both", expand=True, padx=6, pady=6)

        conn = get_connection()
        rows = conn.execute("""
            SELECT st.transaction_number, u.full_name, st.total, st.created_at
            FROM sales_transactions st
            JOIN users u ON u.id = st.cashier_id
            ORDER BY st.created_at DESC LIMIT 8
        """).fetchall()
        conn.close()

        if not rows:
            tree.pack_forget()
            empty = ctk.CTkFrame(tbl_frame, fg_color="transparent")
            empty.pack(expand=True)
            ctk.CTkLabel(empty, text="📭", font=ctk.CTkFont(size=34)).pack(pady=(28, 6))
            ctk.CTkLabel(
                empty, text="No transactions yet today",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=TEXT_MUTED,
            ).pack(pady=(0, 28))
        else:
            for row in rows:
                vals = (row["transaction_number"], row["full_name"],
                        f"₱{row['total']:,.2f}", row["created_at"])
                insert_with_stripes(tree, vals)

    # ── Stat card widget ───────────────────────────────────────────────────

    def _stat_card(self, parent, label: str, value: str, color: str, icon: str):
        """Compact stat card matching the report panel style."""
        card = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=12,
                             border_width=1, border_color=BORDER)

        ctk.CTkFrame(card, fg_color=color, height=3, corner_radius=2).pack(
            fill="x", padx=12, pady=(8, 0))
        ctk.CTkLabel(card, text=icon,
                     font=ctk.CTkFont(size=16), text_color=color).pack(pady=(6, 0))
        ctk.CTkLabel(card, text=label,
                     font=ctk.CTkFont(family="Segoe UI", size=10),
                     text_color=TEXT_MUTED).pack()
        ctk.CTkLabel(card, text=value,
                     font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(pady=(2, 8))
        return card

    # ── Session / activity ─────────────────────────────────────────────────

    def _reset_activity(self, event=None):
        self._last_activity = datetime.datetime.now()

    def _check_session_timeout(self):
        try:
            elapsed = (datetime.datetime.now() - self._last_activity).total_seconds() * 1000
            if elapsed >= self._timeout_ms:
                self._session_expired()
                return
            self.after(30_000, self._check_session_timeout)
        except Exception:
            pass

    def _session_expired(self):
        log_login_event(self.user.get("id"), self.user.get("username"), "SESSION_TIMEOUT")
        try:
            self.destroy()
        except Exception:
            pass
        from ui.login_window import LoginWindow
        login = LoginWindow(self.master)
        msg_info(login, "Session Expired",
                 "Session expired due to inactivity.\nPlease log in again.")

    def logout(self):
        if msg_question(self, "Logout", "Are you sure you want to logout?"):
            log_login_event(self.user.get("id"), self.user.get("username"), "LOGOUT")
            self.destroy()
            from ui.login_window import LoginWindow
            login = LoginWindow(self.master)
            login.mainloop()

    def on_close(self):
        if msg_question(self, "Exit", "Are you sure you want to exit VMDC System?"):
            self.master.destroy()