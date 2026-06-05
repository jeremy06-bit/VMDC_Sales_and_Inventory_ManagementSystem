"""
VMDC Motor Parts — Stock In / Delivery Entry
=============================================
Allows staff to record incoming deliveries.
Each delivery creates:
  • A `stock_in` header record (invoice / supplier / date / remarks)
  • One or more `stock_in_items` rows (product + qty + prices)
  • One `stock_update_requests` row per item (status = 'pending')

Actual inventory quantities are NOT touched until an owner approves
the request from the Approval Management window.
"""

import customtkinter as ctk
from tkinter import ttk
from datetime import date

from database import get_connection
from security import log_audit
from ui.inventory_window import PRODUCT_CATEGORIES, CATEGORY_PREFIX, generate_next_code
from ui.theme import (
    BG_DARK, BG_CARD, BG_CARD_ALT, BG_INPUT, BG_HOVER, BORDER,
    ACCENT, ACCENT_HOVER, ACCENT_LIGHT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    SUCCESS, SUCCESS_HOVER, DANGER,
    style_treeview, insert_with_stripes, Paginator,
    create_dialog_entry, create_dialog_button, style_dialog,
    create_option_menu,
    msg_info, msg_warning, msg_error, msg_success, msg_question,
)


# ─────────────────────────────────────────────────────────────
#  Helper — product lookup
# ─────────────────────────────────────────────────────────────

def _fetch_products():
    """Return list of dicts: id, code, name, cost_price, selling_price, current_stock."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, code, name, cost_price, selling_price, current_stock FROM products ORDER BY name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _check_duplicate_invoice(invoice_number: str) -> bool:
    """Return True if the invoice number already exists in stock_in."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM stock_in WHERE invoice_number = ?", (invoice_number,)
    ).fetchone()
    conn.close()
    return row is not None


# ─────────────────────────────────────────────────────────────
#  Main Frame
# ─────────────────────────────────────────────────────────────

class StockInFrame(ctk.CTkFrame):
    """
    Tab-like layout with two sub-views:
      [1] New Delivery Entry  — form to record a new delivery
      [2] Delivery History    — table of past deliveries + their status
    """

    def __init__(self, master, user: dict):
        super().__init__(master, fg_color="transparent")
        self.user = user
        self._build_ui()
        self._show_tab("entry")

    # ── Layout skeleton ──────────────────────────────────────

    def _build_ui(self):
        # Page header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            header,
            text="Stock In / Delivery Entry",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        # Tab bar
        tab_bar = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=10,
                                border_width=1, border_color=BORDER)
        tab_bar.pack(fill="x", pady=(0, 10))

        inner = ctk.CTkFrame(tab_bar, fg_color="transparent")
        inner.pack(padx=8, pady=6, anchor="w")

        self._tab_btns = {}
        for label, key in [("📥  New Delivery", "entry"), ("📋  Delivery History", "history")]:
            btn = ctk.CTkButton(
                inner, text=label, height=34, width=180,
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

    def _show_tab(self, key: str):
        # Highlight active tab
        for k, btn in self._tab_btns.items():
            if k == key:
                btn.configure(fg_color=ACCENT, text_color="white")
            else:
                btn.configure(fg_color=BG_CARD_ALT, text_color=TEXT_PRIMARY)

        # Clear content
        for child in self._content.winfo_children():
            child.destroy()

        if key == "entry":
            DeliveryEntryForm(self._content, self.user, self._show_tab).pack(
                fill="both", expand=True
            )
        else:
            DeliveryHistoryTable(self._content, self.user).pack(fill="both", expand=True)


# ─────────────────────────────────────────────────────────────
#  Sub-view 1 — New Delivery Entry Form
# ─────────────────────────────────────────────────────────────

class DeliveryEntryForm(ctk.CTkFrame):
    """
    Two-panel layout:
      Left  — invoice / supplier / date header fields
      Right — line-item cart (product list being added to this delivery)
    """

    def __init__(self, master, user: dict, switch_tab_fn):
        super().__init__(master, fg_color="transparent")
        self.user = user
        self._switch_tab = switch_tab_fn
        self._cart = []          # list of dicts: product_id, code, name, qty, cost, sell
        self._products = _fetch_products()
        self._build()

    # ── Build ────────────────────────────────────────────────

    def _build(self):
        # Two-column grid
        self.columnconfigure(0, weight=2)
        self.columnconfigure(1, weight=3)
        self.rowconfigure(0, weight=1)

        self._build_left_panel()
        self._build_right_panel()

    # ── Left: Delivery Header ────────────────────────────────

    def _build_left_panel(self):
        left = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14,
                             border_width=1, border_color=BORDER)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        scroll = ctk.CTkScrollableFrame(left, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=16, pady=14)

        ctk.CTkLabel(
            scroll,
            text="Delivery Information",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 10))

        # ── Invoice Number ──
        self.invoice_var = ctk.StringVar()
        self.invoice_entry = create_dialog_entry(scroll, "Sales Invoice Number *", "")
        self.invoice_var = self.invoice_entry  # create_dialog_entry returns the CTkEntry

        # ── Supplier ──
        self.supplier_entry = create_dialog_entry(scroll, "Supplier Name *", "")

        # ── Delivery Date ──
        self.date_entry = create_dialog_entry(
            scroll, "Delivery Date *", date.today().strftime("%Y-%m-%d")
        )
        ctk.CTkLabel(
            scroll, text="Format: YYYY-MM-DD",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=TEXT_MUTED, anchor="w",
        ).pack(fill="x", pady=(0, 4))

        # ── Remarks ──
        ctk.CTkLabel(
            scroll, text="Remarks", anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_SECONDARY,
        ).pack(fill="x", pady=(8, 3))

        self.remarks_box = ctk.CTkTextbox(
            scroll, height=80,
            fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, corner_radius=8,
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        self.remarks_box.pack(fill="x")

        # ── Divider ──
        ctk.CTkFrame(scroll, fg_color=BORDER, height=1, corner_radius=0).pack(
            fill="x", pady=14
        )

        # ── Add Product to Cart section ──
        ctk.CTkLabel(
            scroll,
            text="Add Product to Delivery",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 8))

        # Product selector search
        prod_label_row = ctk.CTkFrame(scroll, fg_color="transparent")
        prod_label_row.pack(fill="x", pady=(0, 3))
        ctk.CTkLabel(
            prod_label_row, text="Search Product *", anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_SECONDARY,
        ).pack(side="left")
        ctk.CTkButton(
            prod_label_row, text="+ New Product", height=24, width=110,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color="white", corner_radius=6,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=self._open_new_product_dialog,
        ).pack(side="right")

        self.product_search_var = ctk.StringVar()
        self.product_search_var.trace("w", self._filter_product_list)
        search_entry = ctk.CTkEntry(
            scroll, textvariable=self.product_search_var,
            placeholder_text="🔍 Type product name or code...",
            height=36, fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=12), corner_radius=8,
        )
        search_entry.pack(fill="x")

        # Product listbox
        list_frame = ctk.CTkFrame(scroll, fg_color=BG_INPUT, corner_radius=8,
                                   border_width=1, border_color=BORDER)
        list_frame.pack(fill="x", pady=(4, 0))

        self.product_listbox = ttk.Combobox(
            list_frame, state="readonly",
            font=("Segoe UI", 11),
        )
        self.product_listbox.pack(fill="x", padx=6, pady=6)

        # Initialize BEFORE _populate_product_combo so _on_product_selected
        # can safely reference them during the initial auto-selection.
        self.sel_product_id   = None
        self.sel_code_var     = ctk.StringVar(value="—")
        self.sel_stock_var    = ctk.StringVar(value="—")
        self.cost_entry       = None  # built below; guard in _on_product_selected
        self.sell_entry       = None  # built below; guard in _on_product_selected

        self._populate_product_combo(self._products)
        self.product_listbox.bind("<<ComboboxSelected>>", self._on_product_selected)

        info_row = ctk.CTkFrame(scroll, fg_color="transparent")
        info_row.pack(fill="x", pady=(6, 0))
        for lbl, var in [("Code:", self.sel_code_var), ("Current Stock:", self.sel_stock_var)]:
            r = ctk.CTkFrame(info_row, fg_color=BG_CARD_ALT, corner_radius=6,
                              border_width=1, border_color=BORDER)
            r.pack(side="left", fill="x", expand=True, padx=(0, 4))
            ctk.CTkLabel(r, text=lbl, font=ctk.CTkFont(size=10),
                          text_color=TEXT_MUTED).pack(side="left", padx=6, pady=4)
            ctk.CTkLabel(r, textvariable=var, font=ctk.CTkFont(size=10, weight="bold"),
                          text_color=TEXT_PRIMARY).pack(side="left", pady=4)

        # Qty / cost / sell inputs
        self.qty_entry   = create_dialog_entry(scroll, "Quantity Delivered *", "1")
        self.cost_entry  = create_dialog_entry(scroll, "Cost Price (₱) *", "0.00")
        self.sell_entry  = create_dialog_entry(scroll, "Selling Price (₱) *", "0.00")

        # Now that cost_entry and sell_entry exist, fill prices for the pre-selected product
        self._on_product_selected()

        ctk.CTkButton(
            scroll, text="➕  Add to Delivery", height=36,
            fg_color=SUCCESS, hover_color=SUCCESS_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8, command=self._add_to_cart,
        ).pack(fill="x", pady=(10, 0))

    # ── Right: Cart + Submit ─────────────────────────────────

    def _build_right_panel(self):
        right = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14,
                              border_width=1, border_color=BORDER)
        right.grid(row=0, column=1, sticky="nsew")

        # Header row of right panel
        rh = ctk.CTkFrame(right, fg_color="transparent")
        rh.pack(fill="x", padx=16, pady=(14, 6))
        ctk.CTkLabel(
            rh,
            text="📦  Products in this Delivery",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")
        ctk.CTkButton(
            rh, text="🗑 Clear All", height=30, width=100,
            fg_color=BG_CARD_ALT, hover_color=DANGER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY, corner_radius=6,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            command=self._clear_cart,
        ).pack(side="right")

        # Cart table
        table_frame = ctk.CTkFrame(right, fg_color="transparent")
        table_frame.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        cols = ("code", "name", "qty", "cost", "sell")
        self.cart_tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=14)
        headers  = {"code": "Code", "name": "Product Name", "qty": "Qty",
                     "cost": "Cost Price", "sell": "Selling Price"}
        widths   = {"code": 80, "name": 200, "qty": 60, "cost": 90, "sell": 90}

        for col in cols:
            self.cart_tree.heading(col, text=headers[col])
            anchor = "e" if col in ("qty", "cost", "sell") else "w"
            self.cart_tree.column(col, width=widths[col], anchor=anchor)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.cart_tree.yview)
        self.cart_tree.configure(yscrollcommand=scrollbar.set)
        style_treeview(self.cart_tree)
        self.cart_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Remove selected row button
        ctk.CTkButton(
            right, text="❌  Remove Selected Item", height=32,
            fg_color=BG_CARD_ALT, hover_color=DANGER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY, corner_radius=6,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            command=self._remove_selected_cart_item,
        ).pack(padx=14, pady=(0, 6), anchor="w")

        # Info label
        self._cart_info_var = ctk.StringVar(value="No items added yet.")
        ctk.CTkLabel(
            right, textvariable=self._cart_info_var,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED, anchor="w",
        ).pack(padx=16, pady=(0, 6))

        # Notice banner
        notice = ctk.CTkFrame(right, fg_color="#DCE4EA",
                               corner_radius=8, border_width=1, border_color=ACCENT_LIGHT)
        notice.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkLabel(
            notice,
            text="ℹ  Inventory will only update after Owner approval.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=ACCENT, wraplength=380, justify="left",
        ).pack(padx=10, pady=8, anchor="w")

        # Submit button
        ctk.CTkButton(
            right, text="📤  Submit Delivery for Approval", height=42,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            corner_radius=10, command=self._submit_delivery,
        ).pack(fill="x", padx=14, pady=(0, 14))

    # ── Product combo helpers ────────────────────────────────

    def _populate_product_combo(self, products):
        """Fill the combobox from a list of product dicts."""
        self._displayed_products = products
        labels = [f"{p['code']}  —  {p['name']}" for p in products]
        self.product_listbox["values"] = labels
        if labels:
            self.product_listbox.set(labels[0])
            self._on_product_selected()
        else:
            self.product_listbox.set("")
            self.sel_product_id = None
            self.sel_code_var.set("—")
            self.sel_stock_var.set("—")

    def _filter_product_list(self, *_):
        q = self.product_search_var.get().lower()
        filtered = [
            p for p in self._products
            if q in p["name"].lower() or q in p["code"].lower()
        ] if q else self._products
        self._populate_product_combo(filtered)

    def _on_product_selected(self, _=None):
        idx = self.product_listbox.current()
        if idx < 0 or idx >= len(self._displayed_products):
            return
        p = self._displayed_products[idx]
        self.sel_product_id = p["id"]
        self.sel_code_var.set(p["code"])
        self.sel_stock_var.set(str(p["current_stock"]))
        # Pre-fill prices from existing product data (only once widgets exist)
        if self.cost_entry is not None:
            self.cost_entry.delete(0, "end")
            self.cost_entry.insert(0, f"{p['cost_price']:.2f}")
        if self.sell_entry is not None:
            self.sell_entry.delete(0, "end")
            self.sell_entry.insert(0, f"{p['selling_price']:.2f}")

    def _open_new_product_dialog(self):
        """Open a dialog to create a new product, then auto-select it in the form."""
        def on_created(new_product: dict):
            # Refresh product list from DB
            self._products = _fetch_products()
            # Find the newly created product and select it
            self.product_search_var.set("")
            self._filter_product_list()
            for i, p in enumerate(self._displayed_products):
                if p["id"] == new_product["id"]:
                    self.product_listbox.current(i)
                    self._on_product_selected()
                    break

        NewProductDialog(self, on_created)

    # ── Cart management ──────────────────────────────────────

    def _add_to_cart(self):
        if self.sel_product_id is None:
            msg_warning(self, "No Product", "Please select a product first.")
            return

        # Validate qty
        try:
            qty = int(self.qty_entry.get().strip())
            if qty <= 0:
                raise ValueError
        except ValueError:
            msg_warning(self, "Invalid Quantity", "Quantity must be a positive whole number.")
            return

        try:
            cost  = float(self.cost_entry.get().strip())
            sell  = float(self.sell_entry.get().strip())
        except ValueError:
            msg_warning(self, "Invalid Price", "Cost and Selling Price must be valid numbers.")
            return

        # Check if already in cart
        idx = self.product_listbox.current()
        product = self._displayed_products[idx]

        for item in self._cart:
            if item["product_id"] == product["id"]:
                # Update existing cart item
                item["qty"]  += qty
                item["cost"]  = cost
                item["sell"]  = sell
                self._refresh_cart_tree()
                return

        self._cart.append({
            "product_id": product["id"],
            "code":       product["code"],
            "name":       product["name"],
            "qty":        qty,
            "cost":       cost,
            "sell":       sell,
        })
        self._refresh_cart_tree()

    def _refresh_cart_tree(self):
        for row in self.cart_tree.get_children():
            self.cart_tree.delete(row)
        for i, item in enumerate(self._cart):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.cart_tree.insert("", "end", tags=(tag,), values=(
                item["code"],
                item["name"],
                item["qty"],
                f"₱{item['cost']:,.2f}",
                f"₱{item['sell']:,.2f}",
            ))
        count = len(self._cart)
        self._cart_info_var.set(
            f"{count} product{'s' if count != 1 else ''} added to this delivery."
            if count else "No items added yet."
        )

    def _remove_selected_cart_item(self):
        sel = self.cart_tree.selection()
        if not sel:
            msg_warning(self, "Nothing Selected", "Select an item in the cart to remove.")
            return
        idx = self.cart_tree.index(sel[0])
        del self._cart[idx]
        self._refresh_cart_tree()

    def _clear_cart(self):
        if not self._cart:
            return
        if msg_question(self, "Confirm", "Remove all items from this delivery?"):
            self._cart.clear()
            self._refresh_cart_tree()

    # ── Submit ───────────────────────────────────────────────

    def _submit_delivery(self):
        # Validate header fields
        invoice  = self.invoice_entry.get().strip()
        supplier = self.supplier_entry.get().strip()
        del_date = self.date_entry.get().strip()
        remarks  = self.remarks_box.get("1.0", "end").strip()

        if not invoice or not supplier or not del_date:
            msg_warning(self, "Required Fields",
                        "Invoice Number, Supplier Name, and Delivery Date are required.")
            return

        if not self._cart:
            msg_warning(self, "Empty Delivery",
                        "Please add at least one product to this delivery.")
            return

        # Check duplicate invoice
        if _check_duplicate_invoice(invoice):
            msg_warning(self, "Duplicate Invoice",
                        f"Invoice '{invoice}' already exists.\n"
                        "Please check the Delivery History tab.")
            return

        # Confirmation
        item_count = len(self._cart)
        total_qty  = sum(i["qty"] for i in self._cart)
        if not msg_question(
            self, "Confirm Submission",
            f"Submit delivery?\n\n"
            f"Invoice: {invoice}\n"
            f"Supplier: {supplier}\n"
            f"Products: {item_count}  (Total qty: {total_qty})\n\n"
            "Status will be PENDING until Owner approves."
        ):
            return

        try:
            conn = get_connection()

            # 1. Insert stock_in header
            cur = conn.execute(
                """
                INSERT INTO stock_in (invoice_number, supplier_name, delivery_date, remarks, recorded_by, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
                """,
                (invoice, supplier, del_date, remarks or None, self.user["id"]),
            )
            stock_in_id = cur.lastrowid

            for item in self._cart:
                # 2. Insert stock_in_items
                conn.execute(
                    """
                    INSERT INTO stock_in_items
                        (stock_in_id, product_id, qty_delivered, cost_price, selling_price)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (stock_in_id, item["product_id"],
                     item["qty"], item["cost"], item["sell"]),
                )

                # 3. Fetch current quantity for the request record
                prod_row = conn.execute(
                    "SELECT current_stock FROM products WHERE id = ?",
                    (item["product_id"],)
                ).fetchone()
                old_qty = prod_row["current_stock"] if prod_row else 0

                # 4. Create a stock_update_request (status = pending)
                req_cur = conn.execute(
                    """
                    INSERT INTO stock_update_requests
                        (request_type, stock_in_id, product_id, product_name,
                         old_quantity, requested_quantity, quantity_difference,
                         reason, requested_by, status)
                    VALUES ('stock_in', ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                    """,
                    (stock_in_id, item["product_id"], item["name"],
                     old_qty, old_qty + item["qty"], item["qty"],
                     f"Stock In — Invoice {invoice}", self.user["id"]),
                )
                request_id = req_cur.lastrowid

                # 5. Log the submission action
                conn.execute(
                    """
                    INSERT INTO approval_logs
                        (request_id, action, action_by, old_quantity, new_quantity, notes)
                    VALUES (?, 'submitted', ?, ?, ?, ?)
                    """,
                    (request_id, self.user["id"],
                     old_qty, old_qty + item["qty"],
                     f"Delivery submitted by {self.user['full_name']}"),
                )

            conn.commit()
            conn.close()

            log_audit(self.user["id"], self.user["username"], "Stock", "STOCK_IN_SUBMITTED",
                      record_id=stock_in_id,
                      new_value={"invoice": invoice, "supplier": supplier})
            msg_success(self, "Submitted!",
                        f"Delivery for Invoice '{invoice}' has been submitted.\n"
                        "It is now PENDING owner approval.")

            # Reset the form
            self.invoice_entry.delete(0, "end")
            self.supplier_entry.delete(0, "end")
            self.date_entry.delete(0, "end")
            self.date_entry.insert(0, date.today().strftime("%Y-%m-%d"))
            self.remarks_box.delete("1.0", "end")
            self._cart.clear()
            self._refresh_cart_tree()

        except Exception as exc:
            msg_error(self, "Error", str(exc))


# ─────────────────────────────────────────────────────────────
#  Sub-view 2 — Delivery History Table
# ─────────────────────────────────────────────────────────────

class DeliveryHistoryTable(ctk.CTkFrame):
    """
    Shows all past stock_in records with their approval status.
    Owners can expand a delivery to see its line items.
    """

    def __init__(self, master, user: dict):
        super().__init__(master, fg_color="transparent")
        self.user = user
        self._build()
        self._load()

    def _build(self):
        # Search bar
        search_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=10,
                                     border_width=1, border_color=BORDER)
        search_frame.pack(fill="x", pady=(0, 8))

        inner = ctk.CTkFrame(search_frame, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=8)

        self.search_var = ctk.StringVar()
        self.search_var.trace("w", lambda *_: self._load())
        ctk.CTkEntry(
            inner, textvariable=self.search_var,
            placeholder_text="🔍  Search by invoice, supplier...",
            height=36, fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=12), corner_radius=8,
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.status_filter_var = ctk.StringVar(value="All")
        create_option_menu(
            inner,
            values=["All", "Pending", "Approved", "Rejected"],
            variable=self.status_filter_var,
            width=150,
            command=lambda *_: self._load(),
        ).pack(side="right")

        # Delivery header table
        table_card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14,
                                   border_width=1, border_color=BORDER)
        table_card.pack(fill="both", expand=True)

        cols = ("invoice", "supplier", "date", "items", "status", "recorded_by", "created_at")
        self.tree = ttk.Treeview(table_card, columns=cols, show="headings", height=10)

        hdrs   = {"invoice": "Invoice #", "supplier": "Supplier", "date": "Delivery Date",
                   "items": "Items", "status": "Status",
                   "recorded_by": "Recorded By", "created_at": "Submitted At"}
        widths = {"invoice": 130, "supplier": 160, "date": 110, "items": 60,
                   "status": 90, "recorded_by": 120, "created_at": 140}

        for col in cols:
            self.tree.heading(col, text=hdrs[col])
            self.tree.column(col, width=widths[col], anchor="center" if col == "items" else "w")

        sb = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)

        # Tag colours for status
        style_treeview(self.tree)
        self.tree.tag_configure("pending",  foreground="#B88B2E", background="#FFF8E0")
        self.tree.tag_configure("approved", foreground="#4A7C59", background="#E6F2EA")
        self.tree.tag_configure("rejected", foreground="#A94040", background="#F5E0E0")

        self.tree.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        sb.pack(side="right", fill="y", pady=6)

        # Action buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", pady=6)

        ctk.CTkButton(
            btn_row, text="🔄  Refresh", height=34, width=120,
            fg_color=BG_CARD, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY, corner_radius=8,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self._load,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="📋  View Items", height=34, width=140,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color="white", corner_radius=8,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._view_items,
        ).pack(side="left")

    def _load(self):
        q      = f"%{self.search_var.get()}%"
        status = self.status_filter_var.get().lower()

        conn  = get_connection()
        query = """
            SELECT si.id, si.invoice_number, si.supplier_name, si.delivery_date,
                   si.status, si.created_at,
                   u.full_name AS recorded_by,
                   COUNT(sii.id) AS item_count
            FROM stock_in si
            JOIN users u         ON u.id = si.recorded_by
            LEFT JOIN stock_in_items sii ON sii.stock_in_id = si.id
            WHERE (si.invoice_number LIKE ? OR si.supplier_name LIKE ?)
        """
        params: list = [q, q]
        if status != "all":
            query += " AND si.status = ?"
            params.append(status)
        query += " GROUP BY si.id ORDER BY si.created_at DESC"

        rows  = conn.execute(query, params).fetchall()
        conn.close()

        for child in self.tree.get_children():
            self.tree.delete(child)

        for row in rows:
            self.tree.insert(
                "", "end",
                iid=str(row["id"]),
                tags=(row["status"],),
                values=(
                    row["invoice_number"],
                    row["supplier_name"],
                    row["delivery_date"],
                    row["item_count"],
                    row["status"].capitalize(),
                    row["recorded_by"],
                    row["created_at"],
                ),
            )

    def _view_items(self):
        sel = self.tree.selection()
        if not sel:
            msg_warning(self, "Select", "Please select a delivery to view its items.")
            return
        stock_in_id = int(sel[0])
        DeliveryItemsDialog(self, stock_in_id)


class DeliveryItemsDialog(ctk.CTkToplevel):
    """Popup showing line items of a selected stock_in record."""

    def __init__(self, master, stock_in_id: int):
        super().__init__(master)
        self.stock_in_id = stock_in_id
        style_dialog(self, "Delivery Line Items", 700, 460)
        self._build()

    def _build(self):
        conn = get_connection()
        header = conn.execute(
            """
            SELECT si.invoice_number, si.supplier_name, si.delivery_date,
                   si.status, si.remarks, u.full_name AS recorded_by
            FROM stock_in si
            JOIN users u ON u.id = si.recorded_by
            WHERE si.id = ?
            """,
            (self.stock_in_id,),
        ).fetchone()

        items = conn.execute(
            """
            SELECT p.code, p.name, sii.qty_delivered, sii.cost_price, sii.selling_price,
                   r.status AS req_status
            FROM stock_in_items sii
            JOIN products p ON p.id = sii.product_id
            LEFT JOIN stock_update_requests r
                   ON r.stock_in_id = ? AND r.product_id = sii.product_id
            WHERE sii.stock_in_id = ?
            """,
            (self.stock_in_id, self.stock_in_id),
        ).fetchall()
        conn.close()

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=20, pady=16)

        if header:
            ctk.CTkLabel(
                form,
                text=f"Invoice: {header['invoice_number']}  —  {header['supplier_name']}",
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                text_color=TEXT_PRIMARY,
            ).pack(anchor="w", pady=(0, 4))
            ctk.CTkLabel(
                form,
                text=f"Delivery Date: {header['delivery_date']}   |   "
                     f"Status: {header['status'].capitalize()}   |   "
                     f"Recorded by: {header['recorded_by']}",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=TEXT_SECONDARY,
            ).pack(anchor="w", pady=(0, 10))

        table_frame = ctk.CTkFrame(form, fg_color=BG_CARD, corner_radius=10,
                                    border_width=1, border_color=BORDER)
        table_frame.pack(fill="both", expand=True)

        cols   = ("code", "name", "qty", "cost", "sell", "req_status")
        hdrs   = {"code": "Code", "name": "Product", "qty": "Qty Delivered",
                   "cost": "Cost Price", "sell": "Selling Price", "req_status": "Req. Status"}
        widths = {"code": 80, "name": 180, "qty": 90, "cost": 90, "sell": 90, "req_status": 90}

        tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=10)
        for col in cols:
            tree.heading(col, text=hdrs[col])
            anchor = "e" if col in ("qty", "cost", "sell") else "w"
            tree.column(col, width=widths[col], anchor=anchor)

        style_treeview(tree)
        tree.tag_configure("pending",  foreground="#B88B2E")
        tree.tag_configure("approved", foreground="#4A7C59")
        tree.tag_configure("rejected", foreground="#A94040")

        for i, item in enumerate(items):
            status_tag = item["req_status"] or "pending"
            tag = status_tag if status_tag in ("pending", "approved", "rejected") \
                  else ("evenrow" if i % 2 == 0 else "oddrow")
            tree.insert("", "end", tags=(tag,), values=(
                item["code"], item["name"],
                item["qty_delivered"],
                f"₱{item['cost_price']:,.2f}",
                f"₱{item['selling_price']:,.2f}",
                (item["req_status"] or "pending").capitalize(),
            ))

        tree.pack(fill="both", expand=True, padx=6, pady=6)

# ─────────────────────────────────────────────────────────────
#  New Product Dialog — full panel (mirrors Inventory Add Product)
# ─────────────────────────────────────────────────────────────

class NewProductDialog(ctk.CTkToplevel):
    """
    Full-featured product-creation dialog launched from the Stock In form.
    Layout mirrors the Inventory window's "Add Product" panel:
      • Two-column card layout (Product Identity  |  Pricing & Stock)
      • Auto-generated product code driven by category
      • Cancel + Save buttons in the footer
    On save, calls callback(new_product_dict) so the caller can auto-select it.
    """

    def __init__(self, master, callback):
        super().__init__(master)
        self.callback = callback
        style_dialog(self, "Add New Product", 680, 620)
        self._build()

    # ── helper: section card with colored top-strip ──────────
    @staticmethod
    def _section(parent, title, icon, accent_color):
        """Return a frame body ready for fields, wrapped in a card with a header."""
        card = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=12,
                            border_width=1, border_color=BORDER)
        # color strip
        ctk.CTkFrame(card, fg_color=accent_color, height=3,
                     corner_radius=0).pack(fill="x")
        # header row
        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 2))
        ctk.CTkLabel(hdr, text=icon,
                     font=ctk.CTkFont(size=15),
                     text_color=accent_color).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(hdr, text=title,
                     font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(side="left")
        # body area
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(4, 14))
        return card, body

    def _build(self):
        # ── Dialog title row ────────────────────────────────
        title_bar = ctk.CTkFrame(self, fg_color="transparent")
        title_bar.pack(fill="x", padx=24, pady=(18, 4))

        ctk.CTkLabel(
            title_bar,
            text="📦  Add New Product",
            font=ctk.CTkFont(family="Segoe UI", size=19, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        ctk.CTkLabel(
            title_bar,
            text="This product will be created and immediately available to add to this delivery.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
            wraplength=320,
            justify="right",
        ).pack(side="right")

        # thin separator
        ctk.CTkFrame(self, fg_color=BORDER, height=1,
                     corner_radius=0).pack(fill="x", padx=24, pady=(8, 0))

        # ── Scrollable body ─────────────────────────────────
        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(12, 0))

        # Two-column grid
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        # ═══════════════════════════════════════════════════
        #  LEFT COLUMN  — Product Identity
        # ═══════════════════════════════════════════════════
        left_card, left = self._section(body, "Product Identity", "🏷️", ACCENT)
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 10))

        # Category
        ctk.CTkLabel(left, text="Category *", anchor="w",
                     font=ctk.CTkFont(family="Segoe UI", size=12),
                     text_color=TEXT_SECONDARY).pack(fill="x", pady=(4, 3))
        self.category_var = ctk.StringVar(value=PRODUCT_CATEGORIES[0])
        create_option_menu(
            left, values=PRODUCT_CATEGORIES, variable=self.category_var,
            command=self._on_category_change,
        ).pack(fill="x")

        # Product Code (auto-generated)
        ctk.CTkLabel(left, text="Product Code  (auto-generated)", anchor="w",
                     font=ctk.CTkFont(family="Segoe UI", size=12),
                     text_color=TEXT_SECONDARY).pack(fill="x", pady=(10, 3))
        self.code_entry = ctk.CTkEntry(
            left, height=38,
            fg_color=BG_CARD_ALT, border_color=BORDER,
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            corner_radius=8, state="disabled",
        )
        self.code_entry.insert(0, generate_next_code(self.category_var.get()))
        self.code_entry.pack(fill="x")

        # Product Name
        self.entries = {}
        self.entries["name"] = create_dialog_entry(left, "Product Name *", "")

        # Unit
        self.entries["unit"] = create_dialog_entry(left, "Unit  (pc / set / liter...)", "pc")

        # ═══════════════════════════════════════════════════
        #  RIGHT COLUMN  — Pricing & Stock
        # ═══════════════════════════════════════════════════
        right_card, right = self._section(body, "Pricing & Stock", "💰", SUCCESS)
        right_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 10))

        # Cost Price
        self.entries["cost_price"] = create_dialog_entry(right, "Cost Price  (₱)", "0.00")

        # Selling Price
        self.entries["selling_price"] = create_dialog_entry(right, "Selling Price *  (₱)", "0.00")

        # Initial Stock
        self.entries["current_stock"] = create_dialog_entry(right, "Initial Stock", "0")

        # Low Stock Alert
        self.entries["low_stock_threshold"] = create_dialog_entry(right, "Low Stock Alert At", "5")

        # ═══════════════════════════════════════════════════
        #  BOTTOM — Cancel + Save buttons (full width)
        # ═══════════════════════════════════════════════════
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=24, pady=(8, 18))

        ctk.CTkButton(
            btn_frame, text="Cancel", height=44, width=120,
            fg_color=BG_CARD, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_SECONDARY, corner_radius=10,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self.destroy,
        ).pack(side="left")

        ctk.CTkButton(
            btn_frame,
            text="💾  Save & Select Product",
            height=44,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            corner_radius=10, command=self._save,
        ).pack(side="right", fill="x", expand=True, padx=(10, 0))

    def _on_category_change(self, _=None):
        new_code = generate_next_code(self.category_var.get())
        self.code_entry.configure(state="normal")
        self.code_entry.delete(0, "end")
        self.code_entry.insert(0, new_code)
        self.code_entry.configure(state="disabled")

    def _save(self):
        data = {k: e.get().strip() for k, e in self.entries.items()}
        data["category"] = self.category_var.get()

        self.code_entry.configure(state="normal")
        data["code"] = self.code_entry.get().strip()
        self.code_entry.configure(state="disabled")

        if not data["name"] or not data["selling_price"]:
            msg_warning(self, "Required Fields", "Product Name and Selling Price are required.")
            return

        try:
            cost  = float(data["cost_price"] or 0)
            sell  = float(data["selling_price"])
            stock = int(data["current_stock"] or 0)
            thr   = int(data["low_stock_threshold"] or 5)
        except ValueError:
            msg_warning(self, "Invalid Input",
                        "Cost price, selling price, stock and threshold must be valid numbers.")
            return

        try:
            conn = get_connection()
            cur = conn.execute(
                """
                INSERT INTO products (code, name, category, unit, cost_price, selling_price,
                                      current_stock, low_stock_threshold)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["code"], data["name"], data["category"],
                 data["unit"] or "pc", cost, sell, stock, thr),
            )
            new_id = cur.lastrowid
            conn.commit()
            new_product = dict(conn.execute(
                "SELECT id, code, name, cost_price, selling_price, current_stock FROM products WHERE id=?",
                (new_id,)
            ).fetchone())
            conn.close()
            msg_success(self, "Product Created",
                        f"'{data['name']}' ({data['code']}) has been added and selected.")
            self.callback(new_product)
            self.destroy()
        except Exception as exc:
            msg_error(self, "Error", str(exc))