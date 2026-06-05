"""
VMDC Motor Parts — Approval Management Window
=============================================
Owner-only module for reviewing and acting on pending stock requests.

Workflow:
  • Owner sees all pending requests (Stock In deliveries + Stock Adjustments)
  • Owner can Approve → inventory quantity is updated immediately
  • Owner can Reject → request is archived with rejection reason
  • All actions are logged in approval_logs for full audit trail
"""

import customtkinter as ctk
from tkinter import ttk

from database import get_connection
from security import log_audit, require_role
from ui.theme import (
    BG_DARK, BG_CARD, BG_CARD_ALT, BG_INPUT, BG_HOVER, BORDER,
    ACCENT, ACCENT_HOVER, ACCENT_LIGHT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    SUCCESS, SUCCESS_HOVER, DANGER, DANGER_HOVER, WARNING,
    style_treeview, Paginator,
    create_dialog_entry, create_dialog_button, style_dialog,
    create_option_menu,
    msg_info, msg_warning, msg_error, msg_success, msg_question,
)


class ApprovalManagementFrame(ctk.CTkFrame):
    def __init__(self, master, user: dict):
        super().__init__(master, fg_color="transparent")
        self.user = user
        self._build_ui()
        self._show_tab("pending")

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            header, text="Approval Management",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        # Owner-only badge
        badge = ctk.CTkFrame(header, fg_color=ACCENT, corner_radius=8)
        badge.pack(side="left", padx=12)
        ctk.CTkLabel(badge, text="👑  Owner Only",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="white").pack(padx=10, pady=4)

        # Pending count badge (live)
        self.pending_badge_var = ctk.StringVar(value="")
        self.pending_label = ctk.CTkLabel(
            header, textvariable=self.pending_badge_var,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=WARNING,
        )
        self.pending_label.pack(side="right")

        # Tab bar
        tab_bar = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=10,
                                border_width=1, border_color=BORDER)
        tab_bar.pack(fill="x", pady=(0, 10))
        inner = ctk.CTkFrame(tab_bar, fg_color="transparent")
        inner.pack(padx=8, pady=6, anchor="w")

        self._tab_btns = {}
        for label, key in [
            ("⏳  Pending Requests", "pending"),
            ("✅  Approved",         "approved"),
            ("❌  Rejected",         "rejected"),
            ("📋  All History",      "all"),
        ]:
            btn = ctk.CTkButton(
                inner, text=label, height=34, width=175,
                fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
                text_color=TEXT_PRIMARY, corner_radius=8,
                font=ctk.CTkFont(size=12, weight="bold"),
                command=lambda k=key: self._show_tab(k),
            )
            btn.pack(side="left", padx=(0, 6))
            self._tab_btns[key] = btn

        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.pack(fill="both", expand=True)

        self._update_pending_count()

    def _update_pending_count(self):
        conn = get_connection()
        count = conn.execute(
            "SELECT COUNT(*) FROM stock_update_requests WHERE status='pending'"
        ).fetchone()[0]
        conn.close()
        if count > 0:
            self.pending_badge_var.set(f"⚠  {count} pending request{'s' if count != 1 else ''}")
        else:
            self.pending_badge_var.set("✅  No pending requests")

    def _show_tab(self, key: str):
        for k, btn in self._tab_btns.items():
            btn.configure(
                fg_color=ACCENT if k == key else BG_CARD_ALT,
                text_color="white" if k == key else TEXT_PRIMARY,
            )
        for child in self._content.winfo_children():
            child.destroy()

        status_map = {"pending": "pending", "approved": "approved",
                      "rejected": "rejected", "all": None}
        RequestsTable(
            self._content, self.user,
            status_filter=status_map[key],
            on_refresh=self._update_pending_count,
        ).pack(fill="both", expand=True)


# ─────────────────────────────────────────────────────────────
#  Requests Table (reused for all tabs)
# ─────────────────────────────────────────────────────────────

class RequestsTable(ctk.CTkFrame):
    def __init__(self, master, user: dict, status_filter, on_refresh=None):
        super().__init__(master, fg_color="transparent")
        self.user          = user
        self.status_filter = status_filter   # None = all
        self.on_refresh    = on_refresh
        self._build()
        self._load()

    def _build(self):
        # Search bar
        fbar = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=10,
                             border_width=1, border_color=BORDER)
        fbar.pack(fill="x", pady=(0, 8))
        inner = ctk.CTkFrame(fbar, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=8)

        self.search_var = ctk.StringVar()
        self.search_var.trace("w", lambda *_: self._load())
        ctk.CTkEntry(
            inner, textvariable=self.search_var,
            placeholder_text="🔍  Search product or request type...",
            height=36, fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12), corner_radius=8,
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            inner, text="🔄 Refresh", height=36, width=100,
            fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY, corner_radius=8,
            font=ctk.CTkFont(size=12), command=self._load,
        ).pack(side="right")

        # Table
        card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14,
                             border_width=1, border_color=BORDER)
        card.pack(fill="both", expand=True)

        cols = ("req_id", "type", "product", "old_qty", "req_qty",
                "diff", "reason", "requested_by", "date", "status")
        self.tree = ttk.Treeview(card, columns=cols, show="headings", height=12)

        hdrs = {
            "req_id": "ID", "type": "Type", "product": "Product",
            "old_qty": "Old Qty", "req_qty": "New Qty", "diff": "Change",
            "reason": "Reason", "requested_by": "Requested By",
            "date": "Date", "status": "Status",
        }
        widths = {
            "req_id": 50, "type": 120, "product": 160,
            "old_qty": 70, "req_qty": 70, "diff": 80,
            "reason": 160, "requested_by": 110,
            "date": 130, "status": 90,
        }
        for col in cols:
            self.tree.heading(col, text=hdrs[col])
            self.tree.column(col, width=widths[col],
                              anchor="center" if col in ("req_id", "type") else "e" if col in ("old_qty", "req_qty", "diff") else "w")

        sb = ttk.Scrollbar(card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        style_treeview(self.tree)
        self.tree.tag_configure("pending",  foreground="#B88B2E", background="#FFF8E0")
        self.tree.tag_configure("approved", foreground="#4A7C59", background="#E6F2EA")
        self.tree.tag_configure("rejected", foreground="#A94040", background="#F5E0E0")
        self.tree.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        sb.pack(side="right", fill="y", pady=6)

        # Action buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", pady=8)

        ctk.CTkButton(
            btn_row, text="✅  Approve Selected", height=38, width=180,
            fg_color=SUCCESS, hover_color=SUCCESS_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=8, command=self._approve_selected,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_row, text="❌  Reject Selected", height=38, width=180,
            fg_color=DANGER, hover_color=DANGER_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=8, command=self._reject_selected,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_row, text="🔍  View Details", height=38, width=150,
            fg_color=BG_CARD, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY, corner_radius=8,
            font=ctk.CTkFont(size=12),
            command=self._view_details,
        ).pack(side="left")

    def _load(self):
        q = f"%{self.search_var.get()}%"
        conn  = get_connection()
        query = """
            SELECT r.id, r.request_type, r.product_name,
                   r.old_quantity, r.requested_quantity, r.quantity_difference,
                   r.reason, r.status, r.request_date, r.rejection_reason,
                   u.full_name AS requested_by,
                   ab.full_name AS approved_by_name
            FROM stock_update_requests r
            JOIN users u ON u.id = r.requested_by
            LEFT JOIN users ab ON ab.id = r.approved_by
            WHERE (r.product_name LIKE ? OR r.request_type LIKE ?)
        """
        params: list = [q, q]
        if self.status_filter:
            query += " AND r.status = ?"
            params.append(self.status_filter)
        query += " ORDER BY r.request_date DESC"

        rows = conn.execute(query, params).fetchall()
        conn.close()

        for c in self.tree.get_children():
            self.tree.delete(c)
        for row in rows:
            diff = row["quantity_difference"]
            diff_str = f"+{diff}" if diff > 0 else str(diff)
            type_label = {
                "stock_in": "📥 Stock In",
                "stock_adjustment": "🔧 Adjustment",
                "inventory_update": "📦 Inventory",
            }.get(row["request_type"], row["request_type"])

            self.tree.insert(
                "", "end", iid=str(row["id"]),
                tags=(row["status"],),
                values=(
                    row["id"], type_label, row["product_name"],
                    row["old_quantity"], row["requested_quantity"], diff_str,
                    (row["reason"] or "")[:35],
                    row["requested_by"], row["request_date"],
                    row["status"].capitalize(),
                ),
            )

    def _get_selected_request(self):
        sel = self.tree.selection()
        if not sel:
            msg_warning(self, "Select", "Please select a request first.")
            return None
        req_id = int(sel[0])
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM stock_update_requests WHERE id=?", (req_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def _approve_selected(self):
        if self.user["role"] != "owner":
            msg_warning(self, "Access Denied", "Only the Owner can approve requests.")
            return

        req = self._get_selected_request()
        if not req:
            return
        if req["status"] != "pending":
            msg_warning(self, "Already Processed",
                        f"This request is already '{req['status'].capitalize()}'.")
            return

        if not msg_question(
            self, "Confirm Approval",
            f"Approve this request?\n\n"
            f"Product: {req['product_name']}\n"
            f"Change: {req['old_quantity']}  →  {req['requested_quantity']}\n\n"
            "This will immediately update the inventory quantity."
        ):
            return

        try:
            conn = get_connection()
            # Update the actual product stock
            conn.execute(
                """UPDATE products SET current_stock=?, updated_at=datetime('now','localtime')
                   WHERE id=?""",
                (req["requested_quantity"], req["product_id"]),
            )

            # If this is a stock_in request, also update cost/selling prices
            # from the delivery line item so Inventory reflects latest prices
            if req["request_type"] == "stock_in" and req.get("stock_in_id"):
                item_row = conn.execute(
                    """SELECT cost_price, selling_price FROM stock_in_items
                       WHERE stock_in_id=? AND product_id=? LIMIT 1""",
                    (req["stock_in_id"], req["product_id"]),
                ).fetchone()
                if item_row:
                    conn.execute(
                        """UPDATE products SET cost_price=?, selling_price=?,
                                updated_at=datetime('now','localtime')
                           WHERE id=?""",
                        (item_row["cost_price"], item_row["selling_price"],
                         req["product_id"]),
                    )

            # If this is a stock_in request, also mark the parent delivery approved
            # (only when all items of that delivery are approved)
            if req["request_type"] == "stock_in" and req.get("stock_in_id"):
                pending_count = conn.execute(
                    """SELECT COUNT(*) FROM stock_update_requests
                       WHERE stock_in_id=? AND status='pending' AND id != ?""",
                    (req["stock_in_id"], req["id"]),
                ).fetchone()[0]
                if pending_count == 0:
                    conn.execute(
                        "UPDATE stock_in SET status='approved' WHERE id=?",
                        (req["stock_in_id"],),
                    )

            # Mark request approved
            conn.execute(
                """UPDATE stock_update_requests
                   SET status='approved', approved_by=?, approval_date=datetime('now','localtime')
                   WHERE id=?""",
                (self.user["id"], req["id"]),
            )
            # Log
            conn.execute(
                """INSERT INTO approval_logs
                   (request_id, action, action_by, old_quantity, new_quantity, notes)
                   VALUES (?, 'approved', ?, ?, ?, ?)""",
                (req["id"], self.user["id"],
                 req["old_quantity"], req["requested_quantity"],
                 f"Approved by {self.user['full_name']}"),
            )
            conn.commit()
            conn.close()

            log_audit(self.user["id"], self.user["username"], "Stock", "APPROVE_STOCK",
                      record_id=req["id"],
                      new_value={"product": req["product_name"],
                                 "qty": req["requested_quantity"]})
            msg_success(self, "Approved!",
                        f"'{req['product_name']}' inventory updated to {req['requested_quantity']}.")
            self._load()
            if self.on_refresh:
                self.on_refresh()

        except Exception as exc:
            msg_error(self, "Error", str(exc))

    def _reject_selected(self):
        if self.user["role"] != "owner":
            msg_warning(self, "Access Denied", "Only the Owner can reject requests.")
            return

        req = self._get_selected_request()
        if not req:
            return
        if req["status"] != "pending":
            msg_warning(self, "Already Processed",
                        f"This request is already '{req['status'].capitalize()}'.")
            return

        RejectionReasonDialog(self, req, self.user, self._on_reject_done)

    def _on_reject_done(self, req_id, reason):
        try:
            req = None
            conn = get_connection()
            row = conn.execute("SELECT * FROM stock_update_requests WHERE id=?", (req_id,)).fetchone()
            if row:
                req = dict(row)
            conn.execute(
                """UPDATE stock_update_requests
                   SET status='rejected', approved_by=?,
                       approval_date=datetime('now','localtime'),
                       rejection_reason=?
                   WHERE id=?""",
                (self.user["id"], reason, req_id),
            )
            if req and req.get("request_type") == "stock_in" and req.get("stock_in_id"):
                conn.execute(
                    "UPDATE stock_in SET status='rejected' WHERE id=?",
                    (req["stock_in_id"],),
                )
            conn.execute(
                """INSERT INTO approval_logs
                   (request_id, action, action_by, old_quantity, new_quantity, notes)
                   VALUES (?, 'rejected', ?, ?, ?, ?)""",
                (req_id, self.user["id"],
                 req["old_quantity"] if req else None,
                 req["old_quantity"] if req else None,
                 f"Rejected — {reason}"),
            )
            conn.commit()
            conn.close()
            log_audit(self.user["id"], self.user["username"], "Stock", "REJECT_STOCK",
                      record_id=req_id,
                      new_value={"product": req["product_name"] if req else req_id,
                                 "reason": reason})
            msg_success(self, "Rejected", "Request has been rejected and archived.")
            self._load()
            if self.on_refresh:
                self.on_refresh()
        except Exception as exc:
            msg_error(self, "Error", str(exc))

    def _view_details(self):
        req = self._get_selected_request()
        if req:
            RequestDetailDialog(self, req)


# ─────────────────────────────────────────────────────────────
#  Rejection Reason Dialog
# ─────────────────────────────────────────────────────────────

class RejectionReasonDialog(ctk.CTkToplevel):
    def __init__(self, master, req: dict, user: dict, callback):
        super().__init__(master)
        self.req      = req
        self.user     = user
        self.callback = callback
        style_dialog(self, "Reject Request", 440, 340)
        self._build()

    def _build(self):
        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=20, pady=16)

        ctk.CTkLabel(form, text="Reject Request",
                      font=ctk.CTkFont(size=17, weight="bold"),
                      text_color=DANGER).pack(anchor="w", pady=(0, 6))
        ctk.CTkLabel(
            form,
            text=f"Product: {self.req['product_name']}\n"
                 f"Change: {self.req['old_quantity']} → {self.req['requested_quantity']}",
            font=ctk.CTkFont(size=12), text_color=TEXT_SECONDARY,
        ).pack(anchor="w", pady=(0, 12))

        ctk.CTkLabel(form, text="Rejection Reason *", anchor="w",
                      font=ctk.CTkFont(size=12), text_color=TEXT_SECONDARY).pack(fill="x", pady=(0, 3))
        self.reason_box = ctk.CTkTextbox(
            form, height=100,
            fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, corner_radius=8,
            font=ctk.CTkFont(size=12),
        )
        self.reason_box.pack(fill="x")

        ctk.CTkButton(
            form, text="Confirm Rejection", height=40,
            fg_color=DANGER, hover_color=DANGER_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=8, command=self._confirm,
        ).pack(fill="x", pady=(14, 0))

    def _confirm(self):
        reason = self.reason_box.get("1.0", "end").strip()
        if not reason:
            msg_warning(self, "Required", "Please enter a rejection reason.")
            return
        self.destroy()
        self.callback(self.req["id"], reason)


# ─────────────────────────────────────────────────────────────
#  Request Detail Dialog
# ─────────────────────────────────────────────────────────────

class RequestDetailDialog(ctk.CTkToplevel):
    def __init__(self, master, req: dict):
        super().__init__(master)
        self.req = req
        style_dialog(self, f"Request Detail — #{req['id']}", 520, 520)
        self._build()

    def _build(self):
        form = ctk.CTkScrollableFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=20, pady=16)

        ctk.CTkLabel(form, text=f"Request #{self.req['id']} — Details",
                      font=ctk.CTkFont(size=17, weight="bold"),
                      text_color=TEXT_PRIMARY).pack(anchor="w", pady=(0, 12))

        status_colors = {"pending": WARNING, "approved": SUCCESS, "rejected": DANGER}
        status = self.req["status"]

        fields = [
            ("Request Type",    self.req["request_type"].replace("_", " ").title()),
            ("Product",         self.req["product_name"]),
            ("Old Quantity",    str(self.req["old_quantity"])),
            ("Requested Qty",   str(self.req["requested_quantity"])),
            ("Change",          f"{self.req['quantity_difference']:+d}"),
            ("Reason",          self.req.get("reason") or "—"),
            ("Status",          status.capitalize()),
            ("Request Date",    self.req.get("request_date") or "—"),
            ("Approval Date",   self.req.get("approval_date") or "—"),
            ("Rejection Reason", self.req.get("rejection_reason") or "—"),
        ]

        # Fetch user names
        conn = get_connection()
        req_by = conn.execute("SELECT full_name FROM users WHERE id=?",
                               (self.req["requested_by"],)).fetchone()
        app_by = conn.execute("SELECT full_name FROM users WHERE id=?",
                               (self.req.get("approved_by"),)).fetchone() if self.req.get("approved_by") else None

        # Fetch audit log
        logs = conn.execute(
            """SELECT al.action, al.created_at, u.full_name,
                      al.old_quantity, al.new_quantity, al.notes
               FROM approval_logs al
               JOIN users u ON u.id = al.action_by
               WHERE al.request_id = ?
               ORDER BY al.created_at""",
            (self.req["id"],)
        ).fetchall()
        conn.close()

        fields.insert(7, ("Requested By", req_by["full_name"] if req_by else "—"))
        fields.insert(9, ("Approved/Rejected By", app_by["full_name"] if app_by else "—"))

        for label, value in fields:
            row_f = ctk.CTkFrame(form, fg_color=BG_CARD_ALT, corner_radius=8)
            row_f.pack(fill="x", pady=2)
            ctk.CTkLabel(row_f, text=label + ":",
                          font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
                          width=160, anchor="w").pack(side="left", padx=10, pady=6)
            color = status_colors.get(status, TEXT_PRIMARY) if label == "Status" else TEXT_PRIMARY
            ctk.CTkLabel(row_f, text=value,
                          font=ctk.CTkFont(size=11, weight="bold"),
                          text_color=color, anchor="w", wraplength=280).pack(side="left", pady=6)

        if logs:
            ctk.CTkLabel(form, text="Audit Trail",
                          font=ctk.CTkFont(size=13, weight="bold"),
                          text_color=TEXT_PRIMARY).pack(anchor="w", pady=(14, 6))
            for log in logs:
                action_colors = {"submitted": ACCENT, "approved": SUCCESS, "rejected": DANGER}
                color = action_colors.get(log["action"], TEXT_MUTED)
                log_f = ctk.CTkFrame(form, fg_color=BG_CARD, corner_radius=8,
                                      border_width=1, border_color=BORDER)
                log_f.pack(fill="x", pady=2)
                ctk.CTkLabel(
                    log_f,
                    text=f"[{log['created_at']}]  {log['action'].upper()}  by {log['full_name']}",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color=color, anchor="w",
                ).pack(anchor="w", padx=10, pady=(5, 0))
                if log["notes"]:
                    ctk.CTkLabel(log_f, text=log["notes"],
                                  font=ctk.CTkFont(size=10),
                                  text_color=TEXT_MUTED, anchor="w").pack(anchor="w", padx=10, pady=(0, 5))