import customtkinter as ctk
from tkinter import ttk
from database import get_connection
from security import (
    hash_password, validate_password_policy, log_audit, require_role,
)
from ui.theme import (
    BG_DARK, BG_CARD, BG_CARD_ALT, BG_INPUT, BG_HOVER, BORDER,
    ACCENT, ACCENT_HOVER, ACCENT_SUBTLE, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    SUCCESS, SUCCESS_HOVER, DANGER, DANGER_HOVER, WARNING,
    style_treeview, insert_with_stripes, Paginator,
    create_dialog_entry, create_dialog_button, style_dialog, create_option_menu,
    msg_info, msg_warning, msg_error, msg_success, msg_question,
)


# ──────────────────────────────────────────────
#  MAIN FRAME
# ──────────────────────────────────────────────

class UsersFrame(ctk.CTkFrame):
    def __init__(self, master, user: dict):
        super().__init__(master, fg_color="transparent")
        self.user = user
        self._all_rows = []
        self._build_ui()
        self._load()

    # ── UI construction ───────────────────────

    def _build_ui(self):
        # Header row
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            header, text="User Management",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        ctk.CTkButton(
            header, text="＋  Add User", height=38,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            corner_radius=10, command=self._add,
        ).pack(side="right")

        # ── Stats bar ────────────────────────
        self._stats_bar = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=12,
                                       border_width=1, border_color=BORDER)
        self._stats_bar.pack(fill="x", pady=(0, 12))

        self._lbl_total  = self._stat_pill(self._stats_bar, "👤  Total Users", "—")
        self._lbl_owners = self._stat_pill(self._stats_bar, "🔑  Owners", "—")
        self._lbl_cash   = self._stat_pill(self._stats_bar, "🧾  Cashiers", "—")

        # ── Search bar ───────────────────────
        search_row = ctk.CTkFrame(self, fg_color="transparent")
        search_row.pack(fill="x", pady=(0, 10))

        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filter())

        search_entry = ctk.CTkEntry(
            search_row, textvariable=self._search_var,
            placeholder_text="🔍   Search by name, username or role…",
            height=38, corner_radius=10,
            fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        search_entry.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            search_row, text="✕  Clear", width=90, height=38,
            fg_color=BG_CARD, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_MUTED, corner_radius=10,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=lambda: self._search_var.set(""),
        ).pack(side="left", padx=(8, 0))

        # ── Table ────────────────────────────
        table_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14,
                                   border_width=1, border_color=BORDER)
        table_frame.pack(fill="both", expand=True)

        cols = ("full_name", "username", "role", "created_at")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=16)

        hdrs   = {"full_name": "Full Name", "username": "Username",
                  "role": "Role", "created_at": "Member Since"}
        widths = {"full_name": 220, "username": 180, "role": 120, "created_at": 150}

        for col in cols:
            self.tree.heading(col, text=hdrs[col],
                              command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=widths[col], minwidth=80)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        style_treeview(self.tree)

        self.tree.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        scrollbar.pack(side="right", fill="y", pady=6)

        self._pager = Paginator(table_frame, self.tree, page_size=20,
                                render_fn=self._render_page, bar_parent=self)

        # Double-click to edit
        self.tree.bind("<Double-1>", lambda e: self._edit())

        # ── Action buttons ───────────────────
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.pack(fill="x", pady=(8, 0))

        self._btn_edit = ctk.CTkButton(
            action_frame, text="✏   Edit User", height=36,
            fg_color=BG_CARD, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY, corner_radius=8,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self._edit,
        )
        self._btn_edit.pack(side="left", padx=(0, 8))

        self._btn_del = ctk.CTkButton(
            action_frame, text="🗑   Delete User", height=36,
            fg_color=BG_CARD, hover_color="#F0DCDC",
            border_width=1, border_color=BORDER,
            text_color=DANGER, corner_radius=8,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self._delete,
        )
        self._btn_del.pack(side="left")

        self._lbl_hint = ctk.CTkLabel(
            action_frame, text="Double-click a row to edit",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
        )
        self._lbl_hint.pack(side="right")

    # ── Stat pill helper ─────────────────────

    def _stat_pill(self, parent, label: str, value: str):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(side="left", padx=20, pady=10)
        ctk.CTkLabel(frame, text=label,
                     font=ctk.CTkFont(family="Segoe UI", size=11),
                     text_color=TEXT_MUTED).pack(anchor="w")
        lbl = ctk.CTkLabel(frame, text=value,
                            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
                            text_color=TEXT_PRIMARY)
        lbl.pack(anchor="w")
        return lbl

    # ── Data loading ─────────────────────────

    def _load(self):
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM users ORDER BY role, full_name"
        ).fetchall()
        conn.close()
        self._all_rows = list(rows)
        self._update_stats()
        self._apply_filter()

    def _update_stats(self):
        total   = len(self._all_rows)
        owners  = sum(1 for r in self._all_rows if r["role"] == "owner")
        cashiers = total - owners
        self._lbl_total.configure(text=str(total))
        self._lbl_owners.configure(text=str(owners))
        self._lbl_cash.configure(text=str(cashiers))

    def _apply_filter(self):
        q = self._search_var.get().strip().lower()
        if q:
            filtered = [
                r for r in self._all_rows
                if q in r["full_name"].lower()
                or q in r["username"].lower()
                or q in r["role"].lower()
            ]
        else:
            filtered = self._all_rows
        self._pager.set_data(filtered)

    def _render_page(self, rows):
        for row in rows:
            role_display = "👑  Owner" if row["role"] == "owner" else "🧾  Cashier"
            insert_with_stripes(self.tree, (
                row["full_name"],
                row["username"],
                role_display,
                row["created_at"][:10],
            ), iid=row["id"])

    # ── Sorting ──────────────────────────────

    _sort_asc = True
    _sort_col = None

    def _sort_by(self, col):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True

        key_map = {
            "full_name": lambda r: r["full_name"].lower(),
            "username":  lambda r: r["username"].lower(),
            "role":      lambda r: r["role"],
            "created_at": lambda r: r["created_at"],
        }
        self._all_rows.sort(key=key_map[col], reverse=not self._sort_asc)
        self._apply_filter()

    # ── Actions ──────────────────────────────

    def _add(self):
        try:
            require_role(self.user, "owner", "create users")
        except PermissionError as e:
            msg_error(self, "Access Denied", str(e))
            return
        UserDialog(self, current_user=self.user, edit_user=None, callback=self._load)

    def _edit(self):
        sel = self.tree.selection()
        if not sel:
            msg_warning(self, "No Selection", "Please select a user to edit.")
            return
        conn = get_connection()
        user = conn.execute("SELECT * FROM users WHERE id=?", (int(sel[0]),)).fetchone()
        conn.close()
        if user:
            UserDialog(self, current_user=self.user, edit_user=dict(user), callback=self._load)

    def _delete(self):
        try:
            require_role(self.user, "owner", "delete users")
        except PermissionError as e:
            msg_error(self, "Access Denied", str(e))
            return
        sel = self.tree.selection()
        if not sel:
            msg_warning(self, "No Selection", "Please select a user to delete.")
            return
        uid = int(sel[0])

        # Prevent deleting yourself
        if uid == self.user.get("id"):
            msg_warning(self, "Not Allowed", "You cannot delete your own account.")
            return

        conn = get_connection()
        target = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        conn.close()
        if not target:
            return

        # Safety: prevent deleting the last owner
        if target["role"] == "owner":
            conn = get_connection()
            owner_count = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role='owner'"
            ).fetchone()[0]
            conn.close()
            if owner_count <= 1:
                msg_warning(self, "Not Allowed",
                            "Cannot delete the only owner account.\n"
                            "Promote another user to Owner first.")
                return

        confirmed = msg_question(
            self, "Confirm Delete",
            f"Delete user «{target['full_name']}» (@{target['username']})?\n"
            "This action cannot be undone."
        )
        if not confirmed:
            return

        try:
            conn = get_connection()
            conn.execute("DELETE FROM users WHERE id=?", (uid,))
            conn.commit()
            conn.close()
            log_audit(self.user["id"], self.user["username"], "Users", "DELETE_USER",
                      record_id=uid, old_value={"username": target["username"], "role": target["role"]})
            msg_success(self, "Deleted", f"User «{target['full_name']}» has been removed.")
            self._load()
        except Exception as e:
            msg_error(self, "Error", f"Could not delete user: {e}")


# ──────────────────────────────────────────────
#  DIALOG
# ──────────────────────────────────────────────

class UserDialog(ctk.CTkToplevel):
    def __init__(self, master, current_user: dict, edit_user, callback):
        super().__init__(master)
        self.current_user = current_user   # logged-in user
        self.edit_user    = edit_user       # user being edited (None = new)
        self.callback     = callback
        title = "Add User" if not edit_user else "Edit User"
        style_dialog(self, title, 440, 520)
        self._build()

    def _build(self):
        p = self.edit_user or {}
        is_edit = bool(self.edit_user)
        is_self = is_edit and (self.edit_user.get("id") == self.current_user.get("id"))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=28, pady=18)

        # Title
        ctk.CTkLabel(
            form,
            text="Edit User" if is_edit else "Add New User",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 4))

        if is_self:
            ctk.CTkLabel(
                form, text="You are editing your own account.",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=WARNING,
            ).pack(anchor="w", pady=(0, 10))
        else:
            ctk.CTkFrame(form, fg_color=BORDER, height=1).pack(fill="x", pady=(0, 14))

        # Fields
        self.full_name = create_dialog_entry(form, "Full Name *", p.get("full_name", ""),
                                             placeholder="e.g. Juan dela Cruz")
        self.username  = create_dialog_entry(form, "Username *", p.get("username", ""),
                                             placeholder="e.g. jdelacruz")

        # Password with show/hide toggle
        ctk.CTkLabel(form, text="Password *", anchor="w",
                     font=ctk.CTkFont(family="Segoe UI", size=12),
                     text_color=TEXT_SECONDARY).pack(fill="x", pady=(8, 3))

        pw_row = ctk.CTkFrame(form, fg_color="transparent")
        pw_row.pack(fill="x")
        self._show_pw = False
        self.password = ctk.CTkEntry(
            pw_row, show="•",
            fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, height=38, corner_radius=8,
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        # Never pre-fill stored password into the UI
        self.password.pack(side="left", fill="x", expand=True)

        self._eye_btn = ctk.CTkButton(
            pw_row, text="👁", width=44, height=38,
            fg_color=BG_CARD, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_MUTED, corner_radius=8,
            font=ctk.CTkFont(size=14),
            command=self._toggle_pw,
        )
        self._eye_btn.pack(side="left", padx=(6, 0))

        if is_edit:
            ctk.CTkLabel(
                form, text="Leave password unchanged to keep the existing one.",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color=TEXT_MUTED,
            ).pack(anchor="w", pady=(2, 0))

        # Role (disabled if editing own account as owner, to prevent lockout)
        ctk.CTkLabel(form, text="Role *", anchor="w",
                     font=ctk.CTkFont(family="Segoe UI", size=12),
                     text_color=TEXT_SECONDARY).pack(fill="x", pady=(10, 3))
        self.role_var = ctk.StringVar(value=p.get("role", "cashier"))
        role_menu = create_option_menu(form, values=["owner", "cashier"],
                                       variable=self.role_var)
        role_menu.pack(fill="x")

        if is_self and p.get("role") == "owner":
            role_menu.configure(state="disabled")
            ctk.CTkLabel(
                form, text="Cannot change your own role while logged in.",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color=TEXT_MUTED,
            ).pack(anchor="w", pady=(2, 0))

        # Save button
        create_dialog_button(form, "💾  Save User", self._save).pack(fill="x", pady=(20, 0))

    # ── Password toggle ──────────────────────

    def _toggle_pw(self):
        self._show_pw = not self._show_pw
        self.password.configure(show="" if self._show_pw else "•")
        self._eye_btn.configure(text="🙈" if self._show_pw else "👁")

    # ── Save ─────────────────────────────────

    def _save(self):
        full_name = self.full_name.get().strip()
        username  = self.username.get().strip()
        password  = self.password.get().strip()
        role      = self.role_var.get()

        # Role-based guard
        try:
            require_role(self.current_user, "owner", "create or edit users")
        except PermissionError as e:
            msg_error(self, "Access Denied", str(e))
            return

        if not full_name or not username:
            msg_warning(self, "Required", "Full Name and Username are required.")
            return

        if not self.edit_user and not password:
            msg_warning(self, "Required", "Password is required for new users.")
            return

        if " " in username:
            msg_warning(self, "Invalid Username", "Username must not contain spaces.")
            return

        # Password policy enforcement (only when a new password is given)
        if password:
            try:
                validate_password_policy(password)
            except ValueError as e:
                msg_warning(self, "Weak Password", str(e))
                return
            hashed_pw = hash_password(password)
        else:
            hashed_pw = None

        conn = get_connection()
        try:
            if self.edit_user:
                old = dict(conn.execute("SELECT * FROM users WHERE id=?",
                                        (self.edit_user["id"],)).fetchone())
                if hashed_pw:
                    conn.execute(
                        "UPDATE users SET full_name=?, username=?, password=?, role=? WHERE id=?",
                        (full_name, username, hashed_pw, role, self.edit_user["id"]),
                    )
                else:
                    conn.execute(
                        "UPDATE users SET full_name=?, username=?, role=? WHERE id=?",
                        (full_name, username, role, self.edit_user["id"]),
                    )
                conn.commit()
                conn.close()
                # Audit after connection is closed to avoid database lock
                action = "EDIT_USER"
                new_val = {"full_name": full_name, "username": username, "role": role}
                old_val = {"full_name": old["full_name"], "username": old["username"], "role": old["role"]}
                if hashed_pw:
                    new_val["password"] = "***changed***"
                log_audit(self.current_user["id"], self.current_user["username"], "Users",
                          action, record_id=self.edit_user["id"],
                          old_value=old_val, new_value=new_val)
            else:
                conn.execute(
                    "INSERT INTO users (full_name, username, password, role) VALUES (?,?,?,?)",
                    (full_name, username, hashed_pw, role),
                )
                new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                conn.commit()
                conn.close()
                # Audit after connection is closed to avoid database lock
                log_audit(self.current_user["id"], self.current_user["username"], "Users",
                          "CREATE_USER", record_id=new_id,
                          new_value={"full_name": full_name, "username": username, "role": role})
            msg_success(self, "Saved", f"User «{full_name}» saved successfully.")
            self.callback()
            self.destroy()
        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            if "UNIQUE constraint" in str(e):
                msg_error(self, "Duplicate Username",
                          f"Username «{username}» is already taken.\nChoose a different one.")
            else:
                msg_error(self, "Error", f"Could not save user: {e}")