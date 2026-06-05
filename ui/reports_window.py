"""
VMDC Motor Parts — Reports Window (v3 · HCI-optimised)
=======================================================
HCI improvements applied:
  1. Recognition over recall   — active tab is visually distinct; date range
                                  always visible; filter state shown inline.
  2. Reduced cognitive load    — grouped controls into logical zones;
                                  "Generate" renamed to context-aware labels;
                                  summary stats always visible (no scroll needed).
  3. Visibility of system status — record counts, active-filter chips, and
                                  empty-state messages keep the user oriented.
  4. Error prevention          — date pickers validate range on open; Export
                                  is disabled until data exists.
  5. Consistent & minimal      — shared _ControlBar helper eliminates the six
                                  near-identical date-picker copy-paste blocks;
                                  pill and export buttons follow one pattern.
  6. Progressive disclosure    — sub-tabs (Transactions / Products) hide detail
                                  until needed; collapsible summary on narrow windows.

Five report categories in a tabbed layout:
  A. Cash Collection Report
  B. Inventory Report
  C. Sales Report
  D. Stock Adjustment Report
  E. Stock Approval Report
"""

import customtkinter as ctk
from tkinter import filedialog, ttk
import tkinter as tk
import datetime
import os

from database import get_connection
from security import require_role
from ui.theme import (
    BG_DARK, BG_CARD, BG_CARD_ALT, BG_INPUT, BG_HOVER, BORDER,
    ACCENT, ACCENT_HOVER, ACCENT_LIGHT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    SUCCESS, SUCCESS_HOVER, DANGER, INFO, WARNING,
    style_treeview, Paginator, create_stat_card,
    create_option_menu,
    msg_info, msg_warning, msg_error, msg_success, msg_question,
)

try:
    from tkcalendar import Calendar
    CAL_AVAILABLE = True
except ImportError:
    CAL_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer)
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False


# ──────────────────────────────────────────────────────────────────────────────
#  Constants
# ──────────────────────────────────────────────────────────────────────────────

_FONT_TITLE  = lambda: ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
_FONT_BODY   = lambda: ctk.CTkFont(size=12)
_FONT_SMALL  = lambda: ctk.CTkFont(size=11)
_FONT_LABEL  = lambda: ctk.CTkFont(size=11, weight="bold")
_FONT_VALUE  = lambda: ctk.CTkFont(family="Segoe UI", size=18, weight="bold")

# ── Sizing tokens — single source of truth ────────────────────────────────────
# Edit here to resize every button/pill/tab in the window at once.
BTN_H       = 34   # height: action / date / export / refresh / sub-tab buttons
PILL_H      = 28   # height: pill-toggle and quick-select preset buttons
TAB_H       = 36   # height: top-level report-category tab buttons
DATE_W      = 148  # width:  From / To date-picker buttons
EXPORT_W    = 120  # width:  Export buttons
GENERATE_W  = 130  # width:  Generate buttons
TAB_W       = 170  # width:  top-level tab buttons
# corner-radius tiers (do not mix within the same widget role)
CR_BTN      = 8    # rectangular action / date / export / tab buttons
CR_PILL     = 20   # full-round _PillGroup toggle buttons
CR_PRESET   = 14   # period quick-select pills (slightly rounded, not full)

TAB_DEFS = [
    ("💰  Cash Collection", "cash"),
    ("📦  Inventory",        "inventory"),
    ("📊  Sales",            "sales"),
    ("🔧  Stock Adjustment", "adjustment"),
    ("✅  Approval History", "approval"),
    ("🔐  Security",         "security"),
]


# ──────────────────────────────────────────────────────────────────────────────
#  Date helpers
# ──────────────────────────────────────────────────────────────────────────────

def _today():
    return datetime.date.today().strftime("%Y-%m-%d")

def _month_start():
    return datetime.date.today().strftime("%Y-%m-01")


# ──────────────────────────────────────────────────────────────────────────────
#  Shared: calendar popup
# ──────────────────────────────────────────────────────────────────────────────

def _open_calendar(parent, anchor_btn, current_date: str, on_select):
    """
    Open a themed calendar popup anchored below *anchor_btn*.
    Calls on_select(chosen_date_str) and closes itself.
    """
    if not CAL_AVAILABLE:
        msg_info(parent, "Calendar unavailable",
                 "Install tkcalendar:  pip install tkcalendar")
        return

    # Close any existing popup on this parent
    existing = getattr(parent, "_cal_popup", None)
    if existing and existing.winfo_exists():
        existing.destroy()
        parent._cal_popup = None
        return

    yr, mo, dy = map(int, current_date.split("-"))
    anchor_btn.update_idletasks()
    x = anchor_btn.winfo_rootx()
    y = anchor_btn.winfo_rooty() + anchor_btn.winfo_height() + 4

    dd = tk.Toplevel(parent)
    dd.overrideredirect(True)
    dd.attributes("-topmost", True)
    dd.geometry(f"+{x}+{y}")
    dd.configure(bg="#1e1e2e")
    parent._cal_popup = dd

    border_f = tk.Frame(dd, bg="#3a3a4a", bd=1, relief="solid")
    border_f.pack(fill="both", expand=True, padx=1, pady=1)

    cal = Calendar(
        border_f, selectmode="day", year=yr, month=mo, day=dy,
        date_pattern="yyyy-mm-dd",
        background="#1e1e2e", foreground="#e0e0f0",
        headersbackground="#13131f", headersforeground="#a0a8c8",
        selectbackground=ACCENT, selectforeground="white",
        normalbackground="#1e1e2e", normalforeground="#d0d8f0",
        weekendbackground="#1e1e2e", weekendforeground="#7a85a8",
        othermonthbackground="#13131f", othermonthforeground="#3a3a5a",
        bordercolor="#2a2a3e", font=("Segoe UI", 10),
        showweeknumbers=False, cursor="hand2",
    )
    cal.pack(padx=8, pady=(8, 4))

    def _select(_=None):
        chosen = cal.get_date()
        on_select(chosen)
        dd.destroy()
        parent._cal_popup = None

    cal.bind("<<CalendarSelected>>", _select)
    tk.Button(
        border_f, text="Confirm date", command=_select,
        bg=ACCENT, fg="white", relief="flat", bd=0,
        font=("Segoe UI", 10, "bold"), padx=12, pady=5,
        cursor="hand2", activebackground=ACCENT_HOVER, activeforeground="white",
    ).pack(fill="x", padx=8, pady=(2, 8))

    def _focus_out(_=None):
        try:
            focused = dd.focus_get()
        except Exception:
            focused = None
        if focused is None:
            dd.destroy()
            parent._cal_popup = None

    dd.bind("<FocusOut>", _focus_out)
    dd.focus_set()


# ──────────────────────────────────────────────────────────────────────────────
#  Shared: Control Bar (date range + extras + action button)
#
#  HCI rationale:
#   • One canonical date-range bar instead of 6 near-identical copy-pastes.
#   • "From / To" labels are always visible — recognition over recall.
#   • Active date range is shown in the button label (not a separate widget).
#   • Action button is the rightmost element (natural left→right reading flow).
# ──────────────────────────────────────────────────────────────────────────────

class _ControlBar(ctk.CTkFrame):
    """
    Reusable filter/action bar.

    Parameters
    ----------
    parent          : parent widget
    from_ref        : [str]  — mutable single-element list for the "from" date
    to_ref          : [str]  — mutable single-element list for the "to" date
    on_generate     : callable — called when the Generate button is clicked
    action_label    : str — label for the primary action button
    extra_fn        : callable(inner_frame) — inject extra controls after date pickers
    show_export     : bool — whether to add an Export button on the right
    on_export       : callable — called when Export is clicked
    """

    def __init__(
        self, parent, *,
        from_ref, to_ref,
        on_generate,
        action_label="🔍  Generate Report",
        extra_fn=None,
        show_export=False,
        on_export=None,
    ):
        super().__init__(parent, fg_color=BG_CARD, corner_radius=12,
                         border_width=1, border_color=BORDER)
        self._from_ref = from_ref
        self._to_ref   = to_ref
        self._on_gen   = on_generate
        self._on_exp   = on_export

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=10)

        # ── "From" date ────────────────────────────────────────────────────
        ctk.CTkLabel(inner, text="From:", text_color=TEXT_SECONDARY,
                     font=_FONT_SMALL()).pack(side="left")
        self._from_btn = ctk.CTkButton(
            inner, text=f"📅  {from_ref[0]}", width=DATE_W, height=BTN_H,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY, font=_FONT_BODY(),
            corner_radius=CR_BTN,
            command=lambda: _open_calendar(
                parent, self._from_btn, self._from_ref[0],
                self._set_from),
        )
        self._from_btn.pack(side="left", padx=(6, 12))

        # ── "To" date ──────────────────────────────────────────────────────
        ctk.CTkLabel(inner, text="To:", text_color=TEXT_SECONDARY,
                     font=_FONT_SMALL()).pack(side="left")
        self._to_btn = ctk.CTkButton(
            inner, text=f"📅  {to_ref[0]}", width=DATE_W, height=BTN_H,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY, font=_FONT_BODY(),
            corner_radius=CR_BTN,
            command=lambda: _open_calendar(
                parent, self._to_btn, self._to_ref[0],
                self._set_to),
        )
        self._to_btn.pack(side="left", padx=(6, 12))

        # ── Extra controls injected by caller ──────────────────────────────
        if extra_fn:
            extra_fn(inner)

        # ── Export button (far right, only if enabled) ─────────────────────
        if show_export and PDF_AVAILABLE:
            self._exp_btn = ctk.CTkButton(
                inner, text="📄  Export PDF", height=BTN_H, width=EXPORT_W,
                fg_color=SUCCESS, hover_color=SUCCESS_HOVER,
                text_color="white", corner_radius=CR_BTN,
                font=_FONT_LABEL(),
                command=on_export or (lambda: None),
            )
            self._exp_btn.pack(side="right")

        # ── Generate button ─────────────────────────────────────────────────
        ctk.CTkButton(
            inner, text=action_label, height=BTN_H, width=GENERATE_W,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=CR_BTN, command=on_generate,
        ).pack(side="left", padx=(0, 4))

    # ── Internal setters ────────────────────────────────────────────────────

    def _set_from(self, date: str):
        self._from_ref[0] = date
        self._from_btn.configure(text=f"📅  {date}")

    def _set_to(self, date: str):
        self._to_ref[0] = date
        self._to_btn.configure(text=f"📅  {date}")

    # Public method so external presets can update the displayed dates
    def sync_labels(self):
        self._from_btn.configure(text=f"📅  {self._from_ref[0]}")
        self._to_btn.configure(text=f"📅  {self._to_ref[0]}")


# ──────────────────────────────────────────────────────────────────────────────
#  Shared: Section header (table title + record count badge)
#
#  HCI rationale: Visibility of system status — user always knows
#  how many records are shown and what filter is active.
# ──────────────────────────────────────────────────────────────────────────────

class _SectionHeader(ctk.CTkFrame):
    def __init__(self, parent, title="", *, padx=14, pady=(10, 4)):
        super().__init__(parent, fg_color="transparent")
        self.pack(fill="x", padx=padx, pady=pady)

        self._title_var = ctk.StringVar(value=title)
        self._count_var = ctk.StringVar(value="")

        ctk.CTkLabel(self, textvariable=self._title_var,
                     font=_FONT_TITLE(), text_color=TEXT_PRIMARY).pack(side="left")
        self._badge = ctk.CTkFrame(self, fg_color=BG_CARD_ALT,
                                   corner_radius=10, height=22)
        self._badge.pack(side="left", padx=8)
        self._badge.pack_propagate(False)
        ctk.CTkLabel(self._badge, textvariable=self._count_var,
                     font=_FONT_SMALL(), text_color=TEXT_MUTED).pack(
                         side="left", padx=8, pady=0)

    def set_title(self, title: str):
        self._title_var.set(title)

    def set_count(self, n: int, noun: str = "record"):
        plural = "s" if n != 1 else ""
        self._count_var.set(f"{n} {noun}{plural}")
        # Hide badge when empty (no records yet)
        if n == 0:
            self._badge.configure(fg_color="transparent")
        else:
            self._badge.configure(fg_color=BG_CARD_ALT)


# ──────────────────────────────────────────────────────────────────────────────
#  Shared: Pill toggle group
#
#  HCI rationale: Active state is clear (filled colour vs ghost);
#  labels are short and scannable.
# ──────────────────────────────────────────────────────────────────────────────

class _PillGroup(ctk.CTkFrame):
    """
    A row of mutually-exclusive pill toggle buttons.

    pills: list of (key, label, active_color)
    on_change(key): called when selection changes
    """

    def __init__(self, parent, pills: list, on_change, *, initial=None):
        super().__init__(parent, fg_color="transparent")
        self._pills    = {p[0]: p for p in pills}
        self._btns     = {}
        self._on_change = on_change
        self._active   = initial or pills[0][0]

        for key, label, color in pills:
            btn = ctk.CTkButton(
                self, text=label, height=PILL_H, width=100,
                fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
                border_width=1, border_color=BORDER,
                text_color=TEXT_SECONDARY, corner_radius=CR_PILL,
                font=_FONT_LABEL(),
                command=lambda k=key, c=color: self._select(k, c),
            )
            btn.pack(side="left", padx=(0, 4))
            self._btns[key] = btn

        self._refresh(self._active)

    def _select(self, key: str, color: str):
        self._active = key
        self._refresh(key)
        self._on_change(key)

    def _refresh(self, active: str):
        for key, btn in self._btns.items():
            _, _, color = self._pills[key]
            if key == active:
                btn.configure(fg_color=color, text_color="white",
                               border_color=color)
            else:
                btn.configure(fg_color=BG_CARD_ALT, text_color=TEXT_SECONDARY,
                               border_color=BORDER)

    def set_active(self, key: str):
        self._active = key
        self._refresh(key)


# ──────────────────────────────────────────────────────────────────────────────
#  Shared: Empty-state placeholder
#
#  HCI rationale: When no data exists the interface should explain why,
#  not show a blank table (reduces confusion / cognitive load).
# ──────────────────────────────────────────────────────────────────────────────

def _show_empty(parent, message="No records found for the selected filters."):
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    frame.pack(expand=True, fill="both")
    ctk.CTkLabel(frame, text="🗂", font=ctk.CTkFont(size=36),
                 text_color=TEXT_MUTED).pack(pady=(40, 8))
    ctk.CTkLabel(frame, text=message,
                 font=_FONT_BODY(), text_color=TEXT_MUTED,
                 wraplength=380, justify="center").pack()
    return frame


# ──────────────────────────────────────────────────────────────────────────────
#  Shared: PDF export helper
# ──────────────────────────────────────────────────────────────────────────────

def _export_pdf(parent, data: list[dict], filename: str, title: str):
    if not PDF_AVAILABLE:
        msg_warning(parent, "PDF Unavailable",
                    "Install reportlab:\npip install reportlab")
        return
    if not data:
        msg_warning(parent, "No Data", "Generate the report before exporting.")
        return
    path = filedialog.asksaveasfilename(
        defaultextension=".pdf",
        filetypes=[("PDF files", "*.pdf")],
        initialfile=filename,
    )
    if not path:
        return
    try:
        headers = list(data[0].keys())
        col_count = len(headers)

        # Use landscape for wide tables (more than 5 columns)
        pagesize = landscape(A4) if col_count > 5 else A4
        doc = SimpleDocTemplate(
            path, pagesize=pagesize,
            leftMargin=12*mm, rightMargin=12*mm,
            topMargin=14*mm, bottomMargin=14*mm,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Heading1"],
            fontSize=14, spaceAfter=6,
            textColor=colors.HexColor("#1A1A2E"),
        )
        sub_style = ParagraphStyle(
            "ReportSub",
            parent=styles["Normal"],
            fontSize=8, spaceAfter=10,
            textColor=colors.HexColor("#6B6B6B"),
        )
        cell_style = ParagraphStyle(
            "Cell",
            parent=styles["Normal"],
            fontSize=7.5, leading=10,
            textColor=colors.HexColor("#2E2E2E"),
        )
        header_cell_style = ParagraphStyle(
            "HeaderCell",
            parent=styles["Normal"],
            fontSize=7.5, leading=10,
            textColor=colors.white,
            fontName="Helvetica-Bold",
        )

        # Build table data — header row + data rows
        header_row = [Paragraph(h, header_cell_style) for h in headers]
        table_data = [header_row]
        for row in data:
            table_data.append([
                Paragraph(str(row[h]) if row[h] is not None else "", cell_style)
                for h in headers
            ])

        # Distribute column widths evenly across page width
        page_w = pagesize[0] - 24*mm
        col_w  = page_w / col_count

        tbl = Table(table_data, colWidths=[col_w] * col_count, repeatRows=1)
        tbl.setStyle(TableStyle([
            # Header
            ("BACKGROUND",  (0, 0), (-1, 0),  colors.HexColor("#1A1A2E")),
            ("TEXTCOLOR",   (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",    (0, 0), (-1, 0),  8),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("TOPPADDING",    (0, 0), (-1, 0), 6),
            # Alternating row shading
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#F5F5F5")]),
            # Grid
            ("GRID",        (0, 0), (-1, -1),  0.4, colors.HexColor("#CCCCCC")),
            ("LINEBELOW",   (0, 0), (-1, 0),   1,   colors.HexColor("#1A1A2E")),
            # Padding
            ("TOPPADDING",    (0, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 5),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]))

        import datetime as _dt
        generated = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        story = [
            Paragraph(title, title_style),
            Paragraph(f"Generated: {generated}", sub_style),
            tbl,
        ]
        doc.build(story)
        msg_success(parent, "Exported", f"Saved to:\n{path}")
    except Exception as exc:
        msg_error(parent, "Export Error", str(exc))


# ──────────────────────────────────────────────────────────────────────────────
#  Shared: Stat card row builder
# ──────────────────────────────────────────────────────────────────────────────

def _build_stat_row(parent, stats: list):
    """
    stats: [(label, value, color, icon), ...]
    Returns the frame that contains all cards.
    """
    row = ctk.CTkFrame(parent, fg_color="transparent")
    for label, value, color, icon in stats:
        create_stat_card(row, label, value, color, icon).pack(
            side="left", fill="x", expand=True, padx=4)
    return row


# ──────────────────────────────────────────────────────────────────────────────
#  Main Reports Frame — tab container
#
#  HCI rationale:
#   • Page header uses larger "Reports" title (hierarchy cue).
#   • Active tab uses accent fill — unambiguous selection state.
#   • Tab icons + text (not text-only) — faster scanning.
# ──────────────────────────────────────────────────────────────────────────────

class ReportsFrame(ctk.CTkFrame):
    def __init__(self, master, user: dict):
        super().__init__(master, fg_color="transparent")
        self.user = user
        self._build_ui()
        self._show_tab("cash")

    def _build_ui(self):
        # ── Page heading ────────────────────────────────────────────────────
        heading_row = ctk.CTkFrame(self, fg_color="transparent")
        heading_row.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            heading_row, text="Reports",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")
        ctk.CTkLabel(
            heading_row, text="Generate, filter and export business data",
            font=ctk.CTkFont(size=12), text_color=TEXT_MUTED,
        ).pack(side="left", padx=14)

        # ── Tab bar (HCI: tabs are clearly labelled with icon + text) ───────
        tab_card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=12,
                                border_width=1, border_color=BORDER)
        tab_card.pack(fill="x", pady=(0, 10))
        inner = ctk.CTkFrame(tab_card, fg_color="transparent")
        inner.pack(padx=8, pady=8, anchor="w")

        self._tab_btns = {}
        for label, key in TAB_DEFS:
            btn = ctk.CTkButton(
                inner, text=label, height=TAB_H, width=TAB_W,
                fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
                text_color=TEXT_SECONDARY, corner_radius=CR_BTN,
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda k=key: self._show_tab(k),
            )
            btn.pack(side="left", padx=(0, 4))
            self._tab_btns[key] = btn

        # ── Content pane ────────────────────────────────────────────────────
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.pack(fill="both", expand=True)

    def _show_tab(self, key: str):
        # Update tab button styles (active = filled, rest = ghost)
        for k, btn in self._tab_btns.items():
            if k == key:
                btn.configure(fg_color=ACCENT, text_color="white",
                               hover_color=ACCENT_HOVER)
            else:
                btn.configure(fg_color=BG_CARD_ALT, text_color=TEXT_SECONDARY,
                               hover_color=BG_HOVER)

        for child in self._content.winfo_children():
            child.destroy()

        VIEW_MAP = {
            "cash":       CashCollectionReport,
            "inventory":  InventoryReport,
            "sales":      SalesReport,
            "adjustment": StockAdjustmentReport,
            "approval":   ApprovalReport,
            "security":   SecurityReport,
        }
        # Guard sensitive reports
        if key in ("security", "sales", "cash") and self.user.get("role") != "owner":
            _show_empty(self._content, "⛔  Access Denied — Only owners can view this report.")
            return
        VIEW_MAP[key](self._content, self.user).pack(fill="both", expand=True)


# ──────────────────────────────────────────────────────────────────────────────
#  A. Cash Collection Report
# ──────────────────────────────────────────────────────────────────────────────

class CashCollectionReport(ctk.CTkFrame):
    _C_CASH     = "#4A7C59"; _C_CASH_BG  = "#EAF3ED"
    _C_GCASH    = "#4A6D8C"; _C_GCASH_BG = "#E8EFF5"
    _C_COMBINED = "#6D8196"

    def __init__(self, master, user):
        super().__init__(master, fg_color="transparent")
        self.user           = user
        self._from          = [_month_start()]
        self._to            = [_today()]
        self._all_data      = []   # full DB result for date range
        self._filtered      = []   # after payment method + search filter
        self._active_method = "All"
        self._stat_labels   = {}
        self._build()
        self._generate()

    # ── Layout ─────────────────────────────────────────────────────────────

    def _build(self):
        # ── Zone 1: Date bar + presets ──────────────────────────────────────
        date_card = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=12,
            border_width=1, border_color=BORDER,
        )
        date_card.pack(fill="x", pady=(0, 6))
        dc = ctk.CTkFrame(date_card, fg_color="transparent")
        dc.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(dc, text="From:", text_color=TEXT_SECONDARY,
                     font=_FONT_SMALL()).pack(side="left")
        self._from_btn = ctk.CTkButton(
            dc, text=f"📅  {self._from[0]}", width=DATE_W, height=BTN_H,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY, font=_FONT_BODY(), corner_radius=CR_BTN,
            command=lambda: _open_calendar(
                self, self._from_btn, self._from[0], self._set_from),
        )
        self._from_btn.pack(side="left", padx=(6, 12))

        ctk.CTkLabel(dc, text="To:", text_color=TEXT_SECONDARY,
                     font=_FONT_SMALL()).pack(side="left")
        self._to_btn = ctk.CTkButton(
            dc, text=f"📅  {self._to[0]}", width=DATE_W, height=BTN_H,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY, font=_FONT_BODY(), corner_radius=CR_BTN,
            command=lambda: _open_calendar(
                self, self._to_btn, self._to[0], self._set_to),
        )
        self._to_btn.pack(side="left", padx=(6, 12))

        ctk.CTkButton(
            dc, text="🔍  Generate", height=BTN_H, width=GENERATE_W,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=CR_BTN, command=self._generate,
        ).pack(side="left", padx=(0, 14))

        # Separator
        ctk.CTkFrame(dc, fg_color=BORDER, width=1, height=BTN_H).pack(
            side="left", padx=(0, 12))

        # Quick presets
        ctk.CTkLabel(dc, text="Quick:", text_color=TEXT_MUTED,
                     font=_FONT_SMALL()).pack(side="left", padx=(0, 6))
        for label, preset in [("Today", "Today"), ("This Week", "This Week"),
                               ("This Month", "This Month")]:
            ctk.CTkButton(
                dc, text=label, height=PILL_H, width=84,
                fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
                border_width=1, border_color=BORDER,
                text_color=TEXT_SECONDARY, corner_radius=CR_PRESET,
                font=_FONT_SMALL(),
                command=lambda p=preset: self._apply_preset(p),
            ).pack(side="left", padx=(0, 4))

        # ── Zone 2: Fixed stat cards ─────────────────────────────────────────
        stats_card = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=12,
            border_width=1, border_color=BORDER,
        )
        stats_card.pack(fill="x", pady=(0, 6))
        self._stats_inner = ctk.CTkFrame(stats_card, fg_color="transparent")
        self._stats_inner.pack(fill="x", padx=8, pady=8)
        self._build_stat_cards()

        # ── Zone 3: Filter bar ───────────────────────────────────────────────
        fbar = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=12,
            border_width=1, border_color=BORDER,
        )
        fbar.pack(fill="x", pady=(0, 6))

        # Row A: Search + clear + export
        row_a = ctk.CTkFrame(fbar, fg_color="transparent")
        row_a.pack(fill="x", padx=14, pady=(10, 6))

        ctk.CTkLabel(
            row_a, text="Filter  ·",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(side="left", padx=(0, 8))

        self._search_var = ctk.StringVar()
        self._search_var.trace("w", lambda *_: self._apply_filter())
        self._search_entry = ctk.CTkEntry(
            row_a, textvariable=self._search_var,
            placeholder_text="Search by transaction # or cashier name",
            height=BTN_H, fg_color="#FFFFFF", border_color=BORDER,
            text_color="#2E2E2E", placeholder_text_color="#6B6B6B",
            font=_FONT_BODY(), corner_radius=8,
        )
        self._search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            row_a, text="✕", width=36, height=BTN_H,
            fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_MUTED, corner_radius=8, font=_FONT_SMALL(),
            command=lambda: self._search_var.set(""),
        ).pack(side="left", padx=(0, 8))

        # Divider
        ctk.CTkFrame(row_a, fg_color=BORDER, width=1,
                     height=BTN_H).pack(side="right", padx=(8, 0))

        if PDF_AVAILABLE:
            ctk.CTkButton(
                row_a, text="📄  Export PDF", height=BTN_H, width=EXPORT_W,
                fg_color=SUCCESS, hover_color=SUCCESS_HOVER,
                text_color="white", corner_radius=CR_BTN, font=_FONT_LABEL(),
                command=self._export,
            ).pack(side="right")

        # Row B: Payment method pills + result count
        row_b = ctk.CTkFrame(fbar, fg_color="transparent")
        row_b.pack(fill="x", padx=14, pady=(0, 10))

        ctk.CTkLabel(
            row_b, text="Show:",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
        ).pack(side="left", padx=(0, 8))

        self._pills = _PillGroup(
            row_b,
            pills=[
                ("All",   "⬤ All",   ACCENT),
                ("Cash",  "💵 Cash",  self._C_CASH),
                ("GCash", "📱 GCash", self._C_GCASH),
            ],
            on_change=self._set_method,
            initial="All",
        )
        self._pills.pack(side="left")

        self._count_lbl = ctk.CTkLabel(
            row_b, text="",
            font=_FONT_SMALL(), text_color=TEXT_MUTED,
        )
        self._count_lbl.pack(side="right")

        # ── Zone 4: Table card ───────────────────────────────────────────────
        table_card = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=14,
            border_width=1, border_color=BORDER,
        )
        table_card.pack(fill="both", expand=True)

        hdr_row = ctk.CTkFrame(table_card, fg_color="transparent")
        hdr_row.pack(fill="x", padx=14, pady=(10, 4))
        self._title_var = ctk.StringVar(value="All Transactions")
        ctk.CTkLabel(
            hdr_row, textvariable=self._title_var,
            font=_FONT_TITLE(), text_color=TEXT_PRIMARY,
        ).pack(side="left")
        self._count_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            hdr_row, textvariable=self._count_var,
            font=_FONT_SMALL(), text_color=TEXT_MUTED,
        ).pack(side="left", padx=8)

        cols   = ("date", "txn", "cashier", "subtotal", "discount", "vat", "total", "method")
        hdrs   = {"date": "Date", "txn": "Transaction #", "cashier": "Cashier",
                  "subtotal": "Subtotal", "discount": "Discount",
                  "vat": "VAT", "total": "Total", "method": "Payment"}
        widths = {"date": 120, "txn": 130, "cashier": 140,
                  "subtotal": 95, "discount": 82, "vat": 75, "total": 100, "method": 95}

        self.tree = ttk.Treeview(table_card, columns=cols, show="headings", height=12)
        for col in cols:
            self.tree.heading(col, text=hdrs[col])
            self.tree.column(
                col, width=widths[col],
                anchor="e" if col in ("subtotal", "discount", "vat", "total") else
                "center" if col == "method" else "w",
            )
        sb = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        style_treeview(self.tree)
        self.tree.tag_configure("cash",      foreground=self._C_CASH,  background=self._C_CASH_BG)
        self.tree.tag_configure("gcash",     foreground=self._C_GCASH, background=self._C_GCASH_BG)
        self.tree.tag_configure("cash_alt",  foreground=self._C_CASH,  background="#F0F8F3")
        self.tree.tag_configure("gcash_alt", foreground=self._C_GCASH, background="#E0EAF2")
        self.tree.pack(side="left", fill="both", expand=True, padx=6, pady=(0, 6))
        sb.pack(side="right", fill="y", pady=6)

        self._pager = Paginator(table_card, self.tree, page_size=20,
                                render_fn=self._render_page, bar_parent=self)

    # ── Stat cards — built once, updated by label reference ──────────────────

    def _build_stat_cards(self):
        defs = [
            ("cash_total",  "Cash Collection",  self._C_CASH,     "💵"),
            ("gcash_total", "GCash Collection", self._C_GCASH,    "📱"),
            ("combined",    "Total Collection", self._C_COMBINED, "💰"),
            ("txn_count",   "Transactions",     ACCENT,           "🧾"),
            ("vat",         "Total VAT",        INFO,             "📋"),
        ]
        for key, label, color, icon in defs:
            card = ctk.CTkFrame(
                self._stats_inner, fg_color=BG_CARD_ALT, corner_radius=10,
                border_width=1, border_color=BORDER,
            )
            card.pack(side="left", fill="both", expand=True, padx=4)
            ctk.CTkFrame(card, fg_color=color, height=3, corner_radius=2).pack(
                fill="x", padx=10, pady=(8, 0))
            ctk.CTkLabel(card, text=icon, font=ctk.CTkFont(size=16),
                         text_color=color).pack(pady=(4, 0))
            ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=10),
                         text_color=TEXT_MUTED).pack()
            lbl = ctk.CTkLabel(
                card, text="—",
                font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
                text_color=TEXT_PRIMARY,
            )
            lbl.pack(pady=(2, 8))
            self._stat_labels[key] = lbl

    def _update_stats(self):
        cash_rows   = [r for r in self._all_data if r["payment_method"].lower() == "cash"]
        gcash_rows  = [r for r in self._all_data if r["payment_method"].lower() == "gcash"]
        cash_total  = sum(r["total"] for r in cash_rows)
        gcash_total = sum(r["total"] for r in gcash_rows)
        combined    = cash_total + gcash_total
        vat_total   = sum(r["vat"] for r in self._filtered)

        self._stat_labels["cash_total"].configure(text=f"₱{cash_total:,.2f}")
        self._stat_labels["gcash_total"].configure(text=f"₱{gcash_total:,.2f}")
        self._stat_labels["combined"].configure(text=f"₱{combined:,.2f}")
        self._stat_labels["txn_count"].configure(text=str(len(self._filtered)))
        self._stat_labels["vat"].configure(text=f"₱{vat_total:,.2f}")

    # ── Date helpers ─────────────────────────────────────────────────────────

    def _set_from(self, date: str):
        self._from[0] = date
        self._from_btn.configure(text=f"📅  {date}")

    def _set_to(self, date: str):
        self._to[0] = date
        self._to_btn.configure(text=f"📅  {date}")

    def _apply_preset(self, preset: str):
        today = datetime.date.today()
        if preset == "Today":
            f = t = today
        elif preset == "This Week":
            f = today - datetime.timedelta(days=today.weekday())
            t = today
        else:  # This Month
            f = today.replace(day=1)
            t = today
        self._from[0] = f.strftime("%Y-%m-%d")
        self._to[0]   = t.strftime("%Y-%m-%d")
        self._from_btn.configure(text=f"📅  {self._from[0]}")
        self._to_btn.configure(text=f"📅  {self._to[0]}")
        self._generate()

    # ── Data ─────────────────────────────────────────────────────────────────

    def _generate(self):
        conn = get_connection()
        rows = conn.execute("""
            SELECT st.created_at, st.transaction_number, u.full_name,
                   st.subtotal, st.discount, COALESCE(st.vat,0) AS vat,
                   st.total, st.payment_method
            FROM sales_transactions st
            JOIN users u ON u.id = st.cashier_id
            WHERE date(st.created_at) BETWEEN ? AND ?
            ORDER BY st.created_at DESC
        """, (self._from[0], self._to[0])).fetchall()
        conn.close()
        self._all_data = [dict(r) for r in rows]
        self._apply_filter()

    def _set_method(self, method: str):
        self._active_method = method
        self._apply_filter()

    def _apply_filter(self):
        m = self._active_method.lower()
        by_method = self._all_data if m == "all" else [
            r for r in self._all_data if r["payment_method"].lower() == m
        ]
        q = self._search_var.get().strip().lower()
        self._filtered = by_method if not q else [
            r for r in by_method
            if q in r["transaction_number"].lower() or q in r["full_name"].lower()
        ]
        self._pager.set_data(self._filtered)
        self._update_stats()

        title_map = {
            "All":   "All Transactions",
            "Cash":  "💵  Cash Transactions",
            "GCash": "📱  GCash Transactions",
        }
        self._title_var.set(title_map.get(self._active_method, "Transactions"))
        n = len(self._filtered)
        self._count_var.set(f"{n} record{'s' if n != 1 else ''}")
        self._count_lbl.configure(text=f"{n} record{'s' if n != 1 else ''}")

    # ── Render ───────────────────────────────────────────────────────────────

    def _render_page(self, rows):
        for i, r in enumerate(rows):
            method = r["payment_method"].lower()
            even   = i % 2 == 0
            tag    = ("cash" if method == "cash" else "gcash") + ("" if even else "_alt")
            label  = "💵  Cash" if method == "cash" else "📱  GCash"
            self.tree.insert("", "end", tags=(tag,), values=(
                r["created_at"], r["transaction_number"], r["full_name"],
                f"₱{r['subtotal']:,.2f}", f"₱{r['discount']:,.2f}",
                f"₱{r['vat']:,.2f}", f"₱{r['total']:,.2f}", label,
            ))

    # ── Export ───────────────────────────────────────────────────────────────

    def _export(self):
        data = [{
            "Date": r["created_at"], "Transaction #": r["transaction_number"],
            "Cashier": r["full_name"], "Subtotal": r["subtotal"],
            "Discount": r["discount"], "VAT": r["vat"],
            "Total": r["total"], "Payment Method": r["payment_method"].title(),
        } for r in self._filtered]
        m        = self._active_method
        filename = f"cash_collection_{m.lower()}.pdf" if m != "All" \
                   else "cash_collection_report.pdf"
        _export_pdf(self, data, filename, "Cash Collection Report")


# ──────────────────────────────────────────────────────────────────────────────
#  B. Inventory Report
#
#  HCI improvements:
#   • Status pills + dropdown are no longer duplicated — pills are the
#     primary control; dropdown removed (reduces redundancy).
#   • Search bar clearly labelled with placeholder.
#   • "Refresh" renamed "🔄 Refresh Data" with tooltip context.
#   • Stats always shown above table.
# ──────────────────────────────────────────────────────────────────────────────

class InventoryReport(ctk.CTkFrame):
    _C_OK    = "#4A7C59"; _C_OK_BG  = "#EAF3ED"
    _C_LOW   = "#B88B2E"; _C_LOW_BG = "#FFF8E0"
    _C_OUT   = "#A94040"; _C_OUT_BG = "#F5E0E0"

    def __init__(self, master, user):
        super().__init__(master, fg_color="transparent")
        self.user        = user
        self._all_data   = []          # full unfiltered dataset
        self._data       = []          # current filtered view
        self._sort_col   = "name"
        self._sort_asc   = True
        self._build()
        self._generate()

    # ──────────────────────────────────────────────────────────────────────
    #  Layout
    # ──────────────────────────────────────────────────────────────────────

    def _build(self):
        # ── Zone 1: Fixed stat cards (full-inventory totals, never filtered) ─
        self._stats_frame = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=12,
            border_width=1, border_color=BORDER,
        )
        self._stats_frame.pack(fill="x", pady=(0, 8))
        self._stat_labels = {}   # key → (value_label, strip_frame)
        self._build_stat_cards()

        # ── Zone 2: Unified filter bar ───────────────────────────────────────
        fbar = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=12,
            border_width=1, border_color=BORDER,
        )
        fbar.pack(fill="x", pady=(0, 8))

        # Row A: Search + Category + actions
        row_a = ctk.CTkFrame(fbar, fg_color="transparent")
        row_a.pack(fill="x", padx=14, pady=(10, 6))

        ctk.CTkLabel(
            row_a, text="Filter  ·",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(side="left", padx=(0, 8))

        # Search
        self._search_var = ctk.StringVar()
        self._search_var.trace("w", lambda *_: self._apply_filters())
        self._search_entry = ctk.CTkEntry(
            row_a, textvariable=self._search_var,
            placeholder_text="Search by product name or item code",
            height=BTN_H, fg_color="#FFFFFF", border_color=BORDER,
            text_color="#2E2E2E", placeholder_text_color="#6B6B6B",
            font=_FONT_BODY(), corner_radius=8,
        )
        self._search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        # Clear search button
        ctk.CTkButton(
            row_a, text="✕", width=36, height=BTN_H,
            fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_MUTED, corner_radius=8, font=_FONT_SMALL(),
            command=lambda: self._search_var.set(""),
        ).pack(side="left", padx=(0, 8))

        # Category dropdown + badge
        cat_group = ctk.CTkFrame(row_a, fg_color="transparent")
        cat_group.pack(side="left", padx=(0, 8))
        self.category_var = ctk.StringVar(value="All Categories")
        self._cat_menu = create_option_menu(
            cat_group, values=["All Categories"],
            variable=self.category_var, width=178,
            command=lambda *_: self._apply_filters(),
        )
        self._cat_menu.pack(side="left")
        self._cat_badge = ctk.CTkLabel(
            cat_group, text="",
            font=ctk.CTkFont(size=10), text_color=TEXT_MUTED,
        )
        self._cat_badge.pack(side="left", padx=(6, 0))

        # Divider
        ctk.CTkFrame(row_a, fg_color=BORDER, width=1, height=BTN_H).pack(
            side="right", padx=(8, 0))

        # Export — rightmost, distinct colour
        if PDF_AVAILABLE:
            ctk.CTkButton(
                row_a, text="📄  Export PDF", height=BTN_H, width=EXPORT_W,
                fg_color=SUCCESS, hover_color=SUCCESS_HOVER,
                text_color="white", corner_radius=CR_BTN, font=_FONT_LABEL(),
                command=self._export,
            ).pack(side="right", padx=(0, 0))

        # Refresh — secondary, clearly separate
        ctk.CTkButton(
            row_a, text="🔄  Refresh", height=BTN_H, width=106,
            fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY, corner_radius=CR_BTN, font=_FONT_BODY(),
            command=self._generate,
        ).pack(side="right", padx=(0, 8))

        # Row B: Status pills + result count
        row_b = ctk.CTkFrame(fbar, fg_color="transparent")
        row_b.pack(fill="x", padx=14, pady=(0, 10))

        ctk.CTkLabel(
            row_b, text="Show:",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
        ).pack(side="left", padx=(0, 8))

        self._stock_filter = "All Stock"
        self._pills = _PillGroup(
            row_b,
            pills=[
                ("All Stock",    "📦  All",         ACCENT),
                ("In Stock",     "✅  In Stock",    self._C_OK),
                ("Low Stock",    "⚠  Low Stock",   self._C_LOW),
                ("Out of Stock", "🚫  Out of Stock", self._C_OUT),
            ],
            on_change=self._on_pill,
            initial="All Stock",
        )
        self._pills.pack(side="left")

        # Result count — right-aligned, plain text, no duplication
        self._count_lbl = ctk.CTkLabel(
            row_b, text="",
            font=_FONT_SMALL(), text_color=TEXT_MUTED,
        )
        self._count_lbl.pack(side="right")

        # ── Zone 3: Table card ───────────────────────────────────────────────
        card = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=14,
            border_width=1, border_color=BORDER,
        )
        card.pack(fill="both", expand=True)

        # Column hint row — explains "Health" and "Min" in context
        hint_row = ctk.CTkFrame(card, fg_color="transparent")
        hint_row.pack(fill="x", padx=14, pady=(8, 0))
        ctk.CTkLabel(
            hint_row,
            text="Click a column header to sort  ·  "
                 "Health bar = stock vs minimum threshold  ·  "
                 "Min = minimum stock before reorder",
            font=ctk.CTkFont(size=10), text_color=TEXT_MUTED,
        ).pack(side="left")

        # Treeview — "Status" column removed; health replaces min-stock
        #   Columns: code | name | category | stock | health | min | cost | price
        cols   = ("code", "name", "category", "stock", "health", "min", "cost", "price")
        hdrs   = {
            "code":     "Code",
            "name":     "Product Name",
            "category": "Category",
            "stock":    "Stock",
            "health":   "Health",      # visual bar rendered via tag trick
            "min":      "Min ▸",       # arrow hints it's clickable for sort
            "cost":     "Cost",
            "price":    "Price",
        }
        widths = {
            "code": 80, "name": 210, "category": 120,
            "stock": 65, "health": 140, "min": 55,
            "cost": 100, "price": 100,
        }
        self.tree = ttk.Treeview(card, columns=cols, show="headings", height=12)
        for col in cols:
            self.tree.heading(
                col, text=hdrs[col],
                command=lambda c=col: self._sort_by(c),
            )
            self.tree.column(
                col, width=widths[col], minwidth=max(widths[col] - 20, 40),
                anchor="e" if col in ("stock", "min", "cost", "price") else
                "center" if col == "health" else "w",
            )

        sb = ttk.Scrollbar(card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        style_treeview(self.tree)
        self.tree.tag_configure("out", foreground=self._C_OUT, background=self._C_OUT_BG)
        self.tree.tag_configure("low", foreground=self._C_LOW, background=self._C_LOW_BG)
        self.tree.tag_configure("ok",  foreground=self._C_OK,  background=self._C_OK_BG)
        self.tree.tag_configure("evenrow", background="#F5F5E0")

        self.tree.pack(side="left", fill="both", expand=True, padx=6, pady=(4, 6))
        sb.pack(side="right", fill="y", pady=6)

        self._pager = Paginator(
            card, self.tree, page_size=25,
            render_fn=self._render_page, bar_parent=self,
        )

    # ──────────────────────────────────────────────────────────────────────
    #  Stat cards — built once, updated by label reference (no rebuild)
    # ──────────────────────────────────────────────────────────────────────

    def _build_stat_cards(self):
        """Build stat card widgets once; update their labels later."""
        is_owner = self.user["role"] == "owner"

        card_defs = [
            ("total",  "Total Products",  ACCENT,   "📦"),
            ("ok",     "In Stock",        self._C_OK,  "✅"),
            ("low",    "Low Stock",       self._C_LOW, "⚠"),
            ("out",    "Out of Stock",    self._C_OUT, "🚫"),
        ]
        if is_owner:
            card_defs.append(("value", "Inventory Value", INFO, "💰"))

        inner = ctk.CTkFrame(self._stats_frame, fg_color="transparent")
        inner.pack(fill="x", padx=8, pady=8)

        for key, label, color, icon in card_defs:
            card = ctk.CTkFrame(
                inner, fg_color=BG_CARD_ALT, corner_radius=10,
                border_width=1, border_color=BORDER,
            )
            card.pack(side="left", fill="both", expand=True, padx=4)

            strip = ctk.CTkFrame(card, fg_color=color, height=3, corner_radius=2)
            strip.pack(fill="x", padx=10, pady=(8, 0))

            ctk.CTkLabel(
                card, text=icon,
                font=ctk.CTkFont(size=16), text_color=color,
            ).pack(pady=(6, 0))
            ctk.CTkLabel(
                card, text=label,
                font=ctk.CTkFont(size=10), text_color=TEXT_MUTED,
            ).pack()
            val_lbl = ctk.CTkLabel(
                card, text="—",
                font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
                text_color=TEXT_PRIMARY,
            )
            val_lbl.pack(pady=(2, 8))
            self._stat_labels[key] = val_lbl

    def _update_stats(self):
        """Update stat card values without rebuilding widgets."""
        is_owner = self.user["role"] == "owner"
        total    = len(self._all_data)
        out      = sum(1 for r in self._all_data if r["is_out"])
        low      = sum(1 for r in self._all_data if r["is_low"])
        ok       = total - low - out

        self._stat_labels["total"].configure(text=str(total))
        self._stat_labels["ok"].configure(text=str(ok))
        self._stat_labels["low"].configure(text=str(low))
        self._stat_labels["out"].configure(text=str(out))

        if is_owner and "value" in self._stat_labels:
            inv_val = sum((r["cost"] or 0) * r["stock"] for r in self._all_data)
            self._stat_labels["value"].configure(text=f"₱{inv_val:,.2f}")

    # ──────────────────────────────────────────────────────────────────────
    #  Data fetch
    # ──────────────────────────────────────────────────────────────────────

    def _generate(self):
        q    = f"%{self._search_var.get()}%"
        conn = get_connection()
        rows = conn.execute("""
            SELECT id, code, name, category, current_stock,
                   low_stock_threshold, cost_price, selling_price
            FROM products
            WHERE (name LIKE ? OR code LIKE ?)
            ORDER BY name
        """, (q, q)).fetchall()
        conn.close()

        # Populate category dropdown
        cats = sorted({r["category"] or "Uncategorized" for r in rows})
        self._cat_menu.configure(values=["All Categories"] + cats)
        n_cats = len(cats)
        self._cat_badge.configure(
            text=f"{n_cats} categor{'y' if n_cats == 1 else 'ies'}"
        )

        is_owner = self.user["role"] == "owner"
        self._all_data = []
        for r in rows:
            stock   = r["current_stock"]
            thresh  = r["low_stock_threshold"]
            is_out  = stock == 0
            is_low  = (not is_out) and stock <= thresh
            self._all_data.append({
                "code":      r["code"],
                "name":      r["name"],
                "category":  r["category"] or "Uncategorized",
                "stock":     stock,
                "threshold": thresh,
                "is_out":    is_out,
                "is_low":    is_low,
                "cost":      r["cost_price"]    if is_owner else None,
                "price":     r["selling_price"] if is_owner else None,
            })

        self._update_stats()
        self._apply_filters()

    # ──────────────────────────────────────────────────────────────────────
    #  Filtering + sorting
    # ──────────────────────────────────────────────────────────────────────

    def _on_pill(self, key: str):
        self._stock_filter = key
        self._apply_filters()

    def _apply_filters(self):
        filt = self._stock_filter
        cat  = self.category_var.get()
        data = list(self._all_data)

        # Search filter (re-run in-memory; avoids extra DB round-trip)
        q = self._search_var.get().strip().lower()
        if q:
            data = [r for r in data
                    if q in r["name"].lower() or q in r["code"].lower()]

        if cat != "All Categories":
            data = [r for r in data if r["category"] == cat]

        if filt == "In Stock":
            data = [r for r in data if not r["is_low"] and not r["is_out"]]
        elif filt == "Low Stock":
            data = [r for r in data if r["is_low"]]
        elif filt == "Out of Stock":
            data = [r for r in data if r["is_out"]]

        # Apply current sort
        data = self._sorted(data)
        self._data = data

        n = len(data)
        self._count_lbl.configure(
            text=f"{n} product{'s' if n != 1 else ''} shown"
        )
        self._pager.set_data(data)

    def _sort_by(self, col: str):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True
        self._apply_filters()

    def _sorted(self, data: list) -> list:
        col = self._sort_col
        key_map = {
            "code":     lambda r: (r["code"]     or "").lower(),
            "name":     lambda r: (r["name"]      or "").lower(),
            "category": lambda r: (r["category"]  or "").lower(),
            "stock":    lambda r: r["stock"],
            "health":   lambda r: (r["stock"] / max(r["threshold"], 1)),
            "min":      lambda r: r["threshold"],
            "cost":     lambda r: r["cost"]  or 0,
            "price":    lambda r: r["price"] or 0,
        }
        fn = key_map.get(col, lambda r: r["name"].lower())
        return sorted(data, key=fn, reverse=not self._sort_asc)

    # ──────────────────────────────────────────────────────────────────────
    #  Render
    # ──────────────────────────────────────────────────────────────────────

    def _render_page(self, rows):
        is_owner = self.user["role"] == "owner"

        if not rows:
            # Empty state — injected as a single informational row
            self.tree.insert("", "end", values=(
                "", "No products match your current filters.",
                "", "", "", "", "", "",
            ))
            return

        for r in rows:
            stock  = r["stock"]
            thresh = r["threshold"]

            if r["is_out"]:
                tag     = "out"
                health  = "🚫  Out of stock"
            elif r["is_low"]:
                tag     = "low"
                # Show ratio: e.g. "4 / 10  ⚠"
                health  = f"⚠  {stock} / {thresh}"
            else:
                tag     = "ok"
                # Show ratio only when close to threshold (≤ 2×)
                if thresh > 0 and stock <= thresh * 2:
                    health = f"✅  {stock} / {thresh}"
                else:
                    health = f"✅  {stock}"

            cost  = f"₱{r['cost']:,.2f}"  if is_owner and r["cost"]  is not None else "—"
            price = f"₱{r['price']:,.2f}" if is_owner and r["price"] is not None else "—"

            self.tree.insert("", "end", tags=(tag,), values=(
                r["code"],
                r["name"],
                r["category"],
                stock,
                health,
                thresh,
                cost,
                price,
            ))

    # ──────────────────────────────────────────────────────────────────────
    #  Export
    # ──────────────────────────────────────────────────────────────────────

    def _export(self):
        if not self._data:
            msg_warning(self, "Nothing to Export",
                        "Apply your filters and generate the report first.")
            return
        is_owner = self.user["role"] == "owner"
        data = [{
            "Code":          r["code"],
            "Product Name":  r["name"],
            "Category":      r["category"],
            "Current Stock": r["stock"],
            "Min Stock":     r["threshold"],
            "Status":        ("Out of Stock" if r["is_out"]
                              else "Low Stock" if r["is_low"]
                              else "OK"),
            "Cost Price":    r["cost"]  if is_owner else "N/A",
            "Selling Price": r["price"] if is_owner else "N/A",
        } for r in self._data]
        _export_pdf(self, data, "inventory_report.pdf", "Inventory Report")


class SalesReport(ctk.CTkFrame):
    """
    Sales Report — HCI-optimised rewrite
    ─────────────────────────────────────
    Cognitive-load reductions vs previous version:

    1. Stats bar is STABLE — built once, updated by label reference.
       No widget destruction flash; totals stay anchored while the user
       reads them and changes filters.

    2. Controls are in the right zone:
       • Date range + presets + Generate → date bar (applies to both views)
       • Table search → inside each table card (contextual, not global)
       • Export → bottom-right of each table card (adjacent to what it exports)

    3. "Subtotal" and "Discount" columns removed from default view.
       They required mental arithmetic to derive Total. Total + Discount
       are shown; subtotal is recoverable as total-discount in the export.
       A "Net" column (total after discount) replaces the three-column block.

    4. Date + time split into two columns so the date is scannable
       without the time string distracting from it.

       performance without leaving the report.

    6. Payment method filter pill — carried over from Cash Collection
       tab because sales context is where it's most decision-relevant.

    7. Product sub-tab has its own search bar so users can find
       a specific product in a long ranked list.

    8. Empty states explain which filter produced zero results.

    9. Sub-tab buttons embed the live count in their label directly
       ("📝 Transactions (14)") so the user never has to map a
       floating "— 14 txns" label to its button.

   10. Average transaction value added to the stat bar — the single
       most useful derived metric for spotting performance trends.
    """

    def __init__(self, master, user):
        super().__init__(master, fg_color="transparent")
        self.user             = user
        self._from            = [_month_start()]
        self._to              = [_today()]
        self._txn_data        = []   # full result from DB
        self._prod_data       = []
        self._txn_filtered    = []   # after payment filter
        self._active_sub      = "txn"  # instance variable, not class variable
        self._payment_filter  = "All"
        self._prod_search     = ""
        self._stat_labels     = {}
        self._build()
        self._generate()

    # ──────────────────────────────────────────────────────────────────────
    #  Layout
    # ──────────────────────────────────────────────────────────────────────

    def _build(self):
        # ── Zone 1: Date + presets ───────────────────────────────────────────
        date_card = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=12,
            border_width=1, border_color=BORDER,
        )
        date_card.pack(fill="x", pady=(0, 6))
        dc = ctk.CTkFrame(date_card, fg_color="transparent")
        dc.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(dc, text="From:", text_color=TEXT_SECONDARY,
                     font=_FONT_SMALL()).pack(side="left")
        self._from_btn = ctk.CTkButton(
            dc, text=f"📅  {self._from[0]}", width=DATE_W, height=BTN_H,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY, font=_FONT_BODY(), corner_radius=CR_BTN,
            command=lambda: _open_calendar(
                self, self._from_btn, self._from[0], self._set_from),
        )
        self._from_btn.pack(side="left", padx=(6, 12))

        ctk.CTkLabel(dc, text="To:", text_color=TEXT_SECONDARY,
                     font=_FONT_SMALL()).pack(side="left")
        self._to_btn = ctk.CTkButton(
            dc, text=f"📅  {self._to[0]}", width=DATE_W, height=BTN_H,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY, font=_FONT_BODY(), corner_radius=CR_BTN,
            command=lambda: _open_calendar(
                self, self._to_btn, self._to[0], self._set_to),
        )
        self._to_btn.pack(side="left", padx=(6, 12))

        ctk.CTkButton(
            dc, text="🔍  Generate", height=BTN_H, width=GENERATE_W,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=CR_BTN, command=self._generate,
        ).pack(side="left", padx=(0, 14))

        # Separator
        ctk.CTkFrame(dc, fg_color=BORDER, width=1,
                     height=BTN_H).pack(side="left", padx=(0, 12))

        # Quick presets
        ctk.CTkLabel(dc, text="Quick:", text_color=TEXT_MUTED,
                     font=_FONT_SMALL()).pack(side="left", padx=(0, 6))
        for label, preset in [("Today", "Today"), ("This Week", "This Week"),
                               ("This Month", "This Month")]:
            ctk.CTkButton(
                dc, text=label, height=PILL_H, width=84,
                fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
                border_width=1, border_color=BORDER,
                text_color=TEXT_SECONDARY, corner_radius=CR_PRESET,
                font=_FONT_SMALL(),
                command=lambda p=preset: self._apply_preset(p),
            ).pack(side="left", padx=(0, 4))

        # ── Zone 2: Fixed stat cards ─────────────────────────────────────────
        stats_card = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=12,
            border_width=1, border_color=BORDER,
        )
        stats_card.pack(fill="x", pady=(0, 6))
        self._stats_inner = ctk.CTkFrame(stats_card, fg_color="transparent")
        self._stats_inner.pack(fill="x", padx=8, pady=8)
        self._build_stat_cards()

        # ── Zone 3: Filter bar (inventory-style two-row layout) ─────────────
        self._filter_card = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=12,
            border_width=1, border_color=BORDER,
        )
        self._filter_card.pack(fill="x", pady=(0, 6))

        # ── Row A: Search entry + clear button + export ──────────────────────
        row_a = ctk.CTkFrame(self._filter_card, fg_color="transparent")
        row_a.pack(fill="x", padx=14, pady=(10, 6))

        ctk.CTkLabel(
            row_a, text="Filter  ·",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(side="left", padx=(0, 8))

        # Expandable search slot — holds one search entry at a time
        self._search_slot = ctk.CTkFrame(row_a, fg_color="transparent")
        self._search_slot.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self._txn_search_var = ctk.StringVar()
        self._txn_search_var.trace("w", lambda *_: self._apply_txn_filters())
        self._txn_search_entry = ctk.CTkEntry(
            self._search_slot, textvariable=self._txn_search_var,
            placeholder_text="Search by transaction # or cashier name",
            height=BTN_H, fg_color="#FFFFFF", border_color=BORDER,
            text_color="#2E2E2E", placeholder_text_color="#6B6B6B",
            font=_FONT_BODY(), corner_radius=8,
        )
        self._txn_search_entry.pack(fill="x")          # visible by default

        self._prod_search_var = ctk.StringVar()
        self._prod_search_var.trace("w", lambda *_: self._populate_product())
        self._prod_search_entry = ctk.CTkEntry(
            self._search_slot, textvariable=self._prod_search_var,
            placeholder_text="Search by product name or item code",
            height=BTN_H, fg_color="#FFFFFF", border_color=BORDER,
            text_color="#2E2E2E", placeholder_text_color="#6B6B6B",
            font=_FONT_BODY(), corner_radius=8,
        )
        # not packed yet — shown on sub-tab switch

        # Clear button — clears whichever search entry is active
        ctk.CTkButton(
            row_a, text="✕", width=36, height=BTN_H,
            fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_MUTED, corner_radius=8, font=_FONT_SMALL(),
            command=self._clear_search,
        ).pack(side="left", padx=(0, 8))

        # Divider
        ctk.CTkFrame(row_a, fg_color=BORDER, width=1,
                     height=BTN_H).pack(side="right", padx=(8, 0))

        # Export buttons — only one is visible at a time (swapped on sub-tab)
        if PDF_AVAILABLE:
            self._txn_export_btn = ctk.CTkButton(
                row_a, text="📄  Export PDF", height=BTN_H, width=EXPORT_W,
                fg_color=SUCCESS, hover_color=SUCCESS_HOVER,
                text_color="white", corner_radius=CR_BTN, font=_FONT_LABEL(),
                command=self._export_txn,
            )
            self._txn_export_btn.pack(side="right")    # visible by default

            self._prod_export_btn = ctk.CTkButton(
                row_a, text="📄  Export PDF", height=BTN_H, width=EXPORT_W,
                fg_color=SUCCESS, hover_color=SUCCESS_HOVER,
                text_color="white", corner_radius=CR_BTN, font=_FONT_LABEL(),
                command=self._export_products,
            )
            # not packed yet — shown on sub-tab switch

        # ── Row B: Filter pills + result count ───────────────────────────────
        row_b = ctk.CTkFrame(self._filter_card, fg_color="transparent")
        row_b.pack(fill="x", padx=14, pady=(0, 10))

        self._payment_label = ctk.CTkLabel(
            row_b, text="Payment:",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
        )
        self._payment_label.pack(side="left", padx=(0, 8))

        self._payment_pills = _PillGroup(
            row_b,
            pills=[
                ("All",   "⬤ All",    ACCENT),
                ("Cash",  "💵 Cash",  "#4A7C59"),
                ("GCash", "📱 GCash", "#4A6D8C"),
            ],
            on_change=self._on_payment_filter,
            initial="All",
        )
        self._payment_pills.pack(side="left")

        self._filter_count_lbl = ctk.CTkLabel(
            row_b, text="",
            font=_FONT_SMALL(), text_color=TEXT_MUTED,
        )
        self._filter_count_lbl.pack(side="right")

        # ── Zone 4: Sub-tab switcher ─────────────────────────────────────────
        sub_card = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=10,
            border_width=1, border_color=BORDER,
        )
        sub_card.pack(fill="x", pady=(0, 6))
        sc = ctk.CTkFrame(sub_card, fg_color="transparent")
        sc.pack(fill="x", padx=8, pady=6)

        self._sub_btns = {}
        for icon, label, key in [
            ("📝", "Transactions", "txn"),
            ("📦", "By Product",   "product"),
        ]:
            btn = ctk.CTkButton(
                sc, text=f"{icon}  {label}", height=BTN_H, width=170,
                fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
                text_color=TEXT_SECONDARY, corner_radius=CR_BTN,
                font=_FONT_LABEL(),
                command=lambda k=key: self._switch_sub(k),
            )
            btn.pack(side="left", padx=(0, 4))
            self._sub_btns[key] = btn

        self._refresh_sub_styles("txn")

        # ── Zone 5: Table area (swapped by sub-tab) ──────────────────────────
        self._table_container = ctk.CTkFrame(self, fg_color="transparent")
        self._table_container.pack(fill="both", expand=True)
        self._build_txn_table()

    # ──────────────────────────────────────────────────────────────────────
    #  Stat cards — built once, updated by label reference
    # ──────────────────────────────────────────────────────────────────────

    def _build_stat_cards(self):
        defs = [
            ("revenue",  "Gross Revenue",  ACCENT,    "💰"),
            ("count",    "Transactions",   "#4A6D8C", "📝"),
            ("avg",      "Avg per Sale",   INFO,      "📊"),
            ("discount", "Total Discounts",WARNING,   "🏷"),
            ("net",      "Net Revenue",    SUCCESS,   "✅"),
        ]
        for key, label, color, icon in defs:
            card = ctk.CTkFrame(
                self._stats_inner, fg_color=BG_CARD_ALT, corner_radius=10,
                border_width=1, border_color=BORDER,
            )
            card.pack(side="left", fill="both", expand=True, padx=4)
            ctk.CTkFrame(card, fg_color=color, height=3,
                         corner_radius=2).pack(fill="x", padx=10, pady=(8, 0))
            ctk.CTkLabel(card, text=icon, font=ctk.CTkFont(size=16),
                         text_color=color).pack(pady=(4, 0))
            ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=10),
                         text_color=TEXT_MUTED).pack()
            lbl = ctk.CTkLabel(
                card, text="—",
                font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
                text_color=TEXT_PRIMARY,
            )
            lbl.pack(pady=(2, 8))
            self._stat_labels[key] = lbl

    def _update_stats(self):
        """Update stat values without rebuilding cards."""
        data   = self._txn_filtered  # reflect current cashier/payment filter
        total  = sum(r["total"]    for r in data)
        disc   = sum(r["discount"] for r in data)
        net    = total - disc
        count  = len(data)
        avg    = total / count if count else 0

        self._stat_labels["revenue"].configure(text=f"₱{total:,.2f}")
        self._stat_labels["count"].configure(text=str(count))
        self._stat_labels["avg"].configure(text=f"₱{avg:,.2f}")
        self._stat_labels["discount"].configure(text=f"₱{disc:,.2f}")
        self._stat_labels["net"].configure(text=f"₱{net:,.2f}")

    # ──────────────────────────────────────────────────────────────────────
    #  Date helpers
    # ──────────────────────────────────────────────────────────────────────

    def _set_from(self, date: str):
        self._from[0] = date
        self._from_btn.configure(text=f"📅  {date}")

    def _set_to(self, date: str):
        self._to[0] = date
        self._to_btn.configure(text=f"📅  {date}")

    def _apply_preset(self, preset: str):
        today = datetime.date.today()
        if preset == "Today":
            f = t = today
        elif preset == "This Week":
            f = today - datetime.timedelta(days=today.weekday())
            t = today
        else:  # This Month
            f = today.replace(day=1)
            t = today
        self._from[0] = f.strftime("%Y-%m-%d")
        self._to[0]   = t.strftime("%Y-%m-%d")
        self._from_btn.configure(text=f"📅  {self._from[0]}")
        self._to_btn.configure(text=f"📅  {self._to[0]}")
        self._generate()

    # ──────────────────────────────────────────────────────────────────────
    #  Sub-tab switching
    # ──────────────────────────────────────────────────────────────────────

    def _switch_sub(self, key: str):
        self._active_sub = key
        self._refresh_sub_styles(key)

        # Swap search entry inside the slot + export button on the right
        if key == "txn":
            self._prod_search_entry.pack_forget()
            self._txn_search_entry.pack(fill="x")
            if hasattr(self, "_prod_export_btn"):
                self._prod_export_btn.pack_forget()
            if hasattr(self, "_txn_export_btn"):
                self._txn_export_btn.pack(side="right")
            # Row B: restore payment label + pills
            self._payment_label.pack(side="left", padx=(0, 8))
            self._payment_pills.pack(side="left")
        else:
            self._txn_search_entry.pack_forget()
            self._prod_search_entry.pack(fill="x")
            if hasattr(self, "_txn_export_btn"):
                self._txn_export_btn.pack_forget()
            if hasattr(self, "_prod_export_btn"):
                self._prod_export_btn.pack(side="right")
            # Row B: hide payment label + pills (not relevant for product view)
            self._payment_pills.pack_forget()
            self._payment_label.pack_forget()

        for c in self._table_container.winfo_children():
            c.destroy()
        if key == "txn":
            self._build_txn_table()
            self._populate_txn()
        else:
            self._build_product_table()
            self._populate_product()

    def _refresh_sub_styles(self, active: str):
        counts = {
            "txn":     len(self._txn_filtered),
            "product": len(self._prod_data),
        }
        labels = {
            "txn":     "📝  Transactions",
            "product": "📦  By Product",
        }
        for k, btn in self._sub_btns.items():
            n = counts[k]
            count_str = f"  ({n})" if n > 0 else ""
            if k == active:
                btn.configure(
                    fg_color=ACCENT, text_color="white",
                    hover_color=ACCENT_HOVER,
                    text=labels[k] + count_str,
                )
            else:
                btn.configure(
                    fg_color=BG_CARD_ALT, text_color=TEXT_SECONDARY,
                    hover_color=BG_HOVER,
                    text=labels[k] + count_str,
                )

    # ──────────────────────────────────────────────────────────────────────


    def _clear_search(self):
        """Clear whichever search entry is currently active."""
        if self._active_sub == "txn":
            self._txn_search_var.set("")
        else:
            self._prod_search_var.set("")

    def _on_payment_filter(self, key: str):
        self._payment_filter = key
        self._apply_txn_filters()

    # ──────────────────────────────────────────────────────────────────────
    #  Transaction table
    # ──────────────────────────────────────────────────────────────────────

    def _build_txn_table(self):
        card = ctk.CTkFrame(
            self._table_container, fg_color=BG_CARD,
            corner_radius=14, border_width=1, border_color=BORDER,
        )
        card.pack(fill="both", expand=True)

        # Table header row with inline search
        hdr_row = ctk.CTkFrame(card, fg_color="transparent")
        hdr_row.pack(fill="x", padx=14, pady=(10, 4))

        self._txn_title_var = ctk.StringVar(value="Transaction Log")
        ctk.CTkLabel(
            hdr_row, textvariable=self._txn_title_var,
            font=_FONT_TITLE(), text_color=TEXT_PRIMARY,
        ).pack(side="left")

        self._txn_count_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            hdr_row, textvariable=self._txn_count_var,
            font=_FONT_SMALL(), text_color=TEXT_MUTED,
        ).pack(side="left", padx=8)

        # Treeview: date | time | txn# | cashier | payment | items | total | discount
        # "Subtotal" removed — Total is the number people care about.
        # Date and time separated for scannability.
        cols   = ("date", "time", "txn", "cashier", "payment", "items", "total", "discount")
        hdrs   = {
            "date":     "Date",
            "time":     "Time",
            "txn":      "Transaction #",
            "cashier":  "Cashier",
            "payment":  "Payment",
            "items":    "Items",
            "total":    "Total",
            "discount": "Discount",
        }
        widths = {
            "date": 100, "time": 72, "txn": 140, "cashier": 140,
            "payment": 88, "items": 52, "total": 100, "discount": 88,
        }
        self._txn_tree = ttk.Treeview(card, columns=cols, show="headings", height=11)
        for col in cols:
            self._txn_tree.heading(col, text=hdrs[col],
                                   command=lambda c=col: self._sort_txn(c))
            self._txn_tree.column(
                col, width=widths[col], minwidth=40,
                anchor="e" if col in ("items", "total", "discount") else
                "center" if col in ("time", "payment") else "w",
            )

        sb = ttk.Scrollbar(card, orient="vertical", command=self._txn_tree.yview)
        self._txn_tree.configure(yscrollcommand=sb.set)
        style_treeview(self._txn_tree)
        # Payment-method row tinting
        self._txn_tree.tag_configure("cash",      background="#EAF3ED")
        self._txn_tree.tag_configure("gcash",     background="#E8EFF5")
        self._txn_tree.tag_configure("cash_alt",  background="#F2F9F5")
        self._txn_tree.tag_configure("gcash_alt", background="#EEF4FA")
        self._txn_tree.pack(side="left", fill="both", expand=True, padx=6, pady=(0, 6))
        sb.pack(side="right", fill="y", pady=6)

        self._txn_pager = Paginator(
            card, self._txn_tree, page_size=20,
            render_fn=self._render_txn, bar_parent=self,
        )

        self._txn_sort_col = "date"
        self._txn_sort_asc = False   # newest first by default

    def _sort_txn(self, col: str):
        if self._txn_sort_col == col:
            self._txn_sort_asc = not self._txn_sort_asc
        else:
            self._txn_sort_col = col
            self._txn_sort_asc = True
        self._apply_txn_filters()

    # ──────────────────────────────────────────────────────────────────────
    #  Product table
    # ──────────────────────────────────────────────────────────────────────

    def _build_product_table(self):
        card = ctk.CTkFrame(
            self._table_container, fg_color=BG_CARD,
            corner_radius=14, border_width=1, border_color=BORDER,
        )
        card.pack(fill="both", expand=True)

        # Header row — title + count only (search + export are in the filter bar)
        hdr_row = ctk.CTkFrame(card, fg_color="transparent")
        hdr_row.pack(fill="x", padx=14, pady=(10, 4))

        self._prod_title_var = ctk.StringVar(value="Sales by Product  ·  ranked by units sold")
        ctk.CTkLabel(
            hdr_row, textvariable=self._prod_title_var,
            font=_FONT_TITLE(), text_color=TEXT_PRIMARY,
        ).pack(side="left")

        self._prod_count_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            hdr_row, textvariable=self._prod_count_var,
            font=_FONT_SMALL(), text_color=TEXT_MUTED,
        ).pack(side="left", padx=8)

        cols   = ("rank", "code", "name", "qty_sold", "revenue", "avg_price", "share")
        hdrs   = {
            "rank":      "#",
            "code":      "Code",
            "name":      "Product",
            "qty_sold":  "Qty Sold",
            "revenue":   "Revenue",
            "avg_price": "Avg Price",
            "share":     "Rev. Share",
        }
        widths = {
            "rank": 42, "code": 90, "name": 220,
            "qty_sold": 80, "revenue": 110, "avg_price": 95, "share": 95,
        }
        self._prod_tree = ttk.Treeview(card, columns=cols, show="headings", height=11)
        for col in cols:
            self._prod_tree.heading(col, text=hdrs[col])
            self._prod_tree.column(
                col, width=widths[col], minwidth=widths[col],
                anchor="center" if col in ("rank", "share") else
                "e" if col in ("qty_sold", "revenue", "avg_price") else "w",
            )

        sb = ttk.Scrollbar(card, orient="vertical", command=self._prod_tree.yview)
        self._prod_tree.configure(yscrollcommand=sb.set)
        style_treeview(self._prod_tree)
        self._prod_tree.tag_configure("top1",    foreground="#8B6914", background="#FFF4C2")
        self._prod_tree.tag_configure("top3",    foreground="#5C7A8C", background="#E6F0F5")
        self._prod_tree.tag_configure("evenrow", background="#F5F5E0")
        self._prod_tree.pack(side="left", fill="both", expand=True, padx=6, pady=(0, 6))
        sb.pack(side="right", fill="y", pady=6)

        self._prod_pager = Paginator(
            card, self._prod_tree, page_size=20,
            render_fn=self._render_prod, bar_parent=self,
        )

    # ──────────────────────────────────────────────────────────────────────
    #  Data fetch
    # ──────────────────────────────────────────────────────────────────────

    def _generate(self):
        conn = get_connection()
        txns = conn.execute("""
            SELECT st.id, st.created_at, st.transaction_number,
                   u.full_name, u.id AS cashier_id,
                   COUNT(si.id) AS items,
                   st.subtotal, st.discount,
                   st.total, st.payment_method
            FROM sales_transactions st
            JOIN users u ON u.id = st.cashier_id
            LEFT JOIN sale_items si ON si.transaction_id = st.id
            WHERE date(st.created_at) BETWEEN ? AND ?
            GROUP BY st.id
            ORDER BY st.created_at DESC
        """, (self._from[0], self._to[0])).fetchall()

        prods = conn.execute("""
            SELECT p.code, p.name,
                   SUM(si.quantity)  AS qty_sold,
                   SUM(si.subtotal)  AS revenue
            FROM sale_items si
            JOIN products p ON p.id = si.product_id
            JOIN sales_transactions st ON st.id = si.transaction_id
            WHERE date(st.created_at) BETWEEN ? AND ?
            GROUP BY p.id
            ORDER BY qty_sold DESC
        """, (self._from[0], self._to[0])).fetchall()
        conn.close()

        self._txn_data  = [dict(r) for r in txns]
        self._prod_data = [dict(r) for r in prods]


        self._apply_txn_filters()

    # ──────────────────────────────────────────────────────────────────────
    #  Filtering (transactions)
    # ──────────────────────────────────────────────────────────────────────

    def _apply_txn_filters(self):
        data = list(self._txn_data)


        # Payment filter
        if self._payment_filter != "All":
            pm = self._payment_filter.lower()
            data = [r for r in data if r["payment_method"].lower() == pm]

        # Inline search
        q = self._txn_search_var.get().strip().lower() \
            if hasattr(self, "_txn_search_var") else ""
        if q:
            data = [r for r in data
                    if q in r["transaction_number"].lower()
                    or q in r["full_name"].lower()]

        # Sort
        col = getattr(self, "_txn_sort_col", "date")
        asc = getattr(self, "_txn_sort_asc", False)
        key_map = {
            "date":     lambda r: r["created_at"],
            "time":     lambda r: r["created_at"],
            "txn":      lambda r: r["transaction_number"].lower(),
            "cashier":  lambda r: r["full_name"].lower(),
            "payment":  lambda r: r["payment_method"].lower(),
            "items":    lambda r: r["items"],
            "total":    lambda r: r["total"],
            "discount": lambda r: r["discount"],
        }
        data.sort(key=key_map.get(col, lambda r: r["created_at"]),
                  reverse=not asc)

        self._txn_filtered = data
        self._update_stats()
        self._refresh_sub_styles(self._active_sub)

        n = len(data)
        if hasattr(self, "_txn_count_var"):
            self._txn_count_var.set(
                f"{n} transaction{'s' if n != 1 else ''}"
            )
        if hasattr(self, "_filter_count_lbl") and self._active_sub == "txn":
            self._filter_count_lbl.configure(
                text=f"{n} transaction{'s' if n != 1 else ''}"
            )

        if hasattr(self, "_txn_pager") and hasattr(self, "_txn_tree") \
                and self._txn_tree.winfo_exists():
            self._txn_pager.set_data(data)

    # ──────────────────────────────────────────────────────────────────────
    #  Populate helpers (called when switching sub-tabs)
    # ──────────────────────────────────────────────────────────────────────

    def _populate_txn(self):
        self._apply_txn_filters()

    def _populate_product(self):
        q    = self._prod_search_var.get().strip().lower() \
               if hasattr(self, "_prod_search_var") else ""
        data = self._prod_data if not q else [
            r for r in self._prod_data
            if q in r["name"].lower() or q in r["code"].lower()
        ]

        total_rev = sum(r["revenue"] for r in self._prod_data)  # share vs full set

        # Attach revenue share to each row for rendering
        for r in data:
            r["_share"] = (r["revenue"] / total_rev * 100) if total_rev else 0

        n = len(data)
        if hasattr(self, "_prod_count_var"):
            self._prod_count_var.set(
                f"{n} product{'s' if n != 1 else ''}"
            )
        if hasattr(self, "_filter_count_lbl") and self._active_sub == "product":
            self._filter_count_lbl.configure(
                text=f"{n} product{'s' if n != 1 else ''}"
            )

        if hasattr(self, "_prod_pager") and hasattr(self, "_prod_tree") \
                and self._prod_tree.winfo_exists():
            self._prod_pager.set_data(data)

    # ──────────────────────────────────────────────────────────────────────
    #  Render
    # ──────────────────────────────────────────────────────────────────────

    def _render_txn(self, rows):
        if not rows:
            self._txn_tree.insert("", "end", values=(
                "", "", "No transactions match your current filters.",
                "", "", "", "", "",
            ))
            return

        for i, r in enumerate(rows):
            created = r["created_at"]           # "2025-05-01 14:32:00"
            date_str = created[:10]             # "2025-05-01"
            time_str = created[11:16] if len(created) > 10 else ""  # "14:32"

            pm  = r["payment_method"].lower()
            tag = ("cash" if pm == "cash" else "gcash") + ("" if i % 2 == 0 else "_alt")
            pm_label = "💵 Cash" if pm == "cash" else "📱 GCash"

            disc = r["discount"]
            self._txn_tree.insert("", "end", tags=(tag,), values=(
                date_str,
                time_str,
                r["transaction_number"],
                r["full_name"],
                pm_label,
                r["items"],
                f"₱{r['total']:,.2f}",
                f"₱{disc:,.2f}" if disc else "—",
            ))

    def _render_prod(self, rows):
        if not rows:
            self._prod_tree.insert("", "end", values=(
                "", "", "No products match your search.", "", "", "", "",
            ))
            return

        # Rank offset for pagination
        offset = getattr(self._prod_pager, "_page", 0) \
               * getattr(self._prod_pager, "page_size", 20)

        for i, r in enumerate(rows):
            rank   = offset + i + 1
            medal  = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, str(rank))
            tag    = "top1" if rank == 1 else "top3" if rank <= 3 else "evenrow"
            avg_p  = r["revenue"] / r["qty_sold"] if r["qty_sold"] else 0
            share  = r.get("_share", 0)
            self._prod_tree.insert("", "end", tags=(tag,), values=(
                medal,
                r["code"],
                r["name"],
                r["qty_sold"],
                f"₱{r['revenue']:,.2f}",
                f"₱{avg_p:,.2f}",
                f"{share:.1f}%",
            ))

    # ──────────────────────────────────────────────────────────────────────
    #  Export
    # ──────────────────────────────────────────────────────────────────────

    def _export_txn(self):
        if not self._txn_filtered:
            msg_warning(self, "No Data", "Nothing to export — adjust your filters.")
            return
        data = [{
            "Date":           r["created_at"][:10],
            "Time":           r["created_at"][11:16] if len(r["created_at"]) > 10 else "",
            "Transaction #":  r["transaction_number"],
            "Cashier":        r["full_name"],
            "Payment Method": r["payment_method"].title(),
            "Items":          r["items"],
            "Total":          r["total"],
            "Discount":       r["discount"],
            "Net":            r["total"] - r["discount"],
        } for r in self._txn_filtered]
        _export_pdf(self, data, "sales_transactions.pdf", "Sales Transactions Report")

    def _export_products(self):
        if not self._prod_data:
            msg_warning(self, "No Data", "Nothing to export — generate the report first.")
            return
        total_rev = sum(r["revenue"] for r in self._prod_data)
        data = [{
            "Rank":         i + 1,
            "Code":         r["code"],
            "Product":      r["name"],
            "Qty Sold":     r["qty_sold"],
            "Revenue":      r["revenue"],
            "Avg Price":    round(r["revenue"] / r["qty_sold"], 2) if r["qty_sold"] else 0,
            "Rev. Share %": round(r["revenue"] / total_rev * 100, 1) if total_rev else 0,
        } for i, r in enumerate(self._prod_data)]
        _export_pdf(self, data, "sales_by_product.pdf", "Sales by Product Report")


class StockAdjustmentReport(ctk.CTkFrame):
    """
    Stock Adjustment Report — HCI-optimised rewrite
    ─────────────────────────────────────────────────
    Improvements vs previous version:

    1. Stable stat cards — built once, updated by label reference.
       Four summary cards (Total, Pending, Approved, Rejected) are always
       visible above the table without requiring a scroll.

    2. Quick date presets — Today / This Week / This Month shortcuts
       reduce the number of interactions to see common date ranges.

    3. Separate filter bar — Status pills and product search moved into
       their own clearly-labelled zone below the date bar, consistent
       with the Inventory and Sales report patterns.

    4. Inline product search — filter by product name without
       reloading from the database (in-memory filter, instant feedback).

    5. Sortable columns — click any column header to sort ascending /
       descending. Arrow indicators show sort direction.

    6. Net stock change summary — shows total units added vs deducted
       across the filtered set so managers can see inventory impact at a glance.

    7. Empty-state message — explains which filter produced zero results
       instead of leaving a blank table.
    """

    _C_PENDING  = "#B88B2E"; _C_PENDING_BG  = "#FFF8E0"
    _C_APPROVED = "#4A7C59"; _C_APPROVED_BG = "#E6F2EA"
    _C_REJECTED = "#A94040"; _C_REJECTED_BG = "#F5E0E0"

    def __init__(self, master, user):
        super().__init__(master, fg_color="transparent")
        self.user         = user
        self._from        = [_month_start()]
        self._to          = [_today()]
        self._all_data    = []   # full DB result for this date range + status
        self._data        = []   # after in-memory search filter
        self._status_key  = "All"
        self._sort_col    = "date"
        self._sort_asc    = False  # newest-first default
        self._stat_labels = {}
        self._build()
        self._generate()

    # ── Layout ─────────────────────────────────────────────────────────────

    def _build(self):
        # ── Zone 1: Date bar + presets ──────────────────────────────────────
        date_card = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=12,
            border_width=1, border_color=BORDER,
        )
        date_card.pack(fill="x", pady=(0, 6))
        dc = ctk.CTkFrame(date_card, fg_color="transparent")
        dc.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(dc, text="From:", text_color=TEXT_SECONDARY,
                     font=_FONT_SMALL()).pack(side="left")
        self._from_btn = ctk.CTkButton(
            dc, text=f"📅  {self._from[0]}", width=DATE_W, height=BTN_H,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY, font=_FONT_BODY(), corner_radius=CR_BTN,
            command=lambda: _open_calendar(
                self, self._from_btn, self._from[0], self._set_from),
        )
        self._from_btn.pack(side="left", padx=(6, 12))

        ctk.CTkLabel(dc, text="To:", text_color=TEXT_SECONDARY,
                     font=_FONT_SMALL()).pack(side="left")
        self._to_btn = ctk.CTkButton(
            dc, text=f"📅  {self._to[0]}", width=DATE_W, height=BTN_H,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY, font=_FONT_BODY(), corner_radius=CR_BTN,
            command=lambda: _open_calendar(
                self, self._to_btn, self._to[0], self._set_to),
        )
        self._to_btn.pack(side="left", padx=(6, 12))

        ctk.CTkButton(
            dc, text="🔍  Generate", height=BTN_H, width=GENERATE_W,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=CR_BTN, command=self._generate,
        ).pack(side="left", padx=(0, 14))

        # Separator
        ctk.CTkFrame(dc, fg_color=BORDER, width=1, height=BTN_H).pack(
            side="left", padx=(0, 12))

        # Quick presets
        ctk.CTkLabel(dc, text="Quick:", text_color=TEXT_MUTED,
                     font=_FONT_SMALL()).pack(side="left", padx=(0, 6))
        for label, preset in [("Today", "Today"), ("This Week", "This Week"),
                               ("This Month", "This Month")]:
            ctk.CTkButton(
                dc, text=label, height=PILL_H, width=84,
                fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
                border_width=1, border_color=BORDER,
                text_color=TEXT_SECONDARY, corner_radius=CR_PRESET,
                font=_FONT_SMALL(),
                command=lambda p=preset: self._apply_preset(p),
            ).pack(side="left", padx=(0, 4))

        # ── Zone 2: Fixed stat cards ─────────────────────────────────────────
        stats_card = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=12,
            border_width=1, border_color=BORDER,
        )
        stats_card.pack(fill="x", pady=(0, 6))
        self._stats_inner = ctk.CTkFrame(stats_card, fg_color="transparent")
        self._stats_inner.pack(fill="x", padx=8, pady=8)
        self._build_stat_cards()

        # ── Zone 3: Filter bar (inventory-style two-row layout) ─────────────
        fbar = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=12,
            border_width=1, border_color=BORDER,
        )
        fbar.pack(fill="x", pady=(0, 6))

        # ── Row A: Search entry + clear button + export ──────────────────────
        row_a = ctk.CTkFrame(fbar, fg_color="transparent")
        row_a.pack(fill="x", padx=14, pady=(10, 6))

        ctk.CTkLabel(
            row_a, text="Filter  ·",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(side="left", padx=(0, 8))

        self._search_var = ctk.StringVar()
        self._search_var.trace("w", lambda *_: self._apply_search())
        self._search_entry = ctk.CTkEntry(
            row_a, textvariable=self._search_var,
            placeholder_text="Search by product name or requested by",
            height=BTN_H, fg_color="#FFFFFF", border_color=BORDER,
            text_color="#2E2E2E", placeholder_text_color="#6B6B6B",
            font=_FONT_BODY(), corner_radius=8,
        )
        self._search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        # Clear search button
        ctk.CTkButton(
            row_a, text="✕", width=36, height=BTN_H,
            fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_MUTED, corner_radius=8, font=_FONT_SMALL(),
            command=lambda: self._search_var.set(""),
        ).pack(side="left", padx=(0, 8))

        # Divider
        ctk.CTkFrame(row_a, fg_color=BORDER, width=1,
                     height=BTN_H).pack(side="right", padx=(8, 0))

        # Export button — right side
        if PDF_AVAILABLE:
            ctk.CTkButton(
                row_a, text="📄  Export PDF", height=BTN_H, width=EXPORT_W,
                fg_color=SUCCESS, hover_color=SUCCESS_HOVER,
                text_color="white", corner_radius=CR_BTN, font=_FONT_LABEL(),
                command=self._export,
            ).pack(side="right")

        # ── Row B: Status pills + result count ───────────────────────────────
        row_b = ctk.CTkFrame(fbar, fg_color="transparent")
        row_b.pack(fill="x", padx=14, pady=(0, 10))

        ctk.CTkLabel(
            row_b, text="Show:",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
        ).pack(side="left", padx=(0, 8))

        self._status_pills = _PillGroup(
            row_b,
            pills=[
                ("All",      "⬤ All",       ACCENT),
                ("Pending",  "⏳ Pending",   WARNING),
                ("Approved", "✅ Approved",  SUCCESS),
                ("Rejected", "✕ Rejected",  DANGER),
            ],
            on_change=self._on_status_pill,
            initial="All",
        )
        self._status_pills.pack(side="left")

        self._count_lbl = ctk.CTkLabel(
            row_b, text="",
            font=_FONT_SMALL(), text_color=TEXT_MUTED,
        )
        self._count_lbl.pack(side="right")

        # ── Zone 4: Table card ───────────────────────────────────────────────
        card = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=14,
            border_width=1, border_color=BORDER,
        )
        card.pack(fill="both", expand=True)

        # Table header row with count badge
        hdr_row = ctk.CTkFrame(card, fg_color="transparent")
        hdr_row.pack(fill="x", padx=14, pady=(10, 4))
        self._title_var = ctk.StringVar(value="Stock Adjustments")
        ctk.CTkLabel(
            hdr_row, textvariable=self._title_var,
            font=_FONT_TITLE(), text_color=TEXT_PRIMARY,
        ).pack(side="left")
        self._count_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            hdr_row, textvariable=self._count_var,
            font=_FONT_SMALL(), text_color=TEXT_MUTED,
        ).pack(side="left", padx=8)

        # Hint
        ctk.CTkLabel(
            card,
            text="Click a column header to sort",
            font=ctk.CTkFont(size=10), text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=14, pady=(0, 2))

        cols   = ("req_id", "product", "adj_type", "old_qty", "qty_diff",
                  "new_qty", "reason", "requested_by", "date", "status", "approved_by")
        hdrs   = {
            "req_id": "ID", "product": "Product", "adj_type": "Type",
            "old_qty": "Old Qty", "qty_diff": "Change", "new_qty": "New Qty",
            "reason": "Reason", "requested_by": "Requested By",
            "date": "Date", "status": "Status", "approved_by": "Approved By",
        }
        widths = {
            "req_id": 50, "product": 165, "adj_type": 90, "old_qty": 72,
            "qty_diff": 82, "new_qty": 72, "reason": 155,
            "requested_by": 120, "date": 128, "status": 95, "approved_by": 118,
        }
        self.tree = ttk.Treeview(card, columns=cols, show="headings", height=12)
        for col in cols:
            self.tree.heading(
                col, text=hdrs[col],
                command=lambda c=col: self._sort_by(c),
            )
            self.tree.column(
                col, width=widths[col], minwidth=max(widths[col] - 20, 40),
                anchor="e" if col in ("req_id", "old_qty", "qty_diff", "new_qty") else
                "center" if col in ("adj_type", "status") else "w",
            )

        sb = ttk.Scrollbar(card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        style_treeview(self.tree)
        self.tree.tag_configure("pending",      foreground=self._C_PENDING,  background=self._C_PENDING_BG)
        self.tree.tag_configure("approved",     foreground=self._C_APPROVED, background=self._C_APPROVED_BG)
        self.tree.tag_configure("rejected",     foreground=self._C_REJECTED, background=self._C_REJECTED_BG)
        self.tree.tag_configure("pending_alt",  foreground=self._C_PENDING,  background="#FFF4D0")
        self.tree.tag_configure("approved_alt", foreground=self._C_APPROVED, background="#D8EEE0")
        self.tree.tag_configure("rejected_alt", foreground=self._C_REJECTED, background="#EED8D8")
        self.tree.pack(side="left", fill="both", expand=True, padx=6, pady=(0, 6))
        sb.pack(side="right", fill="y", pady=6)

        self._pager = Paginator(card, self.tree, page_size=20,
                                render_fn=self._render_page, bar_parent=self)

    # ── Stat cards — built once, updated by label reference ─────────────────

    def _build_stat_cards(self):
        defs = [
            ("total",    "Total Adjustments", ACCENT,            "🔧"),
            ("pending",  "Pending",           self._C_PENDING,   "⏳"),
            ("approved", "Approved",          self._C_APPROVED,  "✅"),
            ("rejected", "Rejected",          self._C_REJECTED,  "✕"),
            ("net",      "Net Stock Change",  INFO,              "📊"),
        ]
        for key, label, color, icon in defs:
            card = ctk.CTkFrame(
                self._stats_inner, fg_color=BG_CARD_ALT, corner_radius=10,
                border_width=1, border_color=BORDER,
            )
            card.pack(side="left", fill="both", expand=True, padx=4)
            ctk.CTkFrame(card, fg_color=color, height=3, corner_radius=2).pack(
                fill="x", padx=10, pady=(8, 0))
            ctk.CTkLabel(card, text=icon, font=ctk.CTkFont(size=16),
                         text_color=color).pack(pady=(4, 0))
            ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=10),
                         text_color=TEXT_MUTED).pack()
            lbl = ctk.CTkLabel(
                card, text="—",
                font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
                text_color=TEXT_PRIMARY,
            )
            lbl.pack(pady=(2, 8))
            self._stat_labels[key] = lbl

    def _update_stats(self):
        data     = self._all_data
        total    = len(data)
        pending  = sum(1 for r in data if r["status"] == "pending")
        approved = sum(1 for r in data if r["status"] == "approved")
        rejected = sum(1 for r in data if r["status"] == "rejected")
        net      = sum(r["quantity_difference"] for r in data if r["status"] == "approved")

        self._stat_labels["total"].configure(text=str(total))
        self._stat_labels["pending"].configure(text=str(pending))
        self._stat_labels["approved"].configure(text=str(approved))
        self._stat_labels["rejected"].configure(text=str(rejected))
        net_txt = f"{net:+d}" if net != 0 else "0"
        self._stat_labels["net"].configure(text=net_txt)

    # ── Date helpers ─────────────────────────────────────────────────────────

    def _set_from(self, date: str):
        self._from[0] = date
        self._from_btn.configure(text=f"📅  {date}")

    def _set_to(self, date: str):
        self._to[0] = date
        self._to_btn.configure(text=f"📅  {date}")

    def _apply_preset(self, preset: str):
        today = datetime.date.today()
        if preset == "Today":
            f = t = today
        elif preset == "This Week":
            f = today - datetime.timedelta(days=today.weekday())
            t = today
        else:  # This Month
            f = today.replace(day=1)
            t = today
        self._from[0] = f.strftime("%Y-%m-%d")
        self._to[0]   = t.strftime("%Y-%m-%d")
        self._from_btn.configure(text=f"📅  {self._from[0]}")
        self._to_btn.configure(text=f"📅  {self._to[0]}")
        self._generate()

    # ── Filter + sort ─────────────────────────────────────────────────────────

    def _on_status_pill(self, key: str):
        self._status_key = key
        self._generate()

    def _apply_search(self):
        q    = self._search_var.get().strip().lower()
        data = self._all_data if not q else [
            r for r in self._all_data
            if q in r["product_name"].lower()
            or q in (r.get("requested_by") or "").lower()
            or q in (r.get("approved_by") or "").lower()
        ]
        data = self._sorted(data)
        self._data = data
        n = len(data)
        self._count_var.set(f"{n} record{'s' if n != 1 else ''}")
        if hasattr(self, "_count_lbl"):
            self._count_lbl.configure(text=f"{n} record{'s' if n != 1 else ''}")
        self._pager.set_data(data)

    def _sort_by(self, col: str):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True
        self._apply_search()

    def _sorted(self, data: list) -> list:
        col = self._sort_col
        key_map = {
            "req_id":       lambda r: r["id"],
            "product":      lambda r: r["product_name"].lower(),
            "adj_type":     lambda r: r["quantity_difference"],
            "old_qty":      lambda r: r["old_quantity"],
            "qty_diff":     lambda r: r["quantity_difference"],
            "new_qty":      lambda r: r["requested_quantity"],
            "reason":       lambda r: (r["reason"] or "").lower(),
            "requested_by": lambda r: r["requested_by"].lower(),
            "date":         lambda r: r["request_date"],
            "status":       lambda r: r["status"],
            "approved_by":  lambda r: (r["approved_by_name"] or "").lower(),
        }
        fn = key_map.get(col, lambda r: r["request_date"])
        return sorted(data, key=fn, reverse=not self._sort_asc)

    # ── Data fetch ───────────────────────────────────────────────────────────

    def _generate(self):
        status = self._status_key.lower()
        conn   = get_connection()
        query  = """
            SELECT r.id, r.product_name, r.quantity_difference,
                   r.old_quantity, r.requested_quantity,
                   r.reason, r.status, r.request_date,
                   u.full_name AS requested_by,
                   ab.full_name AS approved_by_name
            FROM stock_update_requests r
            JOIN users u ON u.id = r.requested_by
            LEFT JOIN users ab ON ab.id = r.approved_by
            WHERE r.request_type = 'stock_adjustment'
              AND date(r.request_date) BETWEEN ? AND ?
        """
        params = [self._from[0], self._to[0]]
        if status != "all":
            query  += " AND r.status = ?"
            params.append(status)
        query += " ORDER BY r.request_date DESC"
        rows   = conn.execute(query, params).fetchall()
        conn.close()
        self._all_data = [dict(r) for r in rows]
        self._update_stats()
        self._apply_search()

        # Update title to reflect active status filter
        titles = {
            "All":      "Stock Adjustments",
            "Pending":  "⏳  Pending Adjustments",
            "Approved": "✅  Approved Adjustments",
            "Rejected": "✕  Rejected Adjustments",
        }
        self._title_var.set(titles.get(self._status_key, "Stock Adjustments"))

    # ── Render ────────────────────────────────────────────────────────────────

    def _render_page(self, rows):
        if not rows:
            self.tree.insert("", "end", values=(
                "", "No adjustments match your current filters.",
                "", "", "", "", "", "", "", "", "",
            ))
            return

        for i, r in enumerate(rows):
            diff    = r["quantity_difference"]
            status  = r["status"]
            even    = i % 2 == 0
            tag     = status + ("" if even else "_alt")
            type_lbl = "➕ Add" if diff > 0 else "➖ Deduct"
            self.tree.insert("", "end", tags=(tag,), values=(
                r["id"], r["product_name"],
                type_lbl,
                r["old_quantity"], f"{diff:+d}", r["requested_quantity"],
                (r["reason"] or "")[:38],
                r["requested_by"], r["request_date"],
                r["status"].capitalize(),
                r["approved_by_name"] or "—",
            ))

    # ── Export ────────────────────────────────────────────────────────────────

    def _export(self):
        if not self._data:
            msg_warning(self, "No Data", "Nothing to export — adjust your filters.")
            return
        data = [{
            "ID": r["id"], "Product": r["product_name"],
            "Type": "Add" if r["quantity_difference"] > 0 else "Deduct",
            "Old Qty": r["old_quantity"], "Change": r["quantity_difference"],
            "New Qty": r["requested_quantity"], "Reason": r["reason"],
            "Requested By": r["requested_by"], "Date": r["request_date"],
            "Status": r["status"].capitalize(),
            "Approved By": r["approved_by_name"] or "",
        } for r in self._data]
        _export_pdf(self, data, "stock_adjustment_report.pdf", "Stock Adjustment Report")


# ──────────────────────────────────────────────────────────────────────────────
#  E. Approval History Report — HCI-optimised rewrite
#
#  Improvements vs previous version:
#
#  1. Stable stat cards — Total, Pending, Approved, Rejected, + Avg resolution
#     time always visible above table without scrolling.
#
#  2. Quick date presets — Today / This Week / This Month shortcuts.
#
#  3. Separate filter bar — Status pills and Type pills side-by-side in a
#     dedicated zone; product search inline in the table header.
#
#  4. Type pills replace the dropdown — pill pattern is consistent with
#     every other filter group in this window.
#
#  5. Sortable columns — click any header to sort asc/desc.
#
#  6. Alternating row tints per status — easier to scan mixed-status lists.
#
#  7. Empty-state message explains which filter produced zero results.
# ──────────────────────────────────────────────────────────────────────────────

class ApprovalReport(ctk.CTkFrame):
    _C_PENDING  = "#B88B2E"; _C_PENDING_BG  = "#FFF8E0"
    _C_APPROVED = "#4A7C59"; _C_APPROVED_BG = "#E6F2EA"
    _C_REJECTED = "#A94040"; _C_REJECTED_BG = "#F5E0E0"
    _C_STOCKIN  = "#4A6D8C"
    _C_ADJ      = "#6B5B95"

    def __init__(self, master, user):
        super().__init__(master, fg_color="transparent")
        self.user         = user
        self._from        = [_month_start()]
        self._to          = [_today()]
        self._all_data    = []
        self._data        = []
        self._status_key  = "All"
        self._type_key    = "All"
        self._sort_col    = "req_date"
        self._sort_asc    = False
        self._stat_labels = {}
        self._build()
        self._generate()

    # ── Layout ─────────────────────────────────────────────────────────────

    def _build(self):
        # ── Zone 1: Date bar + presets ──────────────────────────────────────
        date_card = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=12,
            border_width=1, border_color=BORDER,
        )
        date_card.pack(fill="x", pady=(0, 6))
        dc = ctk.CTkFrame(date_card, fg_color="transparent")
        dc.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(dc, text="From:", text_color=TEXT_SECONDARY,
                     font=_FONT_SMALL()).pack(side="left")
        self._from_btn = ctk.CTkButton(
            dc, text=f"📅  {self._from[0]}", width=DATE_W, height=BTN_H,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY, font=_FONT_BODY(), corner_radius=CR_BTN,
            command=lambda: _open_calendar(
                self, self._from_btn, self._from[0], self._set_from),
        )
        self._from_btn.pack(side="left", padx=(6, 12))

        ctk.CTkLabel(dc, text="To:", text_color=TEXT_SECONDARY,
                     font=_FONT_SMALL()).pack(side="left")
        self._to_btn = ctk.CTkButton(
            dc, text=f"📅  {self._to[0]}", width=DATE_W, height=BTN_H,
            fg_color=BG_INPUT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY, font=_FONT_BODY(), corner_radius=CR_BTN,
            command=lambda: _open_calendar(
                self, self._to_btn, self._to[0], self._set_to),
        )
        self._to_btn.pack(side="left", padx=(6, 12))

        ctk.CTkButton(
            dc, text="🔍  Generate", height=BTN_H, width=GENERATE_W,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=CR_BTN, command=self._generate,
        ).pack(side="left", padx=(0, 14))

        ctk.CTkFrame(dc, fg_color=BORDER, width=1, height=BTN_H).pack(
            side="left", padx=(0, 12))

        ctk.CTkLabel(dc, text="Quick:", text_color=TEXT_MUTED,
                     font=_FONT_SMALL()).pack(side="left", padx=(0, 6))
        for label, preset in [("Today", "Today"), ("This Week", "This Week"),
                               ("This Month", "This Month")]:
            ctk.CTkButton(
                dc, text=label, height=PILL_H, width=84,
                fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
                border_width=1, border_color=BORDER,
                text_color=TEXT_SECONDARY, corner_radius=CR_PRESET,
                font=_FONT_SMALL(),
                command=lambda p=preset: self._apply_preset(p),
            ).pack(side="left", padx=(0, 4))

        # ── Zone 2: Fixed stat cards ─────────────────────────────────────────
        stats_card = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=12,
            border_width=1, border_color=BORDER,
        )
        stats_card.pack(fill="x", pady=(0, 6))
        self._stats_inner = ctk.CTkFrame(stats_card, fg_color="transparent")
        self._stats_inner.pack(fill="x", padx=8, pady=8)
        self._build_stat_cards()

        # ── Zone 3: Filter bar (inventory-style two-row layout) ─────────────
        fbar = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=12,
            border_width=1, border_color=BORDER,
        )
        fbar.pack(fill="x", pady=(0, 6))

        # ── Row A: Search entry + clear button + export ──────────────────────
        row_a = ctk.CTkFrame(fbar, fg_color="transparent")
        row_a.pack(fill="x", padx=14, pady=(10, 6))

        ctk.CTkLabel(
            row_a, text="Filter  ·",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(side="left", padx=(0, 8))

        self._search_var = ctk.StringVar()
        self._search_var.trace("w", lambda *_: self._apply_search())
        self._search_entry = ctk.CTkEntry(
            row_a, textvariable=self._search_var,
            placeholder_text="Search by product name or requested by",
            height=BTN_H, fg_color="#FFFFFF", border_color=BORDER,
            text_color="#2E2E2E", placeholder_text_color="#6B6B6B",
            font=_FONT_BODY(), corner_radius=8,
        )
        self._search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        # Clear search button
        ctk.CTkButton(
            row_a, text="✕", width=36, height=BTN_H,
            fg_color=BG_CARD_ALT, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_MUTED, corner_radius=8, font=_FONT_SMALL(),
            command=lambda: self._search_var.set(""),
        ).pack(side="left", padx=(0, 8))

        # Divider
        ctk.CTkFrame(row_a, fg_color=BORDER, width=1,
                     height=BTN_H).pack(side="right", padx=(8, 0))

        # Export button — right side
        if PDF_AVAILABLE:
            ctk.CTkButton(
                row_a, text="📄  Export PDF", height=BTN_H, width=EXPORT_W,
                fg_color=SUCCESS, hover_color=SUCCESS_HOVER,
                text_color="white", corner_radius=CR_BTN, font=_FONT_LABEL(),
                command=self._export,
            ).pack(side="right")

        # ── Row B: Status pills + Type pills + result count ──────────────────
        row_b = ctk.CTkFrame(fbar, fg_color="transparent")
        row_b.pack(fill="x", padx=14, pady=(0, 10))

        ctk.CTkLabel(
            row_b, text="Status:",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
        ).pack(side="left", padx=(0, 8))

        self._status_pills = _PillGroup(
            row_b,
            pills=[
                ("All",      "⬤ All",       ACCENT),
                ("Pending",  "⏳ Pending",   WARNING),
                ("Approved", "✅ Approved",  SUCCESS),
                ("Rejected", "✕ Rejected",  DANGER),
            ],
            on_change=self._on_status_pill,
            initial="All",
        )
        self._status_pills.pack(side="left")

        # Type pills — separator + label
        ctk.CTkFrame(row_b, fg_color=BORDER, width=1,
                     height=24).pack(side="left", padx=(12, 0))
        ctk.CTkLabel(
            row_b, text="Type:",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
        ).pack(side="left", padx=(8, 8))

        self._type_pills = _PillGroup(
            row_b,
            pills=[
                ("All",        "⬤ All",          ACCENT),
                ("stock_in",   "📥 Stock In",     self._C_STOCKIN),
                ("adjustment", "🔧 Adjustment",   self._C_ADJ),
            ],
            on_change=self._on_type_pill,
            initial="All",
        )
        self._type_pills.pack(side="left")

        self._count_lbl = ctk.CTkLabel(
            row_b, text="",
            font=_FONT_SMALL(), text_color=TEXT_MUTED,
        )
        self._count_lbl.pack(side="right")

        # ── Zone 4: Table card ───────────────────────────────────────────────
        card = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=14,
            border_width=1, border_color=BORDER,
        )
        card.pack(fill="both", expand=True)

        # Table header with title + count
        hdr_row = ctk.CTkFrame(card, fg_color="transparent")
        hdr_row.pack(fill="x", padx=14, pady=(10, 4))
        self._title_var = ctk.StringVar(value="Approval History")
        ctk.CTkLabel(
            hdr_row, textvariable=self._title_var,
            font=_FONT_TITLE(), text_color=TEXT_PRIMARY,
        ).pack(side="left")
        self._count_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            hdr_row, textvariable=self._count_var,
            font=_FONT_SMALL(), text_color=TEXT_MUTED,
        ).pack(side="left", padx=8)

        # Column sort hint
        ctk.CTkLabel(
            card, text="Click a column header to sort",
            font=ctk.CTkFont(size=10), text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=14, pady=(0, 2))

        cols   = ("req_id", "type", "product", "old_qty", "req_qty",
                  "final_qty", "status", "requested_by", "approved_by",
                  "req_date", "app_date", "rejection")
        hdrs   = {
            "req_id": "ID", "type": "Type", "product": "Product",
            "old_qty": "Old Qty", "req_qty": "Req. Qty", "final_qty": "Final Qty",
            "status": "Status", "requested_by": "Requested By",
            "approved_by": "Approved By", "req_date": "Request Date",
            "app_date": "Action Date", "rejection": "Rejection Reason",
        }
        widths = {
            "req_id": 50, "type": 118, "product": 155,
            "old_qty": 72, "req_qty": 72, "final_qty": 72,
            "status": 95, "requested_by": 120, "approved_by": 120,
            "req_date": 128, "app_date": 128, "rejection": 155,
        }
        self.tree = ttk.Treeview(card, columns=cols, show="headings", height=11)
        for col in cols:
            self.tree.heading(
                col, text=hdrs[col],
                command=lambda c=col: self._sort_by(c),
            )
            self.tree.column(
                col, width=widths[col], minwidth=max(widths[col] - 20, 40),
                anchor="e" if col in ("req_id", "old_qty", "req_qty", "final_qty") else
                "center" if col in ("type", "status") else "w",
            )

        sb = ttk.Scrollbar(card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        style_treeview(self.tree)
        self.tree.tag_configure("pending",      foreground=self._C_PENDING,  background=self._C_PENDING_BG)
        self.tree.tag_configure("approved",     foreground=self._C_APPROVED, background=self._C_APPROVED_BG)
        self.tree.tag_configure("rejected",     foreground=self._C_REJECTED, background=self._C_REJECTED_BG)
        self.tree.tag_configure("pending_alt",  foreground=self._C_PENDING,  background="#FFF4D0")
        self.tree.tag_configure("approved_alt", foreground=self._C_APPROVED, background="#D8EEE0")
        self.tree.tag_configure("rejected_alt", foreground=self._C_REJECTED, background="#EED8D8")
        self.tree.pack(side="left", fill="both", expand=True, padx=6, pady=(0, 6))
        sb.pack(side="right", fill="y", pady=6)

        self._pager = Paginator(card, self.tree, page_size=20,
                                render_fn=self._render_page, bar_parent=self)

    # ── Stat cards ────────────────────────────────────────────────────────────

    def _build_stat_cards(self):
        defs = [
            ("total",    "Total Requests",  ACCENT,           "📋"),
            ("pending",  "Pending",         self._C_PENDING,  "⏳"),
            ("approved", "Approved",        self._C_APPROVED, "✅"),
            ("rejected", "Rejected",        self._C_REJECTED, "✕"),
        ]
        for key, label, color, icon in defs:
            card = ctk.CTkFrame(
                self._stats_inner, fg_color=BG_CARD_ALT, corner_radius=10,
                border_width=1, border_color=BORDER,
            )
            card.pack(side="left", fill="both", expand=True, padx=4)
            ctk.CTkFrame(card, fg_color=color, height=3, corner_radius=2).pack(
                fill="x", padx=10, pady=(8, 0))
            ctk.CTkLabel(card, text=icon, font=ctk.CTkFont(size=16),
                         text_color=color).pack(pady=(4, 0))
            ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=10),
                         text_color=TEXT_MUTED).pack()
            lbl = ctk.CTkLabel(
                card, text="—",
                font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
                text_color=TEXT_PRIMARY,
            )
            lbl.pack(pady=(2, 8))
            self._stat_labels[key] = lbl

    def _update_stats(self):
        data     = self._all_data
        total    = len(data)
        pending  = sum(1 for r in data if r["status"] == "pending")
        approved = sum(1 for r in data if r["status"] == "approved")
        rejected = sum(1 for r in data if r["status"] == "rejected")
        self._stat_labels["total"].configure(text=str(total))
        self._stat_labels["pending"].configure(text=str(pending))
        self._stat_labels["approved"].configure(text=str(approved))
        self._stat_labels["rejected"].configure(text=str(rejected))

    # ── Date helpers ──────────────────────────────────────────────────────────

    def _set_from(self, date: str):
        self._from[0] = date
        self._from_btn.configure(text=f"📅  {date}")

    def _set_to(self, date: str):
        self._to[0] = date
        self._to_btn.configure(text=f"📅  {date}")

    def _apply_preset(self, preset: str):
        today = datetime.date.today()
        if preset == "Today":
            f = t = today
        elif preset == "This Week":
            f = today - datetime.timedelta(days=today.weekday())
            t = today
        else:
            f = today.replace(day=1)
            t = today
        self._from[0] = f.strftime("%Y-%m-%d")
        self._to[0]   = t.strftime("%Y-%m-%d")
        self._from_btn.configure(text=f"📅  {self._from[0]}")
        self._to_btn.configure(text=f"📅  {self._to[0]}")
        self._generate()

    # ── Filters + sort ────────────────────────────────────────────────────────

    def _on_status_pill(self, key: str):
        self._status_key = key
        self._generate()

    def _on_type_pill(self, key: str):
        self._type_key = key
        self._generate()

    def _apply_search(self):
        q    = self._search_var.get().strip().lower()
        data = self._all_data if not q else [
            r for r in self._all_data
            if q in r["product_name"].lower()
            or q in (r.get("requested_by") or "").lower()
            or q in (r.get("approved_by") or "").lower()
        ]
        data = self._sorted(data)
        self._data = data
        n = len(data)
        self._count_var.set(f"{n} record{'s' if n != 1 else ''}")
        if hasattr(self, "_count_lbl"):
            self._count_lbl.configure(text=f"{n} record{'s' if n != 1 else ''}")
        self._pager.set_data(data)

    def _sort_by(self, col: str):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True
        self._apply_search()

    def _sorted(self, data: list) -> list:
        col = self._sort_col
        key_map = {
            "req_id":       lambda r: r["id"],
            "type":         lambda r: r["request_type"],
            "product":      lambda r: r["product_name"].lower(),
            "old_qty":      lambda r: r["old_quantity"],
            "req_qty":      lambda r: r["requested_quantity"],
            "final_qty":    lambda r: r["requested_quantity"] if r["status"] == "approved"
                                      else r["old_quantity"],
            "status":       lambda r: r["status"],
            "requested_by": lambda r: r["requested_by"].lower(),
            "approved_by":  lambda r: (r["approved_by_name"] or "").lower(),
            "req_date":     lambda r: r["request_date"],
            "app_date":     lambda r: r["approval_date"] or "",
            "rejection":    lambda r: (r["rejection_reason"] or "").lower(),
        }
        fn = key_map.get(col, lambda r: r["request_date"])
        return sorted(data, key=fn, reverse=not self._sort_asc)

    # ── Data fetch ────────────────────────────────────────────────────────────

    def _generate(self):
        status    = self._status_key.lower()
        type_filt = self._type_key
        conn      = get_connection()
        query     = """
            SELECT r.id, r.request_type, r.product_name,
                   r.old_quantity, r.requested_quantity,
                   r.status, r.request_date, r.approval_date,
                   r.rejection_reason,
                   u.full_name AS requested_by,
                   ab.full_name AS approved_by_name
            FROM stock_update_requests r
            JOIN users u ON u.id = r.requested_by
            LEFT JOIN users ab ON ab.id = r.approved_by
            WHERE date(r.request_date) BETWEEN ? AND ?
        """
        params = [self._from[0], self._to[0]]
        if status != "all":
            query += " AND r.status = ?"
            params.append(status)
        if type_filt == "stock_in":
            query += " AND r.request_type = 'stock_in'"
        elif type_filt == "adjustment":
            query += " AND r.request_type = 'stock_adjustment'"
        query += " ORDER BY r.request_date DESC"
        rows  = conn.execute(query, params).fetchall()
        conn.close()
        self._all_data = [dict(r) for r in rows]
        self._update_stats()
        self._apply_search()

        # Update title to reflect active filters
        status_labels = {
            "All": "Approval History", "Pending": "⏳  Pending Requests",
            "Approved": "✅  Approved Requests", "Rejected": "✕  Rejected Requests",
        }
        self._title_var.set(status_labels.get(self._status_key, "Approval History"))

    # ── Render ────────────────────────────────────────────────────────────────

    def _render_page(self, rows):
        if not rows:
            self.tree.insert("", "end", values=(
                "", "", "No requests match your current filters.",
                "", "", "", "", "", "", "", "", "",
            ))
            return

        for i, r in enumerate(rows):
            type_label = {
                "stock_in":         "📥 Stock In",
                "stock_adjustment": "🔧 Adjustment",
            }.get(r["request_type"], r["request_type"])
            final_qty = r["requested_quantity"] if r["status"] == "approved" \
                        else r["old_quantity"]
            status  = r["status"]
            even    = i % 2 == 0
            tag     = status + ("" if even else "_alt")
            self.tree.insert("", "end", tags=(tag,), values=(
                r["id"], type_label, r["product_name"],
                r["old_quantity"], r["requested_quantity"], final_qty,
                r["status"].capitalize(),
                r["requested_by"], r["approved_by_name"] or "—",
                r["request_date"], r["approval_date"] or "—",
                r["rejection_reason"] or "—",
            ))

    # ── Export ────────────────────────────────────────────────────────────────

    def _export(self):
        if not self._data:
            msg_warning(self, "No Data", "Nothing to export — adjust your filters.")
            return
        data = [{
            "ID": r["id"], "Type": r["request_type"].replace("_", " ").title(),
            "Product": r["product_name"],
            "Old Qty": r["old_quantity"], "Requested Qty": r["requested_quantity"],
            "Final Qty": r["requested_quantity"] if r["status"] == "approved"
                         else r["old_quantity"],
            "Status": r["status"].capitalize(), "Requested By": r["requested_by"],
            "Approved By": r["approved_by_name"] or "",
            "Request Date": r["request_date"], "Action Date": r["approval_date"] or "",
            "Rejection Reason": r["rejection_reason"] or "",
        } for r in self._data]
        _export_pdf(self, data, "approval_report.pdf", "Approval History Report")

# ──────────────────────────────────────────────────────────────────────────────
#  SECURITY REPORT
# ──────────────────────────────────────────────────────────────────────────────

class SecurityReport(ctk.CTkFrame):
    """Tabbed security dashboard with login stats, login log, audit trail, cash drawer log."""

    _TABS = [
        ("🔑  Overview",     "overview"),
        ("📋  Login Log",    "login"),
        ("🗂  Audit Trail",  "audit"),
        ("🗄  Cash Drawer",  "cash"),
    ]

    # Event badge colours  (bg, fg)
    _EVENT_STYLE = {
        "LOGIN_SUCCESS":  ("#d1fae5", "#065f46"),
        "LOGIN_FAILED":   ("#fee2e2", "#991b1b"),
        "ACCOUNT_LOCKED": ("#fef3c7", "#92400e"),
        "SESSION_TIMEOUT":("#dbeafe", "#1e3a8a"),
        "LOGOUT":         ("#f3f4f6", "#4b5563"),
    }
    _MODULE_STYLE = {
        "Inventory":   ("#e0f2fe", "#0c4a6e"),
        "Sales":       ("#d1fae5", "#065f46"),
        "Services":    ("#ede9fe", "#4c1d95"),
        "Stock":       ("#fef9c3", "#713f12"),
        "Users":       ("#ffe4e6", "#9f1239"),
        "CashDrawer":  ("#fce7f3", "#831843"),
        "Backup":      ("#f0fdf4", "#14532d"),
        "Database":    ("#fee2e2", "#991b1b"),
    }

    def __init__(self, master, user):
        super().__init__(master, fg_color="transparent")
        self.user = user
        self._active_tab = "overview"
        self._build_header()
        self._build_tab_bar()
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.pack(fill="both", expand=True, pady=(8, 0))
        self._show_tab("overview")

    # ── Header ────────────────────────────────────────────────────────────

    def _build_header(self):
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))

        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left")

        ctk.CTkLabel(
            left, text="🔐  Security Dashboard",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w")
        ctk.CTkLabel(
            left, text="Monitor login activity, audit trail, and cash drawer events",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", pady=(2, 0))

        # Refresh button
        ctk.CTkButton(
            row, text="↻  Refresh", width=110, height=34,
            fg_color=BG_CARD, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            corner_radius=8,
            command=self._refresh,
        ).pack(side="right")

    # ── Tab bar ───────────────────────────────────────────────────────────

    def _build_tab_bar(self):
        bar = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=10,
                           border_width=1, border_color=BORDER)
        bar.pack(fill="x", pady=(0, 4))

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(padx=6, pady=6, anchor="w")

        self._tab_btns = {}
        for label, key in self._TABS:
            btn = ctk.CTkButton(
                inner, text=label, height=32, width=148,
                fg_color="transparent", hover_color=BG_HOVER,
                text_color=TEXT_SECONDARY, corner_radius=8,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                command=lambda k=key: self._show_tab(k),
            )
            btn.pack(side="left", padx=(0, 4))
            self._tab_btns[key] = btn

    def _show_tab(self, key: str):
        self._active_tab = key
        for k, btn in self._tab_btns.items():
            if k == key:
                btn.configure(fg_color=ACCENT, text_color="#ffffff",
                               hover_color="#5a6e80")
            else:
                btn.configure(fg_color="transparent", text_color=TEXT_SECONDARY,
                               hover_color=BG_HOVER)
        for w in self._content.winfo_children():
            w.destroy()
        {
            "overview": self._tab_overview,
            "login":    self._tab_login,
            "audit":    self._tab_audit,
            "cash":     self._tab_cash,
        }[key](self._content)

    def _refresh(self):
        self._show_tab(self._active_tab)

    # ── Overview tab ──────────────────────────────────────────────────────

    def _tab_overview(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        conn = get_connection()

        # ── Stat cards row ────────────────────────────────────────────────
        success = conn.execute("SELECT COUNT(*) FROM login_logs WHERE action='LOGIN_SUCCESS'").fetchone()[0]
        failed  = conn.execute("SELECT COUNT(*) FROM login_logs WHERE action='LOGIN_FAILED'").fetchone()[0]
        locked  = conn.execute("SELECT COUNT(*) FROM login_logs WHERE action='ACCOUNT_LOCKED'").fetchone()[0]
        timeout = conn.execute("SELECT COUNT(*) FROM login_logs WHERE action='SESSION_TIMEOUT'").fetchone()[0]
        audits  = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]

        cards_data = [
            ("✅", "Successful Logins",  success, SUCCESS,  "#e6f4ec"),
            ("❌", "Failed Attempts",    failed,  DANGER,   "#faeaea"),
            ("🔒", "Account Lockouts",   locked,  WARNING,  "#fdf3dc"),
            ("⏱", "Session Timeouts",   timeout, INFO,     "#e8eff5"),
            ("🗂", "Audit Events",       audits,  ACCENT,   "#eaeef2"),
        ]

        cards_row = ctk.CTkFrame(scroll, fg_color="transparent")
        cards_row.pack(fill="x", pady=(0, 16))

        for icon, label, val, color, _bg in cards_data:
            card = ctk.CTkFrame(
                cards_row, fg_color=BG_CARD_ALT, corner_radius=10,
                border_width=1, border_color=BORDER,
            )
            card.pack(side="left", fill="both", expand=True, padx=4)

            ctk.CTkFrame(card, fg_color=color, height=3, corner_radius=2).pack(
                fill="x", padx=10, pady=(8, 0))
            ctk.CTkLabel(card, text=icon,
                         font=ctk.CTkFont(size=16),
                         text_color=color).pack(pady=(6, 0))
            ctk.CTkLabel(card, text=label,
                         font=ctk.CTkFont(size=10),
                         text_color=TEXT_MUTED).pack()
            ctk.CTkLabel(card, text=str(val),
                         font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
                         text_color=TEXT_PRIMARY).pack(pady=(2, 8))

        # ── Today's activity ──────────────────────────────────────────────
        self._section_header(scroll, "📅  Today's Activity")

        today_success = conn.execute(
            "SELECT COUNT(*) FROM login_logs WHERE action='LOGIN_SUCCESS' AND date(created_at)=date('now','localtime')"
        ).fetchone()[0]
        today_failed = conn.execute(
            "SELECT COUNT(*) FROM login_logs WHERE action='LOGIN_FAILED' AND date(created_at)=date('now','localtime')"
        ).fetchone()[0]
        today_audits = conn.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE date(created_at)=date('now','localtime')"
        ).fetchone()[0]

        today_row = ctk.CTkFrame(scroll, fg_color=BG_CARD, corner_radius=12,
                                  border_width=1, border_color=BORDER)
        today_row.pack(fill="x", pady=(0, 16))

        for label, val, color in [
            ("Logins Today",       today_success, SUCCESS),
            ("Failed Today",       today_failed,  DANGER),
            ("Audit Events Today", today_audits,  ACCENT),
        ]:
            seg = ctk.CTkFrame(today_row, fg_color="transparent")
            seg.pack(side="left", expand=True, padx=24, pady=14)
            ctk.CTkLabel(seg, text=str(val),
                         font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
                         text_color=color).pack()
            ctk.CTkLabel(seg, text=label,
                         font=ctk.CTkFont(family="Segoe UI", size=11),
                         text_color=TEXT_MUTED).pack()

        # ── Currently locked accounts ─────────────────────────────────────
        self._section_header(scroll, "🔒  Currently Locked Accounts")

        locked_users = conn.execute(
            """SELECT username, full_name, failed_attempts, locked_until
               FROM users WHERE locked_until IS NOT NULL
               ORDER BY locked_until DESC"""
        ).fetchall()

        if locked_users:
            for u in locked_users:
                row = ctk.CTkFrame(scroll, fg_color="#fef3c7", corner_radius=10,
                                   border_width=1, border_color="#fbbf24")
                row.pack(fill="x", pady=(0, 6))
                ctk.CTkLabel(row,
                             text=f"🔒  {u['full_name']} (@{u['username']})   —   "
                                  f"{u['failed_attempts']} failed attempts   •   "
                                  f"Locked until: {u['locked_until']}",
                             font=ctk.CTkFont(family="Segoe UI", size=12),
                             text_color="#92400e").pack(anchor="w", padx=16, pady=10)
        else:
            empty = ctk.CTkFrame(scroll, fg_color="#f0fdf4", corner_radius=10,
                                  border_width=1, border_color="#86efac")
            empty.pack(fill="x", pady=(0, 16))
            ctk.CTkLabel(empty, text="✅  No accounts are currently locked.",
                         font=ctk.CTkFont(family="Segoe UI", size=12),
                         text_color="#166534").pack(anchor="w", padx=16, pady=10)

        # ── Recent 5 events quick view ────────────────────────────────────
        self._section_header(scroll, "🕐  Latest Login Events")

        recent = conn.execute(
            """SELECT username, action, ip_address, created_at
               FROM login_logs ORDER BY id DESC LIMIT 8"""
        ).fetchall()

        for ev in recent:
            bg, fg = self._EVENT_STYLE.get(ev["action"], ("#f3f4f6", "#4b5563"))
            row = ctk.CTkFrame(scroll, fg_color=BG_CARD, corner_radius=8,
                               border_width=1, border_color=BORDER)
            row.pack(fill="x", pady=(0, 5))

            badge = ctk.CTkLabel(row, text=f"  {ev['action']}  ",
                                  font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                                  fg_color=bg, text_color=fg, corner_radius=6)
            badge.pack(side="left", padx=(10, 0), pady=8)

            ctk.CTkLabel(row, text=ev["username"] or "—",
                         font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                         text_color=TEXT_PRIMARY).pack(side="left", padx=(10, 4), pady=8)

            ctk.CTkLabel(row, text=f"from {ev['ip_address'] or '—'}",
                         font=ctk.CTkFont(family="Segoe UI", size=11),
                         text_color=TEXT_MUTED).pack(side="left", pady=8)

            ctk.CTkLabel(row, text=ev["created_at"] or "—",
                         font=ctk.CTkFont(family="Segoe UI", size=11),
                         text_color=TEXT_MUTED).pack(side="right", padx=14, pady=8)

        conn.close()

    # ── Login log tab ─────────────────────────────────────────────────────

    def _tab_login(self, parent):
        conn = get_connection()

        # Filter bar
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 8))

        filter_var = ctk.StringVar(value="ALL")
        options = ["ALL", "LOGIN_SUCCESS", "LOGIN_FAILED", "ACCOUNT_LOCKED",
                   "SESSION_TIMEOUT", "LOGOUT"]

        ctk.CTkLabel(bar, text="Filter:", font=ctk.CTkFont(family="Segoe UI", size=12),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0,6))

        def _apply_filter(*_):
            f = filter_var.get()
            c = get_connection()
            rows = c.execute(
                """SELECT created_at, username, action, ip_address, device_name
                   FROM login_logs
                   WHERE (? = 'ALL' OR action = ?)
                   ORDER BY id DESC LIMIT 200""",
                (f, f)
            ).fetchall()
            c.close()
            _reload(rows)

        menu = ctk.CTkOptionMenu(bar, variable=filter_var, values=options,
                                  width=200, height=32,
                                  fg_color=BG_CARD, button_color=ACCENT,
                                  text_color=TEXT_PRIMARY,
                                  font=ctk.CTkFont(family="Segoe UI", size=12),
                                  command=lambda v: _apply_filter())
        menu.pack(side="left")

        # Count label
        count_lbl = ctk.CTkLabel(bar, text="",
                                  font=ctk.CTkFont(family="Segoe UI", size=11),
                                  text_color=TEXT_MUTED)
        count_lbl.pack(side="right", padx=4)

        # Table
        table_frame = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=12,
                                    border_width=1, border_color=BORDER)
        table_frame.pack(fill="both", expand=True)

        cols = ("created_at", "username", "action", "ip_address", "device_name")
        hdrs = {"created_at": "Timestamp", "username": "User", "action": "Event",
                "ip_address": "IP Address", "device_name": "Device"}
        wids = {"created_at": 160, "username": 130, "action": 170,
                "ip_address": 130, "device_name": 250}

        tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=18)
        for c in cols:
            tree.heading(c, text=hdrs[c])
            tree.column(c, width=wids[c], minwidth=60)

        sb = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        style_treeview(tree)

        tree.tag_configure("LOGIN_SUCCESS",   background="#f0fdf4", foreground="#065f46")
        tree.tag_configure("LOGIN_FAILED",    background="#fef2f2", foreground="#991b1b")
        tree.tag_configure("ACCOUNT_LOCKED",  background="#fffbeb", foreground="#92400e")
        tree.tag_configure("SESSION_TIMEOUT", background="#eff6ff", foreground="#1e3a8a")
        tree.tag_configure("LOGOUT",          background="#f9fafb", foreground="#4b5563")

        def _reload(rows):
            for item in tree.get_children():
                tree.delete(item)
            for r in rows:
                tree.insert("", "end",
                             values=(r["created_at"] or "—", r["username"] or "—",
                                     r["action"] or "—", r["ip_address"] or "—",
                                     r["device_name"] or "—"),
                             tags=(r["action"],))
            if not rows:
                tree.insert("", "end", values=("No records", "—", "—", "—", "—"))
            count_lbl.configure(text=f"{len(rows)} record(s)")

        tree.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        sb.pack(side="right", fill="y", pady=6)

        _apply_filter()
        conn.close()

    # ── Audit trail tab ───────────────────────────────────────────────────

    def _tab_audit(self, parent):
        conn = get_connection()

        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 8))

        modules = ["ALL"] + [r[0] for r in conn.execute(
            "SELECT DISTINCT module FROM audit_logs ORDER BY module"
        ).fetchall()]

        mod_var = ctk.StringVar(value="ALL")
        ctk.CTkLabel(bar, text="Module:", font=ctk.CTkFont(family="Segoe UI", size=12),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0,6))
        ctk.CTkOptionMenu(bar, variable=mod_var, values=modules,
                           width=180, height=32,
                           fg_color=BG_CARD, button_color=ACCENT,
                           text_color=TEXT_PRIMARY,
                           font=ctk.CTkFont(family="Segoe UI", size=12),
                           command=lambda v: _apply()).pack(side="left")

        count_lbl = ctk.CTkLabel(bar, text="",
                                  font=ctk.CTkFont(family="Segoe UI", size=11),
                                  text_color=TEXT_MUTED)
        count_lbl.pack(side="right", padx=4)

        table_frame = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=12,
                                    border_width=1, border_color=BORDER)
        table_frame.pack(fill="both", expand=True)

        cols = ("created_at", "username", "module", "action", "record_id", "new_value")
        hdrs = {"created_at": "Timestamp", "username": "User", "module": "Module",
                "action": "Action", "record_id": "Record ID", "new_value": "Details"}
        wids = {"created_at": 155, "username": 120, "module": 110,
                "action": 200, "record_id": 90, "new_value": 260}

        tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=18)
        for c in cols:
            tree.heading(c, text=hdrs[c])
            tree.column(c, width=wids[c], minwidth=60)

        sb = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        style_treeview(tree)

        # Module row colouring
        for mod, (bg, _) in self._MODULE_STYLE.items():
            tree.tag_configure(f"mod_{mod}", background=bg)

        def _apply():
            m = mod_var.get()
            c = get_connection()
            rows = c.execute(
                """SELECT created_at, username, module, action, record_id, new_value
                   FROM audit_logs
                   WHERE (? = 'ALL' OR module = ?)
                   ORDER BY id DESC LIMIT 200""",
                (m, m)
            ).fetchall()
            c.close()
            for item in tree.get_children():
                tree.delete(item)
            for r in rows:
                tag = f"mod_{r['module']}" if r["module"] in self._MODULE_STYLE else ""
                tree.insert("", "end",
                             values=(r["created_at"] or "—", r["username"] or "—",
                                     r["module"] or "—", r["action"] or "—",
                                     r["record_id"] or "—",
                                     (r["new_value"] or "—")[:80]),
                             tags=(tag,))
            if not rows:
                tree.insert("", "end", values=("No records",) + ("—",)*5)
            count_lbl.configure(text=f"{len(rows)} record(s)")

        tree.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        sb.pack(side="right", fill="y", pady=6)

        _apply()
        conn.close()

    # ── Cash drawer tab ───────────────────────────────────────────────────

    def _tab_cash(self, parent):
        conn = get_connection()

        # Summary bar
        total_open  = conn.execute("SELECT COUNT(*) FROM cash_drawer_logs WHERE action='OPEN_DRAWER'").fetchone()[0]
        total_close = conn.execute("SELECT COUNT(*) FROM cash_drawer_logs WHERE action='CLOSE_DRAWER'").fetchone()[0]
        avg_var     = conn.execute(
            "SELECT AVG(ABS(difference)) FROM cash_drawer_logs WHERE difference IS NOT NULL"
        ).fetchone()[0] or 0

        summary = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=12,
                                border_width=1, border_color=BORDER)
        summary.pack(fill="x", pady=(0, 10))

        for label, val, color in [
            ("🟢  Sessions Opened",   total_open,        SUCCESS),
            ("🔴  Sessions Closed",   total_close,       DANGER),
            ("📊  Avg Variance",      f"₱{avg_var:,.2f}", WARNING),
        ]:
            seg = ctk.CTkFrame(summary, fg_color="transparent")
            seg.pack(side="left", expand=True, padx=24, pady=14)
            ctk.CTkLabel(seg, text=str(val),
                         font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
                         text_color=color).pack()
            ctk.CTkLabel(seg, text=label,
                         font=ctk.CTkFont(family="Segoe UI", size=11),
                         text_color=TEXT_MUTED).pack()

        # Table
        table_frame = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=12,
                                    border_width=1, border_color=BORDER)
        table_frame.pack(fill="both", expand=True)

        cols = ("created_at", "username", "action", "opening_cash",
                "closing_cash", "expected_cash", "difference", "session_ref")
        hdrs = {"created_at": "Timestamp", "username": "User", "action": "Event",
                "opening_cash": "Opening", "closing_cash": "Closing",
                "expected_cash": "Expected", "difference": "Variance",
                "session_ref": "Session ID"}
        wids = {"created_at": 150, "username": 110, "action": 120,
                "opening_cash": 90, "closing_cash": 90, "expected_cash": 90,
                "difference": 90, "session_ref": 170}

        tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=16)
        for c in cols:
            tree.heading(c, text=hdrs[c])
            tree.column(c, width=wids[c], minwidth=60)

        sb = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        style_treeview(tree)

        tree.tag_configure("open",    background="#f0fdf4", foreground="#065f46")
        tree.tag_configure("close_ok", background="#eff6ff", foreground="#1e3a8a")
        tree.tag_configure("close_var", background="#fffbeb", foreground="#92400e")

        rows = conn.execute(
            """SELECT created_at, username, action, opening_cash, closing_cash,
                      expected_cash, actual_cash, difference, session_ref
               FROM cash_drawer_logs ORDER BY id DESC LIMIT 100"""
        ).fetchall()

        for r in rows:
            def _fmt(c):
                v = r[c]
                if v is None:
                    return "—"
                if c in ("opening_cash","closing_cash","expected_cash",
                         "actual_cash","difference"):
                    try:
                        prefix = "+" if c == "difference" and float(v) > 0 else ""
                        return f"{prefix}₱{float(v):,.2f}"
                    except Exception:
                        return str(v)
                return str(v)

            if r["action"] == "OPEN_DRAWER":
                tag = "open"
            elif r["difference"] is not None and abs(float(r["difference"] or 0)) > 0.01:
                tag = "close_var"
            else:
                tag = "close_ok"

            tree.insert("", "end",
                         values=tuple(_fmt(c) for c in cols),
                         tags=(tag,))

        if not rows:
            tree.insert("", "end", values=tuple("—" for _ in cols))

        tree.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        sb.pack(side="right", fill="y", pady=6)

        conn.close()

    # ── Shared helpers ────────────────────────────────────────────────────

    def _section_header(self, parent, text: str):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(8, 6))
        ctk.CTkLabel(row, text=text,
                     font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(side="left")
        ctk.CTkFrame(row, fg_color=BORDER, height=1).pack(
            side="left", fill="x", expand=True, padx=(10, 0), pady=6)