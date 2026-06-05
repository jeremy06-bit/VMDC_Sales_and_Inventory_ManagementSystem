"""
VMDC Motor Parts — Ink Wash Theme
Centralized design tokens and reusable UI helpers.
Palette: Charcoal #4A4A4A · Cool Gray #CBCBCB · Soft Ivory #FFFFE3 · Steel Blue #6D8196
"""

import customtkinter as ctk
from tkinter import ttk

# ──────────────────────────────────────────────
#  COLOR PALETTE  — Ink Wash
# ──────────────────────────────────────────────

# Backgrounds  (light base derived from ivory / gray family)
BG_DARK       = "#FFFFE3"     # soft ivory — main app background
BG_SIDEBAR    = "#E8E8D8"     # slightly darker ivory for sidebar
BG_CARD       = "#F5F5E0"     # card / panel surface
BG_CARD_ALT   = "#EBEBD6"     # slightly deeper card
BG_INPUT      = "#FFFFFF"     # crisp white for input fields
BG_HOVER      = "#D8D8C8"     # subtle cool-gray hover tint

# Accent — steel blue (refined gallery feel)
ACCENT        = "#6D8196"     # primary steel blue
ACCENT_HOVER  = "#566B7D"     # deeper on hover
ACCENT_LIGHT  = "#8FA3B3"     # lighter steel blue
ACCENT_SUBTLE = "#D6DFE6"     # pale blue tint (subtle fills)

# Text
TEXT_PRIMARY   = "#2E2E2E"    # near-black (from charcoal family)
TEXT_SECONDARY = "#4A4A4A"    # charcoal — standard body
TEXT_MUTED     = "#8A8A8A"    # light gray — de-emphasised

# Semantic  (kept readable on ivory bg)
SUCCESS        = "#4A7C59"    # muted forest green
SUCCESS_HOVER  = "#3A6347"
DANGER         = "#A94040"    # muted crimson
DANGER_HOVER   = "#8C3333"
WARNING        = "#B88B2E"    # warm amber
INFO           = "#4A6D8C"    # blue-gray info

# Borders
BORDER         = "#CBCBCB"    # cool gray — main border
BORDER_ACCENT  = "#6D8196"    # steel blue accent border

# Sidebar
SIDEBAR_BG     = "#E8E8D8"    # ivory-gray sidebar
SIDEBAR_ACTIVE = "#C8D4DC"    # steel-blue-tinted active row
SIDEBAR_HOVER  = "#DCDCCC"    # soft hover

# Table rows
ROW_EVEN       = "#F5F5E0"    # card ivory
ROW_ODD        = "#EBEBD6"    # slightly deeper ivory
ROW_SELECTED   = "#C8D4DC"    # steel blue selection


# ──────────────────────────────────────────────
#  TREEVIEW DARK STYLING
# ──────────────────────────────────────────────

def style_treeview(tree: ttk.Treeview, row_height: int = 32):
    """Apply the dark motor-shop theme to any ttk.Treeview widget."""

    style = ttk.Style()
    style_name = f"VMDC_{id(tree)}.Treeview"

    style.theme_use("default")

    style.configure(style_name,
        background=BG_CARD,
        foreground=TEXT_PRIMARY,
        fieldbackground=BG_CARD,
        borderwidth=0,
        rowheight=row_height,
        font=("Segoe UI", 10),
    )
    style.configure(f"{style_name}.Heading",
        background=BG_CARD_ALT,
        foreground=ACCENT,
        borderwidth=0,
        font=("Segoe UI", 10, "bold"),
        relief="flat",
    )
    style.map(style_name,
        background=[("selected", ROW_SELECTED)],
        foreground=[("selected", TEXT_PRIMARY)],
    )
    style.map(f"{style_name}.Heading",
        background=[("active", BG_HOVER)],
    )

    tree.configure(style=style_name)
    tree.tag_configure("evenrow", background=ROW_EVEN)
    tree.tag_configure("oddrow",  background=ROW_ODD)
    tree.tag_configure("low",     foreground=DANGER, background="#F0DCDC")


def insert_with_stripes(tree: ttk.Treeview, values, iid=None, extra_tags=()):
    """Insert a row with automatic even/odd striping."""
    existing = len(tree.get_children())
    tag = "evenrow" if existing % 2 == 0 else "oddrow"
    tags = (tag,) + tuple(extra_tags)
    kw = {"values": values, "tags": tags}
    if iid is not None:
        kw["iid"] = str(iid)
    tree.insert("", "end", **kw)


# ──────────────────────────────────────────────
#  REUSABLE WIDGET HELPERS
# ──────────────────────────────────────────────

def create_page_header(parent, title: str, subtitle: str = None):
    """Create a consistent page title bar."""
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    frame.pack(fill="x", pady=(0, 16))

    ctk.CTkLabel(
        frame, text=title,
        font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
        text_color=TEXT_PRIMARY
    ).pack(side="left")

    if subtitle:
        ctk.CTkLabel(
            frame, text=subtitle,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=TEXT_SECONDARY
        ).pack(side="left", padx=(12, 0))

    return frame


def create_stat_card(parent, label: str, value: str, accent: str = ACCENT, icon: str = ""):
    """Create a single gradient-ish stat card."""
    card = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=14, border_width=1, border_color=BORDER)

    # Top color strip
    strip = ctk.CTkFrame(card, fg_color=accent, height=4, corner_radius=2)
    strip.pack(fill="x", padx=16, pady=(14, 0))

    if icon:
        ctk.CTkLabel(
            card, text=icon,
            font=ctk.CTkFont(size=20),
            text_color=accent
        ).pack(pady=(10, 0))

    ctk.CTkLabel(
        card, text=label,
        font=ctk.CTkFont(family="Segoe UI", size=11),
        text_color=TEXT_SECONDARY
    ).pack(pady=(8, 2))

    ctk.CTkLabel(
        card, text=value,
        font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
        text_color=TEXT_PRIMARY
    ).pack(pady=(0, 16))

    return card


def create_action_button(parent, text: str, command, color=ACCENT, hover=ACCENT_HOVER, icon="", width=None):
    """Create a styled action button."""
    display = f"{icon}  {text}" if icon else text
    kw = {
        "text": display,
        "height": 38,
        "fg_color": color,
        "hover_color": hover,
        "font": ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        "corner_radius": 10,
        "command": command,
    }
    if width:
        kw["width"] = width
    return ctk.CTkButton(parent, **kw)


def create_search_bar(parent, search_var, placeholder="🔍  Search..."):
    """Create a dark-themed search bar inside a card."""
    bar = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=12, border_width=1, border_color=BORDER)
    bar.pack(fill="x", pady=(0, 10))
    entry = ctk.CTkEntry(
        bar,
        textvariable=search_var,
        placeholder_text=placeholder,
        height=40,
        fg_color=BG_INPUT,
        border_color=BORDER,
        text_color=TEXT_PRIMARY,
        placeholder_text_color=TEXT_MUTED,
        font=ctk.CTkFont(family="Segoe UI", size=13),
        corner_radius=10,
    )
    entry.pack(fill="x", padx=12, pady=10)
    return bar, entry


def create_table_frame(parent):
    """Create a dark card that wraps a Treeview table."""
    frame = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=14, border_width=1, border_color=BORDER)
    frame.pack(fill="both", expand=True)
    return frame


def create_dialog_entry(parent, label_text, default="", show=None, placeholder=""):
    """Create a label + entry pair for dialogs."""
    ctk.CTkLabel(
        parent, text=label_text, anchor="w",
        font=ctk.CTkFont(family="Segoe UI", size=12),
        text_color=TEXT_SECONDARY
    ).pack(fill="x", pady=(8, 3))

    kw = {
        "height": 38,
        "fg_color": BG_INPUT,
        "border_color": BORDER,
        "text_color": TEXT_PRIMARY,
        "font": ctk.CTkFont(family="Segoe UI", size=13),
        "corner_radius": 8,
    }
    if show:
        kw["show"] = show
    if placeholder:
        kw["placeholder_text"] = placeholder
        kw["placeholder_text_color"] = TEXT_MUTED

    entry = ctk.CTkEntry(parent, **kw)
    if default:
        entry.insert(0, default)
    entry.pack(fill="x")
    return entry


def create_dialog_button(parent, text, command, color=ACCENT, hover=ACCENT_HOVER):
    """Create a styled dialog save/confirm button."""
    return ctk.CTkButton(
        parent, text=text, height=44,
        fg_color=color, hover_color=hover,
        font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        corner_radius=10,
        command=command,
    )


def style_dialog(dialog, title, width=420, height=500):
    """Apply consistent dark styling to a CTkToplevel dialog."""
    dialog.title(title)
    dialog.geometry(f"{width}x{height}")
    dialog.resizable(False, False)
    dialog.configure(fg_color=BG_DARK)
    dialog.grab_set()


def create_option_menu(parent, values, variable, **kwargs):
    """Create a dark-themed option menu."""
    return ctk.CTkOptionMenu(
        parent,
        values=values,
        variable=variable,
        height=38,
        fg_color=BG_INPUT,
        button_color=ACCENT,
        button_hover_color=ACCENT_HOVER,
        dropdown_fg_color=BG_CARD,
        dropdown_hover_color=BG_HOVER,
        dropdown_text_color=TEXT_PRIMARY,
        text_color=TEXT_PRIMARY,
        font=ctk.CTkFont(family="Segoe UI", size=13),
        corner_radius=8,
        **kwargs,
    )


# ──────────────────────────────────────────────
#  PAGINATOR  — reusable pagination bar
# ──────────────────────────────────────────────

class Paginator:
    """
    Attach a pagination bar below any ttk.Treeview.

    Usage
    ─────
        self._pager = Paginator(parent_frame, self.tree, page_size=20,
                                render_fn=self._render_page)

        # In your load method, after fetching all rows:
        self._pager.set_data(rows)

    render_fn(rows_slice) is called with the current page rows each time
    the user changes page. Fill the tree inside it.
    """

    def __init__(self, parent, tree, page_size: int = 20, render_fn=None, bar_parent=None):
        import math as _math
        self._math     = _math
        self.tree      = tree
        self.page_size = page_size
        self.render_fn = render_fn
        self._data     = []
        self._page     = 0

        # If bar_parent is given, place the pagination bar outside the table card
        _bar_container = bar_parent if bar_parent is not None else parent
        bar = ctk.CTkFrame(_bar_container, fg_color=BG_CARD_ALT,
                           corner_radius=10, height=46)
        bar.pack(fill="x", side="bottom", padx=0, pady=(6, 0))
        bar.pack_propagate(False)

        _btn = dict(
            height=28, width=82,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            corner_radius=6,
        )

        # Rows/page dropdown on the right
        ctk.CTkLabel(bar, text="Rows / page:",
                     font=ctk.CTkFont(family="Segoe UI", size=11),
                     text_color=TEXT_MUTED).pack(side="right", padx=(0, 4))

        self._size_var = ctk.StringVar(value=str(page_size))
        ctk.CTkOptionMenu(
            bar, values=["10", "20", "50", "100"],
            variable=self._size_var,
            width=72, height=26,
            fg_color=BG_INPUT,
            button_color=ACCENT, button_hover_color=ACCENT_HOVER,
            dropdown_fg_color=BG_CARD, dropdown_hover_color=BG_HOVER,
            dropdown_text_color=TEXT_PRIMARY, text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=6,
            command=self._on_size_change,
        ).pack(side="right", padx=(0, 10), pady=5)

        # Centered frame: Prev | page info | Next
        center = ctk.CTkFrame(bar, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        self._prev_btn = ctk.CTkButton(center, text="◀  Prev",
                                       command=self._prev, **_btn)
        self._prev_btn.pack(side="left", padx=(0, 8))

        self._info_var = ctk.StringVar(value="")
        ctk.CTkLabel(center, textvariable=self._info_var,
                     font=ctk.CTkFont(family="Segoe UI", size=12),
                     text_color=TEXT_MUTED).pack(side="left", padx=8)

        self._next_btn = ctk.CTkButton(center, text="Next  ▶",
                                       command=self._next, **_btn)
        self._next_btn.pack(side="left", padx=(8, 0))

    def set_data(self, rows: list):
        self._data = list(rows)
        self._page = 0
        self._refresh()

    def _total_pages(self) -> int:
        if not self._data:
            return 1
        return self._math.ceil(len(self._data) / self.page_size)

    def _refresh(self):
        total     = len(self._data)
        tp        = self._total_pages()
        start_i   = self._page * self.page_size
        end_i     = min(start_i + self.page_size, total)
        page_rows = self._data[start_i:end_i]

        for item in self.tree.get_children():
            self.tree.delete(item)
        if self.render_fn:
            self.render_fn(page_rows)

        if total == 0:
            self._info_var.set("No records found")
        else:
            self._info_var.set(
                f"Showing {start_i + 1}–{end_i} of {total}   "
                f"(page {self._page + 1} of {tp})"
            )

        can_prev = self._page > 0
        can_next = self._page < tp - 1
        self._prev_btn.configure(state="normal" if can_prev else "disabled",
                                 text_color=TEXT_PRIMARY if can_prev else TEXT_MUTED)
        self._next_btn.configure(state="normal" if can_next else "disabled",
                                 text_color=TEXT_PRIMARY if can_next else TEXT_MUTED)

    def _prev(self):
        if self._page > 0:
            self._page -= 1
            self._refresh()

    def _next(self):
        if self._page < self._total_pages() - 1:
            self._page += 1
            self._refresh()

    def _on_size_change(self, value: str):
        self.page_size = int(value)
        self._page = 0
        self._refresh()


# ──────────────────────────────────────────────
#  CUSTOM MESSAGE BOX  (professional redesign)
# ──────────────────────────────────────────────

class MessageBox(ctk.CTkToplevel):
    """
    Professional themed replacement for tkinter.messagebox.

    kind values : "info" | "warning" | "error" | "success" | "question"

    Design language
    ───────────────
    • 3-px colour stripe at the top (matches kind)
    • Square-rounded icon badge (8 px radius) with a Unicode symbol
    • Title + muted kind label stacked beside the icon
    • Thin separator rule between header and message body
    • Message body indented to align with text above
    • Right-aligned button row; ghost Cancel + coloured primary for questions
    • Centred over the parent window
    """

    # (icon_char, stripe_hex, icon_bg, icon_fg, btn_bg, btn_hover, btn_text, kind_label)
    _KIND: dict = {
        "info": (
            "ℹ", INFO, "#D6E4EF", "#4A6D8C",
            "#D6E4EF", "#C2D4E0", "#2E5070", "Information",
        ),
        "warning": (
            "⚠", WARNING, "#F0E6CC", "#B88B2E",
            "#F0E6CC", "#E8DCC0", "#7A5C1A", "Warning",
        ),
        "error": (
            "✕", DANGER, "#F0DCDC", "#A94040",
            "#F0DCDC", "#E8CECE", "#7A2828", "Error",
        ),
        "success": (
            "✓", SUCCESS, "#D8EAE0", "#4A7C59",
            "#D8EAE0", "#C8DED2", "#2E5C3C", "Success",
        ),
        "question": (
            "?", ACCENT, "#C8D4DC", "#6D8196",
            "#C8D4DC", "#BAC8D4", "#3A5060", "Confirm",
        ),
    }

    def __init__(self, parent, kind: str, title: str, message: str):
        super().__init__(parent)
        self._result = False
        cfg = self._KIND.get(kind, self._KIND["info"])
        icon_char, stripe, icon_bg, icon_fg, btn_bg, btn_hover, btn_txt, kind_label = cfg

        # ── window chrome ──────────────────────────────────────────────────
        self.title("")                         # clean title bar
        self.resizable(False, False)
        self.configure(fg_color=BG_CARD)
        self.grab_set()
        self.lift()
        self.focus_force()
        self.overrideredirect(False)           # keep native close button

        # ── size: clamp to 380-480 wide, grow height with message lines ──
        lines      = message.splitlines()
        max_chars  = max((len(l) for l in lines), default=30)
        dlg_width  = min(max(380, max_chars * 7 + 100), 480)
        dlg_height = 210 + max(0, len(lines) - 1) * 16
        self.geometry(f"{dlg_width}x{dlg_height}")

        # ── 3-px top stripe ────────────────────────────────────────────────
        ctk.CTkFrame(
            self, fg_color=stripe, height=3, corner_radius=0
        ).pack(fill="x", side="top")

        # ── outer card body ────────────────────────────────────────────────
        card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0)
        card.pack(fill="both", expand=True, padx=0, pady=0)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=24, pady=20)

        # ── header row: icon badge + stacked labels ────────────────────────
        header = ctk.CTkFrame(inner, fg_color="transparent")
        header.pack(fill="x", pady=(0, 0))

        # icon badge
        badge = ctk.CTkFrame(
            header, fg_color=icon_bg,
            width=40, height=40, corner_radius=8
        )
        badge.pack(side="left", padx=(0, 14))
        badge.pack_propagate(False)
        ctk.CTkLabel(
            badge, text=icon_char,
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
            text_color=icon_fg, fg_color="transparent"
        ).place(relx=0.5, rely=0.5, anchor="center")

        # title + kind label stacked
        label_stack = ctk.CTkFrame(header, fg_color="transparent")
        label_stack.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            label_stack, text=title,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=TEXT_PRIMARY, anchor="w"
        ).pack(anchor="w")

        ctk.CTkLabel(
            label_stack, text=kind_label,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED, anchor="w"
        ).pack(anchor="w")

        # ── thin separator ─────────────────────────────────────────────────
        ctk.CTkFrame(
            inner, fg_color=BORDER, height=1, corner_radius=0
        ).pack(fill="x", pady=(14, 12))

        # ── message body (indented to align with title text) ───────────────
        msg_wrap = dlg_width - 48 - 54   # account for padx + badge width
        ctk.CTkLabel(
            inner, text=message,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_SECONDARY,
            anchor="w", justify="left",
            wraplength=msg_wrap
        ).pack(anchor="w", padx=(54, 0), pady=(0, 18))

        # ── button row ─────────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(fill="x", anchor="e")

        _btn_font = ctk.CTkFont(family="Segoe UI", size=12, weight="bold")

        if kind == "question":
            ctk.CTkButton(
                btn_row, text="Cancel", width=96, height=34,
                fg_color=BG_INPUT, hover_color=BG_HOVER,
                border_width=1, border_color=BORDER,
                text_color=TEXT_SECONDARY,
                font=_btn_font, corner_radius=7,
                command=self._no
            ).pack(side="right", padx=(8, 0))

            ctk.CTkButton(
                btn_row, text="Yes, confirm", width=120, height=34,
                fg_color=btn_bg, hover_color=btn_hover,
                border_width=1, border_color=icon_bg,
                text_color=btn_txt,
                font=_btn_font, corner_radius=7,
                command=self._yes
            ).pack(side="right")
        else:
            ctk.CTkButton(
                btn_row, text="OK", width=96, height=34,
                fg_color=btn_bg, hover_color=btn_hover,
                border_width=1, border_color=icon_bg,
                text_color=btn_txt,
                font=_btn_font, corner_radius=7,
                command=self._yes
            ).pack(side="right")

        # ── centre over parent ─────────────────────────────────────────────
        self.update_idletasks()
        try:
            if parent and parent.winfo_exists():
                px = parent.winfo_rootx() + parent.winfo_width()  // 2 - dlg_width  // 2
                py = parent.winfo_rooty() + parent.winfo_height() // 2 - dlg_height // 2
                self.geometry(f"+{max(0, px)}+{max(0, py)}")
        except Exception:
            pass

        self.wait_window()

    def _yes(self): self._result = True;  self.destroy()
    def _no(self):  self._result = False; self.destroy()

    @property
    def result(self) -> bool:
        return self._result


# ── convenience helpers (drop-in replacements for tkinter.messagebox) ─────────

def msg_info(parent, title: str, message: str) -> None:
    MessageBox(parent, "info", title, message)

def msg_warning(parent, title: str, message: str) -> None:
    MessageBox(parent, "warning", title, message)

def msg_error(parent, title: str, message: str) -> None:
    MessageBox(parent, "error", title, message)

def msg_success(parent, title: str, message: str) -> None:
    MessageBox(parent, "success", title, message)

def msg_question(parent, title: str, message: str) -> bool:
    return MessageBox(parent, "question", title, message).result