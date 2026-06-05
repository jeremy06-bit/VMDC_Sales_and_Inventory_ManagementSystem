"""
VMDC Motor Parts — Sales Window  (HCI-Optimised Redesign)
══════════════════════════════════════════════════════════
Design Principles Applied:
  1. Progressive Disclosure  — Payment panel only activates after cart has items
  2. Visual Hierarchy        — 3-zone layout: Scan → Cart → Pay (left-to-right workflow)
  3. Status Visibility       — Persistent transaction state bar at top
  4. Chunking                — Totals broken into scannable rows with clear labels
  5. Affordance              — Buttons sized and coloured by action severity
  6. Error Prevention        — Inline stock badges, disabled states, confirm guards
  7. Fitts' Law              — Primary actions (PAY, Complete) are large targets
  8. Keyboard Shortcuts      — All critical paths reachable without mouse

Layout:
  TOP BAR  : Transaction # | Cashier | Shortcut pills
  LEFT     : Product Search bar + Cart table (70% width)
  RIGHT    : Order Summary + Payment (30% width)

Popups:
  Product Search → F2 / Browse  (full two-column browser)
  Inline Search  → Type in search bar → dropdown appears (quick add)
  Qty Editor     → Double-click row
  Discount       → F6 / Discount button
  Payment        → F8 / PAY button
  Receipt        → Auto on successful sale

Payment methods: Cash (change computed) | GCash (ref # recorded)
"""

import customtkinter as ctk
from tkinter import ttk
import datetime

from database import get_connection
from security import log_audit
from utils.helpers import generate_transaction_number, format_currency
from ui.cashdrawer_window import get_any_active_session, CloseDrawerDialog
from ui.theme import (
    BG_DARK, BG_CARD, BG_CARD_ALT, BG_INPUT, BG_HOVER, BORDER,
    ACCENT, ACCENT_HOVER, ACCENT_LIGHT, ACCENT_SUBTLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    SUCCESS, SUCCESS_HOVER, DANGER, DANGER_HOVER, WARNING, INFO,
    style_treeview,
    msg_info, msg_warning, msg_error, msg_success, msg_question,
)

GCASH_BLUE   = "#0070E0"
GCASH_HOVER  = "#005BB5"
GCASH_LIGHT  = "#E8F2FF"
GCASH_BORDER = "#0070E0"

VAT_RATE = 0.12


# ══════════════════════════════════════════════════════════════
#  HELPER
# ══════════════════════════════════════════════════════════════

def _centre(win, parent, w, h):
    px = parent.winfo_rootx() + parent.winfo_width()  // 2 - w // 2
    py = parent.winfo_rooty() + parent.winfo_height() // 2 - h // 2
    win.geometry(f"{w}x{h}+{max(0,px)}+{max(0,py)}")


# ══════════════════════════════════════════════════════════════
#  INLINE PRODUCT SEARCH DROPDOWN
# ══════════════════════════════════════════════════════════════

class _ProductDropdown(ctk.CTkToplevel):
    """
    Borderless floating dropdown that appears below the cart search bar
    when the user types.  Selecting a row (click or Enter) immediately
    adds qty=1 of that product to the cart, then dismisses itself.

    Navigation:
      ↑ / ↓   — move cursor through rows
      Enter   — confirm selection
      Escape  — dismiss without adding
      Click   — confirm selection
      FocusOut (after 150 ms delay) — dismiss

    The parent SalesFrame owns the lifecycle; call destroy() to close.
    """

    MAX_ROWS = 8

    def __init__(self, parent_window, anchor_widget, products, on_pick_cb):
        super().__init__(parent_window)
        self._cb       = on_pick_cb
        self._products = products
        self._cursor   = -1

        # Borderless, always-on-top floating window
        self.overrideredirect(True)
        self.configure(fg_color=BG_CARD)
        self.attributes("-topmost", True)

        # Position flush below the anchor entry widget
        self._reposition(anchor_widget)

        # Outer frame with border to visually separate from background
        frame = ctk.CTkFrame(
            self,
            fg_color=BG_CARD,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
        )
        frame.pack(fill="both", expand=True)

        # Product table
        cols = ("name", "price", "stock")
        self._tree = ttk.Treeview(
            frame,
            columns=cols,
            show="headings",
            height=min(len(products), self.MAX_ROWS),
        )
        for col, lbl, w, anchor in [
            ("name",  "Product",  260, "w"),
            ("price", "Price",     90, "e"),
            ("stock", "In Stock",  70, "center"),
        ]:
            self._tree.heading(col, text=lbl)
            self._tree.column(col, width=w, minwidth=40, anchor=anchor)
        style_treeview(self._tree, row_height=30)

        vsb = ttk.Scrollbar(frame, orient="vertical",
                            command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True,
                        padx=(4, 0), pady=4)
        vsb.pack(side="right", fill="y", pady=4, padx=(0, 4))

        self._populate()

        self._tree.bind("<ButtonRelease-1>", self._on_click)
        self._tree.bind("<Double-1>",        self._on_click)

    # ── Layout ───────────────────────────────────────────────

    def _reposition(self, widget):
        """Size and place the dropdown directly below *widget*."""
        widget.update_idletasks()
        x = widget.winfo_rootx()
        y = widget.winfo_rooty() + widget.winfo_height() + 2
        w = widget.winfo_width()
        h = min(len(self._products), self.MAX_ROWS) * 30 + 16
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ── Data ─────────────────────────────────────────────────

    def _populate(self):
        for r in self._tree.get_children():
            self._tree.delete(r)
        for i, p in enumerate(self._products):
            stk = p["current_stock"]
            if stk <= 0:
                tag = "out"
            elif stk <= p.get("low_stock_threshold", 5):
                tag = "low"
            else:
                tag = "evenrow" if i % 2 == 0 else "oddrow"
            self._tree.insert(
                "", "end", iid=str(p["id"]),
                values=(
                    p["name"],
                    f"₱{p['selling_price']:,.2f}",
                    stk,
                ),
                tags=(tag,),
            )
        self._tree.tag_configure("out", foreground="#AAAAAA")

    # ── Keyboard API (called by SalesFrame) ──────────────────

    def move_cursor(self, direction: int):
        """Move selection up (-1) or down (+1) through the rows."""
        children = self._tree.get_children()
        if not children:
            return
        if self._cursor == -1:
            self._cursor = 0 if direction > 0 else len(children) - 1
        else:
            self._cursor = (self._cursor + direction) % len(children)
        iid = children[self._cursor]
        self._tree.selection_set(iid)
        self._tree.see(iid)

    def pick_selected(self):
        """Confirm whichever row is currently selected."""
        sel = self._tree.selection()
        if sel:
            pid = int(sel[0])
            p   = next((x for x in self._products if x["id"] == pid), None)
            if p:
                self._cb(p)

    # ── Internal events ──────────────────────────────────────

    def _on_click(self, event=None):
        self.pick_selected()


# ══════════════════════════════════════════════════════════════
#  PRODUCT SEARCH POPUP  (F2)
# ══════════════════════════════════════════════════════════════

class ProductSearchPopup(ctk.CTkToplevel):
    """
    Two-column product browser.
    LEFT  : searchable product list with category filter pills
    RIGHT : staging basket — review before sending to cart
    """

    def __init__(self, parent, all_products, on_select_cb, on_close_cb):
        super().__init__(parent)
        self._all       = all_products
        self._select_cb = on_select_cb
        self._close_cb  = on_close_cb
        self._staged    = []

        self.title("Add Products")
        self.resizable(True, True)
        self.configure(fg_color=BG_CARD)
        self.grab_set()
        self.focus_force()
        _centre(self, parent, 960, 620)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda e: self._on_close())

        # ── Compact header ──────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=ACCENT, corner_radius=0, height=44)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(
            hdr, text="Add Products to Cart",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#FFFFFF",
        ).pack(side="left", padx=16)

        # ── Two-column body ──────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=10)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        self._build_product_browser(body)
        self._build_staging_panel(body)
        self._populate(all_products)

    # ── LEFT: product browser ────────────────────────────────

    def _build_product_browser(self, parent):
        left = ctk.CTkFrame(parent, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)

        # Search bar
        self._q = ctk.StringVar()
        self._q.trace("w", lambda *_: self._filter())
        self._entry = ctk.CTkEntry(
            left, textvariable=self._q,
            placeholder_text="🔍  Search by name or code…",
            height=38, fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=12), corner_radius=8,
        )
        self._entry.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self._entry.focus()

        # Category pills
        cats = sorted({p["category"] for p in self._all if p.get("category")})
        self._cat = ctk.StringVar(value="All")
        self._pill_btns = {}
        cf = ctk.CTkScrollableFrame(
            left, orientation="horizontal", height=38,
            fg_color="transparent",
            scrollbar_button_color=BG_HOVER,
            scrollbar_button_hover_color=BORDER,
        )
        cf.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        for label in ["All"] + cats:
            btn = ctk.CTkButton(
                cf, text=label, height=28, corner_radius=14,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                command=lambda l=label: self._set_cat(l),
            )
            btn.pack(side="left", padx=(0, 5))
            self._pill_btns[label] = btn
        self._update_pills()

        # Product table
        tf = ctk.CTkFrame(left, fg_color=BG_CARD_ALT, corner_radius=10)
        tf.grid(row=2, column=0, sticky="nsew")
        cols = ("code", "name", "category", "price", "stock")
        self._tree = ttk.Treeview(tf, columns=cols, show="headings")
        for col, lbl, w, anchor in [
            ("code",     "Code",     70,  "w"),
            ("name",     "Product", 230,  "w"),
            ("category", "Category", 95,  "w"),
            ("price",    "Price",    85,  "e"),
            ("stock",    "Stock",    55,  "center"),
        ]:
            self._tree.heading(col, text=lbl)
            self._tree.column(col, width=w, minwidth=40, anchor=anchor)
        style_treeview(self._tree, row_height=30)
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True,
                        padx=(4, 0), pady=4)
        vsb.pack(side="right", fill="y", pady=4, padx=(0, 4))
        self._tree.bind("<Double-1>", self._stage_selected)
        self._tree.bind("<Return>",   self._stage_selected)

        self._count_lbl = ctk.CTkLabel(
            left, text="",
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=10),
        )
        self._count_lbl.grid(row=3, column=0, sticky="w", pady=(4, 0))

    # ── RIGHT: staging panel ─────────────────────────────────

    def _build_staging_panel(self, parent):
        right = ctk.CTkFrame(parent, fg_color=BG_CARD_ALT, corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(2, weight=1)
        right.grid_columnconfigure(0, weight=1)

        # Header row
        rh = ctk.CTkFrame(right, fg_color="transparent")
        rh.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(
            rh, text="🛒  Staging",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=ACCENT,
        ).pack(side="left")
        self._staged_count_lbl = ctk.CTkLabel(
            rh, text="Empty",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=TEXT_MUTED,
        )
        self._staged_count_lbl.pack(side="left", padx=8)

        # Qty row
        qf = ctk.CTkFrame(right, fg_color="transparent")
        qf.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 4))
        qf.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(
            qf, text="Qty",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_SECONDARY,
        ).grid(row=0, column=0, padx=(0, 4))
        ctk.CTkButton(
            qf, text="−", width=30, height=30,
            fg_color=BG_HOVER, hover_color=BORDER, text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            corner_radius=6, command=self._dec_qty,
        ).grid(row=0, column=1)
        self._qty_var = ctk.StringVar(value="1")
        ctk.CTkEntry(
            qf, textvariable=self._qty_var,
            height=30, justify="center", width=50,
            fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Segoe UI", size=12), corner_radius=6,
        ).grid(row=0, column=2, sticky="ew", padx=4)
        ctk.CTkButton(
            qf, text="+", width=30, height=30,
            fg_color=BG_HOVER, hover_color=BORDER, text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            corner_radius=6, command=self._inc_qty,
        ).grid(row=0, column=3)
        ctk.CTkButton(
            qf, text="+ Add", height=30,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=6, command=self._stage_selected,
        ).grid(row=0, column=4, sticky="ew", padx=(6, 0))

        # Staged list
        stf = ctk.CTkFrame(right, fg_color=BG_CARD, corner_radius=8)
        stf.grid(row=2, column=0, sticky="nsew", padx=12, pady=4)
        scols = ("name", "qty", "price")
        self._staged_tree = ttk.Treeview(stf, columns=scols,
                                          show="headings", height=8)
        self._staged_tree.heading("name",  text="Product")
        self._staged_tree.heading("qty",   text="Qty")
        self._staged_tree.heading("price", text="Price")
        self._staged_tree.column("name",  width=155, minwidth=100)
        self._staged_tree.column("qty",   width=45, anchor="center")
        self._staged_tree.column("price", width=75, anchor="e")
        style_treeview(self._staged_tree, row_height=28)
        self._staged_tree.pack(fill="both", expand=True, padx=4, pady=4)

        # Remove / Clear
        rb = ctk.CTkFrame(right, fg_color="transparent")
        rb.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 6))
        rb.grid_columnconfigure(0, weight=1)
        rb.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(
            rb, text="Remove", height=28,
            fg_color=BG_HOVER, hover_color=DANGER, text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=6, command=self._remove_staged,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(
            rb, text="Clear", height=28,
            fg_color=BG_HOVER, hover_color=BORDER, text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=6, command=self._clear_staged,
        ).grid(row=0, column=1, sticky="ew")

        # Footer: Cancel / Confirm
        foot = ctk.CTkFrame(right, fg_color="transparent")
        foot.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 12))
        ctk.CTkButton(
            foot, text="Cancel", height=38, width=80,
            fg_color=BG_HOVER, hover_color=BORDER, text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            corner_radius=8, command=self._on_close,
        ).pack(side="left")
        self._confirm_btn = ctk.CTkButton(
            foot,
            text="✔  Add to Cart",
            height=38,
            fg_color=SUCCESS, hover_color=SUCCESS_HOVER, text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            corner_radius=8, command=self._confirm_all,
        )
        self._confirm_btn.pack(side="right", expand=True, fill="x", padx=(8, 0))

    # ── Helpers ──────────────────────────────────────────────

    def _on_close(self):
        self._close_cb()
        self.destroy()

    def _set_cat(self, cat):
        self._cat.set(cat)
        self._update_pills()
        self._filter()

    def _update_pills(self):
        active = self._cat.get()
        for label, btn in self._pill_btns.items():
            if label == active:
                btn.configure(fg_color=ACCENT, hover_color=ACCENT_HOVER,
                              text_color="#FFFFFF", border_width=0)
            else:
                btn.configure(fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
                              text_color=TEXT_SECONDARY,
                              border_width=1, border_color=BORDER)

    def _filter(self):
        q   = self._q.get().lower()
        cat = self._cat.get()
        res = [
            p for p in self._all
            if (q in p["name"].lower() or q in (p.get("code") or "").lower())
            and (cat == "All" or p.get("category") == cat)
        ]
        self._populate(res)

    def _populate(self, products):
        for r in self._tree.get_children():
            self._tree.delete(r)
        for i, p in enumerate(products):
            stk = p["current_stock"]
            if stk <= 0:
                tag = "out"
            elif stk <= p.get("low_stock_threshold", 5):
                tag = "low"
            else:
                tag = "evenrow" if i % 2 == 0 else "oddrow"
            self._tree.insert(
                "", "end", iid=str(p["id"]),
                values=(
                    p.get("code", ""),
                    p["name"],
                    p.get("category") or "—",
                    f"₱{p['selling_price']:,.2f}",
                    stk,
                ),
                tags=(tag,),
            )
        self._tree.tag_configure("out", foreground="#AAAAAA")
        self._count_lbl.configure(text=f"{len(products)} product(s) found")

    def _get_qty(self):
        try:
            return max(1, int(self._qty_var.get()))
        except ValueError:
            return 1

    def _inc_qty(self):
        self._qty_var.set(str(self._get_qty() + 1))

    def _dec_qty(self):
        self._qty_var.set(str(max(1, self._get_qty() - 1)))

    def _stage_selected(self, event=None):
        sel = self._tree.selection()
        if not sel:
            return
        pid = int(sel[0])
        p   = next((x for x in self._all if x["id"] == pid), None)
        if not p:
            return
        if p["current_stock"] <= 0:
            msg_warning(self, "Out of Stock",
                        f"'{p['name']}' has no stock available.")
            return
        qty = self._get_qty()
        for s in self._staged:
            if s["product"]["id"] == pid:
                new_qty = s["qty"] + qty
                if new_qty > p["current_stock"]:
                    msg_warning(self, "Exceeds Stock",
                        f"Only {p['current_stock']} unit(s) available for '{p['name']}'.")
                    return
                s["qty"] = new_qty
                self._refresh_staged()
                return
        if qty > p["current_stock"]:
            msg_warning(self, "Exceeds Stock",
                        f"Only {p['current_stock']} unit(s) available.")
            return
        self._staged.append({"product": p, "qty": qty})
        self._refresh_staged()
        self._qty_var.set("1")

    def _refresh_staged(self):
        for r in self._staged_tree.get_children():
            self._staged_tree.delete(r)
        for i, s in enumerate(self._staged):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self._staged_tree.insert(
                "", "end", iid=str(i),
                values=(
                    s["product"]["name"],
                    s["qty"],
                    f"₱{s['product']['selling_price']:,.2f}",
                ),
                tags=(tag,),
            )
        n = len(self._staged)
        self._staged_count_lbl.configure(
            text=f"{n} item(s)" if n else "Empty")
        self._confirm_btn.configure(
            text=f"✔  Add {n} to Cart" if n else "✔  Add to Cart")

    def _remove_staged(self):
        sel = self._staged_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self._staged):
            self._staged.pop(idx)
            self._refresh_staged()

    def _clear_staged(self):
        self._staged.clear()
        self._refresh_staged()

    def _confirm_all(self):
        if not self._staged:
            msg_warning(self, "Nothing Staged",
                        "Select products and click \"+ Add\" before confirming.")
            return
        for s in self._staged:
            self._select_cb(s["product"], s["qty"])
        self._on_close()


# ══════════════════════════════════════════════════════════════
#  QTY EDITOR POPUP  (double-click row)
# ══════════════════════════════════════════════════════════════

class QtyEditPopup(ctk.CTkToplevel):
    def __init__(self, parent, item: dict, on_save_cb):
        super().__init__(parent)
        self._item = item
        self._cb   = on_save_cb

        self.title("Edit Quantity")
        self.resizable(False, False)
        self.configure(fg_color=BG_CARD)
        self.grab_set()
        self.focus_force()
        _centre(self, parent, 300, 390)

        # Header
        hdr = ctk.CTkFrame(self, fg_color=ACCENT, corner_radius=0, height=46)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(
            hdr, text="Edit Quantity",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#FFFFFF",
        ).pack(side="left", padx=16)

        # Product info
        ctk.CTkLabel(
            self, text=item["name"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_PRIMARY, wraplength=260,
        ).pack(pady=(12, 2), padx=16)
        ctk.CTkLabel(
            self,
            text=f"₱{item['price']:,.2f} / unit  •  {item['stock']} in stock",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
        ).pack()

        # Qty display
        self._qty_var = ctk.StringVar(value=str(item["qty"]))
        ctk.CTkEntry(
            self, textvariable=self._qty_var,
            height=48, justify="center",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, corner_radius=10,
        ).pack(fill="x", padx=20, pady=10)

        # Numpad
        pad = ctk.CTkFrame(self, fg_color="transparent")
        pad.pack(padx=20)
        for row in [["7","8","9"], ["4","5","6"], ["1","2","3"], ["←","0","✓"]]:
            r = ctk.CTkFrame(pad, fg_color="transparent")
            r.pack(fill="x", pady=2)
            for d in row:
                fc = SUCCESS if d == "✓" else (BG_HOVER if d == "←" else BG_CARD_ALT)
                hc = SUCCESS_HOVER if d == "✓" else (BORDER if d == "←" else BG_HOVER)
                tc = "#FFFFFF" if d == "✓" else (TEXT_SECONDARY if d == "←" else TEXT_PRIMARY)
                ctk.CTkButton(
                    r, text=d, width=64, height=40,
                    fg_color=fc, hover_color=hc, text_color=tc,
                    font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                    corner_radius=8,
                    command=lambda x=d: self._press(x),
                ).pack(side="left", padx=2)

        self.bind("<Return>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self.destroy())

    def _press(self, k):
        cur = self._qty_var.get()
        if k == "←":
            self._qty_var.set(cur[:-1] or "0")
        elif k == "✓":
            self._save()
        else:
            self._qty_var.set(
                "0" if cur == "0" else cur + k if cur != "0" else k)

    def _save(self):
        try:
            qty = int(self._qty_var.get())
        except ValueError:
            qty = 1
        if qty <= 0:
            msg_warning(self, "Invalid", "Quantity must be at least 1.")
            return
        if qty > self._item["stock"]:
            msg_warning(self, "Exceeds Stock",
                        f"Only {self._item['stock']} unit(s) in stock.")
            return
        self._cb(qty)
        self.destroy()


# ══════════════════════════════════════════════════════════════
#  DISCOUNT POPUP  (F6 / Ctrl+D)
# ══════════════════════════════════════════════════════════════

class DiscountPopup(ctk.CTkToplevel):
    def __init__(self, parent, subtotal, current_discount, on_save_cb):
        super().__init__(parent)
        self._sub = subtotal
        self._cb  = on_save_cb

        self.title("Apply Discount")
        self.resizable(False, False)
        self.configure(fg_color=BG_CARD)
        self.grab_set()
        self.focus_force()
        _centre(self, parent, 360, 390)

        hdr = ctk.CTkFrame(self, fg_color=WARNING, corner_radius=0, height=46)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(
            hdr, text="🏷  Apply Discount",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#FFFFFF",
        ).pack(side="left", padx=16)

        ctk.CTkLabel(
            self, text=f"Subtotal  ₱{subtotal:,.2f}",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_MUTED,
        ).pack(pady=(12, 4))

        self._mode = ctk.StringVar(value="peso")
        tog = ctk.CTkFrame(self, fg_color=BG_CARD_ALT, corner_radius=10)
        tog.pack(padx=20, fill="x")
        tr = ctk.CTkFrame(tog, fg_color="transparent")
        tr.pack(pady=8)
        for lbl, val in [("₱ Fixed Amount", "peso"), ("% Percentage", "pct")]:
            ctk.CTkRadioButton(
                tr, text=lbl, variable=self._mode, value=val,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=TEXT_PRIMARY, fg_color=ACCENT,
                command=lambda: (self._val_var.set(""), self._preview()),
            ).pack(side="left", padx=14)

        ctk.CTkLabel(
            self, text="Amount:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_SECONDARY, anchor="w",
        ).pack(fill="x", padx=20, pady=(10, 3))

        self._val_var = ctk.StringVar(
            value=str(current_discount) if current_discount else "")
        ctk.CTkEntry(
            self, textvariable=self._val_var,
            height=44, justify="center",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, corner_radius=10,
        ).pack(fill="x", padx=20)

        self.after(100, lambda: self.focus_force())
        self._val_var.trace("w", lambda *_: self._preview())

        # Quick % presets
        pf = ctk.CTkFrame(self, fg_color="transparent")
        pf.pack(fill="x", padx=20, pady=8)
        ctk.CTkLabel(
            pf, text="Quick %:", text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=11),
        ).pack(anchor="w")
        pr = ctk.CTkFrame(pf, fg_color="transparent")
        pr.pack(fill="x")
        for p in [5, 10, 15, 20, 25, 50]:
            ctk.CTkButton(
                pr, text=f"{p}%", width=48, height=28,
                fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
                text_color=TEXT_SECONDARY, border_width=1, border_color=BORDER,
                font=ctk.CTkFont(family="Segoe UI", size=11), corner_radius=7,
                command=lambda x=p: self._set_pct(x),
            ).pack(side="left", padx=2)

        self._prev_lbl = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=WARNING,
        )
        self._prev_lbl.pack(pady=4)

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=20, pady=(6, 14))
        ctk.CTkButton(
            foot, text="Remove Discount", height=38,
            fg_color=BG_HOVER, hover_color=BORDER, text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(family="Segoe UI", size=12), corner_radius=8,
            command=lambda: (self._cb(0.0), self.destroy()),
        ).pack(side="left")
        ctk.CTkButton(
            foot, text="Apply", height=38,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            corner_radius=8, command=self._save,
        ).pack(side="right")

        self.bind("<Return>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self.destroy())
        self._preview()

    def _set_pct(self, p):
        self._mode.set("pct")
        self._val_var.set(str(p))

    def _preview(self):
        try:
            v    = float(self._val_var.get() or 0)
            disc = self._sub * v / 100 if self._mode.get() == "pct" else v
            self._prev_lbl.configure(
                text=(
                    f"Discount  ₱{disc:,.2f}  →  "
                    f"New Total  ₱{max(self._sub - disc, 0):,.2f}"
                ),
                text_color=WARNING if disc > 0 else TEXT_MUTED,
            )
        except ValueError:
            self._prev_lbl.configure(text="", text_color=TEXT_MUTED)

    def _save(self):
        try:
            v = float(self._val_var.get() or 0)
        except ValueError:
            msg_warning(self, "Invalid", "Enter a valid number.")
            return
        if self._mode.get() == "pct":
            if not 0 <= v <= 100:
                msg_warning(self, "Invalid %", "Must be 0–100.")
                return
            disc = self._sub * v / 100
        else:
            disc = v
        if disc > self._sub:
            msg_warning(self, "Too High",
                        "Discount cannot exceed subtotal.")
            return
        self._cb(round(disc, 2))
        self.destroy()


# ══════════════════════════════════════════════════════════════
#  PAYMENT POPUP  (F8)
# ══════════════════════════════════════════════════════════════

class PaymentPopup(ctk.CTkToplevel):
    """
    Cash tab  : quick-cash presets + numpad, live change display
    GCash tab : reference number + exact amount (no change)
    """

    def __init__(self, parent, total_amount: float, on_confirm_cb):
        super().__init__(parent)
        self._total = total_amount
        self._cb    = on_confirm_cb

        self.title("Payment")
        self.resizable(False, False)
        self.configure(fg_color=BG_CARD)
        self.grab_set()
        self.focus_force()
        _centre(self, parent, 440, 640)

        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header
        hdr = ctk.CTkFrame(self, fg_color=SUCCESS, corner_radius=0, height=50)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.pack_propagate(False)
        ctk.CTkLabel(
            hdr, text="Payment",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color="#FFFFFF",
        ).pack(side="left", padx=16)
        ctk.CTkLabel(
            hdr, text=f"Total  ₱{total_amount:,.2f}",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#C8FFD8",
        ).pack(side="right", padx=16)

        # Total banner
        tot_box = ctk.CTkFrame(self, fg_color=ACCENT_SUBTLE, corner_radius=10)
        tot_box.grid(row=1, column=0, sticky="ew", padx=16, pady=(12, 6))
        ctk.CTkLabel(
            tot_box, text="TOTAL DUE",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=ACCENT,
        ).pack(pady=(8, 0))
        ctk.CTkLabel(
            tot_box, text=f"₱{total_amount:,.2f}",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(pady=(0, 8))

        # Method tabs
        self._method = ctk.StringVar(value="cash")
        tab_row = ctk.CTkFrame(self, fg_color=BG_CARD_ALT, corner_radius=10)
        tab_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))
        tr = ctk.CTkFrame(tab_row, fg_color="transparent")
        tr.pack(pady=6)

        self._cash_btn = ctk.CTkButton(
            tr, text="💵  CASH", width=140, height=38,
            fg_color=SUCCESS, hover_color=SUCCESS_HOVER, text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            corner_radius=8, command=lambda: self._switch("cash"),
        )
        self._cash_btn.pack(side="left", padx=6)

        self._gcash_btn = ctk.CTkButton(
            tr, text="  GCash", width=140, height=38,
            fg_color=BG_HOVER, hover_color=BORDER, text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            corner_radius=8, command=lambda: self._switch("gcash"),
        )
        self._gcash_btn.pack(side="left", padx=6)

        # Content area
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.grid(row=3, column=0, sticky="nsew", padx=16)
        self._cash_panel  = ctk.CTkFrame(self._content, fg_color="transparent")
        self._gcash_panel = ctk.CTkFrame(self._content, fg_color="transparent")
        self._build_cash_panel(self._cash_panel)
        self._build_gcash_panel(self._gcash_panel)
        self._cash_panel.pack(fill="both", expand=True)

        # Footer
        foot = ctk.CTkFrame(self, fg_color=BG_CARD_ALT, corner_radius=0)
        foot.grid(row=4, column=0, sticky="ew")
        inner = ctk.CTkFrame(foot, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=12)
        ctk.CTkButton(
            inner, text="Cancel", height=48, width=110,
            fg_color=DANGER, hover_color=DANGER_HOVER, text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            corner_radius=10, command=self.destroy,
        ).pack(side="left")
        self._confirm_btn = ctk.CTkButton(
            inner, text="✔  Confirm Payment", height=48,
            fg_color=SUCCESS, hover_color=SUCCESS_HOVER, text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            corner_radius=10, command=self._confirm,
        )
        self._confirm_btn.pack(side="right", expand=True, fill="x",
                               padx=(10, 0))

        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self._confirm())

    def _build_cash_panel(self, parent):
        self._cash_amt = ctk.StringVar(value="")
        self._cash_amt.trace("w", lambda *_: self._recompute_cash())

        ctk.CTkEntry(
            parent, textvariable=self._cash_amt,
            height=50, justify="center",
            placeholder_text="Enter amount…",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_MUTED,
            corner_radius=10,
        ).pack(fill="x", pady=(0, 4))

        self._change_lbl = ctk.CTkLabel(
            parent, text="Change: —",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=TEXT_MUTED,
        )
        self._change_lbl.pack(pady=(0, 4))

        # Quick cash presets
        qf = ctk.CTkFrame(parent, fg_color="transparent")
        qf.pack(fill="x")
        ctk.CTkLabel(
            qf, text="Quick Cash:", text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=11),
        ).pack(anchor="w")
        qr = ctk.CTkFrame(qf, fg_color="transparent")
        qr.pack(fill="x")
        for amt in [20, 50, 100, 200, 500, 1000]:
            ctk.CTkButton(
                qr, text=f"₱{amt}", width=56, height=30,
                fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
                text_color=ACCENT, border_width=1, border_color=BORDER,
                font=ctk.CTkFont(family="Segoe UI", size=11), corner_radius=7,
                command=lambda a=amt: self._cash_amt.set(f"{a:.2f}"),
            ).pack(side="left", padx=2, pady=3)
        ctk.CTkButton(
            qr, text="Exact", width=56, height=30,
            fg_color=ACCENT_SUBTLE, hover_color=BG_HOVER,
            text_color=ACCENT, border_width=1, border_color=BORDER,
            font=ctk.CTkFont(family="Segoe UI", size=11), corner_radius=7,
            command=lambda: self._cash_amt.set(f"{self._total:.2f}"),
        ).pack(side="left", padx=2, pady=3)

        # Numpad
        pad = ctk.CTkFrame(parent, fg_color="transparent")
        pad.pack(pady=4)
        for row in [["7","8","9"], ["4","5","6"], ["1","2","3"], [".","0","←"]]:
            r = ctk.CTkFrame(pad, fg_color="transparent")
            r.pack(fill="x", pady=2)
            for d in row:
                fc = BG_HOVER if d == "←" else BG_CARD_ALT
                hc = BORDER   if d == "←" else BG_HOVER
                tc = TEXT_SECONDARY if d == "←" else TEXT_PRIMARY
                ctk.CTkButton(
                    r, text=d, width=88, height=42,
                    fg_color=fc, hover_color=hc, text_color=tc,
                    font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
                    corner_radius=8,
                    command=lambda x=d: self._num_press(x),
                ).pack(side="left", padx=3)

    def _num_press(self, k):
        cur = self._cash_amt.get()
        if k == "←":
            self._cash_amt.set(cur[:-1])
        elif k == "." and "." in cur:
            return
        else:
            self._cash_amt.set(cur + k)

    def _recompute_cash(self):
        try:
            v   = float(self._cash_amt.get() or 0)
            chg = v - self._total
            if v == 0:
                self._change_lbl.configure(
                    text="Change: —", text_color=TEXT_MUTED)
            elif chg >= 0:
                self._change_lbl.configure(
                    text=f"Change: ₱{chg:,.2f}", text_color=SUCCESS)
            else:
                self._change_lbl.configure(
                    text=f"Short by ₱{abs(chg):,.2f}", text_color=DANGER)
        except ValueError:
            self._change_lbl.configure(text="Change: —", text_color=TEXT_MUTED)

    def _build_gcash_panel(self, parent):
        gb = ctk.CTkFrame(parent, fg_color=GCASH_BLUE,
                          corner_radius=10, height=48)
        gb.pack(fill="x", pady=(0, 10))
        gb.pack_propagate(False)
        ctk.CTkLabel(
            gb, text="  GCash Payment",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color="#FFFFFF",
        ).pack(expand=True)

        ctk.CTkLabel(
            parent, text="Amount Sent via GCash:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_SECONDARY, anchor="w",
        ).pack(fill="x")

        self._gcash_amt = ctk.StringVar(value=f"{self._total:.2f}")
        ctk.CTkEntry(
            parent, textvariable=self._gcash_amt,
            height=46, justify="center",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            fg_color=GCASH_LIGHT, border_color=GCASH_BORDER,
            text_color=GCASH_BLUE, corner_radius=10,
        ).pack(fill="x", pady=(4, 10))

        ctk.CTkLabel(
            parent, text="GCash Reference # (optional):",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_SECONDARY, anchor="w",
        ).pack(fill="x")

        self._gcash_ref = ctk.StringVar()
        ctk.CTkEntry(
            parent, textvariable=self._gcash_ref,
            height=42, placeholder_text="e.g. 1234567890",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_MUTED,
            corner_radius=10,
        ).pack(fill="x", pady=(4, 0))

        ctk.CTkLabel(
            parent,
            text=(
                "ℹ  GCash transactions are recorded separately\n"
                "   and can be viewed in Reports → Payment Method."
            ),
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=TEXT_MUTED, justify="left",
        ).pack(pady=(12, 0), anchor="w")

    def _switch(self, method):
        self._method.set(method)
        if method == "cash":
            self._gcash_panel.pack_forget()
            self._cash_panel.pack(fill="both", expand=True)
            self._cash_btn.configure(
                fg_color=SUCCESS, hover_color=SUCCESS_HOVER,
                text_color="#FFFFFF")
            self._gcash_btn.configure(
                fg_color=BG_HOVER, hover_color=BORDER,
                text_color=TEXT_SECONDARY)
            self._confirm_btn.configure(
                fg_color=SUCCESS, hover_color=SUCCESS_HOVER)
        else:
            self._cash_panel.pack_forget()
            self._gcash_panel.pack(fill="both", expand=True)
            self._gcash_btn.configure(
                fg_color=GCASH_BLUE, hover_color=GCASH_HOVER,
                text_color="#FFFFFF")
            self._cash_btn.configure(
                fg_color=BG_HOVER, hover_color=BORDER,
                text_color=TEXT_SECONDARY)
            self._confirm_btn.configure(
                fg_color=GCASH_BLUE, hover_color=GCASH_HOVER)

    def _confirm(self):
        method = self._method.get()
        if method == "cash":
            try:
                amt = float(self._cash_amt.get() or 0)
            except ValueError:
                msg_warning(self, "Invalid", "Enter a valid amount.")
                return
            if amt < self._total:
                msg_warning(
                    self, "Insufficient",
                    f"Tendered ₱{amt:,.2f} is less than total ₱{self._total:,.2f}.",
                )
                return
            self._cb("cash", amt, "")
        else:
            try:
                amt = float(self._gcash_amt.get() or 0)
            except ValueError:
                msg_warning(self, "Invalid",
                            "Enter the GCash amount sent.")
                return
            if amt < self._total:
                msg_warning(
                    self, "Insufficient",
                    f"GCash amount ₱{amt:,.2f} is less than total ₱{self._total:,.2f}.",
                )
                return
            ref = self._gcash_ref.get().strip()
            self._cb("gcash", amt, ref)
        self.destroy()


# ══════════════════════════════════════════════════════════════
#  RECEIPT POPUP
# ══════════════════════════════════════════════════════════════

class ReceiptPopup(ctk.CTkToplevel):
    def __init__(self, parent, txn_num, cashier_name, items,
                 subtotal, discount, vat, total, tendered, change,
                 payment_method, gcash_ref, notes):
        super().__init__(parent)
        self.title("Transaction Receipt")
        self.resizable(False, True)
        self.configure(fg_color=BG_CARD)
        self.grab_set()
        self.focus_force()
        _centre(self, parent, 640, 680)

        is_gcash  = payment_method == "gcash"
        hdr_color = GCASH_BLUE if is_gcash else ACCENT

        # ── Header bar ────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=hdr_color, corner_radius=0, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        ctk.CTkLabel(
            hdr, text="🧾  VMDC Motor Parts",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color="#FFFFFF",
        ).pack(side="left", padx=20)
        ctk.CTkLabel(
            hdr, text="Official Sales Receipt",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#CCDDFF",
        ).pack(side="right", padx=20)

        # ── Scrollable body ───────────────────────────────────────────
        scroll = ctk.CTkScrollableFrame(self, fg_color=BG_CARD, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=0)

        PAD = 24   # horizontal outer padding

        def sep(pady=8):
            ctk.CTkFrame(scroll, fg_color=BORDER, height=1).pack(
                fill="x", padx=PAD, pady=pady)

        def section_label(text):
            ctk.CTkLabel(
                scroll, text=text,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=TEXT_MUTED, anchor="w",
            ).pack(fill="x", padx=PAD, pady=(10, 4))

        # ── Transaction meta: 2-column info grid ──────────────────────
        now = datetime.datetime.now().strftime("%b %d, %Y  %I:%M %p")

        meta_frame = ctk.CTkFrame(scroll, fg_color=BG_CARD_ALT, corner_radius=8)
        meta_frame.pack(fill="x", padx=PAD, pady=(16, 0))
        meta_frame.columnconfigure((0, 1, 2, 3), weight=1, uniform="col")

        def meta_cell(parent, row, col, label, value, val_color=TEXT_PRIMARY):
            cell = ctk.CTkFrame(parent, fg_color="transparent")
            cell.grid(row=row, column=col, padx=14, pady=10, sticky="w")
            ctk.CTkLabel(
                cell, text=label,
                font=ctk.CTkFont(family="Segoe UI", size=9),
                text_color=TEXT_MUTED,
            ).pack(anchor="w")
            ctk.CTkLabel(
                cell, text=value,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=val_color,
            ).pack(anchor="w")

        meta_cell(meta_frame, 0, 0, "TRANSACTION #", txn_num, hdr_color)
        meta_cell(meta_frame, 0, 1, "DATE & TIME",   now)
        meta_cell(meta_frame, 0, 2, "CASHIER",       cashier_name)
        pay_label = "GCash" if is_gcash else "Cash"
        pay_color = GCASH_BLUE if is_gcash else SUCCESS
        meta_cell(meta_frame, 0, 3, "PAYMENT",       pay_label, pay_color)

        if is_gcash and gcash_ref:
            ref_bar = ctk.CTkFrame(scroll, fg_color=GCASH_LIGHT, corner_radius=6)
            ref_bar.pack(fill="x", padx=PAD, pady=(6, 0))
            ctk.CTkLabel(
                ref_bar, text=f"  GCash Reference #:  {gcash_ref}",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=GCASH_BLUE,
            ).pack(side="left", pady=8)

        sep(pady=12)

        # ── Items table ───────────────────────────────────────────────
        section_label("ITEMS PURCHASED")

        tbl_frame = ctk.CTkFrame(scroll, fg_color="transparent", corner_radius=0)
        tbl_frame.pack(fill="x", padx=PAD)
        tbl_frame.columnconfigure(0, weight=1)      # item name
        tbl_frame.columnconfigure(1, weight=0, minsize=60)   # qty
        tbl_frame.columnconfigure(2, weight=0, minsize=90)   # unit price
        tbl_frame.columnconfigure(3, weight=0, minsize=100)  # subtotal

        # Table header
        hdr_bg = BG_CARD_ALT
        th_font = ctk.CTkFont(family="Segoe UI", size=10, weight="bold")
        th_fg   = TEXT_MUTED
        th_row  = ctk.CTkFrame(tbl_frame, fg_color=hdr_bg, corner_radius=6)
        th_row.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 2))
        th_row.columnconfigure(0, weight=1)
        th_row.columnconfigure(1, weight=0, minsize=60)
        th_row.columnconfigure(2, weight=0, minsize=90)
        th_row.columnconfigure(3, weight=0, minsize=100)

        for col_i, (col_txt, anchor) in enumerate([
            ("ITEM / DESCRIPTION", "w"),
            ("QTY",                "center"),
            ("UNIT PRICE",         "e"),
            ("AMOUNT",             "e"),
        ]):
            ctk.CTkLabel(
                th_row, text=col_txt, font=th_font,
                text_color=th_fg, anchor=anchor,
            ).grid(row=0, column=col_i,
                   padx=(10 if col_i == 0 else 6, 10 if col_i == 3 else 6),
                   pady=7, sticky="ew")

        # Table rows
        for idx, it in enumerate(items):
            row_bg = "transparent" if idx % 2 == 0 else BG_CARD_ALT
            r = ctk.CTkFrame(tbl_frame, fg_color=row_bg, corner_radius=4)
            r.grid(row=idx + 1, column=0, columnspan=4, sticky="ew", pady=1)
            r.columnconfigure(0, weight=1)
            r.columnconfigure(1, weight=0, minsize=60)
            r.columnconfigure(2, weight=0, minsize=90)
            r.columnconfigure(3, weight=0, minsize=100)

            unit_price = it["subtotal"] / it["qty"] if it["qty"] else 0

            ctk.CTkLabel(
                r, text=it["name"],
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=TEXT_PRIMARY, anchor="w",
            ).grid(row=0, column=0, padx=(10, 6), pady=7, sticky="w")
            ctk.CTkLabel(
                r, text=str(it["qty"]),
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=TEXT_SECONDARY, anchor="center",
            ).grid(row=0, column=1, padx=6, pady=7, sticky="ew")
            ctk.CTkLabel(
                r, text=f"₱{unit_price:,.2f}",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=TEXT_SECONDARY, anchor="e",
            ).grid(row=0, column=2, padx=6, pady=7, sticky="e")
            ctk.CTkLabel(
                r, text=f"₱{it['subtotal']:,.2f}",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=TEXT_PRIMARY, anchor="e",
            ).grid(row=0, column=3, padx=(6, 10), pady=7, sticky="e")

        sep(pady=12)

        # ── Totals table ──────────────────────────────────────────────
        totals_outer = ctk.CTkFrame(scroll, fg_color="transparent")
        totals_outer.pack(fill="x", padx=PAD, pady=(0, 4))
        totals_outer.columnconfigure(0, weight=1)
        totals_outer.columnconfigure(1, weight=0, minsize=160)

        def total_row(label, value, row, bold=False,
                      lbl_color=TEXT_MUTED, val_color=TEXT_PRIMARY, bg="transparent"):
            cell = ctk.CTkFrame(totals_outer, fg_color=bg, corner_radius=6)
            cell.grid(row=row, column=0, columnspan=2, sticky="ew", pady=1)
            cell.columnconfigure(0, weight=1)
            cell.columnconfigure(1, weight=0, minsize=160)
            ctk.CTkLabel(
                cell, text=label,
                font=ctk.CTkFont(family="Segoe UI", size=11,
                                 weight="bold" if bold else "normal"),
                text_color=lbl_color, anchor="w",
            ).grid(row=0, column=0, padx=10, pady=5, sticky="w")
            ctk.CTkLabel(
                cell, text=value,
                font=ctk.CTkFont(family="Segoe UI", size=11,
                                 weight="bold" if bold else "normal"),
                text_color=val_color, anchor="e",
            ).grid(row=0, column=1, padx=10, pady=5, sticky="e")

        r = 0
        total_row("Subtotal",  f"₱{subtotal:,.2f}", r); r += 1
        if discount > 0:
            total_row("Discount", f"− ₱{discount:,.2f}", r,
                      val_color=WARNING); r += 1
        total_row("VAT (12%)", f"₱{vat:,.2f}", r, val_color=INFO); r += 1

        # Grand total highlighted row
        total_row("TOTAL",     f"₱{total:,.2f}", r, bold=True,
                  lbl_color=TEXT_PRIMARY, val_color=hdr_color,
                  bg=BG_CARD_ALT); r += 1

        sep(pady=10)

        total_row("Amount Tendered", f"₱{tendered:,.2f}", r); r += 1
        if not is_gcash:
            total_row("Change", f"₱{change:,.2f}", r, bold=True,
                      val_color=SUCCESS); r += 1

        # ── Notes ─────────────────────────────────────────────────────
        if notes:
            sep(pady=10)
            note_bar = ctk.CTkFrame(scroll, fg_color=BG_CARD_ALT, corner_radius=6)
            note_bar.pack(fill="x", padx=PAD, pady=(0, 8))
            ctk.CTkLabel(
                note_bar,
                text=f"📝  {notes}",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color=TEXT_MUTED,
                wraplength=560, anchor="w", justify="left",
            ).pack(fill="x", padx=12, pady=8)

        # ── Footer thank-you ──────────────────────────────────────────
        sep(pady=10)
        ctk.CTkLabel(
            scroll,
            text="Thank you for your purchase!",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
        ).pack(pady=(0, 14))

        # ── Close button ──────────────────────────────────────────────
        ctk.CTkButton(
            self, text="✕   Close Receipt", height=44,
            fg_color=hdr_color,
            hover_color=GCASH_HOVER if is_gcash else ACCENT_HOVER,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            corner_radius=0, command=self.destroy,
        ).pack(fill="x")

        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self.destroy())


# ══════════════════════════════════════════════════════════════
#  MAIN SALES FRAME
# ══════════════════════════════════════════════════════════════

class SalesFrame(ctk.CTkFrame):
    """
    HCI-Optimised POS Sales Window.

    Product entry paths
    ───────────────────
    1. Inline search bar  — type in the top-left search bar; a floating
       dropdown appears with matching products.  Click or press Enter to
       add qty-1 of that product instantly.  Escape or clearing the field
       dismisses the dropdown.  ↑/↓ keys move the cursor through rows.

    2. Browse popup (F2)  — full two-column product browser with category
       pills, staging basket, and bulk-qty support.  Unchanged from the
       original design.

    Both paths call the same _on_product_selected() handler so cart
    merging, stock checks, and totals are always consistent.

    Shortcuts
    ─────────
    F2      Browse Product popup
    F6 / Ctrl+D  Discount popup
    F8      Payment popup
    Del     Remove selected cart row
    ↑/↓     Navigate inline search dropdown (when open)
    Enter   Confirm inline dropdown selection (when open)
    Escape  Dismiss inline dropdown (when open)
    """

    def __init__(self, master, user: dict):
        super().__init__(master, fg_color="transparent")
        self.user               = user
        self.cart               = []
        self._total_amount      = 0.0
        self._discount          = 0.0
        self._vat_amount        = 0.0
        self._pending_tender    = 0.0
        self._pending_method    = "cash"
        self._pending_ref       = ""
        self._search_popup_open = False
        self._txn_num           = generate_transaction_number("SL")
        self.all_products       = []

        # Inline dropdown instance (None when closed)
        self._dropdown: "_ProductDropdown | None" = None

        # ── Cash-drawer session gate ──────────────────────────────────────
        self._session = get_any_active_session()
        if not self._session:
            self._build_locked_ui()
        else:
            self._build_ui()
            self._load_products()
            self._bind_shortcuts()

    # ─────────────────────────────────────────────────────────
    #  UI BUILD
    # ─────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top status bar ───────────────────────────────────
        bar = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=10,
                           border_width=1, border_color=BORDER)
        bar.pack(fill="x", pady=(0, 10))

        left_bar = ctk.CTkFrame(bar, fg_color="transparent")
        left_bar.pack(side="left", padx=14, pady=8)
        ctk.CTkLabel(
            left_bar, text="Sales",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")
        self._txn_badge = ctk.CTkLabel(
            left_bar,
            text=f"  {self._txn_num}  ",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=ACCENT, fg_color=ACCENT_SUBTLE, corner_radius=6,
        )
        self._txn_badge.pack(side="left", padx=8)

        # Session indicator badge
        ctk.CTkLabel(
            left_bar,
            text=f"  🟢 {self._session['session_id']}  ",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=SUCCESS, fg_color=BG_CARD_ALT, corner_radius=6,
        ).pack(side="left", padx=(0, 4))

        # Keyboard shortcut reference pills
        right_bar = ctk.CTkFrame(bar, fg_color="transparent")
        right_bar.pack(side="right", padx=14, pady=8)

        ctk.CTkButton(
            right_bar, text="🔒  End Shift", height=30, width=115,
            fg_color=DANGER, hover_color=DANGER_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            corner_radius=8, command=self._end_shift,
        ).pack(side="left", padx=(0, 14))

        for key, label in [
            ("F2",  "Add Product"),
            ("F6",  "Discount"),
            ("F8",  "Pay"),
            ("Del", "Remove"),
        ]:
            pill = ctk.CTkFrame(right_bar, fg_color=BG_CARD_ALT,
                                corner_radius=6, border_width=1,
                                border_color=BORDER)
            pill.pack(side="left", padx=3)
            ctk.CTkLabel(
                pill, text=f" {key} ",
                font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
                text_color=ACCENT, fg_color="transparent",
            ).pack(side="left", padx=(4, 0), pady=4)
            ctk.CTkLabel(
                pill, text=f"{label} ",
                font=ctk.CTkFont(family="Segoe UI", size=9),
                text_color=TEXT_MUTED,
            ).pack(side="left", pady=4)

        # ── Main two-column body ─────────────────────────────
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True)
        main.grid_columnconfigure(0, weight=68)
        main.grid_columnconfigure(1, weight=32, minsize=280)
        main.grid_rowconfigure(0, weight=1)

        self._build_cart_panel(main)
        self._build_order_panel(main)

    # ── Shift management ────────────────────────────────────

    def _end_shift(self):
        CloseDrawerDialog(self, self._session, self.user, self._on_shift_ended)

    def _on_shift_ended(self):
        top = self.winfo_toplevel()
        if hasattr(top, "show_module"):
            top.show_module("cash_drawer")

    # ── Locked screen (no active cash session) ──────────────

    def _build_locked_ui(self):
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True)

        card = ctk.CTkFrame(outer, fg_color=BG_CARD, corner_radius=16,
                             border_width=2, border_color=DANGER)
        card.place(relx=0.5, rely=0.45, anchor="center")

        ctk.CTkFrame(card, fg_color=DANGER, height=4, corner_radius=0).pack(fill="x")

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(padx=60, pady=40)

        ctk.CTkLabel(inner, text="🔒",
                     font=ctk.CTkFont(size=52)).pack(pady=(0, 8))

        ctk.CTkLabel(
            inner, text="Cash Drawer is Closed",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=DANGER,
        ).pack()

        ctk.CTkLabel(
            inner,
            text="Sales cannot be processed until the cash drawer is open.\n"
                 "Open a shift first, then return here to begin selling.",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=TEXT_SECONDARY, justify="center",
        ).pack(pady=(10, 28))

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack()

        ctk.CTkButton(
            btn_row, text="💰  Open Cash Drawer", height=44, width=210,
            fg_color=SUCCESS, hover_color=SUCCESS_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            corner_radius=10, command=self._go_to_cash_drawer,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_row, text="🔄  Check Again", height=44, width=140,
            fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            corner_radius=10, command=self._recheck_session,
        ).pack(side="left")

    def _go_to_cash_drawer(self):
        top = self.winfo_toplevel()
        if hasattr(top, "show_module"):
            top.show_module("cash_drawer")

    def _recheck_session(self):
        session = get_any_active_session()
        if session:
            self._session = session
            for w in self.winfo_children():
                w.destroy()
            self._build_ui()
            self._load_products()
            self._bind_shortcuts()
        else:
            msg_warning(self, "Still Closed",
                        "No active session found.\n"
                        "Please open the cash drawer first.")

    # ── LEFT: Cart panel ─────────────────────────────────────

    def _build_cart_panel(self, parent):
        panel = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=12,
                             border_width=1, border_color=BORDER)
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        panel.grid_propagate(False)
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        # ── Cart toolbar ─────────────────────────────────────
        toolbar = ctk.CTkFrame(panel, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        toolbar.grid_columnconfigure(0, weight=1)

        # ── Inline search bar (dual-mode: product search + cart filter) ──
        self.search_var = ctk.StringVar()
        self._search_entry = ctk.CTkEntry(
            toolbar,
            textvariable=self.search_var,
            placeholder_text="🔍  Search products or filter cart…",
            height=34, fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=12), corner_radius=8,
        )
        self._search_entry.grid(row=0, column=0, sticky="ew")

        # Trace drives both the dropdown and the cart filter
        self.search_var.trace("w", self._on_search_change)

        # Keyboard navigation while focus is in the entry
        self._search_entry.bind("<Down>",
            lambda e: self._dd_move(+1))
        self._search_entry.bind("<Up>",
            lambda e: self._dd_move(-1))
        self._search_entry.bind("<Return>",
            lambda e: self._dd_confirm())
        self._search_entry.bind("<Escape>",
            lambda e: self._dd_close())
        # Dismiss after losing focus (delay lets click events fire first)
        self._search_entry.bind("<FocusOut>",
            lambda e: self.after(150, self._dd_close))

        # Browse product button — opens the full two-column popup
        ctk.CTkButton(
            toolbar, text=" Browse Product  ", width=170, height=34,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8,
            command=self._open_search_popup,
        ).grid(row=0, column=1, sticky="e", padx=(8, 0))

        # ── Cart header row ───────────────────────────────────
        ch = ctk.CTkFrame(panel, fg_color="transparent")
        ch.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        ctk.CTkLabel(
            ch, text="Cart",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")
        self._count_lbl = ctk.CTkLabel(
            ch, text="Empty",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
        )
        self._count_lbl.pack(side="left", padx=10)
        # Inline discount badge
        self._disc_badge = ctk.CTkLabel(
            ch, text="",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=WARNING, fg_color="transparent", corner_radius=6,
        )
        self._disc_badge.pack(side="left")
        ctk.CTkLabel(
            ch, text="Double-click row to edit qty",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=TEXT_MUTED,
        ).pack(side="right")

        # ── Cart table ────────────────────────────────────────
        tf = ctk.CTkFrame(panel, fg_color=BG_CARD_ALT, corner_radius=10)
        tf.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 8))

        cols = ("name", "qty", "price", "subtotal")
        self.cart_tree = ttk.Treeview(
            tf, columns=cols, show="headings", selectmode="browse")
        for col, lbl, w, anchor in [
            ("name",     "Product",    280, "w"),
            ("qty",      "Qty",         55, "center"),
            ("price",    "Unit Price", 100, "e"),
            ("subtotal", "Subtotal",   110, "e"),
        ]:
            self.cart_tree.heading(col, text=lbl)
            self.cart_tree.column(col, width=w, minwidth=40, anchor=anchor)
        style_treeview(self.cart_tree, row_height=36)

        vsb = ttk.Scrollbar(tf, orient="vertical",
                            command=self.cart_tree.yview)
        self.cart_tree.configure(yscrollcommand=vsb.set)
        self.cart_tree.pack(side="left", fill="both", expand=True,
                            padx=(4, 0), pady=4)
        vsb.pack(side="right", fill="y", pady=4, padx=(0, 4))

        self.cart_tree.bind("<Double-1>", self._open_qty_popup)
        self.cart_tree.bind("<Return>",   self._open_qty_popup)
        self.cart_tree.bind("<Delete>",   lambda e: self._remove_item())

        # ── Cart action buttons ───────────────────────────────
        br = ctk.CTkFrame(panel, fg_color="transparent")
        br.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 14))

        ctk.CTkButton(
            br, text="Remove Selected", height=32,
            fg_color=BG_CARD_ALT, hover_color=DANGER,
            text_color=TEXT_SECONDARY,
            border_width=1, border_color=BORDER,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=8, command=self._remove_item,
        ).pack(side="left")

        ctk.CTkButton(
            br, text="Clear Cart", height=32,
            fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
            text_color=TEXT_MUTED,
            border_width=1, border_color=BORDER,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=8, command=self._clear_cart,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            br, text="Discount  [F6]", height=32,
            fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
            text_color=WARNING, border_width=1, border_color=WARNING,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=8, command=self._open_discount_popup,
        ).pack(side="left")

    # ── RIGHT: Order summary + payment ───────────────────────

    def _build_order_panel(self, parent):
        panel = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=12,
                             border_width=1, border_color=BORDER)
        panel.grid(row=0, column=1, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(2, weight=1)

        # ── Section header ────────────────────────────────────
        sec = ctk.CTkFrame(panel, fg_color="transparent")
        sec.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 6))
        ctk.CTkLabel(
            sec, text="Order Summary",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")
        self._method_badge = ctk.CTkLabel(
            sec, text="",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=TEXT_MUTED, fg_color=BG_CARD_ALT, corner_radius=6,
        )
        self._method_badge.pack(side="right")

        # ── Totals card ───────────────────────────────────────
        tot = ctk.CTkFrame(panel, fg_color=BG_CARD_ALT, corner_radius=10)
        tot.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 6))

        self._sub_var  = ctk.StringVar(value="₱0.00")
        self._disc_var = ctk.StringVar(value="₱0.00")
        self._vat_var  = ctk.StringVar(value="₱0.00")
        self._tot_var  = ctk.StringVar(value="₱0.00")

        def srow(lbl, var, big=False, color=TEXT_SECONDARY):
            r = ctk.CTkFrame(tot, fg_color="transparent")
            r.pack(fill="x", padx=14, pady=3)
            ctk.CTkLabel(
                r, text=lbl,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=TEXT_MUTED,
            ).pack(side="left")
            ctk.CTkLabel(
                r, textvariable=var,
                font=ctk.CTkFont(
                    family="Segoe UI",
                    size=16 if big else 12,
                    weight="bold" if big else "normal"),
                text_color=color,
            ).pack(side="right")

        ctk.CTkFrame(tot, fg_color="transparent", height=4).pack()
        srow("Subtotal",   self._sub_var)
        srow("Discount",   self._disc_var, color=WARNING)
        srow("VAT (12%)",  self._vat_var,  color=INFO)
        ctk.CTkFrame(tot, fg_color=BORDER, height=1).pack(
            fill="x", padx=10, pady=3)
        srow("TOTAL DUE",  self._tot_var,  big=True, color=ACCENT)
        ctk.CTkFrame(tot, fg_color="transparent", height=4).pack()

        # ── Tendered / Change ─────────────────────────────────
        ti = ctk.CTkFrame(panel, fg_color="transparent")
        ti.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 4))

        self._tend_var   = ctk.StringVar(value="—")
        self._change_var = ctk.StringVar(value="—")
        self._ref_lbl    = None

        for lbl, var, color in [
            ("Tendered", self._tend_var,   TEXT_PRIMARY),
            ("Change",   self._change_var, SUCCESS),
        ]:
            r = ctk.CTkFrame(ti, fg_color="transparent")
            r.pack(fill="x", pady=2)
            ctk.CTkLabel(
                r, text=lbl,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=TEXT_MUTED,
            ).pack(side="left")
            ctk.CTkLabel(
                r, textvariable=var,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color=color,
            ).pack(side="right")

        self._ref_lbl = ctk.CTkLabel(
            panel, text="",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=GCASH_BLUE,
        )
        self._ref_lbl.grid(row=3, column=0, sticky="w",
                           padx=14, pady=(0, 4))

        # ── Notes field ───────────────────────────────────────
        notes_frame = ctk.CTkFrame(panel, fg_color="transparent")
        notes_frame.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 8))
        ctk.CTkLabel(
            notes_frame, text="Note (optional)",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=TEXT_MUTED, anchor="w",
        ).pack(fill="x")
        self._notes = ctk.CTkEntry(
            notes_frame, height=32,
            placeholder_text="Add a note…",
            fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=11), corner_radius=8,
        )
        self._notes.pack(fill="x")

        # ── PAY button ────────────────────────────────────────
        self._pay_btn = ctk.CTkButton(
            panel,
            text="PAY",
            height=50,
            fg_color=SUCCESS, hover_color=SUCCESS_HOVER, text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            corner_radius=10, command=self._open_payment_popup,
        )
        self._pay_btn.grid(row=5, column=0, sticky="ew",
                           padx=14, pady=(0, 6))

        # ── Complete Sale button ──────────────────────────────
        self._complete_btn = ctk.CTkButton(
            panel,
            text="Complete Sale",
            height=46,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            corner_radius=10, command=self._complete_sale,
        )
        self._complete_btn.grid(row=6, column=0, sticky="ew",
                                padx=14, pady=(0, 14))

        self._set_action_state("disabled")

    # ─────────────────────────────────────────────────────────
    #  SHORTCUTS
    # ─────────────────────────────────────────────────────────

    def _bind_shortcuts(self):
        top = self.winfo_toplevel()
        top.bind("<F2>",        lambda e: self._open_search_popup())
        top.bind("<F6>",        lambda e: self._open_discount_popup())
        top.bind("<Control-d>", lambda e: self._open_discount_popup())
        top.bind("<F8>",        lambda e: self._open_payment_popup())

    # ─────────────────────────────────────────────────────────
    #  DATA
    # ─────────────────────────────────────────────────────────

    def _load_products(self):
        conn = get_connection()
        rows = conn.execute(
            """SELECT id, code, name, category, selling_price,
                      current_stock, low_stock_threshold
               FROM products ORDER BY name"""
        ).fetchall()
        conn.close()
        self.all_products = [dict(r) for r in rows]

    # ─────────────────────────────────────────────────────────
    #  INLINE SEARCH DROPDOWN  (new)
    # ─────────────────────────────────────────────────────────

    def _on_search_change(self, *_):
        """
        Dual-mode handler for the search bar.

        Non-empty text  →  Show product dropdown (add-mode).
                           Matching products are shown in a floating list.
                           Selecting one calls _on_product_selected(qty=1).
                           The cart table is also filtered so it stays
                           consistent with what the user typed.

        Empty text      →  Dismiss dropdown and show full cart.
        """
        q = self.search_var.get().strip()

        if q:
            matches = [
                p for p in self.all_products
                if q.lower() in p["name"].lower()
                or q.lower() in (p.get("code") or "").lower()
            ]
            if matches:
                self._dd_open(matches)
            else:
                self._dd_close()
            # Also filter the cart rows so it doesn't feel stale
            self._filter_cart()
        else:
            self._dd_close()
            self._filter_cart()   # restore full cart view

    def _dd_open(self, products: list):
        """Create (or recreate) the floating product dropdown."""
        # Destroy any existing instance before creating a new one
        # so we don't accumulate stale windows on fast keystrokes
        if self._dropdown and self._dropdown.winfo_exists():
            self._dropdown.destroy()
        self._dropdown = _ProductDropdown(
            self.winfo_toplevel(),
            self._search_entry,
            products,
            self._on_search_product_selected,
        )

    def _dd_close(self):
        """Dismiss the dropdown if it exists."""
        if self._dropdown and self._dropdown.winfo_exists():
            self._dropdown.destroy()
        self._dropdown = None

    def _dd_move(self, direction: int):
        """Pass ↑/↓ key navigation to the dropdown."""
        if self._dropdown and self._dropdown.winfo_exists():
            self._dropdown.move_cursor(direction)

    def _dd_confirm(self):
        """Press Enter while the entry is focused — confirm dropdown row."""
        if self._dropdown and self._dropdown.winfo_exists():
            self._dropdown.pick_selected()

    def _on_search_product_selected(self, product: dict):
        """
        Called when the user picks a product from the inline dropdown.
        Adds qty-1 to the cart (matching one quick tap on a barcode gun),
        clears the search field, and returns focus to the entry so the
        cashier can immediately search for the next product.
        """
        if product["current_stock"] <= 0:
            msg_warning(
                self, "Out of Stock",
                f"'{product['name']}' has no stock available.",
            )
            self._dd_close()
            return

        self._on_product_selected(product, qty=1)   # reuse existing merge logic
        self.search_var.set("")                      # clear → triggers _dd_close
        self._search_entry.focus()

    # ─────────────────────────────────────────────────────────
    #  POPUP OPENERS
    # ─────────────────────────────────────────────────────────

    def _filter_cart(self, *_):
        """Re-render the cart table, optionally filtered by search_var."""
        q = self.search_var.get().lower().strip()
        for r in self.cart_tree.get_children():
            self.cart_tree.delete(r)
        items = self.cart if not q else [
            c for c in self.cart if q in c["name"].lower()
        ]
        for i, c in enumerate(items):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.cart_tree.insert(
                "", "end",
                values=(
                    c["name"], c["qty"],
                    f"₱{c['price']:,.2f}",
                    f"₱{c['subtotal']:,.2f}",
                ),
                tags=(tag,),
            )

    def _open_search_popup(self):
        if self._search_popup_open:
            return
        self._search_popup_open = True
        ProductSearchPopup(
            self.winfo_toplevel(),
            self.all_products,
            self._on_product_selected,
            lambda: setattr(self, "_search_popup_open", False),
        )

    def _open_discount_popup(self):
        sub = sum(c["subtotal"] for c in self.cart)
        if sub == 0:
            msg_warning(self, "Empty Cart",
                        "Add items to the cart before applying a discount.")
            return
        DiscountPopup(
            self.winfo_toplevel(), sub, self._discount,
            self._on_discount_saved,
        )

    def _open_payment_popup(self):
        if not self.cart:
            msg_warning(self, "Empty Cart",
                        "Please add products to the cart first.")
            return
        PaymentPopup(
            self.winfo_toplevel(),
            self._total_amount,
            self._on_payment_confirmed,
        )

    # ─────────────────────────────────────────────────────────
    #  CALLBACKS
    # ─────────────────────────────────────────────────────────

    def _on_product_selected(self, product: dict, qty: int = 1):
        """
        Merge a product into the cart.  If the product is already present
        its quantity is incremented; otherwise a new row is appended.
        """
        pid = product["id"]
        for item in self.cart:
            if item["product_id"] == pid:
                item["qty"]     += qty
                item["subtotal"] = item["qty"] * item["price"]
                self._refresh_cart()
                return
        self.cart.append({
            "product_id": pid,
            "name":       product["name"],
            "qty":        qty,
            "price":      product["selling_price"],
            "subtotal":   product["selling_price"] * qty,
            "stock":      product["current_stock"],
        })
        self._refresh_cart()

    def _on_discount_saved(self, disc: float):
        self._discount = disc
        self._disc_var.set(f"₱{disc:,.2f}")
        if disc > 0:
            self._disc_badge.configure(
                text=f"  Discount ₱{disc:,.2f}  ",
                fg_color="#FFF3CC", text_color=WARNING,
            )
        else:
            self._disc_badge.configure(text="", fg_color="transparent")
        self._update_totals()

    def _on_payment_confirmed(self, method: str, amount: float, ref: str):
        self._pending_method = method
        self._pending_tender = amount
        self._pending_ref    = ref
        change = amount - self._total_amount

        if method == "gcash":
            badge_txt = "  GCash  "
            badge_fg  = GCASH_BLUE
            badge_tc  = "#FFFFFF"
            self._change_var.set("—")
            self._ref_lbl.configure(
                text=f"Ref #: {ref}" if ref else "Ref #: not recorded")
        else:
            badge_txt = "  Cash  "
            badge_fg  = SUCCESS
            badge_tc  = "#FFFFFF"
            self._change_var.set(f"₱{change:,.2f}")
            self._ref_lbl.configure(text="")

        self._method_badge.configure(
            text=badge_txt, fg_color=badge_fg, text_color=badge_tc)
        self._tend_var.set(f"₱{amount:,.2f}")

        if method == "gcash":
            self._pay_btn.configure(
                text="Re-enter GCash",
                fg_color=GCASH_BLUE, hover_color=GCASH_HOVER,
            )
        else:
            self._pay_btn.configure(
                text="Re-enter Cash",
                fg_color=SUCCESS, hover_color=SUCCESS_HOVER,
            )

    # ─────────────────────────────────────────────────────────
    #  CART OPERATIONS
    # ─────────────────────────────────────────────────────────

    def _open_qty_popup(self, event=None):
        sel = self.cart_tree.selection()
        if not sel:
            return
        idx  = self.cart_tree.index(sel[0])
        item = self.cart[idx]

        def _save(new_qty):
            self.cart[idx]["qty"]      = new_qty
            self.cart[idx]["subtotal"] = new_qty * self.cart[idx]["price"]
            self._refresh_cart()

        QtyEditPopup(self.winfo_toplevel(), item, _save)

    def _refresh_cart(self):
        for r in self.cart_tree.get_children():
            self.cart_tree.delete(r)
        for i, c in enumerate(self.cart):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.cart_tree.insert(
                "", "end",
                values=(
                    c["name"], c["qty"],
                    f"₱{c['price']:,.2f}",
                    f"₱{c['subtotal']:,.2f}",
                ),
                tags=(tag,),
            )
        units = sum(c["qty"] for c in self.cart)
        n     = len(self.cart)
        self._count_lbl.configure(
            text=f"{n} item(s) · {units} unit(s)" if n else "Empty")
        self._set_action_state("normal" if n else "disabled")
        self._update_totals()

    def _remove_item(self):
        sel = self.cart_tree.selection()
        if not sel:
            return
        self.cart.pop(self.cart_tree.index(sel[0]))
        self._refresh_cart()

    def _clear_cart(self):
        if self.cart and not msg_question(
                self, "Clear Cart",
                "Remove all items from the cart?"):
            return
        self._reset_session()

    def _update_totals(self):
        # Dismiss the dropdown whenever cart totals change — the product
        # list may now be stale relative to updated stock levels
        self._dd_close()

        sub     = sum(c["subtotal"] for c in self.cart)
        taxable = max(sub - self._discount, 0)
        vat     = round(taxable * VAT_RATE, 2)
        total   = round(taxable + vat, 2)
        self._sub_var.set(f"₱{sub:,.2f}")
        self._vat_var.set(f"₱{vat:,.2f}")
        self._tot_var.set(f"₱{total:,.2f}")
        self._total_amount = total
        self._vat_amount   = vat
        # Reset payment state when cart changes
        self._pending_tender = 0.0
        self._pending_method = "cash"
        self._pending_ref    = ""
        self._tend_var.set("—")
        self._change_var.set("—")
        if self._ref_lbl:
            self._ref_lbl.configure(text="")
        self._method_badge.configure(
            text="", fg_color=BG_CARD_ALT, text_color=TEXT_MUTED)
        self._pay_btn.configure(
            text="PAY",
            fg_color=SUCCESS, hover_color=SUCCESS_HOVER,
        )

    def _set_action_state(self, state: str):
        """Enable or disable primary action buttons based on cart state."""
        self._pay_btn.configure(state=state)
        self._complete_btn.configure(state=state)

    # ─────────────────────────────────────────────────────────
    #  COMPLETE SALE
    # ─────────────────────────────────────────────────────────

    def _complete_sale(self):
        if not self.cart:
            msg_warning(self, "Empty Cart",
                        "Please add products to the cart first.")
            return
        if self._pending_tender < self._total_amount:
            msg_warning(
                self, "Payment Required",
                f"Press PAY first.\nTotal due: ₱{self._total_amount:,.2f}",
            )
            return

        for item in self.cart:
            if item["qty"] > item["stock"]:
                msg_error(
                    self, "Insufficient Stock",
                    f"Not enough stock for '{item['name']}'.\n"
                    f"Available: {item['stock']}, Requested: {item['qty']}",
                )
                return

        # ── Cash-drawer session guard ─────────────────────────────
        active_session = get_any_active_session()
        if not active_session:
            msg_warning(
                self, "Cash Drawer Closed",
                "The cash drawer is not open.\n\n"
                "Please open a shift from the Cash Drawer module\n"
                "before processing a sale.",
            )
            return

        conn = get_connection()
        try:
            sub    = sum(c["subtotal"] for c in self.cart)
            vat    = self._vat_amount
            total  = self._total_amount
            tender = self._pending_tender
            change = tender - total
            method = self._pending_method
            ref    = self._pending_ref
            notes  = self._notes.get()

            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO sales_transactions
                    (transaction_number, cashier_id, subtotal, discount,
                     vat, total, amount_tendered, change_given,
                     payment_method, notes, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._txn_num, self.user["id"],
                    sub, self._discount, vat, total,
                    tender, change if method == "cash" else 0,
                    method, notes, active_session["id"],
                ),
            )
            txn_id = cur.lastrowid

            for item in self.cart:
                cur.execute(
                    """
                    INSERT INTO sale_items
                        (transaction_id, product_id, quantity,
                         unit_price, subtotal)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (txn_id, item["product_id"], item["qty"],
                     item["price"], item["subtotal"]),
                )
                cur.execute(
                    """
                    UPDATE products
                    SET current_stock = current_stock - ?,
                        updated_at = datetime('now','localtime')
                    WHERE id = ?
                    """,
                    (item["qty"], item["product_id"]),
                )
                cur.execute(
                    """
                    INSERT INTO stock_adjustments
                        (product_id, user_id, change_amount, reason, reference)
                    VALUES (?, ?, ?, 'Sale', ?)
                    """,
                    (item["product_id"], self.user["id"],
                     -item["qty"], self._txn_num),
                )

            conn.commit()

            log_audit(self.user["id"], self.user["username"], "Sales", "SALE_CREATED",
                      record_id=txn_id,
                      new_value={"txn": self._txn_num, "total": total, "method": method})

            cart_snap = [dict(c) for c in self.cart]
            ReceiptPopup(
                self.winfo_toplevel(),
                txn_num        = self._txn_num,
                cashier_name   = self.user.get(
                    "full_name", self.user.get("username", "—")),
                items          = cart_snap,
                subtotal       = sub,
                discount       = self._discount,
                vat            = vat,
                total          = total,
                tendered       = tender,
                change         = change,
                payment_method = method,
                gcash_ref      = ref,
                notes          = notes,
            )
            self._reset_session()

        except Exception as exc:
            conn.rollback()
            msg_error(self, "Database Error",
                      f"Failed to save transaction.\n{exc}")
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────
    #  SESSION RESET
    # ─────────────────────────────────────────────────────────

    def _reset_session(self):
        # Close any open dropdown before wiping state
        self._dd_close()

        self.cart             = []
        self._discount        = 0.0
        self._total_amount    = 0.0
        self._vat_amount      = 0.0
        self._pending_tender  = 0.0
        self._pending_method  = "cash"
        self._pending_ref     = ""
        self._txn_num         = generate_transaction_number("SL")
        self._txn_badge.configure(text=f"  {self._txn_num}  ")
        self._disc_badge.configure(text="", fg_color="transparent")
        self._disc_var.set("₱0.00")
        self._notes.delete(0, "end")
        self._refresh_cart()
        self._load_products()