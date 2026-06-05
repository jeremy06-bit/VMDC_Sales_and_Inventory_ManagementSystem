import customtkinter as ctk
from tkinter import ttk
from database import get_connection
from utils.helpers import generate_transaction_number
from ui.theme import (
    BG_DARK, BG_CARD, BG_CARD_ALT, BG_INPUT, BG_HOVER, BORDER,
    ACCENT, ACCENT_HOVER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    style_treeview, insert_with_stripes, Paginator,
    create_dialog_entry, create_dialog_button, style_dialog, create_option_menu,

    msg_info, msg_warning, msg_error, msg_success, msg_question
)

class ExpensesFrame(ctk.CTkFrame):
    def __init__(self, master, user: dict):
        super().__init__(master, fg_color="transparent")
        self.user = user
        self._build_ui()
        self._load()

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(header, text="Expenses",
                    font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
                    text_color=TEXT_PRIMARY).pack(side="left")
        ctk.CTkButton(header, text="+  Add Expense", height=38,
                     fg_color=ACCENT, hover_color=ACCENT_HOVER,
                     font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                     corner_radius=10, command=self._add).pack(side="right")

        table_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14,
                                    border_width=1, border_color=BORDER)
        table_frame.pack(fill="both", expand=True)

        cols = ("date", "category", "description", "amount")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=18)
        hdrs = {"date": "Date", "category": "Category", "description": "Description", "amount": "Amount"}
        widths = {"date": 110, "category": 130, "description": 300, "amount": 100}
        for col in cols:
            self.tree.heading(col, text=hdrs[col])
            self.tree.column(col, width=widths[col], anchor="w" if col == "amount" else "w")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        style_treeview(self.tree)
        self.tree.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        scrollbar.pack(side="right", fill="y", pady=6)
        self._pager = Paginator(table_frame, self.tree, page_size=20,
                                render_fn=self._render_page, bar_parent=self)

    def _load(self):
        conn = get_connection()
        rows = conn.execute("SELECT * FROM expenses ORDER BY expense_date DESC, created_at DESC").fetchall()
        conn.close()
        self._pager.set_data(list(rows))

    def _render_page(self, rows):
        for row in rows:
            insert_with_stripes(self.tree, (row["expense_date"], row["category"],
                                            row["description"], f"₱{row['amount']:,.2f}"))

    def _add(self):
        ExpenseDialog(self, self.user, self._load)


class ExpenseDialog(ctk.CTkToplevel):
    def __init__(self, master, user, callback):
        super().__init__(master)
        self.user = user
        self.callback = callback
        style_dialog(self, "Add Expense", 420, 420)
        self._build()

    def _build(self):
        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=28, pady=18)

        ctk.CTkLabel(form, text="Add Expense",
                    font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
                    text_color=TEXT_PRIMARY).pack(anchor="w", pady=(0, 10))

        ctk.CTkLabel(form, text="Category *", anchor="w",
                    font=ctk.CTkFont(family="Segoe UI", size=12),
                    text_color=TEXT_SECONDARY).pack(fill="x", pady=(0, 3))
        categories = ["Electricity", "Water", "Rent", "Staff Salary", "Supplies", "Miscellaneous"]
        self.category_var = ctk.StringVar(value=categories[0])
        create_option_menu(form, values=categories, variable=self.category_var).pack(fill="x")

        self.description = create_dialog_entry(form, "Description *", placeholder="Brief description")
        self.amount = create_dialog_entry(form, "Amount (₱) *", placeholder="0.00")

        create_dialog_button(form, "Save Expense", self._save).pack(fill="x", pady=(18, 0))

    def _save(self):
        desc = self.description.get().strip()
        if not desc:
            msg_warning(self, "Required", "Description is required.")
            return
        try:
            amount = float(self.amount.get())
        except ValueError:
            msg_warning(self, "Invalid", "Enter a valid amount.")
            return
        conn = get_connection()
        conn.execute("INSERT INTO expenses (recorded_by, category, description, amount) VALUES (?,?,?,?)",
                    (self.user["id"], self.category_var.get(), desc, amount))
        conn.commit()
        conn.close()
        self.callback()
        self.destroy()