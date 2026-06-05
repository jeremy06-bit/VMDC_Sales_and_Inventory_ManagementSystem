import customtkinter as ctk
from ui.theme import (
    BG_DARK, BG_CARD, BG_INPUT, BORDER, ACCENT, ACCENT_HOVER, ACCENT_LIGHT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, SIDEBAR_BG,
    msg_warning, msg_success, msg_error,
    create_dialog_entry, create_dialog_button, style_dialog,
)
from security import (
    authenticate, validate_password_policy, hash_password,
    check_force_password_change, set_force_password_change, log_audit,
)
from database import get_connection


class LoginWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self.title("VMDC Motor Parts - Login")
        self.geometry("480x600")
        self.resizable(False, False)
        self.configure(fg_color=BG_DARK)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (480 // 2)
        y = (self.winfo_screenheight() // 2) - (600 // 2)
        self.geometry(f"+{x}+{y}")

        self._build_ui()

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color=SIDEBAR_BG, corner_radius=0, height=150)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="⚙", font=ctk.CTkFont(size=40),
                     text_color=ACCENT).pack(pady=(30, 0))
        ctk.CTkLabel(header, text="VMDC MOTOR PARTS",
                     font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(pady=(6, 0))
        ctk.CTkLabel(header, text="Sales & Inventory Management System",
                     font=ctk.CTkFont(family="Segoe UI", size=12),
                     text_color=TEXT_SECONDARY).pack(pady=(2, 0))

        ctk.CTkFrame(self, fg_color=ACCENT, height=3, corner_radius=0).pack(fill="x")

        card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=16,
                             border_width=1, border_color=BORDER)
        card.pack(padx=40, pady=30, fill="both", expand=True)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=32, pady=28)

        ctk.CTkLabel(inner, text="Sign In",
                     font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(inner, text="Enter your credentials to continue",
                     font=ctk.CTkFont(family="Segoe UI", size=12),
                     text_color=TEXT_MUTED).pack(anchor="w", pady=(0, 20))

        ctk.CTkLabel(inner, text="Username", anchor="w",
                     font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                     text_color=TEXT_SECONDARY).pack(fill="x", pady=(0, 4))
        self.username_entry = ctk.CTkEntry(
            inner, height=44, placeholder_text="Enter username",
            fg_color=BG_INPUT, border_color=BORDER, text_color=TEXT_PRIMARY,
            placeholder_text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=13), corner_radius=10,
        )
        self.username_entry.pack(fill="x", pady=(0, 14))

        ctk.CTkLabel(inner, text="Password", anchor="w",
                     font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                     text_color=TEXT_SECONDARY).pack(fill="x", pady=(0, 4))
        self.password_entry = ctk.CTkEntry(
            inner, height=44, placeholder_text="Enter password", show="•",
            fg_color=BG_INPUT, border_color=BORDER, text_color=TEXT_PRIMARY,
            placeholder_text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=13), corner_radius=10,
        )
        self.password_entry.pack(fill="x", pady=(0, 10))

        self.error_label = ctk.CTkLabel(
            inner, text="", text_color="#ef4444",
            font=ctk.CTkFont(family="Segoe UI", size=12), wraplength=360,
        )
        self.error_label.pack(pady=(0, 6))

        ctk.CTkButton(
            inner, text="Sign In", height=48,
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=12,
            command=self.do_login
        ).pack(fill="x")

        ctk.CTkLabel(self, text="© 2025 VMDC Motor Parts",
                     font=ctk.CTkFont(family="Segoe UI", size=10),
                     text_color=TEXT_MUTED).pack(pady=(0, 12))

        self.bind("<Return>", lambda e: self.do_login())
        self.username_entry.focus()

    def do_login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get()

        if not username or not password:
            self.error_label.configure(text="Please enter username and password.")
            return

        user, error = authenticate(username, password)

        if error:
            self.error_label.configure(text=error)
            self.password_entry.delete(0, "end")
            return

        self.error_label.configure(text="")

        # Check if user must change password
        if check_force_password_change(user):
            self._prompt_force_change(user)
            return

        self.open_dashboard(user)

    def _prompt_force_change(self, user):
        """Show forced password change dialog."""
        dialog = ctk.CTkToplevel(self)
        style_dialog(dialog, "Password Change Required", 420, 400)

        inner = ctk.CTkFrame(dialog, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=28, pady=18)

        ctk.CTkLabel(inner, text="Change Password Required",
                     font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(inner,
                     text="Your account requires a password change before continuing.\n"
                          "Password must be at least 8 characters with uppercase,\n"
                          "lowercase, number and special character (e.g. VMDC@2026).",
                     font=ctk.CTkFont(family="Segoe UI", size=11),
                     text_color=TEXT_SECONDARY, wraplength=360, justify="left",
                     ).pack(anchor="w", pady=(0, 12))

        pw1 = create_dialog_entry(inner, "New Password *", "", placeholder="e.g. VMDC@2026",
                                   show="•")
        pw2 = create_dialog_entry(inner, "Confirm Password *", "", placeholder="Repeat password",
                                   show="•")

        err_lbl = ctk.CTkLabel(inner, text="", text_color="#ef4444",
                               font=ctk.CTkFont(family="Segoe UI", size=11), wraplength=340)
        err_lbl.pack(pady=(4, 0))

        def _do_change():
            p1 = pw1.get()
            p2 = pw2.get()
            if p1 != p2:
                err_lbl.configure(text="Passwords do not match.")
                return
            try:
                validate_password_policy(p1)
            except ValueError as e:
                err_lbl.configure(text=str(e))
                return
            hashed = hash_password(p1)
            conn = get_connection()
            conn.execute("UPDATE users SET password=?, force_pw_change=0 WHERE id=?",
                         (hashed, user["id"]))
            conn.commit()
            conn.close()
            log_audit(user["id"], user["username"], "Users", "PASSWORD_FORCE_CHANGE",
                      record_id=user["id"])
            dialog.destroy()
            msg_success(self, "Password Updated", "Password changed. Logging in now.")
            # Reload user
            conn = get_connection()
            updated_user = dict(conn.execute("SELECT * FROM users WHERE id=?",
                                             (user["id"],)).fetchone())
            conn.close()
            self.open_dashboard(updated_user)

        create_dialog_button(inner, "💾  Set New Password", _do_change).pack(fill="x", pady=(14, 0))
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)  # prevent closing
        dialog.grab_set()

    def open_dashboard(self, user):
        self.destroy()
        from ui.dashboard_window import DashboardWindow
        dashboard = DashboardWindow(self.master, user)
        dashboard.mainloop()

    def on_close(self):
        self.master.destroy()