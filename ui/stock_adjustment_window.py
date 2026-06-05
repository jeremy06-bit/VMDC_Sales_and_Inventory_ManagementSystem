"""
VMDC Motor Parts — Stock Adjustment Window
==========================================
Allows staff to submit stock adjustment requests (Add / Deduct).
All adjustments go through the approval workflow:
  • A stock_update_requests row is created with status = 'pending'
  • actual inventory is NOT changed until owner approves
History tab shows all past adjustments with status.
"""

import customtkinter as ctk
from tkinter import ttk

from database import get_connection
from security import log_audit
from ui.theme import (
    BG_DARK, BG_CARD, BG_CARD_ALT, BG_INPUT, BG_HOVER, BORDER,
    ACCENT, ACCENT_HOVER, ACCENT_LIGHT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    SUCCESS, SUCCESS_HOVER, DANGER, WARNING,
    style_treeview, Paginator,
    create_dialog_entry, create_dialog_button, style_dialog,
    create_option_menu,
    msg_info, msg_warning, msg_error, msg_success, msg_question,
)

ADJUSTMENT_REASONS = [
    "Damaged / Defective",
    "Expired Product",
    "Inventory Count Correction",
    "Loss / Theft",
    "Return to Supplier",
    "Other",
]


class StockAdjustmentFrame(ctk.CTkFrame):
    def __init__(self, master, user: dict):
        super().__init__(master, fg_color="transparent")
        self.user = user
        self._build_ui()
        self._show_tab("new")

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            header, text="Stock Adjustment",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        tab_bar = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=10,
                                border_width=1, border_color=BORDER)
        tab_bar.pack(fill="x", pady=(0, 10))
        inner = ctk.CTkFrame(tab_bar, fg_color="transparent")
        inner.pack(padx=8, pady=6, anchor="w")

        self._tab_btns = {}
        for label, key in [("📝  New Adjustment", "new"), ("📋  Adjustment History", "history")]:
            btn = ctk.CTkButton(
                inner, text=label, height=34, width=200,
                fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
                text_color=TEXT_PRIMARY, corner_radius=8,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                command=lambda k=key: self._show_tab(k),
            )
            btn.pack(side="left", padx=(0, 6))
            self._tab_btns[key] = btn

        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.pack(fill="both", expand=True)

    def _show_tab(self, key: str):
        for k, btn in self._tab_btns.items():
            btn.configure(
                fg_color=ACCENT if k == key else BG_CARD_ALT,
                text_color="white" if k == key else TEXT_PRIMARY,
            )
        for child in self._content.winfo_children():
            child.destroy()
        if key == "new":
            NewAdjustmentForm(self._content, self.user).pack(fill="both", expand=True)
        else:
            AdjustmentHistoryTable(self._content, self.user).pack(fill="both", expand=True)


class NewAdjustmentForm(ctk.CTkFrame):
    def __init__(self, master, user: dict):
        super().__init__(master, fg_color="transparent")
        self.user = user
        self._products = self._load_products()
        self._selected_product = None
        self._build()

    def _load_products(self):
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, code, name, current_stock FROM products ORDER BY name"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # LEFT: product selection
        left = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14,
                             border_width=1, border_color=BORDER)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        sl = ctk.CTkScrollableFrame(left, fg_color="transparent")
        sl.pack(fill="both", expand=True, padx=16, pady=14)

        ctk.CTkLabel(sl, text="Select Product",
                      font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
                      text_color=TEXT_PRIMARY).pack(anchor="w", pady=(0, 10))

        self.search_var = ctk.StringVar()
        self.search_var.trace("w", self._filter_products)
        ctk.CTkEntry(
            sl, textvariable=self.search_var,
            placeholder_text="🔍 Search product...",
            height=36, fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=12), corner_radius=8,
        ).pack(fill="x", pady=(0, 6))

        self.product_combo = ttk.Combobox(sl, state="readonly", font=("Segoe UI", 11))
        self.product_combo.pack(fill="x", pady=(0, 8))

        # Initialize display vars BEFORE _fill_combo so that _on_product_select
        # (called automatically during initial population) can safely set them.
        self.prod_name_var  = ctk.StringVar(value="—")
        self.prod_code_var  = ctk.StringVar(value="—")
        self.prod_stock_var = ctk.StringVar(value="—")

        # Also pre-initialise adj_type_var and qty_entry so that
        # _compute_new_qty (triggered by _on_product_select) doesn't crash.
        self.adj_type_var = ctk.StringVar(value="Deduct")
        self.qty_entry    = None   # will be replaced by the real widget below

        self._fill_combo(self._products)
        self.product_combo.bind("<<ComboboxSelected>>", self._on_product_select)

        info_frame = ctk.CTkFrame(sl, fg_color=BG_CARD_ALT, corner_radius=10,
                                   border_width=1, border_color=BORDER)
        info_frame.pack(fill="x", pady=(0, 14))

        for lbl, var in [("Product Name", self.prod_name_var),
                          ("Product Code", self.prod_code_var),
                          ("Current Stock", self.prod_stock_var)]:
            rf = ctk.CTkFrame(info_frame, fg_color="transparent")
            rf.pack(fill="x", padx=12, pady=4)
            ctk.CTkLabel(rf, text=lbl + ":", font=ctk.CTkFont(size=11),
                          text_color=TEXT_MUTED, width=110, anchor="w").pack(side="left")
            ctk.CTkLabel(rf, textvariable=var,
                          font=ctk.CTkFont(size=11, weight="bold"),
                          text_color=TEXT_PRIMARY, anchor="w").pack(side="left")

        # RIGHT: adjustment details
        right = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14,
                              border_width=1, border_color=BORDER)
        right.grid(row=0, column=1, sticky="nsew")

        sr = ctk.CTkScrollableFrame(right, fg_color="transparent")
        sr.pack(fill="both", expand=True, padx=16, pady=14)

        ctk.CTkLabel(sr, text="Adjustment Details",
                      font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
                      text_color=TEXT_PRIMARY).pack(anchor="w", pady=(0, 10))

        ctk.CTkLabel(sr, text="Adjustment Type *", anchor="w",
                      font=ctk.CTkFont(size=12), text_color=TEXT_SECONDARY).pack(fill="x", pady=(0, 3))

        self.adj_type_var = ctk.StringVar(value="Deduct")  # already set above; kept for clarity
        type_row = ctk.CTkFrame(sr, fg_color="transparent")
        type_row.pack(fill="x", pady=(0, 12))
        for lbl, val, col in [("➕  Add", "Add", SUCCESS), ("➖  Deduct", "Deduct", DANGER)]:
            ctk.CTkRadioButton(
                type_row, text=lbl, variable=self.adj_type_var, value=val,
                font=ctk.CTkFont(size=13), text_color=TEXT_PRIMARY,
                fg_color=col, hover_color=col, command=self._compute_new_qty,
            ).pack(side="left", padx=(0, 24))

        self.qty_entry = create_dialog_entry(sr, "Quantity Adjustment *", "1")
        self.qty_entry.bind("<KeyRelease>", self._compute_new_qty)

        ctk.CTkLabel(sr, text="New Quantity (computed)", anchor="w",
                      font=ctk.CTkFont(size=12), text_color=TEXT_SECONDARY).pack(fill="x", pady=(8, 3))
        self.new_qty_var = ctk.StringVar(value="—")
        nqf = ctk.CTkFrame(sr, fg_color=BG_CARD_ALT, corner_radius=8,
                            border_width=1, border_color=BORDER, height=38)
        nqf.pack(fill="x")
        nqf.pack_propagate(False)
        ctk.CTkLabel(nqf, textvariable=self.new_qty_var,
                      font=ctk.CTkFont(size=14, weight="bold"),
                      text_color=ACCENT, anchor="w").place(relx=0.03, rely=0.5, anchor="w")

        ctk.CTkLabel(sr, text="Reason *", anchor="w",
                      font=ctk.CTkFont(size=12), text_color=TEXT_SECONDARY).pack(fill="x", pady=(10, 3))
        self.reason_var = ctk.StringVar(value=ADJUSTMENT_REASONS[0])
        create_option_menu(sr, values=ADJUSTMENT_REASONS, variable=self.reason_var).pack(fill="x")

        ctk.CTkLabel(sr, text="Additional Notes", anchor="w",
                      font=ctk.CTkFont(size=12), text_color=TEXT_SECONDARY).pack(fill="x", pady=(10, 3))
        self.notes_box = ctk.CTkTextbox(
            sr, height=70, fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, corner_radius=8,
            font=ctk.CTkFont(size=12),
        )
        self.notes_box.pack(fill="x")

        notice = ctk.CTkFrame(sr, fg_color="#FFF8E0", corner_radius=8,
                               border_width=1, border_color=WARNING)
        notice.pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(notice,
                      text="⚠  Adjustment will be PENDING until approved by the Owner.",
                      font=ctk.CTkFont(size=11), text_color=WARNING,
                      wraplength=360, justify="left").pack(padx=10, pady=8, anchor="w")

        ctk.CTkButton(
            sr, text="📤  Submit Adjustment for Approval", height=42,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=10, command=self._submit,
        ).pack(fill="x", pady=(14, 0))

    def _fill_combo(self, products):
        self._displayed = products
        self.product_combo["values"] = [f"{p['code']}  —  {p['name']}" for p in products]
        if products:
            self.product_combo.current(0)
            self._on_product_select()

    def _filter_products(self, *_):
        q = self.search_var.get().lower()
        filtered = [p for p in self._products
                    if q in p["name"].lower() or q in p["code"].lower()] if q else self._products
        self._fill_combo(filtered)

    def _on_product_select(self, _=None):
        idx = self.product_combo.current()
        if idx < 0 or idx >= len(self._displayed):
            return
        p = self._displayed[idx]
        self._selected_product = p
        self.prod_name_var.set(p["name"])
        self.prod_code_var.set(p["code"])
        self.prod_stock_var.set(str(p["current_stock"]))
        self._compute_new_qty()

    def _compute_new_qty(self, *_):
        if not self._selected_product or self.qty_entry is None:
            return
        try:
            qty = int(self.qty_entry.get().strip())
            current = self._selected_product["current_stock"]
            new_qty = current + qty if self.adj_type_var.get() == "Add" else current - qty
            self.new_qty_var.set(str(new_qty) if new_qty >= 0 else "⚠ Below 0")
        except ValueError:
            self.new_qty_var.set("—")

    def _submit(self):
        if not self._selected_product:
            msg_warning(self, "No Product", "Please select a product first.")
            return
        try:
            qty = int(self.qty_entry.get().strip())
            if qty <= 0:
                raise ValueError
        except ValueError:
            msg_warning(self, "Invalid Quantity", "Quantity must be a positive whole number.")
            return

        adj_type = self.adj_type_var.get()
        current  = self._selected_product["current_stock"]
        diff     = qty if adj_type == "Add" else -qty
        new_qty  = current + diff

        if new_qty < 0:
            msg_warning(self, "Invalid Adjustment",
                        f"Cannot deduct {qty} from stock of {current}.")
            return

        reason = self.reason_var.get()
        notes  = self.notes_box.get("1.0", "end").strip()
        full_reason = reason + (f" — {notes}" if notes else "")

        if not msg_question(self, "Confirm Submission",
                            f"Submit adjustment?\n\n"
                            f"Product: {self._selected_product['name']}\n"
                            f"Type: {adj_type}  {qty} units\n"
                            f"Current Stock: {current}  →  New Stock: {new_qty}\n"
                            f"Reason: {reason}\n\n"
                            "Status will be PENDING until Owner approves."):
            return

        try:
            conn = get_connection()
            req = conn.execute(
                """INSERT INTO stock_update_requests
                   (request_type, product_id, product_name,
                    old_quantity, requested_quantity, quantity_difference,
                    reason, requested_by, status)
                   VALUES ('stock_adjustment', ?, ?, ?, ?, ?, ?, ?, 'pending')""",
                (self._selected_product["id"], self._selected_product["name"],
                 current, new_qty, diff, full_reason, self.user["id"]),
            )
            req_id = req.lastrowid
            conn.execute(
                """INSERT INTO approval_logs
                   (request_id, action, action_by, old_quantity, new_quantity, notes)
                   VALUES (?, 'submitted', ?, ?, ?, ?)""",
                (req_id, self.user["id"], current, new_qty,
                 f"Adjustment ({adj_type}) submitted by {self.user['full_name']}"),
            )
            conn.commit()
            conn.close()
            log_audit(self.user["id"], self.user["username"], "Stock", "STOCK_ADJUSTMENT_SUBMITTED",
                      record_id=req_id,
                      new_value={"product": self._selected_product["name"],
                                 "old_qty": current, "new_qty": new_qty})
            msg_success(self, "Submitted!",
                        f"Adjustment request submitted for '{self._selected_product['name']}'.\n"
                        "Awaiting owner approval.")
            self.qty_entry.delete(0, "end")
            self.qty_entry.insert(0, "1")
            self.notes_box.delete("1.0", "end")
            self.new_qty_var.set("—")
        except Exception as exc:
            msg_error(self, "Error", str(exc))


class AdjustmentHistoryTable(ctk.CTkFrame):
    def __init__(self, master, user: dict):
        super().__init__(master, fg_color="transparent")
        self.user = user
        self._build()
        self._load()

    def _build(self):
        fbar = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=10,
                             border_width=1, border_color=BORDER)
        fbar.pack(fill="x", pady=(0, 8))
        inner = ctk.CTkFrame(fbar, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=8)

        self.search_var = ctk.StringVar()
        self.search_var.trace("w", lambda *_: self._load())
        ctk.CTkEntry(
            inner, textvariable=self.search_var,
            placeholder_text="🔍  Search product name...",
            height=36, fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12), corner_radius=8,
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.status_var = ctk.StringVar(value="All")
        create_option_menu(inner, values=["All", "Pending", "Approved", "Rejected"],
                           variable=self.status_var, width=150,
                           command=lambda *_: self._load()).pack(side="right")

        card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14,
                             border_width=1, border_color=BORDER)
        card.pack(fill="both", expand=True)

        cols = ("req_id", "product", "type", "old_qty", "qty_diff",
                "new_qty", "reason", "requested_by", "date", "status")
        self.tree = ttk.Treeview(card, columns=cols, show="headings", height=14)

        hdrs = {"req_id": "ID", "product": "Product", "type": "Type",
                 "old_qty": "Old Qty", "qty_diff": "Adjustment", "new_qty": "New Qty",
                 "reason": "Reason", "requested_by": "Requested By",
                 "date": "Date", "status": "Status"}
        widths = {"req_id": 50, "product": 170, "type": 80, "old_qty": 70,
                   "qty_diff": 90, "new_qty": 70, "reason": 160,
                   "requested_by": 110, "date": 130, "status": 90}

        for col in cols:
            self.tree.heading(col, text=hdrs[col])
            self.tree.column(col, width=widths[col],
                              anchor="e" if col in ("old_qty", "qty_diff", "new_qty", "req_id") else "w")

        sb = ttk.Scrollbar(card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        style_treeview(self.tree)
        self.tree.tag_configure("pending",  foreground="#B88B2E", background="#FFF8E0")
        self.tree.tag_configure("approved", foreground="#4A7C59", background="#E6F2EA")
        self.tree.tag_configure("rejected", foreground="#A94040", background="#F5E0E0")
        self.tree.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        sb.pack(side="right", fill="y", pady=6)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", pady=6)
        ctk.CTkButton(btn_row, text="🔄  Refresh", height=34, width=120,
                       fg_color=BG_CARD, hover_color=BG_HOVER,
                       border_width=1, border_color=BORDER,
                       text_color=TEXT_PRIMARY, corner_radius=8,
                       font=ctk.CTkFont(size=12), command=self._load).pack(side="left")

    def _load(self):
        q      = f"%{self.search_var.get()}%"
        status = self.status_var.get().lower()
        conn   = get_connection()
        query  = """
            SELECT r.id, r.product_name, r.quantity_difference,
                   r.old_quantity, r.requested_quantity,
                   r.reason, r.status, r.request_date,
                   u.full_name AS requested_by
            FROM stock_update_requests r
            JOIN users u ON u.id = r.requested_by
            WHERE r.request_type = 'stock_adjustment' AND r.product_name LIKE ?
        """
        params: list = [q]
        if status != "all":
            query += " AND r.status = ?"
            params.append(status)
        query += " ORDER BY r.request_date DESC"

        rows = conn.execute(query, params).fetchall()
        conn.close()

        for c in self.tree.get_children():
            self.tree.delete(c)
        for row in rows:
            diff     = row["quantity_difference"]
            diff_str = f"+{diff}" if diff > 0 else str(diff)
            self.tree.insert("", "end", tags=(row["status"],), values=(
                row["id"], row["product_name"],
                "Add" if diff > 0 else "Deduct",
                row["old_quantity"], diff_str, row["requested_quantity"],
                (row["reason"] or "")[:40],
                row["requested_by"], row["request_date"],
                row["status"].capitalize(),
            ))