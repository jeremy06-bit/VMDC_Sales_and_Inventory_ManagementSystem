import customtkinter as ctk
from tkinter import ttk
from database import get_connection
from security import log_audit
from utils.helpers import generate_transaction_number
from ui.cashdrawer_window import get_any_active_session, CloseDrawerDialog
from ui.theme import (
    BG_DARK, BG_CARD, BG_CARD_ALT, BG_INPUT, BG_HOVER, BORDER,
    ACCENT, ACCENT_HOVER, ACCENT_LIGHT, ACCENT_SUBTLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    SUCCESS, SUCCESS_HOVER, DANGER, DANGER_HOVER,
    style_treeview, insert_with_stripes, Paginator,
    create_dialog_entry, create_dialog_button, style_dialog, create_option_menu,

    msg_info, msg_warning, msg_error, msg_success, msg_question
)
from ui.sales_window import _ProductDropdown, ProductSearchPopup

SERVICE_TYPES = [
    "Product Installation",
    "Oil Change Service",
    "Brake Adjustment",
    "Tire Replacement",
    "Basic Motorcycle Check-up",
    "Customer Assistance",
]

SERVICE_PRICE_HINTS = {
    "Product Installation":     "₱50 – ₱300 (side mirrors, bulbs, batteries, horns)",
    "Oil Change Service":       "₱50 – ₱300 (engine oil & gear oil)",
    "Brake Adjustment":         "₱100 – ₱300 (brake tuning & adjustment)",
    "Tire Replacement":         "₱100 – ₱300 (tire & interior replacement)",
    "Basic Motorcycle Check-up":"Free / quoted per job (brakes, lights, battery, engine oil)",
    "Customer Assistance":      "Free (help finding correct parts)",
}

def _get_mechanic_names():
    """Fetch active mechanic display names from the database."""
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT display_name FROM mechanics WHERE active=1 ORDER BY id"
        ).fetchall()
        conn.close()
        return [r["display_name"] for r in rows] or ["No mechanics — add via Manage Mechanics"]
    except Exception:
        return ["No mechanics — add via Manage Mechanics"]


def _get_mechanics():
    """Fetch active mechanics as list of dicts {id, name}."""
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, display_name FROM mechanics WHERE active=1 ORDER BY id"
        ).fetchall()
        conn.close()
        return [{"id": r["id"], "name": r["display_name"]} for r in rows]
    except Exception:
        return []


class ServicesFrame(ctk.CTkFrame):
    def __init__(self, master, user: dict):
        super().__init__(master, fg_color="transparent")
        self.user = user

        # ── Cash-drawer session gate ──────────────────────────────────────
        self._session = get_any_active_session()
        if not self._session:
            self._build_locked_ui()
        else:
            self._build_ui()
            self._load()

    def _build_ui(self):
        # ── Header ──────────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(
            header, text="Service Transactions",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=TEXT_PRIMARY
        ).pack(side="left")
        ctk.CTkButton(
            header, text="+  New Service", height=38,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            corner_radius=10, command=self._new_service
        ).pack(side="right")

        # Session indicator badge
        ctk.CTkLabel(
            header,
            text=f"  🟢 {self._session['session_id']}  ",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=SUCCESS, fg_color=BG_CARD_ALT, corner_radius=6,
        ).pack(side="right", padx=(0, 10))

        ctk.CTkButton(
            header, text="🔒  End Shift", height=38, width=130,
            fg_color=DANGER, hover_color=DANGER_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            corner_radius=10, command=self._end_shift,
        ).pack(side="right", padx=(0, 10))

        if self.user.get("role") == "owner":
            ctk.CTkButton(
                header, text="👷  Manage Mechanics", height=38,
                fg_color=BG_INPUT, hover_color=BG_HOVER,
                border_width=1, border_color=BORDER,
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=TEXT_PRIMARY,
                corner_radius=10, command=self._manage_mechanics
            ).pack(side="right", padx=(0, 10))

        # ── Filter bar ──────────────────────────────────────────────────────
        filter_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=12,
                                    border_width=1, border_color=BORDER)
        filter_frame.pack(fill="x", pady=(0, 10))
        filter_inner = ctk.CTkFrame(filter_frame, fg_color="transparent")
        filter_inner.pack(fill="x", padx=12, pady=10)
        ctk.CTkLabel(
            filter_inner, text="Filter by service:",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_SECONDARY
        ).pack(side="left", padx=(0, 10))
        self.service_filter_var = ctk.StringVar(value="All Services")
        create_option_menu(
            filter_inner, values=["All Services"] + SERVICE_TYPES,
            variable=self.service_filter_var, width=240,
            command=lambda *a: self._load()
        ).pack(side="left")

        ctk.CTkLabel(
            filter_inner,
            text="💡 Click a row to view details and manage its status",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED
        ).pack(side="left", padx=(20, 0))

        # ── Table ────────────────────────────────────────────────────────────
        table_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14,
                                   border_width=1, border_color=BORDER)
        table_frame.pack(fill="both", expand=True)

        cols = ("date", "txn_num", "service", "labor", "parts", "total", "status")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=18)
        headers = {
            "date":    "Date",
            "txn_num": "Txn #",
            "service": "Service Type",
            "labor":   "Labor",
            "parts":   "Parts Cost",
            "total":   "Total",
            "status":  "Status",
        }
        widths = {
            "date":    140,
            "txn_num": 120,
            "service": 180,
            "labor":   90,
            "parts":   90,
            "total":   100,
            "status":  100,
        }
        for col in cols:
            self.tree.heading(col, text=headers[col])
            self.tree.column(
                col, width=widths[col],
                anchor="center" if col == "status" else
                "e" if col in ("labor", "parts", "total") else "w"
            )

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        style_treeview(self.tree)
        self.tree.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        scrollbar.pack(side="right", fill="y", pady=6)
        self._pager = Paginator(table_frame, self.tree, page_size=20,
                                render_fn=self._render_page, bar_parent=self)

        self.tree.bind("<<TreeviewSelect>>", self._on_row_select)

        self._selected_svc_id = None
        self._summary_popup   = None   # holds the open ServiceSummaryPopup, if any
        self._ignore_select   = False  # guard: suppresses <<TreeviewSelect>> during reload

    # ── Load ─────────────────────────────────────────────────────────────────
    def _load(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Close any open summary popup when reloading
        if getattr(self, "_summary_popup", None):
            try:
                self._summary_popup.destroy()
            except Exception:
                pass
            self._summary_popup = None
        self._selected_svc_id = None

        svc_filter = self.service_filter_var.get()
        conn = get_connection()
        if svc_filter == "All Services":
            rows = conn.execute("""
                SELECT sv.*
                FROM service_transactions sv
                ORDER BY sv.created_at DESC LIMIT 200
            """).fetchall()
        else:
            rows = conn.execute("""
                SELECT sv.*
                FROM service_transactions sv
                WHERE sv.service_type=?
                ORDER BY sv.created_at DESC LIMIT 200
            """, (svc_filter,)).fetchall()

        ids = [r["id"] for r in rows]
        self._parts_map     = {}
        self._mechanics_map = {}
        self._rows_map      = {}  # {id: row_dict} for summary panel
        if ids:
            placeholders = ",".join("?" * len(ids))
            parts_rows = conn.execute(f"""
                SELECT sp.service_id, p.code, p.name, sp.quantity, sp.unit_price, sp.subtotal
                FROM service_parts sp
                JOIN products p ON p.id = sp.product_id
                WHERE sp.service_id IN ({placeholders})
                ORDER BY sp.id
            """, ids).fetchall()
            for pr in parts_rows:
                self._parts_map.setdefault(pr["service_id"], []).append(
                    (pr["code"], pr["name"], pr["quantity"], pr["unit_price"], pr["subtotal"])
                )
            mech_rows = conn.execute(f"""
                SELECT service_id, mechanic_name
                FROM service_mechanics
                WHERE service_id IN ({placeholders})
                ORDER BY id
            """, ids).fetchall()
            mech_by_svc = {}
            for mr in mech_rows:
                mech_by_svc.setdefault(mr["service_id"], []).append(mr["mechanic_name"])
            for sid, names in mech_by_svc.items():
                self._mechanics_map[sid] = ", ".join(names)
        conn.close()

        for row in rows:
            row_dict = dict(row)
            sid = row_dict["id"]
            self._rows_map[sid] = row_dict
            status = row_dict.get("status", "completed")

            if status == "pending":
                tag = "pending_row"
            elif status == "in_progress":
                tag = "inprog_row"
            else:
                tag = "evenrow"

            self.tree.insert("", "end", iid=str(sid), tags=(tag,), values=(
                row_dict["created_at"][:16],
                row_dict["transaction_number"],
                row_dict["service_type"],
                f"₱{row_dict['labor_fee']:,.2f}",
                f"₱{row_dict['parts_total']:,.2f}",
                f"₱{row_dict['total']:,.2f}",
                status.replace("_", " ").title(),
            ))

        self._pager.set_data(list(rows))

    def _render_page(self, rows):
        for row in rows:
            row_dict = dict(row)
            sid    = row_dict["id"]
            status = row_dict.get("status", "completed")
            self._rows_map[sid] = row_dict

            if status == "pending":
                tag = "pending_row"
            elif status == "in_progress":
                tag = "inprog_row"
            else:
                tag = "evenrow"

            self.tree.insert("", "end", iid=str(sid), tags=(tag,), values=(
                row_dict["created_at"][:16],
                row_dict["transaction_number"],
                row_dict["service_type"],
                f"₱{row_dict['labor_fee']:,.2f}",
                f"₱{row_dict['parts_total']:,.2f}",
                f"₱{row_dict['total']:,.2f}",
                status.replace("_", " ").title(),
            ))
        self.tree.tag_configure("pending_row",  background="#B88B2E", foreground="#FFFFFF")
        self.tree.tag_configure("inprog_row",   background="#4A6D8C", foreground="#FFFFFF")

    # ── Row select: open summary popup ──────────────────────────────────────
    def _on_row_select(self, event=None):
        if getattr(self, "_ignore_select", False):
            return
        sel = self.tree.selection()
        if not sel:
            self._selected_svc_id = None
            return
        svc_id = int(sel[0])
        self._selected_svc_id = svc_id
        row = getattr(self, "_rows_map", {}).get(svc_id)
        if not row:
            return
        if getattr(self, "_summary_popup", None):
            try:
                self._summary_popup.destroy()
            except Exception:
                pass
            self._summary_popup = None
        self._summary_popup = ServiceSummaryPopup(
            master     = self,
            row        = row,
            parts_list = getattr(self, "_parts_map", {}).get(svc_id, []),
            mechanic   = (
                getattr(self, "_mechanics_map", {}).get(svc_id)
                or row.get("mechanic_name") or "Unknown Mechanic"
            ),
            advance_cb = self._advance_status,
        )

    # ── Advance status: Pending → In Progress → Completed ───────────────────
    def _advance_status(self):
        svc_id = self._selected_svc_id
        if not svc_id:
            return

        conn = get_connection()
        row  = conn.execute(
            "SELECT * FROM service_transactions WHERE id=?", (svc_id,)
        ).fetchone()
        if not row:
            conn.close()
            return

        current = row["status"]
        if current == "completed":
            conn.close()
            return

        next_status = "in_progress" if current == "pending" else "completed"
        row_dict    = dict(row)
        linked_sale = row_dict.get("linked_sale_txn")
        parts_total = row_dict.get("parts_total") or 0

        # On completing: auto-create linked sales transaction if parts exist
        if next_status == "completed" and parts_total > 0 and not linked_sale:
            try:
                sale_txn_num = generate_transaction_number("SL")
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO sales_transactions
                    (transaction_number, cashier_id, subtotal, discount, total,
                     amount_tendered, change_given, payment_method, notes)
                    VALUES (?,?,?,0,?,?,0,'cash',?)
                """, (
                    sale_txn_num, self.user["id"],
                    parts_total, parts_total, parts_total,
                    f"Parts used in service {row_dict['transaction_number']}",
                ))
                sale_id = cur.lastrowid
                parts = cur.execute(
                    "SELECT * FROM service_parts WHERE service_id=?", (svc_id,)
                ).fetchall()
                for part in parts:
                    cur.execute("""
                        INSERT INTO sale_items
                        (transaction_id, product_id, quantity, unit_price, subtotal)
                        VALUES (?,?,?,?,?)
                    """, (sale_id, part["product_id"], part["quantity"],
                          part["unit_price"], part["subtotal"]))
                    cur.execute("""
                        UPDATE products
                        SET current_stock = current_stock - ?,
                            updated_at = datetime('now','localtime')
                        WHERE id=?
                    """, (part["quantity"], part["product_id"]))
                    cur.execute("""
                        INSERT INTO stock_adjustments
                        (product_id, user_id, change_amount, reason, reference)
                        VALUES (?,?,?,'Service Parts Used',?)
                    """, (part["product_id"], self.user["id"],
                          -part["quantity"], row_dict["transaction_number"]))
                linked_sale = sale_txn_num
                conn.commit()
            except Exception as e:
                conn.rollback()
                conn.close()
                msg_error(self, "Error", f"Failed to create linked sales transaction:\n{e}")
                return

        conn.execute("""
            UPDATE service_transactions SET status=?, linked_sale_txn=? WHERE id=?
        """, (next_status, linked_sale, svc_id))
        conn.commit()
        conn.close()

        # Close the popup first — before any dialog appears — so nothing refreshes behind it.
        if getattr(self, "_summary_popup", None):
            try:
                self._summary_popup.destroy()
            except Exception:
                pass
            self._summary_popup = None

        if next_status == "completed" and linked_sale and parts_total > 0:
            msg_info(self, "Completed",
                     f"Service marked as Completed.\n\n"
                     f"Parts recorded as Sales Transaction:\n{linked_sale}")

        # Reload the table so the new status is visible.
        # Guard against <<TreeviewSelect>> reopening the popup during reload.
        self._ignore_select = True
        try:
            self._load()
        finally:
            self._ignore_select = False

    def _clear_tree_selection(self):
        """Deselect all rows without triggering _on_row_select."""
        self._ignore_select = True
        try:
            self.tree.selection_remove(*self.tree.selection())
        finally:
            self._ignore_select = False

    def _manage_mechanics(self):
        ManageMechanicsDialog(self, self.user, self._load)

    def _end_shift(self):
        CloseDrawerDialog(self, self._session, self.user, self._on_shift_ended)

    def _on_shift_ended(self):
        top = self.winfo_toplevel()
        if hasattr(top, "show_module"):
            top.show_module("cash_drawer")

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
            text="Service transactions cannot be recorded until the cash drawer is open.\n"
                 "Open a shift first, then return here to begin.",
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
            self._load()
        else:
            msg_warning(self, "Still Closed",
                        "No active session found.\n"
                        "Please open the cash drawer first.")

    def _new_service(self):
        ServiceDialog(self, self.user, self._load)


# ── Service Summary Popup ─────────────────────────────────────────────────────
class ServiceSummaryPopup(ctk.CTkToplevel):
    """
    Non-blocking popup that shows a full summary of a service transaction.
    Opens when the user clicks any row in the services table.

    Displays:
      - Transaction metadata (Txn #, date, service type, mechanic, status, notes)
      - Cost breakdown (labor, parts, VAT, total)
      - Parts list with quantity / unit price / subtotal
      - Action button to advance status (Pending → In Progress → Completed)
    """

    _W = 640
    _H = 680

    STATUS_COLORS = {
        "pending":     "#B88B2E",
        "in_progress": "#4A6D8C",
        "completed":   SUCCESS,
    }

    def __init__(self, master, row: dict, parts_list: list,
                 mechanic: str, advance_cb, on_close_cb=None):
        super().__init__(master)
        self._row        = row
        self._parts_list = parts_list
        self._mechanic   = mechanic
        self._advance_cb = advance_cb
        self._on_close   = on_close_cb

        self.title("Service Summary")
        self.configure(fg_color=BG_DARK)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_destroy)

        self._build()
        self.after(80, self._finalize)

    def _finalize(self):
        w, h = self._W, self._H
        try:
            mx = self.master.winfo_rootx()
            my = self.master.winfo_rooty()
            mw = self.master.winfo_width()
            mh = self.master.winfo_height()
            x  = mx + (mw - w) // 2
            y  = my + (mh - h) // 2
        except Exception:
            x = (self.winfo_screenwidth()  - w) // 2
            y = (self.winfo_screenheight() - h) // 2
        x = max(0, min(x, self.winfo_screenwidth()  - w))
        y = max(0, min(y, self.winfo_screenheight() - h))
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.lift()
        self.focus_force()

    def _on_destroy(self):
        if callable(self._on_close):
            self._on_close()
        self.destroy()

    def _build(self):
        row        = self._row
        status     = row.get("status", "completed")
        labor      = row.get("labor_fee", 0) or 0
        parts_cost = row.get("parts_total", 0) or 0
        vat        = round(parts_cost * 0.12, 2)
        total      = row.get("total", 0) or 0
        linked     = row.get("linked_sale_txn") or ""

        # ── Header bar ───────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=ACCENT_SUBTLE,
                           corner_radius=0, border_width=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(
            hdr, text="🔧  Service Summary",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=ACCENT
        ).pack(side="left", padx=20, pady=14)

        status_color = self.STATUS_COLORS.get(status, TEXT_PRIMARY)
        ctk.CTkLabel(
            hdr, text=status.replace("_", " ").title(),
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=status_color
        ).pack(side="right", padx=20)

        # ── Scrollable content area ──────────────────────────────────────────
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                        scrollbar_button_color=BG_HOVER,
                                        scrollbar_button_hover_color=BORDER)
        scroll.pack(fill="both", expand=True, padx=14, pady=(10, 4))

        # ── Info card ────────────────────────────────────────────────────────
        info_card = ctk.CTkFrame(scroll, fg_color=BG_CARD, corner_radius=12,
                                 border_width=1, border_color=BORDER)
        info_card.pack(fill="x", pady=(0, 10))

        def _info_row(parent, label, value, value_color=TEXT_PRIMARY):
            r = ctk.CTkFrame(parent, fg_color="transparent")
            r.pack(fill="x", padx=14, pady=(6, 0))
            ctk.CTkLabel(
                r, text=label,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=TEXT_MUTED, width=88, anchor="w"
            ).pack(side="left")
            ctk.CTkLabel(
                r, text=value,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color=value_color, anchor="w",
                wraplength=440, justify="left"
            ).pack(side="left", fill="x", expand=True)

        _info_row(info_card, "Txn #",    row.get("transaction_number", "—"))
        _info_row(info_card, "Date",     (row.get("created_at") or "")[:16] or "—")
        _info_row(info_card, "Service",  row.get("service_type", "—"))
        _info_row(info_card, "Mechanic", self._mechanic)
        _info_row(info_card, "Status",   status.replace("_", " ").title(),
                  value_color=status_color)
        notes = row.get("description") or row.get("notes") or "—"
        _info_row(info_card, "Notes",    notes)
        if linked:
            _info_row(info_card, "Linked Sale", linked, value_color=ACCENT)
        ctk.CTkFrame(info_card, fg_color="transparent", height=8).pack()

        # ── Totals card ──────────────────────────────────────────────────────
        totals_card = ctk.CTkFrame(scroll, fg_color=BG_CARD, corner_radius=12,
                                   border_width=1, border_color=BORDER)
        totals_card.pack(fill="x", pady=(0, 10))
        totals_card.grid_columnconfigure(1, weight=1)

        def _tot_row(parent, label, value, grid_row, bold=False, color=TEXT_SECONDARY):
            ctk.CTkLabel(
                parent, text=label,
                font=ctk.CTkFont(family="Segoe UI", size=12,
                                 weight="bold" if bold else "normal"),
                text_color=color, anchor="w"
            ).grid(row=grid_row, column=0, sticky="w", padx=14,
                   pady=(10 if grid_row == 0 else 3, 3))
            ctk.CTkLabel(
                parent, text=value,
                font=ctk.CTkFont(family="Segoe UI", size=12,
                                 weight="bold" if bold else "normal"),
                text_color=color, anchor="e"
            ).grid(row=grid_row, column=1, sticky="e", padx=14,
                   pady=(10 if grid_row == 0 else 3, 3))

        _tot_row(totals_card, "Labor Fee",  f"₱{labor:,.2f}",      0)
        _tot_row(totals_card, "Parts Cost", f"₱{parts_cost:,.2f}", 1)
        _tot_row(totals_card, "VAT (12%)",  f"₱{vat:,.2f}",        2, color=TEXT_MUTED)
        ctk.CTkFrame(totals_card, fg_color=BORDER, height=1, corner_radius=0
                     ).grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=4)
        _tot_row(totals_card, "Total Due",  f"₱{total:,.2f}",      4,
                 bold=True, color=SUCCESS)
        ctk.CTkFrame(totals_card, fg_color="transparent", height=6
                     ).grid(row=5, column=0)

        # ── Parts list card ──────────────────────────────────────────────────
        parts_card = ctk.CTkFrame(scroll, fg_color=BG_CARD, corner_radius=12,
                                  border_width=1, border_color=BORDER)
        parts_card.pack(fill="x", pady=(0, 10))

        ph = ctk.CTkFrame(parts_card, fg_color="transparent")
        ph.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(
            ph, text="📦  Parts Used",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_PRIMARY
        ).pack(side="left")

        if self._parts_list:
            for p in self._parts_list:
                # p = (code, name, qty, unit_price, subtotal)
                prow = ctk.CTkFrame(parts_card, fg_color=BG_CARD_ALT,
                                    corner_radius=8)
                prow.pack(fill="x", padx=10, pady=(0, 4))
                ctk.CTkLabel(
                    prow,
                    text=f"[{p[0]}] {p[1]}",
                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                    text_color=TEXT_PRIMARY, anchor="w", wraplength=450
                ).pack(anchor="w", padx=10, pady=(6, 1))
                ctk.CTkLabel(
                    prow,
                    text=f"×{p[2]}  @₱{p[3]:,.2f}  =  ₱{p[4]:,.2f}",
                    font=ctk.CTkFont(family="Segoe UI", size=10),
                    text_color=TEXT_MUTED, anchor="w"
                ).pack(anchor="w", padx=10, pady=(0, 6))
        else:
            ctk.CTkLabel(
                parts_card, text="No parts used.",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=TEXT_MUTED, anchor="w"
            ).pack(anchor="w", padx=14, pady=(0, 12))

        # ── Bottom action bar ────────────────────────────────────────────────
        bar = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0)
        bar.pack(fill="x", side="bottom")

        ctk.CTkButton(
            bar, text="Close", width=90, height=36,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(family="Segoe UI", size=12), corner_radius=8,
            command=self._on_destroy
        ).pack(side="left", padx=(14, 0), pady=10)

        if status == "pending":
            btn_text  = "▶  Mark as In Progress"
            btn_color = "#4A6D8C"
            btn_hover = "#3a5a7a"
            enabled   = True
        elif status == "in_progress":
            btn_text  = "✅  Mark as Completed"
            btn_color = SUCCESS
            btn_hover = SUCCESS_HOVER
            enabled   = True
        else:
            btn_text  = "✔  Completed"
            btn_color = BG_INPUT
            btn_hover = BG_INPUT
            enabled   = False

        ctk.CTkButton(
            bar, text=btn_text, height=36,
            fg_color=btn_color, hover_color=btn_hover,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8,
            state="normal" if enabled else "disabled",
            command=self._do_advance
        ).pack(side="right", padx=(0, 14), pady=10)

    def _do_advance(self):
        """Delegate to the parent's _advance_status.
        The parent closes this popup, reloads the table, and restores
        the row selection — no new popup is opened.
        """
        self._advance_cb()


# ── New Service Dialog ────────────────────────────────────────────────────────
class ServiceDialog(ctk.CTkToplevel):
    """
    Redesigned wizard-style dialog for adding a new service transaction.

    UX principles applied:
    - Progressive disclosure via a 3-step wizard (reduces cognitive load)
    - Step indicator shows progress and context at a glance
    - Each step focuses on one concern: Service Info → Mechanic → Parts & Review
    - Inline validation with friendly hints, not error popups
    - Smart defaults (status = Pending, labor = 0) so most fields are optional
    - Keyboard-friendly: Enter advances steps, Esc cancels
    """

    STEPS = ["1  Service Info", "2  Mechanic", "3  Parts & Review"]

    # Dialog dimensions — defined once, used by centering logic
    _W = 980
    _H = 720

    def __init__(self, master, user, callback):
        super().__init__(master)
        self.user               = user
        self.callback           = callback
        self.cart               = []
        self.selected_mechanics = []
        self._all_mechanics     = _get_mechanics()
        self._current_step      = 0
        self._status_buttons    = {}

        # Configure window BEFORE building widgets.
        # We replicate style_dialog manually here so we can defer grab_set().
        # grab_set() called before the CTkToplevel canvas is mapped on Windows
        # causes an infinite freeze — defer it until the window is fully drawn.
        self.title("New Service Transaction")
        self.configure(fg_color=BG_DARK)
        self.resizable(True, True)
        self.minsize(self._W, self._H)
        self._build_chrome()
        self._build_step_panels()
        self._show_step(0)
        # Defer geometry, centering, and grab until after the event loop
        # has processed the initial draw — safe on all platforms.
        self.after(200, self._finalize_window)

    def _finalize_window(self):
        """Called once via after(200) — window is fully drawn by then.
        Sets size, centers over parent, then arms the modal grab safely.
        """
        w, h = self._W, self._H
        # Center over parent; fall back to screen center
        try:
            mx = self.master.winfo_rootx()
            my = self.master.winfo_rooty()
            mw = self.master.winfo_width()
            mh = self.master.winfo_height()
            x = mx + (mw - w) // 2
            y = my + (mh - h) // 2
        except Exception:
            x = (self.winfo_screenwidth()  - w) // 2
            y = (self.winfo_screenheight() - h) // 2
        # Clamp: keep fully on-screen
        x = max(0, min(x, self.winfo_screenwidth()  - w))
        y = max(0, min(y, self.winfo_screenheight() - h))
        self.geometry(f"{w}x{h}+{x}+{y}")
        # Load products (DB read) and grab focus — both safe after draw
        self._load_products()
        self.grab_set()
        self.focus_force()

    # ── Chrome (title bar, step indicator, action bar) ──────────────────────

    def _build_chrome(self):
        import tkinter as tk

        # ── Title bar ───────────────────────────────────────────────────────
        title_bar = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0,
                                 border_width=0)
        title_bar.pack(fill="x", side="top")

        ctk.CTkLabel(
            title_bar, text="🔧  New Service Transaction",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=TEXT_PRIMARY
        ).pack(side="left", padx=20, pady=12)

        # ── Step indicator bar ───────────────────────────────────────────────
        self._step_bar = ctk.CTkFrame(self, fg_color=BG_CARD_ALT,
                                      corner_radius=0, height=44)
        self._step_bar.pack(fill="x", side="top")
        self._step_bar.pack_propagate(False)

        self._step_btns = []
        inner_bar = ctk.CTkFrame(self._step_bar, fg_color="transparent")
        # Use pack instead of place — place() inside pack_propagate(False)
        # triggers an infinite resize loop in CTk on Windows.
        inner_bar.pack(expand=True, anchor="center")

        for i, label in enumerate(self.STEPS):
            btn = ctk.CTkButton(
                inner_bar, text=label, height=28, width=180,
                fg_color="transparent", hover_color=BG_HOVER,
                text_color=TEXT_MUTED,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                corner_radius=6,
                command=lambda s=i: self._show_step(s)
            )
            btn.pack(side="left", padx=4)
            self._step_btns.append(btn)

            if i < len(self.STEPS) - 1:
                ctk.CTkLabel(inner_bar, text="›", text_color=TEXT_MUTED,
                             font=ctk.CTkFont(size=14)).pack(side="left")

        # ── Bottom action bar ────────────────────────────────────────────────
        action_bar = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0)
        action_bar.pack(fill="x", side="bottom")

        ctk.CTkButton(
            action_bar, text="Cancel", width=100, height=38,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(family="Segoe UI", size=12), corner_radius=8,
            command=self.destroy
        ).pack(side="left", padx=(16, 0), pady=10)

        self._back_btn = ctk.CTkButton(
            action_bar, text="← Back", width=100, height=38,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(family="Segoe UI", size=12), corner_radius=8,
            command=self._go_back
        )
        self._back_btn.pack(side="left", padx=(8, 0), pady=10)

        self._next_btn = ctk.CTkButton(
            action_bar, text="Next  →", height=38, width=120,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8, command=self._go_next
        )
        self._next_btn.pack(side="right", padx=(0, 16), pady=10)

        self._save_btn = ctk.CTkButton(
            action_bar, text="💾  Save Transaction", height=38,
            fg_color=SUCCESS, hover_color=SUCCESS_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8, command=self._save
        )
        # _save_btn is shown only on last step (packed on demand)

        # Totals in action bar — visible on step 3
        self._bar_totals = ctk.CTkFrame(action_bar, fg_color="transparent")
        self.parts_total_label = ctk.CTkLabel(
            self._bar_totals, text="Parts: ₱0.00",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_SECONDARY
        )
        self.parts_total_label.pack(side="left", padx=(0, 16))
        self.grand_total_label = ctk.CTkLabel(
            self._bar_totals, text="Total: ₱0.00",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=SUCCESS
        )
        self.grand_total_label.pack(side="left")

    # ── Step panels (all built upfront, only one visible at a time) ──────────

    def _build_step_panels(self):
        import tkinter as tk

        # Container that all step frames live in
        self._panel_host = tk.Frame(self, bg=BG_DARK)
        self._panel_host.pack(fill="both", expand=True)

        self._panels = []
        self._panels.append(self._build_step1(self._panel_host))
        self._panels.append(self._build_step2(self._panel_host))
        self._panels.append(self._build_step3(self._panel_host))

    # ── Step 1 — Service Info ────────────────────────────────────────────────

    def _build_step1(self, host):
        import tkinter as tk

        frame = tk.Frame(host, bg=BG_DARK)

        # Card container
        card = ctk.CTkFrame(frame, fg_color=BG_CARD, corner_radius=14,
                            border_width=1, border_color=BORDER)
        card.pack(fill="both", expand=True, padx=20, pady=10)

        # Step heading
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(16, 4))
        ctk.CTkLabel(head, text="What service was performed?",
                     font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(side="left")

        sep = ctk.CTkFrame(card, fg_color=BORDER, height=1, corner_radius=0)
        sep.pack(fill="x", padx=20, pady=(0, 16))

        # ── Service Type ────────────────────────────────────────────────────
        self._field_label(card, "Service Type  *")
        self.service_type_var = ctk.StringVar(value=SERVICE_TYPES[0])
        create_option_menu(card, values=SERVICE_TYPES,
                           variable=self.service_type_var,
                           command=self._update_hint).pack(fill="x", padx=20)

        self.hint_label = ctk.CTkLabel(
            card, text=SERVICE_PRICE_HINTS[SERVICE_TYPES[0]],
            text_color=ACCENT_LIGHT, wraplength=660,
            font=ctk.CTkFont(family="Segoe UI", size=10, slant="italic"),
            anchor="w", justify="left"
        )
        self.hint_label.pack(fill="x", padx=20, pady=(3, 12))

        # ── Description ─────────────────────────────────────────────────────
        self._field_label(card, "Notes / Description  (optional)")
        self.description = ctk.CTkEntry(
            card, placeholder_text="e.g. Replaced front brake pads, adjusted cable tension",
            height=36, fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=12), corner_radius=8)
        self.description.pack(fill="x", padx=20)
        self.description.bind("<Return>", lambda e: self._go_next())

        # ── Labor Fee ───────────────────────────────────────────────────────
        ctk.CTkFrame(card, fg_color=BORDER, height=1,
                     corner_radius=0).pack(fill="x", padx=20, pady=10)

        self._field_label(card, "Labor Fee  (₱)")

        labor_row = ctk.CTkFrame(card, fg_color="transparent")
        labor_row.pack(fill="x", padx=20, pady=(0, 4))

        ctk.CTkLabel(labor_row, text="₱",
                     font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
                     text_color=TEXT_SECONDARY, width=20).pack(side="left", padx=(0, 4))

        self.labor_fee = ctk.CTkEntry(
            labor_row, placeholder_text="0.00", width=180,
            height=36, fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=13), corner_radius=8)
        self.labor_fee.pack(side="left")
        self.labor_fee.bind("<KeyRelease>", lambda e: self._update_total())
        self.labor_fee.bind("<Return>", lambda e: self._go_next())

        ctk.CTkLabel(labor_row, text="Leave blank for free / quoted later",
                     text_color=TEXT_MUTED,
                     font=ctk.CTkFont(family="Segoe UI", size=10),
                     ).pack(side="left", padx=(12, 0))

        # ── Status ──────────────────────────────────────────────────────────
        ctk.CTkFrame(card, fg_color=BORDER, height=1,
                     corner_radius=0).pack(fill="x", padx=20, pady=10)

        self._field_label(card, "Initial Status")

        status_row = ctk.CTkFrame(card, fg_color="transparent")
        status_row.pack(fill="x", padx=20, pady=(0, 4))
        self.status_var = ctk.StringVar(value="pending")

        STATUS_OPTIONS = [
            ("pending",     "⏳  Pending",     "#B88B2E"),
            ("in_progress", "🔧  In Progress", "#4A6D8C"),
            ("completed",   "✅  Completed",   "#4A7C59"),
        ]
        for val, label, col in STATUS_OPTIONS:
            b = ctk.CTkButton(
                status_row, text=label, height=34,
                fg_color=BG_INPUT, hover_color=BG_HOVER,
                border_width=2, border_color=BORDER,
                text_color=TEXT_SECONDARY,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                corner_radius=8,
                command=lambda v=val, c=col: self._set_status(v, c)
            )
            b.pack(side="left", expand=True, fill="x", padx=(0, 4))
            self._status_buttons[val] = (b, col)

        self._set_status("pending", "#B88B2E")

        # Bottom breathing room so status buttons are never clipped
        ctk.CTkFrame(card, fg_color="transparent", height=14).pack()

        return frame

    # ── Step 2 — Mechanic ────────────────────────────────────────────────────

    def _build_step2(self, host):
        import tkinter as tk
        from tkinter import ttk as _ttk

        frame = tk.Frame(host, bg=BG_DARK)

        card = ctk.CTkFrame(frame, fg_color=BG_CARD, corner_radius=14,
                            border_width=1, border_color=BORDER)
        card.pack(fill="both", expand=True, padx=24, pady=18)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(16, 4))
        ctk.CTkLabel(head, text="Who performed the service?",
                     font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(side="left")

        sep = ctk.CTkFrame(card, fg_color=BORDER, height=1, corner_radius=0)
        sep.pack(fill="x", padx=20, pady=(0, 16))

        # ── Pick & add mechanic ─────────────────────────────────────────────
        self._field_label(card, "Select mechanic from roster  *")

        pick_row = ctk.CTkFrame(card, fg_color="transparent")
        pick_row.pack(fill="x", padx=20, pady=(0, 12))

        mech_names = [m["name"] for m in self._all_mechanics] or ["No mechanics"]
        self._mechanic_pick_var = ctk.StringVar(value=mech_names[0])
        create_option_menu(pick_row, values=mech_names,
                           variable=self._mechanic_pick_var).pack(
                               side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            pick_row, text="+ Add to Job", width=110, height=36,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8, command=self._add_mechanic
        ).pack(side="left")

        # ── Assigned mechanics list ─────────────────────────────────────────
        self._field_label(card, "Assigned to this service")

        list_card = ctk.CTkFrame(card, fg_color=BG_CARD_ALT, corner_radius=8,
                                 border_width=1, border_color=BORDER)
        list_card.pack(fill="x", padx=20, pady=(0, 8))

        self.mech_tree = _ttk.Treeview(list_card, columns=("mname",),
                                        show="headings", height=5)
        self.mech_tree.heading("mname", text="Mechanic")
        self.mech_tree.column("mname", width=400, anchor="w")
        style_treeview(self.mech_tree, row_height=28)
        self.mech_tree.pack(fill="x", padx=6, pady=6)

        ctk.CTkButton(
            card, text="✕  Remove Selected", height=28, width=160,
            fg_color="transparent", hover_color="#F0D0D0",
            border_width=1, border_color=DANGER,
            text_color=DANGER,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=6, command=self._remove_mechanic
        ).pack(anchor="w", padx=20, pady=(0, 12))

        # Empty-state hint
        self._mech_hint = ctk.CTkLabel(
            card,
            text="ℹ️  At least one mechanic is required to save the transaction.",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=TEXT_MUTED, anchor="w"
        )
        self._mech_hint.pack(fill="x", padx=20, pady=(0, 8))

        return frame

    # ── Step 3 — Parts & Review ─────────────────────────────────────────────
    #
    #  Layout mirrors sales_window SalesFrame:
    #    TOP BAR  : Txn badge | shortcut hints
    #    LEFT (70%): Inline search bar + "Browse Product" button
    #                + Parts Used table (single table, no catalog pane)
    #                + Remove / Clear action row
    #    RIGHT(30%): Order summary card (service info, totals breakdown)
    #                + Save-accessible from the action bar below

    def _build_step3(self, host):
        import tkinter as tk

        # Dropdown state (mirrors SalesFrame._dropdown pattern)
        self._parts_dropdown = None
        self._parts_popup_open = False

        frame = tk.Frame(host, bg=BG_DARK)

        # ── Two-column body ─────────────────────────────────────────────────
        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=8)
        body.grid_columnconfigure(0, weight=68)
        body.grid_columnconfigure(1, weight=32, minsize=270)
        body.grid_rowconfigure(0, weight=1)

        # ══════════════════════════════════════════
        #  LEFT — Parts Used panel (sales_window style)
        # ══════════════════════════════════════════
        left_panel = ctk.CTkFrame(body, fg_color=BG_CARD, corner_radius=12,
                                  border_width=1, border_color=BORDER)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left_panel.grid_propagate(False)
        left_panel.grid_rowconfigure(2, weight=1)
        left_panel.grid_columnconfigure(0, weight=1)

        # ── Toolbar: inline search + Browse Product button ───────────────────
        toolbar = ctk.CTkFrame(left_panel, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        toolbar.grid_columnconfigure(0, weight=1)

        self.parts_search_var = ctk.StringVar()
        self._parts_search_entry = ctk.CTkEntry(
            toolbar,
            textvariable=self.parts_search_var,
            placeholder_text="🔍  Search products or filter parts list…",
            height=34, fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=12), corner_radius=8,
        )
        self._parts_search_entry.grid(row=0, column=0, sticky="ew")

        # Drive inline dropdown + parts-table filter on every keystroke
        self.parts_search_var.trace("w", self._on_parts_search_change)

        # Keyboard navigation while focus is in the search entry
        self._parts_search_entry.bind("<Down>",   lambda e: self._pdd_move(+1))
        self._parts_search_entry.bind("<Up>",     lambda e: self._pdd_move(-1))
        self._parts_search_entry.bind("<Return>", lambda e: self._pdd_confirm())
        self._parts_search_entry.bind("<Escape>", lambda e: self._pdd_close())
        self._parts_search_entry.bind(
            "<FocusOut>", lambda e: self.after(150, self._pdd_close))

        # Browse Product button — opens full two-column browser popup
        ctk.CTkButton(
            toolbar, text="  Browse Product  ", width=170, height=34,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8,
            command=self._open_parts_browse_popup,
        ).grid(row=0, column=1, sticky="e", padx=(8, 0))

        # ── Parts table header row ────────────────────────────────────────────
        ph = ctk.CTkFrame(left_panel, fg_color="transparent")
        ph.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        ctk.CTkLabel(
            ph, text="Parts Used",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")
        self._parts_count_lbl = ctk.CTkLabel(
            ph, text="Empty",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
        )
        self._parts_count_lbl.pack(side="left", padx=10)
        ctk.CTkLabel(
            ph, text="Double-click row to edit qty",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=TEXT_MUTED,
        ).pack(side="right")

        # ── Parts Used table (THE single table — no catalog pane) ────────────
        tf = ctk.CTkFrame(left_panel, fg_color=BG_CARD_ALT, corner_radius=10)
        tf.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 8))

        cart_cols = ("name", "qty", "price", "sub")
        self.cart_tree = ttk.Treeview(
            tf, columns=cart_cols, show="headings", selectmode="browse")
        for col, lbl, w, anchor in [
            ("name",  "Part / Product", 260, "w"),
            ("qty",   "Qty",             55, "center"),
            ("price", "Unit Price",     110, "e"),
            ("sub",   "Subtotal",       120, "e"),
        ]:
            self.cart_tree.heading(col, text=lbl)
            self.cart_tree.column(col, width=w, minwidth=40, anchor=anchor)
        style_treeview(self.cart_tree, row_height=36)

        vsb = ttk.Scrollbar(tf, orient="vertical", command=self.cart_tree.yview)
        self.cart_tree.configure(yscrollcommand=vsb.set)
        self.cart_tree.pack(side="left", fill="both", expand=True,
                            padx=(4, 0), pady=4)
        vsb.pack(side="right", fill="y", pady=4, padx=(0, 4))

        # Double-click → inline qty editor, Delete key → remove
        self.cart_tree.bind("<Double-1>", self._open_part_qty_popup)
        self.cart_tree.bind("<Return>",   self._open_part_qty_popup)
        self.cart_tree.bind("<Delete>",   lambda e: self._remove_part())

        # ── Action buttons row (Remove / Clear) ───────────────────────────────
        br = ctk.CTkFrame(left_panel, fg_color="transparent")
        br.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 14))

        ctk.CTkButton(
            br, text="Remove Selected", height=32,
            fg_color=BG_CARD_ALT, hover_color=DANGER,
            text_color=TEXT_SECONDARY,
            border_width=1, border_color=BORDER,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=8, command=self._remove_part,
        ).pack(side="left")

        ctk.CTkButton(
            br, text="Clear All", height=32,
            fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
            text_color=TEXT_MUTED,
            border_width=1, border_color=BORDER,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=8, command=self._clear_parts,
        ).pack(side="left", padx=(8, 0))

        # ══════════════════════════════════════════
        #  RIGHT — Summary panel (order review)
        # ══════════════════════════════════════════
        right_panel = ctk.CTkFrame(body, fg_color=BG_CARD, corner_radius=12,
                                   border_width=1, border_color=BORDER)
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.grid_rowconfigure(1, weight=1)
        right_panel.grid_columnconfigure(0, weight=1)

        # ── Summary header ────────────────────────────────────────────────────
        sh = ctk.CTkFrame(right_panel, fg_color=ACCENT_SUBTLE,
                          corner_radius=10, border_width=1,
                          border_color=ACCENT_LIGHT)
        sh.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        ctk.CTkLabel(
            sh, text="🧾  Service Detail",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=ACCENT,
        ).pack(anchor="w", padx=12, pady=(8, 6))

        # ── Service info review (populated by _update_review) ─────────────────
        info_card = ctk.CTkFrame(right_panel, fg_color=BG_CARD_ALT,
                                 corner_radius=8,
                                 border_width=1, border_color=BORDER)
        info_card.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        info_card.grid_columnconfigure(0, weight=1)

        self._review_svc = ctk.CTkLabel(
            info_card, text="Service: —",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_PRIMARY, anchor="w", wraplength=220,
        )
        self._review_svc.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 2))

        self._review_mech = ctk.CTkLabel(
            info_card, text="Mechanic(s): —",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_SECONDARY, anchor="w", wraplength=220,
        )
        self._review_mech.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 2))

        self._review_status = ctk.CTkLabel(
            info_card, text="Status: —",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_SECONDARY, anchor="w",
        )
        self._review_status.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 2))

        self._review_desc = ctk.CTkLabel(
            info_card, text="Notes: —",
            font=ctk.CTkFont(family="Segoe UI", size=12, slant="italic"),
            text_color=TEXT_MUTED, anchor="w", wraplength=220,
        )
        self._review_desc.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 10))

        # ── Divider ───────────────────────────────────────────────────────────
        ctk.CTkFrame(info_card, fg_color=BORDER, height=1,
                     corner_radius=0).grid(
            row=4, column=0, sticky="ew", padx=8, pady=0)

        # ── Totals breakdown (mirrors sales_window right panel) ───────────────
        def _tot_row(parent, row, label, var, bold=False, color=TEXT_SECONDARY):
            ctk.CTkLabel(
                parent, text=label,
                font=ctk.CTkFont(
                    family="Segoe UI", size=13,
                    weight="bold" if bold else "normal"),
                text_color=color, anchor="w",
            ).grid(row=row, column=0, sticky="w", padx=12,
                   pady=(8 if row == 0 else 2, 2))
            lbl = ctk.CTkLabel(
                parent, textvariable=var,
                font=ctk.CTkFont(
                    family="Segoe UI", size=13,
                    weight="bold" if bold else "normal"),
                text_color=color, anchor="e",
            )
            lbl.grid(row=row, column=1, sticky="e", padx=12,
                     pady=(8 if row == 0 else 2, 2))
            return lbl

        info_card.grid_columnconfigure(1, weight=1)

        self._sum_labor_var  = ctk.StringVar(value="₱0.00")
        self._sum_parts_var  = ctk.StringVar(value="₱0.00")
        self._sum_vat_var    = ctk.StringVar(value="₱0.00")
        self._sum_total_var  = ctk.StringVar(value="₱0.00")
        self._sum_items_var  = ctk.StringVar(value="0 item(s)")

        _tot_row(info_card, 5,  "Labor Fee:",   self._sum_labor_var)
        _tot_row(info_card, 6,  "Parts Cost:",  self._sum_parts_var)
        _tot_row(info_card, 7,  "VAT (12%):",   self._sum_vat_var,
                 color=TEXT_MUTED)

        ctk.CTkFrame(info_card, fg_color=BORDER, height=1,
                     corner_radius=0).grid(
            row=8, column=0, columnspan=2, sticky="ew", padx=8, pady=4)

        _tot_row(info_card, 9, "TOTAL DUE:",   self._sum_total_var,
                 bold=True, color=SUCCESS)

        self._sum_items_lbl = ctk.CTkLabel(
            info_card, textvariable=self._sum_items_var,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_MUTED, anchor="w",
        )
        self._sum_items_lbl.grid(row=10, column=0, columnspan=2,
                                  sticky="w", padx=12, pady=(0, 12))

        return frame

    # ── Wizard navigation ────────────────────────────────────────────────────

    def _show_step(self, step: int):
        # Hide all panels
        for p in self._panels:
            p.pack_forget()

        self._current_step = step
        self._panels[step].pack(fill="both", expand=True)

        # Update step button styles
        for i, btn in enumerate(self._step_btns):
            if i == step:
                btn.configure(
                    fg_color=ACCENT_SUBTLE, text_color=ACCENT,
                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold")
                )
            elif i < step:
                btn.configure(
                    fg_color="transparent", text_color=SUCCESS,
                    font=ctk.CTkFont(family="Segoe UI", size=11)
                )
            else:
                btn.configure(
                    fg_color="transparent", text_color=TEXT_MUTED,
                    font=ctk.CTkFont(family="Segoe UI", size=11)
                )

        is_first = (step == 0)
        is_last  = (step == len(self.STEPS) - 1)

        # Back button visibility
        if is_first:
            self._back_btn.pack_forget()
        else:
            self._back_btn.pack(side="left", padx=(8, 0), pady=10)

        # Next / Save button swap
        if is_last:
            self._next_btn.pack_forget()
            self._save_btn.pack(side="right", padx=(0, 16), pady=10)
            self._bar_totals.pack(side="right", padx=(0, 12))
            self._update_review()
        else:
            self._save_btn.pack_forget()
            self._bar_totals.pack_forget()
            self._next_btn.pack(side="right", padx=(0, 16), pady=10)

    def _go_next(self):
        if self._current_step < len(self.STEPS) - 1:
            if self._validate_step(self._current_step):
                self._show_step(self._current_step + 1)

    def _go_back(self):
        if self._current_step > 0:
            self._show_step(self._current_step - 1)

    def _validate_step(self, step: int) -> bool:
        """Return True if the step passes validation; show inline error otherwise."""
        if step == 0:
            # Labor fee must be numeric if provided
            val = self.labor_fee.get().strip()
            if val:
                try:
                    float(val)
                except ValueError:
                    msg_warning(self, "Invalid Labor Fee",
                                "Labor fee must be a number (e.g. 150 or 0).\n"
                                "Leave it blank if you will quote it later.")
                    return False
        elif step == 1:
            if not self.selected_mechanics:
                msg_warning(self, "Mechanic Required",
                            "Please add at least one mechanic before continuing.")
                return False
        return True

    # ── Review summary (step 3 header) ──────────────────────────────────────

    def _update_review(self):
        stype  = self.service_type_var.get()
        mechs  = ", ".join(m["name"] for m in self.selected_mechanics) or "—"
        status = self.status_var.get().replace("_", " ").title()
        desc   = self.description.get().strip() or "—"
        self._review_svc.configure(text=f"Service: {stype}")
        self._review_mech.configure(text=f"Mechanic(s): {mechs}")
        self._review_status.configure(text=f"Status: {status}")
        self._review_desc.configure(text=f"Notes: {desc}")
        self._update_total()

    # ── Shared helpers ───────────────────────────────────────────────────────

    def _field_label(self, parent, text: str):
        ctk.CTkLabel(parent, text=text, anchor="w",
                     font=ctk.CTkFont(family="Segoe UI", size=11),
                     text_color=TEXT_SECONDARY).pack(fill="x", padx=20, pady=(10, 2))

    # ─────────────────────────────────────────────────────────────────────────
    #  PRODUCTS — load & inline search (sales_window pattern)
    # ─────────────────────────────────────────────────────────────────────────

    def _load_products(self):
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, code, name, category, selling_price, current_stock, "
            "low_stock_threshold FROM products ORDER BY name"
        ).fetchall()
        conn.close()
        # Store as plain dicts so they match the _ProductDropdown contract
        self.all_products = [dict(r) for r in rows]

    # ── Inline search bar callbacks ──────────────────────────────────────────

    def _on_parts_search_change(self, *_):
        """Drive the floating dropdown + filter the parts-used table."""
        q = self.parts_search_var.get().strip()
        if q:
            matches = [
                p for p in self.all_products
                if q.lower() in p["name"].lower()
                or q.lower() in (p.get("code") or "").lower()
            ]
            if matches:
                self._pdd_open(matches)
            else:
                self._pdd_close()
            self._filter_parts_table(q)
        else:
            self._pdd_close()
            self._filter_parts_table("")

    def _filter_parts_table(self, q: str):
        """Re-render parts-used table, optionally filtered by q."""
        for r in self.cart_tree.get_children():
            self.cart_tree.delete(r)
        items = self.cart if not q else [
            c for c in self.cart if q.lower() in c["name"].lower()
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

    # ── Inline dropdown (floating, borderless) ───────────────────────────────

    def _pdd_open(self, products: list):
        """Create / replace the floating product dropdown below the search bar."""
        if self._parts_dropdown and self._parts_dropdown.winfo_exists():
            self._parts_dropdown.destroy()
        self._parts_dropdown = _ProductDropdown(
            self.winfo_toplevel(),
            self._parts_search_entry,
            products,
            self._on_parts_search_selected,
        )

    def _pdd_close(self):
        if self._parts_dropdown and self._parts_dropdown.winfo_exists():
            self._parts_dropdown.destroy()
        self._parts_dropdown = None

    def _pdd_move(self, direction: int):
        if self._parts_dropdown and self._parts_dropdown.winfo_exists():
            self._parts_dropdown.move_cursor(direction)

    def _pdd_confirm(self):
        if self._parts_dropdown and self._parts_dropdown.winfo_exists():
            self._parts_dropdown.pick_selected()

    def _on_parts_search_selected(self, product: dict):
        """Called when user picks a product from the inline dropdown."""
        if product["current_stock"] <= 0:
            msg_warning(self, "Out of Stock",
                        f"'{product['name']}' has no stock available.")
            self._pdd_close()
            return
        self._add_product_to_cart(product, qty=1)
        self.parts_search_var.set("")        # clear → triggers _pdd_close
        self._parts_search_entry.focus()

    # ── Browse Product popup ─────────────────────────────────────────────────

    def _open_parts_browse_popup(self):
        if self._parts_popup_open:
            return
        self._parts_popup_open = True
        ProductSearchPopup(
            self.winfo_toplevel(),
            self.all_products,
            lambda product, qty: self._add_product_to_cart(product, qty),
            lambda: setattr(self, "_parts_popup_open", False),
        )

    # ── Cart operations ──────────────────────────────────────────────────────

    def _add_product_to_cart(self, product: dict, qty: int = 1):
        """Merge product into cart; increment qty if already present."""
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

    def _remove_part(self):
        sel = self.cart_tree.selection()
        if not sel:
            return
        idx = self.cart_tree.index(sel[0])
        if 0 <= idx < len(self.cart):
            self.cart.pop(idx)
            self._refresh_cart()

    def _clear_parts(self):
        if self.cart and not msg_question(
                self, "Clear Parts", "Remove all parts from this service?"):
            return
        self.cart.clear()
        self._refresh_cart()

    def _refresh_cart(self):
        """Full re-render of the parts-used table + update summary."""
        self._pdd_close()
        for item in self.cart_tree.get_children():
            self.cart_tree.delete(item)
        for i, c in enumerate(self.cart):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.cart_tree.insert("", "end", tags=(tag,), values=(
                c["name"], c["qty"],
                f"₱{c['price']:,.2f}", f"₱{c['subtotal']:,.2f}"
            ))
        n = len(self.cart)
        units = sum(c["qty"] for c in self.cart)
        self._parts_count_lbl.configure(
            text=f"{n} item(s) · {units} unit(s)" if n else "Empty")
        self._update_total()

    # ── Qty editor popup (double-click a row) ────────────────────────────────

    def _open_part_qty_popup(self, event=None):
        sel = self.cart_tree.selection()
        if not sel:
            return
        idx  = self.cart_tree.index(sel[0])
        if idx >= len(self.cart):
            return
        item = self.cart[idx]

        def _save(new_qty):
            self.cart[idx]["qty"]     = new_qty
            self.cart[idx]["subtotal"] = new_qty * self.cart[idx]["price"]
            self._refresh_cart()

        PartQtyEditPopup(self.winfo_toplevel(), item, _save)

    def _update_total(self):
        VAT_RATE = 0.12
        parts_total = sum(c["subtotal"] for c in self.cart)
        try:
            labor = float(self.labor_fee.get() or 0)
        except (ValueError, AttributeError):
            labor = 0
        vat   = round(parts_total * VAT_RATE, 2)
        grand = round(labor + parts_total + vat, 2)
        # Action-bar labels (always present)
        self.parts_total_label.configure(text=f"Parts: ₱{parts_total:,.2f}")
        self.grand_total_label.configure(text=f"Total (VAT-inc): ₱{grand:,.2f}")
        # Right-panel summary vars (only available after step 3 is built)
        try:
            self._sum_labor_var.set(f"₱{labor:,.2f}")
            self._sum_parts_var.set(f"₱{parts_total:,.2f}")
            self._sum_vat_var.set(f"₱{vat:,.2f}")
            self._sum_total_var.set(f"₱{grand:,.2f}")
            n     = len(self.cart)
            units = sum(c["qty"] for c in self.cart)
            self._sum_items_var.set(
                f"{n} part type(s), {units} unit(s) total" if n else "No parts added")
        except AttributeError:
            pass  # Summary vars don't exist yet (step 3 not built); safe to skip

    def _set_status(self, value, color):
        self.status_var.set(value)
        for val, (btn, col) in self._status_buttons.items():
            if val == value:
                btn.configure(fg_color=col, text_color="#FFFFFF",
                              border_color=col)
            else:
                btn.configure(fg_color=BG_INPUT, text_color=TEXT_SECONDARY,
                              border_color=BORDER)

    def _add_mechanic(self):
        name = self._mechanic_pick_var.get().strip()
        if not name or name.startswith("No mechanics"):
            return
        mechanic = next((m for m in self._all_mechanics if m["name"] == name), None)
        if mechanic is None:
            return
        # Prevent duplicates
        if any(m["id"] == mechanic["id"] for m in self.selected_mechanics):
            msg_warning(self, "Duplicate", f"{name} is already added.")
            return
        self.selected_mechanics.append(mechanic)
        self._refresh_mech_tree()

    def _remove_mechanic(self):
        sel = self.mech_tree.selection()
        if not sel:
            return
        idx = self.mech_tree.index(sel[0])
        if 0 <= idx < len(self.selected_mechanics):
            self.selected_mechanics.pop(idx)
        self._refresh_mech_tree()

    def _refresh_mech_tree(self):
        for item in self.mech_tree.get_children():
            self.mech_tree.delete(item)
        for i, m in enumerate(self.selected_mechanics):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.mech_tree.insert("", "end", tags=(tag,), values=(m["name"],))

    def _update_hint(self, value):
        self.hint_label.configure(text=SERVICE_PRICE_HINTS.get(value, ""))

    def _save(self):
        stype = self.service_type_var.get()
        if not stype:
            msg_warning(self, "Required", "Service type is required.")
            return
        if not self.selected_mechanics:
            msg_warning(self, "Required", "Please add at least one mechanic.")
            return
        mechanic_names_str = ", ".join(m["name"] for m in self.selected_mechanics)
        try:
            labor = float(self.labor_fee.get() or 0)
        except ValueError:
            msg_warning(self, "Invalid", "Enter a valid labor fee.")
            return

        parts_total = sum(c["subtotal"] for c in self.cart)
        vat         = round(parts_total * 0.12, 2)
        total       = round(labor + parts_total + vat, 2)
        txn_num     = generate_transaction_number("SV")
        status      = self.status_var.get()

        # ── Cash-drawer session guard ─────────────────────────────
        active_session = get_any_active_session()
        if not active_session:
            msg_warning(
                self, "Cash Drawer Closed",
                "The cash drawer is not open.\n\n"
                "Please open a shift from the Cash Drawer module\n"
                "before recording a service.",
            )
            return

        conn = get_connection()
        try:
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO service_transactions
                (transaction_number, mechanic_id, mechanic_name, customer_id,
                 service_type, description, labor_fee, parts_total, total, status, session_id)
                VALUES (?,?,?,NULL,?,?,?,?,?,?,?)
            """, (txn_num, self.user["id"], mechanic_names_str, stype,
                  self.description.get().strip(), labor, parts_total, total, status,
                  active_session["id"]))
            svc_id = cur.lastrowid

            # Insert one-to-many mechanic records
            for m in self.selected_mechanics:
                cur.execute("""
                    INSERT INTO service_mechanics (service_id, mechanic_id, mechanic_name)
                    VALUES (?,?,?)
                """, (svc_id, m["id"], m["name"]))

            for item in self.cart:
                cur.execute("""
                    INSERT INTO service_parts
                    (service_id, product_id, quantity, unit_price, subtotal)
                    VALUES (?,?,?,?,?)
                """, (svc_id, item["product_id"], item["qty"],
                      item["price"], item["subtotal"]))

            linked_sale = None
            if status == "completed" and parts_total > 0:
                sale_txn_num = generate_transaction_number("SL")
                cur.execute("""
                    INSERT INTO sales_transactions
                    (transaction_number, cashier_id, subtotal, discount, total,
                     amount_tendered, change_given, payment_method, notes, session_id)
                    VALUES (?,?,?,0,?,?,0,'cash',?,?)
                """, (sale_txn_num, self.user["id"], parts_total, parts_total,
                      parts_total, f"Parts used in service {txn_num}",
                      active_session["id"]))
                sale_id = cur.lastrowid

                for item in self.cart:
                    cur.execute("""
                        INSERT INTO sale_items
                        (transaction_id, product_id, quantity, unit_price, subtotal)
                        VALUES (?,?,?,?,?)
                    """, (sale_id, item["product_id"], item["qty"],
                          item["price"], item["subtotal"]))
                    cur.execute("""
                        UPDATE products
                        SET current_stock = current_stock - ?,
                            updated_at = datetime('now','localtime')
                        WHERE id=?
                    """, (item["qty"], item["product_id"]))
                    cur.execute("""
                        INSERT INTO stock_adjustments
                        (product_id, user_id, change_amount, reason, reference)
                        VALUES (?,?,?,'Service Parts Used',?)
                    """, (item["product_id"], self.user["id"],
                          -item["qty"], txn_num))

                linked_sale = sale_txn_num
                cur.execute("""
                    UPDATE service_transactions SET linked_sale_txn=? WHERE id=?
                """, (linked_sale, svc_id))

            conn.commit()

            log_audit(self.user["id"], self.user["username"], "Services", "SERVICE_CREATED",
                      record_id=svc_id,
                      new_value={"txn": txn_num, "total": total, "status": status})

            msg = f"Service transaction {txn_num} saved!"
            if linked_sale:
                msg += f"\n\nParts recorded as Sales Transaction:\n{linked_sale}"
            msg_info(self, "Saved", msg)
            self.callback()
            self.destroy()

        except Exception as e:
            conn.rollback()
            msg_error(self, "Error", f"Failed to save:\n{e}")
        finally:
            conn.close()


# ── Part Qty Editor Popup (double-click row in step 3) ────────────────────────
class PartQtyEditPopup(ctk.CTkToplevel):
    """
    Compact numpad popup to edit the quantity of a part already in the
    parts-used list.  Mirrors QtyEditPopup from sales_window.
    """

    def __init__(self, parent, item: dict, on_save_cb):
        super().__init__(parent)
        self._item = item
        self._cb   = on_save_cb

        self.title("Edit Quantity")
        self.resizable(False, False)
        self.configure(fg_color=BG_CARD)
        self.grab_set()
        self.focus_force()
        # Centre over parent
        self.update_idletasks()
        px = parent.winfo_rootx() + parent.winfo_width()  // 2 - 150
        py = parent.winfo_rooty() + parent.winfo_height() // 2 - 195
        self.geometry(f"300x390+{max(0,px)}+{max(0,py)}")

        # Header
        hdr = ctk.CTkFrame(self, fg_color=ACCENT, corner_radius=0, height=46)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(
            hdr, text="Edit Quantity",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#FFFFFF",
        ).pack(side="left", padx=16)

        # Item name & stock info
        ctk.CTkLabel(
            self, text=item["name"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_PRIMARY, wraplength=260,
        ).pack(pady=(12, 2), padx=16)
        ctk.CTkLabel(
            self,
            text=f"₱{item['price']:,.2f} / unit  •  {item.get('stock', '∞')} in stock",
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
        stock = self._item.get("stock")
        if stock is not None and qty > stock:
            msg_warning(self, "Exceeds Stock",
                        f"Only {stock} unit(s) in stock.")
            return
        self._cb(qty)
        self.destroy()


# ── Manage Mechanics Dialog ───────────────────────────────────────────────────
class ManageMechanicsDialog(ctk.CTkToplevel):
    """
    Owner-only dialog to add, rename, and deactivate mechanics.
    Changes are persisted to the `mechanics` table in the database.
    """
    def __init__(self, master, user, callback):
        super().__init__(master)
        self.user     = user
        self.callback = callback
        style_dialog(self, "Manage Mechanics", 480, 560)
        self._build()
        self._load()

    def _build(self):
        # Title
        ctk.CTkLabel(
            self, text="👷  Manage Mechanics",
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
            text_color=TEXT_PRIMARY
        ).pack(anchor="w", padx=24, pady=(20, 4))

        ctk.CTkLabel(
            self,
            text="Add, rename, or deactivate mechanics from the roster.\n"
                 "Inactive mechanics are hidden from the New Service form.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED, justify="left"
        ).pack(anchor="w", padx=24, pady=(0, 12))

        # ── List of mechanics ────────────────────────────────────────────────
        list_card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=12,
                                 border_width=1, border_color=BORDER)
        list_card.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        from tkinter import ttk as _ttk
        cols = ("name", "status")
        self.tree = _ttk.Treeview(list_card, columns=cols, show="headings", height=10)
        self.tree.heading("name",   text="Mechanic Name")
        self.tree.heading("status", text="Status")
        self.tree.column("name",   width=300, anchor="w")
        self.tree.column("status", width=80,  anchor="center")
        style_treeview(self.tree)
        self.tree.pack(fill="both", expand=True, padx=6, pady=6)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # ── Action buttons row ───────────────────────────────────────────────
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 10))

        _btn = dict(height=34, font=ctk.CTkFont(family="Segoe UI", size=12), corner_radius=8)

        ctk.CTkButton(btn_row, text="✏️  Rename", width=120,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self._rename, **_btn).pack(side="left", padx=(0, 8))

        self._toggle_btn = ctk.CTkButton(btn_row, text="🚫  Deactivate", width=130,
                      fg_color=BG_INPUT, hover_color=BG_HOVER,
                      border_width=1, border_color=BORDER,
                      text_color=TEXT_PRIMARY,
                      command=self._toggle_active, **_btn)
        self._toggle_btn.pack(side="left", padx=(0, 8))

        # ── Add new mechanic ─────────────────────────────────────────────────
        add_card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=12,
                                border_width=1, border_color=BORDER)
        add_card.pack(fill="x", padx=20, pady=(0, 16))

        inner = ctk.CTkFrame(add_card, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)

        ctk.CTkLabel(inner, text="Add mechanic:",
                     font=ctk.CTkFont(family="Segoe UI", size=12),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 8))

        self.new_name_var = ctk.StringVar()
        ctk.CTkEntry(
            inner, textvariable=self.new_name_var,
            placeholder_text="e.g. Mechanic 8 — Juan Dela Cruz",
            height=34, fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=12), corner_radius=8,
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            inner, text="Add", width=70, height=34,
            fg_color=SUCCESS, hover_color=SUCCESS_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=12), corner_radius=8,
            command=self._add
        ).pack(side="left")

    def _load(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        conn = get_connection()
        rows = conn.execute("SELECT * FROM mechanics ORDER BY id").fetchall()
        conn.close()
        self._rows = {str(r["id"]): dict(r) for r in rows}
        for r in rows:
            status = "Active" if r["active"] else "Inactive"
            tag    = "active_row" if r["active"] else "inactive_row"
            self.tree.insert("", "end", iid=str(r["id"]), tags=(tag,), values=(r["display_name"], status))
        self.tree.tag_configure("inactive_row", foreground=TEXT_MUTED)

    def _selected_id(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _on_select(self, event=None):
        mid = self._selected_id()
        if mid and str(mid) in self._rows:
            is_active = self._rows[str(mid)]["active"]
            self._toggle_btn.configure(
                text="✅  Activate" if not is_active else "🚫  Deactivate"
            )

    def _add(self):
        name = self.new_name_var.get().strip()
        if not name:
            msg_warning(self, "Required", "Enter a mechanic name.")
            return
        conn = get_connection()
        try:
            conn.execute("INSERT INTO mechanics (display_name) VALUES (?)", (name,))
            conn.commit()
        except Exception as e:
            msg_error(self, "Error", str(e))
        finally:
            conn.close()
        self.new_name_var.set("")
        self._load()
        self.callback()

    def _rename(self):
        mid = self._selected_id()
        if not mid:
            msg_warning(self, "Select", "Select a mechanic to rename.")
            return

        current = self._rows[str(mid)]["display_name"]

        # Inline rename dialog
        dlg = ctk.CTkToplevel(self)
        dlg.title("Rename Mechanic")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.geometry("400x160")
        dlg.configure(fg_color=BG_CARD)

        ctk.CTkLabel(dlg, text="New name:",
                     font=ctk.CTkFont(family="Segoe UI", size=12),
                     text_color=TEXT_SECONDARY).pack(anchor="w", padx=20, pady=(16, 4))

        name_var = ctk.StringVar(value=current)
        entry = ctk.CTkEntry(dlg, textvariable=name_var, height=36,
                             fg_color=BG_INPUT, border_color=BORDER,
                             text_color=TEXT_PRIMARY,
                             font=ctk.CTkFont(family="Segoe UI", size=12), corner_radius=8)
        entry.pack(fill="x", padx=20, pady=(0, 12))
        entry.focus_set()
        entry.select_range(0, "end")

        def _save():
            new = name_var.get().strip()
            if not new:
                return
            conn = get_connection()
            conn.execute("UPDATE mechanics SET display_name=? WHERE id=?", (new, mid))
            conn.commit()
            conn.close()
            dlg.destroy()
            self._load()
            self.callback()

        entry.bind("<Return>", lambda e: _save())
        ctk.CTkButton(dlg, text="Save", height=34,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      font=ctk.CTkFont(family="Segoe UI", size=12), corner_radius=8,
                      command=_save).pack(fill="x", padx=20)

    def _toggle_active(self):
        mid = self._selected_id()
        if not mid:
            msg_warning(self, "Select", "Select a mechanic first.")
            return
        row       = self._rows[str(mid)]
        new_state = 0 if row["active"] else 1
        conn      = get_connection()
        conn.execute("UPDATE mechanics SET active=? WHERE id=?", (new_state, mid))
        conn.commit()
        conn.close()
        self._load()
        self.callback()