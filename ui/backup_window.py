import customtkinter as ctk
from tkinter import filedialog
from database import DB_PATH
from security import (
    create_encrypted_backup, restore_encrypted_backup,
    require_role, log_audit,
)
from ui.theme import (
    BG_DARK, BG_CARD, BG_CARD_ALT, BG_INPUT, BG_HOVER, BORDER,
    ACCENT, ACCENT_HOVER, ACCENT_LIGHT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    SUCCESS, SUCCESS_HOVER,
    msg_info, msg_warning, msg_error, msg_success, msg_question
)
import os
import shutil
import datetime


class BackupFrame(ctk.CTkFrame):
    def __init__(self, master, user: dict):
        super().__init__(master, fg_color="transparent")
        self.user = user
        self._build_ui()
        self._load_backups()

    def _build_ui(self):
        ctk.CTkLabel(
            self, text="Database Backup",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=TEXT_PRIMARY
        ).pack(anchor="w", pady=(0, 14))

        # Info card
        info_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14,
                                   border_width=1, border_color=BORDER)
        info_frame.pack(fill="x", pady=(0, 14))

        ctk.CTkLabel(
            info_frame,
            text="Backups are encrypted. A .enc (data) and .key (decryption key) file are saved together.\n"
                 "Keep the .key file safe — without it the backup cannot be restored.",
            text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            wraplength=620, justify="left",
        ).pack(padx=18, pady=(16, 6))

        db_size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
        ctk.CTkLabel(
            info_frame,
            text=f"📁  {DB_PATH}   |   Size: {db_size/1024:.1f} KB",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED
        ).pack(padx=18, pady=(0, 16))

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", pady=8)

        ctk.CTkButton(
            btn_frame, text="📦  Backup Now (Encrypted)", height=46,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            corner_radius=10, command=self._backup_now
        ).pack(side="left", padx=(0, 12))

        ctk.CTkButton(
            btn_frame, text="♻  Restore from Encrypted Backup", height=46,
            fg_color=BG_CARD, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            corner_radius=10, command=self._restore
        ).pack(side="left")

        # Recent backups list
        ctk.CTkLabel(
            self, text="Recent Backups",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=TEXT_PRIMARY
        ).pack(anchor="w", pady=(14, 8))

        self.backup_list_frame = ctk.CTkScrollableFrame(
            self, fg_color=BG_CARD, corner_radius=14,
            border_width=1, border_color=BORDER
        )
        self.backup_list_frame.pack(fill="both", expand=True)

    def _backup_dir(self):
        d = os.path.normpath(os.path.join(os.path.dirname(DB_PATH), "..", "backups"))
        os.makedirs(d, exist_ok=True)
        return d

    def _load_backups(self):
        for widget in self.backup_list_frame.winfo_children():
            widget.destroy()

        backup_dir = self._backup_dir()
        backups = sorted(
            [f for f in os.listdir(backup_dir) if f.endswith(".enc")],
            reverse=True
        )

        if not backups:
            ctk.CTkLabel(
                self.backup_list_frame,
                text="No encrypted backups found. Create your first backup above.",
                text_color=TEXT_MUTED,
                font=ctk.CTkFont(family="Segoe UI", size=13)
            ).pack(pady=24)
            return

        for fname in backups[:20]:
            fpath = os.path.join(backup_dir, fname)
            size  = os.path.getsize(fpath) / 1024
            key_exists = os.path.exists(fpath + ".key")
            row = ctk.CTkFrame(self.backup_list_frame, fg_color=BG_CARD_ALT, corner_radius=8)
            row.pack(fill="x", padx=8, pady=3)
            ctk.CTkLabel(
                row, text=f"🔒  {fname}",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=TEXT_PRIMARY
            ).pack(side="left", padx=12, pady=8)
            ctk.CTkLabel(
                row,
                text=f"{size:.1f} KB  {'🔑 Key found' if key_exists else '⚠ Key missing'}",
                text_color=TEXT_MUTED if key_exists else "#ef4444",
                font=ctk.CTkFont(family="Segoe UI", size=11)
            ).pack(side="right", padx=16, pady=8)

    def _backup_now(self):
        try:
            require_role(self.user, "owner", "create backups")
        except PermissionError as e:
            msg_error(self, "Access Denied", str(e))
            return

        timestamp    = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"vmdc_backup_{timestamp}.enc"

        dest = filedialog.asksaveasfilename(
            defaultextension=".enc",
            filetypes=[("Encrypted backup", "*.enc")],
            initialfile=default_name,
            title="Choose backup location"
        )
        if not dest:
            return

        try:
            key_path = create_encrypted_backup(DB_PATH, dest)

            # Also save to local backups folder
            local_enc = os.path.join(self._backup_dir(), default_name)
            local_key = local_enc + ".key"
            import shutil as _sh
            _sh.copy2(dest, local_enc)
            _sh.copy2(key_path, local_key)

            log_audit(self.user["id"], self.user["username"], "Backup", "CREATE_BACKUP",
                      new_value={"file": dest})
            msg_info(self, "Backup Complete",
                     f"Encrypted backup saved to:\n{dest}\n\n"
                     f"Encryption key saved to:\n{key_path}\n\n"
                     f"⚠ Keep the .key file safe — it is required to restore this backup.")
            self._load_backups()
        except Exception as e:
            msg_error(self, "Backup Failed", str(e))

    def _restore(self):
        try:
            require_role(self.user, "owner", "restore backups")
        except PermissionError as e:
            msg_error(self, "Access Denied", str(e))
            return

        if not msg_question(self, "Restore Database",
                            "⚠ WARNING: Restoring will replace ALL current data.\n\n"
                            "This cannot be undone. Continue?"):
            return

        enc_path = filedialog.askopenfilename(
            filetypes=[("Encrypted backup", "*.enc")],
            title="Select encrypted backup file (.enc)"
        )
        if not enc_path:
            return

        key_path = filedialog.askopenfilename(
            filetypes=[("Key file", "*.key"), ("All files", "*.*")],
            title="Select encryption key file (.enc.key)"
        )
        if not key_path:
            return

        try:
            # Auto-backup current DB before restoring
            timestamp   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            auto_backup = DB_PATH + f".before_restore_{timestamp}"
            shutil.copy2(DB_PATH, auto_backup)

            restore_encrypted_backup(enc_path, key_path, DB_PATH)
            log_audit(self.user["id"], self.user["username"], "Backup", "RESTORE_BACKUP",
                      new_value={"source": enc_path})
            msg_info(self, "Restore Complete",
                     f"Database restored from:\n{enc_path}\n\n"
                     f"Previous database saved as:\n{auto_backup}\n\n"
                     "Please restart the application.")
        except Exception as e:
            msg_error(self, "Restore Failed", f"Could not restore backup:\n{e}")