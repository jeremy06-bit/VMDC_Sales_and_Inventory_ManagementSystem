import customtkinter as ctk
from tkinter import ttk
from database import get_connection
from security import log_audit, require_role
from ui.theme import (
    BG_DARK, BG_CARD, BG_CARD_ALT, BG_INPUT, BG_HOVER, BORDER,
    ACCENT, ACCENT_HOVER, ACCENT_LIGHT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    SUCCESS, SUCCESS_HOVER, DANGER,
    style_treeview, insert_with_stripes, Paginator,
    create_dialog_entry, create_dialog_button, style_dialog, create_option_menu,

    msg_info, msg_warning, msg_error, msg_success, msg_question
)

PRODUCT_CATEGORIES = [
    "Engine Parts",
    "Electrical Parts",
    "Brake System",
    "Tires and Lubricants",
    "Accessories",
    "After Market Parts",
    "Exhaust Parts",
]

CATEGORY_PREFIX = {
    "Engine Parts":        "EP",
    "Electrical Parts":    "EL",
    "Brake System":        "BR",
    "Tires and Lubricants":"TL",
    "Accessories":         "AC",
    "After Market Parts":  "AM",
    "Exhaust Parts":       "EX",
}


def generate_next_code(category: str) -> str:
    """Return the next auto-incremented product code for the given category."""
    prefix = CATEGORY_PREFIX.get(category, "XX")
    conn = get_connection()
    rows = conn.execute(
        "SELECT code FROM products WHERE category=? ORDER BY code",
        (category,)
    ).fetchall()
    conn.close()

    max_num = 0
    for row in rows:
        code = row["code"] if isinstance(row, dict) else row[0]
        if code and code.startswith(prefix):
            try:
                num = int(code[len(prefix):])
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"{prefix}{max_num + 1:03d}"


class InventoryFrame(ctk.CTkFrame):
    def __init__(self, master, user: dict):
        super().__init__(master, fg_color="transparent")
        self.user = user
        self._build_ui()
        self._load_inventory()

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(
            header, text="Inventory Management",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=TEXT_PRIMARY
        ).pack(side="left")

        if self.user["role"] == "owner":
            ctk.CTkButton(
                header, text="+  Add Product", height=38,
                fg_color=ACCENT, hover_color=ACCENT_HOVER,
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                corner_radius=10, command=self._open_add_product
            ).pack(side="right")

        # Search + Category Filter
        search_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=12,
                                     border_width=1, border_color=BORDER)
        search_frame.pack(fill="x", pady=(0, 10))
        search_inner = ctk.CTkFrame(search_frame, fg_color="transparent")
        search_inner.pack(fill="x", padx=12, pady=10)

        self.search_var = ctk.StringVar()
        self.search_var.trace("w", lambda *a: self._load_inventory())
        ctk.CTkEntry(
            search_inner, textvariable=self.search_var,
            placeholder_text="🔍  Search product...",
            height=40, fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=13), corner_radius=10,
        ).pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.category_filter_var = ctk.StringVar(value="All Categories")
        category_options = ["All Categories"] + PRODUCT_CATEGORIES
        create_option_menu(
            search_inner, values=category_options,
            variable=self.category_filter_var, width=200,
            command=lambda *a: self._load_inventory()
        ).pack(side="right")

        # Table
        table_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14,
                                    border_width=1, border_color=BORDER)
        table_frame.pack(fill="both", expand=True)

        cols = ("code", "name", "category", "stock", "threshold", "cost", "price")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=18)

        headers = {"code": "Code", "name": "Product Name", "category": "Category",
                   "stock": "Stock", "threshold": "Min Stock", "cost": "Cost Price", "price": "Selling Price"}
        widths = {"code": 80, "name": 200, "category": 100, "stock": 70, "threshold": 80, "cost": 90, "price": 90}

        for col in cols:
            self.tree.heading(col, text=headers[col])
            anchor = "e" if col in ("cost", "price", "stock", "threshold") else "w"
            self.tree.column(col, width=widths[col], anchor=anchor)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        style_treeview(self.tree)
        self.tree.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        scrollbar.pack(side="right", fill="y", pady=6)

        self._pager = Paginator(table_frame, self.tree, page_size=20,
                                render_fn=self._render_page, bar_parent=self)

        if self.user["role"] == "owner":
            action_frame = ctk.CTkFrame(self, fg_color="transparent")
            action_frame.pack(fill="x", pady=8)
            ctk.CTkButton(
                action_frame, text="✏  Edit Product", height=36,
                fg_color=BG_CARD, hover_color=BG_HOVER,
                border_width=1, border_color=BORDER,
                text_color=TEXT_PRIMARY, corner_radius=8,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                command=self._edit_product
            ).pack(side="left", padx=(0, 8))

    def _load_inventory(self):
        q = f"%{self.search_var.get()}%"
        cat_filter = self.category_filter_var.get()
        conn = get_connection()
        if self.user["role"] == "owner":
            if cat_filter == "All Categories":
                rows = conn.execute("""
                    SELECT id, code, name, category, current_stock, low_stock_threshold, cost_price, selling_price
                    FROM products WHERE name LIKE ? OR code LIKE ? ORDER BY name
                """, (q, q)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT id, code, name, category, current_stock, low_stock_threshold, cost_price, selling_price
                    FROM products WHERE (name LIKE ? OR code LIKE ?) AND category=? ORDER BY name
                """, (q, q, cat_filter)).fetchall()
        else:
            if cat_filter == "All Categories":
                rows = conn.execute("""
                    SELECT id, code, name, category, current_stock, low_stock_threshold, 0 as cost_price, 0 as selling_price
                    FROM products WHERE name LIKE ? OR code LIKE ? ORDER BY name
                """, (q, q)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT id, code, name, category, current_stock, low_stock_threshold, 0 as cost_price, 0 as selling_price
                    FROM products WHERE (name LIKE ? OR code LIKE ?) AND category=? ORDER BY name
                """, (q, q, cat_filter)).fetchall()
        conn.close()
        self._pager.set_data(list(rows))

    def _render_page(self, rows):
        for i, row in enumerate(rows):
            low = row["current_stock"] <= row["low_stock_threshold"]
            cost  = f"₱{row['cost_price']:,.2f}"   if self.user["role"] == "owner" else "—"
            price = f"₱{row['selling_price']:,.2f}" if self.user["role"] == "owner" else "—"
            tag = "low" if low else ("evenrow" if i % 2 == 0 else "oddrow")
            self.tree.insert("", "end", iid=str(row["id"]), tags=(tag,),
                values=(row["code"], row["name"], row["category"] or "—",
                        row["current_stock"], row["low_stock_threshold"], cost, price))

    
    def _get_selected_id(self):
        sel = self.tree.selection()
        if not sel:
            msg_warning(self, "Select", "Please select a product first.")
            return None
        return int(sel[0])

    def _open_add_product(self):
        ProductDialog(self, None, self.user, self._load_inventory)

    def _edit_product(self):
        pid = self._get_selected_id()
        if pid:
            conn = get_connection()
            product = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            conn.close()
            ProductDialog(self, dict(product), self.user, self._load_inventory)

class ProductDialog(ctk.CTkToplevel):
    def __init__(self, master, product, user, callback):
        super().__init__(master)
        self.product = product
        self.user = user
        self.callback = callback
        title = "Add Product" if not product else "Edit Product"
        style_dialog(self, title, 680, 620)
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
        p = self.product or {}
        is_add = not self.product

        # ── Dialog title row ────────────────────────────────
        title_bar = ctk.CTkFrame(self, fg_color="transparent")
        title_bar.pack(fill="x", padx=24, pady=(18, 4))

        ctk.CTkLabel(
            title_bar,
            text="📦  Add New Product" if is_add else "✏️  Edit Product",
            font=ctk.CTkFont(family="Segoe UI", size=19, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        ctk.CTkLabel(
            title_bar,
            text="Fill in the details below to register a product."
                 if is_add else "Modify the product information below.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
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
        self.category_var = ctk.StringVar(
            value=p.get("category", "") or PRODUCT_CATEGORIES[0])
        create_option_menu(
            left, values=PRODUCT_CATEGORIES, variable=self.category_var,
            command=self._on_category_change
        ).pack(fill="x")

        # Product Code
        initial_code = (p.get("code", "") if not is_add
                        else generate_next_code(self.category_var.get()))
        code_hint = "(auto-generated)" if is_add else "(auto-adjusts)"
        ctk.CTkLabel(left, text=f"Product Code  {code_hint}", anchor="w",
                     font=ctk.CTkFont(family="Segoe UI", size=12),
                     text_color=TEXT_SECONDARY).pack(fill="x", pady=(10, 3))
        self.code_entry = ctk.CTkEntry(
            left, height=38, fg_color=BG_CARD_ALT, border_color=BORDER,
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            corner_radius=8, state="disabled",
        )
        self.code_entry.insert(0, initial_code)
        self.code_entry.pack(fill="x")

        # Product Name
        self.entries = {}
        self.entries["name"] = create_dialog_entry(
            left, "Product Name *", p.get("name", ""))

        # Unit
        self.entries["unit"] = create_dialog_entry(
            left, "Unit  (pc / set / liter...)", p.get("unit", "pc"))

        # ═══════════════════════════════════════════════════
        #  RIGHT COLUMN  — Pricing & Stock
        # ═══════════════════════════════════════════════════
        right_card, right = self._section(body, "Pricing & Stock", "💰", SUCCESS)
        right_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 10))

        # Cost Price
        self.entries["cost_price"] = create_dialog_entry(
            right, "Cost Price  (₱)", str(p.get("cost_price", "0")))

        # Selling Price
        self.entries["selling_price"] = create_dialog_entry(
            right, "Selling Price *  (₱)", str(p.get("selling_price", "0")))

        # Current Stock / Initial Stock
        if is_add:
            self.entries["current_stock"] = create_dialog_entry(
                right, "Initial Stock", str(p.get("current_stock", "0")))
        else:
            ctk.CTkLabel(right, text="Current Stock", anchor="w",
                         font=ctk.CTkFont(family="Segoe UI", size=12),
                         text_color=TEXT_SECONDARY).pack(fill="x", pady=(8, 3))
            stock_row = ctk.CTkFrame(right, fg_color=BG_CARD_ALT, corner_radius=8,
                                     border_width=1, border_color=BORDER, height=38)
            stock_row.pack(fill="x")
            stock_row.pack_propagate(False)
            ctk.CTkLabel(stock_row, text=str(p.get("current_stock", 0)),
                         font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                         text_color=TEXT_PRIMARY, anchor="w"
                         ).place(relx=0.03, rely=0.5, anchor="w")
            ctk.CTkLabel(stock_row,
                         text='Use "Stock Adjustment"',
                         font=ctk.CTkFont(family="Segoe UI", size=10),
                         text_color=TEXT_MUTED, anchor="e"
                         ).place(relx=0.97, rely=0.5, anchor="e")

        # Low Stock Alert
        self.entries["low_stock_threshold"] = create_dialog_entry(
            right, "Low Stock Alert At", str(p.get("low_stock_threshold", "5")))

        # ═══════════════════════════════════════════════════
        #  BOTTOM — Save button (full width)
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
            text="💾  Save Product",
            height=44,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            corner_radius=10, command=self._save,
        ).pack(side="right", fill="x", expand=True, padx=(10, 0))

    def _on_category_change(self, _=None):
        """Adjust the product code when category changes — works for both add and edit."""
        new_cat    = self.category_var.get()
        new_prefix = CATEGORY_PREFIX.get(new_cat, "XX")

        self.code_entry.configure(state="normal")
        current_code = self.code_entry.get().strip()

        if self.product:
            # Edit mode: keep the numeric suffix, just swap the prefix
            old_cat    = self.product.get("category", "")
            old_prefix = CATEGORY_PREFIX.get(old_cat, "XX")
            if current_code.startswith(old_prefix):
                numeric_part = current_code[len(old_prefix):]
            else:
                # Fallback: strip any known prefix to extract the number
                numeric_part = ""
                for pfx in CATEGORY_PREFIX.values():
                    if current_code.startswith(pfx):
                        numeric_part = current_code[len(pfx):]
                        break
            # Validate the numeric part; fall back to next available number
            try:
                int(numeric_part)
                new_code = f"{new_prefix}{numeric_part}"
            except (ValueError, TypeError):
                new_code = generate_next_code(new_cat)
        else:
            # Add mode: generate the next available code for the new category
            new_code = generate_next_code(new_cat)

        self.code_entry.delete(0, "end")
        self.code_entry.insert(0, new_code)
        self.code_entry.configure(state="disabled")

    def _save(self):
        data = {k: e.get().strip() for k, e in self.entries.items()}
        data["category"] = self.category_var.get()
        # Get code — enable temporarily if disabled (add mode) to read value
        self.code_entry.configure(state="normal")
        data["code"] = self.code_entry.get().strip()
        if not self.product:
            self.code_entry.configure(state="disabled")

        if not data["code"] or not data["name"] or not data["selling_price"]:
            msg_warning(self, "Required Fields", "Code, Name, and Selling Price are required.")
            return

        try:
            conn = get_connection()
            if self.product:
                old_vals = dict(self.product)
                conn.execute("""
                    UPDATE products SET code=?, name=?, category=?, unit=?, cost_price=?, selling_price=?,
                    low_stock_threshold=?, updated_at=datetime('now','localtime') WHERE id=?
                """, (data["code"], data["name"], data["category"], data["unit"],
                      float(data["cost_price"] or 0), float(data["selling_price"]),
                      int(data["low_stock_threshold"] or 5),
                      self.product["id"]))
                log_audit(self.user["id"], self.user["username"], "Inventory", "EDIT_PRODUCT",
                          record_id=self.product["id"],
                          old_value={"name": old_vals.get("name"), "price": old_vals.get("selling_price")},
                          new_value={"name": data["name"], "price": data["selling_price"]})
            else:
                conn.execute("""
                    INSERT INTO products (code, name, category, unit, cost_price, selling_price, current_stock, low_stock_threshold)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (data["code"], data["name"], data["category"], data["unit"],
                      float(data["cost_price"] or 0), float(data["selling_price"]),
                      int(data["current_stock"] or 0), int(data["low_stock_threshold"] or 5)))
                new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                log_audit(self.user["id"], self.user["username"], "Inventory", "ADD_PRODUCT",
                          record_id=new_id,
                          new_value={"code": data["code"], "name": data["name"]})
            conn.commit()
            conn.close()
            self.callback()
            self.destroy()
        except Exception as e:
            msg_error(self, "Error", str(e))