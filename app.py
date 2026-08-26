"""Contractor Project Tracker - local Tkinter + SQLite prototype.

Run with: python app.py
No third-party packages are required.
"""

from __future__ import annotations

import calendar
import base64
import csv
import hashlib
import io
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import zipfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape as xml_escape
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, simpledialog, ttk


APP_TITLE = "Contractor Project Tracker"
APP_DIR = Path(__file__).resolve().parent
ALL_PROJECTS_LABEL = "All Projects"
SHARED_CASH_LABEL = "Shared Cash Pool"


def resolve_db_path(candidate: Path | str | None = None) -> Path:
    names = ("contractor_tracker.db", "contractor_tracker.sqlite3", "app.db", "tracker.db")

    if candidate is not None:
        candidate = Path(candidate).expanduser()
        if candidate.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
            return candidate

        candidates = [candidate]
        if candidate.exists() and candidate.is_dir():
            candidates = [candidate] + list(candidate.parents)
        elif not candidate.name:
            candidates = [candidate]
        else:
            candidates = [candidate, candidate.parent] + list(candidate.parents)

        for root in candidates:
            for name in names:
                db_path = root / name if root != root.parent and root.exists() else root / name
                if db_path.exists():
                    return db_path

        if candidate.exists() and candidate.is_dir():
            return candidate / "contractor_tracker.db"
        if candidate.suffix == "":
            return candidate / "contractor_tracker.db"
        return candidate

    env_path = os.environ.get("CONTRACTOR_DB_PATH")
    if env_path:
        return Path(env_path).expanduser()

    roots = [APP_DIR, APP_DIR.parent, APP_DIR.parent.parent]
    for root in roots:
        for name in names:
            db_path = root / name
            if db_path.exists():
                return db_path

    return APP_DIR / "contractor_tracker.db"


DB_PATH = resolve_db_path()
DEFAULT_PHASES = [
    "Pre-Construction", "Site Preparation", "Foundation", "Structural",
    "Roofing", "Electrical", "Plumbing", "Finishes", "Inspection & Handover",
]
DEFAULT_EXPENSE_CATEGORIES = [
    "MATERIALS", "PAYROLL", "TOOLS & EQUIPMENT", "MOBILIZATION",
    "PERMITS", "SOP", "PERSONAL",
]

NAVY = "#0F1A2E"
NAVY_ACTIVE = "#243047"
ORANGE = "#F59E0B"
GREEN = "#10B981"
RED = "#EF4444"
INK = "#111827"
MUTED = "#6B7280"
SURFACE = "#F5F7FA"
WHITE = "#FFFFFF"


def cents(value: str | Decimal) -> int:
    try:
        amount = Decimal(str(value).replace(",", "").strip() or "0")
    except InvalidOperation as exc:
        raise ValueError("Enter a valid amount.") from exc
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def money(value: int | None) -> str:
    return f"{(value or 0) / 100:,.2f}"


def local_timestamp(value: datetime | None = None) -> str:
    """Return a sortable Philippine-local timestamp for new audit records."""
    return (value or datetime.now()).replace(microsecond=0).isoformat(sep=" ")


def write_simple_pdf(path: Path | str, title: str, lines: list[str]):
    """Write a dependency-free, searchable landscape PDF report."""
    wrapped = []
    for line in lines:
        wrapped.extend(textwrap.wrap(str(line), width=132, replace_whitespace=False) or [""])
    pages = [wrapped[index:index + 40] for index in range(0, len(wrapped), 40)] or [[]]
    font_id = 3 + len(pages) * 2
    objects = [None, None]
    page_ids = []
    for page_index, page_lines in enumerate(pages):
        page_id = 3 + page_index * 2
        content_id = page_id + 1
        page_ids.append(page_id)
        def pdf_text(value):
            return value.encode("latin-1", "replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands = ["BT", "/F1 9 Tf", "36 558 Td", "12 TL", f"({pdf_text(title)}) Tj", "T*"]
        commands += [f"({pdf_text(line)}) Tj T*" for line in page_lines]
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1", "replace")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        )
        objects.append(b"<< /Length " + str(len(stream)).encode() + b">>\nstream\n" + stream + b"\nendstream")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects[0] = "<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(f'{item} 0 R' for item in page_ids)}] /Count {len(page_ids)} >>"
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, value in enumerate(objects, 1):
        offsets.append(len(output))
        payload = value if isinstance(value, bytes) else value.encode("latin-1")
        output.extend(f"{object_id} 0 obj\n".encode() + payload + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    Path(path).write_bytes(output)


def write_expense_ledger_pdf(path: Path | str, filters: list[tuple[str, str]],
                             summary: list[str], rows: list[dict]):
    """Write a readable, dependency-free A4 landscape expense table at 10 pt."""
    page_width, page_height = 842, 595  # ISO A4 landscape in PDF points.
    margin, footer_height = 36, 38
    content_width = page_width - margin * 2
    font_size, leading = 10, 12
    columns = [
        ("project", "PROJECT", 38, "left"), ("batch", "BATCH REF", 42, "left"),
        ("status", "PAYMENT", 38, "left"), ("verification", "VERIFIED", 35, "left"),
        ("verification_ref", "VERIFY REF", 40, "left"),
        ("expense", "EXPENSE / ITEM", 64, "left"), ("mop", "MOP", 32, "left"),
        ("bank_ref", "BANK REF", 40, "left"), ("total", "TOTAL", 40, "right"),
        ("recovered", "RECOVERED", 35, "right"), ("net", "NET", 38, "right"),
        ("paid", "PAID", 40, "right"), ("outstanding", "OUTSTANDING", 43, "right"),
        ("date", "DATE", 42, "left"), ("allocation", "CASH REF", 45, "left"),
        ("withdrawal", "WITHDRAWAL", 45, "left"), ("supplier", "SUPPL.", 40, "left"),
        ("area", "AREA", 30, "left"), ("authorized", "HEAD", 43, "left"),
    ]
    if sum(column[2] for column in columns) != content_width:
        raise ValueError("Expense PDF columns must fill the printable page width.")

    def clean(value):
        return (str(value or "").replace("\u2013", "-").replace("\u2014", "-")
                .replace("\u2011", "-").encode("latin-1", "replace").decode("latin-1"))

    def escape(value):
        return clean(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def text_width(value, size=font_size, bold=False):
        total = 0.0
        for character in clean(value):
            if character == " ": factor = .278
            elif character in "ilI.,:;'|!": factor = .278
            elif character in "mwMW@%": factor = .89
            elif character.isupper(): factor = .69
            elif character.isdigit(): factor = .556
            else: factor = .53
            total += factor * size
        return total * (1.04 if bold else 1)

    def wrap_cell(value, width, bold=False):
        available = max(10, width - 8)
        raw_words = clean(value).replace("\r", " ").replace("\n", " ").split()
        words = []
        for word in raw_words:
            if "-" in word and text_width(word, bold=bold) > available:
                parts = word.split("-")
                words.extend(part + ("-" if index < len(parts) - 1 else "")
                             for index, part in enumerate(parts) if part)
            else:
                words.append(word)
        if not words:
            return [""]
        lines, current = [], ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if text_width(candidate, bold=bold) <= available:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
            fragment = ""
            for character in word:
                if fragment and text_width(fragment + character, bold=bold) > available:
                    lines.append(fragment)
                    fragment = character
                else:
                    fragment += character
            current = fragment
        if current or not lines:
            lines.append(current)
        return lines

    def add_text(commands, x, y, value, font="F1", size=font_size,
                 color="0.08 0.11 0.16", align="left", max_width=None):
        rendered = clean(value)
        if align == "right" and max_width is not None:
            x += max_width - text_width(rendered, size, font == "F2")
        commands.append(
            f"BT {color} rg /{font} {size} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm "
            f"({escape(rendered)}) Tj ET"
        )

    filter_text = " | ".join(f"{clean(label)}: {clean(value)}" for label, value in filters)
    summary_text = " | ".join(clean(value) for value in summary)
    pages = []

    def start_page(continued=False):
        commands = []
        add_text(commands, margin, page_height - 42,
                 "ConTracktor_v1 - Filtered Expense Ledger" + (" (continued)" if continued else ""),
                 font="F2", size=16)
        add_text(commands, margin, page_height - 61,
                 f"Exported {datetime.now():%Y-%m-%d %H:%M}", size=10, color="0.35 0.39 0.45")
        y = page_height - 86
        add_text(commands, margin, y, "APPLIED FILTERS", font="F2", size=10)
        y -= 15
        for line in wrap_cell(filter_text, content_width):
            add_text(commands, margin, y, line, size=10)
            y -= leading
        y -= 5
        add_text(commands, margin, y, "FINANCIAL SUMMARY", font="F2", size=10)
        y -= 15
        for line in wrap_cell(summary_text, content_width):
            add_text(commands, margin, y, line, size=10)
            y -= leading
        y -= 10
        header_height = 30
        commands.append(
            f"q 0.07 0.12 0.22 rg {margin} {y-header_height:.2f} {content_width} {header_height} re f Q"
        )
        x = margin
        for _key, heading, width, _align in columns:
            commands.append(
                f"q {x:.2f} {y-header_height:.2f} {width:.2f} {header_height:.2f} re W n"
            )
            # Keep the established two-line Expense / Item heading readable and
            # compatible with previously generated ledgers.
            if _key == "expense":
                lines = ["EXPENSE", "/ ITEM"]
            else:
                lines = wrap_cell(heading, width, bold=True)
            baseline = y - 12 if len(lines) == 1 else y - 10
            for line in lines[:2]:
                add_text(commands, x + 4, baseline, line, font="F2", size=10, color="1 1 1")
                baseline -= leading
            commands.append("Q")
            commands.append(f"0.65 0.69 0.76 RG 0.5 w {x:.2f} {y-header_height:.2f} {width:.2f} {header_height:.2f} re S")
            x += width
        pages.append(commands)
        return commands, y - header_height

    commands, y = start_page()
    for row_index, row in enumerate(rows):
        wrapped = {
            key: wrap_cell(row.get(key, ""), width)
            for key, _heading, width, _align in columns
        }
        line_count = max(len(lines) for lines in wrapped.values())
        row_height = max(26, line_count * leading + 8)
        if y - row_height < footer_height + 12:
            commands, y = start_page(continued=True)
        row_bottom = y - row_height
        if row_index % 2:
            commands.append(
                f"q 0.96 0.97 0.98 rg {margin} {row_bottom:.2f} {content_width} {row_height:.2f} re f Q"
            )
        x = margin
        for key, _heading, width, align in columns:
            commands.append(
                f"q {x+1:.2f} {row_bottom+1:.2f} {width-2:.2f} {row_height-2:.2f} re W n"
            )
            baseline = y - 15
            for line in wrapped[key]:
                if align == "right":
                    add_text(
                        commands, x + 4, baseline, line, size=10, align="right",
                        max_width=width - 8,
                    )
                else:
                    add_text(commands, x + 4, baseline, line, size=10)
                baseline -= leading
            commands.append("Q")
            commands.append(
                f"0.78 0.81 0.85 RG 0.45 w {x:.2f} {row_bottom:.2f} {width:.2f} {row_height:.2f} re S"
            )
            x += width
        y = row_bottom

    if not rows:
        add_text(commands, margin + 8, y - 24, "No expense rows matched the selected filters.", size=10)

    def amount_cents(value):
        try:
            return int((Decimal(clean(value).replace(",", "")) * 100).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            ))
        except (InvalidOperation, ValueError):
            return 0

    active_rows = [row for row in rows if clean(row.get("status", "")).upper() != "VOID"]
    status_groups = (
        ("PAID SUBTOTAL", "PAID"),
        ("UNPAID SUBTOTAL", "UNPAID"),
        ("PARTIALLY PAID SUBTOTAL", "PARTIALLY PAID"),
    )
    totals_rows = []
    for label, status in status_groups:
        matching = [row for row in active_rows if (
            clean(row.get("status", "")).upper().startswith("PARTIALLY PAID")
            if status == "PARTIALLY PAID" else clean(row.get("status", "")).upper().startswith(status)
        )]
        totals_rows.append((
            label,
            sum(amount_cents(row.get("net") or row.get("total")) for row in matching),
            sum(amount_cents(row.get("paid")) for row in matching),
            sum(amount_cents(row.get("outstanding")) for row in matching),
        ))
    totals_rows.append((
        "OVERALL TOTAL",
        sum(amount_cents(row.get("net") or row.get("total")) for row in active_rows),
        sum(amount_cents(row.get("paid")) for row in active_rows),
        sum(amount_cents(row.get("outstanding")) for row in active_rows),
    ))

    totals_height = 30 + 25 * (len(totals_rows) + 1) + 18
    if y - totals_height < footer_height + 12:
        commands = []
        add_text(commands, margin, page_height - 42,
                 "ConTracktor_v1 - Filtered Expense Ledger Totals", font="F2", size=16)
        add_text(commands, margin, page_height - 61,
                 f"Exported {datetime.now():%Y-%m-%d %H:%M}", size=10, color="0.35 0.39 0.45")
        pages.append(commands)
        y = page_height - 86
    else:
        y -= 18

    add_text(commands, margin, y, "TOTALS BY STATUS", font="F2", size=12)
    y -= 12
    total_columns = (
        ("CATEGORY", 200, "left"),
        ("EXPENSE TOTAL", 190, "right"),
        ("PAYMENTS RECORDED", 190, "right"),
        ("OUTSTANDING", 190, "right"),
    )
    header_height = 25
    commands.append(
        f"q 0.07 0.12 0.22 rg {margin} {y-header_height:.2f} {content_width} {header_height} re f Q"
    )
    x = margin
    for heading, width, align in total_columns:
        add_text(commands, x + 4, y - 16, heading, font="F2", size=10, color="1 1 1",
                 align=align, max_width=width - 8)
        commands.append(f"0.65 0.69 0.76 RG 0.5 w {x:.2f} {y-header_height:.2f} {width:.2f} {header_height:.2f} re S")
        x += width
    y -= header_height
    for index, (label, expense_total, payments_total, outstanding_total) in enumerate(totals_rows):
        row_height = 25
        row_bottom = y - row_height
        if label == "OVERALL TOTAL":
            commands.append(
                f"q 0.88 0.92 0.97 rg {margin} {row_bottom:.2f} {content_width} {row_height:.2f} re f Q"
            )
        elif index % 2:
            commands.append(
                f"q 0.96 0.97 0.98 rg {margin} {row_bottom:.2f} {content_width} {row_height:.2f} re f Q"
            )
        values = (label, money(expense_total), money(payments_total), money(outstanding_total))
        x = margin
        for (heading, width, align), value in zip(total_columns, values):
            add_text(commands, x + 4, y - 16, value,
                     font="F2" if label == "OVERALL TOTAL" else "F1", size=10,
                     align=align, max_width=width - 8)
            commands.append(f"0.78 0.81 0.85 RG 0.45 w {x:.2f} {row_bottom:.2f} {width:.2f} {row_height:.2f} re S")
            x += width
        y = row_bottom

    page_count = len(pages)
    for page_number, page_commands in enumerate(pages, 1):
        page_commands.append(
            f"0.65 0.69 0.76 RG 0.5 w {margin} 30 m {page_width-margin} 30 l S"
        )
        footer = f"ConTracktor_v1 | Page {page_number} of {page_count}"
        footer_x = (page_width - text_width(footer, 10)) / 2
        add_text(page_commands, footer_x, 16, footer, size=10, color="0.35 0.39 0.45")

    font_regular_id = 3 + len(pages) * 2
    font_bold_id = font_regular_id + 1
    objects = [None, None]
    page_ids = []
    for page_index, page_commands in enumerate(pages):
        page_id = 3 + page_index * 2
        content_id = page_id + 1
        page_ids.append(page_id)
        stream = "\n".join(page_commands).encode("latin-1", "replace")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] "
            f"/Resources << /Font << /F1 {font_regular_id} 0 R /F2 {font_bold_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        )
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b">>\nstream\n" + stream + b"\nendstream"
        )
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    objects[0] = "<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = (
        f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] "
        f"/Count {len(page_ids)} >>"
    )
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, value in enumerate(objects, 1):
        offsets.append(len(output))
        payload = value if isinstance(value, bytes) else value.encode("latin-1")
        output.extend(f"{object_id} 0 obj\n".encode() + payload + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    Path(path).write_bytes(output)


def qty_decimal(value: str) -> Decimal:
    try:
        result = Decimal(value.strip() or "0")
        if result < 0:
            raise ValueError
        return result
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Quantity must be a non-negative number.") from exc


def inventory_quantity_milli(value: str | Decimal, *, positive: bool = False) -> int:
    """Store stock quantities to three decimal places without floating-point drift."""
    try:
        quantity = Decimal(str(value).replace(",", "").strip() or "0")
    except InvalidOperation as exc:
        raise ValueError("Enter a valid inventory quantity.") from exc
    if quantity < 0 or (positive and quantity <= 0):
        raise ValueError("Inventory quantity must be greater than zero." if positive
                         else "Inventory quantity cannot be negative.")
    return int((quantity * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def inventory_quantity(value_milli: int | None) -> str:
    quantity = Decimal(value_milli or 0) / 1000
    text = f"{quantity:,.3f}".rstrip("0").rstrip(".")
    return text or "0"


def valid_date(value: str, required: bool = False) -> str:
    value = value.strip()
    if not value and not required:
        return ""
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Dates must use YYYY-MM-DD format.") from exc
    return value


def flash_required_widgets(window, widgets, *, pulses: int = 3):
    """Highlight required ttk input boxes without closing their form.

    The original widget styles are restored after a short red pulse.  Keeping
    this behavior in one helper makes validation consistent across dialogs.
    """
    widgets = [widget for widget in widgets if widget is not None and widget.winfo_exists()]
    if not widgets:
        try:
            window.bell()
        except tk.TclError:
            pass
        return
    original = {}
    for widget in widgets:
        try:
            original[widget] = widget.cget("style")
            required_style = (
                "Required.TCombobox" if isinstance(widget, ttk.Combobox)
                else "Required.TEntry"
            )
            widget.configure(style=required_style)
        except tk.TclError:
            original[widget] = None

    def pulse(step=0):
        on = step % 2 == 0
        for widget in widgets:
            try:
                widget.configure(style=(
                    ("Required.TCombobox" if isinstance(widget, ttk.Combobox)
                     else "Required.TEntry") if on else original.get(widget, "")
                ))
            except tk.TclError:
                pass
        if step < pulses * 2 - 1:
            window.after(145, lambda: pulse(step + 1))
        else:
            for widget in widgets:
                try:
                    widget.configure(style=original.get(widget, ""))
                except tk.TclError:
                    pass

    try:
        widgets[0].focus_set()
        window.bell()
    except tk.TclError:
        pass
    pulse()


def flash_missing_fields(window, variables, widgets, required):
    """Flash empty required fields and return True when any are missing."""
    missing = [key for key in required if not variables[key].get().strip()]
    if missing:
        flash_required_widgets(window, [widgets.get(key) for key in missing])
        return True
    return False


def flash_invalid_standard_fields(window, variables, widgets):
    """Validate common date and numeric fields without dismissing a form.

    Form-specific business rules are still enforced by their callers.  This
    catches malformed values at the reusable dialog layer so the user can
    correct them in place instead of having to reopen the window.
    """
    date_keys = {
        "date", "deadline", "start_date", "target_date", "expense_date",
        "due_date", "payment_date", "txn_date", "advance_date",
    }
    money_keys = {
        "amount", "contract_value", "unit_price", "rate", "daily_rate",
        "initial_payment", "weekly_cap",
    }
    decimal_keys = {"qty", "quantity", "standard_hours"}
    positive_keys = {"amount", "rate", "daily_rate", "standard_hours", "qty", "quantity"}
    invalid = []
    messages = []
    for key, variable in variables.items():
        value = variable.get().strip()
        if not value:
            continue
        try:
            if key in date_keys or key.endswith("_date"):
                valid_date(value, True)
            elif key in money_keys:
                parsed = cents(value)
                if key in positive_keys and parsed <= 0:
                    raise ValueError(f"{key.replace('_', ' ').title()} must be greater than zero.")
            elif key in decimal_keys:
                parsed = qty_decimal(value)
                if key in positive_keys and parsed <= 0:
                    raise ValueError(f"{key.replace('_', ' ').title()} must be greater than zero.")
        except ValueError as exc:
            invalid.append(key)
            messages.append(str(exc))
    if invalid:
        flash_required_widgets(window, [widgets.get(key) for key in invalid])
        messagebox.showerror(APP_TITLE, messages[0], parent=window)
        return True
    return False


EXPENSE_IMPORT_HEADERS = (
    ("project", "Project*"),
    ("item", "Item Name / Description*"),
    ("dimensions", "Size / Dimensions*"),
    ("supplier", "Supplier*"),
    ("qty", "Quantity*"),
    ("unit_price", "Unit Price*"),
    ("phase", "Phase*"),
    ("area", "Area / Category*"),
    ("status", "Payment State*"),
    ("initial_payment", "Paid Amount"),
    ("payment_method", "Payment Method*"),
    ("bank", "Bank for Transfer"),
    ("cash_allocation", "Cash Allocation Reference"),
    ("expense_date", "Expense Date*"),
    ("notes", "Notes"),
    ("source_reference", "Source Reference"),
)


def _normalized_import_header(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def write_expense_import_form(path, draft_reference):
    """Write a Google-Sheets/Excel-ready CSV expense form."""
    with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["CONTRACTOR EXPENSE BATCH IMPORT FORM"])
        writer.writerow(["Draft Reference", draft_reference])
        writer.writerow(["Declared Batch Total (required)", ""])
        writer.writerow([
            "Instructions",
            "Fill every * field. Use one project per form. Do not change header names. "
            "The complete form is rejected if any row is invalid or the declared total does not reconcile.",
        ])
        writer.writerow([])
        writer.writerow([label for _key, label in EXPENSE_IMPORT_HEADERS])
        writer.writerow([
            "Example: PROJECT OASIS", "Example item", "N/A", "Example supplier", "1",
            "0.00", "Example phase", "MATERIALS", "Unpaid", "0.00", "Cash", "", "",
            date.today().isoformat(), "Delete this example row before import", "",
        ])


def _xlsx_inline_cell(reference, value, style=0):
    value = xml_escape(str(value or ""))
    style_attr = f' s="{style}"' if style else ""
    return f'<c r="{reference}" t="inlineStr"{style_attr}><is><t>{value}</t></is></c>'


def write_expense_import_xlsx(path, draft_reference, reference_lists):
    """Create a dependency-free Excel workbook with database-backed dropdowns."""
    headers = [label for _key, label in EXPENSE_IMPORT_HEADERS] + ["Calculated Row Total"]
    column_letters = [chr(65 + index) for index in range(len(headers))]
    rows = [
        '<row r="1" ht="28">' + _xlsx_inline_cell("A1", "CONTRACTOR EXPENSE BATCH IMPORT FORM", 1) + '</row>',
        '<row r="2">' + _xlsx_inline_cell("A2", "Draft Reference", 2)
        + _xlsx_inline_cell("B2", draft_reference, 4) + '</row>',
        '<row r="3">' + _xlsx_inline_cell("A3", "Declared Batch Total (required)", 2)
        + '<c r="B3" s="5"/></row>',
        '<row r="4" ht="34">' + _xlsx_inline_cell(
            "A4",
            "Fill every * field and use one project per workbook. The complete form is rejected when any row is invalid or the declared total does not match.",
            4,
        ) + '</row>',
        '<row r="6" ht="32">' + ''.join(
            _xlsx_inline_cell(f"{letter}6", header, 3)
            for letter, header in zip(column_letters, headers)
        ) + '</row>',
    ]
    for row_number in range(7, 507):
        cells = []
        for index, letter in enumerate(column_letters[:-1]):
            style = 5 if index in {4, 5, 9} else 4
            cells.append(_xlsx_inline_cell(f"{letter}{row_number}", "", style))
        cells.append(
            f'<c r="Q{row_number}" s="5"><f>IF(OR(E{row_number}="",F{row_number}=""),"",E{row_number}*F{row_number})</f></c>'
        )
        rows.append(f'<row r="{row_number}">' + ''.join(cells) + '</row>')

    list_order = [
        ("projects", "Projects"), ("suppliers", "Suppliers"), ("phases", "Phases"),
        ("categories", "Categories"), ("statuses", "Payment States"),
        ("methods", "Payment Methods"), ("banks", "Banks"),
        ("allocations", "Cash Allocations"),
    ]
    reference_rows = []
    max_length = max((len(reference_lists.get(key, [])) for key, _title in list_order), default=0)
    reference_rows.append(
        '<row r="1">' + ''.join(
            _xlsx_inline_cell(f"{chr(65 + index)}1", title, 3)
            for index, (_key, title) in enumerate(list_order)
        ) + '</row>'
    )
    for offset in range(max_length):
        row_number = offset + 2
        cells = []
        for index, (key, _title) in enumerate(list_order):
            values = reference_lists.get(key, [])
            if offset < len(values):
                cells.append(_xlsx_inline_cell(f"{chr(65 + index)}{row_number}", values[offset]))
        reference_rows.append(f'<row r="{row_number}">' + ''.join(cells) + '</row>')

    validation_map = [
        ("A7:A506", 0), ("D7:D506", 1), ("G7:G506", 2), ("H7:H506", 3),
        ("I7:I506", 4), ("K7:K506", 5), ("L7:L506", 6), ("M7:M506", 7),
    ]
    range_names = (
        "ProjectOptions", "SupplierOptions", "PhaseOptions", "CategoryOptions",
        "PaymentStateOptions", "PaymentMethodOptions", "BankOptions", "CashAllocationOptions",
    )
    validations = []
    for target, list_index in validation_map:
        key, _title = list_order[list_index]
        count = max(1, len(reference_lists.get(key, [])))
        letter = chr(65 + list_index)
        formula = range_names[list_index]
        validations.append(
            f'<dataValidation type="list" allowBlank="0" showErrorMessage="1" '
            f'errorStyle="stop" errorTitle="Invalid selection" '
            f'error="Choose a value from this workbook dropdown." sqref="{target}">'
            f'<formula1>{formula}</formula1></dataValidation>'
        )
    validations.append(
        '<dataValidation type="date" operator="between" allowBlank="0" showErrorMessage="1" '
        'errorStyle="stop" errorTitle="Invalid date" error="Enter a valid expense date." sqref="N7:N506">'
        '<formula1>DATE(2000,1,1)</formula1><formula2>DATE(2100,12,31)</formula2></dataValidation>'
    )

    sheet_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetViews><sheetView workbookViewId="0"><pane ySplit="6" topLeftCell="A7" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
<cols>{''.join(f'<col min="{i+1}" max="{i+1}" width="{width}" customWidth="1"/>' for i, width in enumerate([24,30,18,24,12,14,20,20,18,15,18,30,36,15,30,20,18]))}</cols>
<sheetData>{''.join(rows)}</sheetData>
<autoFilter ref="A6:Q506"/>
<mergeCells count="2"><mergeCell ref="A1:Q1"/><mergeCell ref="A4:Q4"/></mergeCells>
<dataValidations count="{len(validations)}">{''.join(validations)}</dataValidations>
<pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>
</worksheet>'''
    reference_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetData>{''.join(reference_rows)}</sheetData>
</worksheet>'''
    styles_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="2"><numFmt numFmtId="164" formatCode="#,##0.00"/><numFmt numFmtId="165" formatCode="yyyy-mm-dd"/></numFmts>
<fonts count="3"><font><sz val="10"/><name val="Segoe UI"/></font><font><b/><sz val="16"/><color rgb="FF0F1B2D"/><name val="Segoe UI"/></font><font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Segoe UI"/></font></fonts>
<fills count="5"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF0F1B2D"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFF4CC"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF8FAFC"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="2"><border/><border><left style="thin"><color rgb="FFCBD5E1"/></left><right style="thin"><color rgb="FFCBD5E1"/></right><top style="thin"><color rgb="FFCBD5E1"/></top><bottom style="thin"><color rgb="FFCBD5E1"/></bottom></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="6"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/><xf numFmtId="0" fontId="0" fillId="4" borderId="0" xfId="0"/><xf numFmtId="0" fontId="2" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment wrapText="1" horizontal="center" vertical="center"/></xf><xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf><xf numFmtId="164" fontId="0" fillId="3" borderId="1" xfId="0" applyNumberFormat="1"/></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''
    defined_names = ''.join(
        f'<definedName name="{range_names[index]}">\'Reference Lists\'!${chr(65 + index)}$2:${chr(65 + index)}${max(1, len(reference_lists.get(key, []))) + 1}</definedName>'
        for index, (key, _title) in enumerate(list_order)
    )
    workbook_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<bookViews><workbookView xWindow="0" yWindow="0" windowWidth="24000" windowHeight="14000"/></bookViews>
<sheets><sheet name="Expense Form" sheetId="1" r:id="rId1"/><sheet name="Reference Lists" sheetId="2" state="hidden" r:id="rId2"/></sheets>
<definedNames>{defined_names}</definedNames>
<calcPr calcId="191029" calcMode="auto" fullCalcOnLoad="1" forceFullCalc="1"/>
</workbook>'''
    workbook_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>'''
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/styles.xml", styles_xml)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        archive.writestr("xl/worksheets/sheet2.xml", reference_xml)


def _xlsx_cell_value(cell, shared_strings):
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    cell_type = cell.attrib.get("t", "")
    value = cell.find(namespace + "v")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//" + namespace + "t"))
    if value is None:
        return ""
    raw = value.text or ""
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError):
            return raw
    return raw


def _read_xlsx_rows(path):
    """Read displayed cell values from the first worksheet without dependencies."""
    main_ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rel_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    package_rel_ns = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    with zipfile.ZipFile(path) as archive:
        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(main_ns + "si"):
                shared_strings.append("".join(node.text or "" for node in item.findall(".//" + main_ns + "t")))
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        first_sheet = workbook.find(".//" + main_ns + "sheet")
        if first_sheet is None:
            raise ValueError("The workbook has no worksheet.")
        relation_id = first_sheet.attrib.get(rel_ns + "id")
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = None
        for relation in relations.findall(package_rel_ns + "Relationship"):
            if relation.attrib.get("Id") == relation_id:
                target = relation.attrib.get("Target")
                break
        if not target:
            raise ValueError("The first worksheet could not be read.")
        sheet_path = target.lstrip("/")
        if not sheet_path.startswith("xl/"):
            sheet_path = "xl/" + sheet_path
        sheet = ET.fromstring(archive.read(sheet_path))
        rows = []
        for row in sheet.findall(".//" + main_ns + "row"):
            values = {}
            for cell in row.findall(main_ns + "c"):
                reference = cell.attrib.get("r", "A1")
                letters = re.match(r"[A-Z]+", reference.upper()).group(0)
                column = 0
                for letter in letters:
                    column = column * 26 + ord(letter) - 64
                values[column - 1] = _xlsx_cell_value(cell, shared_strings)
            width = max(values, default=-1) + 1
            rows.append([values.get(index, "") for index in range(width)])
        return rows


def read_expense_import_form(path):
    """Return draft metadata and populated expense rows from CSV or XLSX."""
    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        with Path(path).open("r", newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.reader(handle))
    elif suffix == ".xlsx":
        try:
            rows = _read_xlsx_rows(path)
        except (KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
            raise ValueError("The selected XLSX file is damaged or is not a valid workbook.") from exc
    else:
        raise ValueError("Choose a .csv or .xlsx expense import form.")
    metadata = {}
    header_index = None
    expected = {_normalized_import_header(label): key for key, label in EXPENSE_IMPORT_HEADERS}
    column_keys = {}
    for index, row in enumerate(rows):
        if row:
            first = _normalized_import_header(row[0])
            if first == "draftreference" and len(row) > 1:
                metadata["draft_reference"] = str(row[1]).strip()
            elif first == "declaredbatchtotalrequired" and len(row) > 1:
                metadata["declared_total"] = str(row[1]).strip()
        normalized = [_normalized_import_header(value) for value in row]
        matches = sum(value in expected for value in normalized)
        if matches >= 8 and "itemnamedescription" in normalized:
            header_index = index
            column_keys = {col: expected[value] for col, value in enumerate(normalized) if value in expected}
            break
    if header_index is None:
        raise ValueError("The form headers were not found. Generate a fresh import form and keep its headers unchanged.")
    data_rows = []
    for row_number, row in enumerate(rows[header_index + 1:], header_index + 2):
        values = {key: (str(row[col]).strip() if col < len(row) else "") for col, key in column_keys.items()}
        if any(values.values()):
            values["source_row"] = row_number
            data_rows.append(values)
    metadata.setdefault("draft_reference", "")
    metadata.setdefault("declared_total", "")
    return metadata, data_rows


def employee_daily_rate(employee) -> int:
    """Return an employee's daily rate without rewriting legacy payroll fields."""
    try:
        stored = int(employee["daily_rate_cents"] or 0)
    except (KeyError, IndexError):
        stored = 0
    if stored:
        return stored
    rate = int(employee["rate_cents"] or 0)
    return rate * 8 if str(employee["pay_basis"]).strip().lower() == "hourly" else rate


def employee_age(birthday: str, on_date: date | None = None) -> str:
    if not birthday:
        return ""
    try:
        born = date.fromisoformat(birthday)
    except ValueError:
        return ""
    today = on_date or date.today()
    return str(today.year - born.year - ((today.month, today.day) < (born.month, born.day)))


def payroll_week_bounds(value: str | date) -> tuple[str, str]:
    """Return the Saturday-Friday payroll week containing *value*."""
    selected = date.fromisoformat(value) if isinstance(value, str) else value
    # Python weekday(): Monday=0 ... Saturday=5, Sunday=6.
    saturday = selected - timedelta(days=(selected.weekday() - 5) % 7)
    return saturday.isoformat(), (saturday + timedelta(days=6)).isoformat()


def employee_photo_image(blob: bytes | None, max_size: int = 170):
    """Create a display-sized Tk image from a stored PNG blob."""
    if not blob:
        return None
    try:
        image = tk.PhotoImage(data=base64.b64encode(blob))
        largest = max(image.width(), image.height())
        factor = max(1, (largest + max_size - 1) // max_size)
        return image.subsample(factor, factor) if factor > 1 else image
    except tk.TclError:
        return None


def normalized_employee_photo(path: str | Path) -> bytes:
    """Return a square PNG suitable for portable SQLite attachment storage."""
    source = Path(path)
    if not source.is_file():
        raise ValueError("Select an existing picture file.")
    if source.stat().st_size > 12 * 1024 * 1024:
        raise ValueError("The selected picture is larger than 12 MB.")
    if source.suffix.lower() == ".png":
        payload = source.read_bytes()
        if payload.startswith(b"\x89PNG\r\n\x1a\n"):
            return payload
    destination = Path(tempfile.gettempdir()) / f"contractor_photo_{os.getpid()}_{datetime.now():%f}.png"
    try:
        try:
            # Tk handles GIF/PPM/PGM without third-party dependencies.
            image = tk.PhotoImage(file=str(source))
            image.write(str(destination), format="png")
        except tk.TclError:
            if os.name != "nt":
                raise ValueError("Use a PNG picture on this computer.")
            # Windows' built-in drawing library handles JPEG/BMP and also
            # center-crops the attachment into a true square profile image.
            script = r"""
$sourcePath=$env:CONTRACTOR_PHOTO_SOURCE
$destinationPath=$env:CONTRACTOR_PHOTO_DESTINATION
Add-Type -AssemblyName System.Drawing
$image=[System.Drawing.Image]::FromFile($sourcePath)
try {
  $side=[Math]::Min($image.Width,$image.Height)
  $sourceX=[int](($image.Width-$side)/2)
  $sourceY=[int](($image.Height-$side)/2)
  $bitmap=New-Object System.Drawing.Bitmap 240,240
  $graphics=[System.Drawing.Graphics]::FromImage($bitmap)
  try {
    $graphics.InterpolationMode=[System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $graphics.DrawImage($image,
      ([System.Drawing.Rectangle]::new(0,0,240,240)),
      ([System.Drawing.Rectangle]::new($sourceX,$sourceY,$side,$side)),
      [System.Drawing.GraphicsUnit]::Pixel)
    $bitmap.Save($destinationPath,[System.Drawing.Imaging.ImageFormat]::Png)
  } finally { $graphics.Dispose(); $bitmap.Dispose() }
} finally { $image.Dispose() }
"""
            photo_environment = os.environ.copy()
            photo_environment["CONTRACTOR_PHOTO_SOURCE"] = str(source.resolve())
            photo_environment["CONTRACTOR_PHOTO_DESTINATION"] = str(destination.resolve())
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", script],
                capture_output=True, text=True, env=photo_environment,
                timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if completed.returncode or not destination.exists():
                raise ValueError("The picture could not be read. Try a PNG or JPEG image.")
        payload = destination.read_bytes()
        if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("The picture could not be converted to PNG.")
        return payload
    finally:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass


def compute_shift_pay(clock_in: datetime, clock_out: datetime, daily_rate_cents: int,
                      day_type: str = "Ordinary Day") -> dict:
    """Calculate paid time, lunch exclusion, regular time, and Philippine OT premiums."""
    if clock_out <= clock_in:
        raise ValueError("Time out must be later than time in.")
    elapsed_seconds = Decimal(str((clock_out - clock_in).total_seconds()))
    lunch_seconds = Decimal("0")
    work_day = clock_in.date()
    while work_day <= clock_out.date():
        lunch_start = datetime.combine(work_day, time(12, 0))
        lunch_end = datetime.combine(work_day, time(13, 0))
        overlap_start, overlap_end = max(clock_in, lunch_start), min(clock_out, lunch_end)
        if overlap_end > overlap_start:
            lunch_seconds += Decimal(str((overlap_end - overlap_start).total_seconds()))
        work_day += timedelta(days=1)
    paid_hours = max(Decimal("0"), (elapsed_seconds - lunch_seconds) / Decimal("3600"))
    regular_hours = min(Decimal("8"), paid_hours)
    overtime_hours = max(Decimal("0"), paid_hours - Decimal("8"))
    daily_rate = Decimal(daily_rate_cents)
    hourly_rate = daily_rate / Decimal("8")
    normalized = (day_type or "Ordinary Day").strip().lower()
    if "regular holiday" in normalized:
        regular_multiplier, overtime_multiplier = Decimal("2.00"), Decimal("2.60")
    elif "rest" in normalized or "special" in normalized:
        regular_multiplier, overtime_multiplier = Decimal("1.30"), Decimal("1.69")
    else:
        regular_multiplier, overtime_multiplier = Decimal("1.00"), Decimal("1.25")
    regular_pay = int((regular_hours * hourly_rate * regular_multiplier).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP))
    overtime_pay = int((overtime_hours * hourly_rate * overtime_multiplier).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP))
    hours = lambda value: str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return {
        "hours": hours(paid_hours),
        "lunch_hours": hours(lunch_seconds / Decimal("3600")),
        "regular_hours": hours(regular_hours),
        "overtime_hours": hours(overtime_hours),
        "regular_pay_cents": regular_pay,
        "overtime_pay_cents": overtime_pay,
        "gross_cents": regular_pay + overtime_pay,
        "hourly_rate": hourly_rate,
    }


def hash_pin(pin: str, salt: bytes | None = None) -> tuple[str, str]:
    if len(pin) < 4:
        raise ValueError("PIN must contain at least 4 characters.")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 150_000)
    return salt.hex(), digest.hex()


def verify_pin(pin: str, salt_hex: str, digest_hex: str) -> bool:
    _, candidate = hash_pin(pin, bytes.fromhex(salt_hex))
    return secrets.compare_digest(candidate, digest_hex)


class Database:
    def __init__(self, path: Path | str | None = DB_PATH):
        self.path = resolve_db_path(path)
        self.migration_backup = self._backup_before_shared_cash_migration()
        self.v120_migration_backup = self._backup_before_v120_migration()
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._create_schema()

    def _backup_before_shared_cash_migration(self):
        """Create one recoverable copy before the shared-cash/reference upgrade."""
        path = Path(self.path)
        if not path.exists() or path.stat().st_size == 0:
            return None
        try:
            probe = sqlite3.connect(path)
            migrated = probe.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cash_allocation_sources'"
            ).fetchone()
            probe.close()
            if migrated:
                return None
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = path.with_name(f"{path.stem}_before_shared_cash_{stamp}{path.suffix}")
            shutil.copy2(path, backup)
            return backup
        except (OSError, sqlite3.Error):
            # Migration itself remains transactional; inability to create the
            # convenience copy must not make an otherwise healthy database unusable.
            return None

    def _backup_before_v120_migration(self):
        """Create a recoverable database copy before the v1.2 schema/data repair."""
        path = Path(self.path)
        if not path.exists() or path.stat().st_size == 0:
            return None
        try:
            probe = sqlite3.connect(path)
            has_meta = probe.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='app_metadata'"
            ).fetchone()
            version = None
            if has_meta:
                row = probe.execute(
                    "SELECT value FROM app_metadata WHERE key='schema_version'"
                ).fetchone()
                version = row[0] if row else None
            probe.close()
            if version == "1.2.0":
                return None
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = path.with_name(f"{path.stem}_before_v1_2_0_{stamp}{path.suffix}")
            shutil.copy2(path, backup)
            return backup
        except (OSError, sqlite3.Error):
            return None

    def _create_schema(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, client TEXT NOT NULL DEFAULT '',
            contract_value_cents INTEGER NOT NULL DEFAULT 0, start_date TEXT NOT NULL DEFAULT '',
            target_date TEXT NOT NULL DEFAULT '', address TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS phases (
            id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS project_heads (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name TEXT NOT NULL, position TEXT NOT NULL DEFAULT '',
            pin_salt TEXT NOT NULL, pin_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS app_metadata (
            key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS head_registry (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, position TEXT NOT NULL DEFAULT '',
            pin_salt TEXT NOT NULL, pin_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY, phase_id INTEGER NOT NULL REFERENCES phases(id) ON DELETE CASCADE,
            milestone TEXT NOT NULL DEFAULT '', name TEXT NOT NULL, deadline TEXT NOT NULL DEFAULT '',
            completed INTEGER NOT NULL DEFAULT 0, completed_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name TEXT NOT NULL, item TEXT NOT NULL DEFAULT '', dimensions TEXT NOT NULL DEFAULT '',
            supplier TEXT NOT NULL DEFAULT '', qty TEXT NOT NULL DEFAULT '1', unit TEXT NOT NULL DEFAULT '',
            unit_price_cents INTEGER NOT NULL DEFAULT 0, total_cents INTEGER NOT NULL DEFAULT 0,
            phase_id INTEGER REFERENCES phases(id) ON DELETE SET NULL, area TEXT NOT NULL DEFAULT '',
            trade TEXT NOT NULL DEFAULT '', expense_date TEXT NOT NULL, due_date TEXT NOT NULL DEFAULT '',
            invoice_no TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            voided INTEGER NOT NULL DEFAULT 0, payroll_batch TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY, expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0), payment_date TEXT NOT NULL,
            method TEXT NOT NULL DEFAULT '', reference TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '', bank_account_id INTEGER REFERENCES bank_accounts(id),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name TEXT NOT NULL, role TEXT NOT NULL DEFAULT '', company TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', address TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            employee_no TEXT NOT NULL, pin_salt TEXT NOT NULL, pin_hash TEXT NOT NULL, name TEXT NOT NULL,
            position TEXT NOT NULL DEFAULT '', class TEXT NOT NULL DEFAULT 'Labor',
            pay_basis TEXT NOT NULL DEFAULT 'Daily', rate_cents INTEGER NOT NULL DEFAULT 0,
            standard_hours TEXT NOT NULL DEFAULT '8', active INTEGER NOT NULL DEFAULT 1,
            UNIQUE(project_id, employee_no)
        );
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            clock_in TEXT NOT NULL, clock_out TEXT NOT NULL DEFAULT '', hours TEXT NOT NULL DEFAULT '',
            gross_cents INTEGER NOT NULL DEFAULT 0,
            committed_expense_id INTEGER REFERENCES expenses(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS payroll_batches (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            batch_ref TEXT NOT NULL UNIQUE, period_start TEXT NOT NULL, period_end TEXT NOT NULL,
            gross_cents INTEGER NOT NULL DEFAULT 0, deduction_cents INTEGER NOT NULL DEFAULT 0,
            net_cents INTEGER NOT NULL DEFAULT 0,
            expense_id INTEGER REFERENCES expenses(id) ON DELETE SET NULL,
            authorized_by_head_id INTEGER REFERENCES project_heads(id),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS attendance_closure_batches (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            closure_ref TEXT NOT NULL UNIQUE,
            work_date TEXT NOT NULL,
            attendance_count INTEGER NOT NULL DEFAULT 0,
            gross_cents INTEGER NOT NULL DEFAULT 0,
            authorized_by_head_id INTEGER REFERENCES project_heads(id),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS employee_project_assignments (
            id INTEGER PRIMARY KEY,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            effective_from TEXT NOT NULL,
            effective_to TEXT NOT NULL DEFAULT '',
            position TEXT NOT NULL DEFAULT '',
            daily_rate_cents INTEGER NOT NULL DEFAULT 0,
            reason TEXT NOT NULL DEFAULT '',
            authorized_by_head_id INTEGER REFERENCES project_heads(id),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS attendance_revisions (
            id INTEGER PRIMARY KEY,
            attendance_id INTEGER NOT NULL REFERENCES attendance(id) ON DELETE CASCADE,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            old_clock_in TEXT NOT NULL, old_clock_out TEXT NOT NULL,
            new_clock_in TEXT NOT NULL, new_clock_out TEXT NOT NULL,
            old_gross_cents INTEGER NOT NULL DEFAULT 0,
            new_gross_cents INTEGER NOT NULL DEFAULT 0,
            payroll_batch_id INTEGER REFERENCES payroll_batches(id) ON DELETE SET NULL,
            correction_reason TEXT NOT NULL,
            authorized_by_head_id INTEGER REFERENCES project_heads(id),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS payroll_adjustments (
            id INTEGER PRIMARY KEY,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            source_attendance_id INTEGER REFERENCES attendance(id) ON DELETE SET NULL,
            source_payroll_batch_id INTEGER REFERENCES payroll_batches(id) ON DELETE SET NULL,
            amount_cents INTEGER NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            applied_payroll_batch_id INTEGER REFERENCES payroll_batches(id) ON DELETE SET NULL,
            authorized_by_head_id INTEGER REFERENCES project_heads(id),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS remittances (
            id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            type TEXT NOT NULL CHECK(type IN ('Deposit','Withdrawal')), amount_cents INTEGER NOT NULL,
            txn_date TEXT NOT NULL, purpose TEXT NOT NULL DEFAULT '', care_of TEXT NOT NULL DEFAULT '',
            signature TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            voided INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS bank_accounts (
            id INTEGER PRIMARY KEY, bank_name TEXT NOT NULL, account_name TEXT NOT NULL DEFAULT '',
            account_number TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(bank_name, account_number)
        );
        CREATE TABLE IF NOT EXISTS bank_account_transfers (
            id INTEGER PRIMARY KEY,
            reference TEXT NOT NULL UNIQUE,
            from_bank_account_id INTEGER NOT NULL REFERENCES bank_accounts(id),
            to_bank_account_id INTEGER NOT NULL REFERENCES bank_accounts(id),
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
            transfer_date TEXT NOT NULL,
            transaction_time TEXT NOT NULL DEFAULT '',
            purpose TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            authorized_by_registry_id INTEGER REFERENCES head_registry(id),
            voided INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK(from_bank_account_id <> to_bank_account_id)
        );
        CREATE TABLE IF NOT EXISTS cash_allocations (
            id INTEGER PRIMARY KEY,
            reference TEXT NOT NULL UNIQUE,
            withdrawal_id INTEGER NOT NULL REFERENCES remittances(id),
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            allocation_type TEXT NOT NULL CHECK(allocation_type IN ('Petty Cash','Direct Procurement')),
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
            allocation_date TEXT NOT NULL,
            custodian_head_id INTEGER REFERENCES project_heads(id),
            responsible_head_id INTEGER REFERENCES project_heads(id),
            supplier TEXT NOT NULL DEFAULT '', purpose TEXT NOT NULL DEFAULT '',
            issuer_head_id INTEGER NOT NULL REFERENCES project_heads(id),
            receiver_head_id INTEGER NOT NULL REFERENCES project_heads(id),
            status TEXT NOT NULL DEFAULT 'Active',
            accepted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            closed_at TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            voided INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS cash_allocation_transactions (
            id INTEGER PRIMARY KEY,
            allocation_id INTEGER NOT NULL REFERENCES cash_allocations(id) ON DELETE CASCADE,
            txn_type TEXT NOT NULL,
            amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
            txn_date TEXT NOT NULL,
            expense_id INTEGER REFERENCES expenses(id) ON DELETE SET NULL,
            payment_id INTEGER REFERENCES payments(id) ON DELETE SET NULL,
            actor_head_id INTEGER REFERENCES project_heads(id),
            counterparty_head_id INTEGER REFERENCES project_heads(id),
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS cash_allocation_sources (
            allocation_id INTEGER NOT NULL REFERENCES cash_allocations(id) ON DELETE CASCADE,
            withdrawal_id INTEGER NOT NULL REFERENCES remittances(id),
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
            PRIMARY KEY(allocation_id,withdrawal_id)
        );
        CREATE TABLE IF NOT EXISTS cash_redeposits (
            id INTEGER PRIMARY KEY,
            reference TEXT NOT NULL UNIQUE,
            bank_account_id INTEGER NOT NULL REFERENCES bank_accounts(id),
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
            deposit_date TEXT NOT NULL,
            transaction_time TEXT NOT NULL,
            authorized_by_registry_id INTEGER REFERENCES head_registry(id),
            notes TEXT NOT NULL DEFAULT '', voided INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS cash_redeposit_sources (
            redeposit_id INTEGER NOT NULL REFERENCES cash_redeposits(id) ON DELETE CASCADE,
            allocation_id INTEGER NOT NULL REFERENCES cash_allocations(id),
            withdrawal_id INTEGER NOT NULL REFERENCES remittances(id),
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
            PRIMARY KEY(redeposit_id,allocation_id,withdrawal_id)
        );
        CREATE TABLE IF NOT EXISTS expense_batches (
            id INTEGER PRIMARY KEY,
            reference TEXT NOT NULL UNIQUE,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            committed_at TEXT NOT NULL,
            authorized_by_head_id INTEGER REFERENCES project_heads(id),
            notes TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS expense_verification_batches (
            id INTEGER PRIMARY KEY,
            reference TEXT NOT NULL UNIQUE,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            verification_date TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS expense_verification_items (
            batch_id INTEGER NOT NULL REFERENCES expense_verification_batches(id) ON DELETE CASCADE,
            expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
            PRIMARY KEY(batch_id, expense_id)
        );
        CREATE TABLE IF NOT EXISTS expense_verification_approvals (
            batch_id INTEGER NOT NULL REFERENCES expense_verification_batches(id) ON DELETE CASCADE,
            head_id INTEGER NOT NULL REFERENCES project_heads(id),
            approved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(batch_id, head_id)
        );
        CREATE TABLE IF NOT EXISTS cash_advance_batches (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            batch_ref TEXT NOT NULL UNIQUE,
            advance_date TEXT NOT NULL,
            funding_method TEXT NOT NULL,
            bank_account_id INTEGER REFERENCES bank_accounts(id),
            cash_allocation_id INTEGER REFERENCES cash_allocations(id),
            total_cents INTEGER NOT NULL CHECK(total_cents > 0),
            entry_count INTEGER NOT NULL DEFAULT 0,
            authorized_by_head_id INTEGER REFERENCES project_heads(id),
            recorded_at_local TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS cash_advances (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            expense_id INTEGER REFERENCES expenses(id) ON DELETE SET NULL,
            original_cents INTEGER NOT NULL CHECK(original_cents > 0),
            advance_date TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
            method TEXT NOT NULL DEFAULT 'Cash',
            bank_account_id INTEGER REFERENCES bank_accounts(id),
            authorized_by_head_id INTEGER REFERENCES project_heads(id),
            voided INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS cash_advance_transactions (
            id INTEGER PRIMARY KEY,
            advance_id INTEGER NOT NULL REFERENCES cash_advances(id) ON DELETE CASCADE,
            txn_type TEXT NOT NULL,
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
            txn_date TEXT NOT NULL, method TEXT NOT NULL DEFAULT '',
            bank_account_id INTEGER REFERENCES bank_accounts(id),
            payroll_batch_id INTEGER REFERENCES payroll_batches(id) ON DELETE SET NULL,
            reference TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            authorized_by_head_id INTEGER REFERENCES project_heads(id),
            posted INTEGER NOT NULL DEFAULT 1, voided INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS cash_repayment_surrenders (
            id INTEGER PRIMARY KEY,
            reference TEXT NOT NULL UNIQUE,
            advance_transaction_id INTEGER NOT NULL UNIQUE
                REFERENCES cash_advance_transactions(id) ON DELETE CASCADE,
            advance_id INTEGER NOT NULL REFERENCES cash_advances(id) ON DELETE CASCADE,
            cash_allocation_id INTEGER REFERENCES cash_allocations(id) ON DELETE SET NULL,
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
            surrender_date TEXT NOT NULL,
            transaction_time TEXT NOT NULL DEFAULT '',
            received_by_head_id INTEGER REFERENCES project_heads(id),
            status TEXT NOT NULL DEFAULT 'Awaiting Deposit',
            redeposit_id INTEGER REFERENCES cash_redeposits(id) ON DELETE SET NULL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS expense_categories (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            type TEXT NOT NULL, title TEXT NOT NULL, event_date TEXT NOT NULL,
            event_time TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            completed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS project_completion_snapshots (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            completion_reference TEXT NOT NULL UNIQUE,
            completion_date TEXT NOT NULL,
            completion_time TEXT NOT NULL DEFAULT '',
            completed_by_head_ids TEXT NOT NULL DEFAULT '',
            completed_by_names TEXT NOT NULL DEFAULT '',
            completion_notes TEXT NOT NULL DEFAULT '',
            contract_value_cents INTEGER NOT NULL DEFAULT 0,
            deposited_cents INTEGER NOT NULL DEFAULT 0,
            active_expense_cents INTEGER NOT NULL DEFAULT 0,
            paid_cents INTEGER NOT NULL DEFAULT 0,
            outstanding_cents INTEGER NOT NULL DEFAULT 0,
            budget_remaining_cents INTEGER NOT NULL DEFAULT 0,
            task_count INTEGER NOT NULL DEFAULT 0,
            completed_task_count INTEGER NOT NULL DEFAULT 0,
            progress_percent INTEGER NOT NULL DEFAULT 0,
            expense_count INTEGER NOT NULL DEFAULT 0,
            payroll_batch_count INTEGER NOT NULL DEFAULT 0,
            attendance_count INTEGER NOT NULL DEFAULT 0,
            reactivated_at TEXT NOT NULL DEFAULT '',
            reactivated_by_names TEXT NOT NULL DEFAULT '',
            reactivation_notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS inventory_items (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            item_code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            material_type TEXT NOT NULL CHECK(material_type IN ('Consumable','Non-Consumable')),
            category TEXT NOT NULL DEFAULT '',
            unit TEXT NOT NULL DEFAULT 'piece',
            registered_quantity_milli INTEGER NOT NULL DEFAULT 0,
            reorder_level_milli INTEGER NOT NULL DEFAULT 0,
            condition_status TEXT NOT NULL DEFAULT 'Good',
            notes TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            created_by_head_id INTEGER REFERENCES project_heads(id),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS inventory_transactions (
            id INTEGER PRIMARY KEY,
            reference TEXT NOT NULL UNIQUE,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            item_id INTEGER NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
            employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
            transaction_type TEXT NOT NULL,
            quantity_milli INTEGER NOT NULL CHECK(quantity_milli > 0),
            transaction_date TEXT NOT NULL,
            transaction_time TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            condition_note TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            linked_transaction_id INTEGER REFERENCES inventory_transactions(id) ON DELETE SET NULL,
            authorized_by_head_id INTEGER REFERENCES project_heads(id),
            voided INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY, project_id INTEGER, action TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_expenses_project ON expenses(project_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_phase ON tasks(phase_id);
        CREATE INDEX IF NOT EXISTS idx_events_project_date ON calendar_events(project_id, event_date);
        CREATE INDEX IF NOT EXISTS idx_attendance_employee ON attendance(employee_id, clock_in);
        CREATE INDEX IF NOT EXISTS idx_attendance_closure_project
            ON attendance_closure_batches(project_id,work_date);
        CREATE INDEX IF NOT EXISTS idx_cash_advance_employee ON cash_advances(employee_id, advance_date);
        CREATE INDEX IF NOT EXISTS idx_cash_advance_txn ON cash_advance_transactions(advance_id, txn_date);
        CREATE INDEX IF NOT EXISTS idx_cash_repayment_surrender_status
            ON cash_repayment_surrenders(status,surrender_date);
        CREATE INDEX IF NOT EXISTS idx_cash_alloc_withdrawal ON cash_allocations(withdrawal_id);
        CREATE INDEX IF NOT EXISTS idx_cash_alloc_project ON cash_allocations(project_id,status);
        CREATE INDEX IF NOT EXISTS idx_cash_alloc_txn ON cash_allocation_transactions(allocation_id,txn_date);
        CREATE INDEX IF NOT EXISTS idx_cash_alloc_source_withdrawal ON cash_allocation_sources(withdrawal_id);
        CREATE INDEX IF NOT EXISTS idx_cash_redeposit_bank ON cash_redeposits(bank_account_id,deposit_date);
        CREATE INDEX IF NOT EXISTS idx_cash_redeposit_source_withdrawal ON cash_redeposit_sources(withdrawal_id);
        CREATE INDEX IF NOT EXISTS idx_bank_transfer_source
            ON bank_account_transfers(from_bank_account_id,transfer_date);
        CREATE INDEX IF NOT EXISTS idx_bank_transfer_destination
            ON bank_account_transfers(to_bank_account_id,transfer_date);
        CREATE INDEX IF NOT EXISTS idx_expense_batch_project ON expense_batches(project_id,committed_at);
        CREATE INDEX IF NOT EXISTS idx_expense_verify_item ON expense_verification_items(expense_id);
        CREATE INDEX IF NOT EXISTS idx_project_completion_project
            ON project_completion_snapshots(project_id,completion_date);
        CREATE INDEX IF NOT EXISTS idx_inventory_item_project
            ON inventory_items(project_id,material_type,active);
        CREATE INDEX IF NOT EXISTS idx_inventory_transaction_item
            ON inventory_transactions(item_id,transaction_date,id);
        CREATE INDEX IF NOT EXISTS idx_inventory_transaction_employee
            ON inventory_transactions(employee_id,transaction_date,id);
        """)
        self._ensure_column("expenses", "authorized_by_head_id", "INTEGER")
        self._ensure_column("expenses", "status", "TEXT NOT NULL DEFAULT 'Unpaid'")
        self._ensure_column("projects", "address", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("projects", "status", "TEXT NOT NULL DEFAULT 'Active'")
        self._ensure_column("projects", "completed_at", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("projects", "completion_reference", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("projects", "completion_notes", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("projects", "completed_by_names", "TEXT NOT NULL DEFAULT ''")
        self.conn.execute("UPDATE projects SET status='Active' WHERE TRIM(COALESCE(status,''))='' ")
        self._ensure_column("payments", "bank_account_id", "INTEGER")
        self._ensure_column("payments", "authorized_by_head_id", "INTEGER")
        self._ensure_column("payments", "cash_allocation_id", "INTEGER")
        self._ensure_column("payments", "system_reference", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("payments", "transaction_time", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("payments", "created_at", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("payments", "accounting_excluded", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("expenses", "default_cash_allocation_id", "INTEGER")
        self._ensure_column("expenses", "expense_batch_id", "INTEGER")
        self._ensure_column("expenses", "created_at", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("expenses", "verification_status", "TEXT NOT NULL DEFAULT 'Unverified'")
        self._ensure_column("expenses", "verified_at", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("employees", "birthday", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("employees", "contact_number", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("employees", "daily_rate_cents", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("employees", "nbi_clearance", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("employees", "police_clearance", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("employees", "drug_test", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("employees", "biodata", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("employees", "photo_data", "BLOB")
        self._ensure_column("employees", "photo_filename", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("employees", "photo_mime", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("employees", "archived_at", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("employees", "archive_reason", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("attendance", "regular_hours", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("attendance", "lunch_hours", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("attendance", "overtime_hours", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("attendance", "regular_pay_cents", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("attendance", "overtime_pay_cents", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("attendance", "day_type", "TEXT NOT NULL DEFAULT 'Ordinary Day'")
        self._ensure_column("attendance", "source", "TEXT NOT NULL DEFAULT 'Kiosk'")
        self._ensure_column("attendance", "authorized_by_head_id", "INTEGER")
        self._ensure_column("attendance", "payroll_batch_id", "INTEGER")
        self._ensure_column("attendance", "closure_batch_id", "INTEGER")
        self._ensure_column("attendance", "project_id", "INTEGER")
        self._ensure_column("attendance", "revision_count", "INTEGER NOT NULL DEFAULT 0")
        self.conn.execute(
            """UPDATE attendance SET project_id=(SELECT project_id FROM employees e
               WHERE e.id=attendance.employee_id) WHERE project_id IS NULL"""
        )
        self.conn.execute(
            """INSERT INTO employee_project_assignments(
               employee_id,project_id,effective_from,position,daily_rate_cents,reason)
               SELECT e.id,e.project_id,COALESCE(NULLIF(MIN(SUBSTR(a.clock_in,1,10)),''),
                      SUBSTR(CURRENT_TIMESTAMP,1,10)),e.position,
                      CASE WHEN e.daily_rate_cents>0 THEN e.daily_rate_cents
                           WHEN LOWER(TRIM(e.pay_basis))='hourly' THEN e.rate_cents*8
                           ELSE e.rate_cents END,'Migrated current assignment'
               FROM employees e LEFT JOIN attendance a ON a.employee_id=e.id
               WHERE NOT EXISTS (SELECT 1 FROM employee_project_assignments x
                                 WHERE x.employee_id=e.id)
               GROUP BY e.id"""
        )
        self.conn.execute(
            """UPDATE employee_project_assignments SET effective_to=COALESCE(
                 NULLIF((SELECT archived_at FROM employees e
                         WHERE e.id=employee_project_assignments.employee_id),''),
                 SUBSTR(CURRENT_TIMESTAMP,1,10))
               WHERE effective_to='' AND EXISTS (SELECT 1 FROM employees e
                 WHERE e.id=employee_project_assignments.employee_id AND e.active=0)"""
        )
        self.conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_employee_current_assignment
               ON employee_project_assignments(employee_id) WHERE effective_to=''"""
        )
        self.conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_attendance_project_date
               ON attendance(project_id,clock_in)"""
        )
        self.conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_attendance_revision_record
               ON attendance_revisions(attendance_id,created_at)"""
        )
        self.conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_payroll_adjustment_pending
               ON payroll_adjustments(project_id,status,employee_id)"""
        )
        self._ensure_column("remittances", "authorized_by_head_id", "INTEGER")
        self._ensure_column("remittances", "authorized_by_registry_id", "INTEGER")
        self._ensure_column("remittances", "bank_account_id", "INTEGER")
        self._ensure_column("remittances", "shared_cash", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("remittances", "system_reference", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("remittances", "transaction_time", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("remittances", "created_at", "TEXT NOT NULL DEFAULT ''")
        self.conn.execute("UPDATE remittances SET shared_cash=1 WHERE type='Withdrawal'")
        self._ensure_column("cash_allocations", "shared_scope", "INTEGER NOT NULL DEFAULT 1")
        self._ensure_column("cash_allocations", "allocation_time", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("cash_allocations", "issuer_registry_id", "INTEGER")
        self._ensure_column("cash_allocations", "receiver_registry_id", "INTEGER")
        self._ensure_column("cash_allocations", "created_at", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("cash_allocation_transactions", "system_reference", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("cash_allocation_transactions", "transaction_time", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("cash_allocation_transactions", "created_at", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("expense_verification_batches", "verification_time", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("expense_verification_batches", "created_at", "TEXT NOT NULL DEFAULT ''")
        # Cash-advance funding and recovery preferences are additive migrations.
        # Existing advances remain valid and default to the legacy/manual workflow.
        self._ensure_column("cash_advances", "cash_allocation_id", "INTEGER")
        self._ensure_column("cash_advances", "repayment_plan", "TEXT NOT NULL DEFAULT 'Manual / Mixed'")
        self._ensure_column("cash_advances", "weekly_deduction_cap_cents", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("cash_advances", "batch_id", "INTEGER")
        self._ensure_column("cash_advances", "system_reference", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("cash_advances", "recorded_at_local", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("cash_advance_transactions", "recorded_at_local", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("payroll_batches", "week_schedule", "TEXT NOT NULL DEFAULT 'Legacy / Stored Period'")
        self._ensure_column("payroll_batches", "adjustment_cents", "INTEGER NOT NULL DEFAULT 0")
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cash_advance_batch ON cash_advances(batch_id)"
        )
        self.conn.execute(
            """UPDATE cash_advances SET system_reference=COALESCE((
                   SELECT reference FROM cash_advance_transactions t
                   WHERE t.advance_id=cash_advances.id AND t.txn_type='Advance'
                   ORDER BY t.id LIMIT 1),'') WHERE system_reference=''"""
        )
        self.conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_cash_advance_system_reference
               ON cash_advances(system_reference) WHERE system_reference<>''"""
        )
        # A salary deduction settles an employee receivable; it is not another
        # cash/bank payment against the net payroll expense.
        self.conn.execute(
            """UPDATE payments SET accounting_excluded=1
               WHERE LOWER(TRIM(method))='salary deduction'"""
        )
        self.conn.execute(
            """UPDATE expenses SET
                 total_cents=COALESCE((SELECT b.net_cents FROM payroll_batches b
                                      WHERE b.expense_id=expenses.id),total_cents),
                 unit_price_cents=COALESCE((SELECT b.net_cents FROM payroll_batches b
                                           WHERE b.expense_id=expenses.id),unit_price_cents)
               WHERE id IN (SELECT expense_id FROM payroll_batches WHERE expense_id IS NOT NULL)"""
        )
        self.conn.execute(
            """UPDATE expenses SET status=CASE
                 WHEN total_cents<=0 THEN 'Paid'
                 WHEN COALESCE((SELECT SUM(amount_cents) FROM payments
                                WHERE expense_id=expenses.id AND accounting_excluded=0),0)>=total_cents
                   THEN 'Paid'
                 WHEN COALESCE((SELECT SUM(amount_cents) FROM payments
                                WHERE expense_id=expenses.id AND accounting_excluded=0),0)>0
                   THEN 'Partially Paid'
                 ELSE 'Unpaid' END
               WHERE id IN (SELECT expense_id FROM payroll_batches WHERE expense_id IS NOT NULL)"""
        )
        self._ensure_column("project_heads", "registry_head_id", "INTEGER")
        self.conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_head_registry_identity
               ON head_registry(LOWER(TRIM(name)), LOWER(TRIM(position)))"""
        )
        self._migrate_project_head_registry()
        self.conn.execute(
            """UPDATE cash_allocations SET issuer_registry_id=(
                   SELECT registry_head_id FROM project_heads WHERE id=cash_allocations.issuer_head_id)
               WHERE issuer_registry_id IS NULL"""
        )
        self.conn.execute(
            """UPDATE cash_allocations SET receiver_registry_id=(
                   SELECT registry_head_id FROM project_heads WHERE id=cash_allocations.receiver_head_id)
               WHERE receiver_registry_id IS NULL"""
        )
        # Some prototype builds created a smaller bank_accounts table. CREATE TABLE
        # IF NOT EXISTS does not expand an existing table, so add every v1 field
        # individually. Constant defaults keep these ALTER TABLE statements valid
        # on older SQLite versions and preserve all enrolled accounts.
        self._ensure_column("bank_accounts", "bank_name", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("bank_accounts", "account_name", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("bank_accounts", "account_number", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("bank_accounts", "notes", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("bank_accounts", "active", "INTEGER NOT NULL DEFAULT 1")
        self._ensure_column("bank_accounts", "created_at", "TEXT NOT NULL DEFAULT ''")
        active_banks = self.conn.execute(
            "SELECT id FROM bank_accounts WHERE active=1 ORDER BY id"
        ).fetchall()
        if len(active_banks) == 1:
            # Older versions recorded the method but not the source account.
            # With one enrolled bank the intended account is unambiguous.
            self.conn.execute(
                """UPDATE payments SET bank_account_id=?
                   WHERE bank_account_id IS NULL AND LOWER(method) LIKE '%bank%'""",
                (active_banks[0]["id"],),
            )
        self.conn.executemany(
            "INSERT OR IGNORE INTO expense_categories(name) VALUES(?)",
            [(name,) for name in DEFAULT_EXPENSE_CATEGORIES],
        )
        # Preserve old employee rates while normalizing new payroll calculations to
        # a daily rate divided by eight. Hourly legacy rows are converted only into
        # the additive daily-rate field; their original fields remain untouched.
        self.conn.execute(
            """UPDATE employees SET daily_rate_cents=CASE
                 WHEN LOWER(TRIM(pay_basis))='hourly' THEN rate_cents*8
                 ELSE rate_cents END
               WHERE daily_rate_cents=0 AND rate_cents>0"""
        )
        self.conn.execute(
            """UPDATE expenses SET status=CASE
                 WHEN voided=1 THEN status
                 WHEN total_cents<=0 THEN 'Paid'
                 WHEN COALESCE((SELECT SUM(amount_cents) FROM payments
                                WHERE expense_id=expenses.id AND accounting_excluded=0),0)
                      >= total_cents THEN 'Paid'
                 WHEN COALESCE((SELECT SUM(amount_cents) FROM payments
                                WHERE expense_id=expenses.id AND accounting_excluded=0),0)>0
                      THEN 'Partially Paid'
                 ELSE 'Unpaid' END"""
        )
        self._backfill_shared_cash_references()
        self._migrate_cash_repayment_surrenders()
        self._migrate_v120_payroll_deductions()
        self.conn.execute(
            """INSERT INTO app_metadata(key,value,updated_at) VALUES('schema_version','1.2.0',?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""",
            (local_timestamp(),),
        )
        self.conn.commit()

    def _backfill_shared_cash_references(self):
        """Add stable audit references without changing any financial amounts."""
        for row in self.conn.execute(
            "SELECT id,type,txn_date,created_at FROM remittances ORDER BY id"
        ).fetchall():
            stamp = (row["txn_date"] or "0000-00-00").replace("-", "")
            prefix = "WD" if row["type"] == "Withdrawal" else "BD"
            self.conn.execute(
                """UPDATE remittances SET system_reference=CASE WHEN system_reference=''
                       THEN ? ELSE system_reference END,
                       transaction_time=CASE WHEN transaction_time='' THEN COALESCE(NULLIF(created_at,''),?)
                       ELSE transaction_time END WHERE id=?""",
                (f"{prefix}-{stamp}-{row['id']:06d}", local_timestamp(), row["id"]),
            )
        for row in self.conn.execute(
            "SELECT id,payment_date,method,created_at FROM payments ORDER BY id"
        ).fetchall():
            stamp = (row["payment_date"] or "0000-00-00").replace("-", "")
            reference = f"BT-{stamp}-{row['id']:06d}" if "bank" in (row["method"] or "").lower() else ""
            self.conn.execute(
                """UPDATE payments SET system_reference=CASE WHEN system_reference='' THEN ? ELSE system_reference END,
                       transaction_time=CASE WHEN transaction_time='' THEN COALESCE(NULLIF(created_at,''),?)
                       ELSE transaction_time END WHERE id=?""",
                (reference, local_timestamp(), row["id"]),
            )
        self.conn.execute(
            """UPDATE cash_allocations SET allocation_time=COALESCE(NULLIF(allocation_time,''),
                   NULLIF(created_at,''),allocation_date || ' 00:00:00'),shared_scope=1"""
        )
        self.conn.execute(
            """UPDATE cash_allocation_transactions SET transaction_time=COALESCE(
                   NULLIF(transaction_time,''),NULLIF(created_at,''),txn_date || ' 00:00:00')"""
        )
        self.conn.execute(
            """UPDATE expense_verification_batches SET verification_time=COALESCE(
                   NULLIF(verification_time,''),NULLIF(created_at,''),verification_date || ' 00:00:00')"""
        )
        self.conn.execute(
            """INSERT OR IGNORE INTO cash_allocation_sources(allocation_id,withdrawal_id,amount_cents)
               SELECT id,withdrawal_id,amount_cents FROM cash_allocations"""
        )
        legacy = self.conn.execute(
            "SELECT id,project_id,created_at,notes FROM expenses WHERE expense_batch_id IS NULL ORDER BY id"
        ).fetchall()
        for row in legacy:
            reference = f"EB-LEGACY-{row['id']:06d}"
            batch_id = self.conn.execute(
                """INSERT INTO expense_batches(reference,project_id,committed_at,notes)
                   VALUES(?,?,?,?)""",
                (reference, row["project_id"], row["created_at"] or local_timestamp(), "Backfilled existing expense"),
            ).lastrowid
            self.conn.execute("UPDATE expenses SET expense_batch_id=? WHERE id=?", (batch_id, row["id"]))

    def _migrate_cash_repayment_surrenders(self):
        """Place every historical physical cash repayment in surrendered custody.

        The repayment remains linked to the employee advance, while the surrender
        record prevents that cash from silently becoming spendable unallocated cash.
        INSERT OR IGNORE makes this safe to run every time the application starts.
        """
        rows = self.conn.execute(
            """SELECT t.id transaction_id,t.advance_id,t.amount_cents,t.txn_date,
                      t.created_at,t.authorized_by_head_id,t.notes,
                      a.cash_allocation_id,e.name employee
               FROM cash_advance_transactions t
               JOIN cash_advances a ON a.id=t.advance_id
               JOIN employees e ON e.id=a.employee_id
               LEFT JOIN cash_repayment_surrenders s
                      ON s.advance_transaction_id=t.id
               WHERE t.posted=1 AND t.voided=0 AND a.voided=0
                 AND t.txn_type IN ('Cash Repayment','Repayment')
                 AND LOWER(TRIM(t.method)) NOT LIKE '%bank%'
                 AND s.id IS NULL
               ORDER BY t.txn_date,t.id"""
        ).fetchall()
        for row in rows:
            reference = self._next_system_reference(
                "SR", "cash_repayment_surrenders", "reference", row["txn_date"]
            )
            stamp = row["created_at"] or local_timestamp()
            self.conn.execute(
                """INSERT OR IGNORE INTO cash_repayment_surrenders(
                   reference,advance_transaction_id,advance_id,cash_allocation_id,
                   amount_cents,surrender_date,transaction_time,received_by_head_id,
                   status,notes) VALUES(?,?,?,?,?,?,?,?, 'Awaiting Deposit',?)""",
                (reference, row["transaction_id"], row["advance_id"],
                 row["cash_allocation_id"], row["amount_cents"], row["txn_date"],
                 stamp, row["authorized_by_head_id"],
                 f"Cash repayment from {row['employee']}; migrated to surrendered custody. "
                  f"{row['notes'] or ''}".strip()),
            )

    def _migrate_v120_payroll_deductions(self):
        """Repair salary deductions posted into a payroll ending before the advance.

        v1.1 selected every unposted salary-deduction schedule for an employee,
        regardless of the advance's effective date.  When an older payroll was
        committed late, newer advances could therefore be consumed by that older
        payroll.  This migration returns only those invalid postings to pending,
        reapplies them FIFO to the earliest eligible existing payroll, and then
        reconciles the affected payroll expenses.  All other history is untouched.
        """
        already = self.conn.execute(
            "SELECT value FROM app_metadata WHERE key='payroll_date_repair_v120'"
        ).fetchone()
        if already:
            return
        invalid = self.conn.execute(
            """SELECT t.*,ca.employee_id,ca.project_id,ca.advance_date,
                      ca.weekly_deduction_cap_cents,pb.period_end invalid_period_end
               FROM cash_advance_transactions t
               JOIN cash_advances ca ON ca.id=t.advance_id
               JOIN payroll_batches pb ON pb.id=t.payroll_batch_id
               WHERE t.txn_type='Salary Deduction' AND t.posted=1
                 AND t.voided=0 AND ca.voided=0
                 AND ca.advance_date>pb.period_end
               ORDER BY ca.advance_date,ca.id,t.id"""
        ).fetchall()
        if not invalid:
            self.conn.execute(
                "INSERT INTO app_metadata(key,value,updated_at) VALUES('payroll_date_repair_v120','0',?)",
                (local_timestamp(),),
            )
            return

        affected_batches = {row["payroll_batch_id"] for row in invalid}
        employee_ids = sorted({row["employee_id"] for row in invalid})
        repaired_amount = sum(row["amount_cents"] for row in invalid)
        stamp = local_timestamp()

        for row in invalid:
            note = (row["notes"] or "").strip()
            note = (note + "; " if note else "") + (
                f"v1.2 repair: removed from payroll ending {row['invalid_period_end']} "
                f"because advance date is {row['advance_date']}"
            )
            self.conn.execute(
                """UPDATE cash_advance_transactions
                   SET posted=0,payroll_batch_id=NULL,txn_date=?,notes=?,recorded_at_local=?
                   WHERE id=?""",
                (row["advance_date"], note, stamp, row["id"]),
            )

        for employee_id in employee_ids:
            pending_ids = [
                row["id"] for row in invalid if row["employee_id"] == employee_id
            ]
            for transaction_id in pending_ids:
                while True:
                    pending = self.conn.execute(
                        """SELECT t.*,ca.advance_date,ca.weekly_deduction_cap_cents
                           FROM cash_advance_transactions t
                           JOIN cash_advances ca ON ca.id=t.advance_id
                           WHERE t.id=? AND t.posted=0 AND t.voided=0""",
                        (transaction_id,),
                    ).fetchone()
                    if not pending:
                        break
                    candidates = self.conn.execute(
                        """SELECT pb.*,
                                  COALESCE((SELECT SUM(a.gross_cents) FROM attendance a
                                    WHERE a.payroll_batch_id=pb.id AND a.employee_id=?),0) employee_gross
                           FROM payroll_batches pb
                           WHERE pb.project_id=(SELECT project_id FROM employees WHERE id=?)
                             AND pb.period_end>=?
                           ORDER BY pb.period_end,pb.id""",
                        (employee_id, employee_id, pending["advance_date"]),
                    ).fetchall()
                    applied_any = False
                    for batch in candidates:
                        posted_for_employee = self.conn.execute(
                            """SELECT COALESCE(SUM(t.amount_cents),0) total
                               FROM cash_advance_transactions t
                               JOIN cash_advances ca ON ca.id=t.advance_id
                               WHERE t.payroll_batch_id=? AND ca.employee_id=?
                                 AND t.txn_type='Salary Deduction' AND t.posted=1
                                 AND t.voided=0 AND ca.voided=0""",
                            (batch["id"], employee_id),
                        ).fetchone()["total"]
                        capacity = max(0, batch["employee_gross"] - posted_for_employee)
                        if capacity <= 0:
                            continue
                        cap = max(0, pending["weekly_deduction_cap_cents"] or 0)
                        posted_for_advance = self.conn.execute(
                            """SELECT COALESCE(SUM(amount_cents),0) total
                               FROM cash_advance_transactions
                               WHERE payroll_batch_id=? AND advance_id=?
                                 AND txn_type='Salary Deduction' AND posted=1 AND voided=0""",
                            (batch["id"], pending["advance_id"]),
                        ).fetchone()["total"]
                        cap_left = max(0, cap - posted_for_advance) if cap else capacity
                        applied = min(pending["amount_cents"], capacity, cap_left)
                        if applied <= 0:
                            continue
                        post_date = (batch["created_at"] or batch["period_end"])[:10]
                        affected_batches.add(batch["id"])
                        if applied == pending["amount_cents"]:
                            self.conn.execute(
                                """UPDATE cash_advance_transactions
                                   SET posted=1,payroll_batch_id=?,txn_date=?,recorded_at_local=?
                                   WHERE id=?""",
                                (batch["id"], post_date, stamp, pending["id"]),
                            )
                        else:
                            self.conn.execute(
                                "UPDATE cash_advance_transactions SET amount_cents=? WHERE id=?",
                                (pending["amount_cents"] - applied, pending["id"]),
                            )
                            self.conn.execute(
                                """INSERT INTO cash_advance_transactions(
                                   advance_id,txn_type,amount_cents,txn_date,method,
                                   payroll_batch_id,reference,notes,authorized_by_head_id,
                                   posted,recorded_at_local)
                                   VALUES(?,'Salary Deduction',?,?,'Salary Deduction',?,?,?,?,1,?)""",
                                (pending["advance_id"], applied, post_date, batch["id"],
                                 pending["reference"], pending["notes"],
                                 pending["authorized_by_head_id"], stamp),
                            )
                        applied_any = True
                        break
                    if not applied_any:
                        break

        for batch_id in sorted(affected_batches):
            batch = self.conn.execute(
                "SELECT * FROM payroll_batches WHERE id=?", (batch_id,)
            ).fetchone()
            if not batch:
                continue
            deductions = self.conn.execute(
                """SELECT COALESCE(SUM(amount_cents),0) total
                   FROM cash_advance_transactions
                   WHERE payroll_batch_id=? AND txn_type='Salary Deduction'
                     AND posted=1 AND voided=0""",
                (batch_id,),
            ).fetchone()["total"]
            net = max(0, batch["gross_cents"] - deductions)
            self.conn.execute(
                "UPDATE payroll_batches SET deduction_cents=?,net_cents=? WHERE id=?",
                (deductions, net, batch_id),
            )
            if batch["expense_id"]:
                paid = self.conn.execute(
                    """SELECT COALESCE(SUM(amount_cents),0) total FROM payments
                       WHERE expense_id=? AND accounting_excluded=0""",
                    (batch["expense_id"],),
                ).fetchone()["total"]
                status = "Paid" if net <= 0 or paid >= net else "Partially Paid" if paid else "Unpaid"
                self.conn.execute(
                    """UPDATE expenses SET total_cents=?,unit_price_cents=?,status=?
                       WHERE id=?""",
                    (net, net, status, batch["expense_id"]),
                )
            self.conn.execute(
                """INSERT INTO audit_log(project_id,action,details,created_at)
                   VALUES(?,'PAYROLL_DEDUCTION_DATE_REPAIRED',?,?)""",
                (batch["project_id"],
                 f"{batch['batch_ref']} reconciled to {money(deductions)} deductions and {money(net)} net pay",
                 stamp),
            )
        self.conn.execute(
            "INSERT INTO app_metadata(key,value,updated_at) VALUES('payroll_date_repair_v120',?,?)",
            (f"{len(invalid)} postings / {repaired_amount} cents", stamp),
        )

    def _migrate_project_head_registry(self):
        """Import legacy project-bound heads once and set their requested default PIN."""
        legacy_heads = self.conn.execute(
            """SELECT * FROM project_heads
               WHERE registry_head_id IS NULL ORDER BY id"""
        ).fetchall()
        for head in legacy_heads:
            registered = self.conn.execute(
                """SELECT * FROM head_registry
                   WHERE LOWER(TRIM(name))=LOWER(TRIM(?))
                     AND LOWER(TRIM(position))=LOWER(TRIM(?))""",
                (head["name"], head["position"]),
            ).fetchone()
            if registered:
                registry_id = registered["id"]
                salt, digest = registered["pin_salt"], registered["pin_hash"]
            else:
                salt, digest = hash_pin("0000")
                registry_id = self.conn.execute(
                    """INSERT INTO head_registry(name,position,pin_salt,pin_hash)
                       VALUES(?,?,?,?)""",
                    (head["name"].strip(), head["position"].strip(), salt, digest),
                ).lastrowid
            self.conn.execute(
                """UPDATE project_heads
                   SET registry_head_id=?,pin_salt=?,pin_hash=? WHERE id=?""",
                (registry_id, salt, digest, head["id"]),
            )

    def registered_heads(self):
        return self.all(
            "SELECT * FROM head_registry WHERE active=1 ORDER BY name COLLATE NOCASE,position COLLATE NOCASE"
        )

    def project_head_for_registry(self, registry_id: int, preferred_project_id: int | None = None):
        """Return an active project-head row used by legacy foreign-key columns.

        Shared-cash ownership is registry based.  The project-head row returned here
        is only a compatibility identity for older tables, not an accounting scope.
        """
        return self.one(
            """SELECT h.* FROM project_heads h
               WHERE h.registry_head_id=? AND h.active=1
               ORDER BY CASE WHEN h.project_id=? THEN 0 ELSE 1 END,h.id LIMIT 1""",
            (registry_id, preferred_project_id),
        )

    def add_registered_head(self, name: str, position: str) -> int:
        name, position = name.strip(), position.strip()
        if not name or not position:
            raise ValueError("Name and position are required.")
        existing = self.one(
            """SELECT * FROM head_registry
               WHERE LOWER(TRIM(name))=LOWER(TRIM(?))
                 AND LOWER(TRIM(position))=LOWER(TRIM(?))""",
            (name, position),
        )
        if existing:
            if existing["active"]:
                raise ValueError("That project head is already registered.")
            salt, digest = hash_pin("0000")
            self.execute(
                """UPDATE head_registry SET active=1,pin_salt=?,pin_hash=? WHERE id=?""",
                (salt, digest, existing["id"]),
            )
            return existing["id"]
        salt, digest = hash_pin("0000")
        return self.execute(
            """INSERT INTO head_registry(name,position,pin_salt,pin_hash)
               VALUES(?,?,?,?)""", (name, position, salt, digest)
        ).lastrowid

    def update_registered_head(self, registry_id: int, name: str, position: str,
                               current_pin: str, new_pin: str = ""):
        """Edit a registry identity and propagate it to every linked project."""
        head = self.one("SELECT * FROM head_registry WHERE id=? AND active=1", (registry_id,))
        if not head:
            raise ValueError("The selected project head is no longer active.")
        if not verify_pin(current_pin, head["pin_salt"], head["pin_hash"]):
            raise ValueError("The current project-head PIN is incorrect.")
        name, position = name.strip(), position.strip()
        if not name or not position:
            raise ValueError("Name and position are required.")
        salt, digest = head["pin_salt"], head["pin_hash"]
        if new_pin:
            salt, digest = hash_pin(new_pin)
        assigned_projects = self.all(
            "SELECT DISTINCT project_id FROM project_heads WHERE registry_head_id=?",
            (registry_id,),
        )
        with self.conn:
            self.conn.execute(
                """UPDATE head_registry SET name=?,position=?,pin_salt=?,pin_hash=?
                   WHERE id=?""",
                (name, position, salt, digest, registry_id),
            )
            self.conn.execute(
                """UPDATE project_heads SET name=?,position=?,pin_salt=?,pin_hash=?
                   WHERE registry_head_id=?""",
                (name, position, salt, digest, registry_id),
            )
            for project in assigned_projects:
                self.conn.execute(
                    """INSERT INTO audit_log(project_id,action,details,created_at)
                       VALUES(?,'PROJECT_HEAD_UPDATED',?,?)""",
                    (project["project_id"],
                     f"Registry head #{registry_id} updated to {name} / {position}; "
                     f"PIN {'changed' if new_pin else 'retained'}",
                     local_timestamp()),
                )

    def _assign_registered_heads(self, project_id: int, registry_ids):
        for registry_id in dict.fromkeys(int(value) for value in registry_ids):
            head = self.conn.execute(
                "SELECT * FROM head_registry WHERE id=? AND active=1", (registry_id,)
            ).fetchone()
            if not head:
                raise ValueError("One of the selected project heads is no longer registered.")
            linked = self.conn.execute(
                """SELECT id FROM project_heads
                   WHERE project_id=? AND registry_head_id=?""", (project_id, registry_id)
            ).fetchone()
            if linked:
                self.conn.execute(
                    """UPDATE project_heads SET name=?,position=?,pin_salt=?,pin_hash=?,active=1
                       WHERE id=?""",
                    (head["name"], head["position"], head["pin_salt"], head["pin_hash"], linked["id"]),
                )
            else:
                self.conn.execute(
                    """INSERT INTO project_heads(
                       project_id,name,position,pin_salt,pin_hash,registry_head_id)
                       VALUES(?,?,?,?,?,?)""",
                    (project_id, head["name"], head["position"], head["pin_salt"],
                     head["pin_hash"], registry_id),
                )

    def assign_registered_heads(self, project_id: int, registry_ids):
        with self.conn:
            self._assign_registered_heads(project_id, registry_ids)

    def _ensure_column(self, table: str, column: str, definition: str):
        columns = {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def one(self, sql, params=()):
        return self.conn.execute(sql, params).fetchone()

    def all(self, sql, params=()):
        return self.conn.execute(sql, params).fetchall()

    def execute(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur

    def enroll_bank_account(self, values: dict) -> int:
        """Enroll an account across both current and legacy bank table layouts."""
        duplicate = self.one(
            """SELECT id FROM bank_accounts
               WHERE LOWER(TRIM(bank_name))=LOWER(TRIM(?))
                 AND TRIM(account_number)=TRIM(?) LIMIT 1""",
            (values["bank_name"], values["account_number"]),
        )
        if duplicate:
            raise ValueError("That bank and account number are already enrolled.")

        columns = {row["name"] for row in self.all("PRAGMA table_info(bank_accounts)")}
        payload = {
            "bank_name": values["bank_name"],
            "account_name": values.get("account_name", ""),
            "account_number": values["account_number"],
            "notes": values.get("notes", ""),
        }
        # Early prototype databases used `name` as a required display label.
        # Populate it when present instead of rebuilding or replacing the table.
        if "name" in columns:
            payload["name"] = values.get("account_name") or values["bank_name"]
        payload = {key: value for key, value in payload.items() if key in columns}
        fields = ",".join(payload)
        placeholders = ",".join("?" for _ in payload)
        return self.execute(
            f"INSERT INTO bank_accounts({fields}) VALUES({placeholders})",
            tuple(payload.values()),
        ).lastrowid

    def audit(self, project_id: int | None, action: str, details: str = ""):
        self.execute(
            "INSERT INTO audit_log(project_id, action, details) VALUES(?,?,?)",
            (project_id, action, details),
        )

    def bank_balance(self, bank_account_id: int) -> int:
        remitted = self.one(
            """SELECT COALESCE(SUM(CASE WHEN type='Deposit' THEN amount_cents ELSE -amount_cents END),0) balance
               FROM remittances WHERE bank_account_id=? AND voided=0""", (bank_account_id,)
        )["balance"]
        redeposited = self.one(
            """SELECT COALESCE(SUM(amount_cents),0) total FROM cash_redeposits
               WHERE bank_account_id=? AND voided=0""", (bank_account_id,)
        )["total"]
        direct_payments = self.one(
            """SELECT COALESCE(SUM(pay.amount_cents),0) total
               FROM payments pay JOIN expenses e ON e.id=pay.expense_id
               WHERE pay.bank_account_id=? AND e.voided=0
                 AND pay.accounting_excluded=0""", (bank_account_id,)
        )["total"]
        recoveries = self.one(
            """SELECT COALESCE(SUM(t.amount_cents),0) total
               FROM cash_advance_transactions t
               JOIN cash_advances a ON a.id=t.advance_id
               WHERE t.bank_account_id=? AND t.posted=1 AND t.voided=0 AND a.voided=0
                 AND t.txn_type IN ('Bank Repayment','Repayment')
                 AND LOWER(t.method) LIKE '%bank%'""", (bank_account_id,)
        )["total"]
        inbound = self.one(
            """SELECT COALESCE(SUM(amount_cents),0) total FROM bank_account_transfers
               WHERE to_bank_account_id=? AND voided=0""", (bank_account_id,)
        )["total"]
        outbound = self.one(
            """SELECT COALESCE(SUM(amount_cents),0) total FROM bank_account_transfers
               WHERE from_bank_account_id=? AND voided=0""", (bank_account_id,)
        )["total"]
        return remitted + redeposited - direct_payments + recoveries + inbound - outbound

    def create_bank_account_transfer(self, *, from_bank_account_id: int,
                                     to_bank_account_id: int, amount_cents: int,
                                     transfer_date: str, purpose: str,
                                     notes: str, authorized_by_registry_id: int) -> dict:
        """Move money between enrolled banks without changing project funding totals."""
        transfer_date = valid_date(transfer_date, True)
        if from_bank_account_id == to_bank_account_id:
            raise ValueError("Source and destination bank accounts must be different.")
        if amount_cents <= 0:
            raise ValueError("Transfer amount must be greater than zero.")
        accounts = self.all(
            "SELECT id FROM bank_accounts WHERE active=1 AND id IN (?,?)",
            (from_bank_account_id, to_bank_account_id),
        )
        if {row["id"] for row in accounts} != {from_bank_account_id, to_bank_account_id}:
            raise ValueError("Both bank accounts must still be actively enrolled.")
        if not self.one(
            "SELECT id FROM head_registry WHERE id=? AND active=1",
            (authorized_by_registry_id,),
        ):
            raise ValueError("The authorizing project head is no longer active.")
        available = self.bank_balance(from_bank_account_id)
        if amount_cents > available:
            raise ValueError(
                f"The source account only has {money(available)} available."
            )
        reference = self._next_system_reference(
            "IBT", "bank_account_transfers", "reference", transfer_date
        )
        transaction_time = local_timestamp()
        with self.conn:
            cursor = self.conn.execute(
                """INSERT INTO bank_account_transfers(
                       reference,from_bank_account_id,to_bank_account_id,amount_cents,
                       transfer_date,transaction_time,purpose,notes,authorized_by_registry_id)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (reference, from_bank_account_id, to_bank_account_id, amount_cents,
                 transfer_date, transaction_time, purpose.strip(), notes.strip(),
                 authorized_by_registry_id),
            )
            self.conn.execute(
                "INSERT INTO audit_log(project_id,action,details) VALUES(NULL,?,?)",
                ("BANK_ACCOUNT_TRANSFER_ADDED",
                 f"{reference} {money(amount_cents)} bank {from_bank_account_id} to {to_bank_account_id}"),
            )
        return {"id": cursor.lastrowid, "reference": reference,
                "transaction_time": transaction_time}

    def project_employee_code(self, project_id: int) -> str:
        row = self.one("SELECT name FROM projects WHERE id=?", (project_id,))
        if not row:
            raise ValueError("Select a valid project before adding an employee.")
        words = ["".join(ch for ch in word.upper() if ch.isalnum())
                 for word in row["name"].replace("-", " ").split()]
        words = [word for word in words if word and word not in {"PROJECT", "THE"}]
        if not words:
            words = ["PRJ"]
        return "-".join(words)[:20].rstrip("-") or "PRJ"

    def next_employee_number(self, project_id: int) -> str:
        """Return PROJECT-NNN, continuing after the current project roster size."""
        prefix = self.project_employee_code(project_id)
        rows = self.all(
            "SELECT employee_no FROM employees WHERE project_id=? ORDER BY id",
            (project_id,),
        )
        suffixes = []
        for row in rows:
            value = (row["employee_no"] or "").upper()
            if value.startswith(prefix + "-") and value.rsplit("-", 1)[-1].isdigit():
                suffixes.append(int(value.rsplit("-", 1)[-1]))
        sequence = max([len(rows), *suffixes], default=0) + 1
        candidate = f"{prefix}-{sequence:03d}"
        while self.one(
            "SELECT 1 FROM employees WHERE project_id=? AND employee_no=?",
            (project_id, candidate),
        ):
            sequence += 1
            candidate = f"{prefix}-{sequence:03d}"
        return candidate

    def expense_recoveries(self, expense_id: int) -> int:
        row = self.one(
            """SELECT COALESCE(SUM(t.amount_cents),0) total
               FROM cash_advances a JOIN cash_advance_transactions t ON t.advance_id=a.id
               WHERE a.expense_id=? AND a.voided=0 AND t.voided=0 AND t.posted=1
                 AND t.txn_type IN ('Cash Repayment','Bank Repayment','Repayment')""", (expense_id,)
        )
        return row["total"] if row else 0

    def project_recoveries(self, project_id: int) -> int:
        return self.one(
            """SELECT COALESCE(SUM(t.amount_cents),0) total
               FROM cash_advances a JOIN cash_advance_transactions t ON t.advance_id=a.id
               WHERE a.project_id=? AND a.voided=0 AND t.voided=0 AND t.posted=1
                 AND t.txn_type IN ('Cash Repayment','Bank Repayment','Repayment')""", (project_id,)
        )["total"]

    def project_budget(self, project_id: int) -> tuple[int, int, int]:
        """Return deposited, payments recorded, and payment-basis balance."""
        deposited = self.one(
            """SELECT COALESCE(SUM(amount_cents),0) total FROM remittances
               WHERE project_id=? AND type='Deposit' AND voided=0""", (project_id,)
        )["total"]
        paid = self.one(
            """SELECT COALESCE(SUM(pay.amount_cents),0) total
               FROM payments pay JOIN expenses e ON e.id=pay.expense_id
               WHERE e.project_id=? AND e.voided=0 AND pay.accounting_excluded=0""", (project_id,)
        )["total"]
        paid = max(0, paid - self.project_recoveries(project_id))
        return deposited, paid, deposited - paid

    def project_commitment_budget(self, project_id: int) -> tuple[int, int, int]:
        """Return deposited, all active expense commitments, and committed balance."""
        deposited = self.one(
            """SELECT COALESCE(SUM(amount_cents),0) total FROM remittances
               WHERE project_id=? AND type='Deposit' AND voided=0""", (project_id,)
        )["total"]
        committed = self.one(
            """SELECT COALESCE(SUM(total_cents),0) total FROM expenses
               WHERE project_id=? AND voided=0""", (project_id,)
        )["total"]
        committed = max(0, committed - self.project_recoveries(project_id))
        return deposited, committed, deposited - committed

    def cash_summary(self, project_id: int | None = None) -> tuple[int, int, int]:
        clause = " AND project_id=?" if project_id else ""
        params = (project_id,) if project_id else ()
        withdrawn = self.one(
            f"""SELECT COALESCE(SUM(amount_cents),0) total FROM remittances
                 WHERE type='Withdrawal' AND voided=0{clause}""", params
        )["total"]
        paid = self.one(
            f"""SELECT COALESCE(SUM(pay.amount_cents),0) total
                 FROM payments pay JOIN expenses e ON e.id=pay.expense_id
                 WHERE e.voided=0 AND pay.accounting_excluded=0
                   AND LOWER(TRIM(pay.method)) NOT LIKE '%bank%'
                   AND LOWER(TRIM(pay.method)) NOT LIKE '%salary deduction%'{clause}""", params
        )["total"]
        recovery_clause = " AND a.project_id=?" if project_id else ""
        cash_recovered = self.one(
            f"""SELECT COALESCE(SUM(t.amount_cents),0) total
                 FROM cash_advance_transactions t JOIN cash_advances a ON a.id=t.advance_id
                 WHERE t.posted=1 AND t.voided=0 AND a.voided=0
                   AND t.txn_type IN ('Cash Repayment','Repayment')
                   AND LOWER(TRIM(t.method)) NOT LIKE '%bank%'{recovery_clause}""", params
        )["total"]
        redeposited = self.one(
            "SELECT COALESCE(SUM(amount_cents),0) total FROM cash_redeposits WHERE voided=0"
        )["total"]
        net_withdrawn = withdrawn - redeposited
        return net_withdrawn, paid - cash_recovered, net_withdrawn - paid + cash_recovered

    def allocation_returned(self, allocation_id: int) -> int:
        row = self.one(
            """SELECT COALESCE(SUM(amount_cents),0) total
               FROM cash_allocation_transactions
               WHERE allocation_id=? AND txn_type IN ('Surrendered','Returned')""",
            (allocation_id,),
        )
        return row["total"] if row else 0

    def allocation_spent(self, allocation_id: int) -> int:
        row = self.one(
            """SELECT COALESCE(SUM(p.amount_cents),0) total
               FROM payments p JOIN expenses e ON e.id=p.expense_id
               WHERE p.cash_allocation_id=? AND e.voided=0
                 AND p.accounting_excluded=0""", (allocation_id,)
        )
        return row["total"] if row else 0

    def allocation_balance(self, allocation_id: int) -> int:
        row = self.one(
            "SELECT amount_cents,voided FROM cash_allocations WHERE id=?", (allocation_id,)
        )
        if not row or row["voided"]:
            return 0
        return max(0, row["amount_cents"] - self.allocation_spent(allocation_id)
                   - self.allocation_returned(allocation_id))

    def withdrawal_available(self, withdrawal_id: int) -> int:
        withdrawal = self.one(
            """SELECT amount_cents FROM remittances
               WHERE id=? AND type='Withdrawal' AND voided=0""", (withdrawal_id,)
        )
        if not withdrawal:
            return 0
        allocated = self.one(
            """SELECT COALESCE(SUM(s.amount_cents),0) total
               FROM cash_allocation_sources s JOIN cash_allocations a ON a.id=s.allocation_id
               WHERE s.withdrawal_id=? AND a.voided=0""", (withdrawal_id,)
        )["total"]
        return max(0, withdrawal["amount_cents"] - allocated)

    def fifo_withdrawal_sources(self, amount_cents: int):
        """Reserve an amount across the oldest withdrawals with remaining capacity."""
        if amount_cents <= 0:
            raise ValueError("Allocation amount must be positive.")
        remaining, sources = amount_cents, []
        rows = self.all(
            """SELECT id,system_reference,txn_date FROM remittances
               WHERE type='Withdrawal' AND voided=0 ORDER BY txn_date,id"""
        )
        for row in rows:
            available = self.withdrawal_available(row["id"])
            if available <= 0:
                continue
            take = min(remaining, available)
            sources.append((row["id"], take, row["system_reference"] or f"WD-{row['id']:04d}"))
            remaining -= take
            if remaining <= 0:
                break
        if remaining:
            raise ValueError(
                f"Allocation exceeds unallocated withdrawn cash by {money(remaining)}."
            )
        return sources

    def allocation_source_text(self, allocation_id: int) -> str:
        rows = self.all(
            """SELECT s.amount_cents,COALESCE(NULLIF(r.system_reference,''),'WD-' || PRINTF('%04d',r.id)) reference
               FROM cash_allocation_sources s JOIN remittances r ON r.id=s.withdrawal_id
               WHERE s.allocation_id=? ORDER BY r.txn_date,r.id""", (allocation_id,)
        )
        return ", ".join(f"{row['reference']} ({money(row['amount_cents'])})" for row in rows)

    def cash_allocation_rows(self, project_id: int | None = None, active_only: bool = False):
        where, params = ["a.voided=0"], []
        # Allocations are a shared custody layer. project_id is retained only as
        # legacy issuance context and never limits where the cash may be spent.
        if active_only:
            where.append("a.status IN ('Active','Partially Used','Open')")
        return self.all(
            f"""SELECT a.*,pr.name project,r.txn_date withdrawal_date,
                       COALESCE(c.name,resp.name,'') holder,
                       COALESCE(iss.name,'') issuer,COALESCE(rec.name,'') receiver,
                       r.amount_cents withdrawal_cents,
                       (SELECT GROUP_CONCAT(COALESCE(NULLIF(sr.system_reference,''),'WD-' || PRINTF('%04d',sr.id)))
                          FROM cash_allocation_sources src JOIN remittances sr ON sr.id=src.withdrawal_id
                          WHERE src.allocation_id=a.id) withdrawal_references,
                       COALESCE((SELECT SUM(p.amount_cents) FROM payments p
                         JOIN expenses e ON e.id=p.expense_id
                         WHERE p.cash_allocation_id=a.id AND e.voided=0
                           AND p.accounting_excluded=0),0) spent_cents,
                       COALESCE((SELECT SUM(t.amount_cents) FROM cash_allocation_transactions t
                         WHERE t.allocation_id=a.id AND t.txn_type IN ('Surrendered','Returned')),0) returned_cents,
                       COALESCE((SELECT SUM(s.amount_cents) FROM cash_repayment_surrenders s
                         WHERE s.cash_allocation_id=a.id),0) repayment_surrendered_cents
                FROM cash_allocations a
                JOIN projects pr ON pr.id=a.project_id
                JOIN remittances r ON r.id=a.withdrawal_id
                LEFT JOIN project_heads c ON c.id=a.custodian_head_id
                LEFT JOIN project_heads resp ON resp.id=a.responsible_head_id
                LEFT JOIN project_heads iss ON iss.id=a.issuer_head_id
                LEFT JOIN project_heads rec ON rec.id=a.receiver_head_id
                WHERE {' AND '.join(where)}
                ORDER BY a.allocation_date DESC,a.id DESC""", tuple(params)
        )

    def unallocated_cash(self) -> int:
        total_cash = self.cash_summary()[2]
        active_balances = sum(
            max(0, row["amount_cents"] - row["spent_cents"] - row["returned_cents"])
            for row in self.cash_allocation_rows()
        )
        return max(0, total_cash - active_balances - self.surrendered_awaiting_deposit())

    def surrendered_awaiting_deposit(self) -> int:
        allocation_surrendered = self.one(
            """SELECT COALESCE(SUM(t.amount_cents),0) total
               FROM cash_allocation_transactions t
               JOIN cash_allocations a ON a.id=t.allocation_id
               WHERE a.voided=0 AND t.txn_type='Surrendered'"""
        )["total"]
        allocation_redeposited = self.one(
            """SELECT COALESCE(SUM(s.amount_cents),0) total
               FROM cash_redeposit_sources s
               JOIN cash_redeposits d ON d.id=s.redeposit_id
               WHERE d.voided=0"""
        )["total"]
        repayment_surrendered = self.one(
            """SELECT COALESCE(SUM(amount_cents),0) total
               FROM cash_repayment_surrenders
               WHERE status='Awaiting Deposit'"""
        )["total"]
        return max(0, allocation_surrendered - allocation_redeposited) + repayment_surrendered

    def cash_allocation_summary(self, project_id: int | None = None) -> dict:
        rows = self.cash_allocation_rows(project_id)
        petty = direct = surrendered = 0
        for row in rows:
            balance = max(0, row["amount_cents"] - row["spent_cents"] - row["returned_cents"])
            if row["allocation_type"] == "Petty Cash": petty += balance
            else: direct += balance
            surrendered += row["returned_cents"]
        total_cash = self.cash_summary()[2]
        return {"total": total_cash, "unallocated": self.unallocated_cash(),
                "petty": petty, "direct": direct,
                "surrendered": self.surrendered_awaiting_deposit()}

    def _next_system_reference(self, prefix: str, table: str, column: str,
                               txn_date: str) -> str:
        stamp = txn_date.replace("-", "")[:8]
        base = f"{prefix}-{stamp}"
        sequence = self.one(
            f"SELECT COUNT(*) n FROM {table} WHERE {column} LIKE ?", (base + "-%",)
        )["n"] + 1
        reference = f"{base}-{sequence:04d}"
        while self.one(f"SELECT 1 FROM {table} WHERE {column}=?", (reference,)):
            sequence += 1
            reference = f"{base}-{sequence:04d}"
        return reference

    def _new_reference(self, prefix: str, project_id: int, txn_date: str) -> str:
        return self._next_system_reference(prefix, "cash_allocations", "reference", txn_date)

    def create_cash_allocation(self, *, project_id: int,
                               allocation_type: str, amount_cents: int,
                               allocation_date: str, issuer_head_id: int,
                               receiver_head_id: int, purpose: str = "",
                               supplier: str = "", notes: str = "",
                               withdrawal_id: int | None = None,
                               issuer_registry_id: int | None = None,
                               receiver_registry_id: int | None = None) -> int:
        if allocation_type not in {"Petty Cash", "Direct Procurement"}:
            raise ValueError("Select Petty Cash or Direct Procurement.")
        issuer_link = self.one(
            "SELECT registry_head_id FROM project_heads WHERE id=? AND active=1", (issuer_head_id,)
        )
        receiver_link = self.one(
            "SELECT registry_head_id FROM project_heads WHERE id=? AND active=1", (receiver_head_id,)
        )
        issuer_registry_id = issuer_registry_id or (
            issuer_link["registry_head_id"] if issuer_link and issuer_link["registry_head_id"] else None
        )
        receiver_registry_id = receiver_registry_id or (
            receiver_link["registry_head_id"] if receiver_link and receiver_link["registry_head_id"] else None
        )
        if issuer_registry_id and receiver_registry_id:
            valid_registry = self.one(
                """SELECT COUNT(*) n FROM head_registry
                   WHERE active=1 AND id IN (?,?)""", (issuer_registry_id, receiver_registry_id)
            )["n"]
            if valid_registry != 2:
                raise ValueError("Both approving people must be active registered project heads.")
        if (issuer_registry_id and issuer_registry_id == receiver_registry_id) or (
                not issuer_registry_id and issuer_head_id == receiver_head_id):
            raise ValueError("Issuer/approver and receiver/responsible head must be different people.")
        if not issuer_link or not receiver_link:
            raise ValueError("Both approving people must be active project heads assigned to at least one project.")
        if amount_cents <= 0:
            raise ValueError("Allocation amount must be positive.")
        if amount_cents > self.unallocated_cash():
            raise ValueError("This amount exceeds total unallocated cash on-hand.")
        sources = self.fifo_withdrawal_sources(amount_cents)
        withdrawal_id = sources[0][0]
        if allocation_type == "Petty Cash":
            count = self.one(
                """SELECT COUNT(*) n FROM cash_allocations a
                   LEFT JOIN project_heads h ON h.id=a.custodian_head_id
                   WHERE COALESCE(a.receiver_registry_id,h.registry_head_id,h.id)=? AND a.voided=0
                      AND a.status IN ('Active','Partially Used','Open')""",
                ((receiver_registry_id or receiver_head_id),),
            )["n"]
            if count >= 2:
                raise ValueError("This project head already has two active petty-cash allocations shared across all projects.")
        elif not supplier.strip():
            raise ValueError("A supplier or payee is required for Direct Procurement.")
        prefix = "PC" if allocation_type == "Petty Cash" else "DP"
        reference = self._new_reference(prefix, project_id, allocation_date)
        with self.conn:
            cursor = self.conn.execute(
                """INSERT INTO cash_allocations(reference,withdrawal_id,project_id,allocation_type,
                   amount_cents,allocation_date,custodian_head_id,responsible_head_id,supplier,purpose,
                   issuer_head_id,receiver_head_id,status,notes,shared_scope,allocation_time,
                   issuer_registry_id,receiver_registry_id)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (reference, withdrawal_id, project_id, allocation_type, amount_cents,
                 allocation_date, receiver_head_id if allocation_type == "Petty Cash" else None,
                 receiver_head_id if allocation_type == "Direct Procurement" else None,
                 supplier.strip(), purpose.strip(), issuer_head_id, receiver_head_id, "Active", notes.strip(),
                 1, local_timestamp(), issuer_registry_id, receiver_registry_id),
            )
            allocation_id = cursor.lastrowid
            self.conn.executemany(
                """INSERT INTO cash_allocation_sources(allocation_id,withdrawal_id,amount_cents)
                   VALUES(?,?,?)""",
                [(allocation_id, source_id, source_amount) for source_id, source_amount, _ref in sources],
            )
            self.conn.execute(
                """INSERT INTO cash_allocation_transactions(allocation_id,txn_type,amount_cents,
                   txn_date,actor_head_id,counterparty_head_id,notes,transaction_time)
                   VALUES(?,'Issued and Accepted',?,?,?,?,?,?)""",
                (allocation_id, amount_cents, allocation_date, issuer_head_id, receiver_head_id,
                 f"{allocation_type}: {purpose}", local_timestamp()),
            )
            self.conn.execute(
                "INSERT INTO audit_log(project_id,action,details) VALUES(?,?,?)",
                (project_id, "CASH_ALLOCATION_CREATED",
                 f"{reference} {allocation_type} {money(amount_cents)} from "
                 + ", ".join(f"{ref} {money(value)}" for _wid, value, ref in sources)),
            )
        return allocation_id

    def close_cash_allocation(self, allocation_id: int, txn_date: str,
                              actor_head_id: int, approver_head_id: int, notes: str = "") -> int:
        row = self.one("SELECT * FROM cash_allocations WHERE id=? AND voided=0", (allocation_id,))
        if not row or row["status"] not in {"Active", "Partially Used", "Open"}:
            raise ValueError("Select an active cash allocation.")
        if actor_head_id == approver_head_id:
            raise ValueError("Surrender requires two different project heads.")
        identities = self.all(
            """SELECT id,COALESCE(registry_head_id,id) registry_id FROM project_heads
               WHERE active=1 AND id IN (?,?)""", (actor_head_id, approver_head_id)
        )
        expected = {
            row["receiver_registry_id"] or row["receiver_head_id"],
            row["issuer_registry_id"] or row["issuer_head_id"],
        }
        if len(identities) != 2 or {identity["registry_id"] for identity in identities} != expected:
            raise ValueError("The registered receiver and issuer must both approve this surrender.")
        remaining = self.allocation_balance(allocation_id)
        with self.conn:
            self.conn.execute(
                """INSERT INTO cash_allocation_transactions(allocation_id,txn_type,amount_cents,
                   txn_date,actor_head_id,counterparty_head_id,notes,transaction_time)
                   VALUES(?,'Surrendered',?,?,?,?,?,?)""",
                (allocation_id, remaining, txn_date, actor_head_id, approver_head_id,
                 notes.strip(), local_timestamp()),
            )
            self.conn.execute(
                "UPDATE cash_allocations SET status='Surrendered',closed_at=? WHERE id=?",
                (txn_date, allocation_id),
            )
            self.conn.execute(
                "INSERT INTO audit_log(project_id,action,details) VALUES(?,?,?)",
                (row["project_id"], "CASH_ALLOCATION_SURRENDERED",
                 f"{row['reference']} returned {money(remaining)}"),
            )
        return remaining

    def _allocation_unspent_sources(self, allocation_id: int):
        spent = self.allocation_spent(allocation_id)
        result = []
        for row in self.all(
            """SELECT s.withdrawal_id,s.amount_cents,r.txn_date
               FROM cash_allocation_sources s JOIN remittances r ON r.id=s.withdrawal_id
               WHERE s.allocation_id=? ORDER BY r.txn_date,r.id""", (allocation_id,)
        ):
            consumed = min(spent, row["amount_cents"])
            spent -= consumed
            remaining = row["amount_cents"] - consumed
            if remaining > 0:
                result.append((row["withdrawal_id"], remaining))
        return result

    def redeposit_all_surrendered(self, bank_account_id: int, deposit_date: str,
                                  authorized_by_registry_id: int | None,
                                  notes: str = "") -> tuple[str, int]:
        bank = self.one("SELECT id FROM bank_accounts WHERE id=? AND active=1", (bank_account_id,))
        if not bank:
            raise ValueError("Select an active destination bank account.")
        lines = []
        allocations = self.all(
            """SELECT DISTINCT a.id FROM cash_allocations a
               JOIN cash_allocation_transactions t ON t.allocation_id=a.id
               WHERE a.voided=0 AND t.txn_type='Surrendered' ORDER BY a.id"""
        )
        for allocation in allocations:
            for withdrawal_id, available in self._allocation_unspent_sources(allocation["id"]):
                already = self.one(
                    """SELECT COALESCE(SUM(s.amount_cents),0) total
                       FROM cash_redeposit_sources s JOIN cash_redeposits d ON d.id=s.redeposit_id
                       WHERE s.allocation_id=? AND s.withdrawal_id=? AND d.voided=0""",
                    (allocation["id"], withdrawal_id),
                )["total"]
                amount = max(0, available - already)
                if amount:
                    lines.append((allocation["id"], withdrawal_id, amount))
        repayment_rows = self.all(
            """SELECT * FROM cash_repayment_surrenders
               WHERE status='Awaiting Deposit'
               ORDER BY surrender_date,id"""
        )
        total = sum(line[2] for line in lines) + sum(
            row["amount_cents"] for row in repayment_rows
        )
        if total <= 0:
            raise ValueError("There is no surrendered cash awaiting bank deposit.")
        reference = self._next_system_reference(
            "RD", "cash_redeposits", "reference", deposit_date
        )
        stamp = local_timestamp()
        with self.conn:
            redeposit_id = self.conn.execute(
                """INSERT INTO cash_redeposits(reference,bank_account_id,amount_cents,
                   deposit_date,transaction_time,authorized_by_registry_id,notes)
                   VALUES(?,?,?,?,?,?,?)""",
                (reference, bank_account_id, total, deposit_date, stamp,
                 authorized_by_registry_id, notes.strip()),
            ).lastrowid
            self.conn.executemany(
                """INSERT INTO cash_redeposit_sources(
                   redeposit_id,allocation_id,withdrawal_id,amount_cents) VALUES(?,?,?,?)""",
                [(redeposit_id, *line) for line in lines],
            )
            if repayment_rows:
                self.conn.executemany(
                    """UPDATE cash_repayment_surrenders
                       SET status='Redeposited',redeposit_id=? WHERE id=?""",
                    [(redeposit_id, row["id"]) for row in repayment_rows],
                )
            by_allocation = {}
            for allocation_id, _withdrawal_id, amount in lines:
                by_allocation[allocation_id] = by_allocation.get(allocation_id, 0) + amount
            for allocation_id, amount in by_allocation.items():
                self.conn.execute(
                    """INSERT INTO cash_allocation_transactions(allocation_id,txn_type,
                       amount_cents,txn_date,notes,system_reference,transaction_time)
                       VALUES(?,'Redeposited',?,?,?,?,?)""",
                    (allocation_id, amount, deposit_date,
                     f"Deposited to bank as {reference}", reference, stamp),
                )
                self.conn.execute(
                    "UPDATE cash_allocations SET status='Redeposited' WHERE id=?",
                    (allocation_id,),
                )
            self.conn.execute(
                "INSERT INTO audit_log(project_id,action,details,created_at) VALUES(NULL,?,?,?)",
                ("SURRENDERED_CASH_REDEPOSITED", f"{reference} {money(total)}", stamp),
            )
        return reference, total

    def validate_cash_allocation_payment(self, project_id: int, allocation_id: int | None,
                                         amount_cents: int):
        if not allocation_id:
            raise ValueError("Select an active Petty Cash or Direct Procurement reference for this cash payment.")
        allocation = self.one(
            """SELECT * FROM cash_allocations WHERE id=? AND voided=0
               AND status IN ('Active','Partially Used','Open')""", (allocation_id,)
        )
        if not allocation:
            raise ValueError("The selected shared cash allocation is not active.")
        available = self.allocation_balance(allocation_id)
        if amount_cents > available:
            raise ValueError(
                f"Payment exceeds {allocation['reference']}'s remaining balance of {money(available)}."
            )

    def register_allocation_payment(self, allocation_id: int, payment_id: int,
                                    expense_id: int, amount_cents: int,
                                    txn_date: str, head_id: int | None):
        self.conn.execute(
            """INSERT INTO cash_allocation_transactions(allocation_id,txn_type,amount_cents,
               txn_date,expense_id,payment_id,actor_head_id,notes,transaction_time)
               VALUES(?,'Expense Payment',?,?,?,?,?,?,?)""",
            (allocation_id, amount_cents, txn_date, expense_id, payment_id, head_id,
             f"Expense #{expense_id}", local_timestamp()),
        )
        if self.allocation_balance(allocation_id) <= 0:
            self.conn.execute(
                "UPDATE cash_allocations SET status='Completed',closed_at=? WHERE id=?",
                (txn_date, allocation_id),
            )
        else:
            self.conn.execute(
                "UPDATE cash_allocations SET status='Partially Used' WHERE id=? AND status='Active'",
                (allocation_id,),
            )

    def active_allocation_options(self, project_id: int | None = None) -> dict:
        options = {}
        for row in self.cash_allocation_rows(None, active_only=True):
            balance = max(0, row["amount_cents"] - row["spent_cents"] - row["returned_cents"])
            if balance <= 0: continue
            holder = row["holder"] or row["supplier"] or "Unassigned"
            label = f"{row['reference']} | {row['allocation_type']} | {holder} | {money(balance)} remaining"
            options[label] = row["id"]
        return options

    def salary_deduction_plan(self, employee_id: int, available_gross_cents: int,
                              eligible_through: str | None = None):
        """Allocate safe deductions FIFO without using a future-dated advance."""
        remaining_pay = max(0, int(available_gross_cents))
        if remaining_pay <= 0:
            return []
        rows = self.all(
            """SELECT t.*,ca.weekly_deduction_cap_cents,ca.advance_date
               FROM cash_advance_transactions t
               JOIN cash_advances ca ON ca.id=t.advance_id
               WHERE ca.employee_id=? AND ca.voided=0 AND t.voided=0
                  AND t.txn_type='Salary Deduction' AND t.posted=0
                  AND (? IS NULL OR ca.advance_date<=?)
               ORDER BY ca.advance_date,ca.id,t.id""",
            (employee_id, eligible_through, eligible_through)
        )
        used_by_advance, plan = {}, []
        for row in rows:
            if remaining_pay <= 0:
                break
            cap = max(0, row["weekly_deduction_cap_cents"] or 0)
            cap_left = max(0, cap - used_by_advance.get(row["advance_id"], 0)) if cap else remaining_pay
            amount = min(row["amount_cents"], remaining_pay, cap_left)
            if amount <= 0:
                continue
            plan.append({"transaction": row, "amount_cents": amount})
            remaining_pay -= amount
            used_by_advance[row["advance_id"]] = used_by_advance.get(row["advance_id"], 0) + amount
        return plan

    def post_salary_deduction_plan(self, plan, payroll_batch_id: int,
                                   posted_date: str, authorized_by_head_id: int):
        """Post only the applied amount and carry any scheduled remainder forward."""
        for item in plan:
            row, applied = item["transaction"], item["amount_cents"]
            if applied >= row["amount_cents"]:
                self.conn.execute(
                    """UPDATE cash_advance_transactions
                       SET posted=1,payroll_batch_id=?,txn_date=?,authorized_by_head_id=?
                       WHERE id=?""",
                    (payroll_batch_id, posted_date, authorized_by_head_id, row["id"]),
                )
                continue
            remainder = row["amount_cents"] - applied
            self.conn.execute(
                "UPDATE cash_advance_transactions SET amount_cents=? WHERE id=?",
                (remainder, row["id"]),
            )
            self.conn.execute(
                """INSERT INTO cash_advance_transactions(
                   advance_id,txn_type,amount_cents,txn_date,method,bank_account_id,
                   payroll_batch_id,reference,notes,authorized_by_head_id,posted)
                   VALUES(?,'Salary Deduction',?,?, 'Salary Deduction',NULL,?,?,?,?,1)""",
                (row["advance_id"], applied, posted_date, payroll_batch_id,
                 row["reference"], row["notes"], authorized_by_head_id),
            )

    def reduce_pending_salary_schedule(self, advance_id: int, amount_cents: int):
        """Reduce a future deduction when an advance is repaid by cash or bank."""
        remaining = max(0, int(amount_cents))
        rows = self.all(
            """SELECT * FROM cash_advance_transactions
               WHERE advance_id=? AND txn_type='Salary Deduction'
                 AND posted=0 AND voided=0 ORDER BY id""", (advance_id,)
        )
        for row in rows:
            if remaining <= 0:
                break
            if remaining >= row["amount_cents"]:
                remaining -= row["amount_cents"]
                self.conn.execute(
                    """UPDATE cash_advance_transactions SET voided=1,
                       notes=TRIM(notes || ' | Cancelled after direct recovery') WHERE id=?""",
                    (row["id"],),
                )
            else:
                self.conn.execute(
                    """UPDATE cash_advance_transactions SET amount_cents=?,
                       notes=TRIM(notes || ' | Reduced after direct recovery') WHERE id=?""",
                    (row["amount_cents"] - remaining, row["id"]),
                )
                remaining = 0

    def verify_expense_batch(self, project_id: int, expense_ids, head_ids,
                             verification_date: str, notes: str = "") -> str:
        expense_ids = list(dict.fromkeys(int(value) for value in expense_ids))
        head_ids = list(dict.fromkeys(int(value) for value in head_ids))
        if len(head_ids) != 2:
            raise ValueError("Verification requires two different project heads.")
        valid_heads = self.one(
            f"SELECT COUNT(*) n FROM project_heads WHERE project_id=? AND active=1 AND id IN ({','.join('?' for _ in head_ids)})",
            (project_id, *head_ids),
        )["n"]
        if valid_heads != 2:
            raise ValueError("Both verifiers must be active heads assigned to this project.")
        if not expense_ids:
            raise ValueError("Select at least one expense to verify.")
        placeholders = ','.join('?' for _ in expense_ids)
        valid_expenses = self.one(
            f"SELECT COUNT(*) n FROM expenses WHERE project_id=? AND voided=0 AND id IN ({placeholders})",
            (project_id, *expense_ids),
        )["n"]
        if valid_expenses != len(expense_ids):
            raise ValueError("Every selected expense must be active and belong to the same project.")
        stamp = verification_date.replace('-', '')
        base = f"VF-{stamp}"
        sequence = self.one(
            "SELECT COUNT(*) n FROM expense_verification_batches WHERE reference LIKE ?",
            (base + '-%',),
        )["n"] + 1
        reference = f"{base}-{sequence:03d}"
        with self.conn:
            batch_id = self.conn.execute(
                """INSERT INTO expense_verification_batches(reference,project_id,verification_date,
                   notes,verification_time) VALUES(?,?,?,?,?)""",
                (reference, project_id, verification_date, notes.strip(), local_timestamp())
            ).lastrowid
            self.conn.executemany(
                "INSERT INTO expense_verification_items(batch_id,expense_id) VALUES(?,?)",
                [(batch_id, expense_id) for expense_id in expense_ids],
            )
            self.conn.executemany(
                "INSERT INTO expense_verification_approvals(batch_id,head_id) VALUES(?,?)",
                [(batch_id, head_id) for head_id in head_ids],
            )
            self.conn.execute(
                f"UPDATE expenses SET verification_status='Verified',verified_at=? WHERE id IN ({placeholders})",
                (verification_date, *expense_ids),
            )
            self.conn.execute(
                "INSERT INTO audit_log(project_id,action,details) VALUES(?,?,?)",
                (project_id, "EXPENSES_VERIFIED", f"{reference}: {len(expense_ids)} expense(s)"),
            )
        return reference

    def validate_payment_source(self, project_id: int, amount_cents: int, method: str,
                                bank_account_id: int | None = None,
                                cash_allocation_id: int | None = None,
                                require_cash_allocation: bool = False):
        if amount_cents <= 0:
            raise ValueError("Payment amount must be positive.")
        _deposited, _paid, project_remaining = self.project_budget(project_id)
        if amount_cents > project_remaining:
            raise ValueError(
                f"Payment exceeds the project's remaining budget of {money(project_remaining)}."
            )
        if "bank" in method.strip().lower():
            if not bank_account_id:
                raise ValueError("Select the bank account used for this bank transfer.")
            available = self.bank_balance(bank_account_id)
            if amount_cents > available:
                raise ValueError(
                    f"Bank transfer exceeds the selected bank balance of {money(available)}."
                )
        else:
            _withdrawn, _cash_spent, cash_remaining = self.cash_summary()
            if amount_cents > cash_remaining:
                raise ValueError(
                    f"Cash payment exceeds cash on hand of {money(cash_remaining)}."
                )
            if require_cash_allocation:
                self.validate_cash_allocation_payment(project_id, cash_allocation_id, amount_cents)

    def employee_daily_rate_at(self, employee_id: int, work_date: str) -> int:
        assignment = self.one(
            """SELECT daily_rate_cents FROM employee_project_assignments
               WHERE employee_id=? AND effective_from<=?
                 AND (effective_to='' OR effective_to>=?)
               ORDER BY effective_from DESC,id DESC LIMIT 1""",
            (employee_id, work_date, work_date),
        )
        if assignment and assignment["daily_rate_cents"] > 0:
            return assignment["daily_rate_cents"]
        employee = self.one("SELECT * FROM employees WHERE id=?", (employee_id,))
        if not employee:
            raise ValueError("The selected employee no longer exists.")
        return employee_daily_rate(employee)

    def archive_employee(self, employee_id: int, reason: str,
                         authorized_by_head_id: int) -> None:
        employee = self.one("SELECT * FROM employees WHERE id=?", (employee_id,))
        if not employee or not employee["active"]:
            raise ValueError("Select an active employee to archive.")
        if self.one("SELECT 1 FROM attendance WHERE employee_id=? AND clock_out=''", (employee_id,)):
            raise ValueError("Clock the employee out before archiving their profile.")
        head = self.one(
            "SELECT id,name FROM project_heads WHERE id=? AND project_id=? AND active=1",
            (authorized_by_head_id, employee["project_id"]),
        )
        if not head:
            raise ValueError("An active project head from the employee's project must authorize archiving.")
        archived_at = local_timestamp()
        with self.conn:
            self.conn.execute(
                "UPDATE employees SET active=0,archived_at=?,archive_reason=? WHERE id=?",
                (archived_at, reason.strip(), employee_id),
            )
            self.conn.execute(
                "UPDATE employee_project_assignments SET effective_to=? WHERE employee_id=? AND effective_to=''",
                (archived_at[:10], employee_id),
            )
            self.conn.execute(
                "INSERT INTO audit_log(project_id,action,details) VALUES(?,?,?)",
                (employee["project_id"], "EMPLOYEE_ARCHIVED",
                 f"{employee['name']} [{employee['employee_no']}]: {reason}; authorized by {head['name']}"),
            )

    def transfer_employee(self, employee_id: int, destination_project_id: int,
                          effective_date: str, reason: str, position: str,
                          daily_rate_cents: int, source_head_id: int,
                          destination_head_id: int) -> None:
        effective_date = valid_date(effective_date, True)
        employee = self.one("SELECT * FROM employees WHERE id=?", (employee_id,))
        destination = self.one("SELECT id,name,status FROM projects WHERE id=?", (destination_project_id,))
        if not employee or not employee["active"]:
            raise ValueError("Select an active employee to transfer.")
        if not destination or destination_project_id == employee["project_id"]:
            raise ValueError("Select a different destination project.")
        if destination["status"] == "Completed":
            raise ValueError("Employees cannot be transferred into a completed project.")
        if daily_rate_cents <= 0:
            raise ValueError("The daily rate must be greater than zero.")
        if self.one("SELECT 1 FROM attendance WHERE employee_id=? AND clock_out=''", (employee_id,)):
            raise ValueError("Clock the employee out before transferring them.")
        source_head = self.one(
            "SELECT id,name FROM project_heads WHERE id=? AND project_id=? AND active=1",
            (source_head_id, employee["project_id"]),
        )
        destination_head = self.one(
            "SELECT id,name FROM project_heads WHERE id=? AND project_id=? AND active=1",
            (destination_head_id, destination_project_id),
        )
        if not source_head or not destination_head:
            raise ValueError("Both source and destination project heads must authorize the transfer.")
        try:
            with self.conn:
                self.conn.execute(
                    "UPDATE employee_project_assignments SET effective_to=? WHERE employee_id=? AND effective_to=''",
                    (effective_date, employee_id),
                )
                self.conn.execute(
                    """INSERT INTO employee_project_assignments(employee_id,project_id,
                       effective_from,position,daily_rate_cents,reason,authorized_by_head_id)
                       VALUES(?,?,?,?,?,?,?)""",
                    (employee_id, destination_project_id, effective_date, position.strip(),
                     daily_rate_cents, reason.strip(), destination_head_id),
                )
                self.conn.execute(
                    """UPDATE employees SET project_id=?,position=?,pay_basis='Daily',
                       rate_cents=?,daily_rate_cents=? WHERE id=?""",
                    (destination_project_id, position.strip(), daily_rate_cents,
                     daily_rate_cents, employee_id),
                )
                details = (f"{employee['name']} [{employee['employee_no']}] transferred to "
                           f"{destination['name']} effective {effective_date}: {reason}; "
                           f"source approval {source_head['name']}; destination approval {destination_head['name']}")
                self.conn.execute("INSERT INTO audit_log(project_id,action,details) VALUES(?,?,?)",
                                  (employee["project_id"], "EMPLOYEE_TRANSFERRED_OUT", details))
                self.conn.execute("INSERT INTO audit_log(project_id,action,details) VALUES(?,?,?)",
                                  (destination_project_id, "EMPLOYEE_TRANSFERRED_IN", details))
        except sqlite3.IntegrityError as exc:
            if "employees.project_id, employees.employee_no" in str(exc):
                raise ValueError("That employee number is already used in the destination project.") from exc
            raise

    def reactivate_employee(self, employee_id: int, destination_project_id: int,
                            effective_date: str, reason: str, position: str,
                            daily_rate_cents: int, authorized_by_head_id: int) -> None:
        effective_date = valid_date(effective_date, True)
        employee = self.one("SELECT * FROM employees WHERE id=?", (employee_id,))
        destination = self.one("SELECT id,name,status FROM projects WHERE id=?", (destination_project_id,))
        if not employee or employee["active"]:
            raise ValueError("Select an archived employee to reactivate.")
        if not destination or daily_rate_cents <= 0:
            raise ValueError("Select a destination project and enter a positive daily rate.")
        if destination["status"] == "Completed":
            raise ValueError("Employees cannot be reactivated into a completed project.")
        head = self.one(
            "SELECT id,name FROM project_heads WHERE id=? AND project_id=? AND active=1",
            (authorized_by_head_id, destination_project_id),
        )
        if not head:
            raise ValueError("An active destination-project head must authorize reactivation.")
        with self.conn:
            self.conn.execute(
                """INSERT INTO employee_project_assignments(employee_id,project_id,effective_from,
                   position,daily_rate_cents,reason,authorized_by_head_id) VALUES(?,?,?,?,?,?,?)""",
                (employee_id, destination_project_id, effective_date, position.strip(),
                 daily_rate_cents, reason.strip(), authorized_by_head_id),
            )
            self.conn.execute(
                """UPDATE employees SET active=1,project_id=?,position=?,pay_basis='Daily',
                   rate_cents=?,daily_rate_cents=?,archived_at='',archive_reason='' WHERE id=?""",
                (destination_project_id, position.strip(), daily_rate_cents,
                 daily_rate_cents, employee_id),
            )
            self.conn.execute("INSERT INTO audit_log(project_id,action,details) VALUES(?,?,?)",
                (destination_project_id, "EMPLOYEE_REACTIVATED",
                 f"{employee['name']} [{employee['employee_no']}] reactivated in {destination['name']} "
                 f"effective {effective_date}: {reason}; authorized by {head['name']}"))

    def revise_attendance(self, attendance_id: int, new_clock_in: datetime,
                          new_clock_out: datetime, correction_reason: str,
                          authorized_by_head_id: int) -> dict:
        row = self.one(
            """SELECT a.*,e.name,e.employee_no,e.project_id current_project_id
               FROM attendance a JOIN employees e ON e.id=a.employee_id WHERE a.id=?""",
            (attendance_id,),
        )
        if not row or not row["clock_out"]:
            raise ValueError("Only completed attendance can be corrected.")
        reason = correction_reason.strip()
        if not reason:
            raise ValueError("Enter the reason for this attendance correction.")
        project_id = row["project_id"] or row["current_project_id"]
        head = self.one(
            "SELECT id,name FROM project_heads WHERE id=? AND project_id=? AND active=1",
            (authorized_by_head_id, project_id),
        )
        if not head:
            raise ValueError("An active project head for this attendance project must authorize the correction.")
        rate = self.employee_daily_rate_at(row["employee_id"], new_clock_in.date().isoformat())
        result = compute_shift_pay(new_clock_in, new_clock_out, rate)
        delta = result["gross_cents"] - row["gross_cents"]
        batch = (self.one("SELECT * FROM payroll_batches WHERE id=?", (row["payroll_batch_id"],))
                 if row["payroll_batch_id"] else None)
        locked = False
        if batch and batch["expense_id"]:
            expense = self.one(
                """SELECT e.*,COALESCE((SELECT SUM(amount_cents) FROM payments p
                   WHERE p.expense_id=e.id AND p.accounting_excluded=0),0) paid_cents
                   FROM expenses e WHERE e.id=?""", (batch["expense_id"],),
            )
            locked = bool(expense and (expense["paid_cents"] > 0 or
                          (expense["verification_status"] or "Unverified") == "Verified"))
        adjustment_id = None
        with self.conn:
            self.conn.execute(
                """INSERT INTO attendance_revisions(attendance_id,project_id,old_clock_in,
                   old_clock_out,new_clock_in,new_clock_out,old_gross_cents,new_gross_cents,
                   payroll_batch_id,correction_reason,authorized_by_head_id)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (attendance_id, project_id, row["clock_in"], row["clock_out"],
                 new_clock_in.isoformat(timespec="seconds"), new_clock_out.isoformat(timespec="seconds"),
                 row["gross_cents"], result["gross_cents"], row["payroll_batch_id"],
                 reason, authorized_by_head_id),
            )
            self.conn.execute(
                """UPDATE attendance SET project_id=?,clock_in=?,clock_out=?,hours=?,lunch_hours=?,
                   regular_hours=?,overtime_hours=?,regular_pay_cents=?,overtime_pay_cents=?,
                   gross_cents=?,revision_count=revision_count+1 WHERE id=?""",
                (project_id, new_clock_in.isoformat(timespec="seconds"),
                 new_clock_out.isoformat(timespec="seconds"), result["hours"], result["lunch_hours"],
                 result["regular_hours"], result["overtime_hours"], result["regular_pay_cents"],
                 result["overtime_pay_cents"], result["gross_cents"], attendance_id),
            )
            if row["closure_batch_id"]:
                self.conn.execute(
                    """UPDATE attendance_closure_batches SET gross_cents=COALESCE((
                       SELECT SUM(gross_cents) FROM attendance
                       WHERE closure_batch_id=attendance_closure_batches.id),0) WHERE id=?""",
                    (row["closure_batch_id"],),
                )
            if batch and delta:
                if locked:
                    adjustment_id = self.conn.execute(
                        """INSERT INTO payroll_adjustments(employee_id,project_id,
                           source_attendance_id,source_payroll_batch_id,amount_cents,reason,
                           authorized_by_head_id) VALUES(?,?,?,?,?,?,?)""",
                        (row["employee_id"], project_id, attendance_id, batch["id"], delta,
                         reason, authorized_by_head_id),
                    ).lastrowid
                else:
                    new_gross = batch["gross_cents"] + delta
                    new_net = batch["net_cents"] + delta
                    if new_net < 0:
                        raise ValueError("The correction would make this payroll batch negative.")
                    self.conn.execute("UPDATE payroll_batches SET gross_cents=?,net_cents=? WHERE id=?",
                                      (new_gross, new_net, batch["id"]))
                    self.conn.execute(
                        """UPDATE expenses SET total_cents=?,unit_price_cents=?,status=CASE
                           WHEN ?<=0 THEN 'Paid' ELSE 'Unpaid' END WHERE id=?""",
                        (new_net, new_net, new_net, batch["expense_id"]),
                    )
            self.conn.execute("INSERT INTO audit_log(project_id,action,details) VALUES(?,?,?)",
                (project_id, "ATTENDANCE_CORRECTED",
                 f"Attendance #{attendance_id}, {row['name']} [{row['employee_no']}], "
                 f"gross {money(row['gross_cents'])} to {money(result['gross_cents'])}, "
                 f"reason: {reason}; authorized by {head['name']}"))
        return {"attendance_id": attendance_id, "delta_cents": delta,
                "locked_adjustment": bool(batch and locked and delta),
                "adjustment_id": adjustment_id, **result}

    def closable_attendance_dates(self, project_id: int):
        """Return work dates that still need daily attendance closure."""
        return self.all(
            """SELECT SUBSTR(a.clock_in,1,10) work_date,COUNT(*) attendance_count,
                      COALESCE(SUM(a.gross_cents),0) gross_cents
               FROM attendance a JOIN employees e ON e.id=a.employee_id
               WHERE COALESCE(a.project_id,e.project_id)=? AND a.clock_out<>''
                 AND a.committed_expense_id IS NULL AND a.payroll_batch_id IS NULL
                 AND a.closure_batch_id IS NULL
               GROUP BY SUBSTR(a.clock_in,1,10) ORDER BY work_date""",
            (project_id,),
        )

    def close_attendance_day(self, project_id: int, work_date: str,
                             authorized_by_head_id: int) -> dict:
        """Lock one completed work day into the weekly payroll accumulator."""
        work_date = valid_date(work_date, True)
        rows = self.all(
            """SELECT a.id,a.gross_cents FROM attendance a
               JOIN employees e ON e.id=a.employee_id
               WHERE COALESCE(a.project_id,e.project_id)=? AND SUBSTR(a.clock_in,1,10)=?
                 AND a.clock_out<>'' AND a.committed_expense_id IS NULL
                 AND a.payroll_batch_id IS NULL AND a.closure_batch_id IS NULL
               ORDER BY a.id""", (project_id, work_date),
        )
        if not rows:
            raise ValueError("There is no completed, unclosed attendance for that date.")
        head = self.one(
            "SELECT id,name FROM project_heads WHERE id=? AND project_id=? AND active=1",
            (authorized_by_head_id, project_id),
        )
        if not head:
            raise ValueError("The authorizing project head is not active for this project.")
        gross = sum(row["gross_cents"] for row in rows)
        reference = self._next_system_reference(
            "ATD", "attendance_closure_batches", "closure_ref", work_date
        )
        with self.conn:
            batch_id = self.conn.execute(
                """INSERT INTO attendance_closure_batches(
                   project_id,closure_ref,work_date,attendance_count,gross_cents,
                   authorized_by_head_id) VALUES(?,?,?,?,?,?)""",
                (project_id, reference, work_date, len(rows), gross, authorized_by_head_id),
            ).lastrowid
            self.conn.executemany(
                "UPDATE attendance SET closure_batch_id=? WHERE id=?",
                [(batch_id, row["id"]) for row in rows],
            )
            self.conn.execute(
                "INSERT INTO audit_log(project_id,action,details) VALUES(?,?,?)",
                (project_id, "DAILY_ATTENDANCE_CLOSED",
                 f"{reference}: {len(rows)} attendance record(s), gross {money(gross)}, "
                 f"authorized by {head['name']}"),
            )
        return {"id": batch_id, "reference": reference, "work_date": work_date,
                "count": len(rows), "gross_cents": gross}

    def weekly_payroll_summary(self, project_id: int, week_value: str | date):
        """Return every active employee and closed, uncommitted pay for a week."""
        week_start, week_end = payroll_week_bounds(week_value)
        employees = self.all(
            """SELECT e.*,p.name project_name,
                      COUNT(a.id) attendance_count,
                      COALESCE(SUM(CAST(NULLIF(a.regular_hours,'') AS REAL)),0) regular_hours_total,
                      COALESCE(SUM(CAST(NULLIF(a.overtime_hours,'') AS REAL)),0) overtime_hours_total,
                      COALESCE(SUM(a.gross_cents),0) gross_cents,
                      COALESCE(GROUP_CONCAT(DISTINCT cb.closure_ref),'') closure_references
               FROM employees e JOIN projects p ON p.id=?
               LEFT JOIN attendance a ON a.employee_id=e.id AND a.clock_out<>''
                    AND a.closure_batch_id IS NOT NULL AND a.payroll_batch_id IS NULL
                    AND a.committed_expense_id IS NULL
                    AND COALESCE(a.project_id,e.project_id)=?
                    AND SUBSTR(a.clock_in,1,10) BETWEEN ? AND ?
               LEFT JOIN attendance_closure_batches cb ON cb.id=a.closure_batch_id
               WHERE (e.project_id=? AND e.active=1) OR a.id IS NOT NULL
               GROUP BY e.id ORDER BY e.name COLLATE NOCASE""",
            (project_id, project_id, week_start, week_end, project_id),
        )
        result = []
        for employee in employees:
            deduction = sum(
                item["amount_cents"]
                for item in self.salary_deduction_plan(
                    employee["id"], employee["gross_cents"], week_end)
            )
            adjustment = self.one(
                """SELECT COALESCE(SUM(amount_cents),0) total FROM payroll_adjustments
                   WHERE employee_id=? AND project_id=? AND status='Pending'""",
                (employee["id"], project_id),
            )["total"]
            row = dict(employee)
            row.update(week_start=week_start, week_end=week_end,
                       deduction_cents=deduction,
                       adjustment_cents=adjustment,
                       net_cents=employee["gross_cents"] - deduction + adjustment)
            result.append(row)
        return result

    def payroll_batch_employee_summary(self, batch_id: int):
        """Return one reconciled weekly-payroll row per employee in a committed batch."""
        if not self.one("SELECT 1 FROM payroll_batches WHERE id=?", (batch_id,)):
            raise ValueError("The selected payroll batch no longer exists.")
        return self.all(
            """SELECT e.id employee_id,e.employee_no,e.name,e.position,e.class,
                      COUNT(a.id) attendance_entries,
                      COUNT(DISTINCT SUBSTR(a.clock_in,1,10)) attendance_days,
                      COALESCE(SUM(CAST(NULLIF(a.regular_hours,'') AS REAL)),0) regular_hours,
                      COALESCE(SUM(CAST(NULLIF(a.overtime_hours,'') AS REAL)),0) overtime_hours,
                      COALESCE(SUM(a.regular_pay_cents),0) regular_pay_cents,
                      COALESCE(SUM(a.overtime_pay_cents),0) overtime_pay_cents,
                      COALESCE(SUM(a.gross_cents),0) gross_cents,
                       COALESCE((SELECT SUM(t.amount_cents)
                        FROM cash_advance_transactions t
                        JOIN cash_advances ca ON ca.id=t.advance_id
                        WHERE t.payroll_batch_id=? AND ca.employee_id=e.id
                          AND t.txn_type='Salary Deduction' AND t.posted=1
                          AND t.voided=0 AND ca.voided=0),0) deduction_cents,
                       COALESCE((SELECT SUM(pa.amount_cents) FROM payroll_adjustments pa
                         WHERE pa.applied_payroll_batch_id=? AND pa.employee_id=e.id
                           AND pa.status='Applied'),0) adjustment_cents
               FROM attendance a JOIN employees e ON e.id=a.employee_id
               WHERE a.payroll_batch_id=?
               GROUP BY e.id ORDER BY e.name COLLATE NOCASE""",
            (batch_id, batch_id, batch_id),
        )

    def commit_weekly_payroll(self, project_id: int, week_value: str | date,
                              authorized_by_head_id: int) -> dict:
        """Create one weekly payroll expense from daily-closed attendance only."""
        week_start, week_end = payroll_week_bounds(week_value)
        attendance = self.all(
            """SELECT a.*,e.id employee_id,e.name FROM attendance a
               JOIN employees e ON e.id=a.employee_id
               WHERE COALESCE(a.project_id,e.project_id)=? AND a.clock_out<>''
                 AND a.closure_batch_id IS NOT NULL AND a.payroll_batch_id IS NULL
                 AND a.committed_expense_id IS NULL
                 AND SUBSTR(a.clock_in,1,10) BETWEEN ? AND ?
               ORDER BY a.clock_in,a.id""", (project_id, week_start, week_end),
        )
        if not attendance:
            raise ValueError("This week has no daily-closed attendance awaiting payroll.")
        head = self.one(
            "SELECT id,name FROM project_heads WHERE id=? AND project_id=? AND active=1",
            (authorized_by_head_id, project_id),
        )
        if not head:
            raise ValueError("The authorizing project head is not active for this project.")
        gross_by_employee = {}
        for row in attendance:
            gross_by_employee[row["employee_id"]] = (
                gross_by_employee.get(row["employee_id"], 0) + row["gross_cents"]
            )
        deduction_plan = []
        for employee_id, employee_gross in gross_by_employee.items():
            deduction_plan.extend(
                self.salary_deduction_plan(employee_id, employee_gross, week_end)
            )
        gross = sum(row["gross_cents"] for row in attendance)
        deduction_total = sum(item["amount_cents"] for item in deduction_plan)
        adjustment_rows = self.all(
            f"""SELECT * FROM payroll_adjustments WHERE project_id=? AND status='Pending'
               AND employee_id IN ({','.join('?' for _ in gross_by_employee)}) ORDER BY id""",
            (project_id, *gross_by_employee),
        )
        adjustment_total = sum(row["amount_cents"] for row in adjustment_rows)
        net = gross - deduction_total + adjustment_total
        _deposited, _committed, remaining = self.project_commitment_budget(project_id)
        if net > remaining:
            raise ValueError(
                f"Weekly payroll exceeds the project's remaining commitment budget of {money(remaining)}."
            )
        commit_date = date.today().isoformat()
        reference = self._next_system_reference(
            "PAYW", "payroll_batches", "batch_ref", week_start
        )
        with self.conn:
            expense_id = self.conn.execute(
                """INSERT INTO expenses(project_id,name,item,supplier,qty,unit,
                   unit_price_cents,total_cents,area,trade,expense_date,due_date,
                   payroll_batch,notes,authorized_by_head_id,status)
                   VALUES(?,?,?,?, '1','week',?,?,?,?,?,?,?,?,?,?)""",
                (project_id, f"Weekly Payroll {week_start} to {week_end}",
                 "Daily-closed attendance payroll", "Payroll", net, net,
                 "PAYROLL", "Labor", commit_date, commit_date, reference,
                  f"{len(attendance)} attendance record(s); salary deductions {money(deduction_total)}; "
                  f"attendance corrections {money(adjustment_total)}",
                 authorized_by_head_id, "Paid" if net <= 0 else "Unpaid"),
            ).lastrowid
            batch_id = self.conn.execute(
                """INSERT INTO payroll_batches(project_id,batch_ref,period_start,
                   period_end,gross_cents,deduction_cents,adjustment_cents,net_cents,expense_id,
                   authorized_by_head_id,week_schedule) VALUES(?,?,?,?,?,?,?,?,?,?,'Saturday-Friday')""",
                 (project_id, reference, week_start, week_end, gross,
                  deduction_total, adjustment_total, net, expense_id, authorized_by_head_id),
            ).lastrowid
            self.conn.executemany(
                """UPDATE attendance SET committed_expense_id=?,payroll_batch_id=?
                   WHERE id=?""",
                [(expense_id, batch_id, row["id"]) for row in attendance],
            )
            if deduction_plan:
                self.post_salary_deduction_plan(
                    deduction_plan, batch_id, commit_date, authorized_by_head_id
                )
            if adjustment_rows:
                self.conn.executemany(
                    """UPDATE payroll_adjustments SET status='Applied',applied_payroll_batch_id=?
                       WHERE id=?""",
                    [(batch_id, row["id"]) for row in adjustment_rows],
                )
            self.conn.execute(
                "INSERT INTO audit_log(project_id,action,details) VALUES(?,?,?)",
                (project_id, "WEEKLY_PAYROLL_COMMITTED",
                 f"{reference}: {week_start} to {week_end}, gross {money(gross)}, "
                  f"deductions {money(deduction_total)}, corrections {money(adjustment_total)}, "
                  f"net {money(net)}, "
                 f"authorized by {head['name']}"),
            )
        return {"id": batch_id, "reference": reference,
                "week_start": week_start, "week_end": week_end,
                "attendance_count": len(attendance), "gross_cents": gross,
                "deduction_cents": deduction_total, "adjustment_cents": adjustment_total,
                "net_cents": net,
                "expense_id": expense_id}

    def create_project(self, values: dict) -> int:
        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO projects(name,client,contract_value_cents,start_date,target_date,address,notes)
                   VALUES(?,?,?,?,?,?,?)""",
                (values["name"], values["client"], cents(values["contract_value"]),
                 valid_date(values["start_date"]), valid_date(values["target_date"]),
                 values.get("address", ""), values["notes"]),
            )
            project_id = cur.lastrowid
            self.conn.executemany(
                "INSERT INTO phases(project_id,name,sort_order) VALUES(?,?,?)",
                [(project_id, name, index) for index, name in enumerate(DEFAULT_PHASES)],
            )
            if values.get("head_ids"):
                self._assign_registered_heads(project_id, values["head_ids"])
            else:
                # Backward-compatible import path for early callers that supplied
                # head details directly instead of selecting from the registry.
                for head in values.get("heads", []):
                    salt, digest = hash_pin(head["pin"])
                    registered = self.conn.execute(
                        """SELECT id FROM head_registry
                           WHERE LOWER(TRIM(name))=LOWER(TRIM(?))
                             AND LOWER(TRIM(position))=LOWER(TRIM(?))""",
                        (head["name"], head["position"]),
                    ).fetchone()
                    if registered:
                        registry_id = registered["id"]
                    else:
                        registry_id = self.conn.execute(
                            """INSERT INTO head_registry(name,position,pin_salt,pin_hash)
                               VALUES(?,?,?,?)""",
                            (head["name"], head["position"], salt, digest),
                        ).lastrowid
                    self.conn.execute(
                        """INSERT INTO project_heads(
                           project_id,name,position,pin_salt,pin_hash,registry_head_id)
                           VALUES(?,?,?,?,?,?)""",
                        (project_id, head["name"], head["position"], salt, digest, registry_id),
                    )
            self.conn.execute(
                "INSERT INTO audit_log(project_id,action,details) VALUES(?,?,?)",
                (project_id, "PROJECT_CREATED", values["name"]),
            )
        return project_id

    def project_is_active(self, project_id: int | None) -> bool:
        if not project_id:
            return False
        row = self.one("SELECT status FROM projects WHERE id=?", (project_id,))
        return bool(row and (row["status"] or "Active") != "Completed")

    def project_completion_metrics(self, project_id: int) -> dict:
        project = self.one("SELECT * FROM projects WHERE id=?", (project_id,))
        if not project:
            raise ValueError("The selected project no longer exists.")
        deposited, paid, _payment_balance = self.project_budget(project_id)
        _dep, committed, budget_remaining = self.project_commitment_budget(project_id)
        tasks = self.one(
            """SELECT COUNT(*) total,COALESCE(SUM(t.completed),0) done
               FROM tasks t JOIN phases p ON p.id=t.phase_id WHERE p.project_id=?""",
            (project_id,),
        )
        task_count = tasks["total"]
        completed_task_count = tasks["done"]
        progress = round(completed_task_count * 100 / task_count) if task_count else 0
        expense_count = self.one(
            "SELECT COUNT(*) n FROM expenses WHERE project_id=? AND voided=0", (project_id,)
        )["n"]
        payroll_batch_count = self.one(
            "SELECT COUNT(*) n FROM payroll_batches WHERE project_id=?", (project_id,)
        )["n"]
        attendance_count = self.one(
            """SELECT COUNT(*) n FROM attendance a JOIN employees e ON e.id=a.employee_id
               WHERE COALESCE(a.project_id,e.project_id)=?""", (project_id,)
        )["n"]
        return {
            "contract_value_cents": project["contract_value_cents"],
            "deposited_cents": deposited,
            "active_expense_cents": committed,
            "paid_cents": paid,
            "outstanding_cents": max(0, committed - paid),
            "budget_remaining_cents": budget_remaining,
            "task_count": task_count,
            "completed_task_count": completed_task_count,
            "progress_percent": progress,
            "expense_count": expense_count,
            "payroll_batch_count": payroll_batch_count,
            "attendance_count": attendance_count,
        }

    def project_completion_checks(self, project_id: int) -> dict:
        """Return blockers that must be resolved and warnings retained in the closeout."""
        open_attendance = self.one(
            """SELECT COUNT(*) n FROM attendance a JOIN employees e ON e.id=a.employee_id
               WHERE COALESCE(a.project_id,e.project_id)=? AND a.clock_out=''""", (project_id,)
        )["n"]
        uncommitted_attendance = self.one(
            """SELECT COUNT(*) n FROM attendance a JOIN employees e ON e.id=a.employee_id
               WHERE COALESCE(a.project_id,e.project_id)=? AND a.clock_out<>''
                 AND a.payroll_batch_id IS NULL""", (project_id,)
        )["n"]
        metrics = self.project_completion_metrics(project_id)
        unverified = self.one(
            """SELECT COUNT(*) n FROM expenses WHERE project_id=? AND voided=0
               AND COALESCE(verification_status,'Unverified')<>'Verified'""", (project_id,)
        )["n"]
        outstanding_advances = self.one(
            """SELECT COALESCE(SUM(MAX(a.original_cents-COALESCE((SELECT SUM(t.amount_cents)
                   FROM cash_advance_transactions t WHERE t.advance_id=a.id AND t.posted=1
                   AND t.voided=0 AND t.txn_type<>'Advance'),0),0)),0) total
               FROM cash_advances a WHERE a.project_id=? AND a.voided=0""", (project_id,)
        )["total"]
        return {
            "blockers": [message for count, message in (
                (open_attendance, f"{open_attendance} employee attendance record(s) are still clocked in."),
                (uncommitted_attendance,
                 f"{uncommitted_attendance} closed attendance record(s) have not been committed to weekly payroll."),
            ) if count],
            "warnings": [message for condition, message in (
                (metrics["outstanding_cents"] > 0,
                 f"Outstanding expense commitments: {money(metrics['outstanding_cents'])}."),
                (metrics["completed_task_count"] < metrics["task_count"],
                 f"Incomplete process tasks: {metrics['task_count']-metrics['completed_task_count']} of {metrics['task_count']}."),
                (unverified > 0, f"Unverified active expenses: {unverified}."),
                (outstanding_advances > 0,
                 f"Outstanding employee cash advances: {money(outstanding_advances)}."),
            ) if condition],
            "metrics": metrics,
        }

    def complete_project(self, project_id: int, completion_date: str,
                         notes: str, approving_heads) -> str:
        project = self.one("SELECT * FROM projects WHERE id=?", (project_id,))
        if not project:
            raise ValueError("The selected project no longer exists.")
        if not self.project_is_active(project_id):
            raise ValueError("This project is already completed.")
        completion_date = valid_date(completion_date, True)
        checks = self.project_completion_checks(project_id)
        if checks["blockers"]:
            raise ValueError("Project completion is blocked:\n\n" + "\n".join(checks["blockers"]))
        metrics = checks["metrics"]
        reference = self._next_system_reference(
            "CMP", "project_completion_snapshots", "completion_reference", completion_date
        )
        head_ids = ",".join(str(row["id"]) for row in approving_heads)
        head_names = ", ".join(row["name"] for row in approving_heads)
        completed_at = local_timestamp()
        with self.conn:
            self.conn.execute(
                """INSERT INTO project_completion_snapshots(
                   project_id,completion_reference,completion_date,completion_time,
                   completed_by_head_ids,completed_by_names,completion_notes,
                   contract_value_cents,deposited_cents,active_expense_cents,paid_cents,
                   outstanding_cents,budget_remaining_cents,task_count,completed_task_count,
                   progress_percent,expense_count,payroll_batch_count,attendance_count)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (project_id, reference, completion_date, completed_at, head_ids, head_names,
                 notes.strip(), metrics["contract_value_cents"], metrics["deposited_cents"],
                 metrics["active_expense_cents"], metrics["paid_cents"],
                 metrics["outstanding_cents"], metrics["budget_remaining_cents"],
                 metrics["task_count"], metrics["completed_task_count"],
                 metrics["progress_percent"], metrics["expense_count"],
                 metrics["payroll_batch_count"], metrics["attendance_count"]),
            )
            self.conn.execute(
                """UPDATE projects SET status='Completed',completed_at=?,completion_reference=?,
                   completion_notes=?,completed_by_names=? WHERE id=?""",
                (completed_at, reference, notes.strip(), head_names, project_id),
            )
            self.conn.execute(
                "INSERT INTO audit_log(project_id,action,details) VALUES(?,?,?)",
                (project_id, "PROJECT_COMPLETED",
                 f"{reference}; completion date {completion_date}; approved by {head_names}; {notes.strip()}"),
            )
        return reference

    def reactivate_project(self, project_id: int, notes: str, approving_heads) -> None:
        project = self.one("SELECT * FROM projects WHERE id=?", (project_id,))
        if not project or (project["status"] or "Active") != "Completed":
            raise ValueError("Only a completed project can be reactivated.")
        if not notes.strip():
            raise ValueError("Enter a reason for reactivating the project.")
        head_names = ", ".join(row["name"] for row in approving_heads)
        now = local_timestamp()
        with self.conn:
            self.conn.execute(
                """UPDATE project_completion_snapshots SET reactivated_at=?,
                   reactivated_by_names=?,reactivation_notes=?
                   WHERE id=(SELECT id FROM project_completion_snapshots
                             WHERE project_id=? AND reactivated_at='' ORDER BY id DESC LIMIT 1)""",
                (now, head_names, notes.strip(), project_id),
            )
            self.conn.execute(
                """UPDATE projects SET status='Active',completed_at='',completion_reference='',
                   completion_notes='',completed_by_names='' WHERE id=?""", (project_id,)
            )
            self.conn.execute(
                "INSERT INTO audit_log(project_id,action,details) VALUES(?,?,?)",
                (project_id, "PROJECT_REACTIVATED", f"Approved by {head_names}; {notes.strip()}"),
            )

    def next_inventory_item_code(self, project_id: int) -> str:
        sequence = self.one(
            "SELECT COUNT(*) n FROM inventory_items WHERE project_id=?", (project_id,)
        )["n"] + 1
        code = f"INV-{project_id:03d}-{sequence:04d}"
        while self.one("SELECT 1 FROM inventory_items WHERE item_code=?", (code,)):
            sequence += 1
            code = f"INV-{project_id:03d}-{sequence:04d}"
        return code

    def inventory_item_balance(self, item_id: int) -> dict:
        item = self.one("SELECT * FROM inventory_items WHERE id=?", (item_id,))
        if not item:
            raise ValueError("The selected inventory item no longer exists.")
        if item["material_type"] == "Consumable":
            movement = self.one(
                """SELECT COALESCE(SUM(CASE
                       WHEN transaction_type IN ('Initial Stock','Restock') THEN quantity_milli
                       WHEN transaction_type='Consume' THEN -quantity_milli ELSE 0 END),0) balance
                   FROM inventory_transactions WHERE item_id=? AND voided=0""", (item_id,)
            )["balance"]
            on_hand = max(0, movement)
            status = ("Out of Stock" if on_hand <= 0 else
                      "Low Stock" if on_hand <= item["reorder_level_milli"] else "In Stock")
            return {"on_hand_milli": on_hand, "borrowed_milli": 0,
                    "available_milli": on_hand, "status": status}
        borrowed = self.one(
            """SELECT COALESCE(SUM(CASE WHEN transaction_type='Borrow' THEN quantity_milli
                       WHEN transaction_type='Return' THEN -quantity_milli ELSE 0 END),0) total
               FROM inventory_transactions WHERE item_id=? AND voided=0""", (item_id,)
        )["total"]
        borrowed = max(0, borrowed)
        available = max(0, item["registered_quantity_milli"] - borrowed)
        status = ("Available" if borrowed == 0 else
                  "Borrowed" if available == 0 else "Partially Borrowed")
        return {"on_hand_milli": item["registered_quantity_milli"],
                "borrowed_milli": borrowed, "available_milli": available, "status": status}

    def inventory_item_rows(self, project_id: int, include_inactive: bool = False) -> list[dict]:
        clause = "" if include_inactive else " AND active=1"
        rows = self.all(
            f"""SELECT * FROM inventory_items WHERE project_id=?{clause}
                ORDER BY material_type,name COLLATE NOCASE,item_code""", (project_id,)
        )
        result = []
        for row in rows:
            values = dict(row); values.update(self.inventory_item_balance(row["id"])); result.append(values)
        return result

    def active_inventory_loans(self, project_id: int) -> list[dict]:
        rows = self.all(
            """SELECT borrow.*,i.item_code,i.name item_name,i.unit,e.name employee,
                   e.employee_no,COALESCE(SUM(ret.quantity_milli),0) returned_milli
               FROM inventory_transactions borrow
               JOIN inventory_items i ON i.id=borrow.item_id
               JOIN employees e ON e.id=borrow.employee_id
               LEFT JOIN inventory_transactions ret ON ret.linked_transaction_id=borrow.id
                    AND ret.transaction_type='Return' AND ret.voided=0
               WHERE borrow.project_id=? AND borrow.transaction_type='Borrow' AND borrow.voided=0
               GROUP BY borrow.id HAVING borrow.quantity_milli-COALESCE(SUM(ret.quantity_milli),0)>0
               ORDER BY borrow.transaction_date,borrow.id""", (project_id,)
        )
        result = []
        for row in rows:
            values = dict(row)
            values["outstanding_milli"] = row["quantity_milli"] - row["returned_milli"]
            result.append(values)
        return result

    def register_inventory_item(self, *, project_id: int, name: str, material_type: str,
                                category: str, unit: str, opening_quantity_milli: int,
                                reorder_level_milli: int, condition_status: str,
                                notes: str, authorized_by_head_id: int,
                                registration_date: str) -> dict:
        if not self.project_is_active(project_id):
            raise ValueError("Inventory cannot be changed for a completed project.")
        if not name.strip() or not category.strip() or not unit.strip():
            raise ValueError("Item name, category and unit are required.")
        if material_type not in {"Consumable", "Non-Consumable"}:
            raise ValueError("Select Consumable or Non-Consumable.")
        if opening_quantity_milli <= 0:
            raise ValueError("Opening quantity must be greater than zero.")
        if material_type == "Non-Consumable" and opening_quantity_milli % 1000:
            raise ValueError("Non-consumable tools must use a whole-number quantity.")
        head = self.one(
            "SELECT id,name FROM project_heads WHERE id=? AND project_id=? AND active=1",
            (authorized_by_head_id, project_id),
        )
        if not head:
            raise ValueError("An active project head must authorize inventory registration.")
        registration_date = valid_date(registration_date, True)
        item_code = self.next_inventory_item_code(project_id)
        reference = self._next_system_reference(
            "STK", "inventory_transactions", "reference", registration_date
        )
        with self.conn:
            item_id = self.conn.execute(
                """INSERT INTO inventory_items(project_id,item_code,name,material_type,category,
                   unit,registered_quantity_milli,reorder_level_milli,condition_status,notes,
                   created_by_head_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (project_id,item_code,name.strip(),material_type,category.strip(),unit.strip(),
                 opening_quantity_milli,reorder_level_milli,condition_status.strip() or "Good",
                 notes.strip(),authorized_by_head_id),
            ).lastrowid
            self.conn.execute(
                """INSERT INTO inventory_transactions(reference,project_id,item_id,transaction_type,
                   quantity_milli,transaction_date,transaction_time,reason,condition_note,notes,
                   authorized_by_head_id) VALUES(?,?,?,'Initial Stock',?,?,?,?,?,?,?)""",
                (reference,project_id,item_id,opening_quantity_milli,registration_date,
                 local_timestamp(),"Inventory registration",condition_status.strip(),notes.strip(),
                 authorized_by_head_id),
            )
            self.conn.execute(
                "INSERT INTO audit_log(project_id,action,details) VALUES(?,?,?)",
                (project_id,"INVENTORY_ITEM_REGISTERED",
                 f"{item_code} {name.strip()} ({material_type}), {inventory_quantity(opening_quantity_milli)} {unit}; authorized by {head['name']}"),
            )
        return {"id": item_id, "item_code": item_code, "reference": reference}

    def record_inventory_movement(self, *, item_id: int, transaction_type: str,
                                  quantity_milli: int, transaction_date: str, reason: str,
                                  notes: str, authorized_by_head_id: int,
                                  employee_id: int | None = None,
                                  condition_note: str = "",
                                  linked_transaction_id: int | None = None) -> str:
        item = self.one("SELECT * FROM inventory_items WHERE id=? AND active=1", (item_id,))
        if not item:
            raise ValueError("Select an active inventory item.")
        project_id = item["project_id"]
        if not self.project_is_active(project_id):
            raise ValueError("Inventory cannot be changed for a completed project.")
        if transaction_type not in {"Restock", "Consume", "Borrow", "Return"}:
            raise ValueError("Select a valid inventory activity.")
        if quantity_milli <= 0:
            raise ValueError("Quantity must be greater than zero.")
        if item["material_type"] == "Non-Consumable" and quantity_milli % 1000:
            raise ValueError("Non-consumable tools must use a whole-number quantity.")
        if transaction_type in {"Restock", "Consume"} and item["material_type"] != "Consumable":
            raise ValueError("Restock and usage apply only to consumable materials.")
        if transaction_type in {"Borrow", "Return"} and item["material_type"] != "Non-Consumable":
            raise ValueError("Borrow and return apply only to non-consumable tools.")
        if not reason.strip():
            raise ValueError("Enter the purpose or reason for this inventory activity.")
        head = self.one(
            "SELECT id,name FROM project_heads WHERE id=? AND project_id=? AND active=1",
            (authorized_by_head_id, project_id),
        )
        if not head:
            raise ValueError("An active project head must authorize this inventory activity.")
        employee = None
        if transaction_type in {"Consume", "Borrow", "Return"}:
            employee = self.one(
                "SELECT id,name FROM employees WHERE id=? AND project_id=? AND active=1",
                (employee_id, project_id),
            )
            if not employee:
                raise ValueError("Select an active employee assigned to this project.")
        balance = self.inventory_item_balance(item_id)
        if transaction_type == "Consume" and quantity_milli > balance["on_hand_milli"]:
            raise ValueError(
                f"Only {inventory_quantity(balance['on_hand_milli'])} {item['unit']} is currently in stock."
            )
        if transaction_type == "Borrow" and quantity_milli > balance["available_milli"]:
            raise ValueError(
                f"Only {inventory_quantity(balance['available_milli'])} {item['unit']} is available to borrow."
            )
        if transaction_type == "Return":
            loan = self.one(
                """SELECT b.*,COALESCE(SUM(r.quantity_milli),0) returned_milli
                   FROM inventory_transactions b LEFT JOIN inventory_transactions r
                     ON r.linked_transaction_id=b.id AND r.transaction_type='Return' AND r.voided=0
                   WHERE b.id=? AND b.item_id=? AND b.employee_id=? AND b.transaction_type='Borrow'
                     AND b.voided=0 GROUP BY b.id""",
                (linked_transaction_id,item_id,employee_id),
            )
            if not loan:
                raise ValueError("Select an active borrowing record to return.")
            outstanding = loan["quantity_milli"] - loan["returned_milli"]
            if quantity_milli > outstanding:
                raise ValueError(
                    f"This borrowing record only has {inventory_quantity(outstanding)} {item['unit']} outstanding."
                )
        transaction_date = valid_date(transaction_date, True)
        prefix = {"Restock":"RST","Consume":"USE","Borrow":"BRW","Return":"RTN"}[transaction_type]
        reference = self._next_system_reference(
            prefix,"inventory_transactions","reference",transaction_date
        )
        with self.conn:
            self.conn.execute(
                """INSERT INTO inventory_transactions(reference,project_id,item_id,employee_id,
                   transaction_type,quantity_milli,transaction_date,transaction_time,reason,
                   condition_note,notes,linked_transaction_id,authorized_by_head_id)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (reference,project_id,item_id,employee_id,transaction_type,quantity_milli,
                 transaction_date,local_timestamp(),reason.strip(),condition_note.strip(),notes.strip(),
                 linked_transaction_id,authorized_by_head_id),
            )
            employee_text = f" by {employee['name']}" if employee else ""
            self.conn.execute(
                "INSERT INTO audit_log(project_id,action,details) VALUES(?,?,?)",
                (project_id,f"INVENTORY_{transaction_type.upper()}",
                 f"{reference} {item['item_code']} {inventory_quantity(quantity_milli)} {item['unit']}{employee_text}; {reason.strip()}; authorized by {head['name']}"),
            )
        return reference

    def close(self):
        self.conn.close()


def center_toplevel(window):
    """Center an ordinary dialog over its parent without disturbing full-screen windows."""
    try:
        if not window.winfo_exists() or window.attributes("-fullscreen"):
            return
        window.update_idletasks()
        width = max(window.winfo_width(), window.winfo_reqwidth())
        height = max(window.winfo_height(), window.winfo_reqheight())
        parent = window.master.winfo_toplevel() if window.master else None
        if parent and parent.winfo_exists() and parent.winfo_viewable():
            x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
            y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 2)
        else:
            x = max(0, (window.winfo_screenwidth() - width) // 2)
            y = max(0, (window.winfo_screenheight() - height) // 2)
        x = min(max(0, x), max(0, window.winfo_screenwidth() - width))
        y = min(max(0, y), max(0, window.winfo_screenheight() - height))
        window.geometry(f"+{x}+{y}")
    except tk.TclError:
        pass


class FormDialog(tk.Toplevel):
    def __init__(self, parent, title: str, fields: list[tuple], initial: dict | None = None,
                 required_keys=()):
        super().__init__(parent)
        self.title(title)
        two_columns = len(fields) >= 7
        self.resizable(two_columns, False)
        self.result = None
        self.vars = {}
        self.widgets = {}
        self.required_keys = tuple(required_keys)
        initial = initial or {}
        body = ttk.Frame(self, padding=20)
        body.grid(sticky="nsew")
        self.columnconfigure(0, weight=1)
        for index, spec in enumerate(fields):
            key, label = spec[0], spec[1]
            choices = spec[2] if len(spec) > 2 else None
            mode = spec[3] if len(spec) > 3 else None
            row = index // 2 if two_columns else index
            pair = index % 2 if two_columns else 0
            label_column, input_column = pair * 2, pair * 2 + 1
            display_label = label + (" *" if key in self.required_keys and not label.endswith("*") else "")
            ttk.Label(body, text=display_label).grid(
                row=row, column=label_column, sticky="w",
                padx=((0 if pair == 0 else 18), 8), pady=6,
            )
            var = tk.StringVar(value=str(initial.get(key, "")))
            self.vars[key] = var
            if mode == "display":
                widget = ttk.Label(body, textvariable=var, style="Section.TLabel")
            elif choices:
                widget = ttk.Combobox(body, textvariable=var, values=choices, state="readonly", width=31)
                if not var.get() and choices:
                    var.set(choices[0])
            else:
                widget = ttk.Entry(body, textvariable=var, width=34)
            widget.grid(row=row, column=input_column, sticky="ew", pady=6)
            body.columnconfigure(input_column, weight=1)
            self.widgets[key] = widget
        buttons = ttk.Frame(body)
        button_row = (len(fields) + 1) // 2 if two_columns else len(fields)
        buttons.grid(row=button_row, column=0, columnspan=4 if two_columns else 2,
                     sticky="e", pady=(16, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Save", command=self.save).pack(side="right")
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self.save())
        self.transient(parent)
        self.grab_set()
        self.wait_visibility()
        center_toplevel(self)
        self.focus_force()

    def save(self):
        if flash_missing_fields(self, self.vars, self.widgets, self.required_keys):
            return
        if flash_invalid_standard_fields(self, self.vars, self.widgets):
            return
        self.result = {key: var.get().strip() for key, var in self.vars.items()}
        self.destroy()


def dialog(parent, title, fields, initial=None, required_keys=()):
    win = FormDialog(parent, title, fields, initial, required_keys)
    parent.wait_window(win)
    return win.result


class HeadEditorDialog(tk.Toplevel):
    """Small reusable editor for a project head and their private approval PIN."""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Add Project Head")
        self.resizable(False, False)
        self.result = None
        self.vars = {key: tk.StringVar() for key in ("name", "position", "pin", "confirm")}
        self.widgets = {}
        body = ttk.Frame(self, padding=20); body.pack(fill="both", expand=True)
        ttk.Label(body, text="Project head", style="DialogTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        labels = [("name", "Full name", False), ("position", "Position", False),
                  ("pin", "Private PIN", True), ("confirm", "Confirm PIN", True)]
        for row, (key, label, secret) in enumerate(labels, 1):
            ttk.Label(body, text=label + " *").grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
            widget = ttk.Entry(body, textvariable=self.vars[key], show="*" if secret else "", width=34)
            widget.grid(row=row, column=1, pady=5); self.widgets[key] = widget
        ttk.Label(body, text="PINs are hashed and are never displayed again.", style="Muted.TLabel").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(6, 12))
        buttons = ttk.Frame(body); buttons.grid(row=6, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Cancel", style="Secondary.TButton", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Add Head", style="Primary.TButton", command=self.save).pack(side="right")
        self.transient(parent); self.grab_set(); self.bind("<Escape>", lambda _e: self.destroy())

    def save(self):
        values = {key: var.get().strip() for key, var in self.vars.items()}
        if flash_missing_fields(self, self.vars, self.widgets, ("name", "position", "pin", "confirm")):
            return
        if values["pin"] != values["confirm"]:
            flash_required_widgets(self, [self.widgets["pin"], self.widgets["confirm"]])
            messagebox.showerror(APP_TITLE, "The PIN confirmation does not match.", parent=self); return
        try:
            hash_pin(values["pin"])
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self); return
        self.result = {"name": values["name"], "position": values["position"], "pin": values["pin"]}
        self.destroy()


class ProjectHeadEditDialog(tk.Toplevel):
    """Secure registry editor that never exposes a stored PIN."""
    def __init__(self, parent, head):
        super().__init__(parent)
        self.title("Edit Project Head")
        self.resizable(False, False)
        self.result = None
        self.vars = {
            "name": tk.StringVar(value=head["name"]),
            "position": tk.StringVar(value=head["position"]),
            "current_pin": tk.StringVar(),
            "new_pin": tk.StringVar(),
            "confirm_pin": tk.StringVar(),
        }
        self.widgets = {}
        body = ttk.Frame(self, padding=22); body.pack(fill="both", expand=True)
        ttk.Label(body, text="Edit project head", style="DialogTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        ttk.Label(
            body,
            text="The current PIN confirms the change. Leave the new PIN blank to retain it.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 12))
        fields = (
            ("name", "Full name", False), ("position", "Position", False),
            ("current_pin", "Current PIN", True), ("new_pin", "New PIN", True),
            ("confirm_pin", "Confirm new PIN", True),
        )
        for row, (key, label, secret) in enumerate(fields, 2):
            required = key in {"name", "position", "current_pin"}
            ttk.Label(body, text=label + (" *" if required else "")).grid(
                row=row, column=0, sticky="w", padx=(0, 14), pady=5)
            widget = ttk.Entry(body, textvariable=self.vars[key], show="*" if secret else "", width=36)
            widget.grid(row=row, column=1, sticky="ew", pady=5); self.widgets[key] = widget
        buttons = ttk.Frame(body); buttons.grid(row=7, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Save Changes", style="Primary.TButton",
                   command=self.save).pack(side="right", padx=(0, 8))
        self.transient(parent); self.grab_set(); self.bind("<Escape>", lambda _e: self.destroy())

    def save(self):
        values = {key: var.get().strip() for key, var in self.vars.items()}
        if flash_missing_fields(self, self.vars, self.widgets, ("name", "position", "current_pin")):
            return
        if values["new_pin"] != values["confirm_pin"]:
            flash_required_widgets(self, [self.widgets["new_pin"], self.widgets["confirm_pin"]])
            messagebox.showerror(APP_TITLE, "The new PIN confirmation does not match.", parent=self)
            return
        if values["new_pin"]:
            try:
                hash_pin(values["new_pin"])
            except ValueError as exc:
                messagebox.showerror(APP_TITLE, str(exc), parent=self)
                return
        self.result = values
        self.destroy()


class HeadRegistryDialog(tk.Toplevel):
    """Global reusable project-head directory."""
    def __init__(self, parent, db):
        super().__init__(parent)
        self.title("Project Head Registry")
        self.geometry("680x470")
        self.minsize(560, 390)
        self.db = db
        body = ttk.Frame(self, padding=20); body.pack(fill="both", expand=True)
        ttk.Label(body, text="Registered project heads", style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(
            body,
            text="Register heads once, then assign them to one or more projects. "
                 "The current default PIN is 0000.",
            style="Muted.TLabel", wraplength=620,
        ).pack(anchor="w", pady=(2, 12))
        bar = ttk.Frame(body); bar.pack(fill="x", pady=(0, 8))
        ttk.Button(
            bar, text="+ Add Project Head", style="Primary.TButton", command=self.add
        ).pack(side="left")
        ttk.Button(
            bar, text="Edit Project Head", style="Secondary.TButton", command=self.edit
        ).pack(side="left", padx=(6, 0))
        ttk.Label(
            bar, text="PINs are stored as hashes.", style="Muted.TLabel"
        ).pack(side="right")
        self.tree = ttk.Treeview(
            body, columns=("name", "position", "pin"), show="headings", height=12
        )
        self.tree.heading("name", text="NAME")
        self.tree.heading("position", text="POSITION")
        self.tree.heading("pin", text="DEFAULT PIN")
        self.tree.column("name", width=260, stretch=True)
        self.tree.column("position", width=230, stretch=True)
        self.tree.column("pin", width=105, anchor="center", stretch=False)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda _event: self.edit())
        ttk.Button(
            body, text="Done", style="Primary.TButton", command=self.destroy
        ).pack(anchor="e", pady=(12, 0))
        self.refresh()
        self.transient(parent); self.grab_set(); self.bind("<Escape>", lambda _e: self.destroy())

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for head in self.db.registered_heads():
            self.tree.insert(
                "", "end", iid=head["id"], values=(head["name"], head["position"], "0000")
            )

    def add(self):
        values = dialog(
            self, "Add Project Head",
            [("name", "Full name"), ("position", "Position")],
            required_keys=("name", "position"),
        )
        if not values:
            return
        try:
            self.db.add_registered_head(values["name"], values["position"])
            self.refresh()
            messagebox.showinfo(
                APP_TITLE,
                f"{values['name'].strip()} was registered with the default PIN 0000.",
                parent=self,
            )
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)

    def edit(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo(APP_TITLE, "Select a project head to edit.", parent=self)
            return
        head = self.db.one("SELECT * FROM head_registry WHERE id=?", (int(selected[0]),))
        if not head:
            return
        win = ProjectHeadEditDialog(self, head)
        self.wait_window(win)
        if not win.result:
            return
        values = win.result
        try:
            self.db.update_registered_head(
                head["id"], values["name"], values["position"],
                values["current_pin"], values["new_pin"],
            )
            self.refresh()
            messagebox.showinfo(
                APP_TITLE,
                f"{values['name']} was updated across every assigned project.",
                parent=self,
            )
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)


class DatePickerPopup(tk.Toplevel):
    """Calendar with scrollable year, month and day controls.

    The spin controls make distant dates such as employee birthdays practical,
    while the calendar grid remains convenient for ordinary transaction dates.
    """
    def __init__(self, parent, target_var, year_min=1900, year_max=2100):
        super().__init__(parent)
        self.target_var = target_var
        self.year_min = int(year_min)
        self.year_max = int(year_max)
        self.title("Pick a date")
        self.resizable(False, False)
        self.current_year = date.today().year
        self.current_month = date.today().month
        initial = target_var.get().strip()
        if initial:
            try:
                parsed = date.fromisoformat(initial)
                self.current_year = parsed.year
                self.current_month = parsed.month
            except ValueError:
                pass
        selectors = ttk.LabelFrame(self, text="Scroll or type a date", padding=10)
        selectors.pack(fill="x", padx=10, pady=(10, 4))
        self.year_var = tk.IntVar(value=self.current_year)
        self.month_var = tk.StringVar(value=calendar.month_name[self.current_month])
        self.day_var = tk.IntVar(value=parsed.day if initial and 'parsed' in locals() else 1)
        ttk.Label(selectors, text="Year").grid(row=0, column=0, sticky="w")
        ttk.Label(selectors, text="Month").grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Label(selectors, text="Day").grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.year_spin = ttk.Spinbox(
            selectors, from_=self.year_min, to=self.year_max,
            textvariable=self.year_var, width=8, wrap=False, command=self.selector_changed)
        self.month_combo = ttk.Combobox(
            selectors, textvariable=self.month_var,
            values=list(calendar.month_name)[1:], state="readonly", width=12)
        self.day_spin = ttk.Spinbox(
            selectors, from_=1, to=31, textvariable=self.day_var,
            width=6, wrap=True)
        self.year_spin.grid(row=1, column=0, sticky="ew")
        self.month_combo.grid(row=1, column=1, sticky="ew", padx=(8, 0))
        self.day_spin.grid(row=1, column=2, sticky="ew", padx=(8, 0))
        ttk.Button(selectors, text="Use selected date", style="Primary.TButton",
                   command=self.select_from_controls).grid(row=1, column=3, padx=(10, 0))
        self.month_combo.bind("<<ComboboxSelected>>", self.selector_changed)
        self.year_spin.bind("<Return>", self.selector_changed)
        self.year_spin.bind("<FocusOut>", self.selector_changed)

        self.header = ttk.Frame(self, padding=(10, 6, 10, 6)); self.header.pack(fill="x")
        self.prev_month = ttk.Button(
            self.header, text="<", command=lambda: self.shift_month(-1), width=3)
        self.prev_month.pack(side="left")
        self.month_label = ttk.Label(self.header, text="", font=("Segoe UI", 10, "bold"))
        self.month_label.pack(side="left", expand=True)
        self.next_month = ttk.Button(
            self.header, text=">", command=lambda: self.shift_month(1), width=3)
        self.next_month.pack(side="right")
        self.days_frame = ttk.Frame(self, padding=(10, 0, 10, 10)); self.days_frame.pack()
        self.day_buttons = []
        self.render_calendar()
        self.transient(parent); self.grab_set(); self.bind("<Escape>", lambda _e: self.destroy())

    def shift_month(self, direction):
        self.current_month += direction
        if self.current_month > 12:
            self.current_month = 1; self.current_year += 1
        if self.current_month < 1:
            self.current_month = 12; self.current_year -= 1
        self.current_year = min(self.year_max, max(self.year_min, self.current_year))
        self.year_var.set(self.current_year)
        self.month_var.set(calendar.month_name[self.current_month])
        self.render_calendar()

    def selector_changed(self, _event=None):
        try:
            selected_year = int(self.year_var.get())
            selected_month = list(calendar.month_name).index(self.month_var.get())
        except (ValueError, tk.TclError):
            return
        if not 1 <= selected_month <= 12:
            return
        self.current_year = min(self.year_max, max(self.year_min, selected_year))
        self.current_month = selected_month
        self.year_var.set(self.current_year)
        self.render_calendar()

    def select_from_controls(self):
        try:
            selected = date(int(self.year_var.get()),
                            list(calendar.month_name).index(self.month_var.get()),
                            int(self.day_var.get()))
        except (ValueError, tk.TclError):
            messagebox.showerror(APP_TITLE, "Select a valid year, month and day.", parent=self)
            return
        if not self.year_min <= selected.year <= self.year_max:
            messagebox.showerror(
                APP_TITLE,
                f"Year must be between {self.year_min} and {self.year_max}.",
                parent=self,
            )
            return
        self.select(selected.isoformat())

    def render_calendar(self):
        self.month_label.config(text=f"{calendar.month_name[self.current_month]} {self.current_year}")
        for child in self.days_frame.winfo_children():
            child.destroy()
        for col, name in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
            ttk.Label(self.days_frame, text=name, width=3).grid(row=0, column=col, padx=2, pady=2)
        self.day_buttons = []
        for row in range(1, 7):
            for col in range(7):
                btn = tk.Button(self.days_frame, text="", width=3, height=1, bg="#F3F4F6", fg="#111827",
                                bd=1, relief="solid", command=lambda: None)
                btn.grid(row=row, column=col, padx=2, pady=2)
                self.day_buttons.append(btn)
        month_days = calendar.monthcalendar(self.current_year, self.current_month)
        idx = 0
        for week in month_days:
            for col, day in enumerate(week):
                button = self.day_buttons[idx]
                if day == 0:
                    button.config(text="", state="disabled", bg="#F9FAFB", command=lambda: None)
                else:
                    date_value = date(self.current_year, self.current_month, day)
                    button.config(text=str(day), state="normal", bg="#FFFFFF",
                                  command=lambda value=date_value.isoformat(): self.select(value))
                idx += 1
        self.days_frame.update_idletasks()

    def select(self, value: str):
        self.target_var.set(value)
        self.destroy()


class ProjectDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Create New Project")
        self.geometry("760x610")
        self.minsize(700, 560)
        self.result = None
        self.db = parent.db
        self.head_ids = []
        self.registry_lookup = {}
        self.vars = {key: tk.StringVar() for key in
                     ("name", "client", "contract_value", "start_date", "target_date", "address", "notes")}
        self.widgets = {}
        self.vars["start_date"].set(date.today().isoformat())
        body = ttk.Frame(self, padding=22); body.pack(fill="both", expand=True)
        ttk.Label(body, text="Create a new project", style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(body, text="Select registered project heads to authorize protected financial activity.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 14))
        fields = ttk.Frame(body); fields.pack(fill="x")
        specs = [("name", "Project name"), ("client", "Client"),
                 ("contract_value", "Contract value"), ("start_date", "Start date (YYYY-MM-DD)"),
                 ("target_date", "Target date (YYYY-MM-DD)"), ("address", "Project address"),
                 ("notes", "Notes")]
        for index, (key, label) in enumerate(specs):
            row, col = divmod(index, 2)
            cell = ttk.Frame(fields); cell.grid(row=row, column=col, sticky="ew", padx=(0 if col == 0 else 8, 8 if col == 0 else 0), pady=5)
            ttk.Label(cell, text=label + (" *" if key == "name" else "")).pack(anchor="w")
            entry_frame = ttk.Frame(cell); entry_frame.pack(fill="x", pady=(3, 0))
            widget = ttk.Entry(entry_frame, textvariable=self.vars[key])
            widget.pack(side="left", fill="x", expand=True); self.widgets[key] = widget
            if key in {"start_date", "target_date"}:
                ttk.Button(entry_frame, text="📅", width=3, command=lambda current=self.vars[key]: self.open_date_picker(current)).pack(side="right", padx=(6, 0))
        fields.columnconfigure(0, weight=1); fields.columnconfigure(1, weight=1)
        headbar = ttk.Frame(body); headbar.pack(fill="x", pady=(18, 6))
        ttk.Label(headbar, text="Project heads", style="Section.TLabel").pack(side="left")
        ttk.Button(headbar, text="Create This Project", style="Primary.TButton", command=self.save, width=18).pack(side="right", padx=(6, 0))
        selector = ttk.Frame(body); selector.pack(fill="x", pady=(0, 6))
        self.head_var = tk.StringVar()
        self.head_combo = ttk.Combobox(
            selector, textvariable=self.head_var, state="readonly", width=44
        )
        self.head_combo.pack(side="left", fill="x", expand=True)
        ttk.Button(
            selector, text="+ Assign Selected", style="Primary.TButton", command=self.add_head
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            selector, text="Remove", style="Secondary.TButton", command=self.remove_head
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            selector, text="Head Registry", style="Secondary.TButton", command=self.open_registry
        ).pack(side="left", padx=(6, 0))
        self.tree = ttk.Treeview(body, columns=("name", "position"), show="headings", height=7)
        self.tree.heading("name", text="NAME"); self.tree.heading("position", text="POSITION")
        self.tree.column("name", width=280); self.tree.column("position", width=260)
        self.tree.pack(fill="both", expand=True)
        self.refresh_registry()
        self.transient(parent); self.grab_set(); self.bind("<Escape>", lambda _e: self.destroy())

    def open_date_picker(self, target_var):
        DatePickerPopup(self, target_var)

    def add_head(self):
        registry_id = self.registry_lookup.get(self.head_var.get())
        if not registry_id:
            messagebox.showinfo(
                APP_TITLE, "Select a registered project head first.", parent=self
            )
            return
        if registry_id not in self.head_ids:
            self.head_ids.append(registry_id)
            self.refresh_heads()

    def remove_head(self):
        selected = self.tree.selection()
        if selected:
            self.head_ids.remove(int(selected[0])); self.refresh_heads()

    def open_registry(self):
        win = HeadRegistryDialog(self, self.db); self.wait_window(win)
        self.refresh_registry()

    def refresh_registry(self):
        rows = self.db.registered_heads()
        self.registry_lookup = {
            f"{row['name']} — {row['position']}": row["id"] for row in rows
        }
        self.head_combo.configure(values=list(self.registry_lookup))
        if self.head_var.get() not in self.registry_lookup:
            self.head_var.set(next(iter(self.registry_lookup), ""))

    def refresh_heads(self):
        self.tree.delete(*self.tree.get_children())
        rows = {row["id"]: row for row in self.db.registered_heads()}
        self.head_ids = [head_id for head_id in self.head_ids if head_id in rows]
        for head_id in self.head_ids:
            head = rows[head_id]
            self.tree.insert("", "end", iid=str(head_id), values=(head["name"], head["position"]))

    def save(self):
        values = {key: var.get().strip() for key, var in self.vars.items()}
        if flash_missing_fields(self, self.vars, self.widgets, ("name",)):
            return
        try:
            cents(values["contract_value"])
            valid_date(values["start_date"]); valid_date(values["target_date"])
            if not self.head_ids: raise ValueError("Select at least one registered project head.")
        except ValueError as exc:
            message = str(exc).lower()
            if "date" in message:
                flash_required_widgets(self, [self.widgets["start_date"], self.widgets["target_date"]])
            elif "number" in message or "amount" in message:
                flash_required_widgets(self, [self.widgets["contract_value"]])
            messagebox.showerror(APP_TITLE, str(exc), parent=self); return
        values["head_ids"] = list(self.head_ids); self.result = values; self.destroy()


class HeadAuthorizationDialog(tk.Toplevel):
    def __init__(self, parent, heads, action: str, details: str):
        super().__init__(parent)
        self.title("Project Head Authorization")
        self.resizable(False, False)
        self.result = None
        self.heads = {f"{row['name']} — {row['position']}": row for row in heads}
        self.head_var = tk.StringVar(value=next(iter(self.heads), "")); self.pin_var = tk.StringVar()
        body = ttk.Frame(self, padding=22); body.pack(fill="both", expand=True)
        ttk.Label(body, text="Confirm protected action", style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(body, text=action, style="Section.TLabel").pack(anchor="w", pady=(8, 2))
        ttk.Label(body, text=details, wraplength=430, style="Muted.TLabel").pack(anchor="w", pady=(0, 14))
        ttk.Label(body, text="Authorizing project head").pack(anchor="w")
        ttk.Combobox(body, textvariable=self.head_var, values=list(self.heads), state="readonly", width=48).pack(fill="x", pady=(3, 10))
        ttk.Label(body, text="Private PIN").pack(anchor="w")
        entry = ttk.Entry(body, textvariable=self.pin_var, show="*", width=48); entry.pack(fill="x", pady=(3, 14)); entry.focus_set()
        footer = ttk.Frame(body); footer.pack(fill="x")
        ttk.Button(footer, text="Cancel", style="Secondary.TButton", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="Authorize & Continue", style="Primary.TButton", command=self.authorize).pack(side="right")
        self.transient(parent); self.grab_set(); self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self.authorize())

    def authorize(self):
        head = self.heads.get(self.head_var.get())
        if head and verify_pin(self.pin_var.get(), head["pin_salt"], head["pin_hash"]):
            self.result = head; self.destroy(); return
        self.pin_var.set("")
        messagebox.showerror(APP_TITLE, "Incorrect project-head PIN.", parent=self)


class TwoHeadAuthorizationDialog(tk.Toplevel):
    """Requires two different project heads and records both authenticated identities."""
    def __init__(self, parent, heads, action: str, details: str,
                 role_one="Issuer / approver", role_two="Receiver / reviewer", head_ids=None):
        super().__init__(parent)
        self.title("Two-Head Authorization")
        self.resizable(False, False)
        self.result = None
        self.heads = {row["id"]: row for row in heads}
        labels = {row["id"]: f"{row['name']} - {row['position']}" for row in heads}
        self.label_to_id = {label: head_id for head_id, label in labels.items()}
        ids = list(self.heads)
        fixed = list(head_ids or [])
        first_id = fixed[0] if len(fixed) > 0 else (ids[0] if ids else None)
        second_id = fixed[1] if len(fixed) > 1 else (ids[1] if len(ids) > 1 else first_id)
        self.first_var = tk.StringVar(value=labels.get(first_id, ""))
        self.second_var = tk.StringVar(value=labels.get(second_id, ""))
        self.first_pin = tk.StringVar(); self.second_pin = tk.StringVar()
        body = ttk.Frame(self, padding=22); body.pack(fill="both", expand=True)
        ttk.Label(body, text="Two-person approval required", style="DialogTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(body, text=action, style="Section.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(8, 2))
        ttk.Label(body, text=details, wraplength=520, style="Muted.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(0, 14))
        values = list(self.label_to_id)
        for row_no, role, person_var, pin_var in (
            (3, role_one, self.first_var, self.first_pin),
            (5, role_two, self.second_var, self.second_pin),
        ):
            ttk.Label(body, text=role).grid(row=row_no, column=0, sticky="w", padx=(0, 12), pady=4)
            combo = ttk.Combobox(body, textvariable=person_var, values=values,
                                 state="disabled" if head_ids else "readonly", width=44)
            combo.grid(row=row_no, column=1, sticky="ew", pady=4)
            ttk.Label(body, text="Private PIN").grid(row=row_no + 1, column=0, sticky="w", padx=(0, 12), pady=4)
            ttk.Entry(body, textvariable=pin_var, show="*", width=28).grid(
                row=row_no + 1, column=1, sticky="ew", pady=4)
        footer = ttk.Frame(body); footer.grid(row=7, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(footer, text="Cancel", style="Secondary.TButton", command=self.destroy).pack(
            side="right", padx=(8, 0))
        ttk.Button(footer, text="Verify Both & Continue", style="Primary.TButton",
                   command=self.authorize).pack(side="right")
        self.transient(parent); self.grab_set(); self.bind("<Escape>", lambda _e: self.destroy())
        self.after_idle(lambda: center_toplevel(self))

    def authorize(self):
        first_id = self.label_to_id.get(self.first_var.get())
        second_id = self.label_to_id.get(self.second_var.get())
        if not first_id or not second_id:
            messagebox.showerror(APP_TITLE, "Select both project heads.", parent=self); return
        if first_id == second_id:
            messagebox.showerror(APP_TITLE, "Two different project heads are required.", parent=self); return
        first, second = self.heads[first_id], self.heads[second_id]
        if not verify_pin(self.first_pin.get(), first["pin_salt"], first["pin_hash"]):
            self.first_pin.set("")
            messagebox.showerror(APP_TITLE, f"Incorrect PIN for {first['name']}.", parent=self); return
        if not verify_pin(self.second_pin.get(), second["pin_salt"], second["pin_hash"]):
            self.second_pin.set("")
            messagebox.showerror(APP_TITLE, f"Incorrect PIN for {second['name']}.", parent=self); return
        self.result = [first, second]
        self.destroy()


class AllHeadsAuthorizationDialog(tk.Toplevel):
    """Requires a valid PIN from every active head on the selected project."""
    def __init__(self, parent, heads, action: str, details: str):
        super().__init__(parent)
        self.title("All Project Heads Approval")
        self.resizable(False, False)
        self.result = None
        self.heads = list(heads)
        self.pin_vars = {row["id"]: tk.StringVar() for row in self.heads}
        body = ttk.Frame(self, padding=22); body.pack(fill="both", expand=True)
        ttk.Label(body, text="All-head approval required", style="DialogTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(body, text=action, style="Section.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(8, 2))
        ttk.Label(body, text=details, wraplength=480, style="Muted.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(0, 14))
        for index, head in enumerate(self.heads, 3):
            ttk.Label(body, text=f"{head['name']} — {head['position']}").grid(
                row=index, column=0, sticky="w", padx=(0, 16), pady=5)
            ttk.Entry(body, textvariable=self.pin_vars[head["id"]], show="*", width=24).grid(
                row=index, column=1, sticky="ew", pady=5)
        footer = ttk.Frame(body); footer.grid(
            row=3 + len(self.heads), column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(footer, text="Cancel", style="Secondary.TButton", command=self.destroy).pack(
            side="right", padx=(8, 0))
        ttk.Button(footer, text="Verify All & Continue", style="Primary.TButton",
                   command=self.authorize).pack(side="right")
        self.transient(parent); self.grab_set(); self.bind("<Escape>", lambda _e: self.destroy())

    def authorize(self):
        invalid = [head["name"] for head in self.heads if not verify_pin(
            self.pin_vars[head["id"]].get(), head["pin_salt"], head["pin_hash"]
        )]
        if invalid:
            for var in self.pin_vars.values(): var.set("")
            messagebox.showerror(
                APP_TITLE, "Approval failed. Every listed project head must enter their correct PIN.", parent=self
            )
            return
        self.result = self.heads
        self.destroy()


class SearchableCombobox(ttk.Combobox):
    """Editable combobox that narrows its dropdown while the user types."""
    def __init__(self, parent, values=(), **kwargs):
        self.source_values = list(values)
        super().__init__(parent, values=self.source_values, **kwargs)
        self.bind("<KeyRelease>", self._filter_values, add="+")

    def set_source(self, values):
        self.source_values = list(values)
        self.configure(values=self.source_values)

    def _filter_values(self, event=None):
        if event and event.keysym in {"Up", "Down", "Left", "Right", "Return", "Escape", "Tab"}:
            return
        term = self.get().strip().lower()
        matches = [value for value in self.source_values if term in value.lower()]
        self.configure(values=matches or self.source_values)


class ManageHeadsDialog(tk.Toplevel):
    def __init__(self, parent, db, project_id):
        super().__init__(parent)
        self.title("Manage Project Heads"); self.geometry("700x440")
        self.db, self.project_id = db, project_id
        self.registry_lookup = {}
        body = ttk.Frame(self, padding=20); body.pack(fill="both", expand=True)
        ttk.Label(body, text="Project heads", style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(body, text="Assign registered heads who can authorize expenses, remittances and payroll commitments.", style="Muted.TLabel").pack(anchor="w", pady=(2, 12))
        bar = ttk.Frame(body); bar.pack(fill="x")
        self.registry_var = tk.StringVar()
        self.registry_combo = ttk.Combobox(
            bar, textvariable=self.registry_var, state="readonly", width=36
        )
        self.registry_combo.pack(side="left", fill="x", expand=True)
        ttk.Button(bar, text="+ Assign", style="Primary.TButton", command=self.add).pack(side="left", padx=6)
        ttk.Button(bar, text="Head Registry", style="Secondary.TButton", command=self.open_registry).pack(side="left")
        ttk.Button(bar, text="Edit Head", style="Secondary.TButton", command=self.edit).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Remove", style="Secondary.TButton", command=self.remove).pack(side="left", padx=(6, 0))
        self.tree = ttk.Treeview(body, columns=("name", "position"), show="headings")
        self.tree.heading("name", text="NAME"); self.tree.heading("position", text="POSITION")
        self.tree.pack(fill="both", expand=True, pady=10)
        self.tree.bind("<Double-1>", lambda _event: self.edit())
        ttk.Button(body, text="Done", style="Primary.TButton", command=self.destroy).pack(anchor="e")
        self.refresh_registry(); self.refresh(); self.transient(parent); self.grab_set()

    def refresh_registry(self):
        self.registry_lookup = {
            f"{row['name']} — {row['position']}": row["id"]
            for row in self.db.registered_heads()
        }
        self.registry_combo.configure(values=list(self.registry_lookup))
        if self.registry_var.get() not in self.registry_lookup:
            self.registry_var.set(next(iter(self.registry_lookup), ""))

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for row in self.db.all("SELECT * FROM project_heads WHERE project_id=? AND active=1 ORDER BY name", (self.project_id,)):
            self.tree.insert("", "end", iid=row["id"], values=(row["name"], row["position"]))

    def add(self):
        registry_id = self.registry_lookup.get(self.registry_var.get())
        if not registry_id:
            messagebox.showinfo(APP_TITLE, "Register or select a project head first.", parent=self)
            return
        try:
            self.db.assign_registered_heads(self.project_id, [registry_id])
            self.refresh()
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)

    def open_registry(self):
        win = HeadRegistryDialog(self, self.db); self.wait_window(win)
        self.refresh_registry()

    def edit(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo(APP_TITLE, "Select a project head to edit.", parent=self); return
        project_head = self.db.one("SELECT * FROM project_heads WHERE id=?", (int(selected[0]),))
        if not project_head or not project_head["registry_head_id"]:
            messagebox.showerror(APP_TITLE, "This head is not linked to the shared registry.", parent=self); return
        head = self.db.one("SELECT * FROM head_registry WHERE id=?", (project_head["registry_head_id"],))
        win = ProjectHeadEditDialog(self, head); self.wait_window(win)
        if not win.result: return
        values = win.result
        try:
            self.db.update_registered_head(
                head["id"], values["name"], values["position"],
                values["current_pin"], values["new_pin"])
            self.refresh_registry(); self.refresh()
            messagebox.showinfo(APP_TITLE, "Project-head details were updated.", parent=self)
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)

    def remove(self):
        selected = self.tree.selection()
        count = self.db.one("SELECT COUNT(*) n FROM project_heads WHERE project_id=? AND active=1", (self.project_id,))["n"]
        if not selected: return
        if count <= 1:
            messagebox.showerror(APP_TITLE, "A project must keep at least one active head.", parent=self); return
        head = self.db.one("SELECT * FROM project_heads WHERE id=?", (int(selected[0]),))
        if not head:
            return
        pin = simpledialog.askstring(
            "Confirm Project-Head Removal",
            f"{head['name']} must enter their private PIN to be unassigned from this project:",
            parent=self, show="*",
        )
        if pin is None:
            return
        if not verify_pin(pin, head["pin_salt"], head["pin_hash"]):
            messagebox.showerror(APP_TITLE, "PIN verification failed. The project head was not removed.", parent=self)
            return
        if messagebox.askyesno(
            APP_TITLE,
            f"Unassign {head['name']} from this project?\n\nTheir global registry and shared petty-cash history remain intact.",
            parent=self,
        ):
            self.db.execute("UPDATE project_heads SET active=0 WHERE id=?", (head["id"],))
            self.db.audit(self.project_id, "PROJECT_HEAD_UNASSIGNED", head["name"])
            self.refresh()


class BaseTab(ttk.Frame):
    def __init__(self, app):
        super().__init__(app.notebook, padding=10)
        self.app = app
        self.db = app.db

    @property
    def project_id(self):
        return self.app.project_id

    def require_project(self):
        if not self.project_id:
            messagebox.showinfo(APP_TITLE, "Create or select a project first.")
            return False
        if not self.db.project_is_active(self.project_id):
            messagebox.showinfo(
                APP_TITLE,
                "This project is completed and read-only. Open Completed Projects to review its records."
            )
            return False
        return True

    def selected_id(self, tree):
        selected = tree.selection()
        if not selected:
            messagebox.showinfo(APP_TITLE, "Select a record first.")
            return None
        return int(selected[0])


class LedgerTree(ttk.Treeview):
    """Treeview with a 20-row preview and an in-place full-ledger toggle."""
    def __init__(self, parent, *args, row_limit=20, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.row_limit = row_limit
        self.showing_all = False
        self._records = []
        self._serial = 0
        self._rendering = False
        self.limit_label = None
        self.limit_button = None
        self.full_ledger_callback = None

    def attach_limiter(self, label, button):
        self.limit_label, self.limit_button = label, button
        self._update_limiter()

    def insert(self, parent, index, iid=None, **kwargs):
        if self._rendering:
            return super().insert(parent, index, iid=iid, **kwargs)
        self._serial += 1
        record_iid = str(iid) if iid is not None else f"ledger-row-{self._serial}"
        self._records.append((str(parent), record_iid, dict(kwargs)))
        if self.showing_all or len(self._records) <= self.row_limit:
            super().insert(parent, "end", iid=record_iid, **kwargs)
        self._update_limiter()
        return record_iid

    def delete(self, *items):
        if self._rendering:
            return super().delete(*items)
        visible = {str(item) for item in super().get_children("")}
        requested = {str(item) for item in items}
        if not items or (visible and requested == visible):
            self._records.clear()
            if visible:
                super().delete(*visible)
        else:
            self._records = [record for record in self._records if record[1] not in requested]
            existing = [item for item in requested if super().exists(item)]
            if existing:
                super().delete(*existing)
            self._render_records()
        self.showing_all = False
        self._update_limiter()

    def toggle_full_ledger(self):
        if len(self._records) <= self.row_limit:
            return
        self.showing_all = not self.showing_all
        self._render_records()
        if self.full_ledger_callback:
            self.full_ledger_callback()

    def _render_records(self):
        self._rendering = True
        try:
            visible = super().get_children("")
            if visible:
                super().delete(*visible)
            records = self._records if self.showing_all else self._records[:self.row_limit]
            for parent, iid, kwargs in records:
                super().insert(parent, "end", iid=iid, **kwargs)
        finally:
            self._rendering = False
        self._update_limiter()

    def _update_limiter(self):
        if not self.limit_label or not self.limit_button:
            return
        total = len(self._records)
        visible = total if self.showing_all else min(total, self.row_limit)
        self.limit_label.config(text=f"Showing {visible} of {total} entries")
        self.limit_button.config(
            text="Show first 20" if self.showing_all else f"See full ledger ({total})",
            state="normal" if total > self.row_limit else "disabled",
        )

    def open_expanded_ledger(self):
        """Open every stored row in a large, resizable ledger window."""
        window = tk.Toplevel(self)
        window.title("Expanded ledger")
        screen_width, screen_height = window.winfo_screenwidth(), window.winfo_screenheight()
        width = max(900, min(1450, screen_width - 90))
        height = max(620, min(900, screen_height - 110))
        window.geometry(f"{width}x{height}")
        window.minsize(780, 520)
        body = ttk.Frame(window, padding=14)
        body.pack(fill="both", expand=True)

        header = ttk.Frame(body)
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="Expanded ledger", style="DialogTitle.TLabel").pack(side="left")
        count = ttk.Label(header, style="Muted.TLabel")
        count.pack(side="right")
        search_var = tk.StringVar()
        search_row = ttk.Frame(body)
        search_row.pack(fill="x", pady=(0, 8))
        ttk.Label(search_row, text="Search this ledger").pack(side="left")
        search_entry = ttk.Entry(search_row, textvariable=search_var)
        search_entry.pack(side="left", fill="x", expand=True, padx=(8, 0))

        table = ttk.Frame(body)
        table.pack(fill="both", expand=True)
        columns = tuple(self["columns"])
        expanded = ttk.Treeview(table, columns=columns, show=self["show"], selectmode="browse")
        for key in columns:
            heading = self.heading(key)
            column = self.column(key)
            expanded.heading(key, text=heading.get("text", key))
            expanded.column(
                key, width=max(70, int(column.get("width", 100))),
                minwidth=max(55, int(column.get("minwidth", 55))),
                anchor=column.get("anchor", "w"), stretch=True,
            )
        record_tags = set()
        for _parent, _iid, kwargs in self._records:
            tags = kwargs.get("tags", ())
            if isinstance(tags, str):
                tags = (tags,)
            record_tags.update(tags)
        for tag in record_tags:
            options = self.tag_configure(tag)
            options = {key: value for key, value in options.items() if value not in (None, "")}
            if options:
                expanded.tag_configure(tag, **options)
        scroll_y = ttk.Scrollbar(table, orient="vertical", command=expanded.yview)
        scroll_x = ttk.Scrollbar(table, orient="horizontal", command=expanded.xview)
        expanded.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        expanded.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)

        def render(*_args):
            expanded.delete(*expanded.get_children())
            term = search_var.get().strip().lower()
            visible = 0
            for _parent, iid, kwargs in self._records:
                values = kwargs.get("values", ())
                if term and term not in " ".join(str(value) for value in values).lower():
                    continue
                safe_iid = iid if not expanded.exists(iid) else f"expanded-{visible}-{iid}"
                expanded.insert("", "end", iid=safe_iid, **kwargs)
                visible += 1
            count.config(text=f"Showing {visible} of {len(self._records)} entries")

        search_var.trace_add("write", render)
        footer = ttk.Frame(body)
        footer.pack(fill="x", pady=(10, 0))
        ttk.Label(footer, text="Resize the window or drag column dividers as needed.", style="Muted.TLabel").pack(side="left")
        ttk.Button(footer, text="Close", command=window.destroy).pack(side="right")
        render()
        search_entry.focus_set()
        window.transient(self.winfo_toplevel())
        window.bind("<Escape>", lambda _event: window.destroy())
        return window


class ProjectChecklist(ttk.Frame):
    """Compact checkbox dropdown for dashboard multi-project filtering."""
    def __init__(self, parent, command=None):
        super().__init__(parent)
        self.command = command
        self.projects = {}
        self.variables = {}
        self.label_var = tk.StringVar(value="All projects")
        self.button = tk.Menubutton(
            self, textvariable=self.label_var, relief="solid", bd=1,
            bg=WHITE, fg=INK, padx=10, pady=5, anchor="w",
        )
        self.menu = tk.Menu(self.button, tearoff=False)
        self.button.configure(menu=self.menu)
        self.button.pack(fill="x", expand=True)

    def set_projects(self, rows):
        previous = self.selected_ids()
        first_load = not self.projects
        previously_all = bool(self.projects) and len(previous) == len(self.projects)
        self.projects = {row["id"]: row["name"] for row in rows}
        self.variables = {}
        self.menu.delete(0, "end")
        self.menu.add_command(label="Select all", command=lambda: self._set_all(True))
        self.menu.add_command(label="Clear selection", command=lambda: self._set_all(False))
        self.menu.add_separator()
        for project_id, name in self.projects.items():
            selected = first_load or previously_all or project_id in previous
            variable = tk.BooleanVar(value=selected)
            self.variables[project_id] = variable
            self.menu.add_checkbutton(
                label=name, variable=variable, command=self._changed,
            )
        self._update_label()

    def selected_ids(self):
        return [project_id for project_id, variable in self.variables.items() if variable.get()]

    def _set_all(self, selected):
        for variable in self.variables.values():
            variable.set(selected)
        self._changed()

    def _changed(self):
        self._update_label()
        if self.command:
            self.command()

    def _update_label(self):
        selected = self.selected_ids()
        if not selected:
            text = "No projects selected"
        elif len(selected) == len(self.projects):
            text = f"All projects ({len(selected)})"
        elif len(selected) == 1:
            text = self.projects[selected[0]]
        else:
            text = f"{len(selected)} projects selected"
        self.label_var.set(text)

    def display_text(self):
        return self.label_var.get()


class DynamicChecklist(ttk.Frame):
    """Reusable checkbox dropdown whose values can be refreshed from SQLite."""
    def __init__(self, parent, all_label, none_label, plural_label, command=None, width=0):
        super().__init__(parent)
        self.command = command
        self.all_label = all_label
        self.none_label = none_label
        self.plural_label = plural_label
        self.options = {}
        self.variables = {}
        self.label_var = tk.StringVar(value=all_label)
        button_options = dict(
            textvariable=self.label_var, relief="solid", bd=1,
            bg=WHITE, fg=INK, padx=8, pady=3, anchor="w",
        )
        if width:
            button_options["width"] = width
        self.button = tk.Menubutton(self, **button_options)
        self.menu = tk.Menu(self.button, tearoff=False)
        self.button.configure(menu=self.menu)
        self.button.pack(fill="x", expand=True)

    def set_options(self, options):
        """Set ``(key, label)`` pairs while retaining the user's selection."""
        previous = set(self.selected())
        first_load = not self.options
        previously_all = bool(self.options) and len(previous) == len(self.options)
        self.options = dict(options)
        self.variables = {}
        self.menu.delete(0, "end")
        self.menu.add_command(label="Select all", command=lambda: self.set_all(True))
        self.menu.add_command(label="Clear selection", command=lambda: self.set_all(False))
        self.menu.add_separator()
        for key, label in self.options.items():
            variable = tk.BooleanVar(value=first_load or previously_all or key in previous)
            self.variables[key] = variable
            self.menu.add_checkbutton(label=label, variable=variable, command=self._changed)
        self._update_label()

    def selected(self):
        return [key for key, variable in self.variables.items() if variable.get()]

    def set_all(self, selected):
        for variable in self.variables.values():
            variable.set(selected)
        self._changed()

    def display_text(self):
        selected = self.selected()
        if not self.options or len(selected) == len(self.options):
            return self.all_label
        if not selected:
            return self.none_label
        if len(selected) == 1:
            return self.options[selected[0]]
        return f"{len(selected)} {self.plural_label} selected"

    def _update_label(self):
        self.label_var.set(self.display_text())

    def _changed(self):
        self._update_label()
        if self.command:
            self.command()


class StatusChecklist(ttk.Frame):
    """Checkbox dropdown allowing multiple expense statuses at once."""
    OPTIONS = ("Paid", "Partially Paid", "Unpaid", "Void")

    def __init__(self, parent, command=None):
        super().__init__(parent)
        self.command = command
        self.variables = {status: tk.BooleanVar(value=True) for status in self.OPTIONS}
        self.label_var = tk.StringVar(value="All Statuses")
        self.button = tk.Menubutton(
            self, textvariable=self.label_var, relief="solid", bd=1,
            bg=WHITE, fg=INK, padx=8, pady=3, anchor="w",
        )
        self.menu = tk.Menu(self.button, tearoff=False)
        self.menu.add_command(label="Select all", command=lambda: self.set_all(True))
        self.menu.add_command(label="Clear selection", command=lambda: self.set_all(False))
        self.menu.add_separator()
        for status in self.OPTIONS:
            self.menu.add_checkbutton(
                label=status, variable=self.variables[status], command=self._changed,
            )
        self.button.configure(menu=self.menu)
        self.button.pack(fill="x", expand=True)

    def selected(self):
        return [status for status, variable in self.variables.items() if variable.get()]

    def set_all(self, selected):
        for variable in self.variables.values():
            variable.set(selected)
        self._changed()

    def select_only(self, statuses):
        selected = set(statuses)
        for status, variable in self.variables.items():
            variable.set(status in selected)
        self._changed()

    def display_text(self):
        selected = self.selected()
        if len(selected) == len(self.OPTIONS):
            return "All Statuses"
        if not selected:
            return "No Statuses"
        return ", ".join(selected)

    def _changed(self):
        self.label_var.set(self.display_text())
        if self.command:
            self.command()


class VerificationChecklist(ttk.Frame):
    """Checkbox dropdown keeping review status separate from payment status."""
    OPTIONS = ("Verified", "Unverified")

    def __init__(self, parent, command=None):
        super().__init__(parent)
        self.command = command
        self.variables = {value: tk.BooleanVar(value=True) for value in self.OPTIONS}
        self.label_var = tk.StringVar(value="All Verification")
        self.button = tk.Menubutton(
            self, textvariable=self.label_var, relief="solid", bd=1,
            bg=WHITE, fg=INK, padx=8, pady=3, anchor="w",
        )
        self.menu = tk.Menu(self.button, tearoff=False)
        self.menu.add_command(label="Select all", command=lambda: self.set_all(True))
        self.menu.add_command(label="Clear selection", command=lambda: self.set_all(False))
        self.menu.add_separator()
        for value in self.OPTIONS:
            self.menu.add_checkbutton(label=value, variable=self.variables[value], command=self._changed)
        self.button.configure(menu=self.menu); self.button.pack(fill="x", expand=True)

    def selected(self):
        return [value for value, variable in self.variables.items() if variable.get()]

    def set_all(self, selected):
        for variable in self.variables.values(): variable.set(selected)
        self._changed()

    def display_text(self):
        selected = self.selected()
        if len(selected) == len(self.OPTIONS): return "All Verification"
        if not selected: return "No Verification"
        return ", ".join(selected)

    def _changed(self):
        self.label_var.set(self.display_text())
        if self.command: self.command()


class PaymentMethodChecklist(ttk.Frame):
    """Checkbox dropdown for expense payment sources."""
    OPTIONS = ("Cash", "Bank Transfer", "Other")

    def __init__(self, parent, command=None):
        super().__init__(parent)
        self.command = command
        self.variables = {method: tk.BooleanVar(value=True) for method in self.OPTIONS}
        self.label_var = tk.StringVar(value="All MOP")
        self.button = tk.Menubutton(
            self, textvariable=self.label_var, relief="solid", bd=1,
            bg=WHITE, fg=INK, padx=8, pady=3, anchor="w",
        )
        self.menu = tk.Menu(self.button, tearoff=False)
        self.menu.add_command(label="Select all", command=lambda: self.set_all(True))
        self.menu.add_command(label="Clear selection", command=lambda: self.set_all(False))
        self.menu.add_separator()
        for method in self.OPTIONS:
            self.menu.add_checkbutton(
                label=method, variable=self.variables[method], command=self._changed,
            )
        self.button.configure(menu=self.menu)
        self.button.pack(fill="x", expand=True)

    def selected(self):
        return [method for method, variable in self.variables.items() if variable.get()]

    def set_all(self, selected):
        for variable in self.variables.values():
            variable.set(selected)
        self._changed()

    def display_text(self):
        selected = self.selected()
        if len(selected) == len(self.OPTIONS):
            return "All MOP"
        if not selected:
            return "No MOP"
        return ", ".join(selected)

    def _changed(self):
        self.label_var.set(self.display_text())
        if self.command:
            self.command()


def make_tree(parent, columns: list[tuple[str, str, int]]):
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=True, pady=(8, 0))
    toolbar = ttk.Frame(frame); toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 3))
    count_label = ttk.Label(toolbar, text="Showing 0 of 0 entries", style="Muted.TLabel")
    count_label.pack(side="left")
    full_button = ttk.Button(toolbar, text="See full ledger (0)")
    full_button.pack(side="right")
    expand_button = ttk.Button(toolbar, text="Open expanded")
    expand_button.pack(side="right", padx=(0, 6))
    tree = LedgerTree(frame, columns=[c[0] for c in columns], show="headings", selectmode="browse")
    full_button.configure(command=tree.toggle_full_ledger)
    expand_button.configure(command=tree.open_expanded_ledger)
    tree.attach_limiter(count_label, full_button)
    for key, label, width in columns:
        tree.heading(key, text=label)
        # Every ledger column participates in window resizing and remains
        # manually adjustable by dragging its heading divider.
        tree.column(key, width=width, minwidth=min(70, width), anchor="w", stretch=True)
    scroll_y = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    scroll_x = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
    tree.grid(row=1, column=0, sticky="nsew")
    scroll_y.grid(row=1, column=1, sticky="ns")
    scroll_x.grid(row=2, column=0, sticky="ew")
    frame.rowconfigure(1, weight=1)
    frame.columnconfigure(0, weight=1)
    tree.bind("<MouseWheel>", lambda event: tree.yview_scroll(int(-event.delta / 120), "units"))
    return tree


class AutoFitLabel(tk.Label):
    """Label that reduces its font size until its text fits the available width."""
    def __init__(self, parent, *, base_size=22, min_size=10, **kwargs):
        self.base_size = base_size
        self.min_size = min_size
        self.font_family = "Segoe UI"
        self.font_weight = "bold"
        super().__init__(parent, **kwargs)
        self.bind("<Configure>", lambda _event: self.after_idle(self._fit_text), add="+")

    def configure(self, cnf=None, **kwargs):
        result = super().configure(cnf, **kwargs)
        if self.winfo_exists():
            self.after_idle(self._fit_text)
        return result

    config = configure

    def _fit_text(self):
        if not self.winfo_exists():
            return
        available = max(40, self.master.winfo_width() - 32)
        text = str(self.cget("text"))
        size = self.base_size
        while size > self.min_size:
            font = tkfont.Font(family=self.font_family, size=size, weight=self.font_weight)
            if font.measure(text) <= available:
                break
            size -= 1
        super().configure(font=(self.font_family, size, self.font_weight))


class FinancialPieChart(ttk.Frame):
    """Responsive nested chart for contract funding and expense commitments."""
    def __init__(self, parent):
        super().__init__(parent)
        self.title_label = ttk.Label(self, text="Contract funding", style="Section.TLabel")
        self.title_label.pack(anchor="w")
        self.subtitle_label = ttk.Label(
            self, text="Deposited > payments > outstanding",
            style="Muted.TLabel",
        )
        self.subtitle_label.pack(anchor="w", pady=(0, 4))
        self.canvas = tk.Canvas(self, bg=WHITE, highlightbackground="#D8DEE8", highlightthickness=1)
        self.canvas.pack(fill="both", expand=True)
        self.data = {}
        self.canvas.bind("<Configure>", lambda _event: self.redraw())

    def set_data(self, contract=0, deposited=0, paid=0, outstanding=0, progress=0):
        self.data = {
            "contract": max(0, int(contract)),
            "deposited": max(0, int(deposited)),
            "paid": max(0, int(paid)),
            "outstanding": max(0, int(outstanding)),
            "progress": max(0, min(100, int(progress))),
        }
        self.redraw()

    @staticmethod
    def _short_money(value):
        amount = (value or 0) / 100
        if abs(amount) >= 1_000_000:
            return f"{amount / 1_000_000:.2f}M"
        if abs(amount) >= 1_000:
            return f"{amount / 1_000:.2f}K"
        return f"{amount:,.2f}"

    def redraw(self):
        canvas = self.canvas
        canvas.delete("all")
        width, height = max(canvas.winfo_width(), 80), max(canvas.winfo_height(), 190)
        narrow = width < 170
        self.title_label.configure(text="Funding" if narrow else "Contract funding")
        self.subtitle_label.configure(
            text="" if narrow else "Deposited > payments > outstanding"
        )
        contract = self.data.get("contract", 0)
        deposited = self.data.get("deposited", 0)
        paid = self.data.get("paid", 0)
        outstanding = self.data.get("outstanding", 0)
        progress = self.data.get("progress", 0)
        available = max(0, deposited - paid)
        covered_outstanding = min(outstanding, available)
        free_budget = max(0, available - outstanding)
        unfunded_outstanding = max(0, outstanding - available)

        diameter = max(58, min(width - 18, height - 132, 238))
        left = (width - diameter) / 2
        top = 12
        ring_width = max(4, int(diameter * .065))
        ring_gap = max(2, int(diameter * .025))

        def draw_ring(inset, basis, segments, track="#E5E7EB"):
            box = (left + inset, top + inset, left + diameter - inset, top + diameter - inset)
            canvas.create_arc(
                *box, start=90, extent=-359.9, style="arc", outline=track,
                width=ring_width,
            )
            if basis <= 0:
                return
            start = 90
            remaining = basis
            for value, color in segments:
                amount = min(max(0, value), remaining)
                if amount <= 0:
                    continue
                extent = -(amount * 359.9 / basis)
                canvas.create_arc(
                    *box, start=start, extent=extent, style="arc", outline=color,
                    width=ring_width,
                )
                start += extent
                remaining -= amount

        # Outer: how much of the total contract has been deposited.
        draw_ring(0, max(contract, deposited), ((deposited, "#2563EB"),))
        # Middle: how deposited funds divide between recorded payments and funds after payments.
        second_inset = ring_width + ring_gap
        draw_ring(second_inset, max(deposited, paid), ((paid, GREEN), (available, "#93C5FD")))
        # Inner: how much available budget is reserved by outstanding commitments.
        third_inset = second_inset * 2
        inner_basis = max(available, outstanding)
        draw_ring(
            third_inset, inner_basis,
            ((covered_outstanding, RED), (free_budget, "#D8E8FA"),
             (unfunded_outstanding, "#991B1B")),
        )

        center_x = width / 2
        center_y = top + diameter / 2
        if contract or deposited or paid or outstanding:
            if diameter >= 105:
                canvas.create_text(
                    center_x, center_y - 9, text="PROGRESS", fill=MUTED,
                    font=("Segoe UI", 7, "bold"),
                )
            canvas.create_text(
                center_x, center_y + (10 if diameter >= 105 else 0),
                text=f"{progress}%", fill=ORANGE,
                font=("Segoe UI", 13 if diameter >= 105 else 9, "bold"),
            )
        else:
            canvas.create_text(center_x, center_y, text="No financial data", fill=MUTED)

        def percent(part, whole):
            return part * 100 / whole if whole else 0

        legend_rows = [
            ("#2563EB", f"Deposited  {self._short_money(deposited)} / {self._short_money(contract)}  "
                        f"({percent(deposited, contract):.1f}%)"),
            (GREEN, f"Payments  {self._short_money(paid)}  "
                    f"({percent(paid, deposited):.1f}% of deposits)"),
            ("#93C5FD", f"Funds after payments  {self._short_money(available)}"),
            (RED, f"Outstanding  {self._short_money(outstanding)}"),
            ("#D8E8FA", f"Project budget remaining  {self._short_money(free_budget)}"),
        ]
        if unfunded_outstanding:
            legend_rows[-1] = (
                "#991B1B", f"Unfunded outstanding  {self._short_money(unfunded_outstanding)}"
            )
        if narrow:
            legend_rows = [
                ("#2563EB", f"Dep. {self._short_money(deposited)} ({percent(deposited, contract):.1f}%)"),
                (GREEN, f"Paid {self._short_money(paid)} ({percent(paid, deposited):.1f}%)"),
                ("#93C5FD", f"Avail. {self._short_money(available)}"),
                (RED, f"Outst. {self._short_money(outstanding)}"),
                (("#991B1B" if unfunded_outstanding else "#D8E8FA"),
                 f"{'Unfund.' if unfunded_outstanding else 'Free'} "
                 f"{self._short_money(unfunded_outstanding or free_budget)}"),
            ]
        legend_y = top + diameter + 13
        for index, (color, label) in enumerate(legend_rows):
            row_height = 15 if narrow else 18
            row_y = legend_y + index * row_height
            square_left = 5 if narrow else 12
            square_size = 8 if narrow else 10
            text_left = 17 if narrow else 28
            canvas.create_rectangle(
                square_left, row_y, square_left + square_size, row_y + square_size,
                fill=color, outline="",
            )
            font_size = 7 if narrow else 8
            minimum_size = 5 if narrow else 6
            while font_size > minimum_size and tkfont.Font(family="Segoe UI", size=font_size).measure(label) > width - text_left - 4:
                font_size -= 1
            canvas.create_text(
                text_left, row_y + square_size / 2, anchor="w", fill=INK,
                font=("Segoe UI", font_size), text=label,
            )


def metric_card(parent, title: str, accent: str = ORANGE):
    card = tk.Frame(parent, bg=WHITE, highlightbackground="#D8DEE8", highlightthickness=1, padx=16, pady=13)
    AutoFitLabel(
        card, text=title.upper(), bg=WHITE, fg=MUTED,
        base_size=9, min_size=7,
    ).pack(anchor="w", fill="x")
    value = AutoFitLabel(card, text="—", bg=WHITE, fg=accent, base_size=22, min_size=10)
    value.pack(anchor="w", fill="x", pady=(7, 0))
    card.bind("<Configure>", lambda _event: value._fit_text(), add="+")
    return card, value


def metric_card_with_detail(parent, title: str, detail_title: str, accent: str = ORANGE):
    """Metric card with a responsive secondary amount beneath the main value."""
    card, value = metric_card(parent, title, accent)
    detail_label = AutoFitLabel(
        card, text=detail_title.upper(), bg=WHITE, fg=MUTED,
        base_size=7, min_size=6,
    )
    detail_label.pack(anchor="w", fill="x", pady=(7, 0))
    detail_value = AutoFitLabel(
        card, text="—", bg=WHITE, fg=NAVY_ACTIVE, base_size=12, min_size=8,
    )
    detail_value.pack(anchor="w", fill="x", pady=(2, 0))
    card.bind("<Configure>", lambda _event: detail_value._fit_text(), add="+")
    return card, value, detail_label, detail_value


def layout_metric_cards(parent, cards):
    """Arrange summary cards as equal, responsive columns."""
    for column, card in enumerate(cards):
        parent.columnconfigure(column, weight=1, uniform="metric_cards")
        card.grid(row=0, column=column, sticky="nsew", padx=(0, 8))


class ProjectCompletionDialog(tk.Toplevel):
    def __init__(self, parent, project, checks):
        super().__init__(parent)
        self.title("Complete Project")
        self.geometry("700x560"); self.minsize(620, 500)
        self.result = None
        self.date_var = tk.StringVar(value=date.today().isoformat())
        self.notes_var = tk.StringVar()
        body = ttk.Frame(self, padding=22); body.pack(fill="both", expand=True)
        ttk.Label(body, text="Complete and archive this project", style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(body, text=project["name"], style="Section.TLabel").pack(anchor="w", pady=(5, 2))
        ttk.Label(body, text=(
            "Completion preserves every record and locks the project against new operational entries. "
            "It remains available in Completed Projects."
        ), style="Muted.TLabel", wraplength=640).pack(anchor="w", pady=(0, 14))
        metrics = checks["metrics"]
        summary = ttk.LabelFrame(body, text="Closeout snapshot", padding=12)
        summary.pack(fill="x")
        values = (
            ("Contract value", money(metrics["contract_value_cents"])),
            ("Deposited", money(metrics["deposited_cents"])),
            ("Active expenses", money(metrics["active_expense_cents"])),
            ("Payments recorded", money(metrics["paid_cents"])),
            ("Outstanding", money(metrics["outstanding_cents"])),
            ("Progress", f"{metrics['progress_percent']}%"),
        )
        for index, (label, value) in enumerate(values):
            row, column = divmod(index, 3)
            cell = ttk.Frame(summary); cell.grid(row=row, column=column, sticky="ew", padx=8, pady=5)
            ttk.Label(cell, text=label, style="Muted.TLabel").pack(anchor="w")
            ttk.Label(cell, text=value, style="Section.TLabel").pack(anchor="w")
            summary.columnconfigure(column, weight=1)
        if checks["warnings"]:
            warning = ttk.LabelFrame(body, text="Items retained as closeout notes", padding=10)
            warning.pack(fill="x", pady=(12, 0))
            ttk.Label(warning, text="\n".join(f"• {item}" for item in checks["warnings"]),
                      wraplength=620).pack(anchor="w")
        form = ttk.Frame(body); form.pack(fill="x", pady=(14, 0)); form.columnconfigure(1, weight=1)
        ttk.Label(form, text="Completion date *").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=5)
        date_entry = ttk.Entry(form, textvariable=self.date_var, width=22)
        date_entry.grid(row=0, column=1, sticky="w", pady=5)
        ttk.Button(form, text="📅", width=3, command=lambda: DatePickerPopup(self, self.date_var)).grid(
            row=0, column=2, sticky="w", padx=(6, 0), pady=5)
        ttk.Label(form, text="Completion / turnover notes *").grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=5)
        notes_entry = ttk.Entry(form, textvariable=self.notes_var)
        notes_entry.grid(row=1, column=1, columnspan=2, sticky="ew", pady=5)
        self.widgets = {"completion_date": date_entry, "notes": notes_entry}
        footer = ttk.Frame(body); footer.pack(fill="x", pady=(18, 0))
        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(footer, text="Continue to All-Heads Approval", style="Primary.TButton",
                   command=self.save).pack(side="right", padx=(0, 8))
        self.transient(parent); self.grab_set(); self.bind("<Escape>", lambda _e: self.destroy())

    def save(self):
        if not self.date_var.get().strip() or not self.notes_var.get().strip():
            missing = [widget for key, widget in self.widgets.items()
                       if not (self.date_var.get() if key == "completion_date" else self.notes_var.get()).strip()]
            flash_required_widgets(self, missing)
            return
        try:
            completion_date = valid_date(self.date_var.get(), True)
        except ValueError as exc:
            flash_required_widgets(self, [self.widgets["completion_date"]])
            messagebox.showerror(APP_TITLE, str(exc), parent=self); return
        self.result = {"completion_date": completion_date, "notes": self.notes_var.get().strip()}
        self.destroy()


class CompletedProjectDetailsDialog(tk.Toplevel):
    def __init__(self, parent, db, project_id):
        super().__init__(parent)
        self.db = db; self.project_id = project_id
        self.title("Completed Project Record"); self.geometry("1240x760"); self.minsize(1000, 650)
        project = db.one("SELECT * FROM projects WHERE id=?", (project_id,))
        snapshot = db.one(
            """SELECT * FROM project_completion_snapshots WHERE project_id=?
               ORDER BY id DESC LIMIT 1""", (project_id,)
        )
        metrics = db.project_completion_metrics(project_id)
        body = ttk.Frame(self, padding=18); body.pack(fill="both", expand=True)
        ttk.Label(body, text=project["name"], style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(body, text=(
            f"{project['client']}  |  {project['address'] or 'No address recorded'}  |  "
            f"Completion ref. {project['completion_reference'] or 'Legacy completion'}"
        ), style="Muted.TLabel").pack(anchor="w", pady=(2, 10))
        notebook = ttk.Notebook(body); notebook.pack(fill="both", expand=True)
        overview = ttk.Frame(notebook, padding=14); expenses_page = ttk.Frame(notebook, padding=8)
        process_page = ttk.Frame(notebook, padding=8); inventory_page = ttk.Frame(notebook, padding=8)
        finance_page = ttk.Frame(notebook, padding=8)
        payroll_page = ttk.Frame(notebook, padding=8); people_page = ttk.Frame(notebook, padding=8)
        audit_page = ttk.Frame(notebook, padding=8)
        for page, label in ((overview,"Overview"),(expenses_page,"Expenses"),
                            (process_page,"Phases & Processes"),(finance_page,"Remittances"),
                            (inventory_page,"Inventory"),
                            (payroll_page,"Payroll & Attendance"),(people_page,"People"),
                            (audit_page,"Audit History")):
            notebook.add(page, text=label)
        self._build_overview(overview, project, snapshot, metrics)
        self._build_expenses(expenses_page)
        self._build_processes(process_page)
        self._build_inventory(inventory_page)
        self._build_remittances(finance_page)
        self._build_payroll(payroll_page)
        self._build_people(people_page)
        self._build_audit(audit_page)
        ttk.Button(body, text="Close", command=self.destroy).pack(anchor="e", pady=(10, 0))
        self.transient(parent); self.grab_set()

    @staticmethod
    def _duration_text(start_value, end_value):
        try:
            days = (date.fromisoformat(end_value) - date.fromisoformat(start_value)).days + 1
            return f"{max(0, days):,} calendar day(s)"
        except (TypeError, ValueError):
            return "Not available"

    def _build_overview(self, page, project, snapshot, metrics):
        completion_date = snapshot["completion_date"] if snapshot else (
            project["completed_at"][:10] if project["completed_at"] else ""
        )
        ttk.Label(page, text="Project closeout summary", style="Section.TLabel").pack(anchor="w")
        grid = ttk.Frame(page); grid.pack(fill="x", pady=(10, 18))
        fields = (
            ("Project", project["name"]), ("Client", project["client"]),
            ("Address", project["address"] or "—"), ("Status", project["status"]),
            ("Planned schedule", f"{project['start_date'] or '—'} to {project['target_date'] or '—'}"),
            ("Actual duration", self._duration_text(project["start_date"], completion_date)),
            ("Completed", completion_date or "—"),
            ("Approved by", project["completed_by_names"] or "Legacy / not recorded"),
            ("Contract value", money(metrics["contract_value_cents"])),
            ("Deposited", money(metrics["deposited_cents"])),
            ("Active expenses", money(metrics["active_expense_cents"])),
            ("Payments recorded", money(metrics["paid_cents"])),
            ("Outstanding", money(metrics["outstanding_cents"])),
            ("Budget remaining", money(metrics["budget_remaining_cents"])),
            ("Process completion", f"{metrics['completed_task_count']}/{metrics['task_count']} tasks — {metrics['progress_percent']}%"),
        )
        for index, (label, value) in enumerate(fields):
            row, column = divmod(index, 3)
            cell = tk.Frame(grid, bg=WHITE, highlightbackground="#D8DEE8", highlightthickness=1,
                            padx=12, pady=9)
            cell.grid(row=row, column=column, sticky="nsew", padx=4, pady=4)
            tk.Label(cell, text=label.upper(), bg=WHITE, fg=MUTED,
                     font=("Segoe UI", 8, "bold")).pack(anchor="w")
            tk.Label(cell, text=str(value), bg=WHITE, fg=INK, wraplength=300,
                     justify="left", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(4, 0))
            grid.columnconfigure(column, weight=1, uniform="overview")
        notes = snapshot["completion_notes"] if snapshot else project["completion_notes"]
        ttk.Label(page, text="Completion / turnover notes", style="Section.TLabel").pack(anchor="w")
        ttk.Label(page, text=notes or "No completion notes recorded.", wraplength=1050,
                  justify="left").pack(anchor="w", fill="x", pady=(5, 0))

    def _build_expenses(self, page):
        split = ttk.Panedwindow(page, orient="vertical"); split.pack(fill="both", expand=True)
        expense_pane = ttk.Frame(split); payment_pane = ttk.Frame(split)
        split.add(expense_pane, weight=3); split.add(payment_pane, weight=2)
        ttk.Label(expense_pane, text="Complete expense ledger", style="Section.TLabel").pack(anchor="w")
        tree = make_tree(expense_pane, [("date","Date",90),("batch","Batch Ref.",135),
            ("status","Status",95),("verify","Verification",95),("name","Expense",180),
            ("item","Item",170),("supplier","Supplier",130),("area","Area",105),
            ("total","Total",95),("paid","Paid",95),("outstanding","Outstanding",100),
            ("mop","MOP",110),("notes","Notes",220)])
        rows = self.db.all("""SELECT e.*,COALESCE(b.reference,'Legacy') batch_ref,
            COALESCE(SUM(CASE WHEN p.accounting_excluded=0 THEN p.amount_cents ELSE 0 END),0) paid,
            COALESCE(GROUP_CONCAT(DISTINCT CASE WHEN p.accounting_excluded=0 THEN p.method END),'Not Paid') mop
            FROM expenses e LEFT JOIN expense_batches b ON b.id=e.expense_batch_id
            LEFT JOIN payments p ON p.expense_id=e.id WHERE e.project_id=?
            GROUP BY e.id ORDER BY e.expense_date,e.id""", (self.project_id,))
        for row in rows:
            tree.insert("","end",iid=row["id"],values=(row["expense_date"],row["batch_ref"],
                "Void" if row["voided"] else row["status"],row["verification_status"],row["name"],
                row["item"],row["supplier"],row["area"],money(row["total_cents"]),money(row["paid"]),
                money(max(0,row["total_cents"]-row["paid"])),row["mop"],row["notes"]))
        ttk.Label(payment_pane, text="Every recorded expense payment", style="Section.TLabel").pack(
            anchor="w", pady=(8, 0))
        payments = make_tree(payment_pane, [("time","Date & Time",145),("expense","Expense",190),
            ("amount","Amount",100),("method","MOP",110),("system","System Ref.",145),
            ("user","User Ref.",130),("bank","Bank",150),("authorized","Authorized By",140),
            ("notes","Notes",210)])
        rows = self.db.all("""SELECT p.*,e.name expense_name,
            COALESCE(b.bank_name||' '||COALESCE(b.account_name,b.account_number),'') bank,
            COALESCE(h.name,'Legacy / not recorded') authorized FROM payments p
            JOIN expenses e ON e.id=p.expense_id LEFT JOIN bank_accounts b ON b.id=p.bank_account_id
            LEFT JOIN project_heads h ON h.id=p.authorized_by_head_id
            WHERE e.project_id=? ORDER BY p.payment_date,p.id""", (self.project_id,))
        for row in rows:
            payments.insert("","end",iid=row["id"],values=(row["transaction_time"] or row["payment_date"],
                row["expense_name"],money(row["amount_cents"]),row["method"],row["system_reference"] or "—",
                row["reference"] or "—",row["bank"],row["authorized"],row["notes"]))

    def _build_processes(self, page):
        tree = make_tree(page, [("phase","Phase",170),("milestone","Milestone",170),
            ("task","Task / Process",260),("deadline","Deadline",100),("status","Status",95),
            ("completed","Completed At",145),("timing","Schedule Result",120)])
        today = date.today().isoformat()
        rows = self.db.all("""SELECT p.name phase,t.* FROM phases p LEFT JOIN tasks t ON t.phase_id=p.id
            WHERE p.project_id=? ORDER BY p.sort_order,t.deadline,t.id""", (self.project_id,))
        for index, row in enumerate(rows):
            if row["id"] is None:
                tree.insert("","end",iid=f"phase-{index}",values=(row["phase"],"—","No tasks recorded","—","—","—","—")); continue
            timing = "Completed" if row["completed"] else ("Overdue" if row["deadline"] and row["deadline"] < today else "Open")
            tree.insert("","end",iid=row["id"],values=(row["phase"],row["milestone"],row["name"],
                row["deadline"] or "—","Completed" if row["completed"] else "Incomplete",
                row["completed_at"] or "—",timing))

    def _build_remittances(self, page):
        tree = make_tree(page, [("time","Date & Time",145),("reference","Reference",145),
            ("bank","Bank",160),("type","Type",90),("amount","Amount",105),
            ("purpose","Purpose",220),("care","C/O",120),("status","Status",70)])
        rows = self.db.all("""SELECT r.*,COALESCE(b.bank_name,'') bank_name,
            COALESCE(b.account_name,b.account_number,'') account_name FROM remittances r
            LEFT JOIN bank_accounts b ON b.id=r.bank_account_id WHERE r.project_id=?
            ORDER BY r.txn_date,r.id""", (self.project_id,))
        for row in rows:
            tree.insert("","end",iid=row["id"],values=(row["transaction_time"] or row["txn_date"],
                row["system_reference"] or f"Legacy #{row['id']}",
                f"{row['bank_name']} {row['account_name']}".strip(),row["type"],money(row["amount_cents"]),
                row["purpose"],row["care_of"],"VOID" if row["voided"] else "Active"))

    def _build_inventory(self, page):
        split = ttk.Panedwindow(page, orient="vertical"); split.pack(fill="both", expand=True)
        stock_page = ttk.Frame(split); activity_page = ttk.Frame(split)
        split.add(stock_page, weight=2); split.add(activity_page, weight=3)
        ttk.Label(stock_page, text="Final material and tool register", style="Section.TLabel").pack(anchor="w")
        stock = make_tree(stock_page, [("code","Item Code",125),("item","Material / Tool",180),
            ("type","Type",120),("category","Category",125),("unit","Unit",70),
            ("on_hand","Registered / On Hand",125),("available","Available",85),
            ("borrowed","Borrowed",85),("status","Status",115),("notes","Notes",220)])
        for row in self.db.inventory_item_rows(self.project_id, include_inactive=True):
            stock.insert("","end",iid=row["id"],values=(row["item_code"],row["name"],row["material_type"],
                row["category"],row["unit"],inventory_quantity(row["on_hand_milli"]),
                inventory_quantity(row["available_milli"]),inventory_quantity(row["borrowed_milli"]),
                row["status"],row["notes"]))
        ttk.Label(activity_page, text="Inventory custody and usage history", style="Section.TLabel").pack(
            anchor="w", pady=(8,0))
        activity = make_tree(activity_page, [("time","Date & Time",145),("ref","Reference",145),
            ("item","Material / Tool",170),("action","Activity",95),("quantity","Quantity",85),
            ("unit","Unit",65),("employee","Employee",140),("reason","Reason",220),
            ("authorized","Authorized By",130),("notes","Notes",200)])
        rows = self.db.all("""SELECT t.*,i.name item_name,i.unit,COALESCE(e.name,'—') employee,
            COALESCE(h.name,'Legacy / not recorded') authorized FROM inventory_transactions t
            JOIN inventory_items i ON i.id=t.item_id LEFT JOIN employees e ON e.id=t.employee_id
            LEFT JOIN project_heads h ON h.id=t.authorized_by_head_id
            WHERE t.project_id=? ORDER BY t.transaction_date,t.id""", (self.project_id,))
        for row in rows: activity.insert("","end",iid=row["id"],values=(
            row["transaction_time"] or row["transaction_date"],row["reference"],row["item_name"],
            row["transaction_type"],inventory_quantity(row["quantity_milli"]),row["unit"],
            row["employee"],row["reason"],row["authorized"],row["notes"]))

    def _build_payroll(self, page):
        split = ttk.Panedwindow(page, orient="vertical"); split.pack(fill="both", expand=True)
        payroll = ttk.Frame(split); attendance = ttk.Frame(split); split.add(payroll, weight=2); split.add(attendance, weight=3)
        ttk.Label(payroll, text="Committed weekly payrolls", style="Section.TLabel").pack(anchor="w")
        batches = make_tree(payroll, [("ref","Batch",155),("start","Period Start",95),("end","Period End",95),
            ("gross","Gross",100),("deductions","Deductions",100),("adjustments","Corrections",100),
            ("net","Net",100),("created","Committed",145)])
        for row in self.db.all("SELECT * FROM payroll_batches WHERE project_id=? ORDER BY period_start,id",(self.project_id,)):
            batches.insert("","end",iid=row["id"],values=(row["batch_ref"],row["period_start"],row["period_end"],
                money(row["gross_cents"]),money(row["deduction_cents"]),money(row["adjustment_cents"]),
                money(row["net_cents"]),row["created_at"]))
        ttk.Label(attendance, text="Daily attendance history", style="Section.TLabel").pack(anchor="w", pady=(8,0))
        logs = make_tree(attendance, [("employee","Employee",145),("in","Time In",145),("out","Time Out",145),
            ("regular","Regular Hrs",80),("ot","OT Hrs",70),("gross","Gross",95),
            ("source","Source",90),("corrections","Corrections",80)])
        rows = self.db.all("""SELECT a.*,e.name FROM attendance a JOIN employees e ON e.id=a.employee_id
            WHERE COALESCE(a.project_id,e.project_id)=? ORDER BY a.clock_in,a.id""",(self.project_id,))
        for row in rows: logs.insert("","end",iid=row["id"],values=(row["name"],row["clock_in"].replace("T"," "),
            row["clock_out"].replace("T"," "),row["regular_hours"],row["overtime_hours"],
            money(row["gross_cents"]),row["source"],row["revision_count"]))

    def _build_people(self, page):
        tree = make_tree(page, [("type","Record Type",100),("name","Name",170),("role","Position / Role",160),
            ("company","Company / Project",150),("phone","Contact",125),("email","Email",170),
            ("status","Status",85)])
        serial = 0
        for row in self.db.all("SELECT name,position,active FROM project_heads WHERE project_id=? ORDER BY name",(self.project_id,)):
            serial += 1; tree.insert("","end",iid=f"h-{serial}",values=("Project Head",row["name"],row["position"],"—","—","—","Active" if row["active"] else "Inactive"))
        for row in self.db.all("""SELECT e.name,a.position,e.contact_number,e.active,
            a.effective_from,a.effective_to FROM employee_project_assignments a
            JOIN employees e ON e.id=a.employee_id WHERE a.project_id=?
            ORDER BY e.name,a.effective_from""",(self.project_id,)):
            assignment = f"Assigned {row['effective_from'] or '—'} to {row['effective_to'] or 'Current'}"
            serial += 1; tree.insert("","end",iid=f"e-{serial}",values=("Employee",row["name"],
                row["position"],assignment,row["contact_number"],"—",
                "Historical" if row["effective_to"] else ("Active" if row["active"] else "Archived")))
        for row in self.db.all("SELECT * FROM contacts WHERE project_id=? ORDER BY name",(self.project_id,)):
            serial += 1; tree.insert("","end",iid=f"c-{serial}",values=("Contact",row["name"],row["role"],row["company"],row["phone"],row["email"],"Recorded"))

    def _build_audit(self, page):
        tree = make_tree(page, [("time","Date & Time",150),("action","Action",190),("details","Details",700)])
        for row in self.db.all("SELECT * FROM audit_log WHERE project_id=? ORDER BY id DESC",(self.project_id,)):
            tree.insert("","end",iid=row["id"],values=(row["created_at"],row["action"],row["details"]))


class CompletedProjectsTab(BaseTab):
    def __init__(self, app):
        super().__init__(app)
        header = ttk.Frame(self); header.pack(fill="x")
        title = ttk.Frame(header); title.pack(side="left")
        ttk.Label(title, text="Completed Projects", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title, text="Permanent closeout records, durations, finances and process history.",
                  style="Muted.TLabel").pack(anchor="w")
        ttk.Button(header, text="Reactivate Project", command=self.reactivate).pack(side="right")
        ttk.Button(header, text="View Full Project Record", style="Primary.TButton",
                   command=self.open_selected).pack(side="right", padx=(0, 8))
        self.tree = make_tree(self, [("ref","Completion Ref.",155),("project","Project",180),
            ("client","Client",150),("start","Started",90),("completed","Completed",95),
            ("duration","Duration",100),("progress","Progress",75),("contract","Contract",110),
            ("deposited","Deposited",110),("expenses","Expenses",110),("outstanding","Outstanding",105),
            ("approved","Approved By",180)])
        self.tree.bind("<Double-1>", self.open_selected)

    def open_selected(self, _event=None):
        project_id = self.selected_id(self.tree)
        if project_id:
            win = CompletedProjectDetailsDialog(self, self.db, project_id); self.wait_window(win)

    def reactivate(self):
        project_id = self.selected_id(self.tree)
        if not project_id: return
        project = self.db.one("SELECT * FROM projects WHERE id=?", (project_id,))
        data = dialog(self, "Reactivate Completed Project", [("reason","Reason for reactivation")],
                      required_keys=("reason",))
        if not data: return
        approvals = self.app.authorize_all_heads(
            project_id, "Reactivate completed project",
            f"{project['name']} will return to active operations.\nReason: {data['reason']}",
            allow_completed=True,
        )
        if not approvals: return
        try:
            self.db.reactivate_project(project_id, data["reason"], approvals)
            self.app.load_projects(project_id); self.app.show_page("Dashboard")
            messagebox.showinfo(APP_TITLE, f"{project['name']} is active again.", parent=self)
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        rows = self.db.all("""SELECT p.*,s.completion_date,s.progress_percent,
            s.deposited_cents,s.active_expense_cents,s.outstanding_cents
            FROM projects p LEFT JOIN project_completion_snapshots s
              ON s.completion_reference=p.completion_reference
            WHERE p.status='Completed' ORDER BY p.completed_at DESC,p.id DESC""")
        for row in rows:
            end = row["completion_date"] or (row["completed_at"][:10] if row["completed_at"] else "")
            self.tree.insert("","end",iid=row["id"],values=(row["completion_reference"] or "Legacy",
                row["name"],row["client"],row["start_date"] or "—",end or "—",
                CompletedProjectDetailsDialog._duration_text(row["start_date"],end),
                f"{row['progress_percent'] or 0}%",money(row["contract_value_cents"]),
                money(row["deposited_cents"] or 0),money(row["active_expense_cents"] or 0),
                money(row["outstanding_cents"] or 0),row["completed_by_names"] or "Legacy / not recorded"))


class ProjectsTab(BaseTab):
    FIELDS = [
        ("name", "Project name"), ("client", "Client"), ("contract_value", "Contract value"),
        ("start_date", "Start date (YYYY-MM-DD)"), ("target_date", "Target date (YYYY-MM-DD)"),
        ("address", "Project address"), ("notes", "Notes"),
    ]

    def __init__(self, app):
        super().__init__(app)
        header = ttk.Frame(self); header.pack(fill="x")
        title = ttk.Frame(header); title.pack(side="left")
        ttk.Label(title, text="Dashboard Overview", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title, text="Real-time project metrics and upcoming activity.", style="Muted.TLabel").pack(anchor="w")
        self.add_project_head_button = ttk.Button(
            header, text="+ Add Project Head", style="Primary.TButton",
            command=self.app.manage_head_registry,
        )
        self.add_project_head_button.pack(side="right")
        cards = ttk.Frame(self); cards.pack(fill="x", pady=(18, 14))
        self.contract_card, self.contract_value = metric_card(cards, "Total Contract Value", INK)
        self.deposit_card, self.deposit_value = metric_card(cards, "Contract Value Deposited", "#2563EB")
        self.paid_card, self.paid_value = metric_card(cards, "Payments Recorded", GREEN)
        self.outstanding_card, self.outstanding_value = metric_card(cards, "Outstanding", RED)
        self.progress_card, self.progress_value = metric_card(cards, "Overall Progress", ORANGE)
        layout_metric_cards(cards, (
            self.contract_card, self.deposit_card, self.paid_card,
            self.outstanding_card, self.progress_card,
        ))
        self.expense_reconciliation = ttk.Label(self, style="Muted.TLabel")
        self.expense_reconciliation.pack(anchor="w", fill="x", pady=(0, 10))
        lower = ttk.Panedwindow(self, orient="horizontal"); lower.pack(fill="both", expand=True)
        projects = ttk.Frame(lower, padding=(0, 0, 8, 0))
        chart = ttk.Frame(lower, padding=(8, 0))
        events = ttk.Frame(lower, padding=(8, 0, 0, 0))
        lower.add(projects, weight=3); lower.add(chart, weight=2); lower.add(events, weight=2)
        ttk.Label(projects, text="Projects", style="Section.TLabel").pack(anchor="w", pady=(0, 5))
        self.tree = make_tree(projects, [
            ("name", "Project", 180), ("status", "Status", 85), ("client", "Client", 145), ("contract", "Contract", 105),
            ("payments", "Payments", 100), ("outstanding", "Outstanding", 105),
            ("budget", "Budget Remaining", 115),
        ])
        self.tree.bind("<Double-1>", self.choose)
        self.financial_chart = FinancialPieChart(chart)
        self.financial_chart.pack(fill="both", expand=True)
        ttk.Label(events, text="Upcoming Events", style="Section.TLabel").pack(anchor="w", pady=(0, 5))
        self.events = make_tree(events, [
            ("date", "Date", 85), ("project", "Project", 120),
            ("event", "Event", 180), ("type", "Type", 75),
        ])

    def add(self):
        win = ProjectDialog(self); self.wait_window(win); data = win.result
        if not data:
            return
        try:
            if not data["name"]:
                raise ValueError("Project name is required.")
            project_id = self.db.create_project(data)
            self.app.load_projects(project_id)
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def manage_heads(self):
        if not self.require_project(): return
        win = ManageHeadsDialog(self, self.db, self.project_id); self.wait_window(win)

    def edit(self):
        if not self.require_project():
            return
        row = self.db.one("SELECT * FROM projects WHERE id=?", (self.project_id,))
        initial = dict(row)
        initial["contract_value"] = money(row["contract_value_cents"])
        data = dialog(self, "Edit Project", self.FIELDS, initial, required_keys=("name",))
        if not data:
            return
        try:
            if not data["name"]:
                raise ValueError("Project name is required.")
            self.db.execute(
                """UPDATE projects SET name=?,client=?,contract_value_cents=?,start_date=?,
                   target_date=?,address=?,notes=? WHERE id=?""",
                (data["name"], data["client"], cents(data["contract_value"]),
                 valid_date(data["start_date"]), valid_date(data["target_date"]),
                 data["address"], data["notes"], self.project_id),
            )
            self.db.audit(self.project_id, "PROJECT_EDITED", data["name"])
            self.app.load_projects(self.project_id)
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def complete_project(self):
        if not self.project_id:
            messagebox.showinfo(APP_TITLE, "Select an active project first.", parent=self); return
        project = self.db.one("SELECT * FROM projects WHERE id=?", (self.project_id,))
        if not project or not self.db.project_is_active(self.project_id):
            messagebox.showinfo(
                APP_TITLE, "This project is already completed. Open Completed Projects to review it.",
                parent=self,
            ); return
        checks = self.db.project_completion_checks(self.project_id)
        if checks["blockers"]:
            messagebox.showerror(
                APP_TITLE, "Project completion is blocked:\n\n" + "\n".join(checks["blockers"]),
                parent=self,
            ); return
        win = ProjectCompletionDialog(self, project, checks); self.wait_window(win)
        if not win.result: return
        approvals = self.app.authorize_all_heads(
            self.project_id, "Complete and archive project",
            f"{project['name']} will be locked against new entries and moved to Completed Projects.\n"
            f"Completion date: {win.result['completion_date']}\n"
            f"Notes: {win.result['notes']}",
        )
        if not approvals: return
        try:
            reference = self.db.complete_project(
                self.project_id, win.result["completion_date"], win.result["notes"], approvals
            )
            completed_name = project["name"]
            self.app.load_projects(None); self.app.show_page("Completed Projects")
            messagebox.showinfo(
                APP_TITLE,
                f"{completed_name} is now completed and read-only.\n\nCompletion reference: {reference}",
                parent=self,
            )
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)

    def choose(self, _event=None):
        selected = self.tree.selection()
        if selected:
            self.app.select_project(int(selected[0]))

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self.events.delete(*self.events.get_children())
        project_rows = self.db.all("SELECT * FROM projects ORDER BY created_at DESC")
        project_ids = ([self.project_id] if self.project_id else
                       [row["id"] for row in project_rows if row["status"] != "Completed"])
        for row in project_rows:
            if row["id"] not in project_ids:
                continue
            _deposited, payments, _payment_balance = self.db.project_budget(row["id"])
            _committed_deposit, _committed, budget = self.db.project_commitment_budget(row["id"])
            outstanding = self.db.one(
                """SELECT COALESCE(SUM(MAX(e.total_cents-COALESCE(x.paid,0),0)),0) total
                   FROM expenses e LEFT JOIN (
                     SELECT expense_id,SUM(amount_cents) paid FROM payments
                     WHERE accounting_excluded=0 GROUP BY expense_id
                   ) x ON x.expense_id=e.id
                   WHERE e.project_id=? AND e.voided=0""", (row["id"],)
            )["total"]
            self.tree.insert("", "end", iid=row["id"], values=(
                row["name"], row["status"], row["client"], money(row["contract_value_cents"]),
                money(payments), money(outstanding), money(budget),
            ))
        if project_ids:
            placeholders = ",".join("?" for _ in project_ids)
            tasks = self.db.one(
                f"""SELECT COUNT(*) total, COALESCE(SUM(completed),0) done FROM tasks
                   WHERE phase_id IN (
                     SELECT id FROM phases WHERE project_id IN ({placeholders}))""", tuple(project_ids)
            )
            paid = sum(self.db.project_budget(project_id)[1] for project_id in project_ids)
            progress = round(tasks["done"] * 100 / tasks["total"]) if tasks["total"] else 0
            outstanding = self.db.one(
                f"""SELECT COALESCE(SUM(MAX(e.total_cents-COALESCE(x.paid,0),0)),0) total
                   FROM expenses e LEFT JOIN (SELECT expense_id,SUM(amount_cents) paid FROM payments
                   WHERE accounting_excluded=0 GROUP BY expense_id) x
                   ON x.expense_id=e.id WHERE e.project_id IN ({placeholders}) AND e.voided=0""", tuple(project_ids)
            )["total"]
            contract = self.db.one(
                "SELECT COALESCE(SUM(contract_value_cents),0) total FROM projects WHERE id IN (" +
                placeholders + ")", tuple(project_ids)
            )["total"]
            deposited = sum(self.db.project_budget(project_id)[0] for project_id in project_ids)
            self.contract_value.config(text=money(contract))
            self.deposit_value.config(text=money(deposited), fg="#2563EB")
            self.paid_value.config(text=money(paid))
            self.outstanding_value.config(text=money(outstanding))
            self.progress_value.config(text=f"{progress}%")
            committed = paid + outstanding
            budget_remaining = deposited - committed
            self.expense_reconciliation.config(
                text=(f"Expense reconciliation: payments recorded {money(paid)} + outstanding "
                      f"{money(outstanding)} = active expenses {money(committed)}. "
                      f"Deposited {money(deposited)} − active expenses {money(committed)} = "
                      f"project budget remaining {money(budget_remaining)}.")
            )
            self.financial_chart.set_data(contract, deposited, paid, outstanding, progress)
            for event in self.db.all(
                f"""SELECT ce.*,p.name project FROM calendar_events ce JOIN projects p ON p.id=ce.project_id
                   WHERE ce.project_id IN ({placeholders}) AND ce.completed=0 AND ce.event_date>=?
                   ORDER BY ce.event_date,ce.event_time""", tuple(project_ids) + (date.today().isoformat(),)):
                self.events.insert("", "end", iid=event["id"], values=(
                    event["event_date"], event["project"], event["title"], event["type"],
                ))
        else:
            for label in (self.contract_value, self.deposit_value, self.paid_value,
                          self.outstanding_value, self.progress_value):
                label.config(text="—")
            self.expense_reconciliation.config(text="No project financial records to reconcile.")
            self.financial_chart.set_data()


class InventoryTab(BaseTab):
    MATERIAL_TYPES = ("Consumable", "Non-Consumable")

    def __init__(self, app):
        super().__init__(app)
        header = ttk.Frame(self); header.pack(fill="x")
        title = ttk.Frame(header); title.pack(side="left")
        ttk.Label(title, text="Project Inventory", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title, text="Consumable stock usage and employee-accountable tool borrowing.",
                  style="Muted.TLabel").pack(anchor="w")
        selector = ttk.Frame(header); selector.pack(side="right")
        ttk.Label(selector, text="Inventory project").pack(side="left", padx=(0, 6))
        self.project_var = tk.StringVar(); self.project_lookup = {}
        self.project_combo = ttk.Combobox(selector, textvariable=self.project_var,
                                          state="readonly", width=28)
        self.project_combo.pack(side="left")
        self.project_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        actions = ttk.Frame(self); actions.pack(fill="x", pady=(12, 6))
        self.action_buttons = []
        for text_value, command, primary in (
            ("+ Register Material / Tool", self.register_item, True),
            ("Restock Consumable", self.restock, False),
            ("Issue Consumable", self.consume, False),
            ("Borrow Tool", self.borrow, False),
            ("Return Tool", self.return_tool, False),
        ):
            button = ttk.Button(actions, text=text_value, command=command,
                                style="Primary.TButton" if primary else "Secondary.TButton")
            button.pack(side="left", padx=(0, 6)); self.action_buttons.append(button)

        cards = ttk.Frame(self); cards.pack(fill="x", pady=(4, 8))
        self.consumable_card, self.consumable_value = metric_card(cards, "Consumable Items", GREEN)
        self.tool_card, self.tool_value = metric_card(cards, "Non-Consumable Units", INK)
        self.available_card, self.available_value = metric_card(cards, "Tools Available", GREEN)
        self.borrowed_card, self.borrowed_value = metric_card(cards, "Tools Borrowed", ORANGE)
        self.low_card, self.low_value = metric_card(cards, "Low / Out of Stock", RED)
        layout_metric_cards(cards, (self.consumable_card,self.tool_card,self.available_card,
                                    self.borrowed_card,self.low_card))

        filters = ttk.Frame(self); filters.pack(fill="x", pady=(2, 5))
        self.type_filter = tk.StringVar(value="All Material Types")
        self.search_var = tk.StringVar()
        ttk.Label(filters, text="Type").pack(side="left")
        type_combo = ttk.Combobox(filters, textvariable=self.type_filter, state="readonly",
                                  values=["All Material Types", *self.MATERIAL_TYPES], width=22)
        type_combo.pack(side="left", padx=(5, 12)); type_combo.bind("<<ComboboxSelected>>",lambda _e:self.refresh())
        ttk.Label(filters, text="Search").pack(side="left")
        search = ttk.Entry(filters, textvariable=self.search_var, width=38)
        search.pack(side="left", fill="x", expand=True, padx=(5, 0))
        search.bind("<KeyRelease>", lambda _e: self.refresh())

        self.notebook = ttk.Notebook(self); self.notebook.pack(fill="both", expand=True, pady=(4, 0))
        stock_page = ttk.Frame(self.notebook, padding=5)
        activity_page = ttk.Frame(self.notebook, padding=5)
        loans_page = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(stock_page, text="Inventory Stock")
        self.notebook.add(activity_page, text="Activity Ledger")
        self.notebook.add(loans_page, text="Active Borrowers")
        self.stock_tree = make_tree(stock_page, [("code","Item Code",125),("name","Material / Tool",190),
            ("type","Type",120),("category","Category",130),("unit","Unit",75),
            ("total","Registered / On Hand",125),("available","Available",90),
            ("borrowed","Borrowed",85),("reorder","Reorder Level",95),
            ("status","Status",115),("condition","Condition",100),("notes","Notes",220)])
        self.activity_tree = make_tree(activity_page, [("time","Date & Time",145),
            ("ref","Reference",145),("code","Item Code",120),("item","Material / Tool",175),
            ("action","Activity",100),("qty","Quantity",85),("unit","Unit",70),
            ("employee","Employee",145),("reason","Purpose / Reason",220),
            ("condition","Condition",110),("authorized","Authorized By",135),("notes","Notes",200)])
        self.loan_tree = make_tree(loans_page, [("ref","Borrow Ref.",145),("date","Borrowed",95),
            ("code","Item Code",120),("item","Tool",175),("employee","Responsible Employee",170),
            ("borrowed","Borrowed",85),("returned","Returned",85),("outstanding","Outstanding",95),
            ("unit","Unit",70),("purpose","Purpose",210),("condition","Condition Out",115)])

    def requested_page_height(self):
        return 1150

    def selected_project_id(self):
        return self.project_lookup.get(self.project_var.get())

    def require_inventory_project(self):
        project_id = self.selected_project_id()
        if not project_id:
            messagebox.showinfo(APP_TITLE, "Select an inventory project first.", parent=self); return None
        if not self.db.project_is_active(project_id):
            messagebox.showinfo(APP_TITLE,
                "Completed-project inventory is read-only. Reactivate the project before recording stock activity.",
                parent=self); return None
        return project_id

    def item_options(self, material_type):
        project_id = self.selected_project_id()
        rows = self.db.inventory_item_rows(project_id) if project_id else []
        return {f"{row['item_code']} — {row['name']} — {inventory_quantity(row['available_milli'])} {row['unit']} available":row
                for row in rows if row["material_type"] == material_type}

    def employee_options(self, project_id):
        return {f"{row['name']} [{row['employee_no']}]":row["id"] for row in self.db.all(
            "SELECT id,name,employee_no FROM employees WHERE project_id=? AND active=1 ORDER BY name COLLATE NOCASE",
            (project_id,))}

    def register_item(self):
        project_id = self.require_inventory_project()
        if not project_id: return
        data = dialog(self,"Register Inventory Material / Tool",[
            ("name","Item name / description"),("material_type","Material type",list(self.MATERIAL_TYPES)),
            ("category","Category"),("unit","Unit of measure"),("opening_quantity","Opening quantity"),
            ("reorder_level","Low-stock / reorder level"),("condition","Opening condition"),
            ("registration_date","Registration date"),("notes","Notes")],
            {"material_type":"Consumable","unit":"piece","opening_quantity":"1",
             "reorder_level":"0","condition":"Good","registration_date":date.today().isoformat()},
            required_keys=("name","material_type","category","unit","opening_quantity",
                           "reorder_level","condition","registration_date"))
        if not data:return
        try:
            opening = inventory_quantity_milli(data["opening_quantity"], positive=True)
            reorder = inventory_quantity_milli(data["reorder_level"])
            valid_date(data["registration_date"], True)
        except ValueError as exc:
            messagebox.showerror(APP_TITLE,str(exc),parent=self);return
        head = self.app.authorize_for_project(project_id,"Register inventory item",
            f"{data['name']} — {data['material_type']} — {data['opening_quantity']} {data['unit']}")
        if not head:return
        try:
            result=self.db.register_inventory_item(project_id=project_id,name=data["name"],
                material_type=data["material_type"],category=data["category"],unit=data["unit"],
                opening_quantity_milli=opening,reorder_level_milli=reorder,
                condition_status=data["condition"],notes=data["notes"],
                authorized_by_head_id=head["id"],registration_date=data["registration_date"])
            self.app.refresh_all(); messagebox.showinfo(APP_TITLE,
                f"Inventory item registered.\nItem code: {result['item_code']}\nStock reference: {result['reference']}",parent=self)
        except (ValueError,sqlite3.Error) as exc:messagebox.showerror(APP_TITLE,str(exc),parent=self)

    def restock(self):
        project_id = self.require_inventory_project()
        if not project_id:return
        options=self.item_options("Consumable")
        if not options:messagebox.showinfo(APP_TITLE,"Register a consumable material first.",parent=self);return
        data=dialog(self,"Restock Consumable",[("item","Consumable",list(options)),
            ("quantity","Restock quantity"),("transaction_date","Restock date"),
            ("reason","Restock source / reason"),("notes","Notes")],
            {"item":next(iter(options)),"transaction_date":date.today().isoformat()},
            required_keys=("item","quantity","transaction_date","reason"))
        if not data:return
        self._commit_movement(project_id,options[data["item"]]["id"],"Restock",data,None,None)

    def consume(self):
        project_id=self.require_inventory_project()
        if not project_id:return
        options=self.item_options("Consumable"); employees=self.employee_options(project_id)
        if not options:messagebox.showinfo(APP_TITLE,"Register a consumable material first.",parent=self);return
        if not employees:messagebox.showinfo(APP_TITLE,"Add an active employee to this project first.",parent=self);return
        data=dialog(self,"Issue / Use Consumable Material",[("item","Consumable",list(options)),
            ("employee","Employee receiving material",list(employees)),("quantity","Quantity issued"),
            ("transaction_date","Issue date"),("reason","Usage purpose / work area"),("notes","Notes")],
            {"item":next(iter(options)),"employee":next(iter(employees)),
             "transaction_date":date.today().isoformat()},
            required_keys=("item","employee","quantity","transaction_date","reason"))
        if not data:return
        self._commit_movement(project_id,options[data["item"]]["id"],"Consume",data,
                              employees[data["employee"]],None)

    def borrow(self):
        project_id=self.require_inventory_project()
        if not project_id:return
        options=self.item_options("Non-Consumable"); employees=self.employee_options(project_id)
        if not options:messagebox.showinfo(APP_TITLE,"Register a non-consumable tool first.",parent=self);return
        if not employees:messagebox.showinfo(APP_TITLE,"Add an active employee to this project first.",parent=self);return
        data=dialog(self,"Borrow Non-Consumable Tool",[("item","Tool / equipment",list(options)),
            ("employee","Responsible employee",list(employees)),("quantity","Quantity borrowed"),
            ("transaction_date","Borrow date"),("reason","Purpose / work assignment"),
            ("condition","Condition when released"),("notes","Notes")],
            {"item":next(iter(options)),"employee":next(iter(employees)),"quantity":"1",
             "transaction_date":date.today().isoformat(),"condition":"Good"},
            required_keys=("item","employee","quantity","transaction_date","reason","condition"))
        if not data:return
        self._commit_movement(project_id,options[data["item"]]["id"],"Borrow",data,
                              employees[data["employee"]],None)

    def return_tool(self):
        project_id=self.require_inventory_project()
        if not project_id:return
        loans=self.db.active_inventory_loans(project_id)
        options={f"{row['reference']} — {row['item_name']} — {row['employee']} — {inventory_quantity(row['outstanding_milli'])} {row['unit']} due":row
                 for row in loans}
        if not options:messagebox.showinfo(APP_TITLE,"There are no borrowed tools awaiting return.",parent=self);return
        data=dialog(self,"Return Borrowed Tool",[("loan","Active borrowing record",list(options)),
            ("quantity","Quantity returned"),("transaction_date","Return date"),
            ("reason","Return / handover reason"),("condition","Condition upon return"),
            ("notes","Damage, loss or other notes")],
            {"loan":next(iter(options)),"quantity":inventory_quantity(next(iter(options.values()))["outstanding_milli"]),
             "transaction_date":date.today().isoformat(),"reason":"Returned to project inventory","condition":"Good"},
            required_keys=("loan","quantity","transaction_date","reason","condition"))
        if not data:return
        loan=options[data["loan"]]
        self._commit_movement(project_id,loan["item_id"],"Return",data,loan["employee_id"],loan["id"])

    def _commit_movement(self, project_id, item_id, transaction_type, data, employee_id, linked_id):
        try:
            quantity=inventory_quantity_milli(data["quantity"],positive=True)
            valid_date(data["transaction_date"],True)
            item=self.db.one("SELECT * FROM inventory_items WHERE id=?",(item_id,))
        except ValueError as exc:messagebox.showerror(APP_TITLE,str(exc),parent=self);return
        employee=self.db.one("SELECT name FROM employees WHERE id=?",(employee_id,)) if employee_id else None
        details=(f"{transaction_type} {inventory_quantity(quantity)} {item['unit']} of "
                 f"{item['item_code']} {item['name']}" + (f" for {employee['name']}" if employee else "") +
                 f". Purpose: {data['reason']}")
        head=self.app.authorize_for_project(project_id,f"Authorize inventory {transaction_type.lower()}",details)
        if not head:return
        try:
            reference=self.db.record_inventory_movement(item_id=item_id,transaction_type=transaction_type,
                quantity_milli=quantity,transaction_date=data["transaction_date"],reason=data["reason"],
                notes=data.get("notes",""),authorized_by_head_id=head["id"],employee_id=employee_id,
                condition_note=data.get("condition",""),linked_transaction_id=linked_id)
            self.app.refresh_all();messagebox.showinfo(APP_TITLE,
                f"Inventory activity recorded.\nReference: {reference}",parent=self)
        except (ValueError,sqlite3.Error) as exc:messagebox.showerror(APP_TITLE,str(exc),parent=self)

    def refresh(self):
        projects=self.db.all("SELECT id,name,status FROM projects ORDER BY name COLLATE NOCASE")
        self.project_lookup={f"{'✓ ' if row['status']=='Completed' else ''}{row['name']} [#{row['id']}]":row["id"] for row in projects}
        self.project_combo.configure(values=list(self.project_lookup))
        valid_labels=set(self.project_lookup)
        if self.project_var.get() not in valid_labels:
            preferred=next((label for label,pid in self.project_lookup.items() if pid==self.app.project_id),"")
            self.project_var.set(preferred or next(iter(self.project_lookup),""))
        project_id=self.selected_project_id()
        active=bool(project_id and self.db.project_is_active(project_id))
        for button in self.action_buttons:button.configure(state="normal" if active else "disabled")
        for tree in (self.stock_tree,self.activity_tree,self.loan_tree):tree.delete(*tree.get_children())
        if not project_id:
            for value in (self.consumable_value,self.tool_value,self.available_value,self.borrowed_value,self.low_value):value.config(text="—")
            return
        rows=self.db.inventory_item_rows(project_id)
        search=self.search_var.get().strip().lower(); material_filter=self.type_filter.get()
        displayed=[]
        for row in rows:
            haystack=" ".join(str(row.get(key,"")) for key in ("item_code","name","material_type","category","unit","status","condition_status","notes")).lower()
            if search and search not in haystack:continue
            if material_filter in self.MATERIAL_TYPES and row["material_type"]!=material_filter:continue
            displayed.append(row)
            self.stock_tree.insert("","end",iid=row["id"],values=(row["item_code"],row["name"],row["material_type"],
                row["category"],row["unit"],inventory_quantity(row["on_hand_milli"]),
                inventory_quantity(row["available_milli"]),inventory_quantity(row["borrowed_milli"]),
                inventory_quantity(row["reorder_level_milli"]),row["status"],row["condition_status"],row["notes"]))
        consumables=[row for row in rows if row["material_type"]=="Consumable"]
        tools=[row for row in rows if row["material_type"]=="Non-Consumable"]
        self.consumable_value.config(text=str(len(consumables)))
        self.tool_value.config(text=inventory_quantity(sum(row["on_hand_milli"] for row in tools)))
        self.available_value.config(text=inventory_quantity(sum(row["available_milli"] for row in tools)))
        self.borrowed_value.config(text=inventory_quantity(sum(row["borrowed_milli"] for row in tools)))
        self.low_value.config(text=str(sum(row["status"] in {"Low Stock","Out of Stock"} for row in consumables)))
        activity=self.db.all("""SELECT t.*,i.item_code,i.name item_name,i.unit,
            COALESCE(e.name,'—') employee,COALESCE(h.name,'Legacy / not recorded') authorized
            FROM inventory_transactions t JOIN inventory_items i ON i.id=t.item_id
            LEFT JOIN employees e ON e.id=t.employee_id LEFT JOIN project_heads h ON h.id=t.authorized_by_head_id
            WHERE t.project_id=? ORDER BY t.transaction_date DESC,t.id DESC""",(project_id,))
        for row in activity:self.activity_tree.insert("","end",iid=row["id"],values=(
            row["transaction_time"] or row["transaction_date"],row["reference"],row["item_code"],
            row["item_name"],row["transaction_type"],inventory_quantity(row["quantity_milli"]),
            row["unit"],row["employee"],row["reason"],row["condition_note"],row["authorized"],row["notes"]))
        for row in self.db.active_inventory_loans(project_id):self.loan_tree.insert("","end",iid=row["id"],values=(
            row["reference"],row["transaction_date"],row["item_code"],row["item_name"],row["employee"],
            inventory_quantity(row["quantity_milli"]),inventory_quantity(row["returned_milli"]),
            inventory_quantity(row["outstanding_milli"]),row["unit"],row["reason"],row["condition_note"]))


class ProgressTab(BaseTab):
    def __init__(self, app):
        super().__init__(app)
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Phases, milestones and tasks", style="Title.TLabel").pack(side="left")
        self.progress_label = ttk.Label(top, text="0%")
        self.progress_label.pack(side="right")
        self.progress = ttk.Progressbar(self, maximum=100)
        self.progress.pack(fill="x", pady=(8, 10))
        controls = ttk.Frame(self)
        controls.pack(fill="x")
        ttk.Label(controls, text="Phase:").pack(side="left")
        self.phase_var = tk.StringVar()
        self.phase_combo = ttk.Combobox(controls, textvariable=self.phase_var, state="readonly", width=28)
        self.phase_combo.pack(side="left", padx=5)
        ttk.Button(controls, text="Add Phase", command=self.add_phase).pack(side="left")
        ttk.Button(controls, text="Remove Phase", command=self.remove_phase).pack(side="left", padx=5)
        ttk.Button(controls, text="Add Task", command=self.add_task).pack(side="left", padx=(14, 5))
        ttk.Button(controls, text="Edit Task", command=self.edit_task).pack(side="left")
        ttk.Button(controls, text="✓ Toggle Complete", command=self.toggle).pack(side="left", padx=5)
        self.tree = make_tree(self, [
            ("done", "Done", 55), ("phase", "Phase", 150), ("milestone", "Milestone", 150),
            ("task", "Task", 260), ("deadline", "Deadline", 100), ("timing", "Timing", 90),
        ])

    def phase_map(self):
        return {r["name"]: r["id"] for r in self.db.all(
            "SELECT id,name FROM phases WHERE project_id=? ORDER BY sort_order,id", (self.project_id,)
        )}

    def add_phase(self):
        if not self.require_project():
            return
        data = dialog(self, "Add Phase", [("name", "Phase name")], required_keys=("name",))
        if data and data["name"]:
            order = self.db.one("SELECT COALESCE(MAX(sort_order),0)+1 n FROM phases WHERE project_id=?",
                                (self.project_id,))["n"]
            self.db.execute("INSERT INTO phases(project_id,name,sort_order) VALUES(?,?,?)",
                            (self.project_id, data["name"], order))
            self.db.audit(self.project_id, "PHASE_ADDED", data["name"])
            self.app.refresh_all()

    def remove_phase(self):
        if not self.require_project():
            return
        phase_id = self.phase_map().get(self.phase_var.get())
        if not phase_id:
            return
        if messagebox.askyesno(APP_TITLE, "Remove this phase and all of its tasks?"):
            self.db.execute("DELETE FROM phases WHERE id=?", (phase_id,))
            self.db.audit(self.project_id, "PHASE_REMOVED", self.phase_var.get())
            self.app.refresh_all()

    def task_form(self, initial=None):
        phases = list(self.phase_map())
        if not phases:
            messagebox.showinfo(APP_TITLE, "Add a phase first.")
            return None
        return dialog(self, "Task", [
            ("phase", "Phase", phases), ("milestone", "Milestone"),
            ("name", "Task"), ("deadline", "Deadline (YYYY-MM-DD)"),
        ], initial, required_keys=("phase", "name"))

    def add_task(self):
        if not self.require_project():
            return
        data = self.task_form({"phase": self.phase_var.get()})
        if not data:
            return
        try:
            if not data["name"]:
                raise ValueError("Task name is required.")
            self.db.execute(
                "INSERT INTO tasks(phase_id,milestone,name,deadline) VALUES(?,?,?,?)",
                (self.phase_map()[data["phase"]], data["milestone"], data["name"],
                 valid_date(data["deadline"])),
            )
            self.db.audit(self.project_id, "TASK_ADDED", data["name"])
            self.app.refresh_all()
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def edit_task(self):
        if not self.require_project():
            return
        task_id = self.selected_id(self.tree)
        if not task_id:
            return
        row = self.db.one(
            "SELECT t.*,p.name phase FROM tasks t JOIN phases p ON p.id=t.phase_id WHERE t.id=?", (task_id,)
        )
        data = self.task_form(dict(row))
        if data:
            try:
                self.db.execute("UPDATE tasks SET phase_id=?,milestone=?,name=?,deadline=? WHERE id=?",
                                (self.phase_map()[data["phase"]], data["milestone"], data["name"],
                                 valid_date(data["deadline"]), task_id))
                self.app.refresh_all()
            except ValueError as exc:
                messagebox.showerror(APP_TITLE, str(exc))

    def toggle(self):
        if not self.require_project():
            return
        task_id = self.selected_id(self.tree)
        if task_id:
            self.db.execute(
                """UPDATE tasks SET completed=CASE completed WHEN 1 THEN 0 ELSE 1 END,
                   completed_at=CASE completed WHEN 0 THEN ? ELSE '' END WHERE id=?""",
                (datetime.now().isoformat(timespec="seconds"), task_id),
            )
            self.db.audit(self.project_id, "TASK_TOGGLED", str(task_id))
            self.app.refresh_all()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        if not self.project_id:
            self.phase_combo["values"] = []
            self.progress["value"] = 0
            return
        phase_names = list(self.phase_map())
        self.phase_combo["values"] = phase_names
        if phase_names and self.phase_var.get() not in phase_names:
            self.phase_var.set(phase_names[0])
        rows = self.db.all(
            """SELECT t.*,p.name phase FROM tasks t JOIN phases p ON p.id=t.phase_id
               WHERE p.project_id=? ORDER BY p.sort_order,t.deadline,t.id""", (self.project_id,)
        )
        today = date.today().isoformat()
        for row in rows:
            timing = "Completed" if row["completed"] else (
                "Overdue" if row["deadline"] and row["deadline"] < today else "On track"
            )
            self.tree.insert("", "end", iid=row["id"], values=(
                "✓" if row["completed"] else "", row["phase"], row["milestone"],
                row["name"], row["deadline"], timing,
            ))
        done = sum(r["completed"] for r in rows)
        percent = round(done * 100 / len(rows)) if rows else 0
        self.progress["value"] = percent
        self.progress_label.config(text=f"{done}/{len(rows)} tasks — {percent}%")


class LegacyExpensesTab(BaseTab):
    BASE_FIELDS = [
        ("name", "Expense name"), ("item", "Item / description"), ("dimensions", "Size / dimensions"),
        ("supplier", "Supplier"), ("qty", "Quantity"), ("unit", "Unit"),
        ("unit_price", "Unit price"), ("phase", "Phase"), ("area", "Area"),
        ("trade", "Trade / category"), ("expense_date", "Expense date (YYYY-MM-DD)"),
        ("due_date", "Due date (YYYY-MM-DD)"), ("invoice_no", "Invoice / reference"),
        ("notes", "Notes"),
    ]

    def __init__(self, app):
        super().__init__(app)
        header = ttk.Frame(self)
        header.pack(fill="x")
        ttk.Label(header, text="Expense ledger", style="Title.TLabel").pack(side="left")
        self.totals = ttk.Label(header)
        self.totals.pack(side="right")
        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=(10, 0))
        ttk.Button(controls, text="＋ Add Expense", command=self.add).pack(side="left")
        ttk.Button(controls, text="Edit", command=self.edit).pack(side="left", padx=5)
        ttk.Button(controls, text="Record Payment", command=self.pay).pack(side="left")
        ttk.Button(controls, text="Void / Restore", command=self.void).pack(side="left", padx=5)
        ttk.Label(controls, text="Filter:").pack(side="left", padx=(18, 4))
        self.filter_var = tk.StringVar()
        entry = ttk.Entry(controls, textvariable=self.filter_var, width=26)
        entry.pack(side="left")
        entry.bind("<KeyRelease>", lambda _e: self.refresh())
        self.tree = make_tree(self, [
            ("name", "Name", 150), ("supplier", "Supplier", 130), ("trade", "Trade", 105),
            ("phase", "Phase", 120), ("date", "Date", 90), ("total", "Total", 100),
            ("paid", "Paid", 100), ("balance", "Balance", 100), ("status", "Status", 90),
            ("authorized", "Authorized by", 140),
        ])

    def phase_map(self):
        return {r["name"]: r["id"] for r in self.db.all(
            "SELECT id,name FROM phases WHERE project_id=? ORDER BY sort_order,id", (self.project_id,)
        )}

    def expense_form(self, initial=None):
        fields = []
        for spec in self.BASE_FIELDS:
            fields.append((spec[0], spec[1], [""] + list(self.phase_map())) if spec[0] == "phase" else spec)
        return dialog(
            self, "Expense", fields, initial,
            required_keys=("name", "qty", "unit_price", "expense_date"),
        )

    def save_values(self, data, expense_id=None, authorized_head_id=None):
        if not data["name"]:
            raise ValueError("Expense name is required.")
        quantity = qty_decimal(data["qty"])
        unit_price = cents(data["unit_price"])
        if unit_price < 0:
            raise ValueError("Unit price cannot be negative.")
        total = int((quantity * unit_price).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        values = (
            data["name"], data["item"], data["dimensions"], data["supplier"], str(quantity),
            data["unit"], unit_price, total, self.phase_map().get(data["phase"]),
            data["area"], data["trade"], valid_date(data["expense_date"], True),
            valid_date(data["due_date"]), data["invoice_no"], data["notes"],
        )
        if expense_id:
            self.db.execute(
                """UPDATE expenses SET name=?,item=?,dimensions=?,supplier=?,qty=?,unit=?,
                   unit_price_cents=?,total_cents=?,phase_id=?,area=?,trade=?,expense_date=?,
                   due_date=?,invoice_no=?,notes=? WHERE id=?""", values + (expense_id,)
            )
            self.db.audit(self.project_id, "EXPENSE_EDITED", f"#{expense_id} {data['name']}")
        else:
            self.db.execute(
                """INSERT INTO expenses(project_id,name,item,dimensions,supplier,qty,unit,
                   unit_price_cents,total_cents,phase_id,area,trade,expense_date,due_date,invoice_no,notes,
                   authorized_by_head_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self.project_id,) + values + (authorized_head_id,)
            )
            self.db.audit(self.project_id, "EXPENSE_ADDED", data["name"])

    def add(self):
        if not self.require_project():
            return
        data = self.expense_form({"qty": "1", "expense_date": date.today().isoformat()})
        if data:
            try:
                quantity = qty_decimal(data["qty"]); total = int(quantity * cents(data["unit_price"]))
                head = self.app.authorize(
                    "Add expense",
                    f"{data['name']} — {money(total)}\nSupplier: {data['supplier'] or 'Not specified'}"
                )
                if not head: return
                self.save_values(data, authorized_head_id=head["id"])
                self.db.audit(self.project_id, "EXPENSE_AUTHORIZED", f"{data['name']} by {head['name']}")
                self.app.refresh_all()
            except (ValueError, sqlite3.Error) as exc:
                messagebox.showerror(APP_TITLE, str(exc))

    def edit(self):
        expense_id = self.selected_id(self.tree)
        if not expense_id:
            return
        row = self.db.one(
            """SELECT e.*,COALESCE(p.name,'') phase FROM expenses e
               LEFT JOIN phases p ON p.id=e.phase_id WHERE e.id=?""", (expense_id,)
        )
        initial = dict(row)
        initial["unit_price"] = money(row["unit_price_cents"])
        data = self.expense_form(initial)
        if data:
            try:
                self.save_values(data, expense_id)
                self.app.refresh_all()
            except (ValueError, sqlite3.Error) as exc:
                messagebox.showerror(APP_TITLE, str(exc))

    def pay(self):
        expense_id = self.selected_id(self.tree)
        if not expense_id:
            return
        row = self.db.one(
            """SELECT e.*,COALESCE(SUM(p.amount_cents),0) paid FROM expenses e
               LEFT JOIN payments p ON p.expense_id=e.id AND p.accounting_excluded=0
               WHERE e.id=? GROUP BY e.id""", (expense_id,)
        )
        if row["voided"]:
            messagebox.showerror(APP_TITLE, "Restore this expense before recording payment.")
            return
        balance = row["total_cents"] - row["paid"]
        data = dialog(self, "Record Payment", [
            ("amount", f"Amount (balance {money(balance)})"),
            ("payment_date", "Payment date (YYYY-MM-DD)"),
            ("method", "Method", ["Cash", "Bank Transfer", "Check", "Card", "Other"]),
            ("reference", "Reference"), ("notes", "Notes"),
        ], {"amount": money(balance), "payment_date": date.today().isoformat()},
           required_keys=("amount", "payment_date", "method"))
        if data:
            try:
                amount = cents(data["amount"])
                if amount <= 0 or amount > balance:
                    raise ValueError("Payment must be greater than zero and no more than the balance.")
                self.db.execute(
                    """INSERT INTO payments(expense_id,amount_cents,payment_date,method,reference,notes)
                       VALUES(?,?,?,?,?,?)""",
                    (expense_id, amount, valid_date(data["payment_date"], True),
                     data["method"], data["reference"], data["notes"]),
                )
                self.db.audit(self.project_id, "PAYMENT_RECORDED", f"Expense #{expense_id}: {money(amount)}")
                self.app.refresh_all()
            except (ValueError, sqlite3.Error) as exc:
                messagebox.showerror(APP_TITLE, str(exc))

    def void(self):
        expense_id = self.selected_id(self.tree)
        if expense_id and messagebox.askyesno(
            APP_TITLE, "Void or restore the selected expense?\n\nThe audit history will be retained."
        ):
            self.db.execute(
                "UPDATE expenses SET voided=CASE voided WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (expense_id,)
            )
            self.db.audit(self.project_id, "EXPENSE_VOID_TOGGLED", str(expense_id))
            self.app.refresh_all()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        if not self.project_id:
            self.totals.config(text="")
            return
        search = f"%{self.filter_var.get().strip()}%"
        rows = self.db.all(
            """SELECT e.*,COALESCE(ph.name,'') phase,COALESCE(h.name,'') authorized_by,
               COALESCE(SUM(p.amount_cents),0) paid
               FROM expenses e LEFT JOIN phases ph ON ph.id=e.phase_id
               LEFT JOIN payments p ON p.expense_id=e.id AND p.accounting_excluded=0
               LEFT JOIN project_heads h ON h.id=e.authorized_by_head_id
               WHERE e.project_id=? AND (e.name LIKE ? OR e.item LIKE ? OR e.supplier LIKE ?
                 OR e.trade LIKE ? OR e.area LIKE ? OR e.expense_date LIKE ? OR ph.name LIKE ?)
               GROUP BY e.id ORDER BY e.expense_date DESC,e.id DESC""",
            (self.project_id,) + (search,) * 7,
        )
        committed = paid_total = outstanding = 0
        for row in rows:
            balance = row["total_cents"] - row["paid"]
            status = "VOID" if row["voided"] else (
                "Paid" if balance == 0 else "Partial" if row["paid"] else "Unpaid"
            )
            if not row["voided"]:
                committed += row["total_cents"]
                paid_total += row["paid"]
                outstanding += balance
            self.tree.insert("", "end", iid=row["id"], values=(
                row["name"], row["supplier"], row["trade"], row["phase"], row["expense_date"],
                money(row["total_cents"]), money(row["paid"]), money(balance), status,
                row["authorized_by"] or "Legacy / not recorded",
            ))
        self.totals.config(
            text=f"Committed {money(committed)}   |   Paid {money(paid_total)}   |   Outstanding {money(outstanding)}"
        )


class ExpenseImportReviewDialog(tk.Toplevel):
    """Review a complete import form; invalid rows are never silently skipped."""
    def __init__(self, parent, filename, metadata, reviews):
        super().__init__(parent)
        self.title("Review Expense Import")
        self.geometry("1000x620")
        self.minsize(820, 500)
        self.result = False
        self.reviews = reviews
        body = ttk.Frame(self, padding=18); body.pack(fill="both", expand=True)
        ttk.Label(body, text="Review expense import", style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(
            body,
            text=f"{Path(filename).name}  |  Draft {metadata.get('draft_reference') or 'not supplied'}",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 10))
        valid = [review for review in reviews if review.get("item")]
        invalid = [review for review in reviews if not review.get("item")]
        calculated = sum(review["item"]["total_cents"] for review in valid)
        try:
            declared = cents(metadata.get("declared_total", ""))
            declared_error = "" if metadata.get("declared_total", "").strip() else "Enter the declared batch total in the form."
        except ValueError:
            declared, declared_error = 0, "The declared batch total is not a valid amount."
        reconciled = not declared_error and declared == calculated
        summary_color = GREEN if not invalid and reconciled and reviews else RED
        self.summary = ttk.Label(
            body,
            text=(f"Rows: {len(reviews)}  |  Ready: {len(valid)}  |  Needs correction: {len(invalid)}  |  "
                  f"Declared: {money(declared)}  |  Calculated: {money(calculated)}"),
            foreground=summary_color, style="Section.TLabel",
        )
        self.summary.pack(anchor="w", pady=(0, 8))
        if declared_error or (not reconciled and not declared_error):
            message = declared_error or (
                f"Declared total differs from the valid-row total by {money(abs(declared - calculated))}."
            )
            ttk.Label(body, text=message, foreground=RED).pack(anchor="w", pady=(0, 8))
        columns = [
            ("row", "Source row", 78), ("project", "Project", 145),
            ("item", "Item / description", 220), ("total", "Total", 95),
            ("status", "Review status", 115), ("message", "Validation message", 310),
        ]
        tree = make_tree(body, columns)
        for index, review in enumerate(reviews):
            item = review.get("item")
            source = review.get("source", {})
            tree.insert("", "end", iid=str(index), values=(
                source.get("source_row", ""),
                item["project_name"] if item else source.get("project", ""),
                item["item"] if item else source.get("item", ""),
                money(item["total_cents"]) if item else "—",
                "Ready" if item else "Needs correction",
                review.get("error", "Ready to stage"),
            ), tags=("ready" if item else "invalid",))
        tree.tag_configure("ready", foreground="#047857")
        tree.tag_configure("invalid", foreground="#B91C1C", background="#FEF2F2")
        footer = ttk.Frame(body); footer.pack(fill="x", pady=(12, 0))
        ttk.Label(
            footer,
            text="No row is imported unless the complete form passes review.",
            style="Muted.TLabel",
        ).pack(side="left")
        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side="right")
        stage = ttk.Button(
            footer, text="Stage Complete Form", style="Primary.TButton", command=self.accept,
        )
        stage.pack(side="right", padx=(0, 8))
        if invalid or not reconciled or not reviews:
            stage.configure(state="disabled")
        self.transient(parent); self.grab_set(); self.bind("<Escape>", lambda _e: self.destroy())

    def accept(self):
        self.result = True
        self.destroy()


class BulkExpenseDialog(tk.Toplevel):
    """Stages multiple expense items before project-head authorization."""
    def __init__(self, parent, db, initial_project_id=None):
        super().__init__(parent)
        self.title("Bulk Expense Entry"); self.geometry("1120x720"); self.minsize(980, 650)
        self.db, self.result, self.items = db, None, []
        self.import_metadata = {}
        projects = db.all("SELECT id,name FROM projects WHERE status<>'Completed' ORDER BY name")
        self.projects = {f"{row['name']} [#{row['id']}]": row["id"] for row in projects}
        self.context_project_id = initial_project_id or (projects[0]["id"] if projects else None)
        banks = db.all("SELECT * FROM bank_accounts WHERE active=1 ORDER BY bank_name,account_name")
        self.banks = {
            f"{row['bank_name']} — {row['account_name'] or row['account_number']} (••{row['account_number'][-4:]})": row["id"]
            for row in banks
        }
        keys = ("project", "name", "item", "dimensions", "supplier", "qty", "unit", "unit_price",
                "phase", "area", "trade", "expense_date", "due_date", "invoice_no", "notes", "status",
                "initial_payment", "payment_method", "bank", "cash_allocation")
        self.vars = {key: tk.StringVar() for key in keys}
        self.vars["qty"].set("1"); self.vars["expense_date"].set(date.today().isoformat())
        self.vars["status"].set("Unpaid"); self.vars["payment_method"].set("Cash")
        if self.banks: self.vars["bank"].set(next(iter(self.banks)))
        if self.projects:
            preferred = next((label for label, pid in self.projects.items() if pid == initial_project_id), None)
            self.vars["project"].set(preferred or next(iter(self.projects)))
        body = ttk.Frame(self, padding=18); body.pack(fill="both", expand=True)
        top = ttk.Frame(body); top.pack(fill="x")
        ttk.Label(top, text="Add expense items", style="DialogTitle.TLabel").pack(side="left")
        funding = ttk.Frame(top); funding.pack(side="right")
        self.cash_label = ttk.Label(funding, style="Section.TLabel")
        self.cash_label.pack(anchor="e")
        self.cash_after_label = ttk.Label(funding, style="Muted.TLabel")
        self.cash_after_label.pack(anchor="e")
        self.bank_after_label = ttk.Label(funding, style="Muted.TLabel")
        self.bank_after_label.pack(anchor="e")
        self.budget_label = ttk.Label(funding, style="Muted.TLabel")
        self.budget_label.pack(anchor="e")
        form = ttk.Frame(body); form.pack(fill="x", pady=(12, 8))
        specs = [("project", "Project *"), ("item", "Item name / description *"),
                 ("dimensions", "Size / dimensions *"), ("supplier", "Supplier *"), ("qty", "Quantity *"),
                 ("unit_price", "Unit price *"), ("phase", "Phase *"),
                 ("area", "Area / category *"), ("status", "Payment state *"),
                 ("initial_payment", "Paid amount if Partially Paid"),
                 ("payment_method", "Payment method *"), ("bank", "Bank for transfer"),
                 ("cash_allocation", "Cash allocation reference"),
                 ("expense_date", "Expense date *"), ("notes", "Notes (optional)")]
        self.widgets = {}
        for index, (key, label) in enumerate(specs):
            row, col = divmod(index, 4)
            cell = ttk.Frame(form); cell.grid(row=row, column=col, sticky="ew", padx=5, pady=4)
            ttk.Label(cell, text=label).pack(anchor="w")
            if key == "project":
                widget = ttk.Combobox(cell, textvariable=self.vars[key], values=list(self.projects), state="readonly")
                widget.bind("<<ComboboxSelected>>", lambda _e: self.project_changed())
            elif key == "supplier":
                widget = SearchableCombobox(cell, textvariable=self.vars[key])
                widget.bind("<<ComboboxSelected>>", self.supplier_selected)
            elif key in {"phase", "area", "status", "payment_method", "bank", "cash_allocation"}:
                if key == "status": values = ["Paid", "Partially Paid", "Unpaid"]
                elif key == "payment_method": values = ["Cash", "Bank Transfer"]
                elif key == "bank": values = list(self.banks)
                else: values = []
                widget = ttk.Combobox(cell, textvariable=self.vars[key], values=values, state="readonly")
                if key == "area": widget.bind("<<ComboboxSelected>>", self.category_selected)
                if key in {"status", "payment_method"}:
                    widget.bind("<<ComboboxSelected>>", lambda _e: self.update_payment_controls(), add="+")
            elif key == "expense_date":
                holder = ttk.Frame(cell)
                holder.pack(fill="x", pady=(2, 0))
                widget = ttk.Entry(holder, textvariable=self.vars[key])
                widget.pack(side="left", fill="x", expand=True)
                ttk.Button(
                    holder, text="\U0001F4C5", width=3,
                    command=lambda current=self.vars[key]: DatePickerPopup(self, current),
                ).pack(side="right", padx=(5, 0))
                self.widgets[key] = widget
                form.columnconfigure(col, weight=1)
                continue
            else:
                widget = ttk.Entry(cell, textvariable=self.vars[key])
            widget.pack(fill="x", pady=(2, 0)); self.widgets[key] = widget
            form.columnconfigure(col, weight=1)
        actions = ttk.Frame(body); actions.pack(fill="x", pady=(4, 6))
        ttk.Button(actions, text="+ Add Expense Item", style="Primary.TButton", command=self.add_item).pack(side="left")
        ttk.Button(actions, text="Remove Selected", style="Secondary.TButton", command=self.remove_item).pack(side="left", padx=6)
        ttk.Button(actions, text="Create Import Form", command=self.create_import_form).pack(side="left", padx=(2, 6))
        ttk.Button(actions, text="Import Filled Form", command=self.import_filled_form).pack(side="left", padx=(0, 6))
        self.count_label = ttk.Label(actions, text="0 items", style="Muted.TLabel")
        self.count_label.pack(side="left")
        self.commit_button = ttk.Button(
            actions, text="Commit Batch to Expense Ledger", style="Primary.TButton",
            command=self.finish,
        )
        self.commit_button.pack(side="right")
        ttk.Button(
            actions, text="Cancel", style="Secondary.TButton", command=self.destroy
        ).pack(side="right", padx=(0, 8))
        totals = ttk.Frame(body); totals.pack(fill="x", pady=(1, 7))
        for column in range(3):
            totals.columnconfigure(column, weight=1, uniform="batch_totals")
        self.paid_total_label = ttk.Label(totals, text="Paid: 0.00", style="Section.TLabel")
        self.unpaid_total_label = ttk.Label(
            totals, text="Unpaid / Partially Paid: 0.00", style="Section.TLabel"
        )
        self.batch_total_label = ttk.Label(totals, text="Batch total: 0.00", style="Section.TLabel")
        self.paid_total_label.grid(row=0, column=0, sticky="w")
        self.unpaid_total_label.grid(row=0, column=1, sticky="w")
        self.batch_total_label.grid(row=0, column=2, sticky="e")
        self.tree = make_tree(body, [("project", "Project", 150), ("name", "Expense", 145),
            ("item", "Item", 155), ("supplier", "Supplier", 130), ("area", "Area", 120),
            ("qty", "Qty", 55), ("total", "Total", 95), ("status", "Status", 80),
            ("method", "Payment source", 105)])
        self.allocation_options = {}
        self.project_changed(); self.update_payment_controls(); self.transient(parent); self.grab_set()
        self.bind("<Escape>", lambda _e: self.destroy())

    def current_project_id(self):
        return self.projects.get(self.vars["project"].get())

    def project_changed(self):
        project_id = self.current_project_id()
        phases = [row["name"] for row in self.db.all(
            "SELECT name FROM phases WHERE project_id=? ORDER BY sort_order,id", (project_id,)
        )] if project_id else []
        self.widgets["phase"].configure(values=[""] + phases); self.vars["phase"].set("")
        self.refresh_suppliers(); self.refresh_categories()
        self.refresh_cash_allocations()
        if project_id:
            deposited, paid, remaining = self.db.project_budget(project_id)
            self.budget_label.config(text=f"Deposited {money(deposited)} | Payments {money(paid)} | Available {money(remaining)}")
        self.refresh_funding_summary()

    def refresh_cash_allocations(self):
        project_id = self.current_project_id()
        self.allocation_options = self.db.active_allocation_options(project_id) if project_id else {}
        values = ["Intended source not selected"] + list(self.allocation_options)
        self.widgets["cash_allocation"].configure(values=values)
        if self.vars["cash_allocation"].get() not in values:
            self.vars["cash_allocation"].set(values[0])

    def update_payment_controls(self):
        status = self.vars["status"].get()
        method = self.vars["payment_method"].get()
        partial = status == "Partially Paid"
        self.widgets["initial_payment"].configure(state="normal" if partial else "disabled")
        if not partial: self.vars["initial_payment"].set("")
        has_payment = status in {"Paid", "Partially Paid"}
        self.widgets["bank"].configure(state="readonly" if has_payment and "bank" in method.lower() else "disabled")
        cash_state = "readonly" if has_payment and method == "Cash" else "disabled"
        self.widgets["cash_allocation"].configure(state=cash_state)

    def refresh_funding_summary(self):
        cash_on_hand = self.db.cash_summary()[2]
        staged_cash = sum(
            item["payment_amount_cents"] for item in self.items
            if item["payment_amount_cents"] > 0 and "bank" not in item.get("payment_method", "").lower()
        )
        after_batch = cash_on_hand - staged_cash
        self.cash_label.config(
            text=f"Cash on-hand: {money(cash_on_hand)}",
            foreground=GREEN if cash_on_hand >= 0 else RED,
        )
        self.cash_after_label.config(
            text=f"Paid-by-cash staged: {money(staged_cash)} | After batch: {money(after_batch)}",
            foreground=GREEN if after_batch >= 0 else RED,
        )
        staged_bank_items = [
            item for item in self.items
            if item["payment_amount_cents"] > 0 and "bank" in item.get("payment_method", "").lower()
        ]
        staged_bank = sum(item["payment_amount_cents"] for item in staged_bank_items)
        bank_ids = {item.get("bank_account_id") for item in staged_bank_items if item.get("bank_account_id")}
        if not bank_ids:
            selected_bank_id = self.banks.get(self.vars["bank"].get())
            if selected_bank_id:
                bank_ids.add(selected_bank_id)
        available_bank = sum(self.db.bank_balance(bank_id) for bank_id in bank_ids)
        bank_after = available_bank - staged_bank
        self.bank_after_label.config(
            text=(f"Paid-by-bank-transfer staged: {money(staged_bank)} | "
                  f"Bank funds after batch: {money(bank_after)}"),
            foreground=GREEN if bank_after >= 0 else RED,
        )

    def refresh_suppliers(self):
        rows = self.db.all("""SELECT DISTINCT CASE WHEN TRIM(company)<>'' THEN company ELSE name END supplier
            FROM contacts WHERE LOWER(role)='supplier' ORDER BY supplier COLLATE NOCASE""")
        self.widgets["supplier"].set_source(
            ["+ Add Supplier..."] + [row["supplier"] for row in rows if row["supplier"]]
        )

    def supplier_selected(self, _event=None):
        if self.vars["supplier"].get() != "+ Add Supplier...": return
        project_id = self.current_project_id()
        data = dialog(
            self, "Add Supplier", [("company", "Company name"),
            ("contact", "Contact person"), ("phone", "Contact number")],
            required_keys=("company", "contact", "phone"),
        ) if project_id else None
        if not data or not data["company"]:
            self.vars["supplier"].set(""); return
        self.db.execute("""INSERT INTO contacts(project_id,name,role,company,phone,email,address,notes)
            VALUES(?,?,?,?,?,'','','Added from expense supplier list')""",
            (project_id, data["contact"] or data["company"], "Supplier", data["company"], data["phone"]))
        self.refresh_suppliers(); self.vars["supplier"].set(data["company"])

    def refresh_categories(self):
        values = ["+ Add Category..."] + [row["name"] for row in self.db.all(
            "SELECT name FROM expense_categories ORDER BY name COLLATE NOCASE")]
        self.widgets["area"].configure(values=values)
        if self.vars["area"].get() not in values: self.vars["area"].set("")

    def category_selected(self, _event=None):
        if self.vars["area"].get() != "+ Add Category...": return
        value = simpledialog.askstring("Add Expense Category", "Category name:", parent=self)
        if not value: self.vars["area"].set(""); return
        value = value.strip().upper()
        self.db.execute("INSERT OR IGNORE INTO expense_categories(name) VALUES(?)", (value,))
        self.refresh_categories(); self.vars["area"].set(value)

    def _project_label(self, value):
        wanted = str(value or "").strip().casefold()
        for label in self.projects:
            if wanted in {label.casefold(), label.split(" [#")[0].casefold()}:
                return label
        return ""

    @staticmethod
    def _excel_date_text(value):
        value = str(value or "").strip()
        if re.fullmatch(r"\d+(?:\.0+)?", value):
            serial = int(float(value))
            if 20000 <= serial <= 80000:
                return (date(1899, 12, 30) + timedelta(days=serial)).isoformat()
        return value

    def _build_item(self, values, staged_items):
        values = {key: str(value or "").strip() for key, value in values.items()}
        if not self.db.one("SELECT 1 FROM bank_accounts WHERE active=1 LIMIT 1"):
            raise ValueError("Enroll a bank account in Remittances before adding expenses.")
        project_label = self._project_label(values.get("project"))
        project_id = self.projects.get(project_label)
        if not project_id:
            raise ValueError("Project does not match an existing project.")
        _deposited, _paid, remaining = self.db.project_budget(project_id)
        if remaining <= 0:
            raise ValueError("This project has no remaining deposited budget.")
        quantity = qty_decimal(values.get("qty", ""))
        unit_price = cents(values.get("unit_price", ""))
        if quantity <= 0 or unit_price < 0:
            raise ValueError("Quantity must be positive and price cannot be negative.")
        total = int((quantity * unit_price).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        phases = {row["name"].casefold(): row["name"] for row in self.db.all(
            "SELECT name FROM phases WHERE project_id=? ORDER BY sort_order,id", (project_id,)
        )}
        phase = phases.get(values.get("phase", "").casefold())
        if not phase:
            raise ValueError("Phase does not match a phase for the selected project.")
        categories = {row["name"].casefold(): row["name"] for row in self.db.all(
            "SELECT name FROM expense_categories ORDER BY name COLLATE NOCASE"
        )}
        area = categories.get(values.get("area", "").casefold())
        if not area:
            raise ValueError("Area / category does not match an existing category.")
        suppliers = {
            row["supplier"].casefold(): row["supplier"] for row in self.db.all(
                """SELECT DISTINCT CASE WHEN TRIM(company)<>'' THEN company ELSE name END supplier
                   FROM contacts WHERE LOWER(role)='supplier' ORDER BY supplier COLLATE NOCASE"""
            ) if row["supplier"]
        }
        supplier = suppliers.get(values.get("supplier", "").casefold())
        if not supplier:
            raise ValueError("Supplier does not match an existing supplier. Add it in Contacts first.")
        status_lookup = {
            "paid": "Paid", "partially paid": "Partially Paid", "partial": "Partially Paid",
            "unpaid": "Unpaid",
        }
        status = status_lookup.get(values.get("status", "").casefold())
        if not status:
            raise ValueError("Payment State must be Paid, Partially Paid, or Unpaid.")
        entered_initial = cents(values.get("initial_payment", ""))
        if status == "Paid":
            payment_amount = total
        elif status == "Partially Paid":
            payment_amount = entered_initial
            if payment_amount <= 0 or payment_amount >= total:
                raise ValueError("Partially Paid requires a paid amount above zero and below the row total.")
        else:
            payment_amount = 0
            if entered_initial:
                raise ValueError("Paid Amount must be blank or zero for an Unpaid item.")
        payment_method_lookup = {"cash": "Cash", "bank transfer": "Bank Transfer", "bank": "Bank Transfer"}
        payment_method = payment_method_lookup.get(values.get("payment_method", "").casefold())
        if not payment_method:
            raise ValueError("Payment Method must be Cash or Bank Transfer.")
        bank_account_id = None
        cash_allocation_id = None
        if payment_amount > 0 and "bank" in payment_method.lower():
            wanted_bank = values.get("bank", "").casefold()
            bank_label = next((label for label in self.banks if label.casefold() == wanted_bank), "")
            if not bank_label:
                raise ValueError("Select an exact enrolled bank label for the transfer.")
            bank_account_id = self.banks[bank_label]
        elif payment_amount > 0:
            allocation_options = self.db.active_allocation_options(project_id)
            wanted_allocation = values.get("cash_allocation", "").casefold()
            allocation_label = next(
                (label for label in allocation_options
                 if label.casefold() == wanted_allocation or label.split(" | ", 1)[0].casefold() == wanted_allocation),
                "",
            )
            if not allocation_label:
                raise ValueError("Select an active Petty Cash or Direct Procurement reference for paid cash.")
            values["cash_allocation"] = allocation_label
            cash_allocation_id = allocation_options[allocation_label]
        _commit_deposit, _committed, commitment_remaining = self.db.project_commitment_budget(project_id)
        staged_commitments = sum(x["total_cents"] for x in staged_items if x["project_id"] == project_id)
        if staged_commitments + total > commitment_remaining:
            raise ValueError("This row would exceed the project's uncommitted deposited budget.")
        staged_payments = sum(x["payment_amount_cents"] for x in staged_items if x["project_id"] == project_id)
        if staged_payments + payment_amount > remaining:
            raise ValueError("Staged payments exceed this project's remaining deposited budget.")
        if payment_amount > 0 and bank_account_id:
            staged_bank = sum(x["payment_amount_cents"] for x in staged_items
                              if x.get("bank_account_id") == bank_account_id)
            if staged_bank + payment_amount > self.db.bank_balance(bank_account_id):
                raise ValueError("Staged transfers exceed the selected bank balance.")
        elif payment_amount > 0:
            self.db.validate_cash_allocation_payment(project_id, cash_allocation_id, payment_amount)
            staged_allocation = sum(x["payment_amount_cents"] for x in staged_items
                                    if x.get("cash_allocation_id") == cash_allocation_id)
            if staged_allocation + payment_amount > self.db.allocation_balance(cash_allocation_id):
                raise ValueError("Staged cash payments exceed the selected allocation balance.")
        expense_date = self._excel_date_text(values.get("expense_date", ""))
        valid_date(expense_date, True)
        source_reference = values.get("source_reference", "")
        item = dict(values)
        item.update(
            name=values["item"], item=values["item"], project=project_label,
            project_id=project_id, project_name=project_label.split(" [#")[0],
            dimensions=values["dimensions"], supplier=supplier, qty=str(quantity), unit="item",
            unit_price_cents=unit_price, total_cents=total, phase=phase, area=area,
            trade="", status=status, initial_payment=values.get("initial_payment", ""),
            payment_amount_cents=payment_amount, payment_method=payment_method,
            bank_account_id=bank_account_id, cash_allocation_id=cash_allocation_id,
            expense_date=expense_date, due_date="", invoice_no=source_reference,
            notes=values.get("notes", ""),
        )
        return item

    def create_import_form(self):
        draft_reference = "DRF-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        suggested = f"ConTracktor_Expense_Import_{draft_reference}.xlsx"
        path = filedialog.asksaveasfilename(
            parent=self, title="Create Expense Import Form", initialfile=suggested,
            defaultextension=".xlsx", filetypes=[("Excel / Google Sheets form", "*.xlsx")],
        )
        if not path:
            return
        try:
            suppliers = [row["supplier"] for row in self.db.all(
                """SELECT DISTINCT CASE WHEN TRIM(company)<>'' THEN company ELSE name END supplier
                   FROM contacts WHERE LOWER(role)='supplier' ORDER BY supplier COLLATE NOCASE"""
            ) if row["supplier"]]
            phases = [row["name"] for row in self.db.all(
                "SELECT DISTINCT name FROM phases ORDER BY name COLLATE NOCASE"
            ) if row["name"]]
            categories = [row["name"] for row in self.db.all(
                "SELECT name FROM expense_categories ORDER BY name COLLATE NOCASE"
            )]
            allocations = list(self.db.active_allocation_options(None))
            reference_lists = {
                "projects": list(self.projects), "suppliers": suppliers, "phases": phases,
                "categories": categories, "statuses": ["Paid", "Partially Paid", "Unpaid"],
                "methods": ["Cash", "Bank Transfer"], "banks": list(self.banks),
                "allocations": allocations,
            }
            write_expense_import_xlsx(path, draft_reference, reference_lists)
            messagebox.showinfo(
                APP_TITLE,
                "The dropdown-enabled form was created. Open it in Excel or upload it to Google Sheets. "
                "After completing it, download it as Microsoft Excel (.xlsx) and import that file here.\n\n"
                "Dropdowns are a snapshot of current local records; generate a fresh form whenever "
                "projects, suppliers, banks, petty cash, or direct-procurement references change.",
                parent=self,
            )
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"The import form could not be saved:\n{exc}", parent=self)

    def import_filled_form(self):
        if self.items:
            messagebox.showinfo(
                APP_TITLE,
                "Commit or remove the currently staged items before importing a filled form.",
                parent=self,
            )
            return
        path = filedialog.askopenfilename(
            parent=self, title="Import Filled Expense Form",
            filetypes=[("Expense forms", "*.csv *.xlsx"), ("CSV", "*.csv"), ("Excel workbook", "*.xlsx")],
        )
        if not path:
            return
        try:
            metadata, rows = read_expense_import_form(path)
            reviews, staged = [], []
            project_ids = set()
            required = (
                "project", "item", "dimensions", "supplier", "qty", "unit_price",
                "phase", "area", "status", "payment_method", "expense_date",
            )
            for source in rows:
                missing = [dict(EXPENSE_IMPORT_HEADERS)[key].rstrip("*") for key in required
                           if not source.get(key, "").strip()]
                if missing:
                    reviews.append({
                        "source": source, "item": None,
                        "error": "Missing required field(s): " + ", ".join(missing),
                    })
                    continue
                try:
                    item = self._build_item(source, staged)
                    item["import_draft_reference"] = metadata.get("draft_reference", "")
                    item["import_source_file"] = Path(path).name
                    item["import_source_row"] = source.get("source_row", "")
                    staged.append(item); project_ids.add(item["project_id"])
                    reviews.append({"source": source, "item": item, "error": ""})
                except ValueError as exc:
                    reviews.append({"source": source, "item": None, "error": str(exc)})
            if len(project_ids) > 1:
                reviews = [
                    {**review, "item": None,
                     "error": "Use one project per import form so it produces one auditable batch reference."}
                    for review in reviews
                ]
            review_window = ExpenseImportReviewDialog(self, path, metadata, reviews)
            self.wait_window(review_window)
            if not review_window.result:
                return
            self.items = staged
            self.import_metadata = {
                "draft_reference": metadata.get("draft_reference", ""),
                "source_file": Path(path).name,
            }
            if staged:
                label = next(label for label, project_id in self.projects.items()
                             if project_id == staged[0]["project_id"])
                self.vars["project"].set(label)
                self.widgets["project"].configure(state="disabled")
            self.redraw_items()
        except (OSError, ValueError) as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)

    def add_item(self):
        required = (
            "project", "item", "dimensions", "supplier", "qty", "unit_price",
            "phase", "area", "status", "payment_method", "expense_date",
        )
        if flash_missing_fields(self, self.vars, self.widgets, required):
            return
        try:
            values = {key: var.get().strip() for key, var in self.vars.items()}
            item = self._build_item(values, self.items)
            self.items.append(item); self.redraw_items()
            self.widgets["project"].configure(state="disabled")
            for key in ("name", "item", "dimensions", "qty", "unit_price", "initial_payment",
                        "trade", "due_date", "invoice_no", "notes"):
                self.vars[key].set("1" if key == "qty" else "")
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)

    def redraw_items(self):
        self.tree.delete(*self.tree.get_children())
        for index, item in enumerate(self.items):
            self.tree.insert("", "end", iid=str(index), values=(item["project_name"], item["name"], item["item"],
                item["supplier"], item["area"], item["qty"], money(item["total_cents"]), item["status"],
                ((item["payment_method"] + (f" | {item['cash_allocation']}" if item.get("cash_allocation_id") else ""))
                 if item["payment_amount_cents"] > 0 else f"Planned {item['payment_method']}")))
        paid = sum(item["payment_amount_cents"] for item in self.items)
        outstanding = sum(
            max(0, item["total_cents"] - item["payment_amount_cents"]) for item in self.items
        )
        paid_cash = sum(item["payment_amount_cents"] for item in self.items
                        if "bank" not in item["payment_method"].lower())
        paid_bank = paid - paid_cash
        outstanding_cash = sum(
            max(0, item["total_cents"] - item["payment_amount_cents"]) for item in self.items
            if item["payment_amount_cents"] and "bank" not in item["payment_method"].lower()
        )
        outstanding_bank = sum(
            max(0, item["total_cents"] - item["payment_amount_cents"]) for item in self.items
            if item["payment_amount_cents"] and "bank" in item["payment_method"].lower()
        )
        batch_total = paid + outstanding
        self.count_label.config(text=f"{len(self.items)} item(s)")
        self.paid_total_label.config(
            text=f"Paid: {money(paid)}\nCash: {money(paid_cash)} | Bank transfer: {money(paid_bank)}"
        )
        self.unpaid_total_label.config(
            text=(f"Unpaid / partially-paid outstanding: {money(outstanding)}\n"
                  f"Cash partial balance: {money(outstanding_cash)} | Bank partial balance: {money(outstanding_bank)}")
        )
        self.batch_total_label.config(text=f"Batch total: {money(batch_total)}")
        self.refresh_funding_summary()

    def remove_item(self):
        selected = self.tree.selection()
        if selected:
            self.items.pop(int(selected[0])); self.redraw_items()
            if not self.items:
                self.widgets["project"].configure(state="readonly")

    def finish(self):
        if not self.items: messagebox.showinfo(APP_TITLE, "Add at least one expense item.", parent=self); return
        try:
            cash_required = sum(
                item["payment_amount_cents"] for item in self.items
                if item["payment_amount_cents"] > 0 and "bank" not in item.get("payment_method", "").lower()
            )
            cash_available = self.db.cash_summary()[2]
            if cash_required > cash_available:
                raise ValueError(
                    f"Paid cash items require {money(cash_required)}, but cash on-hand is only "
                    f"{money(cash_available)}."
                )
            bank_ids = {
                item.get("bank_account_id") for item in self.items
                if item["payment_amount_cents"] > 0 and "bank" in item.get("payment_method", "").lower()
            }
            for bank_id in bank_ids:
                if not bank_id:
                    raise ValueError("Every paid bank-transfer item must specify a bank account.")
                required = sum(
                    item["payment_amount_cents"] for item in self.items
                    if item["payment_amount_cents"] > 0 and item.get("bank_account_id") == bank_id
                )
                available = self.db.bank_balance(bank_id)
                if required > available:
                    bank = self.db.one("SELECT bank_name FROM bank_accounts WHERE id=?", (bank_id,))
                    raise ValueError(
                        f"Paid transfers from {bank['bank_name']} require {money(required)}, "
                        f"but the bank balance is only {money(available)}."
                    )
            for project_id in {item["project_id"] for item in self.items}:
                required = sum(
                    item["payment_amount_cents"] for item in self.items
                    if item["project_id"] == project_id
                )
                available = self.db.project_budget(project_id)[2]
                if required > available:
                    project = self.db.one("SELECT name FROM projects WHERE id=?", (project_id,))
                    raise ValueError(
                        f"Paid items for {project['name']} require {money(required)}, "
                        f"but its deposited budget is only {money(available)}."
                    )
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)
            return
        self.result = list(self.items)
        self.destroy()


class PaymentHistoryDialog(tk.Toplevel):
    """Readable drill-down for every payment made against one expense."""
    def __init__(self, parent, db, expense_id):
        super().__init__(parent)
        self.title("Expense Payment History")
        self.geometry("820x430")
        self.minsize(700, 360)
        expense = db.one("SELECT name,item,total_cents FROM expenses WHERE id=?", (expense_id,))
        payments = db.all(
            """SELECT p.payment_date,p.amount_cents,p.method,p.reference,p.notes,p.created_at,
                      COALESCE(h.name,'Legacy / not recorded') authorized_by,
                      CASE
                        WHEN ca.id IS NOT NULL THEN ca.reference
                        WHEN LOWER(COALESCE(p.method,''))='cash' THEN 'Legacy / Unlinked Cash'
                        ELSE '—'
                      END allocation_reference,
                      CASE WHEN ca.id IS NULL THEN '—' ELSE 'WD-' || PRINTF('%04d',ca.withdrawal_id) END withdrawal_reference
               FROM payments p
               LEFT JOIN project_heads h ON h.id=p.authorized_by_head_id
               LEFT JOIN cash_allocations ca ON ca.id=p.cash_allocation_id
               WHERE p.expense_id=? AND p.accounting_excluded=0
               ORDER BY p.payment_date DESC,p.id DESC""", (expense_id,)
        )
        paid = sum(row["amount_cents"] for row in payments)
        body = ttk.Frame(self, padding=20); body.pack(fill="both", expand=True)
        ttk.Label(body, text="Payment history", style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(
            body,
            text=(f"{expense['name']} / {expense['item']}  |  Total paid {money(paid)}  |  "
                  f"Outstanding {money(max(0, expense['total_cents'] - paid))}"),
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(3, 12))
        columns = (("date", "Date", 105), ("amount", "Amount", 115), ("mop", "MOP", 105),
                   ("allocation", "Cash allocation", 155), ("withdrawal", "Withdrawal", 105),
                   ("authorized", "Authorized by", 145), ("reference", "Reference", 135),
                   ("notes", "Notes", 190))
        table = ttk.Frame(body); table.pack(fill="both", expand=True)
        tree = ttk.Treeview(table, columns=[col[0] for col in columns], show="headings")
        for key, label, width in columns:
            tree.heading(key, text=label); tree.column(key, width=width, minwidth=75, stretch=True)
        scroll = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True); scroll.pack(side="left", fill="y")
        for index, row in enumerate(payments):
            tree.insert("", "end", iid=str(index), values=(
                row["payment_date"] or row["created_at"][:10], money(row["amount_cents"]),
                row["method"] or "Not recorded", row["allocation_reference"], row["withdrawal_reference"],
                row["authorized_by"], row["reference"], row["notes"],
            ))
        if not payments:
            tree.insert("", "end", values=("No payments recorded", "", "", "", "", "", "", ""))
        ttk.Button(body, text="Close", command=self.destroy).pack(anchor="e", pady=(12, 0))
        self.transient(parent); self.grab_set(); self.bind("<Escape>", lambda _e: self.destroy())
        self.after_idle(lambda: center_toplevel(self))


class ExpenseDetailsDialog(tk.Toplevel):
    """Read-only expense card opened by double-clicking a ledger row."""
    def __init__(self, parent, db, expense_id, edit_callback):
        super().__init__(parent)
        self.title("Expense Details")
        self.geometry("860x570")
        self.minsize(760, 500)
        row = db.one(
            """SELECT e.*,pr.name project,COALESCE(ph.name,'') phase,
                      COALESCE(h.name,'Legacy / not recorded') authorized_by,
                      COALESCE(SUM(p.amount_cents),0) payment_total,
                      COALESCE(GROUP_CONCAT(DISTINCT NULLIF(TRIM(p.method),'')),'') payment_methods,
                      COALESCE((SELECT SUM(t.amount_cents) FROM cash_advances a
                        JOIN cash_advance_transactions t ON t.advance_id=a.id
                        WHERE a.expense_id=e.id AND a.voided=0 AND t.posted=1 AND t.voided=0
                          AND t.txn_type IN ('Cash Repayment','Bank Repayment','Repayment')),0) recovery_total,
                      COALESCE(NULLIF((SELECT GROUP_CONCAT(DISTINCT ca.reference) FROM payments pp
                        JOIN cash_allocations ca ON ca.id=pp.cash_allocation_id
                        WHERE pp.expense_id=e.id),''),
                        (SELECT ca.reference FROM cash_allocations ca
                         WHERE ca.id=e.default_cash_allocation_id),'') allocation_references,
                      COALESCE(NULLIF((SELECT GROUP_CONCAT(DISTINCT 'WD-' || PRINTF('%04d',ca.withdrawal_id))
                        FROM payments pp JOIN cash_allocations ca ON ca.id=pp.cash_allocation_id
                        WHERE pp.expense_id=e.id),''),
                        (SELECT 'WD-' || PRINTF('%04d',ca.withdrawal_id) FROM cash_allocations ca
                         WHERE ca.id=e.default_cash_allocation_id),'') withdrawal_references,
                      COALESCE((SELECT GROUP_CONCAT(DISTINCT vh.name) FROM expense_verification_items vi
                        JOIN expense_verification_approvals va ON va.batch_id=vi.batch_id
                        JOIN project_heads vh ON vh.id=va.head_id WHERE vi.expense_id=e.id),'') verified_by
               FROM expenses e JOIN projects pr ON pr.id=e.project_id
               LEFT JOIN phases ph ON ph.id=e.phase_id
               LEFT JOIN project_heads h ON h.id=e.authorized_by_head_id
               LEFT JOIN payments p ON p.expense_id=e.id AND p.accounting_excluded=0
               WHERE e.id=? GROUP BY e.id""", (expense_id,)
        )
        outstanding = max(0, row["total_cents"] - row["payment_total"])
        status = ("VOID" if row["voided"] else "Paid" if outstanding == 0 and row["total_cents"] > 0
                  else "Partially Paid" if row["payment_total"] > 0 else "Unpaid")
        details = [
            ("Project", row["project"]), ("Status", status),
            ("Verification", row["verification_status"] or "Unverified"),
            ("Verified by", row["verified_by"] or "—"),
            ("Expense name", row["name"]), ("Item / description", row["item"]),
            ("Size / dimensions", row["dimensions"]), ("Supplier", row["supplier"]),
            ("Quantity", row["qty"]), ("Unit", row["unit"]),
            ("Total amount", money(row["total_cents"])), ("Amount recovered", money(row["recovery_total"])),
            ("Net amount", money(max(0,row["total_cents"]-row["recovery_total"]))), ("Amount paid", money(row["payment_total"])),
            ("Outstanding", money(outstanding)), ("MOP", row["payment_methods"] or "Not Paid"),
            ("Cash allocation ref.", row["allocation_references"] or "Legacy / Unlinked"),
            ("Withdrawal ref.", row["withdrawal_references"] or "—"),
            ("Phase", row["phase"]), ("Area / category", row["area"]),
            ("Trade", row["trade"]), ("Expense date", row["expense_date"]),
            ("Due date", row["due_date"]), ("Invoice / reference", row["invoice_no"]),
            ("Authorized by", row["authorized_by"]), ("Notes", row["notes"]),
        ]
        body = ttk.Frame(self, padding=22); body.pack(fill="both", expand=True)
        ttk.Label(body, text="Expense details", style="DialogTitle.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))
        for index, (label, value) in enumerate(details):
            grid_row, pair = index // 2 + 1, index % 2
            label_column, value_column = pair * 2, pair * 2 + 1
            ttk.Label(body, text=label, style="Muted.TLabel").grid(
                row=grid_row, column=label_column, sticky="nw", padx=((0 if not pair else 20), 8), pady=5)
            ttk.Label(body, text=value or "-", wraplength=255, justify="left").grid(
                row=grid_row, column=value_column, sticky="nw", pady=5)
            body.columnconfigure(value_column, weight=1)
        buttons = ttk.Frame(body); buttons.grid(
            row=(len(details) + 1) // 2 + 1, column=0, columnspan=4, sticky="e", pady=(18, 0))
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right", padx=(8, 0))
        def edit_expense():
            self.destroy()
            parent.after_idle(edit_callback)
        ttk.Button(buttons, text="Edit Expense", style="Primary.TButton",
                   command=edit_expense).pack(side="right")
        self.transient(parent); self.grab_set(); self.bind("<Escape>", lambda _e: self.destroy())
        self.after_idle(lambda: center_toplevel(self))


class CashAllocationDialog(tk.Toplevel):
    """Creates a withdrawal-linked petty-cash or direct-procurement allocation."""
    def __init__(self, parent, db, initial_project_id=None, initial_withdrawal_id=None):
        super().__init__(parent)
        self.title("Allocate Withdrawn Cash")
        self.geometry("820x560"); self.minsize(720, 520)
        self.db, self.result = db, None
        self.initial_withdrawal_id = initial_withdrawal_id
        projects = db.all("SELECT id,name FROM projects ORDER BY name")
        self.projects = {f"{row['name']} [#{row['id']}]": row["id"] for row in projects}
        self.context_project_id = initial_project_id or (projects[0]["id"] if projects else None)
        self.vars = {key: tk.StringVar() for key in (
            "withdrawal", "allocation_type", "issuer", "receiver",
            "amount", "allocation_date", "supplier", "purpose", "notes",
        )}
        self.vars["allocation_type"].set("Petty Cash")
        self.vars["allocation_date"].set(date.today().isoformat())
        self.withdrawals, self.heads, self.head_registries = {}, {}, {}
        body = ttk.Frame(self, padding=22); body.pack(fill="both", expand=True)
        ttk.Label(body, text="Allocate withdrawn cash", style="DialogTitle.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(
            body, text="Cash is shared across projects. Withdrawal sources are assigned automatically, oldest first.",
            style="Muted.TLabel", wraplength=740,
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(3, 14))
        specs = [
            ("allocation_type", "Allocation type"), ("amount", "Amount"),
            ("allocation_date", "Allocation date"),
            ("issuer", "Issuer / approving head"), ("receiver", "Receiver / responsible head"),
            ("supplier", "Supplier / payee"),
            ("purpose", "Purpose"), ("notes", "Notes"),
        ]
        self.widgets = {}
        for index, (key, label) in enumerate(specs):
            row, pair = divmod(index, 2); row += 2
            col = pair * 2
            ttk.Label(body, text=label).grid(row=row, column=col, sticky="w", padx=((0 if not pair else 18), 8), pady=6)
            if key == "allocation_type":
                widget = ttk.Combobox(body, textvariable=self.vars[key], values=["Petty Cash", "Direct Procurement"], state="readonly")
                widget.bind("<<ComboboxSelected>>", lambda _e: self.update_type())
            elif key in {"issuer", "receiver"}:
                widget = ttk.Combobox(body, textvariable=self.vars[key], state="readonly")
            elif key == "supplier":
                widget = SearchableCombobox(body, textvariable=self.vars[key])
            else:
                widget = ttk.Entry(body, textvariable=self.vars[key])
            widget.grid(row=row, column=col + 1, sticky="ew", pady=6)
            body.columnconfigure(col + 1, weight=1)
            self.widgets[key] = widget
        self.balance_note = ttk.Label(body, style="Muted.TLabel", wraplength=740)
        self.balance_note.grid(row=7, column=0, columnspan=4, sticky="w", pady=(10, 4))
        buttons = ttk.Frame(body); buttons.grid(row=8, column=0, columnspan=4, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Cancel", style="Secondary.TButton", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Continue to Two-PIN Approval", style="Primary.TButton", command=self.save).pack(side="right")
        self.refresh_context(); self.update_type()
        self.transient(parent); self.grab_set(); self.bind("<Escape>", lambda _e: self.destroy())
        self.after_idle(lambda: center_toplevel(self))

    def project_id(self):
        return self.context_project_id

    def refresh_context(self):
        rows = self.db.all(
            """SELECT r.*,(
                   SELECT h.id FROM project_heads h WHERE h.registry_head_id=r.id AND h.active=1
                   ORDER BY CASE WHEN h.project_id=? THEN 0 ELSE 1 END,h.id LIMIT 1
               ) project_head_id
               FROM head_registry r WHERE r.active=1 ORDER BY r.name COLLATE NOCASE""",
            (self.context_project_id,),
        )
        rows = [row for row in rows if row["project_head_id"]]
        self.heads = {f"{row['name']} - {row['position']}": row["project_head_id"] for row in rows}
        self.head_registries = {f"{row['name']} - {row['position']}": row["id"] for row in rows}
        for key in ("issuer", "receiver"):
            self.widgets[key].configure(values=list(self.heads))
        values = list(self.heads)
        if values:
            self.vars["issuer"].set(values[0])
            self.vars["receiver"].set(values[1] if len(values) > 1 else values[0])
        suppliers = [row["supplier"] for row in self.db.all(
            """SELECT DISTINCT CASE WHEN TRIM(company)<>'' THEN company ELSE name END supplier
               FROM contacts WHERE LOWER(role)='supplier' ORDER BY supplier COLLATE NOCASE"""
        ) if row["supplier"]]
        self.widgets["supplier"].set_source(suppliers)
        self.balance_note.config(
            text=(f"Shared cash on-hand: {money(self.db.cash_summary()[2])} | "
                  f"Unallocated cash: {money(self.db.unallocated_cash())} | "
                  f"Registered heads available: {len(rows)}")
        )

    def update_type(self):
        direct = self.vars["allocation_type"].get() == "Direct Procurement"
        self.widgets["supplier"].configure(state="normal" if direct else "disabled")
        if not direct: self.vars["supplier"].set("")

    def save(self):
        try:
            project_id = self.project_id()
            issuer_id = self.heads.get(self.vars["issuer"].get())
            receiver_id = self.heads.get(self.vars["receiver"].get())
            amount = cents(self.vars["amount"].get())
            if not project_id: raise ValueError("Create a project before allocating withdrawn cash.")
            if not issuer_id or not receiver_id: raise ValueError("Select both registered project heads.")
            if issuer_id == receiver_id: raise ValueError("Issuer and receiver must be different people.")
            if amount <= 0: raise ValueError("Amount must be positive.")
            allocation_date = valid_date(self.vars["allocation_date"].get(), True)
            if self.vars["allocation_type"].get() == "Direct Procurement" and not self.vars["supplier"].get().strip():
                raise ValueError("Supplier or payee is required for Direct Procurement.")
            self.result = {
                "project_id": project_id,
                "allocation_type": self.vars["allocation_type"].get(), "amount_cents": amount,
                "allocation_date": allocation_date, "issuer_head_id": issuer_id,
                "receiver_head_id": receiver_id, "supplier": self.vars["supplier"].get().strip(),
                "issuer_registry_id": self.head_registries.get(self.vars["issuer"].get()),
                "receiver_registry_id": self.head_registries.get(self.vars["receiver"].get()),
                "purpose": self.vars["purpose"].get().strip(), "notes": self.vars["notes"].get().strip(),
            }
            self.destroy()
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)


class ExpensesTab(BaseTab):
    """Cross-project expense ledger with project-budget-aware bulk entry."""
    def __init__(self, app):
        super().__init__(app)
        header = ttk.Frame(self); header.pack(fill="x")
        ttk.Label(header, text="Expense ledger — all projects", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="+ Add Expense Batch", style="Primary.TButton", command=self.add).pack(side="right")
        cards = ttk.Frame(self); cards.pack(fill="x", pady=(12, 8))
        (self.total_card, self.total_value, self.verified_label,
         self.verified_value) = metric_card_with_detail(
            cards, "Filtered expenses", "Verified expenses", INK
        )
        (self.payments_card, self.payments_value, self.payments_outstanding_label,
         self.payments_outstanding_value) = metric_card_with_detail(
            cards, "Payments recorded", "Outstanding payments", GREEN
        )
        (self.cash_card, self.cash_value, self.cash_unallocated_label,
         self.cash_unallocated_value) = metric_card_with_detail(
            cards, "Cash on-hand", "Unallocated cash | Surrendered", ORANGE
        )
        self.deposit_card, self.deposit_value = metric_card(cards, "Project amount deposited", "#2563EB")
        self.budget_card, self.budget_value = metric_card(cards, "Project budget remaining", GREEN)
        (self.contract_card, self.contract_value, self.collectible_label,
         self.collectible_value) = metric_card_with_detail(
            cards, "Total contract amount", "Contract amount collectible", INK
        )
        layout_metric_cards(cards, (
            self.total_card, self.payments_card, self.cash_card, self.deposit_card,
            self.budget_card, self.contract_card,
        ))
        self.reconciliation_label = ttk.Label(
            self,
            text="Cash on-hand is shared across projects. Project budget remaining = deposits − all active expenses.",
            style="Muted.TLabel",
        )
        self.reconciliation_label.pack(anchor="w", pady=(0, 7))
        self.head_cash_frame = ttk.Frame(self)
        self.head_cash_frame.pack(fill="x", pady=(0, 8))
        self.expense_notebook = ttk.Notebook(self)
        self.expense_notebook.pack(fill="both", expand=True)
        self.ledger_page = ttk.Frame(self.expense_notebook, padding=(2, 6))
        self.cash_page = ttk.Frame(self.expense_notebook, padding=(2, 6))
        self.expense_notebook.add(self.ledger_page, text="Expense Ledger")
        self.expense_notebook.add(self.cash_page, text="Petty Cash & Direct Procurement")
        filters = ttk.Frame(self.ledger_page); filters.pack(fill="x")
        self.filter_var = tk.StringVar()
        filter_definitions = (
            ("Project", 20), ("Status", 13), ("Verification", 14), ("MOP", 15),
            ("Area", 16), ("Supplier", 17),
        )
        for column in range(7):
            filters.columnconfigure(column, weight=1, uniform="expense_filters")
        for index, (label, width) in enumerate(filter_definitions):
            group = ttk.Frame(filters); group.grid(
                row=0, column=index, sticky="ew", padx=(0, 5), pady=(0, 3)
            )
            ttk.Label(group, text=label).pack(anchor="w")
            if label == "Status":
                self.status_selector = StatusChecklist(group, command=self.refresh)
                self.status_selector.pack(fill="x")
                continue
            if label == "Verification":
                self.verification_selector = VerificationChecklist(group, command=self.refresh)
                self.verification_selector.pack(fill="x")
                continue
            if label == "MOP":
                self.mop_selector = PaymentMethodChecklist(group, command=self.refresh)
                self.mop_selector.pack(fill="x")
                continue
            if label == "Project":
                self.project_selector = ProjectChecklist(group, command=self.refresh)
                self.project_selector.pack(fill="x")
                continue
            selector = DynamicChecklist(
                group,
                all_label=f"All {label}s",
                none_label=f"No {label}s",
                plural_label=label.lower() + "s",
                command=self.refresh,
            )
            selector.pack(fill="x")
            setattr(self, f"{label.lower()}_selector", selector)
        search_group = ttk.Frame(filters); search_group.grid(
            row=0, column=6, sticky="ew", pady=(0, 3)
        )
        ttk.Label(search_group, text="Search").pack(anchor="w")
        search = ttk.Entry(search_group, textvariable=self.filter_var, width=16); search.pack(fill="x")
        search.bind("<KeyRelease>", lambda _e: self.refresh())
        date_filters = ttk.Frame(self.ledger_page); date_filters.pack(fill="x", pady=(3, 0))
        today = date.today().isoformat()
        self.date_from_filter = tk.StringVar(value=today)
        self.date_to_filter = tk.StringVar(value=today)
        self.funding_option_map = {}
        ttk.Label(date_filters, text="Funding source").pack(side="left")
        self.funding_selector = DynamicChecklist(
            date_filters, "All Funding Sources", "No Funding Sources", "funding sources",
            command=self.refresh, width=28,
        )
        self.funding_selector.pack(side="left", fill="x", padx=(4, 12))
        ttk.Label(date_filters, text="Expense date").pack(side="left")
        for label, variable, boundary in (("From", self.date_from_filter, "from"),
                                           ("To", self.date_to_filter, "to")):
            ttk.Label(date_filters, text=label).pack(side="left", padx=(12, 4))
            entry = ttk.Entry(date_filters, textvariable=variable, width=12, state="readonly")
            entry.pack(side="left")
            entry.bind("<Button-1>", lambda _event, which=boundary: self.open_date_filter(which))
            ttk.Button(date_filters, text="ðŸ“…", width=3,
                       command=lambda which=boundary: self.open_date_filter(which)).pack(side="left", padx=(3, 0))
            date_filters.winfo_children()[-1].configure(text="\U0001F4C5")
            setattr(self, f"date_{boundary}_entry", entry)
        ttk.Button(date_filters, text="All Dates", command=self.clear_date_filters).pack(side="left", padx=12)
        controls = ttk.Frame(self.ledger_page); controls.pack(fill="x", pady=(4, 0))
        ttk.Button(controls, text="Edit (all heads)", command=self.edit).pack(side="left")
        ttk.Button(controls, text="Record Payment", command=self.pay).pack(side="left", padx=5)
        ttk.Button(controls, text="Verify Selected", command=self.verify_selected).pack(side="left")
        ttk.Button(controls, text="Void / Restore", command=self.void).pack(side="left")
        ttk.Button(controls, text="Export Filtered PDF", command=self.export_pdf).pack(side="right")
        self.tree = make_tree(self.ledger_page, [("project", "Project", 135), ("batch", "Batch Ref.", 125),
            ("status", "Payment Status", 120), ("verification", "Verification", 105),
            ("verification_ref", "Verification Ref.", 125), ("name", "Expense", 145), ("mop", "MOP", 105),
            ("bank_ref", "Bank Transfer Ref.", 135),
            ("total", "Total Amount", 105), ("recovered", "Recovered", 95),
            ("net", "Net Amount", 100), ("paid", "Amount Paid", 105),
            ("outstanding", "Outstanding Amount", 125), ("date", "Payment Dates â–¾", 125),
            ("allocation", "Cash Allocation Ref.", 150), ("withdrawal", "Withdrawal Ref.", 115),
            ("item", "Item", 145), ("supplier", "Supplier", 125), ("area", "Area", 115),
            ("phase", "Phase", 105),
            ("authorized", "Authorized by", 125)])
        self.tree.configure(selectmode="extended")
        self.tree.tag_configure("paid", background="#ECFDF5", foreground="#065F46")
        self.tree.tag_configure("unpaid", background="#FEF2F2", foreground="#991B1B")
        self.tree.tag_configure("pending", background="#FFF7ED", foreground="#9A3412")
        self.tree.tag_configure("pending-partial", background="#FFF7ED", foreground="#9A3412")
        self.tree.tag_configure("void", background="#F3F4F6", foreground="#6B7280")
        self.tree.bind("<ButtonRelease-1>", self._ledger_click, add="+")
        self.tree.bind("<Double-1>", self._ledger_double_click, add="+")
        self.tree.full_ledger_callback = self._ledger_size_changed
        self.current_rows = []
        self._build_cash_allocation_tab()

    def _build_cash_allocation_tab(self):
        toolbar = ttk.Frame(self.cash_page); toolbar.pack(fill="x", pady=(0, 8))
        ttk.Label(toolbar, text="Scope").pack(side="left")
        self.cash_project_filter = tk.StringVar(value="Shared Cash Pool")
        self.cash_project_combo = ttk.Combobox(
            toolbar, textvariable=self.cash_project_filter, state="readonly", width=28
        )
        self.cash_project_combo.pack(side="left", padx=(6, 10))
        self.cash_project_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_cash_tab())
        ttk.Button(toolbar, text="+ Allocate Withdrawal", style="Primary.TButton",
                   command=self.issue_cash_allocation).pack(side="right")
        ttk.Button(toolbar, text="Deposit All Surrendered", style="Primary.TButton",
                   command=self.deposit_surrendered_cash).pack(side="right", padx=(0, 6))
        ttk.Button(toolbar, text="Surrender / Close", command=self.surrender_cash_allocation).pack(
            side="right", padx=(0, 6))

        summary = ttk.Frame(self.cash_page); summary.pack(fill="x", pady=(0, 8))
        self.cash_summary_values = {}
        for key, title, color in (
            ("unallocated", "Unallocated shared cash", GREEN),
            ("petty", "Active petty cash", ORANGE),
            ("direct", "Direct procurement reserved", "#2563EB"),
            ("surrendered", "Surrendered / returned", INK),
        ):
            card, value = metric_card(summary, title, color)
            card.pack(side="left", fill="x", expand=True, padx=(0, 6))
            self.cash_summary_values[key] = value

        pane = ttk.Panedwindow(self.cash_page, orient="vertical")
        pane.pack(fill="both", expand=True)
        allocations = ttk.Labelframe(pane, text="Withdrawal allocations", padding=6)
        transactions = ttk.Labelframe(pane, text="Allocation activity", padding=6)
        repayments = ttk.Labelframe(
            pane, text="Employee cash repayments surrendered for bank deposit", padding=6
        )
        pane.add(allocations, weight=3); pane.add(transactions, weight=2)
        pane.add(repayments, weight=2)
        self.allocation_tree = make_tree(allocations, [
            ("reference", "Reference", 155), ("project", "Scope", 125),
            ("type", "Type", 125), ("holder", "Holder / Payee", 145),
            ("withdrawal", "Withdrawal", 100), ("issued", "Issued", 105),
            ("spent", "Money Out", 105), ("repayment", "Repayment Surrendered", 135),
            ("net_used", "Net Expense", 105), ("remaining", "Spendable Remaining", 125),
            ("date", "Date & Time", 145), ("status", "Status", 100),
        ])
        self.allocation_tree.bind("<<TreeviewSelect>>", lambda _e: self._refresh_allocation_transactions())
        self.allocation_txn_tree = make_tree(transactions, [
            ("date", "Date & Time", 145), ("reference", "Allocation", 155),
            ("type", "Activity", 120), ("amount", "Amount", 105),
            ("expense", "Expense", 175), ("actor", "Recorded / authorized by", 155),
            ("notes", "Notes", 230),
        ])
        self.repayment_surrender_tree = make_tree(repayments, [
            ("reference", "Surrender Ref.", 145), ("date", "Date & Time", 145),
            ("employee", "Employee", 145), ("advance", "Advance Ref.", 145),
            ("allocation", "Original Cash Allocation", 155), ("amount", "Amount", 105),
            ("receiver", "Received / authorized by", 155), ("status", "Status", 120),
            ("redeposit", "Redeposit Ref.", 140), ("notes", "Notes", 220),
        ])

    def issue_cash_allocation(self, initial_withdrawal_id=None):
        project_id = self.project_options().get(self.cash_project_filter.get()) or self.project_id
        win = CashAllocationDialog(
            self, self.db, project_id, initial_withdrawal_id=initial_withdrawal_id
        ); self.wait_window(win)
        if not win.result:
            return
        data = win.result
        approval = self.app.authorize_two_registered_heads(
            "Issue cash allocation",
            f"Shared {data['allocation_type']} of {money(data['amount_cents'])}; withdrawal sources use FIFO",
            role_one="Issuer / approving head", role_two="Receiver / responsible head",
            registry_ids=[data["issuer_registry_id"], data["receiver_registry_id"]],
        )
        if not approval:
            return
        try:
            allocation_id = self.db.create_cash_allocation(**data)
            row = self.db.one("SELECT reference FROM cash_allocations WHERE id=?", (allocation_id,))
            self.app.refresh_all()
            messagebox.showinfo(
                APP_TITLE,
                f"Cash allocation {row['reference']} is now active.\n\n"
                f"FIFO sources: {self.db.allocation_source_text(allocation_id)}\n\n"
                "Use this reference when recording cash expenses.",
                parent=self,
            )
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)

    def surrender_cash_allocation(self):
        selection = self.allocation_tree.selection()
        allocation_id = int(selection[0]) if selection else None
        if not allocation_id:
            return
        row = self.db.one("SELECT * FROM cash_allocations WHERE id=?", (allocation_id,))
        if not row or row["status"] not in {"Active", "Partially Used", "Open"}:
            messagebox.showinfo(APP_TITLE, "Select an active allocation to surrender.", parent=self)
            return
        remaining = self.db.allocation_balance(allocation_id)
        if not messagebox.askyesno(
            APP_TITLE,
            f"Surrender the entire remaining {money(remaining)} from {row['reference']}?\n\n"
            "It will be locked as surrendered cash until deposited back to a bank.",
            parent=self,
        ):
            return
        approval = self.app.authorize_two_registered_heads(
            "Surrender cash allocation",
            f"{row['reference']} | remaining amount {money(remaining)}",
            role_one="Custodian / responsible head", role_two="Issuer / approving head",
            registry_ids=[row["receiver_registry_id"], row["issuer_registry_id"]],
        )
        if not approval:
            return
        try:
            receiver_identity = self.db.project_head_for_registry(row["receiver_registry_id"])
            issuer_identity = self.db.project_head_for_registry(row["issuer_registry_id"])
            if not receiver_identity or not issuer_identity:
                raise ValueError("The receiver and issuer must each remain assigned to at least one project.")
            returned = self.db.close_cash_allocation(
                allocation_id, date.today().isoformat(), receiver_identity["id"],
                issuer_identity["id"], "Closed from Expenses allocation ledger",
            )
            self.app.refresh_all()
            messagebox.showinfo(
                APP_TITLE, f"{money(returned)} is now surrendered and awaiting bank deposit.", parent=self
            )
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)

    def deposit_surrendered_cash(self):
        amount = self.db.surrendered_awaiting_deposit()
        if amount <= 0:
            messagebox.showinfo(APP_TITLE, "There is no surrendered cash awaiting deposit.", parent=self)
            return
        banks = {
            f"{row['bank_name']} - {row['account_name'] or row['account_number']} (..{row['account_number'][-4:]})": row["id"]
            for row in self.db.all(
                "SELECT * FROM bank_accounts WHERE active=1 ORDER BY bank_name,account_name"
            )
        }
        data = dialog(
            self, "Deposit All Surrendered Cash",
            [("_amount", "Full surrendered amount", None, "display"),
             ("bank", "Destination bank", list(banks)),
             ("deposit_date", "Deposit date"), ("notes", "Notes")],
            {"_amount": money(amount), "bank": next(iter(banks), ""),
             "deposit_date": date.today().isoformat()},
            required_keys=("bank", "deposit_date"),
        )
        if not data:
            return
        bank_id = banks.get(data["bank"])
        if not bank_id:
            messagebox.showerror(APP_TITLE, "Select the destination bank account.", parent=self)
            return
        head = self.app.authorize_registered_head(
            "Deposit all surrendered cash",
            f"Deposit the full surrendered balance of {money(amount)} to {data['bank']}",
        )
        if not head:
            return
        try:
            reference, deposited = self.db.redeposit_all_surrendered(
                bank_id, valid_date(data["deposit_date"], True), head["id"], data["notes"]
            )
            self.app.refresh_all()
            messagebox.showinfo(
                APP_TITLE,
                f"{reference} deposited {money(deposited)}. The surrendered-cash bucket is now clear.",
                parent=self,
            )
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)

    def _refresh_cash_tab(self):
        if not hasattr(self, "allocation_tree"):
            return
        projects = self.project_options()
        choices = ["Shared Cash Pool"]
        self.cash_project_combo.configure(values=choices)
        if self.cash_project_filter.get() not in choices:
            self.cash_project_filter.set("Shared Cash Pool")
        project_id = None
        summary = self.db.cash_allocation_summary(project_id)
        for key, widget in self.cash_summary_values.items():
            widget.config(text=money(summary[key]))
        rows = self.db.cash_allocation_rows(project_id)
        records = []
        for row in rows:
            remaining = max(0, row["amount_cents"] - row["spent_cents"] - row["returned_cents"])
            net_used = max(0, row["spent_cents"] - row["repayment_surrendered_cents"])
            records.append((row["id"], (
                row["reference"], "Shared Cash Pool", row["allocation_type"],
                row["holder"] or row["supplier"] or "—", row["withdrawal_references"] or "—",
                money(row["amount_cents"]), money(row["spent_cents"]),
                money(row["repayment_surrendered_cents"]), money(net_used), money(remaining),
                row["allocation_time"] or row["allocation_date"], row["status"],
            ), ()))
        self.allocation_tree.delete(*self.allocation_tree.get_children())
        for iid, values, tags in records:
            self.allocation_tree.insert("", "end", iid=iid, values=values, tags=tags)
        children = self.allocation_tree.get_children()
        if children:
            self.allocation_tree.selection_set(children[0]); self.allocation_tree.focus(children[0])
        self._refresh_allocation_transactions()
        self._refresh_repayment_surrenders()

    def _refresh_repayment_surrenders(self):
        if not hasattr(self, "repayment_surrender_tree"):
            return
        rows = self.db.all(
            """SELECT s.*,e.name employee,COALESCE(NULLIF(t.reference,''),
                      'CA-' || PRINTF('%06d',t.id)) advance_reference,
                      COALESCE(a.reference,'Legacy / Unlinked') allocation_reference,
                      COALESCE(h.name,'Legacy / not recorded') receiver,
                      COALESCE(d.reference,'—') redeposit_reference
               FROM cash_repayment_surrenders s
               JOIN cash_advance_transactions t ON t.id=s.advance_transaction_id
               JOIN cash_advances ca ON ca.id=s.advance_id
               JOIN employees e ON e.id=ca.employee_id
               LEFT JOIN cash_allocations a ON a.id=s.cash_allocation_id
               LEFT JOIN project_heads h ON h.id=s.received_by_head_id
               LEFT JOIN cash_redeposits d ON d.id=s.redeposit_id
               ORDER BY s.surrender_date DESC,s.id DESC"""
        )
        self.repayment_surrender_tree.delete(*self.repayment_surrender_tree.get_children())
        for row in rows:
            self.repayment_surrender_tree.insert("", "end", iid=row["id"], values=(
                row["reference"], row["transaction_time"] or row["surrender_date"],
                row["employee"], row["advance_reference"], row["allocation_reference"],
                money(row["amount_cents"]), row["receiver"], row["status"],
                row["redeposit_reference"], row["notes"],
            ))

    def _refresh_allocation_transactions(self):
        if not hasattr(self, "allocation_txn_tree"):
            return
        selection = self.allocation_tree.selection()
        allocation_id = int(selection[0]) if selection else None
        where, params = ("t.allocation_id=?", [allocation_id]) if allocation_id else ("1=0", [])
        rows = self.db.all(
            f"""SELECT t.*,a.reference,COALESCE(e.name,'') expense,
                       COALESCE(h.name,'System / legacy') actor
                FROM cash_allocation_transactions t
                JOIN cash_allocations a ON a.id=t.allocation_id
                LEFT JOIN expenses e ON e.id=t.expense_id
                LEFT JOIN project_heads h ON h.id=t.actor_head_id
                WHERE {where} ORDER BY t.txn_date DESC,t.id DESC""", tuple(params)
        )
        self.allocation_txn_tree.delete(*self.allocation_txn_tree.get_children())
        for row in rows:
            self.allocation_txn_tree.insert(
                "", "end", iid=row["id"],
                values=(row["transaction_time"] or row["txn_date"], row["reference"],
                        "Cash Advance Release" if row["txn_type"]=="Expense Payment" and
                        row["expense"].upper().startswith("CASH ADVANCE") else row["txn_type"],
                        money(row["amount_cents"]), row["expense"], row["actor"], row["notes"]),
            )

    def _refresh_head_cash_breakdown(self, project_id=None):
        for child in self.head_cash_frame.winfo_children():
            child.destroy()
        heads = self.db.all(
            "SELECT id,name,position FROM head_registry WHERE active=1 ORDER BY name COLLATE NOCASE"
        )
        active_rows = self.db.cash_allocation_rows(None, active_only=True)
        by_head = {}
        for row in active_rows:
            if row["allocation_type"] == "Petty Cash" and row["custodian_head_id"]:
                registry_id = row["receiver_registry_id"]
                if not registry_id:
                    linked = self.db.one(
                        "SELECT COALESCE(registry_head_id,id) registry_id FROM project_heads WHERE id=?",
                        (row["custodian_head_id"],),
                    )
                    registry_id = linked["registry_id"] if linked else None
                if registry_id:
                    by_head.setdefault(registry_id, []).append(row)
        ttk.Label(self.head_cash_frame, text="Shared petty cash by project head", style="Muted.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 3))
        for index, head in enumerate(heads):
            items = by_head.get(head["id"], [])
            lines = []
            for item in items[:2]:
                remaining = self.db.allocation_balance(item["id"])
                number = item["reference"].rsplit("-", 1)[-1]
                lines.append(f"{item['reference']}: {money(remaining)}")
            title = head["name"]
            text = title + "\n" + ("  |  ".join(lines) if lines else "No active petty cash")
            card = tk.Label(
                self.head_cash_frame, text=text, anchor="w", justify="left", bg=WHITE, fg=INK,
                padx=8, pady=4, relief="solid", bd=1, font=("Segoe UI", 8),
            )
            card.grid(row=index // 4 + 1, column=index % 4, sticky="ew", padx=(0, 5), pady=(0, 4))
        for column in range(4):
            self.head_cash_frame.columnconfigure(column, weight=1, uniform="head_cash")

    def _clicked_column(self, event):
        column = self.tree.identify_column(event.x)
        try:
            return self.tree["columns"][int(column[1:]) - 1]
        except (ValueError, IndexError, TypeError):
            return ""

    def _ledger_click(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        if not (event.state & 0x0004):
            self.tree.selection_set(item)
        self.tree.focus(item)
        if self._clicked_column(event) == "date":
            self.after_idle(lambda expense_id=int(item): self.show_payment_history(expense_id))

    def _ledger_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if not item or self._clicked_column(event) == "date":
            return
        self.tree.selection_set(item); self.tree.focus(item)
        self.after_idle(lambda expense_id=int(item): self.show_expense_details(expense_id))

    def _ledger_size_changed(self):
        row_count = len(self.tree._records) if self.tree.showing_all else min(20, len(self.tree._records))
        self.app.set_page_content_height(max(1000, 535 + row_count * 36))

    def requested_page_height(self):
        row_count = len(self.tree._records) if self.tree.showing_all else min(20, len(self.tree._records))
        return max(1000, 535 + row_count * 36)

    def show_payment_history(self, expense_id):
        win = PaymentHistoryDialog(self, self.db, expense_id)
        self.wait_window(win)

    def show_expense_details(self, expense_id):
        win = ExpenseDetailsDialog(self, self.db, expense_id, self.edit)
        self.wait_window(win)

    def open_date_filter(self, boundary):
        variable = self.date_from_filter if boundary == "from" else self.date_to_filter
        popup = DatePickerPopup(self, variable)
        self.wait_window(popup)
        date_from, date_to = self.date_from_filter.get(), self.date_to_filter.get()
        if date_from and date_to and date_from > date_to:
            if boundary == "from":
                self.date_to_filter.set(date_from)
            else:
                self.date_from_filter.set(date_to)
        self.refresh()

    def clear_date_filters(self):
        self.date_from_filter.set("")
        self.date_to_filter.set("")
        self.refresh()

    def project_options(self):
        return {f"{row['name']} [#{row['id']}]": row["id"] for row in self.db.all(
            "SELECT id,name FROM projects ORDER BY name")}

    def phase_map(self, project_id):
        return {row["name"]: row["id"] for row in self.db.all(
            "SELECT id,name FROM phases WHERE project_id=? ORDER BY sort_order,id", (project_id,))}

    def add(self):
        if not self.db.one("SELECT 1 FROM bank_accounts WHERE active=1 LIMIT 1"):
            messagebox.showerror(APP_TITLE, "Enroll a bank account in Remittances before adding expenses."); return
        if not self.db.one("SELECT 1 FROM projects WHERE status<>'Completed' LIMIT 1"):
            messagebox.showinfo(
                APP_TITLE, "There are no active projects. Create or reactivate a project before adding expenses."
            ); return
        win = BulkExpenseDialog(self, self.db, self.project_id); self.wait_window(win)
        if not win.result: return
        groups = {}
        for item in win.result: groups.setdefault(item["project_id"], []).append(item)
        try:
            approvals = {}
            paid_items = [item for items in groups.values() for item in items if item["payment_amount_cents"] > 0]
            staged_cash = sum(item["payment_amount_cents"] for item in paid_items
                              if "bank" not in item.get("payment_method", "").lower())
            if staged_cash > self.db.cash_summary()[2]:
                raise ValueError("This batch exceeds the shared cash on hand.")
            allocation_holders = {}
            cash_allocation_ids = {item.get("cash_allocation_id") for item in paid_items
                                   if "bank" not in item.get("payment_method", "").lower()}
            for allocation_id in cash_allocation_ids:
                if not allocation_id:
                    raise ValueError("Every paid cash item requires a Petty Cash or Direct Procurement reference.")
                required = sum(item["payment_amount_cents"] for item in paid_items
                               if item.get("cash_allocation_id") == allocation_id)
                if required > self.db.allocation_balance(allocation_id):
                    raise ValueError("This batch exceeds a selected cash allocation's remaining balance.")
                allocation = self.db.one(
                    """SELECT a.reference,
                              COALESCE(a.receiver_registry_id,ah.registry_head_id,ah.id) holder_registry
                       FROM cash_allocations a
                       JOIN project_heads ah ON ah.id=COALESCE(a.custodian_head_id,a.responsible_head_id)
                       WHERE a.id=?""", (allocation_id,),
                )
                if not allocation:
                    raise ValueError("A selected cash-allocation reference is no longer available.")
                allocation_holders[allocation_id] = allocation
            for project_id, items in groups.items():
                project = self.db.one("SELECT name FROM projects WHERE id=?", (project_id,))
                holder_ids = {
                    allocation_holders[item["cash_allocation_id"]]["holder_registry"]
                    for item in items if item["payment_amount_cents"] > 0
                    and "bank" not in item.get("payment_method", "").lower()
                }
                if len(holder_ids) > 1:
                    raise ValueError(
                        "One expense batch can use paid cash from only one project head. "
                        "Commit separate batches for different petty-cash holders."
                    )
                details = (f"{len(items)} item(s) for {project['name']} totaling "
                           f"{money(sum(x['total_cents'] for x in items))}")
                if holder_ids:
                    registry_id = next(iter(holder_ids))
                    registered = self.app.authorize_registered_head(
                        "Add expense batch", details, registry_id=registry_id,
                    )
                    if not registered:
                        return
                    identity = self.db.project_head_for_registry(registry_id, project_id)
                    if not identity:
                        raise ValueError("The cash custodian must remain assigned to at least one project.")
                    approvals[project_id] = dict(identity)
                    approvals[project_id]["name"] = registered["name"]
                else:
                    approvals[project_id] = self.app.authorize_for_project(
                        project_id, "Add expense batch", details,
                    )
                    if not approvals[project_id]:
                        return
            for bank_id in {item.get("bank_account_id") for item in paid_items if item.get("bank_account_id")}:
                staged_bank = sum(item["payment_amount_cents"] for item in paid_items
                                  if item.get("bank_account_id") == bank_id)
                if staged_bank > self.db.bank_balance(bank_id):
                    raise ValueError("This batch exceeds an enrolled bank account's available balance.")
            with self.db.conn:
                for project_id, items in groups.items():
                    _deposited, _paid, remaining = self.db.project_budget(project_id)
                    _commit_deposit, _committed, commitment_remaining = self.db.project_commitment_budget(project_id)
                    if sum(x["total_cents"] for x in items) > commitment_remaining:
                        raise ValueError("A project's batch exceeds its uncommitted deposited budget.")
                    if remaining <= 0 or sum(x["payment_amount_cents"] for x in items) > remaining:
                        raise ValueError("A project's staged payments exceed its remaining deposited budget.")
                    phases = self.phase_map(project_id)
                    committed_at = local_timestamp()
                    batch_reference = self.db._next_system_reference(
                        "EB", "expense_batches", "reference", committed_at[:10]
                    )
                    import_reference = next(
                        (item.get("import_draft_reference", "") for item in items
                         if item.get("import_draft_reference")), "",
                    )
                    import_file = next(
                        (item.get("import_source_file", "") for item in items
                         if item.get("import_source_file")), "",
                    )
                    batch_notes = f"{len(items)} expense item(s)"
                    if import_reference or import_file:
                        batch_notes += (
                            f" | Imported draft {import_reference or 'unreferenced'}"
                            f" | Source {import_file or 'not recorded'}"
                        )
                    batch_id = self.db.conn.execute(
                        """INSERT INTO expense_batches(reference,project_id,committed_at,
                           authorized_by_head_id,notes) VALUES(?,?,?,?,?)""",
                        (batch_reference, project_id, committed_at, approvals[project_id]["id"],
                         batch_notes),
                    ).lastrowid
                    for item in items:
                        cursor = self.db.conn.execute("""INSERT INTO expenses(project_id,name,item,dimensions,supplier,
                            qty,unit,unit_price_cents,total_cents,phase_id,area,trade,expense_date,due_date,invoice_no,
                            notes,authorized_by_head_id,status,default_cash_allocation_id,expense_batch_id)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (project_id, item["name"], item["item"], item["dimensions"], item["supplier"], item["qty"],
                             item["unit"], item["unit_price_cents"], item["total_cents"], phases.get(item["phase"]),
                             item["area"], item["trade"], item["expense_date"], item["due_date"], item["invoice_no"],
                             ((item["notes"] + " | " if item["notes"] else "") +
                              (f"Import row {item.get('import_source_row')}" if item.get("import_source_row") else "")),
                             approvals[project_id]["id"], item["status"],
                             item.get("cash_allocation_id"), batch_id))
                        if item["payment_amount_cents"] > 0:
                            bank_transfer = "bank" in item["payment_method"].lower()
                            payment_reference = self.db._next_system_reference(
                                "BT", "payments", "system_reference", item["expense_date"]
                            ) if bank_transfer else ""
                            payment_cursor = self.db.conn.execute("""INSERT INTO payments(expense_id,amount_cents,payment_date,method,
                                reference,notes,bank_account_id,authorized_by_head_id,cash_allocation_id,
                                system_reference,transaction_time)
                                VALUES(?,?,?,?,?,'Initial payment from bulk entry',?,?,?,?,?)""",
                                (cursor.lastrowid, item["payment_amount_cents"], item["expense_date"],
                                 item["payment_method"], "", item.get("bank_account_id"),
                                 approvals[project_id]["id"], item.get("cash_allocation_id"),
                                 payment_reference, local_timestamp()))
                            if item.get("cash_allocation_id"):
                                self.db.register_allocation_payment(
                                    item["cash_allocation_id"], payment_cursor.lastrowid,
                                    cursor.lastrowid, item["payment_amount_cents"], item["expense_date"],
                                    approvals[project_id]["id"],
                                )
                    self.db.conn.execute("INSERT INTO audit_log(project_id,action,details) VALUES(?,?,?)",
                        (project_id, "EXPENSE_BATCH_ADDED",
                         f"{batch_reference}: {len(items)} item(s) authorized by {approvals[project_id]['name']}"))
            self.app.refresh_all()
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def verify_selected(self):
        expense_ids = [int(value) for value in self.tree.selection()]
        if not expense_ids:
            messagebox.showinfo(APP_TITLE, "Select one or more expenses to verify.", parent=self)
            return
        rows = self.db.all(
            f"SELECT id,project_id,name,voided FROM expenses WHERE id IN ({','.join('?' for _ in expense_ids)})",
            tuple(expense_ids),
        )
        if any(row["voided"] for row in rows):
            messagebox.showerror(APP_TITLE, "Void expenses cannot be verified.", parent=self)
            return
        groups = {}
        for row in rows:
            groups.setdefault(row["project_id"], []).append(row)
        references = []
        for project_id, project_rows in groups.items():
            project = self.db.one("SELECT name FROM projects WHERE id=?", (project_id,))
            approval = self.app.authorize_two_heads(
                project_id, "Weekly expense verification",
                f"Verify {len(project_rows)} selected expense(s) for {project['name']}.",
                role_one="First verifying head", role_two="Second verifying head",
            )
            if not approval:
                return
            try:
                reference = self.db.verify_expense_batch(
                    project_id, [row["id"] for row in project_rows],
                    [head["id"] for head in approval], date.today().isoformat(),
                    "Verified from the Expenses ledger",
                )
                references.append(reference)
            except (ValueError, sqlite3.Error) as exc:
                messagebox.showerror(APP_TITLE, str(exc), parent=self)
                return
        self.app.refresh_all()
        messagebox.showinfo(
            APP_TITLE,
            "Verification recorded with two-head approval.\n\n" + "\n".join(references),
            parent=self,
        )

    def edit(self):
        expense_id = self.selected_id(self.tree)
        if not expense_id: return
        row = self.db.one("""SELECT e.*,COALESCE(ph.name,'') phase,
            COALESCE((SELECT SUM(amount_cents) FROM payments
                      WHERE expense_id=e.id AND accounting_excluded=0),0) payment_total FROM expenses e
            LEFT JOIN phases ph ON ph.id=e.phase_id WHERE e.id=?""", (expense_id,))
        projects = self.project_options(); current = next((label for label,pid in projects.items() if pid == row["project_id"]), "")
        suppliers = [r["supplier"] for r in self.db.all("""SELECT DISTINCT CASE WHEN TRIM(company)<>'' THEN company
            ELSE name END supplier FROM contacts WHERE LOWER(role)='supplier' ORDER BY supplier COLLATE NOCASE""")]
        areas = [r["name"] for r in self.db.all("SELECT name FROM expense_categories ORDER BY name COLLATE NOCASE")]
        fields = [("project", "Project", list(projects)), ("name", "Expense name"), ("item", "Item / description"),
            ("dimensions", "Size / dimensions"), ("supplier", "Supplier", [""] + suppliers), ("qty", "Quantity"),
            ("unit", "Unit"), ("unit_price", "Unit price"),
            ("phase", "Phase", [""] + list(self.phase_map(row["project_id"]))),
            ("area", "Area", areas), ("trade", "Trade"),
            ("expense_date", "Expense date"), ("due_date", "Due date"),
            ("invoice_no", "Invoice / reference"), ("notes", "Notes")]
        initial = dict(row); initial.update(project=current, unit_price=money(row["unit_price_cents"]))
        data = dialog(self, "Edit Expense — All Heads Required", fields, initial)
        if not data: return
        new_project_id = projects.get(data["project"])
        approvals = []
        for project_id in dict.fromkeys([row["project_id"], new_project_id]):
            result = self.app.authorize_all_heads(project_id, "Edit expense",
                f"Expense #{expense_id}: {row['name']} — every active project head must approve.")
            if not result: return
            approvals.extend(head["name"] for head in result)
        try:
            quantity = qty_decimal(data["qty"]); price = cents(data["unit_price"])
            total = int((quantity * price).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if not new_project_id:
                raise ValueError("Select a project.")
            if total < row["payment_total"]:
                raise ValueError("Expense total cannot be lower than its recorded payments.")
            if new_project_id != row["project_id"] and row["payment_total"]:
                _deposited, _paid, available = self.db.project_budget(new_project_id)
                if row["payment_total"] > available:
                    raise ValueError("The destination project cannot cover this expense's recorded payments.")
            status = "Paid" if row["payment_total"] >= total and total > 0 else (
                "Partially Paid" if row["payment_total"] > 0 else "Unpaid"
            )
            values = (new_project_id, data["name"], data["item"], data["dimensions"], data["supplier"], str(quantity),
                data["unit"], price, total, self.phase_map(new_project_id).get(data["phase"]), data["area"], data["trade"],
                valid_date(data["expense_date"], True), valid_date(data["due_date"]), data["invoice_no"], data["notes"],
                status, expense_id)
            with self.db.conn:
                self.db.conn.execute("""UPDATE expenses SET project_id=?,name=?,item=?,dimensions=?,supplier=?,qty=?,unit=?,
                    unit_price_cents=?,total_cents=?,phase_id=?,area=?,trade=?,expense_date=?,due_date=?,invoice_no=?,notes=?,
                    status=?,verification_status='Unverified',verified_at='' WHERE id=?""", values)
                self.db.conn.execute("INSERT INTO audit_log(project_id,action,details) VALUES(?,?,?)",
                    (new_project_id, "EXPENSE_EDITED_ALL_HEADS", f"#{expense_id} approved by {', '.join(approvals)}"))
            self.app.refresh_all()
        except (ValueError, sqlite3.Error) as exc: messagebox.showerror(APP_TITLE, str(exc))

    def pay(self):
        expense_id = self.selected_id(self.tree)
        if not expense_id: return
        row = self.db.one("""SELECT e.*,COALESCE(SUM(p.amount_cents),0) paid FROM expenses e
            LEFT JOIN payments p ON p.expense_id=e.id AND p.accounting_excluded=0
            WHERE e.id=? GROUP BY e.id""", (expense_id,))
        if row["voided"]: messagebox.showerror(APP_TITLE, "Restore this expense before recording payment."); return
        balance = max(0, row["total_cents"] - row["paid"])
        if balance <= 0:
            messagebox.showinfo(APP_TITLE, "This expense is already paid in full."); return
        _deposited, _paid, available = self.db.project_budget(row["project_id"])
        _withdrawn, _cash_spent, cash_available = self.db.cash_summary()
        banks = {f"{bank['bank_name']} — {bank['account_name'] or bank['account_number']} (••{bank['account_number'][-4:]})": bank["id"]
                 for bank in self.db.all("SELECT * FROM bank_accounts WHERE active=1 ORDER BY bank_name,account_name")}
        # Cash allocations are shared across projects. Show every active source
        # before asking for a PIN; the selected source determines which holder
        # must authorize the completed form.
        allocation_lookup = self.db.active_allocation_options()
        data = dialog(self, "Record Payment", [
            ("_cash_available", "Shared cash on-hand", None, "display"),
            ("_unallocated", "Unallocated cash", None, "display"),
            ("_project_budget", "Project payment budget", None, "display"),
            ("amount", f"Amount (expense balance {money(balance)})"),
            ("payment_date", "Payment date"), ("method", "Method", ["Cash", "Bank Transfer"]),
            ("allocation", "Petty cash / direct procurement ref.", [""] + list(allocation_lookup)),
            ("bank", "Bank account for transfer", [""] + list(banks)),
            ("reference", "Reference"), ("notes", "Notes")],
            {"_cash_available": money(cash_available), "_unallocated": money(self.db.unallocated_cash()),
             "_project_budget": money(available),
             "amount": money(balance), "payment_date": date.today().isoformat()})
        if not data: return
        try:
            amount = cents(data["amount"])
            if amount <= 0 or amount > balance: raise ValueError("Payment must be positive and no more than the balance.")
            bank_account_id = banks.get(data["bank"]) if "bank" in data["method"].lower() else None
            cash_allocation_id = allocation_lookup.get(data["allocation"]) if data["method"] == "Cash" else None
            payment_date = valid_date(data["payment_date"], True)
            self.db.validate_payment_source(
                row["project_id"], amount, data["method"], bank_account_id,
                cash_allocation_id, require_cash_allocation=(data["method"] == "Cash"),
            )
            if cash_allocation_id:
                custody = self.db.one(
                    """SELECT a.reference,
                              COALESCE(a.receiver_registry_id,holder.registry_head_id,holder.id) holder_registry
                       FROM cash_allocations a
                       LEFT JOIN project_heads holder
                         ON holder.id=COALESCE(a.custodian_head_id,a.responsible_head_id)
                       WHERE a.id=? AND a.voided=0
                         AND a.status IN ('Active','Partially Used','Open')""", (cash_allocation_id,),
                )
                if not custody or not custody["holder_registry"]:
                    raise ValueError("The selected petty-cash/direct-procurement reference is no longer active.")
                payment_authorizer = self.app.authorize_registered_head(
                    "Authorize payment from assigned cash",
                    f"{custody['reference']} will pay {money(amount)} toward expense #{expense_id}.",
                    registry_id=custody["holder_registry"],
                )
                if not payment_authorizer:
                    return
                authorizing_identity = self.db.project_head_for_registry(
                    custody["holder_registry"], row["project_id"]
                )
                if not authorizing_identity:
                    raise ValueError("The selected cash holder is not assigned to any active project.")
            else:
                payment_authorizer = self.app.authorize_for_project(
                    row["project_id"],
                    "Authorize bank-transfer payment",
                    f"Expense #{expense_id}: {row['name']} — {money(amount)} from {data['bank']}.",
                )
                if not payment_authorizer:
                    return
                authorizing_identity = payment_authorizer

            # Recheck immediately before committing in case a selected balance
            # changed while the PIN dialog was open.
            self.db.validate_payment_source(
                row["project_id"], amount, data["method"], bank_account_id,
                cash_allocation_id, require_cash_allocation=(data["method"] == "Cash"),
            )
            new_paid = row["paid"] + amount
            system_reference = self.db._next_system_reference(
                "BT", "payments", "system_reference", payment_date
            ) if "bank" in data["method"].lower() else ""
            with self.db.conn:
                payment_cursor = self.db.conn.execute("""INSERT INTO payments(expense_id,amount_cents,payment_date,method,reference,notes,
                    bank_account_id,authorized_by_head_id,cash_allocation_id,system_reference,transaction_time)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (expense_id, amount,
                    payment_date, data["method"], data["reference"], data["notes"],
                    bank_account_id, authorizing_identity["id"], cash_allocation_id,
                    system_reference, local_timestamp()))
                if cash_allocation_id:
                    self.db.register_allocation_payment(
                        cash_allocation_id, payment_cursor.lastrowid, expense_id, amount,
                        payment_date, authorizing_identity["id"],
                    )
                self.db.conn.execute(
                    """UPDATE expenses SET status=?,
                       default_cash_allocation_id=COALESCE(default_cash_allocation_id,?) WHERE id=?""",
                    ("Paid" if new_paid >= row["total_cents"] else "Partially Paid",
                     cash_allocation_id, expense_id),
                )
            self.db.audit(row["project_id"], "PAYMENT_RECORDED",
                          f"Expense #{expense_id}: {money(amount)} via {data['method']} authorized by "
                          f"{payment_authorizer['name']}")
            self.app.refresh_all()
        except (ValueError, sqlite3.Error) as exc: messagebox.showerror(APP_TITLE, str(exc))

    def void(self):
        expense_id = self.selected_id(self.tree)
        if expense_id:
            project_row = self.db.one(
                "SELECT p.status FROM expenses e JOIN projects p ON p.id=e.project_id WHERE e.id=?",
                (expense_id,),
            )
            if project_row and project_row["status"] == "Completed":
                messagebox.showinfo(
                    APP_TITLE,
                    "This expense belongs to a completed project and cannot be changed unless the project is reactivated.",
                    parent=self,
                )
                return
        if expense_id and messagebox.askyesno(APP_TITLE, "Void or restore this expense? The audit history is retained."):
            self.db.execute(
                """UPDATE expenses SET voided=CASE voided WHEN 1 THEN 0 ELSE 1 END,
                   verification_status='Unverified',verified_at='' WHERE id=?""", (expense_id,)
            )
            self.db.audit(None, "EXPENSE_VOID_TOGGLED", str(expense_id)); self.app.refresh_all()

    def filtered_rows(self):
        projects = self.project_options(); where, params = ["1=1"], []
        all_project_ids = list(projects.values())
        project_ids = self.project_selector.selected_ids()
        if not project_ids:
            where.append("0=1")
        elif len(project_ids) != len(all_project_ids):
            placeholders = ",".join("?" for _ in project_ids)
            where.append(f"e.project_id IN ({placeholders})")
            params.extend(project_ids)
        for selector, column in (
            (self.area_selector, "e.area"),
            (self.supplier_selector, "e.supplier"),
        ):
            selected = selector.selected()
            if not selected:
                where.append("0=1")
            elif len(selected) != len(selector.options):
                placeholders = ",".join("?" for _ in selected)
                where.append(f"{column} IN ({placeholders})")
                params.extend(selected)
        payment_total_sql = "COALESCE((SELECT SUM(px.amount_cents) FROM payments px WHERE px.expense_id=e.id AND px.accounting_excluded=0),0)"
        selected_statuses = self.status_selector.selected()
        if len(selected_statuses) != len(self.status_selector.OPTIONS):
            status_clauses = []
            if "Paid" in selected_statuses:
                status_clauses.append(
                    f"(e.voided=0 AND {payment_total_sql}>=e.total_cents AND e.total_cents>0)"
                )
            if "Partially Paid" in selected_statuses:
                status_clauses.append(
                    f"(e.voided=0 AND {payment_total_sql}>0 AND {payment_total_sql}<e.total_cents)"
                )
            if "Unpaid" in selected_statuses:
                status_clauses.append(f"(e.voided=0 AND {payment_total_sql}=0)")
            if "Void" in selected_statuses:
                status_clauses.append("e.voided=1")
            where.append(f"({' OR '.join(status_clauses)})" if status_clauses else "0=1")
        selected_verifications = self.verification_selector.selected()
        if len(selected_verifications) != len(self.verification_selector.OPTIONS):
            if selected_verifications:
                placeholders = ",".join("?" for _ in selected_verifications)
                where.append(f"COALESCE(NULLIF(e.verification_status,''),'Unverified') IN ({placeholders})")
                params.extend(selected_verifications)
            else:
                where.append("0=1")
        selected_methods = self.mop_selector.selected()
        if len(selected_methods) != len(self.mop_selector.OPTIONS):
            method_clauses = []
            if "Cash" in selected_methods:
                method_clauses.append("LOWER(TRIM(pm.method))='cash'")
            if "Bank Transfer" in selected_methods:
                method_clauses.append("LOWER(pm.method) LIKE '%bank%'")
            if "Other" in selected_methods:
                method_clauses.append("(LOWER(TRIM(pm.method))<>'cash' AND LOWER(pm.method) NOT LIKE '%bank%')")
            if method_clauses:
                where.append("EXISTS (SELECT 1 FROM payments pm WHERE pm.expense_id=e.id AND pm.accounting_excluded=0 AND (" +
                             " OR ".join(method_clauses) + "))")
            else:
                where.append("0=1")
        selected_funding = self.funding_selector.selected()
        if not selected_funding:
            where.append("0=1")
        elif len(selected_funding) != len(self.funding_selector.options):
            funding_clauses, funding_params = [], []
            for funding_label in selected_funding:
                funding_kind, funding_value = self.funding_option_map.get(funding_label, ("", None))
                if funding_kind == "head":
                    funding_clauses.append("""EXISTS (SELECT 1 FROM payments fp
                        JOIN cash_allocations fa ON fa.id=fp.cash_allocation_id
                        JOIN project_heads fh ON fh.id=fa.custodian_head_id
                        WHERE fp.expense_id=e.id AND fh.registry_head_id=?)""")
                    funding_params.append(funding_value)
                elif funding_kind == "allocation":
                    funding_clauses.append("""(e.default_cash_allocation_id=? OR EXISTS (
                        SELECT 1 FROM payments fp WHERE fp.expense_id=e.id AND fp.cash_allocation_id=?))""")
                    funding_params.extend((funding_value, funding_value))
                elif funding_kind == "direct_all":
                    funding_clauses.append("""EXISTS (SELECT 1 FROM cash_allocations fa
                        WHERE fa.allocation_type='Direct Procurement' AND
                        (fa.id=e.default_cash_allocation_id OR EXISTS (
                            SELECT 1 FROM payments fp WHERE fp.expense_id=e.id AND fp.cash_allocation_id=fa.id)))""")
                elif funding_kind == "bank":
                    funding_clauses.append(
                        "EXISTS (SELECT 1 FROM payments fp WHERE fp.expense_id=e.id AND fp.bank_account_id IS NOT NULL)"
                    )
                elif funding_kind == "legacy":
                    funding_clauses.append("""EXISTS (SELECT 1 FROM payments fp WHERE fp.expense_id=e.id
                        AND LOWER(TRIM(fp.method))='cash' AND fp.cash_allocation_id IS NULL)""")
            where.append(f"({' OR '.join(funding_clauses)})" if funding_clauses else "0=1")
            params.extend(funding_params)
        # Build one searchable representation of the complete ledger row. This
        # includes visible columns, underlying expense details, every payment,
        # allocation/withdrawal reference, verification, batch and recovery data.
        # Historical PC/DP references therefore remain searchable after surrender
        # or redeposit without cluttering the Funding Source dropdown.
        search_columns = """LOWER(
            CAST(e.id AS TEXT) || ' ' || COALESCE(pr.name,'') || ' ' || COALESCE(pr.client,'') || ' ' ||
            COALESCE(pr.address,'') || ' ' || COALESCE(e.name,'') || ' ' || COALESCE(e.item,'') || ' ' ||
            COALESCE(e.dimensions,'') || ' ' || COALESCE(e.supplier,'') || ' ' || COALESCE(e.qty,'') || ' ' ||
            COALESCE(e.unit,'') || ' ' || COALESCE(e.area,'') || ' ' || COALESCE(e.trade,'') || ' ' ||
            COALESCE(e.expense_date,'') || ' ' || COALESCE(e.due_date,'') || ' ' || COALESCE(e.invoice_no,'') || ' ' ||
            COALESCE(e.notes,'') || ' ' || COALESCE(e.status,'') || ' ' || COALESCE(e.verification_status,'') || ' ' ||
            COALESCE(e.verified_at,'') || ' ' || COALESCE(e.created_at,'') || ' ' || COALESCE(ph.name,'') || ' ' ||
            COALESCE(h.name,'') || ' ' || COALESCE(h.position,'') || ' ' || CAST(e.unit_price_cents AS TEXT) || ' ' ||
            PRINTF('%.2f',e.unit_price_cents/100.0) || ' ' || CAST(e.total_cents AS TEXT) || ' ' ||
            PRINTF('%.2f',e.total_cents/100.0) || ' ' ||
            COALESCE((SELECT GROUP_CONCAT(
                CAST(ps.id AS TEXT) || ' ' || CAST(ps.amount_cents AS TEXT) || ' ' ||
                PRINTF('%.2f',ps.amount_cents/100.0) || ' ' || COALESCE(ps.payment_date,'') || ' ' ||
                COALESCE(ps.transaction_time,'') || ' ' || COALESCE(ps.method,'') || ' ' ||
                COALESCE(ps.reference,'') || ' ' || COALESCE(ps.system_reference,'') || ' ' ||
                COALESCE(ps.notes,'') || ' ' || COALESCE(ba.bank_name,'') || ' ' ||
                COALESCE(ba.account_name,'') || ' ' || COALESCE(ba.account_number,'') || ' ' ||
                COALESCE(ah.name,'') || ' ' || COALESCE(ca.reference,'') || ' ' ||
                COALESCE(ca.allocation_type,'') || ' ' || COALESCE(ca.status,'') || ' ' ||
                COALESCE(ca.supplier,'') || ' ' || COALESCE(ca.purpose,'') || ' ' ||
                COALESCE(rh.name,ch.name,''), ' ')
                FROM payments ps
                LEFT JOIN bank_accounts ba ON ba.id=ps.bank_account_id
                LEFT JOIN project_heads ah ON ah.id=ps.authorized_by_head_id
                LEFT JOIN cash_allocations ca ON ca.id=ps.cash_allocation_id
                LEFT JOIN head_registry rh ON rh.id=ca.receiver_registry_id
                LEFT JOIN project_heads ch ON ch.id=COALESCE(ca.custodian_head_id,ca.responsible_head_id)
                WHERE ps.expense_id=e.id),'') || ' ' ||
            COALESCE((SELECT GROUP_CONCAT(
                COALESCE(NULLIF(wr.system_reference,''),'WD-' || PRINTF('%04d',wr.id)) || ' ' ||
                COALESCE(wr.txn_date,'') || ' ' || COALESCE(wr.transaction_time,'') || ' ' ||
                COALESCE(wr.purpose,'') || ' ' || CAST(src.amount_cents AS TEXT) || ' ' ||
                PRINTF('%.2f',src.amount_cents/100.0), ' ')
                FROM payments wp
                JOIN cash_allocation_sources src ON src.allocation_id=wp.cash_allocation_id
                JOIN remittances wr ON wr.id=src.withdrawal_id
                WHERE wp.expense_id=e.id),'') || ' ' ||
            COALESCE((SELECT ca.reference || ' ' || ca.allocation_type || ' ' || ca.status || ' ' ||
                COALESCE(ca.supplier,'') || ' ' || COALESCE(ca.purpose,'') || ' ' ||
                COALESCE(rh.name,ch.name,'')
                FROM cash_allocations ca
                LEFT JOIN head_registry rh ON rh.id=ca.receiver_registry_id
                LEFT JOIN project_heads ch ON ch.id=COALESCE(ca.custodian_head_id,ca.responsible_head_id)
                WHERE ca.id=e.default_cash_allocation_id),'') || ' ' ||
            COALESCE((SELECT eb.reference || ' ' || COALESCE(eb.committed_at,'') || ' ' || COALESCE(eb.notes,'')
                FROM expense_batches eb WHERE eb.id=e.expense_batch_id),'') || ' ' ||
            COALESCE((SELECT GROUP_CONCAT(vb.reference || ' ' || COALESCE(vb.verification_date,'') || ' ' ||
                COALESCE(vb.verification_time,'') || ' ' || COALESCE(vb.notes,'') || ' ' ||
                COALESCE(vh.name,''), ' ')
                FROM expense_verification_items vi
                JOIN expense_verification_batches vb ON vb.id=vi.batch_id
                LEFT JOIN expense_verification_approvals va ON va.batch_id=vb.id
                LEFT JOIN project_heads vh ON vh.id=va.head_id
                WHERE vi.expense_id=e.id),'') || ' ' ||
            COALESCE((SELECT GROUP_CONCAT(CAST(cat.amount_cents AS TEXT) || ' ' ||
                PRINTF('%.2f',cat.amount_cents/100.0) || ' ' || COALESCE(cat.txn_type,'') || ' ' ||
                COALESCE(cat.txn_date,'') || ' ' || COALESCE(cat.method,'') || ' ' ||
                COALESCE(cat.reference,'') || ' ' || COALESCE(cat.notes,'') || ' ' ||
                COALESCE(cah.name,''), ' ')
                FROM cash_advances cav
                JOIN cash_advance_transactions cat ON cat.advance_id=cav.id
                LEFT JOIN project_heads cah ON cah.id=cat.authorized_by_head_id
                WHERE cav.expense_id=e.id),'') || ' ' ||
            CAST(COALESCE((SELECT SUM(pa.amount_cents) FROM payments pa WHERE pa.expense_id=e.id AND pa.accounting_excluded=0),0) AS TEXT) || ' ' ||
            PRINTF('%.2f',COALESCE((SELECT SUM(pa.amount_cents) FROM payments pa WHERE pa.expense_id=e.id AND pa.accounting_excluded=0),0)/100.0) || ' ' ||
            CAST(MAX(e.total_cents-COALESCE((SELECT SUM(pa.amount_cents) FROM payments pa WHERE pa.expense_id=e.id AND pa.accounting_excluded=0),0),0) AS TEXT) || ' ' ||
            PRINTF('%.2f',MAX(e.total_cents-COALESCE((SELECT SUM(pa.amount_cents) FROM payments pa WHERE pa.expense_id=e.id AND pa.accounting_excluded=0),0),0)/100.0) || ' ' ||
            CAST(COALESCE((SELECT SUM(rt.amount_cents) FROM cash_advances ra
                JOIN cash_advance_transactions rt ON rt.advance_id=ra.id
                WHERE ra.expense_id=e.id AND ra.voided=0 AND rt.voided=0 AND rt.posted=1
                  AND rt.txn_type IN ('Cash Repayment','Bank Repayment','Repayment')),0) AS TEXT) || ' ' ||
            PRINTF('%.2f',COALESCE((SELECT SUM(rt.amount_cents) FROM cash_advances ra
                JOIN cash_advance_transactions rt ON rt.advance_id=ra.id
                WHERE ra.expense_id=e.id AND ra.voided=0 AND rt.voided=0 AND rt.posted=1
                  AND rt.txn_type IN ('Cash Repayment','Bank Repayment','Repayment')),0)/100.0) || ' ' ||
            CAST(MAX(e.total_cents-COALESCE((SELECT SUM(rt.amount_cents) FROM cash_advances ra
                JOIN cash_advance_transactions rt ON rt.advance_id=ra.id
                WHERE ra.expense_id=e.id AND ra.voided=0 AND rt.voided=0 AND rt.posted=1
                  AND rt.txn_type IN ('Cash Repayment','Bank Repayment','Repayment')),0),0) AS TEXT) || ' ' ||
            PRINTF('%.2f',MAX(e.total_cents-COALESCE((SELECT SUM(rt.amount_cents) FROM cash_advances ra
                JOIN cash_advance_transactions rt ON rt.advance_id=ra.id
                WHERE ra.expense_id=e.id AND ra.voided=0 AND rt.voided=0 AND rt.posted=1
                  AND rt.txn_type IN ('Cash Repayment','Bank Repayment','Repayment')),0),0)/100.0)
        )"""
        for term in self.filter_var.get().strip().lower().replace(",", "").split():
            where.append(f"REPLACE({search_columns}, ',', '') LIKE ?")
            params.append(f"%{term}%")
        if self.date_from_filter.get():
            where.append("e.expense_date>=?"); params.append(self.date_from_filter.get())
        if self.date_to_filter.get():
            where.append("e.expense_date<=?"); params.append(self.date_to_filter.get())
        return self.db.all(f"""SELECT e.*,pr.name project,COALESCE(ph.name,'') phase,
            COALESCE(h.name,'') authorized_by,COALESCE(SUM(pay.amount_cents),0) payment_total,
            COALESCE(GROUP_CONCAT(DISTINCT NULLIF(TRIM(pay.method),'')),'') payment_methods,
            COALESCE(MAX(pay.payment_date),'') latest_payment_date,COUNT(pay.id) payment_count,
            COALESCE((SELECT b.reference FROM expense_batches b WHERE b.id=e.expense_batch_id),'Legacy') batch_reference,
            COALESCE((SELECT vb.reference FROM expense_verification_items vi
                JOIN expense_verification_batches vb ON vb.id=vi.batch_id
                WHERE vi.expense_id=e.id ORDER BY vb.id DESC LIMIT 1),'') verification_reference,
            COALESCE((SELECT GROUP_CONCAT(DISTINCT NULLIF(px.system_reference,'')) FROM payments px
                WHERE px.expense_id=e.id AND px.bank_account_id IS NOT NULL),'') bank_transfer_references,
            COALESCE((SELECT SUM(cat.amount_cents) FROM cash_advances ca
                JOIN cash_advance_transactions cat ON cat.advance_id=ca.id
                WHERE ca.expense_id=e.id AND ca.voided=0 AND cat.voided=0 AND cat.posted=1
                  AND cat.txn_type IN ('Cash Repayment','Bank Repayment','Repayment')),0) recovery_total,
            COALESCE((SELECT ca.id FROM cash_advances ca WHERE ca.expense_id=e.id AND ca.voided=0 LIMIT 1),0) cash_advance_id,
            COALESCE((SELECT GROUP_CONCAT(DISTINCT cs.reference) FROM payments px
                JOIN cash_allocations cs ON cs.id=px.cash_allocation_id WHERE px.expense_id=e.id),
                (SELECT cs.reference FROM cash_allocations cs WHERE cs.id=e.default_cash_allocation_id),'') allocation_references,
            COALESCE((SELECT GROUP_CONCAT(DISTINCT COALESCE(NULLIF(wr.system_reference,''),'WD-' || PRINTF('%04d',wr.id)))
                FROM payments px JOIN cash_allocation_sources src ON src.allocation_id=px.cash_allocation_id
                JOIN remittances wr ON wr.id=src.withdrawal_id WHERE px.expense_id=e.id),
                (SELECT GROUP_CONCAT(DISTINCT COALESCE(NULLIF(wr.system_reference,''),'WD-' || PRINTF('%04d',wr.id)))
                 FROM cash_allocation_sources src JOIN remittances wr ON wr.id=src.withdrawal_id
                 WHERE src.allocation_id=e.default_cash_allocation_id),'') withdrawal_references
            FROM expenses e JOIN projects pr ON pr.id=e.project_id LEFT JOIN phases ph ON ph.id=e.phase_id
            LEFT JOIN project_heads h ON h.id=e.authorized_by_head_id
            LEFT JOIN payments pay ON pay.expense_id=e.id AND pay.accounting_excluded=0
            WHERE {' AND '.join(where)} GROUP BY e.id ORDER BY e.expense_date DESC,e.id DESC""", tuple(params)), project_ids

    def refresh(self):
        projects = self.project_options()
        self.project_selector.set_projects([
            {"id": project_id, "name": label} for label, project_id in projects.items()
        ])
        areas = [r["area"] for r in self.db.all("SELECT DISTINCT area FROM expenses WHERE area<>'' ORDER BY area COLLATE NOCASE")]
        suppliers = [r["supplier"] for r in self.db.all("SELECT DISTINCT supplier FROM expenses WHERE supplier<>'' ORDER BY supplier COLLATE NOCASE")]
        self.area_selector.set_options((value, value) for value in areas)
        self.supplier_selector.set_options((value, value) for value in suppliers)
        funding = {"Direct Procurements": ("direct_all", None),
                   "Bank Transfers": ("bank", None),
                   "Legacy / Unlinked Cash": ("legacy", None)}
        for head in self.db.all(
            """SELECT DISTINCT r.id,r.name FROM head_registry r JOIN project_heads h ON h.registry_head_id=r.id
               JOIN cash_allocations a ON a.custodian_head_id=h.id
               WHERE a.allocation_type='Petty Cash' ORDER BY r.name COLLATE NOCASE"""
        ):
            funding[f"Head: {head['name']}"] = ("head", head["id"])
        self.funding_option_map = funding
        self.funding_selector.set_options((label, label) for label in funding)
        self.tree.delete(*self.tree.get_children()); self.current_rows, project_ids = self.filtered_rows()
        total = 0; filtered_payments = 0; filtered_outstanding = 0; verified_total = 0
        for row in self.current_rows:
            outstanding = max(0, row["total_cents"] - row["payment_total"])
            net_total = max(0, row["total_cents"] - row["recovery_total"])
            net_payments = max(0, row["payment_total"] - row["recovery_total"])
            if not row["voided"]:
                total += net_total
                filtered_payments += net_payments
                filtered_outstanding += outstanding
                if (row["verification_status"] or "Unverified") == "Verified":
                    verified_total += net_total
            advance_status = ("Advance Settled" if net_total == 0 else
                              "Advance Partial" if row["recovery_total"] else "Advance Outstanding")
            display_status = ("VOID" if row["voided"] else
                              f"Paid - {advance_status}" if row["cash_advance_id"] else
                              "Paid" if outstanding <= 0 and row["total_cents"] > 0 else
                              "Partially Paid" if row["payment_total"] > 0 else "Unpaid")
            row_tag = "void" if row["voided"] else "paid" if outstanding <= 0 else "pending-partial" if row["payment_total"] else "unpaid"
            methods = [method.strip() for method in row["payment_methods"].split(",") if method.strip()]
            mop = " / ".join(methods) if methods else "Not Paid"
            payment_dates = (f"{row['latest_payment_date']} ({row['payment_count']}) â–¾"
                             if row["payment_count"] else "No payments â–¾")
            allocation = row["allocation_references"] or (
                "Legacy / Unlinked Cash" if any("cash" in method.lower() for method in methods) else "—"
            )
            withdrawal = row["withdrawal_references"] or "—"
            self.tree.insert("", "end", iid=row["id"], values=(row["project"], row["batch_reference"], display_status,
                row["verification_status"] or "Unverified", row["verification_reference"] or "—",
                row["name"], mop, row["bank_transfer_references"] or "—", money(row["total_cents"]),
                money(row["recovery_total"]), money(net_total), money(row["payment_total"]),
                money(outstanding), payment_dates, allocation, withdrawal, row["item"],
                row["supplier"], row["area"], row["phase"],
                row["authorized_by"] or "Legacy / not recorded"), tags=(row_tag,))
        _withdrawn, _cash_spent, cash = self.db.cash_summary()
        self.total_value.config(text=money(total))
        self.verified_value.config(text=money(verified_total), fg=GREEN)
        self.payments_value.config(text=money(filtered_payments), fg=GREEN)
        self.payments_outstanding_value.config(
            text=money(filtered_outstanding), fg=RED if filtered_outstanding > 0 else GREEN
        )
        self.cash_value.config(text=money(cash), fg=GREEN if cash >= 0 else RED)
        unallocated = self.db.unallocated_cash()
        surrendered = self.db.cash_allocation_summary()["surrendered"]
        self.cash_unallocated_value.config(
            text=f"{money(unallocated)} | {money(surrendered)}",
            fg=GREEN if unallocated >= 0 else RED,
        )
        deposited = sum(self.db.project_budget(pid)[0] for pid in project_ids)
        contract = sum(
            self.db.one("SELECT contract_value_cents FROM projects WHERE id=?", (pid,))["contract_value_cents"]
            for pid in project_ids
        )
        committed = sum(self.db.project_commitment_budget(pid)[1] for pid in project_ids)
        budget = deposited - committed
        collectible = contract - deposited
        self.deposit_value.config(text=money(deposited), fg="#2563EB")
        self.budget_value.config(text=money(budget), fg=GREEN if budget >= 0 else RED)
        self.contract_value.config(text=money(contract), fg=INK)
        self.collectible_value.config(text=money(collectible), fg=GREEN if collectible >= 0 else RED)
        excluded = committed - total
        filter_note = (
            f"Current filters show {money(total)} in expenses and {money(filtered_payments)} in payments; "
            f"{money(excluded)} of active expenses is excluded by filters."
            if excluded else
            f"Current filters include all active expenses and {money(filtered_payments)} in payments "
            "for this project selection."
        )
        self.reconciliation_label.config(
            text=(f"Reconciliation: deposited {money(deposited)} = all active expenses {money(committed)} + "
                  f"budget remaining {money(budget)}. {filter_note} Cash on-hand is shared across projects.")
        )
        self._refresh_head_cash_breakdown()
        self._refresh_cash_tab()
        visible_rows = self.tree.get_children()
        if visible_rows:
            self.tree.selection_set(visible_rows[0])
            self.tree.focus(visible_rows[0])
        self._ledger_size_changed()

    def export_pdf(self):
        rows, project_ids = self.filtered_rows()
        if not rows: messagebox.showinfo(APP_TITLE, "There are no filtered rows to export."); return
        destination = filedialog.asksaveasfilename(title="Export Filtered Expense Ledger",
            initialfile=f"expenses_{date.today():%Y%m%d}.pdf", defaultextension=".pdf",
            filetypes=[("PDF document", "*.pdf")])
        if not destination: return
        total = sum(max(0,row["total_cents"]-row["recovery_total"]) for row in rows if not row["voided"])
        _withdrawn, _cash_spent, cash = self.db.cash_summary()
        projects = self.project_options()
        deposited = sum(self.db.project_budget(pid)[0] for pid in project_ids)
        contract = sum(self.db.one(
            "SELECT contract_value_cents FROM projects WHERE id=?", (pid,)
        )["contract_value_cents"] for pid in project_ids)
        committed = sum(self.db.project_commitment_budget(pid)[1] for pid in project_ids)
        applied_filters = [
            ("Project", self.project_selector.display_text()),
            ("Status", self.status_selector.display_text()),
            ("Verification", self.verification_selector.display_text()),
            ("MOP", self.mop_selector.display_text()),
            ("Funding source", self.funding_selector.display_text()),
            ("Area", self.area_selector.display_text()),
            ("Supplier", self.supplier_selector.display_text()),
            ("Date from", self.date_from_filter.get() or "All dates"),
            ("Date to", self.date_to_filter.get() or "All dates"),
            ("Search", self.filter_var.get() or "(none)"),
        ]
        financial_summary = [
            f"Filtered expenses {money(total)}",
            f"Verified expenses {money(sum(max(0,row['total_cents']-row['recovery_total']) for row in rows if not row['voided'] and (row['verification_status'] or 'Unverified') == 'Verified'))}",
            f"Payments recorded {money(sum(max(0,row['payment_total']-row['recovery_total']) for row in rows if not row['voided']))}",
            f"Advance recoveries {money(sum(row['recovery_total'] for row in rows if not row['voided']))}",
            f"Outstanding payments {money(sum(max(0, row['total_cents']-row['payment_total']) for row in rows if not row['voided']))}",
            f"Cash on-hand {money(cash)}",
            f"Deposited {money(deposited)}",
            f"Budget remaining {money(deposited-committed)}",
            f"Total contract {money(contract)}",
            f"Contract collectible {money(contract-deposited)}",
        ]
        report_rows = [{
            "project": row["project"],
            "batch": row["batch_reference"],
            "date": row["expense_date"],
            "verification": row["verification_status"] or "Unverified",
            "verification_ref": row["verification_reference"] or "-",
            "expense": f"{row['name']} / {row['item']}",
            "mop": " / ".join(
                method.strip() for method in row["payment_methods"].split(",") if method.strip()
            ) or "Not Paid",
            "bank_ref": row["bank_transfer_references"] or "-",
            "supplier": row["supplier"],
            "area": row["area"].title(),
            "total": money(row["total_cents"]),
            "recovered": money(row["recovery_total"]),
            "net": money(max(0,row["total_cents"]-row["recovery_total"])),
            "paid": money(row["payment_total"]),
            "outstanding": money(max(0, row["total_cents"] - row["payment_total"])),
            "status": ("VOID" if row["voided"] else
                       ("Paid - Advance Settled" if row["recovery_total"]>=row["total_cents"] else
                        "Paid - Advance Partial" if row["recovery_total"] else "Paid - Advance Outstanding") if row["cash_advance_id"] else
                       "Paid" if row["payment_total"] >= row["total_cents"] and row["total_cents"] > 0 else
                       "Partially Paid" if row["payment_total"] > 0 else "Unpaid"),
            "allocation": row["allocation_references"] or "Legacy / Unlinked",
            "withdrawal": row["withdrawal_references"] or "—",
            "authorized": row["authorized_by"] or "Legacy / not recorded",
        } for row in rows]
        write_expense_ledger_pdf(
            destination, applied_filters, financial_summary, report_rows
        )
        messagebox.showinfo(APP_TITLE, f"Filtered expense PDF saved:\n{destination}")


class ContactsTab(BaseTab):
    FIELDS = [
        ("name", "Name"), ("role", "Role / relationship"), ("company", "Company"),
        ("phone", "Phone"), ("email", "Email"), ("address", "Address"), ("notes", "Notes"),
    ]

    def __init__(self, app):
        super().__init__(app)
        ttk.Label(self, text="Project contacts", style="Title.TLabel").pack(anchor="w")
        bar = ttk.Frame(self); bar.pack(fill="x", pady=(10, 0))
        ttk.Button(bar, text="＋ Add Contact", command=self.add).pack(side="left")
        ttk.Button(bar, text="Edit", command=self.edit).pack(side="left", padx=5)
        ttk.Button(bar, text="Delete", command=self.delete).pack(side="left")
        self.tree = make_tree(self, [
            ("name", "Name", 180), ("role", "Role", 150), ("company", "Company", 160),
            ("phone", "Phone", 125), ("email", "Email", 190), ("address", "Address", 220),
        ])

    def add(self):
        if not self.require_project():
            return
        data = dialog(self, "Contact", self.FIELDS, required_keys=("name",))
        if data and data["name"]:
            self.db.execute(
                """INSERT INTO contacts(project_id,name,role,company,phone,email,address,notes)
                   VALUES(?,?,?,?,?,?,?,?)""", (self.project_id,) + tuple(data[k] for k, *_ in self.FIELDS)
            )
            self.app.refresh_all()

    def edit(self):
        if not self.require_project():
            return
        record_id = self.selected_id(self.tree)
        if not record_id:
            return
        row = self.db.one("SELECT * FROM contacts WHERE id=?", (record_id,))
        data = dialog(self, "Contact", self.FIELDS, dict(row), required_keys=("name",))
        if data:
            self.db.execute(
                """UPDATE contacts SET name=?,role=?,company=?,phone=?,email=?,address=?,notes=? WHERE id=?""",
                tuple(data[k] for k, *_ in self.FIELDS) + (record_id,),
            )
            self.app.refresh_all()

    def delete(self):
        if not self.require_project():
            return
        record_id = self.selected_id(self.tree)
        if record_id and messagebox.askyesno(APP_TITLE, "Delete this contact?"):
            self.db.execute("DELETE FROM contacts WHERE id=?", (record_id,))
            self.app.refresh_all()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        if self.project_id:
            for row in self.db.all("SELECT * FROM contacts WHERE project_id=? ORDER BY name", (self.project_id,)):
                self.tree.insert("", "end", iid=row["id"], values=(
                    row["name"], row["role"], row["company"], row["phone"], row["email"], row["address"]
                ))


class KioskWindow(tk.Toplevel):
    """Full-screen employee clock designed for a shared site computer."""
    def __init__(self, payroll):
        super().__init__(payroll)
        self.payroll = payroll
        self.title("ConTracktor Site Kiosk")
        self.configure(bg=NAVY)
        self.attributes("-fullscreen", True)
        self.employee_no = tk.StringVar(); self.pin = tk.StringVar()
        top = tk.Frame(self, bg=NAVY, padx=34, pady=22); top.pack(fill="x")
        tk.Label(top, text="ConTracktor", bg=NAVY, fg=WHITE,
                 font=("Segoe UI", 23, "bold")).pack(side="left")
        ttk.Button(top, text="Exit Kiosk", style="Secondary.TButton", command=self.destroy).pack(side="right")
        project = payroll.db.one("SELECT name FROM projects WHERE id=?", (payroll.project_id,))
        tk.Label(self, text=project["name"] if project else "Site Attendance", bg=NAVY,
                 fg="#9CA3AF", font=("Segoe UI", 13)).pack()
        self.clock_label = tk.Label(self, text="", bg=NAVY, fg=ORANGE,
                                    font=("Consolas", 54, "bold"))
        self.clock_label.pack(pady=(45, 30))
        card = tk.Frame(self, bg=WHITE, padx=42, pady=36,
                        highlightthickness=1, highlightbackground="#D8DEE8")
        card.pack(ipadx=40)
        tk.Label(card, text="ENTER EMPLOYEE NUMBER AND PIN", bg=WHITE, fg=INK,
                 font=("Segoe UI", 13, "bold")).pack(pady=(0, 18))
        ttk.Entry(card, textvariable=self.employee_no, font=("Segoe UI", 18), width=26).pack(ipady=8, pady=5)
        ttk.Entry(card, textvariable=self.pin, show="*", font=("Segoe UI", 22), width=26).pack(ipady=8, pady=5)
        buttons = tk.Frame(card, bg=WHITE); buttons.pack(fill="x", pady=(22, 0))
        ttk.Button(buttons, text="TIME IN", style="Success.TButton",
                   command=lambda: self.submit("in")).pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=10)
        ttk.Button(buttons, text="TIME OUT", style="Secondary.TButton",
                   command=lambda: self.submit("out")).pack(side="left", fill="x", expand=True, padx=(6, 0), ipady=10)
        tk.Label(self, text="Press Esc to exit kiosk mode", bg=NAVY, fg="#7F8CA3").pack(side="bottom", pady=20)
        self.bind("<Escape>", lambda _e: self.destroy()); self.update_clock()

    def update_clock(self):
        if self.winfo_exists():
            self.clock_label.config(text=datetime.now().strftime("%I:%M:%S %p"))
            self.after(1000, self.update_clock)

    def submit(self, direction):
        if self.payroll.process_clock(direction, self.employee_no.get(), self.pin.get(), self):
            self.employee_no.set(""); self.pin.set("")


class PayrollTab(BaseTab):
    EMPLOYEE_FIELDS = [
        ("employee_no", "Employee number"), ("pin", "PIN (4+ characters)"), ("name", "Name"),
        ("position", "Position"), ("class", "Class", ["Skilled", "Labor"]),
        ("pay_basis", "Pay basis", ["Daily", "Hourly"]), ("rate", "Rate"),
        ("standard_hours", "Standard hours/day"),
    ]

    def __init__(self, app):
        super().__init__(app)
        ttk.Label(self, text="Attendance and payroll", style="Title.TLabel").pack(anchor="w")
        actions = ttk.Frame(self); actions.pack(fill="x", pady=(10, 4))
        ttk.Button(actions, text="＋ Add Employee", command=self.add_employee).pack(side="left")
        ttk.Button(actions, text="Edit Employee", command=self.edit_employee).pack(side="left", padx=5)
        ttk.Button(actions, text="Commit Closed Attendance to Expenses", command=self.commit).pack(side="left")
        clock = tk.Frame(self, bg=NAVY, padx=16, pady=12)
        clock.pack(fill="x", pady=8)
        tk.Label(clock, text="SITE KIOSK", bg=NAVY, fg=WHITE,
                 font=("Segoe UI", 12, "bold")).pack(side="left", padx=(0, 15))
        tk.Label(clock, text="Employee no.", bg=NAVY, fg="#CBD5E1").pack(side="left")
        self.employee_no = tk.StringVar()
        ttk.Entry(clock, textvariable=self.employee_no, width=14).pack(side="left", padx=5)
        tk.Label(clock, text="PIN", bg=NAVY, fg="#CBD5E1").pack(side="left")
        self.pin = tk.StringVar()
        ttk.Entry(clock, textvariable=self.pin, show="*", width=10).pack(side="left", padx=5)
        ttk.Button(clock, text="IN", style="Success.TButton",
                   command=lambda: self.clock("in")).pack(side="left", padx=3)
        ttk.Button(clock, text="OUT", style="Secondary.TButton",
                   command=lambda: self.clock("out")).pack(side="left", padx=3)
        ttk.Button(clock, text="Expand Kiosk", style="Primary.TButton",
                   command=self.open_kiosk).pack(side="right")
        self.summary = tk.Label(clock, text="", bg=NAVY, fg=WHITE)
        self.summary.pack(side="right", padx=12)
        lists = ttk.Notebook(self)
        lists.pack(fill="both", expand=True, pady=(6, 0))
        employee_page = ttk.Frame(lists, padding=4)
        attendance_page = ttk.Frame(lists, padding=4)
        lists.add(employee_page, text="Employee Roster")
        lists.add(attendance_page, text="Attendance Ledger")
        self.employees = make_tree(employee_page, [
            ("no", "Employee No.", 110), ("name", "Name", 180), ("position", "Position", 150),
            ("class", "Class", 90), ("basis", "Basis", 75), ("rate", "Rate", 100),
            ("state", "Current Status", 120),
        ])
        self.attendance = make_tree(attendance_page, [
            ("employee", "Employee", 170), ("in", "Time In", 150), ("out", "Time Out", 150),
            ("hours", "Hours", 80), ("gross", "Gross Pay", 100), ("committed", "Committed", 90),
        ])

    def add_employee(self):
        if not self.require_project():
            return
        data = dialog(self, "Employee", self.EMPLOYEE_FIELDS, {"standard_hours": "8"})
        if data:
            try:
                if not data["employee_no"] or not data["name"]:
                    raise ValueError("Employee number and name are required.")
                salt, digest = hash_pin(data["pin"])
                hours = qty_decimal(data["standard_hours"])
                if hours <= 0:
                    raise ValueError("Standard hours must be greater than zero.")
                self.db.execute(
                    """INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,name,position,
                       class,pay_basis,rate_cents,standard_hours) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (self.project_id, data["employee_no"], salt, digest, data["name"], data["position"],
                     data["class"], data["pay_basis"], cents(data["rate"]), str(hours)),
                )
                self.db.audit(self.project_id, "EMPLOYEE_ADDED", data["name"])
                self.app.refresh_all()
            except (ValueError, sqlite3.IntegrityError) as exc:
                messagebox.showerror(APP_TITLE, str(exc))

    def edit_employee(self):
        employee_id = self.selected_id(self.employees)
        if not employee_id:
            return
        row = self.db.one("SELECT * FROM employees WHERE id=?", (employee_id,))
        initial = dict(row)
        initial["rate"] = money(row["rate_cents"])
        initial["pin"] = ""
        updated = dialog(self, "Edit Employee", self.EMPLOYEE_FIELDS, initial)
        if updated:
            try:
                pin_sql = ""
                params = [updated["employee_no"], updated["name"], updated["position"], updated["class"],
                          updated["pay_basis"], cents(updated["rate"]), str(qty_decimal(updated["standard_hours"]))]
                if updated["pin"]:
                    salt, digest = hash_pin(updated["pin"])
                    pin_sql = ",pin_salt=?,pin_hash=?"
                    params += [salt, digest]
                params.append(row["id"])
                self.db.execute(
                    f"""UPDATE employees SET employee_no=?,name=?,position=?,class=?,pay_basis=?,
                        rate_cents=?,standard_hours=?{pin_sql} WHERE id=?""", tuple(params)
                )
                self.app.refresh_all()
            except (ValueError, sqlite3.Error) as exc:
                messagebox.showerror(APP_TITLE, str(exc))

    def open_kiosk(self):
        if self.require_project():
            KioskWindow(self)

    def clock(self, direction=None):
        self.process_clock(direction, self.employee_no.get(), self.pin.get(), self)

    def process_clock(self, direction, employee_no, pin, parent=None):
        if not self.require_project():
            return False
        employee = self.db.one("SELECT * FROM employees WHERE project_id=? AND employee_no=? AND active=1",
                               (self.project_id, employee_no.strip()))
        if not employee or not verify_pin(pin, employee["pin_salt"], employee["pin_hash"]):
            messagebox.showerror(APP_TITLE, "Employee number or PIN is incorrect.", parent=parent)
            return False
        open_row = self.db.one("SELECT * FROM attendance WHERE employee_id=? AND clock_out=''",
                               (employee["id"],))
        now = datetime.now()
        if direction == "in" and open_row:
            messagebox.showinfo(APP_TITLE, f"{employee['name']} is already clocked in.", parent=parent)
            return False
        if direction == "out" and not open_row:
            messagebox.showinfo(APP_TITLE, f"{employee['name']} is not currently clocked in.", parent=parent)
            return False
        if not open_row:
            self.db.execute("INSERT INTO attendance(employee_id,clock_in) VALUES(?,?)",
                            (employee["id"], now.isoformat(timespec="seconds")))
            messagebox.showinfo(APP_TITLE, f"Welcome, {employee['name']}!\nTime in: {now:%I:%M %p}", parent=parent)
        else:
            started = datetime.fromisoformat(open_row["clock_in"])
            hours = max(Decimal("0"), Decimal(str((now - started).total_seconds() / 3600))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if employee["pay_basis"] == "Hourly":
                gross = int((hours * employee["rate_cents"]).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            else:
                standard = Decimal(employee["standard_hours"])
                gross = int((hours / standard * employee["rate_cents"]).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                ))
            self.db.execute(
                "UPDATE attendance SET clock_out=?,hours=?,gross_cents=? WHERE id=?",
                (now.isoformat(timespec="seconds"), str(hours), gross, open_row["id"]),
            )
            messagebox.showinfo(
                APP_TITLE, f"Goodbye, {employee['name']}!\nHours: {hours}\nGross: {money(gross)}", parent=parent
            )
        self.pin.set("")
        self.app.refresh_all()
        return True

    def commit(self):
        if not self.require_project():
            return
        rows = self.db.all(
            """SELECT a.* FROM attendance a JOIN employees e ON e.id=a.employee_id
               WHERE e.project_id=? AND a.clock_out<>'' AND a.committed_expense_id IS NULL""",
            (self.project_id,),
        )
        if not rows:
            messagebox.showinfo(APP_TITLE, "There is no uncommitted closed attendance.")
            return
        total = sum(r["gross_cents"] for r in rows)
        head = self.app.authorize(
            "Commit payroll to expenses",
            f"{len(rows)} closed attendance record(s) totaling {money(total)}.\n"
            "This will create one unpaid payroll expense."
        )
        if not head: return
        batch = datetime.now().strftime("%Y%m%d-%H%M%S")
        with self.db.conn:
            cur = self.db.conn.execute(
                """INSERT INTO expenses(project_id,name,item,supplier,qty,unit,unit_price_cents,
                   total_cents,trade,expense_date,due_date,payroll_batch,notes,authorized_by_head_id)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self.project_id, f"Payroll {date.today():%Y-%m-%d}", "Closed attendance payroll",
                 "Payroll", "1", "batch", total, total, "Labor", date.today().isoformat(),
                 date.today().isoformat(), batch, f"{len(rows)} attendance record(s)", head["id"]),
            )
            expense_id = cur.lastrowid
            self.db.conn.executemany(
                "UPDATE attendance SET committed_expense_id=? WHERE id=?",
                [(expense_id, r["id"]) for r in rows],
            )
        self.db.audit(self.project_id, "PAYROLL_COMMITTED",
                      f"{batch}: {money(total)} authorized by {head['name']}")
        messagebox.showinfo(APP_TITLE, f"Payroll of {money(total)} was added as an unpaid expense.")
        self.app.refresh_all()

    def refresh(self):
        self.employees.delete(*self.employees.get_children())
        self.attendance.delete(*self.attendance.get_children())
        if not self.project_id:
            self.summary.config(text="")
            return
        employee_rows = self.db.all(
            """SELECT e.*,CASE WHEN EXISTS(SELECT 1 FROM attendance a WHERE a.employee_id=e.id
               AND a.clock_out='') THEN 'Clocked in' ELSE 'Clocked out' END state
               FROM employees e WHERE e.project_id=? ORDER BY e.name""", (self.project_id,)
        )
        for employee in employee_rows:
            self.employees.insert("", "end", iid=employee["id"], values=(
                employee["employee_no"], employee["name"], employee["position"], employee["class"],
                employee["pay_basis"], money(employee["rate_cents"]), employee["state"],
            ))
        rows = self.db.all(
            """SELECT a.*,e.name FROM attendance a JOIN employees e ON e.id=a.employee_id
               WHERE e.project_id=? ORDER BY a.clock_in DESC""", (self.project_id,)
        )
        total = 0
        for row in rows:
            total += row["gross_cents"]
            self.attendance.insert("", "end", iid=row["id"], values=(
                row["name"], row["clock_in"].replace("T", " "), row["clock_out"].replace("T", " "),
                row["hours"], money(row["gross_cents"]), "Yes" if row["committed_expense_id"] else "No",
            ))
        self.summary.config(text=f"Recorded gross: {money(total)}")


class EmployeeEditorDialog(tk.Toplevel):
    """Employee form with calendar, compliance checklist and embedded photo."""
    def __init__(self, parent, initial=None, employee_number=""):
        super().__init__(parent)
        self.title("Edit Employee" if initial else "Add Employee")
        self.geometry("820x610"); self.minsize(760, 570); self.result = None
        initial = dict(initial or {})
        if not initial.get("employee_no"):
            initial["employee_no"] = employee_number
        self.vars = {key: tk.StringVar(value=str(initial.get(key, "") or "")) for key in (
            "employee_no", "pin", "name", "birthday", "contact_number",
            "position", "class", "daily_rate",
        )}
        self.widgets = {}
        self.vars["class"].set(self.vars["class"].get() or "Labor")
        self.compliance = {
            key: tk.BooleanVar(value=bool(initial.get(key, 0))) for key in
            ("nbi_clearance", "police_clearance", "drug_test", "biodata")
        }
        self.photo_data = initial.get("photo_data")
        self.photo_filename = initial.get("photo_filename", "") or ""
        self.photo_image = None

        body = ttk.Frame(self, padding=22); body.pack(fill="both", expand=True)
        ttk.Label(body, text=self.title(), style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(body, text=("PIN may be left blank to keep the existing PIN. Employee numbers are permanent."
                  if initial and not employee_number else
                  "The employee number is generated from the project name. Daily rate is converted using 8 hours/day."),
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 14))
        content = ttk.Frame(body); content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=3); content.columnconfigure(1, weight=2)

        form = ttk.Frame(content); form.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        form.columnconfigure(0, weight=1); form.columnconfigure(1, weight=1)
        fields = (("employee_no", "Employee number"), ("pin", "PIN (4+ characters)"),
                  ("name", "Full name"), ("position", "Position"),
                  ("class", "Class"), ("daily_rate", "Daily rate"),
                  ("birthday", "Birthday"), ("contact_number", "Contact number"))
        for index, (key, label) in enumerate(fields):
            row, column = divmod(index, 2)
            cell = ttk.Frame(form); cell.grid(row=row, column=column, sticky="ew",
                padx=(0, 8) if column == 0 else (8, 0), pady=(0, 11))
            required = key in {"employee_no", "name", "position", "class", "daily_rate"}
            ttk.Label(cell, text=label + (" *" if required else "")).pack(anchor="w")
            if key == "class":
                widget = ttk.Combobox(cell, textvariable=self.vars[key],
                                      values=["Skilled", "Labor"], state="readonly")
                widget.pack(fill="x")
            elif key == "birthday":
                line = ttk.Frame(cell); line.pack(fill="x")
                widget = ttk.Entry(line, textvariable=self.vars[key], state="readonly")
                widget.pack(side="left", fill="x", expand=True); self.widgets[key] = widget
                ttk.Button(line, text="\U0001F4C5", width=3,
                           command=lambda: DatePickerPopup(
                               self, self.vars["birthday"], year_min=1900,
                               year_max=date.today().year)).pack(
                               side="left", padx=(4, 0))
            else:
                widget = ttk.Entry(cell, textvariable=self.vars[key],
                                   state="readonly" if key == "employee_no" else "normal",
                                   show="*" if key == "pin" else "")
                widget.pack(fill="x"); self.widgets[key] = widget
            if key == "class":
                self.widgets[key] = widget

        ttk.Label(form, text="Employment compliance documents",
                  style="Section.TLabel").grid(row=4, column=0, columnspan=2,
                                                sticky="w", pady=(5, 5))
        compliance_frame = ttk.Frame(form); compliance_frame.grid(
            row=5, column=0, columnspan=2, sticky="ew")
        compliance_labels = (("nbi_clearance", "NBI clearance"),
                             ("police_clearance", "Police clearance"),
                             ("drug_test", "Drug test"), ("biodata", "Biodata"))
        for index, (key, label) in enumerate(compliance_labels):
            ttk.Checkbutton(compliance_frame, text=label,
                            variable=self.compliance[key]).grid(
                                row=index // 2, column=index % 2, sticky="w",
                                padx=(0, 30), pady=4)

        photo = ttk.LabelFrame(content, text="1×1 picture attachment", padding=14)
        photo.grid(row=0, column=1, sticky="nsew")
        self.photo_preview = ttk.Label(photo, text="No picture attached", anchor="center")
        self.photo_preview.pack(fill="both", expand=True, pady=(0, 10))
        self.photo_name_label = ttk.Label(photo, style="Muted.TLabel", wraplength=230)
        self.photo_name_label.pack(fill="x", pady=(0, 8))
        photo_buttons = ttk.Frame(photo); photo_buttons.pack(fill="x")
        ttk.Button(photo_buttons, text="Attach / Replace", command=self.attach_photo).pack(
            side="left", fill="x", expand=True)
        ttk.Button(photo_buttons, text="Remove", command=self.remove_photo).pack(
            side="left", padx=(6, 0))
        ttk.Label(photo, text="PNG, JPEG, GIF or BMP; stored inside SQLite.",
                  style="Muted.TLabel", wraplength=230).pack(anchor="w", pady=(9, 0))
        self.refresh_photo()

        buttons = ttk.Frame(body); buttons.pack(fill="x", pady=(16, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Save Employee", style="Primary.TButton",
                   command=self.save).pack(side="right", padx=(0, 8))
        self.transient(parent); self.grab_set(); self.bind("<Escape>", lambda _e: self.destroy())

    def attach_photo(self):
        selected = filedialog.askopenfilename(
            parent=self, title="Select employee 1x1 picture",
            filetypes=[("Picture files", "*.png *.jpg *.jpeg *.gif *.bmp *.ppm *.pgm"),
                       ("All files", "*.*")],
        )
        if not selected:
            return
        try:
            self.photo_data = normalized_employee_photo(selected)
            self.photo_filename = Path(selected).name
            self.refresh_photo()
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)

    def remove_photo(self):
        self.photo_data = None; self.photo_filename = ""; self.refresh_photo()

    def refresh_photo(self):
        self.photo_image = employee_photo_image(self.photo_data, 210)
        if self.photo_image:
            self.photo_preview.configure(image=self.photo_image, text="")
        else:
            self.photo_preview.configure(image="", text="No picture attached")
        self.photo_name_label.configure(text=self.photo_filename or "No attachment")

    def save(self):
        values = {key: variable.get().strip() for key, variable in self.vars.items()}
        if flash_missing_fields(
                self, self.vars, self.widgets,
                ("employee_no", "name", "position", "class", "daily_rate")):
            return
        try:
            if values["pin"]:
                hash_pin(values["pin"])
            valid_date(values["birthday"])
            if cents(values["daily_rate"]) <= 0:
                raise ValueError("Daily rate must be greater than zero.")
        except ValueError as exc:
            message = str(exc).lower()
            if "pin" in message:
                flash_required_widgets(self, [self.widgets["pin"]])
            elif "date" in message:
                flash_required_widgets(self, [self.widgets["birthday"]])
            else:
                flash_required_widgets(self, [self.widgets["daily_rate"]])
            messagebox.showerror(APP_TITLE, str(exc), parent=self); return
        values.update({key: int(variable.get()) for key, variable in self.compliance.items()})
        values.update(photo_data=self.photo_data, photo_filename=self.photo_filename,
                      photo_mime="image/png" if self.photo_data else "")
        self.result = values; self.destroy()


class EmployeeProfileDialog(tk.Toplevel):
    def __init__(self, parent, db, employee_id):
        super().__init__(parent); self.title("Employee Profile"); self.geometry("1000x700")
        self.minsize(900, 620)
        employee = db.one("""SELECT e.*,p.name project_name FROM employees e
            JOIN projects p ON p.id=e.project_id WHERE e.id=?""", (employee_id,))
        daily = employee_daily_rate(employee)
        outstanding = db.one("""SELECT COALESCE(SUM(a.original_cents),0)-COALESCE(SUM(
            (SELECT SUM(t.amount_cents) FROM cash_advance_transactions t WHERE t.advance_id=a.id
             AND t.posted=1 AND t.voided=0 AND t.txn_type<>'Advance')),0) balance
            FROM cash_advances a WHERE a.employee_id=? AND a.voided=0""", (employee_id,))["balance"]
        body = ttk.Frame(self, padding=20); body.pack(fill="both", expand=True)
        profile = ttk.Frame(body); profile.pack(fill="x")
        photo_frame = ttk.LabelFrame(profile, text="1×1 picture", padding=10)
        photo_frame.pack(side="left", fill="y", padx=(0, 18))
        self.photo_image = employee_photo_image(employee["photo_data"], 170)
        ttk.Label(photo_frame, image=self.photo_image,
                  text="No picture\nattached" if not self.photo_image else "",
                  anchor="center", width=22).pack(fill="both", expand=True)
        if employee["photo_filename"]:
            ttk.Label(photo_frame, text=employee["photo_filename"],
                      style="Muted.TLabel", wraplength=175).pack(pady=(6, 0))
        profile_details = ttk.Frame(profile); profile_details.pack(
            side="left", fill="both", expand=True)
        ttk.Label(profile_details, text=employee["name"],
                  style="DialogTitle.TLabel").pack(anchor="w")
        info = ttk.Frame(profile_details); info.pack(fill="x", pady=(10, 8))
        details = [("Employee number", employee["employee_no"]), ("Position", employee["position"]),
            ("Class", employee["class"]), ("Birthday", employee["birthday"] or "-"),
            ("Age", employee_age(employee["birthday"]) or "-"),
            ("Contact number", employee["contact_number"] or "-"),
            ("Daily rate", money(daily)), ("Hourly rate", money(int((Decimal(daily)/8).quantize(Decimal('1'), rounding=ROUND_HALF_UP)))),
            ("Outstanding advances", money(max(0, outstanding))),
            ("Current / last project", employee["project_name"]),
            ("Employment status", "Active" if employee["active"] else "Archived"),
            ("Archive notes", employee["archive_reason"] or "-")]
        for index, (label, value) in enumerate(details):
            row, pair = divmod(index, 3)
            card = ttk.Frame(info, padding=6); card.grid(row=row, column=pair, sticky="ew", padx=(0, 8), pady=3)
            ttk.Label(card, text=label, style="Muted.TLabel").pack(anchor="w")
            ttk.Label(card, text=value, style="Section.TLabel").pack(anchor="w")
            info.columnconfigure(pair, weight=1)
        compliance = ttk.LabelFrame(profile_details, text="Employment compliance", padding=(10, 7))
        compliance.pack(fill="x")
        compliance_items = (("NBI clearance", employee["nbi_clearance"]),
                            ("Police clearance", employee["police_clearance"]),
                            ("Drug test", employee["drug_test"]),
                            ("Biodata", employee["biodata"]))
        for index, (label, complete) in enumerate(compliance_items):
            tk.Label(compliance, text=f"{'✓' if complete else '—'}  {label}",
                     bg=WHITE, fg=GREEN if complete else MUTED,
                     font=("Segoe UI", 9, "bold"), padx=6, pady=4).grid(
                         row=0, column=index, sticky="w")
            compliance.columnconfigure(index, weight=1)
        ttk.Label(body, text="Cash-advance transaction history", style="Section.TLabel").pack(
            anchor="w", pady=(15, 0))
        columns = (("date","Date",95),("type","Transaction",130),("amount","Amount",100),
                   ("mop","MOP",110),("reference","Reference",120),("head","Authorized by",130),
                   ("balance","Balance after",110))
        frame=ttk.Frame(body); frame.pack(fill="both", expand=True, pady=(6,0))
        tree=ttk.Treeview(frame,columns=[c[0] for c in columns],show="headings")
        for key,label,width in columns: tree.heading(key,text=label); tree.column(key,width=width,stretch=True)
        sy=ttk.Scrollbar(frame,orient="vertical",command=tree.yview); tree.configure(yscrollcommand=sy.set)
        tree.pack(side="left",fill="both",expand=True); sy.pack(side="left",fill="y")
        txns=db.all("""SELECT t.*,COALESCE(h.name,'Legacy / not recorded') head,a.original_cents
            FROM cash_advance_transactions t JOIN cash_advances a ON a.id=t.advance_id
            LEFT JOIN project_heads h ON h.id=t.authorized_by_head_id
            WHERE a.employee_id=? AND a.voided=0 AND t.voided=0 ORDER BY t.txn_date,t.id""",(employee_id,))
        balances={}
        for txn in txns:
            advance_id=txn["advance_id"]; balances.setdefault(advance_id,0)
            balances[advance_id] += txn["amount_cents"] if txn["txn_type"]=="Advance" else (-txn["amount_cents"] if txn["posted"] else 0)
            tree.insert("","end",values=(txn["txn_date"],txn["txn_type"]+(" (Pending)" if not txn["posted"] else ""),
                money(txn["amount_cents"]),txn["method"],txn["reference"],txn["head"],money(max(0,balances[advance_id]))))
        ttk.Button(body,text="Close",command=self.destroy).pack(anchor="e",pady=(12,0))
        self.transient(parent); self.grab_set(); self.bind("<Escape>",lambda _e:self.destroy())


class BatchAttendanceDialog(tk.Toplevel):
    def __init__(self, parent, employees):
        super().__init__(parent); self.title("Batch Attendance"); self.geometry("920x650"); self.result=None
        body=ttk.Frame(self,padding=18); body.pack(fill="both",expand=True)
        ttk.Label(body,text="Mark batch attendance",style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(body,text="Select employees and adjust individual times. Lunch overlap from 12:00-1:00 PM is unpaid.",style="Muted.TLabel").pack(anchor="w",pady=(2,10))
        defaults=ttk.Frame(body); defaults.pack(fill="x")
        self.work_date=tk.StringVar(value=date.today().isoformat()); self.default_in=tk.StringVar(value="08:00"); self.default_out=tk.StringVar(value="17:00")
        for label,var,width in (("Date",self.work_date,12),("Default in",self.default_in,8),("Default out",self.default_out,8)):
            ttk.Label(defaults,text=label).pack(side="left",padx=(0,4)); ttk.Entry(defaults,textvariable=var,width=width).pack(side="left",padx=(0,10))
        self.search=tk.StringVar(); ttk.Label(defaults,text="Search").pack(side="left",padx=(10,4))
        entry=ttk.Entry(defaults,textvariable=self.search); entry.pack(side="left",fill="x",expand=True)
        ttk.Button(defaults,text="Apply defaults",command=self.apply_defaults).pack(side="left",padx=(8,0))
        headings=ttk.Frame(body); headings.pack(fill="x",pady=(12,2))
        for text,width in (("Present",9),("Employee",32),("Time in",12),("Time out",12)):
            ttk.Label(headings,text=text,width=width,style="Muted.TLabel").pack(side="left")
        outer=ttk.Frame(body); outer.pack(fill="both",expand=True)
        canvas=tk.Canvas(outer,bg=WHITE,highlightthickness=1,highlightbackground="#CBD5E1")
        scroll=ttk.Scrollbar(outer,orient="vertical",command=canvas.yview); canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right",fill="y"); canvas.pack(side="left",fill="both",expand=True)
        self.rows_frame=ttk.Frame(canvas); self.window=canvas.create_window((0,0),window=self.rows_frame,anchor="nw")
        self.rows=[]
        for employee in employees:
            row=ttk.Frame(self.rows_frame,padding=(6,4)); row.pack(fill="x")
            selected=tk.BooleanVar(); time_in=tk.StringVar(value="08:00"); time_out=tk.StringVar(value="17:00")
            ttk.Checkbutton(row,variable=selected).pack(side="left",padx=(4,20))
            ttk.Label(row,text=f"{employee['name']}  [{employee['employee_no']}]",width=37).pack(side="left")
            ttk.Entry(row,textvariable=time_in,width=12).pack(side="left",padx=(0,20))
            ttk.Entry(row,textvariable=time_out,width=12).pack(side="left")
            self.rows.append((employee,row,selected,time_in,time_out))
        self.rows_frame.bind("<Configure>",lambda _e:canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",lambda e:canvas.itemconfigure(self.window,width=e.width))
        entry.bind("<KeyRelease>",self.filter_rows)
        buttons=ttk.Frame(body); buttons.pack(fill="x",pady=(12,0))
        ttk.Button(buttons,text="Select all",command=lambda:self.select_all(True)).pack(side="left")
        ttk.Button(buttons,text="Clear",command=lambda:self.select_all(False)).pack(side="left",padx=5)
        ttk.Button(buttons,text="Cancel",command=self.destroy).pack(side="right")
        ttk.Button(buttons,text="Authorize and Save",style="Primary.TButton",command=self.save).pack(side="right",padx=8)
        self.transient(parent); self.grab_set(); self.bind("<Escape>",lambda _e:self.destroy())
    def select_all(self,value):
        for _employee,row,var,_tin,_tout in self.rows:
            if row.winfo_manager(): var.set(value)
    def apply_defaults(self):
        for _employee,_row,var,tin,tout in self.rows:
            if var.get(): tin.set(self.default_in.get()); tout.set(self.default_out.get())
    def filter_rows(self,_event=None):
        text=self.search.get().strip().lower()
        for employee,row,_var,_tin,_tout in self.rows:
            if text in f"{employee['name']} {employee['employee_no']} {employee['position']}".lower(): row.pack(fill="x")
            else: row.pack_forget()
    def save(self):
        try:
            work_date=valid_date(self.work_date.get(),True); result=[]
            for employee,_row,selected,tin,tout in self.rows:
                if not selected.get(): continue
                started=datetime.fromisoformat(f"{work_date}T{datetime.strptime(tin.get().strip(),'%H:%M').strftime('%H:%M:%S')}")
                ended=datetime.fromisoformat(f"{work_date}T{datetime.strptime(tout.get().strip(),'%H:%M').strftime('%H:%M:%S')}")
                result.append((employee,started,ended))
            if not result: raise ValueError("Select at least one employee.")
            self.result=result; self.destroy()
        except ValueError as exc: messagebox.showerror(APP_TITLE,str(exc),parent=self)


class CashAdvanceGrantDialog(tk.Toplevel):
    def __init__(self,parent,employees,banks,allocations):
        super().__init__(parent); self.title("Grant Cash Advance"); self.result=None
        self.banks=banks; self.allocations=allocations
        screen_width,screen_height=self.winfo_screenwidth(),self.winfo_screenheight()
        self.geometry(f"{max(820,min(980,screen_width-100))}x{max(630,min(760,screen_height-100))}")
        self.minsize(780,600); self.resizable(True,True)
        body=ttk.Frame(self,padding=18); body.pack(fill="both",expand=True)
        body.columnconfigure(0,weight=1); body.rowconfigure(2,weight=1)
        ttk.Label(body,text="Grant employee cash advance",style="DialogTitle.TLabel").grid(row=0,column=0,sticky="w")
        self.search=tk.StringVar(); search=ttk.Frame(body); search.grid(row=1,column=0,sticky="ew",pady=(10,5))
        ttk.Label(search,text="Search employees").pack(side="left"); entry=ttk.Entry(search,textvariable=self.search); entry.pack(side="left",fill="x",expand=True,padx=8)
        table=ttk.Frame(body); table.grid(row=2,column=0,sticky="nsew")
        table.columnconfigure(0,weight=1); table.rowconfigure(0,weight=1)
        self.tree=ttk.Treeview(table,columns=("no","name","position","class"),show="headings",height=7)
        for key,label,width in (("no","Employee No.",120),("name","Name",220),("position","Position",170),("class","Class",100)):
            self.tree.heading(key,text=label); self.tree.column(key,width=width,stretch=True)
        tree_scroll=ttk.Scrollbar(table,orient="vertical",command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.grid(row=0,column=0,sticky="nsew"); tree_scroll.grid(row=0,column=1,sticky="ns")
        self.employees={str(e["id"]):e for e in employees}
        def render(*_):
            self.tree.delete(*self.tree.get_children()); term=self.search.get().strip().lower()
            for e in employees:
                if term in f"{e['employee_no']} {e['name']} {e['position']} {e['class']}".lower(): self.tree.insert("","end",iid=e["id"],values=(e["employee_no"],e["name"],e["position"],e["class"]))
        entry.bind("<KeyRelease>",render); render()
        form=ttk.Frame(body); form.grid(row=3,column=0,sticky="ew",pady=(10,0))
        self.vars={"amount":tk.StringVar(),"date":tk.StringVar(value=date.today().isoformat()),
            "reason":tk.StringVar(),"method":tk.StringVar(value="Cash Allocation"),
            "allocation":tk.StringVar(),"bank":tk.StringVar(),
            "repayment_plan":tk.StringVar(value="Salary Deduction"),"weekly_cap":tk.StringVar()}
        self.widgets = {}
        specs=(("amount","Amount"),("date","Advance date"),("reason","Reason"),
            ("method","Funding source"),("allocation","Petty cash / direct procurement"),
            ("bank","Bank account"),("repayment_plan","Repayment method"),
            ("weekly_cap","Maximum weekly salary deduction (blank = available salary)"))
        for index,(key,label) in enumerate(specs):
            row,col=divmod(index,2); cell=ttk.Frame(form); cell.grid(row=row,column=col,sticky="ew",padx=(0 if col==0 else 8,8 if col==0 else 0),pady=4)
            required = key in {"amount", "date", "reason", "method", "repayment_plan"}
            ttk.Label(cell,text=label + (" *" if required else "")).pack(anchor="w")
            if key=="method": widget=ttk.Combobox(cell,textvariable=self.vars[key],values=["Cash Allocation","Bank Transfer"],state="readonly")
            elif key=="allocation": widget=ttk.Combobox(cell,textvariable=self.vars[key],values=list(allocations),state="readonly")
            elif key=="bank": widget=ttk.Combobox(cell,textvariable=self.vars[key],values=list(banks),state="readonly")
            elif key=="date":
                line=ttk.Frame(cell); line.pack(fill="x")
                widget=ttk.Entry(line,textvariable=self.vars[key],state="readonly")
                widget.pack(side="left",fill="x",expand=True)
                ttk.Button(line,text="Calendar",width=9,
                           command=lambda:DatePickerPopup(self,self.vars["date"])).pack(
                               side="left",padx=(4,0))
            elif key=="repayment_plan": widget=ttk.Combobox(cell,textvariable=self.vars[key],
                values=["Salary Deduction","Cash Repayment","Bank Repayment","Manual / Mixed"],state="readonly")
            else: widget=ttk.Entry(cell,textvariable=self.vars[key])
            if key!="date": widget.pack(fill="x")
            self.widgets[key] = widget
            form.columnconfigure(col,weight=1)
            if key=="bank": self.bank_widget=widget
            if key=="allocation": self.allocation_widget=widget
            if key=="weekly_cap": self.cap_widget=widget
        buttons=ttk.Frame(body); buttons.grid(row=4,column=0,sticky="ew",pady=(12,0)); ttk.Button(buttons,text="Cancel",command=self.destroy).pack(side="right")
        ttk.Button(buttons,text="Authorize and Commit Cash Advance",style="Primary.TButton",command=self.save).pack(side="right",padx=8)
        def update_source_state(*_args):
            is_transfer=self.vars["method"].get()=="Bank Transfer"
            self.bank_widget.configure(state="readonly" if is_transfer else "disabled")
            if not is_transfer:self.vars["bank"].set("")
            self.allocation_widget.configure(state="disabled" if is_transfer else "readonly")
            if is_transfer:self.vars["allocation"].set("")
        def update_plan_state(*_args):
            salary=self.vars["repayment_plan"].get()=="Salary Deduction"
            self.cap_widget.configure(state="normal" if salary else "disabled")
            if not salary:self.vars["weekly_cap"].set("")
        self.vars["method"].trace_add("write",update_source_state); update_source_state()
        self.vars["repayment_plan"].trace_add("write",update_plan_state); update_plan_state()
        self.transient(parent); self.grab_set(); self.bind("<Escape>",lambda _e:self.destroy())
    def save(self):
        selected=self.tree.selection()
        if not selected: messagebox.showerror(APP_TITLE,"Select an employee.",parent=self); return
        required = ["amount", "date", "reason", "method", "repayment_plan"]
        required.append("bank" if self.vars["method"].get() == "Bank Transfer" else "allocation")
        if flash_missing_fields(self, self.vars, self.widgets, required):
            return
        try:
            amount = cents(self.vars["amount"].get())
            if amount <= 0:
                raise ValueError("Amount must be greater than zero.")
            valid_date(self.vars["date"].get(), True)
            if (self.vars["repayment_plan"].get() == "Salary Deduction"
                    and self.vars["weekly_cap"].get().strip()
                    and cents(self.vars["weekly_cap"].get()) <= 0):
                raise ValueError("The weekly deduction limit must be positive or left blank.")
        except ValueError as exc:
            message = str(exc).lower()
            if "date" in message:
                flash_required_widgets(self, [self.widgets["date"]])
            elif "weekly" in message:
                flash_required_widgets(self, [self.widgets["weekly_cap"]])
            else:
                flash_required_widgets(self, [self.widgets["amount"]])
            messagebox.showerror(APP_TITLE, str(exc), parent=self)
            return
        self.result={key:var.get().strip() for key,var in self.vars.items()}; self.result["employee_id"]=int(selected[0]); self.destroy()


class CashAdvanceBatchDialog(tk.Toplevel):
    """Stage multiple Wednesday advances and authorize the batch once."""
    def __init__(self, parent, employees, banks, allocations):
        super().__init__(parent)
        self.title("Batch Cash Advance Grant")
        self.geometry("1180x790"); self.minsize(980, 680); self.resizable(True, True)
        self.result = None
        self.employees = {str(row["id"]): row for row in employees}
        self.banks, self.allocations = banks, allocations
        self.staged = {}
        body = ttk.Frame(self, padding=18); body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1); body.rowconfigure(4, weight=1)
        ttk.Label(body, text="Batch employee cash advances", style="DialogTitle.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(
            body,
            text="Use one effective date and one funding source. Stage each employee amount, then authorize the complete batch once.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 10))

        shared = ttk.LabelFrame(body, text="Batch funding", padding=10)
        shared.grid(row=2, column=0, sticky="ew")
        for column in range(4): shared.columnconfigure(column, weight=1)
        self.vars = {
            "date": tk.StringVar(value=date.today().isoformat()),
            "method": tk.StringVar(value="Cash Allocation"),
            "allocation": tk.StringVar(), "bank": tk.StringVar(),
            "amount": tk.StringVar(), "reason": tk.StringVar(),
            "repayment_plan": tk.StringVar(value="Salary Deduction"),
            "weekly_cap": tk.StringVar(), "search": tk.StringVar(),
        }
        self.widgets = {}
        ttk.Label(shared, text="Effective advance date *").grid(row=0, column=0, sticky="w")
        date_line = ttk.Frame(shared); date_line.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        date_widget = ttk.Entry(date_line, textvariable=self.vars["date"], state="readonly")
        date_widget.pack(side="left", fill="x", expand=True); self.widgets["date"] = date_widget
        ttk.Button(date_line, text="Calendar", width=9,
                   command=lambda: DatePickerPopup(self, self.vars["date"])).pack(
                       side="left", padx=(4, 0))
        ttk.Label(shared, text="Funding source").grid(row=0, column=1, sticky="w")
        self.method_widget = ttk.Combobox(
            shared, textvariable=self.vars["method"],
            values=["Cash Allocation", "Bank Transfer"], state="readonly")
        self.method_widget.grid(row=1, column=1, sticky="ew", padx=(0, 8))
        self.widgets["method"] = self.method_widget
        ttk.Label(shared, text="Petty cash / direct procurement").grid(row=0, column=2, sticky="w")
        self.allocation_widget = ttk.Combobox(
            shared, textvariable=self.vars["allocation"],
            values=list(allocations), state="readonly")
        self.allocation_widget.grid(row=1, column=2, sticky="ew", padx=(0, 8))
        self.widgets["allocation"] = self.allocation_widget
        ttk.Label(shared, text="Bank account").grid(row=0, column=3, sticky="w")
        self.bank_widget = ttk.Combobox(
            shared, textvariable=self.vars["bank"], values=list(banks), state="readonly")
        self.bank_widget.grid(row=1, column=3, sticky="ew")
        self.widgets["bank"] = self.bank_widget

        entry_area = ttk.Panedwindow(body, orient="horizontal")
        entry_area.grid(row=3, column=0, sticky="nsew", pady=(10, 8))
        employee_frame = ttk.LabelFrame(entry_area, text="Select employees", padding=8)
        details_frame = ttk.LabelFrame(entry_area, text="Advance details for selected employees", padding=8)
        entry_area.add(employee_frame, weight=3); entry_area.add(details_frame, weight=2)
        employee_frame.columnconfigure(0, weight=1); employee_frame.rowconfigure(1, weight=1)
        ttk.Entry(employee_frame, textvariable=self.vars["search"]).grid(
            row=0, column=0, sticky="ew", pady=(0, 5))
        self.employee_tree = ttk.Treeview(
            employee_frame, columns=("no", "name", "position", "class"),
            show="headings", selectmode="extended", height=8)
        for key, label, width in (("no", "Employee No.", 110), ("name", "Name", 190),
                                  ("position", "Position", 140), ("class", "Class", 80)):
            self.employee_tree.heading(key, text=label); self.employee_tree.column(key, width=width)
        employee_scroll = ttk.Scrollbar(employee_frame, orient="vertical", command=self.employee_tree.yview)
        self.employee_tree.configure(yscrollcommand=employee_scroll.set)
        self.employee_tree.grid(row=1, column=0, sticky="nsew"); employee_scroll.grid(row=1, column=1, sticky="ns")

        detail_fields = (
            ("amount", "Amount"), ("reason", "Reason"),
            ("repayment_plan", "Repayment method"),
            ("weekly_cap", "Maximum weekly deduction (optional)"),
        )
        details_frame.columnconfigure(0, weight=1)
        for row_index, (key, label) in enumerate(detail_fields):
            required = key in {"amount", "reason", "repayment_plan"}
            ttk.Label(details_frame, text=label + (" *" if required else "")).grid(
                row=row_index * 2, column=0, sticky="w")
            if key == "repayment_plan":
                widget = ttk.Combobox(
                    details_frame, textvariable=self.vars[key],
                    values=["Salary Deduction", "Cash Repayment", "Bank Repayment", "Manual / Mixed"],
                    state="readonly")
            else:
                widget = ttk.Entry(details_frame, textvariable=self.vars[key])
            widget.grid(row=row_index * 2 + 1, column=0, sticky="ew", pady=(0, 7))
            self.widgets[key] = widget
            if key == "weekly_cap": self.cap_widget = widget
        detail_buttons = ttk.Frame(details_frame)
        detail_buttons.grid(row=8, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(detail_buttons, text="Stage Selected Employees", style="Primary.TButton",
                   command=self.stage_selected).pack(side="left")

        staged_frame = ttk.LabelFrame(body, text="Staged advances", padding=8)
        staged_frame.grid(row=4, column=0, sticky="nsew")
        staged_frame.columnconfigure(0, weight=1); staged_frame.rowconfigure(1, weight=1)
        staged_bar = ttk.Frame(staged_frame); staged_bar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ttk.Button(staged_bar, text="Remove Selected", command=self.remove_staged).pack(side="left")
        self.total_label = ttk.Label(staged_bar, text="Entries: 0 | Batch total: 0.00", style="Section.TLabel")
        self.total_label.pack(side="right")
        columns = (("employee", "Employee", 190), ("number", "Employee No.", 110),
                   ("amount", "Amount", 100), ("plan", "Repayment", 125),
                   ("cap", "Weekly Limit", 100), ("reason", "Reason", 260))
        self.staged_tree = ttk.Treeview(
            staged_frame, columns=[item[0] for item in columns], show="headings", height=8)
        for key, label, width in columns:
            self.staged_tree.heading(key, text=label); self.staged_tree.column(key, width=width)
        staged_scroll = ttk.Scrollbar(staged_frame, orient="vertical", command=self.staged_tree.yview)
        self.staged_tree.configure(yscrollcommand=staged_scroll.set)
        self.staged_tree.grid(row=1, column=0, sticky="nsew"); staged_scroll.grid(row=1, column=1, sticky="ns")

        buttons = ttk.Frame(body); buttons.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Review and Authorize Batch", style="Primary.TButton",
                   command=self.save).pack(side="right", padx=(0, 8))
        self.vars["search"].trace_add("write", self.render_employees)
        self.vars["method"].trace_add("write", self.update_source_state)
        self.vars["repayment_plan"].trace_add("write", self.update_plan_state)
        self.render_employees(); self.update_source_state(); self.update_plan_state()
        if allocations: self.vars["allocation"].set(next(iter(allocations)))
        if banks: self.vars["bank"].set(next(iter(banks)))
        self.transient(parent); self.grab_set(); self.bind("<Escape>", lambda _e: self.destroy())

    def render_employees(self, *_args):
        self.employee_tree.delete(*self.employee_tree.get_children())
        term = self.vars["search"].get().strip().lower()
        for key, employee in self.employees.items():
            haystack = f"{employee['employee_no']} {employee['name']} {employee['position']} {employee['class']}".lower()
            if term in haystack:
                self.employee_tree.insert("", "end", iid=key, values=(
                    employee["employee_no"], employee["name"], employee["position"], employee["class"]))

    def update_source_state(self, *_args):
        transfer = self.vars["method"].get() == "Bank Transfer"
        self.bank_widget.configure(state="readonly" if transfer else "disabled")
        self.allocation_widget.configure(state="disabled" if transfer else "readonly")

    def update_plan_state(self, *_args):
        salary = self.vars["repayment_plan"].get() == "Salary Deduction"
        self.cap_widget.configure(state="normal" if salary else "disabled")
        if not salary: self.vars["weekly_cap"].set("")

    def stage_selected(self):
        selected = self.employee_tree.selection()
        if not selected:
            messagebox.showerror(APP_TITLE, "Select at least one employee.", parent=self); return
        if flash_missing_fields(self, self.vars, self.widgets, ("amount", "reason", "repayment_plan")):
            return
        try:
            amount = cents(self.vars["amount"].get())
            if amount <= 0: raise ValueError("Enter a positive advance amount.")
            if not self.vars["reason"].get().strip(): raise ValueError("Reason is required.")
            weekly_cap = 0
            if self.vars["repayment_plan"].get() == "Salary Deduction" and self.vars["weekly_cap"].get().strip():
                weekly_cap = cents(self.vars["weekly_cap"].get())
                if weekly_cap <= 0: raise ValueError("Weekly deduction limit must be positive.")
        except ValueError as exc:
            message = str(exc).lower()
            flash_required_widgets(
                self,
                [self.widgets["weekly_cap"] if "weekly" in message else self.widgets["amount"]],
            )
            messagebox.showerror(APP_TITLE, str(exc), parent=self); return
        for employee_id in selected:
            employee = self.employees[employee_id]
            self.staged[employee_id] = {
                "employee_id": int(employee_id), "employee": employee["name"],
                "employee_no": employee["employee_no"], "amount_cents": amount,
                "reason": self.vars["reason"].get().strip(),
                "repayment_plan": self.vars["repayment_plan"].get(),
                "weekly_cap_cents": weekly_cap,
            }
        self.refresh_staged()

    def remove_staged(self):
        for item in self.staged_tree.selection(): self.staged.pop(item, None)
        self.refresh_staged()

    def refresh_staged(self):
        self.staged_tree.delete(*self.staged_tree.get_children())
        total = 0
        for key, row in self.staged.items():
            total += row["amount_cents"]
            self.staged_tree.insert("", "end", iid=key, values=(
                row["employee"], row["employee_no"], money(row["amount_cents"]),
                row["repayment_plan"], money(row["weekly_cap_cents"]) if row["weekly_cap_cents"] else "No limit",
                row["reason"]))
        self.total_label.config(text=f"Entries: {len(self.staged)} | Batch total: {money(total)}")

    def save(self):
        if not self.staged:
            messagebox.showerror(APP_TITLE, "Stage at least one employee advance.", parent=self); return
        required = ["date", "method"]
        required.append("bank" if self.vars["method"].get() == "Bank Transfer" else "allocation")
        if flash_missing_fields(self, self.vars, self.widgets, required):
            return
        try:
            valid_date(self.vars["date"].get(), True)
        except ValueError as exc:
            flash_required_widgets(self, [self.widgets["date"]])
            messagebox.showerror(APP_TITLE, str(exc), parent=self); return
        if self.vars["method"].get() == "Bank Transfer":
            if self.vars["bank"].get() not in self.banks:
                messagebox.showerror(APP_TITLE, "Select a funded bank account.", parent=self); return
        elif self.vars["allocation"].get() not in self.allocations:
            messagebox.showerror(APP_TITLE, "Select an active cash allocation.", parent=self); return
        self.result = {
            "date": self.vars["date"].get(), "method": self.vars["method"].get(),
            "allocation": self.vars["allocation"].get(), "bank": self.vars["bank"].get(),
            "entries": list(self.staged.values()),
        }
        self.destroy()


class CashAdvanceRecoveryDialog(tk.Toplevel):
    def __init__(self,parent,advances,banks):
        super().__init__(parent); self.title("Record Advance Recovery"); self.result=None
        self.advances=advances; self.banks=banks; self.geometry("760x410"); self.minsize(700,390)
        body=ttk.Frame(self,padding=20); body.pack(fill="both",expand=True)
        ttk.Label(body,text="Record employee cash-advance recovery",style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(body,text="Salary deductions reduce weekly net pay. A bank is required only for a bank repayment.",style="Muted.TLabel").pack(anchor="w",pady=(2,12))
        form=ttk.Frame(body); form.pack(fill="x"); form.columnconfigure(0,weight=1); form.columnconfigure(1,weight=1)
        self.vars={"advance":tk.StringVar(),"amount":tk.StringVar(),
            "txn_date":tk.StringVar(value=date.today().isoformat()),"method":tk.StringVar(),
            "bank":tk.StringVar(),"reference":tk.StringVar(),"notes":tk.StringVar()}
        self.widgets={}
        specs=(("advance","Cash advance"),("amount","Amount"),("txn_date","Transaction date"),
            ("method","Recovery method"),("bank","Bank receiving repayment"),("reference","Reference"),("notes","Notes"))
        for index,(key,label) in enumerate(specs):
            row,col=divmod(index,2); cell=ttk.Frame(form); cell.grid(row=row,column=col,sticky="ew",padx=(0,8) if col==0 else (8,0),pady=5)
            ttk.Label(cell,text=label).pack(anchor="w")
            if key=="advance":widget=ttk.Combobox(cell,textvariable=self.vars[key],values=list(advances),state="readonly")
            elif key=="method":widget=ttk.Combobox(cell,textvariable=self.vars[key],values=["Cash Repayment","Bank Repayment","Salary Deduction"],state="readonly")
            elif key=="bank":widget=ttk.Combobox(cell,textvariable=self.vars[key],values=list(banks),state="readonly")
            elif key=="txn_date":
                line=ttk.Frame(cell); line.pack(fill="x")
                widget=ttk.Entry(line,textvariable=self.vars[key],state="readonly")
                widget.pack(side="left",fill="x",expand=True)
                ttk.Button(line,text="Calendar",width=9,
                           command=lambda:DatePickerPopup(self,self.vars["txn_date"])).pack(
                               side="left",padx=(4,0))
            else:widget=ttk.Entry(cell,textvariable=self.vars[key])
            if key!="txn_date":widget.pack(fill="x")
            if key=="bank":self.bank_widget=widget
            self.widgets[key]=widget
        self.plan_note=ttk.Label(body,text="",style="Muted.TLabel"); self.plan_note.pack(anchor="w",pady=(10,0))
        buttons=ttk.Frame(body); buttons.pack(fill="x",pady=(18,0))
        ttk.Button(buttons,text="Cancel",command=self.destroy).pack(side="right")
        ttk.Button(buttons,text="Continue to PIN Verification",style="Primary.TButton",command=self.save).pack(side="right",padx=8)
        def update_advance(*_):
            row=advances.get(self.vars["advance"].get())
            if not row:return
            plan=row["repayment_plan"] if "repayment_plan" in row.keys() else "Manual / Mixed"
            self.vars["method"].set(plan if plan in {"Cash Repayment","Bank Repayment","Salary Deduction"} else "Cash Repayment")
            self.vars["amount"].set(money(row["outstanding"]))
            self.plan_note.config(text=f"Selected repayment plan: {plan}. Outstanding: {money(row['outstanding'])}")
        def update_bank(*_):
            needed=self.vars["method"].get()=="Bank Repayment"
            self.bank_widget.configure(state="readonly" if needed else "disabled")
            if not needed:self.vars["bank"].set("")
        self.vars["advance"].trace_add("write",update_advance)
        self.vars["method"].trace_add("write",update_bank)
        if advances:self.vars["advance"].set(next(iter(advances)))
        update_bank(); self.transient(parent); self.grab_set(); self.bind("<Escape>",lambda _e:self.destroy())
    def save(self):
        required=["advance","amount","txn_date","method"]
        if self.vars["method"].get()=="Bank Repayment": required.append("bank")
        if flash_missing_fields(self,self.vars,self.widgets,required): return
        try:
            amount=cents(self.vars["amount"].get())
            if amount<=0: raise ValueError("Amount must be greater than zero.")
            valid_date(self.vars["txn_date"].get(),True)
            selected=self.advances.get(self.vars["advance"].get())
            if selected and amount>int(selected["outstanding"]):
                raise ValueError("Recovery amount cannot exceed the outstanding advance.")
        except ValueError as exc:
            target="txn_date" if "date" in str(exc).lower() else "amount"
            flash_required_widgets(self,[self.widgets[target]])
            messagebox.showerror(APP_TITLE,str(exc),parent=self); return
        self.result={key:value.get().strip() for key,value in self.vars.items()}; self.destroy()


class AttendanceEditDialog(tk.Toplevel):
    def __init__(self, parent, attendance):
        super().__init__(parent); self.title("Correct Attendance"); self.result=None
        self.resizable(False,False)
        body=ttk.Frame(self,padding=20); body.pack(fill="both",expand=True)
        ttk.Label(body,text="Correct closed attendance",style="DialogTitle.TLabel").grid(
            row=0,column=0,columnspan=3,sticky="w")
        ttk.Label(body,text=(f"{attendance['name']} [{attendance['employee_no']}]\n"
            f"Original: {attendance['clock_in'].replace('T',' ')} to {attendance['clock_out'].replace('T',' ')} | "
            f"Gross {money(attendance['gross_cents'])}"),style="Muted.TLabel").grid(
            row=1,column=0,columnspan=3,sticky="w",pady=(3,14))
        original_in=datetime.fromisoformat(attendance["clock_in"])
        original_out=datetime.fromisoformat(attendance["clock_out"])
        self.vars={
            "date":tk.StringVar(value=original_in.date().isoformat()),
            "time_in":tk.StringVar(value=original_in.strftime("%H:%M")),
            "time_out":tk.StringVar(value=original_out.strftime("%H:%M")),
            "reason":tk.StringVar(),
        }
        self.widgets={}
        for row_index,(key,label) in enumerate((("date","Work date"),("time_in","Time in (HH:MM)"),
                                                ("time_out","Time out (HH:MM)"),("reason","Correction reason")),2):
            ttk.Label(body,text=label).grid(row=row_index,column=0,sticky="w",pady=5,padx=(0,12))
            entry=ttk.Entry(body,textvariable=self.vars[key],width=34)
            entry.grid(row=row_index,column=1,sticky="ew",pady=5); self.widgets[key]=entry
            if key=="date":
                ttk.Button(body,text="\U0001F4C5",width=3,
                           command=lambda:DatePickerPopup(self,self.vars["date"])).grid(
                    row=row_index,column=2,padx=(5,0))
        footer=ttk.Frame(body); footer.grid(row=6,column=0,columnspan=3,sticky="e",pady=(15,0))
        ttk.Button(footer,text="Cancel",command=self.destroy).pack(side="right")
        ttk.Button(footer,text="Continue to PIN Authorization",style="Primary.TButton",
                   command=self.save).pack(side="right",padx=(0,8))
        self.transient(parent); self.grab_set(); self.bind("<Escape>",lambda _e:self.destroy())
    def save(self):
        if flash_missing_fields(self,self.vars,self.widgets,["date","time_in","time_out","reason"]):return
        try:
            work_date=valid_date(self.vars["date"].get(),True)
            time_in=datetime.strptime(self.vars["time_in"].get().strip(),"%H:%M").strftime("%H:%M:%S")
            time_out=datetime.strptime(self.vars["time_out"].get().strip(),"%H:%M").strftime("%H:%M:%S")
            started=datetime.fromisoformat(f"{work_date}T{time_in}")
            ended=datetime.fromisoformat(f"{work_date}T{time_out}")
            if ended<=started:raise ValueError("Time out must be later than time in.")
        except ValueError as exc:
            flash_required_widgets(self,[self.widgets["date"],self.widgets["time_in"],self.widgets["time_out"]])
            messagebox.showerror(APP_TITLE,str(exc),parent=self);return
        self.result={"started":started,"ended":ended,"reason":self.vars["reason"].get().strip()}
        self.destroy()


class WeeklyEmployeeDetailsDialog(tk.Toplevel):
    def __init__(self,parent,employee_id,project_id,week_start,week_end):
        super().__init__(parent); self.parent_tab=parent; self.db=parent.db
        self.employee_id=employee_id; self.project_id=project_id
        self.week_start=week_start; self.week_end=week_end
        employee=self.db.one("SELECT employee_no,name FROM employees WHERE id=?",(employee_id,))
        self.title("Weekly Attendance Details"); self.geometry("1050x620"); self.minsize(850,500)
        body=ttk.Frame(self,padding=18); body.pack(fill="both",expand=True)
        ttk.Label(body,text=f"{employee['name']} — daily attendance",style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(body,text=f"{employee['employee_no']} | {week_start} through {week_end}",style="Muted.TLabel").pack(anchor="w",pady=(2,8))
        self.tree=make_tree(body,[("date","Date",90),("in","Time In",145),("out","Time Out",145),
            ("regular","Regular",75),("ot","OT",65),("gross","Gross",95),("closure","Daily Close",135),
            ("payroll","Payroll Batch",145),("revisions","Corrections",80)])
        self.tree.bind("<Double-1>",self.edit_selected)
        footer=ttk.Frame(body); footer.pack(fill="x",pady=(8,0))
        ttk.Label(footer,text="Double-click a row to correct its time entry.",style="Muted.TLabel").pack(side="left")
        ttk.Button(footer,text="Close",command=self.destroy).pack(side="right")
        ttk.Button(footer,text="Edit Selected Attendance",style="Primary.TButton",command=self.edit_selected).pack(side="right",padx=8)
        self.refresh(); self.transient(parent); self.grab_set()
    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        rows=self.db.all("""SELECT a.*,COALESCE(cb.closure_ref,'') closure_ref,
            COALESCE(pb.batch_ref,'') payroll_ref FROM attendance a
            JOIN employees e ON e.id=a.employee_id
            LEFT JOIN attendance_closure_batches cb ON cb.id=a.closure_batch_id
            LEFT JOIN payroll_batches pb ON pb.id=a.payroll_batch_id
            WHERE a.employee_id=? AND COALESCE(a.project_id,e.project_id)=?
              AND SUBSTR(a.clock_in,1,10) BETWEEN ? AND ? ORDER BY a.clock_in,a.id""",
            (self.employee_id,self.project_id,self.week_start,self.week_end))
        for row in rows:self.tree.insert("","end",iid=row["id"],values=(row["clock_in"][:10],
            row["clock_in"].replace("T"," "),row["clock_out"].replace("T"," "),row["regular_hours"],
            row["overtime_hours"],money(row["gross_cents"]),row["closure_ref"] or "—",
            row["payroll_ref"] or "Not committed",row["revision_count"]))
    def edit_selected(self,_event=None):
        selected=self.tree.selection()
        if not selected:return
        if self.parent_tab.edit_attendance_id(int(selected[0])):self.refresh()


class PayrollBatchDetailsDialog(tk.Toplevel):
    def __init__(self,parent,db,batch_id):
        super().__init__(parent); self.title("Committed Weekly Payroll"); self.geometry("1180x680")
        self.minsize(980,580); self.resizable(True,True)
        batch=db.one("SELECT * FROM payroll_batches WHERE id=?",(batch_id,)); body=ttk.Frame(self,padding=18); body.pack(fill="both",expand=True)
        ttk.Label(body,text=f"Payroll batch {batch['batch_ref']}",style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(body,text=f"{batch['period_start']} to {batch['period_end']}  |  Gross {money(batch['gross_cents'])}  |  Deductions {money(batch['deduction_cents'])}  |  Corrections {money(batch['adjustment_cents'])}  |  Net {money(batch['net_cents'])}",style="Muted.TLabel").pack(anchor="w",pady=(3,10))
        notebook=ttk.Notebook(body); notebook.pack(fill="both",expand=True)
        summary_page=ttk.Frame(notebook,padding=6); detail_page=ttk.Frame(notebook,padding=6)
        notebook.add(summary_page,text="Employee Weekly Summary")
        notebook.add(detail_page,text="Daily Attendance Details")
        summary_rows=db.payroll_batch_employee_summary(batch_id)
        ttk.Label(summary_page,text="One consolidated salary entry per employee",
                  style="Section.TLabel").pack(anchor="w",pady=(0,5))
        ttk.Label(summary_page,text="Gross salary includes regular and overtime pay. Net weekly pay is gross salary less recorded cash-advance deductions.",
                  style="Muted.TLabel").pack(anchor="w",pady=(0,8))
        summary_columns=(("employee","Employee",150),("number","Employee No.",110),
            ("position","Position",110),("days","Days",55),("entries","Logs",55),
            ("regular","Regular Hours",90),("ot","OT Hours",75),
            ("regular_pay","Regular Pay",95),("ot_pay","OT Pay",85),
            ("gross","Gross Salary",100),("deductions","Deductions",95),("adjustments","Corrections",90),
            ("net","Net Weekly Pay",110))
        summary_frame=ttk.Frame(summary_page); summary_frame.pack(fill="both",expand=True)
        summary_tree=ttk.Treeview(summary_frame,columns=[c[0] for c in summary_columns],show="headings")
        for key,label,width in summary_columns:
            summary_tree.heading(key,text=label)
            summary_tree.column(key,width=width,stretch=True,
                anchor="e" if key in {"regular","ot","regular_pay","ot_pay","gross","deductions","adjustments","net"}
                else "center" if key in {"days","entries"} else "w")
        summary_y=ttk.Scrollbar(summary_frame,orient="vertical",command=summary_tree.yview)
        summary_x=ttk.Scrollbar(summary_frame,orient="horizontal",command=summary_tree.xview)
        summary_tree.configure(yscrollcommand=summary_y.set,xscrollcommand=summary_x.set)
        summary_tree.grid(row=0,column=0,sticky="nsew"); summary_y.grid(row=0,column=1,sticky="ns")
        summary_x.grid(row=1,column=0,sticky="ew"); summary_frame.rowconfigure(0,weight=1); summary_frame.columnconfigure(0,weight=1)
        for row in summary_rows:
            net=row["gross_cents"]-row["deduction_cents"]+row["adjustment_cents"]
            summary_tree.insert("","end",iid=row["employee_id"],values=(row["name"],row["employee_no"],
                row["position"],row["attendance_days"],row["attendance_entries"],
                f"{row['regular_hours']:.2f}",f"{row['overtime_hours']:.2f}",
                money(row["regular_pay_cents"]),money(row["overtime_pay_cents"]),
                money(row["gross_cents"]),money(row["deduction_cents"]),money(row["adjustment_cents"]),money(net)))
        summarized_gross=sum(row["gross_cents"] for row in summary_rows)
        summarized_deductions=sum(row["deduction_cents"] for row in summary_rows)
        summarized_adjustments=sum(row["adjustment_cents"] for row in summary_rows)
        ttk.Label(summary_page,text=(f"Employees: {len(summary_rows)}   |   Gross salary: {money(summarized_gross)}   |   "
                  f"Deductions: {money(summarized_deductions)}   |   Corrections: {money(summarized_adjustments)}   |   "
                  f"Net weekly pay: {money(summarized_gross-summarized_deductions+summarized_adjustments)}"),
                  style="Section.TLabel").pack(anchor="e",pady=(8,0))
        columns=(("employee","Employee",160),("in","Time In",150),("out","Time Out",150),("lunch","Lunch",70),("regular","Regular",75),("ot","OT",65),("regpay","Regular Pay",100),("otpay","OT Pay",90),("gross","Gross",100),("revisions","Corrections",80))
        frame=ttk.Frame(detail_page); frame.pack(fill="both",expand=True); tree=ttk.Treeview(frame,columns=[c[0] for c in columns],show="headings")
        for key,label,width in columns: tree.heading(key,text=label); tree.column(key,width=width,stretch=True)
        sy=ttk.Scrollbar(frame,orient="vertical",command=tree.yview); sx=ttk.Scrollbar(frame,orient="horizontal",command=tree.xview)
        tree.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        tree.grid(row=0,column=0,sticky="nsew"); sy.grid(row=0,column=1,sticky="ns"); sx.grid(row=1,column=0,sticky="ew")
        frame.rowconfigure(0,weight=1); frame.columnconfigure(0,weight=1)
        for row in db.all("""SELECT a.*,e.name FROM attendance a JOIN employees e ON e.id=a.employee_id WHERE a.payroll_batch_id=? ORDER BY e.name,a.clock_in""",(batch_id,)):
            tree.insert("","end",iid=row["id"],values=(row["name"],row["clock_in"].replace("T"," "),row["clock_out"].replace("T"," "),row["lunch_hours"],row["regular_hours"],row["overtime_hours"],money(row["regular_pay_cents"]),money(row["overtime_pay_cents"]),money(row["gross_cents"]),row["revision_count"]))
        if hasattr(parent,"edit_attendance_id"):
            def edit_committed_attendance(_event=None):
                selected=tree.selection()
                if selected and parent.edit_attendance_id(int(selected[0])):self.destroy()
            tree.bind("<Double-1>",edit_committed_attendance)
        ttk.Button(body,text="Close",command=self.destroy).pack(anchor="e",pady=(10,0)); self.transient(parent); self.grab_set()


class PayrollTab(BaseTab):
    EMPLOYEE_FIELDS=[("employee_no","Employee number"),("pin","PIN (4+ characters)"),("name","Name"),
        ("birthday","Birthday (YYYY-MM-DD)"),("contact_number","Contact number"),("position","Position"),
        ("class","Class",["Skilled","Labor"]),("daily_rate","Daily rate")]
    def __init__(self,app):
        super().__init__(app)
        ttk.Label(self,text="Attendance and payroll",style="Title.TLabel").pack(anchor="w")
        actions=ttk.Frame(self); actions.pack(fill="x",pady=(8,4))
        ttk.Button(actions,text="+ Add Employee",command=self.add_employee).pack(side="left")
        ttk.Button(actions,text="Edit Employee",command=self.edit_employee).pack(side="left",padx=5)
        ttk.Button(actions,text="Transfer Employee",command=self.transfer_employee).pack(side="left")
        ttk.Button(actions,text="Archive Employee",command=self.archive_employee).pack(side="left",padx=5)
        ttk.Button(actions,text="Batch Attendance",style="Primary.TButton",command=self.batch_attendance).pack(side="left")
        ttk.Button(actions,text="Close Daily Attendance",command=self.close_daily_attendance).pack(side="left",padx=5)
        cards=ttk.Frame(self); cards.pack(fill="x",pady=(4,7))
        (self.running_card,self.running_value,self.period_label,self.period_value)=metric_card_with_detail(cards,"Running payroll","Current period",GREEN)
        (self.last_card,self.last_value,self.last_date_label,self.last_date_value)=metric_card_with_detail(cards,"Last committed batch","Commit date",INK)
        self.open_card,self.open_value=metric_card(cards,"Open attendance",ORANGE)
        layout_metric_cards(cards,(self.running_card,self.last_card,self.open_card))
        clock=tk.Frame(self,bg=NAVY,padx=14,pady=9); clock.pack(fill="x")
        tk.Label(clock,text="SITE KIOSK",bg=NAVY,fg=WHITE,font=("Segoe UI",11,"bold")).pack(side="left",padx=(0,12))
        tk.Label(clock,text="Employee no.",bg=NAVY,fg="#CBD5E1").pack(side="left"); self.employee_no=tk.StringVar()
        ttk.Entry(clock,textvariable=self.employee_no,width=14).pack(side="left",padx=5)
        tk.Label(clock,text="PIN",bg=NAVY,fg="#CBD5E1").pack(side="left"); self.pin=tk.StringVar()
        ttk.Entry(clock,textvariable=self.pin,show="*",width=10).pack(side="left",padx=5)
        ttk.Button(clock,text="IN",style="Success.TButton",command=lambda:self.clock("in")).pack(side="left",padx=3)
        ttk.Button(clock,text="OUT",command=lambda:self.clock("out")).pack(side="left",padx=3)
        ttk.Button(clock,text="Expand Kiosk",style="Primary.TButton",command=self.open_kiosk).pack(side="right")
        self.lists=ttk.Notebook(self); self.lists.pack(fill="both",expand=True,pady=(6,0))
        employee_page,archive_page,attendance_page,weekly_page,batch_page,advance_page=(ttk.Frame(self.lists,padding=4) for _ in range(6))
        for page,title in ((employee_page,"Employee Roster"),(attendance_page,"Attendance Ledger"),
                           (archive_page,"Employee Archive"),
                           (weekly_page,"Weekly Payroll"),(batch_page,"Committed Weekly Payrolls"),
                           (advance_page,"Cash Advances")): self.lists.add(page,text=title)
        self.employees=make_tree(employee_page,[("no","Employee No.",105),("name","Name",155),("project","Project",130),("position","Position",120),("class","Class",75),("daily","Daily Rate",90),("hourly","Hourly Rate",90),("advance","Advance Balance",110),("state","Status",90)])
        archive_actions=ttk.Frame(archive_page); archive_actions.pack(fill="x",pady=(0,4))
        ttk.Label(archive_actions,text="Archived profiles retain attendance, payroll and cash-advance history.",style="Muted.TLabel").pack(side="left")
        ttk.Button(archive_actions,text="Reactivate Employee",style="Primary.TButton",command=self.reactivate_employee).pack(side="right")
        self.archived_employees=make_tree(archive_page,[("no","Employee No.",105),("name","Name",155),
            ("project","Last Project",135),("position","Position",120),("daily","Daily Rate",90),
            ("archived","Archived",145),("reason","Reason",220)])
        self.attendance=make_tree(attendance_page,[("employee","Employee",145),("date","Date",90),("in","Time In",130),("out","Time Out",130),("lunch","Lunch",60),("regular","Regular",65),("ot","OT",55),("gross","Gross Pay",90),("source","Source",75),("closure","Daily Close Ref.",135),("workflow","Payroll Status",125),("revisions","Corrections",75)])
        weekly_controls=ttk.Frame(weekly_page); weekly_controls.pack(fill="x",pady=(0,5))
        ttk.Label(weekly_controls,text="Payroll week").pack(side="left")
        self.week_var=tk.StringVar(value=payroll_week_bounds(date.today())[0])
        ttk.Button(weekly_controls,text="<",width=3,command=lambda:self.shift_week(-7)).pack(side="left",padx=(7,3))
        self.week_entry=ttk.Entry(weekly_controls,textvariable=self.week_var,state="readonly",width=12)
        self.week_entry.pack(side="left")
        ttk.Button(weekly_controls,text="\U0001F4C5",width=3,
                   command=lambda:DatePickerPopup(self,self.week_var)).pack(side="left",padx=3)
        ttk.Button(weekly_controls,text=">",width=3,command=lambda:self.shift_week(7)).pack(side="left")
        ttk.Button(weekly_controls,text="Current Week",command=self.current_week).pack(side="left",padx=7)
        self.week_range_label=ttk.Label(weekly_controls,style="Muted.TLabel"); self.week_range_label.pack(side="left",padx=8)
        ttk.Button(weekly_controls,text="Commit This Week to Expenses",style="Primary.TButton",
                   command=self.commit_weekly).pack(side="right")
        self.weekly_summary=ttk.Label(weekly_page,style="Section.TLabel"); self.weekly_summary.pack(anchor="w",pady=(0,5))
        self.weekly=make_tree(weekly_page,[("employee","Employee",150),("project","Project",125),
            ("days","Closed Days",75),("regular","Regular Hours",85),("ot","OT Hours",70),
            ("gross","Gross",95),("deductions","Advance Deductions",115),("adjustments","Corrections",95),("net","Net Payable",100),
            ("refs","Daily Close References",220),("status","Status",100)])
        self.batches=make_tree(batch_page,[("ref","Batch",145),("start","Period Start",95),("end","Period End",95),("count","Entries",65),("gross","Gross",100),("deductions","Deductions",95),("adjustments","Corrections",95),("net","Net Payable",100),("head","Authorized by",120),("created","Committed",145)])
        advance_actions=ttk.Frame(advance_page); advance_actions.pack(fill="x",pady=(0,4))
        ttk.Button(advance_actions,text="+ Grant Cash Advance",style="Primary.TButton",command=self.grant_cash_advance).pack(side="left")
        ttk.Button(advance_actions,text="+ Batch Cash Advances",style="Primary.TButton",
                   command=self.grant_cash_advance_batch).pack(side="left",padx=5)
        ttk.Button(advance_actions,text="Record Recovery",command=self.record_recovery).pack(side="left",padx=5)
        self.advance_summary=ttk.Label(advance_actions,style="Section.TLabel"); self.advance_summary.pack(side="right")
        pane=ttk.Panedwindow(advance_page,orient="vertical"); pane.pack(fill="both",expand=True)
        advances_frame=ttk.Frame(pane); transactions_frame=ttk.Frame(pane); pane.add(advances_frame,weight=1); pane.add(transactions_frame,weight=1)
        ttk.Label(advances_frame,text="Employee advances",style="Section.TLabel").pack(anchor="w")
        self.advances=make_tree(advances_frame,[("date","Date",90),("batch","Batch Ref.",145),("reference","Advance Ref.",135),("employee","Employee",150),("original","Original",90),("recovered","Recovered",90),("net","Net Amount",90),("mop","Funding Source",110),("plan","Repayment Plan",120),("status","Recovery Status",120),("reason","Reason",180)])
        ttk.Label(transactions_frame,text="Every advance and recovery transaction",style="Section.TLabel").pack(anchor="w",pady=(5,0))
        self.advance_transactions=make_tree(transactions_frame,[("date","Date",90),("employee","Employee",140),("type","Transaction",125),("amount","Amount",90),("mop","MOP",100),("reference","Reference",115),("head","Authorized by",115),("balance","Balance after",95)])
        self.employees.bind("<Double-1>",self.open_employee_profile)
        self.archived_employees.bind("<Double-1>",self.open_archived_employee_profile)
        self.attendance.bind("<Double-1>",self.edit_selected_attendance)
        self.weekly.bind("<Double-1>",self.open_weekly_employee_details)
        self.batches.bind("<Double-1>",self.open_batch_details)
        self.advances.bind("<Double-1>",self.open_selected_advance_employee)
        self.week_var.trace_add("write",lambda *_args:self.refresh_weekly())

    def add_employee(self):
        if not self.require_project(): return
        try:
            employee_number = self.db.next_employee_number(self.project_id)
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc)); return
        win=EmployeeEditorDialog(self, employee_number=employee_number)
        self.wait_window(win); data=win.result
        if not data:return
        try:
            if not data["pin"]: raise ValueError("A PIN of at least four characters is required.")
            birthday=valid_date(data["birthday"]); daily=cents(data["daily_rate"])
            if daily<=0: raise ValueError("Daily rate must be greater than zero.")
            salt,digest=hash_pin(data["pin"])
            with self.db.conn:
                employee_id=self.db.conn.execute("""INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,
                    name,position,class,pay_basis,rate_cents,standard_hours,birthday,
                    contact_number,daily_rate_cents,nbi_clearance,police_clearance,
                    drug_test,biodata,photo_data,photo_filename,photo_mime)
                    VALUES(?,?,?,?,?,?,?,'Daily',?,8,?,?,?,?,?,?,?,?,?,?)""",
                    (self.project_id,data["employee_no"],salt,digest,data["name"],data["position"],
                     data["class"],daily,birthday,data["contact_number"],daily,
                     data["nbi_clearance"],data["police_clearance"],data["drug_test"],
                     data["biodata"],data["photo_data"],data["photo_filename"],data["photo_mime"])).lastrowid
                self.db.conn.execute("""INSERT INTO employee_project_assignments(employee_id,project_id,
                    effective_from,position,daily_rate_cents,reason) VALUES(?,?,?,?,?,'Initial assignment')""",
                    (employee_id,self.project_id,date.today().isoformat(),data["position"],daily))
            self.db.audit(self.project_id,"EMPLOYEE_ADDED",data["name"]); self.app.refresh_all()
        except (ValueError,sqlite3.Error) as exc: messagebox.showerror(APP_TITLE,str(exc))

    def edit_employee(self):
        employee_id=self.selected_id(self.employees)
        if not employee_id:return
        row=self.db.one("SELECT * FROM employees WHERE id=?",(employee_id,)); initial=dict(row); initial["pin"]=""; initial["daily_rate"]=money(employee_daily_rate(row))
        win=EmployeeEditorDialog(self,initial); self.wait_window(win); data=win.result
        if not data:return
        try:
            daily=cents(data["daily_rate"]); birthday=valid_date(data["birthday"])
            if daily<=0: raise ValueError("Daily rate must be greater than zero.")
            pin_sql=""; params=[data["employee_no"],data["name"],data["position"],data["class"],daily,daily,birthday,data["contact_number"],
                data["nbi_clearance"],data["police_clearance"],data["drug_test"],data["biodata"],
                data["photo_data"],data["photo_filename"],data["photo_mime"]]
            if data["pin"]: salt,digest=hash_pin(data["pin"]); pin_sql=",pin_salt=?,pin_hash=?"; params.extend([salt,digest])
            params.append(employee_id)
            self.db.execute(f"""UPDATE employees SET employee_no=?,name=?,position=?,class=?,
                pay_basis='Daily',rate_cents=?,daily_rate_cents=?,standard_hours='8',birthday=?,
                contact_number=?,nbi_clearance=?,police_clearance=?,drug_test=?,biodata=?,
                photo_data=?,photo_filename=?,photo_mime=?{pin_sql} WHERE id=?""",tuple(params)); self.app.refresh_all()
        except (ValueError,sqlite3.Error) as exc: messagebox.showerror(APP_TITLE,str(exc))

    def archive_employee(self):
        employee_id=self.selected_id(self.employees)
        if not employee_id:return
        employee=self.db.one("SELECT * FROM employees WHERE id=?",(employee_id,))
        if not employee:return
        outstanding=self.db.one("""SELECT COALESCE(SUM(a.original_cents),0)-COALESCE(SUM((
            SELECT SUM(t.amount_cents) FROM cash_advance_transactions t WHERE t.advance_id=a.id
            AND t.posted=1 AND t.voided=0 AND t.txn_type<>'Advance')),0) total
            FROM cash_advances a WHERE a.employee_id=? AND a.voided=0""",(employee_id,))["total"]
        initial_note=(f"Outstanding cash advance: {money(max(0,outstanding))}. " if outstanding>0 else "")
        data=dialog(self,"Archive Employee",[("reason","Reason for leaving / archiving")],{"reason":initial_note})
        if not data or not data["reason"].strip():return
        head=self.app.authorize_for_project(employee["project_id"],"Archive employee",
            f"{employee['name']} [{employee['employee_no']}]\n{data['reason']}")
        if not head:return
        try:
            self.db.archive_employee(employee_id,data["reason"],head["id"])
            messagebox.showinfo(APP_TITLE,f"{employee['name']} was moved to the Employee Archive.")
            self.app.refresh_all()
        except (ValueError,sqlite3.Error) as exc:messagebox.showerror(APP_TITLE,str(exc))

    def transfer_employee(self):
        employee_id=self.selected_id(self.employees)
        if not employee_id:return
        employee=self.db.one("SELECT * FROM employees WHERE id=?",(employee_id,))
        projects={f"{row['name']} [#{row['id']}]":row["id"] for row in self.db.all(
            "SELECT id,name FROM projects WHERE id<>? AND status<>'Completed' ORDER BY name",
            (employee["project_id"],))}
        if not projects:messagebox.showinfo(APP_TITLE,"Create another project before transferring an employee.");return
        data=dialog(self,"Transfer Employee",[("project","Destination project",list(projects)),
            ("effective_date","Effective date (YYYY-MM-DD)"),("position","Position in destination project"),
            ("daily_rate","Daily rate"),("reason","Transfer reason")],
            {"project":next(iter(projects)),"effective_date":date.today().isoformat(),
             "position":employee["position"],"daily_rate":money(employee_daily_rate(employee)),"reason":""})
        if not data:return
        try:
            destination_id=projects.get(data["project"]); daily=cents(data["daily_rate"])
            if not destination_id or not data["reason"].strip():raise ValueError("Select a destination and enter a transfer reason.")
            valid_date(data["effective_date"],True)
        except ValueError as exc:messagebox.showerror(APP_TITLE,str(exc));return
        source_project = self.db.one("SELECT status FROM projects WHERE id=?", (employee["project_id"],))
        if source_project and source_project["status"] == "Completed":
            source_head = self.app.authorize_all_heads(
                employee["project_id"], "Transfer employee from completed project",
                f"Release {employee['name']} to {data['project']} effective {data['effective_date']}.",
                allow_completed=True,
            )
            source_head = source_head[0] if source_head else None
        else:
            source_head=self.app.authorize_for_project(employee["project_id"],"Transfer employee — source approval",
                f"Release {employee['name']} to {data['project']} effective {data['effective_date']}.")
        if not source_head:return
        destination_head=self.app.authorize_for_project(destination_id,"Transfer employee — destination approval",
            f"Accept {employee['name']} as {data['position']} at {money(daily)} per day.")
        if not destination_head:return
        try:
            self.db.transfer_employee(employee_id,destination_id,data["effective_date"],data["reason"],
                data["position"],daily,source_head["id"],destination_head["id"])
            messagebox.showinfo(APP_TITLE,f"{employee['name']} was transferred successfully.")
            self.app.refresh_all()
        except (ValueError,sqlite3.Error) as exc:messagebox.showerror(APP_TITLE,str(exc))

    def reactivate_employee(self):
        selected=self.archived_employees.selection()
        if not selected:messagebox.showinfo(APP_TITLE,"Select an archived employee first.");return
        employee_id=int(selected[0]); employee=self.db.one("SELECT * FROM employees WHERE id=?",(employee_id,))
        projects={f"{row['name']} [#{row['id']}]":row["id"] for row in self.db.all(
            "SELECT id,name FROM projects WHERE status<>'Completed' ORDER BY name")}
        data=dialog(self,"Reactivate Employee",[("project","Current project",list(projects)),
            ("effective_date","Reactivation date (YYYY-MM-DD)"),("position","Position"),
            ("daily_rate","Daily rate"),("reason","Reactivation notes")],
            {"project":next((label for label,pid in projects.items() if pid==employee["project_id"]),next(iter(projects),"")),
             "effective_date":date.today().isoformat(),"position":employee["position"],
             "daily_rate":money(employee_daily_rate(employee)),"reason":"Returned to active employment"})
        if not data:return
        try:
            project_id=projects.get(data["project"]);daily=cents(data["daily_rate"])
            if not project_id or not data["reason"].strip():raise ValueError("Select a project and enter reactivation notes.")
        except ValueError as exc:messagebox.showerror(APP_TITLE,str(exc));return
        head=self.app.authorize_for_project(project_id,"Reactivate employee",
            f"{employee['name']} in {data['project']} effective {data['effective_date']}.")
        if not head:return
        try:
            self.db.reactivate_employee(employee_id,project_id,data["effective_date"],data["reason"],
                data["position"],daily,head["id"])
            messagebox.showinfo(APP_TITLE,f"{employee['name']} is active again.")
            self.app.refresh_all();self.lists.select(0)
        except (ValueError,sqlite3.Error) as exc:messagebox.showerror(APP_TITLE,str(exc))

    def open_archived_employee_profile(self,_event=None):
        selected=self.archived_employees.selection()
        if selected:
            win=EmployeeProfileDialog(self,self.db,int(selected[0]));self.wait_window(win)

    def edit_selected_attendance(self,_event=None):
        selected=self.attendance.selection()
        if selected:self.edit_attendance_id(int(selected[0]))

    def edit_attendance_id(self,attendance_id):
        attendance=self.db.one("""SELECT a.*,e.name,e.employee_no,e.project_id current_project_id
            FROM attendance a JOIN employees e ON e.id=a.employee_id WHERE a.id=?""",(attendance_id,))
        if not attendance:return False
        win=AttendanceEditDialog(self,attendance);self.wait_window(win)
        if not win.result:return False
        project_id=attendance["project_id"] or attendance["current_project_id"]
        head=self.app.authorize_for_project(project_id,"Correct closed attendance",
            f"{attendance['name']} [{attendance['employee_no']}]\n{win.result['reason']}")
        if not head:return False
        try:
            result=self.db.revise_attendance(attendance_id,win.result["started"],win.result["ended"],
                win.result["reason"],head["id"])
            notice=("The settled payroll was preserved. A correction of "
                    f"{money(result['delta_cents'])} will be applied to the employee's next weekly payroll."
                    if result["locked_adjustment"] else
                    "The attendance and its uncommitted/unpaid payroll totals were recalculated.")
            messagebox.showinfo(APP_TITLE,f"Attendance corrected successfully.\n\n{notice}")
            self.app.refresh_all();return True
        except (ValueError,sqlite3.Error) as exc:messagebox.showerror(APP_TITLE,str(exc));return False

    def open_weekly_employee_details(self,_event=None):
        selected=self.weekly.selection()
        if not selected or not self.project_id:return
        week_start,week_end=payroll_week_bounds(self.week_var.get() or date.today())
        win=WeeklyEmployeeDetailsDialog(self,int(selected[0]),self.project_id,week_start,week_end)
        self.wait_window(win);self.refresh_weekly()

    def open_employee_profile(self,_event=None):
        selected=self.employees.selection()
        if selected: win=EmployeeProfileDialog(self,self.db,int(selected[0])); self.wait_window(win)
    def open_selected_advance_employee(self,_event=None):
        selected=self.advances.selection()
        if selected:
            row=self.db.one("SELECT employee_id FROM cash_advances WHERE id=?",(int(selected[0]),)); win=EmployeeProfileDialog(self,self.db,row["employee_id"]); self.wait_window(win)
    def open_batch_details(self,_event=None):
        selected=self.batches.selection()
        if selected: win=PayrollBatchDetailsDialog(self,self.db,int(selected[0])); self.wait_window(win)
    def open_kiosk(self):
        if self.require_project(): KioskWindow(self)
    def clock(self,direction=None): self.process_clock(direction,self.employee_no.get(),self.pin.get(),self)
    def process_clock(self,direction,employee_no,pin,parent=None):
        if not self.require_project():return False
        employee=self.db.one("SELECT * FROM employees WHERE project_id=? AND employee_no=? AND active=1",(self.project_id,employee_no.strip()))
        if not employee or not verify_pin(pin,employee["pin_salt"],employee["pin_hash"]): messagebox.showerror(APP_TITLE,"Employee number or PIN is incorrect.",parent=parent); return False
        open_row=self.db.one("SELECT * FROM attendance WHERE employee_id=? AND clock_out=''",(employee["id"],)); now=datetime.now()
        if direction=="in" and open_row: messagebox.showinfo(APP_TITLE,f"{employee['name']} is already clocked in.",parent=parent); return False
        if direction=="out" and not open_row: messagebox.showinfo(APP_TITLE,f"{employee['name']} is not currently clocked in.",parent=parent); return False
        if not open_row:
            self.db.execute("INSERT INTO attendance(employee_id,project_id,clock_in,source) VALUES(?,?,?,'Kiosk')",(employee["id"],employee["project_id"],now.isoformat(timespec="seconds"))); messagebox.showinfo(APP_TITLE,f"Welcome, {employee['name']}!\nTime in: {now:%I:%M %p}",parent=parent)
        else:
            result=compute_shift_pay(datetime.fromisoformat(open_row["clock_in"]),now,employee_daily_rate(employee))
            self.db.execute("""UPDATE attendance SET clock_out=?,hours=?,lunch_hours=?,regular_hours=?,overtime_hours=?,regular_pay_cents=?,overtime_pay_cents=?,gross_cents=? WHERE id=?""",
                (now.isoformat(timespec="seconds"),result["hours"],result["lunch_hours"],result["regular_hours"],result["overtime_hours"],result["regular_pay_cents"],result["overtime_pay_cents"],result["gross_cents"],open_row["id"]))
            messagebox.showinfo(APP_TITLE,f"Goodbye, {employee['name']}!\nPaid hours: {result['hours']}\nOvertime: {result['overtime_hours']}\nGross: {money(result['gross_cents'])}",parent=parent)
        self.pin.set(""); self.app.refresh_all(); return True

    def batch_attendance(self):
        if not self.require_project():return
        employees=self.db.all("SELECT * FROM employees WHERE project_id=? AND active=1 ORDER BY name",(self.project_id,))
        if not employees: messagebox.showinfo(APP_TITLE,"Add employees first."); return
        win=BatchAttendanceDialog(self,employees); self.wait_window(win)
        if not win.result:return
        head=self.app.authorize("Record batch attendance",f"{len(win.result)} manually entered attendance record(s)")
        if not head:return
        try:
            records=[]
            for employee,started,ended in win.result:
                if self.db.one("SELECT 1 FROM attendance WHERE employee_id=? AND clock_out=''",(employee["id"],)): raise ValueError(f"{employee['name']} currently has an open attendance record.")
                result=compute_shift_pay(started,ended,employee_daily_rate(employee))
                records.append((employee["id"],started.isoformat(timespec="seconds"),ended.isoformat(timespec="seconds"),result))
            with self.db.conn:
                for employee_id,started,ended,result in records:
                    self.db.conn.execute("""INSERT INTO attendance(employee_id,project_id,clock_in,clock_out,hours,lunch_hours,regular_hours,overtime_hours,regular_pay_cents,overtime_pay_cents,gross_cents,day_type,source,authorized_by_head_id)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,'Ordinary Day','Manual Batch',?)""",(employee_id,self.project_id,started,ended,result["hours"],result["lunch_hours"],result["regular_hours"],result["overtime_hours"],result["regular_pay_cents"],result["overtime_pay_cents"],result["gross_cents"],head["id"]))
            self.db.audit(self.project_id,"BATCH_ATTENDANCE_ADDED",f"{len(records)} entries authorized by {head['name']}"); self.app.refresh_all()
        except (ValueError,sqlite3.Error) as exc: messagebox.showerror(APP_TITLE,str(exc))

    def close_daily_attendance(self):
        if not self.require_project(): return
        available=self.db.closable_attendance_dates(self.project_id)
        if not available:
            messagebox.showinfo(APP_TITLE,
                "There is no completed attendance awaiting daily closure."); return
        choices={f"{row['work_date']}  |  {row['attendance_count']} employee log(s)  |  {money(row['gross_cents'])}":row
                 for row in available}
        data=dialog(self,"Close Daily Attendance",[
            ("day","Completed attendance date",list(choices)),
        ],{"day":next(iter(choices))})
        if not data:return
        selected=choices.get(data["day"])
        if not selected:return
        head=self.app.authorize(
            "Close daily attendance",
            f"{selected['work_date']}: {selected['attendance_count']} attendance record(s), "
            f"gross {money(selected['gross_cents'])}. This will add the day to Weekly Payroll."
        )
        if not head:return
        try:
            result=self.db.close_attendance_day(
                self.project_id,selected["work_date"],head["id"])
            messagebox.showinfo(APP_TITLE,
                f"Daily attendance closed as {result['reference']}.\n\n"
                f"{result['count']} record(s)\nGross: {money(result['gross_cents'])}\n\n"
                "The amounts are now visible in Weekly Payroll.")
            self.app.refresh_all()
            self.lists.select(3)
        except (ValueError,sqlite3.Error) as exc:
            messagebox.showerror(APP_TITLE,str(exc))

    def current_week(self):
        self.week_var.set(payroll_week_bounds(date.today())[0])

    def shift_week(self,days):
        try:selected=date.fromisoformat(self.week_var.get())
        except ValueError:selected=date.today()
        self.week_var.set((selected+timedelta(days=days)).isoformat())

    def refresh_weekly(self):
        if not hasattr(self,"weekly"):return
        self.weekly.delete(*self.weekly.get_children())
        try:
            week_start,week_end=payroll_week_bounds(self.week_var.get() or date.today())
        except ValueError:
            return
        if self.week_var.get()!=week_start:
            self.week_var.set(week_start);return
        self.week_range_label.config(text=f"Saturday {week_start} through Friday {week_end}")
        if not self.project_id:
            self.weekly_summary.config(text="Select one project to review and commit weekly payroll.")
            return
        rows=self.db.weekly_payroll_summary(self.project_id,week_start)
        gross=deductions=adjustments=net=closed_days=0
        for row in rows:
            gross+=row["gross_cents"]
            if row["attendance_count"]:
                deductions+=row["deduction_cents"]
                adjustments+=row["adjustment_cents"]
                net+=row["net_cents"]
                closed_days+=row["attendance_count"]
            status=("No closed attendance" if not row["attendance_count"] else
                    "Check deductions" if row["net_cents"]<0 else "Ready")
            self.weekly.insert("","end",iid=row["id"],values=(
                row["name"],row["project_name"],row["attendance_count"],
                f"{row['regular_hours_total']:.2f}",f"{row['overtime_hours_total']:.2f}",
                money(row["gross_cents"]),money(row["deduction_cents"] if row["attendance_count"] else 0),
                money(row["adjustment_cents"] if row["attendance_count"] else 0),
                money(max(0,row["net_cents"]) if row["attendance_count"] else 0),
                row["closure_references"] or "—",status))
        self.weekly_summary.config(
            text=f"Closed attendance entries: {closed_days}   |   Gross: {money(gross)}   |   "
                 f"Advance deductions: {money(deductions)}   |   Corrections: {money(adjustments)}   |   "
                 f"Net payable: {money(net)}")

    def commit_weekly(self):
        if not self.require_project():return
        week_start,week_end=payroll_week_bounds(self.week_var.get() or date.today())
        summary=[row for row in self.db.weekly_payroll_summary(self.project_id,week_start)
                 if row["attendance_count"]]
        if not summary:
            messagebox.showinfo(APP_TITLE,
                "Close at least one day's completed attendance for this week first.");return
        gross=sum(row["gross_cents"] for row in summary)
        deductions=sum(row["deduction_cents"] for row in summary)
        adjustments=sum(row["adjustment_cents"] for row in summary)
        net=gross-deductions+adjustments
        if any(row["net_cents"]<0 for row in summary):
            messagebox.showerror(APP_TITLE,
                "One or more employees have salary deductions greater than their weekly gross pay.");return
        head=self.app.authorize(
            "Commit weekly payroll to Expenses",
            f"Week {week_start} to {week_end}: {len(summary)} employee(s), gross {money(gross)}, "
            f"deductions {money(deductions)}, corrections {money(adjustments)}, net payable {money(net)}."
        )
        if not head:return
        try:
            result=self.db.commit_weekly_payroll(
                self.project_id,week_start,head["id"])
            messagebox.showinfo(APP_TITLE,
                f"Weekly payroll committed as {result['reference']}.\n\n"
                f"Gross: {money(result['gross_cents'])}\n"
                f"Advance deductions: {money(result['deduction_cents'])}\n"
                f"Attendance corrections: {money(result['adjustment_cents'])}\n"
                f"Net payable: {money(result['net_cents'])}")
            self.app.refresh_all();self.lists.select(4)
        except (ValueError,sqlite3.Error) as exc:
            messagebox.showerror(APP_TITLE,str(exc))

    def grant_cash_advance(self):
        if not self.require_project():return
        employees=self.db.all("SELECT * FROM employees WHERE project_id=? AND active=1 ORDER BY name",(self.project_id,)); banks={f"{b['bank_name']} - {b['account_name']} (..{b['account_number'][-4:]})":b["id"] for b in self.db.all("SELECT * FROM bank_accounts WHERE active=1 ORDER BY bank_name,account_name")}
        if not employees:messagebox.showinfo(APP_TITLE,"Add employees first.");return
        allocations={}
        for row in self.db.cash_allocation_rows(None,active_only=True):
            balance=self.db.allocation_balance(row["id"])
            if balance<=0:continue
            holder=row["holder"] or row["supplier"] or "Unassigned"
            allocations[f"{row['reference']} | {row['allocation_type']} | {holder} | {money(balance)} remaining"]=row
        if not allocations and not banks:
            messagebox.showinfo(APP_TITLE,"Create an active petty-cash/direct-procurement allocation or enroll a funded bank first.");return
        win=CashAdvanceGrantDialog(self,employees,banks,allocations); self.wait_window(win)
        if not win.result:return
        data=win.result; employee=self.db.one("SELECT * FROM employees WHERE id=?",(data["employee_id"],))
        try:
            amount=cents(data["amount"]); advance_date=valid_date(data["date"],True)
            is_bank=data["method"]=="Bank Transfer"; bank_id=banks.get(data["bank"]) if is_bank else None
            allocation=allocations.get(data["allocation"]) if not is_bank else None
            allocation_id=allocation["id"] if allocation else None
            if amount<=0 or not data["reason"]: raise ValueError("A positive amount and reason are required.")
            if is_bank:self.db.validate_payment_source(self.project_id,amount,"Bank Transfer",bank_id)
            else:
                self.db.validate_cash_allocation_payment(self.project_id,allocation_id,amount)
                if allocation["allocation_type"]=="Direct Procurement" and not messagebox.askyesno(APP_TITLE,
                    f"Use Direct Procurement {allocation['reference']} for an employee cash advance?\n\n"
                    "This remains fully traceable, but petty cash is normally the clearer source.",parent=self):return
            _dep,_committed,remaining=self.db.project_commitment_budget(self.project_id)
            if amount>remaining: raise ValueError(f"Advance exceeds the project's uncommitted budget of {money(remaining)}.")
            weekly_cap=0
            if data["repayment_plan"]=="Salary Deduction" and data["weekly_cap"]:
                weekly_cap=cents(data["weekly_cap"])
                if weekly_cap<=0:raise ValueError("The weekly deduction limit must be positive or left blank.")
            if is_bank:
                head=self.app.authorize("Grant employee cash advance",f"{employee['name']} - {money(amount)} via Bank Transfer")
            else:
                head=self.app.authorize_registered_head("Release employee cash advance",
                    f"{employee['name']} - {money(amount)} from {allocation['reference']}",
                    allocation["receiver_registry_id"] or None)
            if not head:return
            authorizing_head_id=allocation["receiver_head_id"] if allocation else head["id"]
            reference=self.db._next_system_reference("CA","cash_advances","system_reference",advance_date)
            payment_method="Bank Transfer" if is_bank else "Cash"
            recorded_at=local_timestamp()
            with self.db.conn:
                cur=self.db.conn.execute("""INSERT INTO expenses(project_id,name,item,supplier,qty,unit,unit_price_cents,total_cents,area,trade,expense_date,due_date,invoice_no,notes,authorized_by_head_id,status,default_cash_allocation_id)
                    VALUES(?,?,?,?, '1','advance',?,?,?,?,?,?,?,?,?,'Paid',?)""",(self.project_id,f"CASH ADVANCE - {employee['name']}",f"CASH ADVANCE - {employee['name']}",employee["name"],amount,amount,"PAYROLL","Recoverable Employee Advance",advance_date,advance_date,reference,data["reason"],authorizing_head_id,allocation_id))
                expense_id=cur.lastrowid
                payment_id=self.db.conn.execute("""INSERT INTO payments(expense_id,amount_cents,payment_date,method,reference,notes,bank_account_id,authorized_by_head_id,cash_allocation_id,system_reference,transaction_time) VALUES(?,?,?,?,?,'Employee cash advance',?,?,?,?,?)""",(expense_id,amount,advance_date,payment_method,reference,bank_id,authorizing_head_id,allocation_id,reference,recorded_at)).lastrowid
                advance_id=self.db.conn.execute("""INSERT INTO cash_advances(project_id,employee_id,expense_id,original_cents,advance_date,reason,method,bank_account_id,authorized_by_head_id,cash_allocation_id,repayment_plan,weekly_deduction_cap_cents,system_reference,recorded_at_local) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(self.project_id,employee["id"],expense_id,amount,advance_date,data["reason"],data["method"],bank_id,authorizing_head_id,allocation_id,data["repayment_plan"],weekly_cap,reference,recorded_at)).lastrowid
                self.db.conn.execute("""INSERT INTO cash_advance_transactions(advance_id,txn_type,amount_cents,txn_date,method,bank_account_id,reference,notes,authorized_by_head_id,recorded_at_local) VALUES(?,'Advance',?,?,?,?,?,?,?,?)""",(advance_id,amount,advance_date,data["method"],bank_id,reference,data["reason"],authorizing_head_id,recorded_at))
                if allocation_id:self.db.register_allocation_payment(allocation_id,payment_id,expense_id,amount,advance_date,authorizing_head_id)
                if data["repayment_plan"]=="Salary Deduction":
                    self.db.conn.execute("""INSERT INTO cash_advance_transactions(advance_id,txn_type,amount_cents,txn_date,method,reference,notes,authorized_by_head_id,posted,recorded_at_local) VALUES(?,'Salary Deduction',?,?,'Salary Deduction',?,?,?,0,?)""",(advance_id,amount,advance_date,reference,"Scheduled at grant"+(f"; weekly cap {money(weekly_cap)}" if weekly_cap else "; deduct up to available net pay"),authorizing_head_id,recorded_at))
            self.db.audit(self.project_id,"CASH_ADVANCE_GRANTED",f"{reference}: {money(amount)} to {employee['name']} from {allocation['reference'] if allocation else data['bank']}; repayment {data['repayment_plan']}; authorized by {head['name']}"); self.app.refresh_all()
        except (ValueError,sqlite3.Error) as exc:messagebox.showerror(APP_TITLE,str(exc))

    def grant_cash_advance_batch(self):
        if not self.require_project(): return
        employees = self.db.all(
            "SELECT * FROM employees WHERE project_id=? AND active=1 ORDER BY name",
            (self.project_id,),
        )
        if not employees:
            messagebox.showinfo(APP_TITLE, "Add employees first."); return
        banks = {
            f"{row['bank_name']} - {row['account_name']} (..{row['account_number'][-4:]})": row["id"]
            for row in self.db.all(
                "SELECT * FROM bank_accounts WHERE active=1 ORDER BY bank_name,account_name")
        }
        allocations = {}
        for row in self.db.cash_allocation_rows(None, active_only=True):
            balance = self.db.allocation_balance(row["id"])
            if balance <= 0: continue
            holder = row["holder"] or row["supplier"] or "Unassigned"
            allocations[
                f"{row['reference']} | {row['allocation_type']} | {holder} | {money(balance)} remaining"
            ] = row
        if not allocations and not banks:
            messagebox.showinfo(
                APP_TITLE,
                "Create an active petty-cash/direct-procurement allocation or enroll a funded bank first.")
            return
        win = CashAdvanceBatchDialog(self, employees, banks, allocations)
        self.wait_window(win)
        if not win.result: return
        data = win.result
        try:
            advance_date = valid_date(data["date"], True)
            total = sum(row["amount_cents"] for row in data["entries"])
            is_bank = data["method"] == "Bank Transfer"
            bank_id = banks.get(data["bank"]) if is_bank else None
            allocation = allocations.get(data["allocation"]) if not is_bank else None
            allocation_id = allocation["id"] if allocation else None
            if is_bank:
                self.db.validate_payment_source(self.project_id, total, "Bank Transfer", bank_id)
            else:
                self.db.validate_cash_allocation_payment(self.project_id, allocation_id, total)
                if allocation["allocation_type"] == "Direct Procurement" and not messagebox.askyesno(
                    APP_TITLE,
                    f"Use Direct Procurement {allocation['reference']} for this employee-advance batch?\n\n"
                    "This remains traceable, but petty cash is normally the clearer source.",
                    parent=self,
                ):
                    return
            _deposited, _committed, remaining = self.db.project_commitment_budget(self.project_id)
            if total > remaining:
                raise ValueError(
                    f"Batch exceeds the project's uncommitted budget of {money(remaining)}.")
            source_name = data["bank"] if is_bank else allocation["reference"]
            employee_preview = ", ".join(row["employee"] for row in data["entries"][:5])
            if len(data["entries"]) > 5: employee_preview += f" and {len(data['entries']) - 5} more"
            if is_bank:
                head = self.app.authorize(
                    "Grant batch employee cash advances",
                    f"{len(data['entries'])} employees; {money(total)} via {source_name}; "
                    f"effective {advance_date}. {employee_preview}")
            else:
                head = self.app.authorize_registered_head(
                    "Release batch employee cash advances",
                    f"{len(data['entries'])} employees; {money(total)} from {source_name}; "
                    f"effective {advance_date}. {employee_preview}",
                    allocation["receiver_registry_id"] or None)
            if not head: return
            authorizing_head_id = allocation["receiver_head_id"] if allocation else head["id"]
            recorded_at = local_timestamp()
            batch_ref = self.db._next_system_reference(
                "CAB", "cash_advance_batches", "batch_ref", advance_date)
            payment_method = "Bank Transfer" if is_bank else "Cash"
            with self.db.conn:
                batch_id = self.db.conn.execute(
                    """INSERT INTO cash_advance_batches(
                       project_id,batch_ref,advance_date,funding_method,bank_account_id,
                       cash_allocation_id,total_cents,entry_count,authorized_by_head_id,
                       recorded_at_local,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (self.project_id, batch_ref, advance_date, data["method"], bank_id,
                     allocation_id, total, len(data["entries"]), authorizing_head_id,
                     recorded_at, f"Employees: {employee_preview}"),
                ).lastrowid
                for item in data["entries"]:
                    employee = self.db.one("SELECT * FROM employees WHERE id=?", (item["employee_id"],))
                    reference = self.db._next_system_reference(
                        "CA", "cash_advances", "system_reference", advance_date)
                    expense_id = self.db.conn.execute(
                        """INSERT INTO expenses(project_id,name,item,supplier,qty,unit,
                           unit_price_cents,total_cents,area,trade,expense_date,due_date,
                           invoice_no,notes,authorized_by_head_id,status,default_cash_allocation_id)
                           VALUES(?,?,?,?, '1','advance',?,?,?,?,?,?,?,?,?,'Paid',?)""",
                        (self.project_id, f"CASH ADVANCE - {employee['name']}",
                         f"CASH ADVANCE - {employee['name']}", employee["name"],
                         item["amount_cents"], item["amount_cents"], "PAYROLL",
                         "Recoverable Employee Advance", advance_date, advance_date,
                         reference, f"{item['reason']}; batch {batch_ref}",
                         authorizing_head_id, allocation_id),
                    ).lastrowid
                    payment_id = self.db.conn.execute(
                        """INSERT INTO payments(expense_id,amount_cents,payment_date,method,
                           reference,notes,bank_account_id,authorized_by_head_id,
                           cash_allocation_id,system_reference,transaction_time)
                           VALUES(?,?,?,?,?,'Employee cash advance batch',?,?,?,?,?)""",
                        (expense_id, item["amount_cents"], advance_date, payment_method,
                         reference, bank_id, authorizing_head_id, allocation_id,
                         reference, recorded_at),
                    ).lastrowid
                    advance_id = self.db.conn.execute(
                        """INSERT INTO cash_advances(project_id,employee_id,expense_id,
                           original_cents,advance_date,reason,method,bank_account_id,
                           authorized_by_head_id,cash_allocation_id,repayment_plan,
                           weekly_deduction_cap_cents,batch_id,system_reference,recorded_at_local)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (self.project_id, employee["id"], expense_id, item["amount_cents"],
                         advance_date, item["reason"], data["method"], bank_id,
                         authorizing_head_id, allocation_id, item["repayment_plan"],
                         item["weekly_cap_cents"], batch_id, reference, recorded_at),
                    ).lastrowid
                    self.db.conn.execute(
                        """INSERT INTO cash_advance_transactions(advance_id,txn_type,
                           amount_cents,txn_date,method,bank_account_id,reference,notes,
                           authorized_by_head_id,recorded_at_local)
                           VALUES(?,'Advance',?,?,?,?,?,?,?,?)""",
                        (advance_id, item["amount_cents"], advance_date, data["method"],
                         bank_id, reference, f"{item['reason']}; batch {batch_ref}",
                         authorizing_head_id, recorded_at),
                    )
                    if allocation_id:
                        self.db.register_allocation_payment(
                            allocation_id, payment_id, expense_id, item["amount_cents"],
                            advance_date, authorizing_head_id)
                    if item["repayment_plan"] == "Salary Deduction":
                        cap_note = (f"; weekly cap {money(item['weekly_cap_cents'])}"
                                    if item["weekly_cap_cents"] else
                                    "; deduct up to available net pay")
                        self.db.conn.execute(
                            """INSERT INTO cash_advance_transactions(advance_id,txn_type,
                               amount_cents,txn_date,method,reference,notes,
                               authorized_by_head_id,posted,recorded_at_local)
                               VALUES(?,'Salary Deduction',?,?,'Salary Deduction',?,?,?,0,?)""",
                            (advance_id, item["amount_cents"], advance_date, reference,
                             f"Scheduled in {batch_ref}{cap_note}", authorizing_head_id,
                             recorded_at),
                        )
                self.db.conn.execute(
                    """INSERT INTO audit_log(project_id,action,details,created_at)
                       VALUES(?,'CASH_ADVANCE_BATCH_GRANTED',?,?)""",
                    (self.project_id,
                     f"{batch_ref}: {len(data['entries'])} advances totaling {money(total)} "
                     f"from {source_name}; authorized by {head['name']}", recorded_at),
                )
            messagebox.showinfo(
                APP_TITLE,
                f"Cash-advance batch {batch_ref} committed.\n\n"
                f"Employees: {len(data['entries'])}\nTotal: {money(total)}")
            self.app.refresh_all(); self.lists.select(5)
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)

    def record_recovery(self):
        if not self.require_project():return
        rows=self.db.all("""SELECT a.*,e.name employee,e.employee_no,a.original_cents-COALESCE((SELECT SUM(t.amount_cents) FROM cash_advance_transactions t WHERE t.advance_id=a.id AND t.posted=1 AND t.voided=0 AND t.txn_type<>'Advance'),0) outstanding
            FROM cash_advances a JOIN employees e ON e.id=a.employee_id WHERE a.project_id=? AND a.voided=0 ORDER BY e.name,a.advance_date""",(self.project_id,))
        active=[r for r in rows if r["outstanding"]>0]
        if not active:messagebox.showinfo(APP_TITLE,"There are no outstanding employee advances.");return
        advances={f"{r['employee']} - {r['advance_date']} - balance {money(r['outstanding'])} [#{r['id']}]":r for r in active}
        banks={f"{b['bank_name']} - {b['account_name']} (..{b['account_number'][-4:]})":b["id"] for b in self.db.all("SELECT * FROM bank_accounts WHERE active=1 ORDER BY bank_name,account_name")}
        win=CashAdvanceRecoveryDialog(self,advances,banks); self.wait_window(win)
        data=win.result
        if not data:return
        try:
            advance=advances.get(data["advance"]); amount=cents(data["amount"]); txn_date=valid_date(data["txn_date"],True)
            if not advance or amount<=0 or amount>advance["outstanding"]:raise ValueError("Recovery must be positive and cannot exceed the outstanding advance.")
            bank_id=banks.get(data["bank"]) if "bank" in data["method"].lower() else None
            if "bank" in data["method"].lower() and not bank_id:raise ValueError("Select the bank receiving the repayment.")
            posted=1
            if data["method"]=="Salary Deduction":
                pending=self.db.one("""SELECT COALESCE(SUM(t.amount_cents),0) total FROM cash_advance_transactions t JOIN cash_advances a ON a.id=t.advance_id WHERE a.employee_id=? AND t.txn_type='Salary Deduction' AND t.posted=0 AND t.voided=0""",(advance["employee_id"],))["total"]
                if amount>advance["outstanding"]-pending:raise ValueError(f"Salary deduction exceeds the unscheduled advance balance of {money(max(0,advance['outstanding']-pending))}.")
                posted=0
            head=self.app.authorize("Record cash-advance recovery",f"{advance['employee']} - {money(amount)} via {data['method']}")
            if not head:return
            with self.db.conn:
                surrender_reference = (self.db._next_system_reference(
                    "SR", "cash_repayment_surrenders", "reference", txn_date
                ) if data["method"]=="Cash Repayment" else "")
                transaction_reference = surrender_reference or data["reference"]
                transaction_id=self.db.conn.execute("""INSERT INTO cash_advance_transactions(advance_id,txn_type,amount_cents,txn_date,method,bank_account_id,reference,notes,authorized_by_head_id,posted) VALUES(?,?,?,?,?,?,?,?,?,?)""",(advance["id"],data["method"],amount,txn_date,data["method"],bank_id,transaction_reference,data["notes"],head["id"],posted)).lastrowid
                if data["method"]=="Cash Repayment":
                    self.db.conn.execute("""INSERT INTO cash_repayment_surrenders(
                        reference,advance_transaction_id,advance_id,cash_allocation_id,
                        amount_cents,surrender_date,transaction_time,received_by_head_id,
                        status,notes) VALUES(?,?,?,?,?,?,?,?, 'Awaiting Deposit',?)""",
                        (surrender_reference,transaction_id,advance["id"],advance["cash_allocation_id"],
                         amount,txn_date,local_timestamp(),head["id"],
                         (f"Employee cash repayment from {advance['employee']}. "
                          f"User reference: {data['reference'] or 'none'}. {data['notes']}").strip()))
                if posted:self.db.reduce_pending_salary_schedule(advance["id"],amount)
            self.db.audit(self.project_id,"CASH_ADVANCE_RECOVERY",f"Advance #{advance['id']}: {money(amount)} via {data['method']} authorized by {head['name']}"+(f"; surrendered as {surrender_reference}" if surrender_reference else ""))
            if surrender_reference:
                messagebox.showinfo(APP_TITLE,
                    f"Cash repayment recorded as surrendered cash {surrender_reference}.\n\n"
                    "It is excluded from spendable cash until deposited to a bank.")
            self.app.refresh_all()
        except (ValueError,sqlite3.Error) as exc:messagebox.showerror(APP_TITLE,str(exc))

    def legacy_commit(self):
        if not self.require_project():return
        rows=self.db.all("""SELECT a.*,e.name,e.id employee_id FROM attendance a JOIN employees e ON e.id=a.employee_id WHERE e.project_id=? AND a.clock_out<>'' AND a.committed_expense_id IS NULL ORDER BY a.clock_in""",(self.project_id,))
        if not rows:messagebox.showinfo(APP_TITLE,"There is no uncommitted closed attendance.");return
        employee_ids=sorted({r["employee_id"] for r in rows}); placeholders=",".join("?" for _ in employee_ids)
        deductions=self.db.all(f"""SELECT t.*,a.employee_id FROM cash_advance_transactions t JOIN cash_advances a ON a.id=t.advance_id WHERE a.employee_id IN ({placeholders}) AND t.txn_type='Salary Deduction' AND t.posted=0 AND t.voided=0 AND a.voided=0""",tuple(employee_ids))
        gross=sum(r["gross_cents"] for r in rows); deduction_total=sum(r["amount_cents"] for r in deductions); net=gross-deduction_total
        if net<0:messagebox.showerror(APP_TITLE,"Pending salary deductions exceed this payroll batch.");return
        _dep,_committed,remaining=self.db.project_commitment_budget(self.project_id)
        if gross-deduction_total>remaining:messagebox.showerror(APP_TITLE,f"Payroll exceeds the project's remaining commitment budget of {money(remaining)}.");return
        period_start=min(r["clock_in"][:10] for r in rows); period_end=max(r["clock_out"][:10] for r in rows)
        head=self.app.authorize("Commit payroll to expenses",f"{len(rows)} attendance record(s), gross {money(gross)}, deductions {money(deduction_total)}, net payable {money(net)}")
        if not head:return
        batch_ref=datetime.now().strftime("PAY-%Y%m%d-%H%M%S")
        with self.db.conn:
            expense_id=self.db.conn.execute("""INSERT INTO expenses(project_id,name,item,supplier,qty,unit,unit_price_cents,total_cents,area,trade,expense_date,due_date,payroll_batch,notes,authorized_by_head_id,status) VALUES(?,?,?,?, '1','batch',?,?,?,?,?,?,?,?,?,?)""",(self.project_id,f"Payroll {period_start} to {period_end}","Committed attendance payroll","Payroll",net,net,"PAYROLL","Labor",date.today().isoformat(),date.today().isoformat(),batch_ref,f"{len(rows)} attendance record(s); salary deductions {money(deduction_total)}",head["id"],"Paid" if net<=0 else "Unpaid")).lastrowid
            batch_id=self.db.conn.execute("""INSERT INTO payroll_batches(project_id,batch_ref,period_start,period_end,gross_cents,deduction_cents,net_cents,expense_id,authorized_by_head_id) VALUES(?,?,?,?,?,?,?,?,?)""",(self.project_id,batch_ref,period_start,period_end,gross,deduction_total,net,expense_id,head["id"])).lastrowid
            self.db.conn.executemany("UPDATE attendance SET committed_expense_id=?,payroll_batch_id=? WHERE id=?",[(expense_id,batch_id,r["id"]) for r in rows])
            if deductions:
                self.db.conn.executemany("UPDATE cash_advance_transactions SET posted=1,payroll_batch_id=? WHERE id=?",[(batch_id,r["id"]) for r in deductions])
        self.db.audit(self.project_id,"PAYROLL_COMMITTED",f"{batch_ref}: gross {money(gross)}, deductions {money(deduction_total)}, net {money(net)} authorized by {head['name']}")
        messagebox.showinfo(APP_TITLE,f"Payroll committed.\nGross: {money(gross)}\nAdvance deductions: {money(deduction_total)}\nNet payable: {money(net)}");self.app.refresh_all()

    def refresh(self):
        for tree in (self.employees,self.archived_employees,self.attendance,self.weekly,self.batches,self.advances,self.advance_transactions):tree.delete(*tree.get_children())
        employee_project_filter=" AND e.project_id=?" if self.project_id else ""
        attendance_project_filter=" AND COALESCE(a.project_id,e.project_id)=?" if self.project_id else ""
        batch_project_filter=" AND b.project_id=?" if self.project_id else ""
        advance_project_filter=" AND a.project_id=?" if self.project_id else ""
        employee_params=(self.project_id,) if self.project_id else ()
        employees=self.db.all(f"""SELECT e.*,p.name project_name,CASE WHEN EXISTS(SELECT 1 FROM attendance a WHERE a.employee_id=e.id AND a.clock_out='') THEN 'Clocked in' ELSE 'Clocked out' END state FROM employees e JOIN projects p ON p.id=e.project_id WHERE e.active=1{employee_project_filter} ORDER BY p.name,e.name""",employee_params)
        for e in employees:
            daily=employee_daily_rate(e); outstanding=self.db.one("""SELECT COALESCE(SUM(a.original_cents),0)-COALESCE(SUM((SELECT SUM(t.amount_cents) FROM cash_advance_transactions t WHERE t.advance_id=a.id AND t.posted=1 AND t.voided=0 AND t.txn_type<>'Advance')),0) total FROM cash_advances a WHERE a.employee_id=? AND a.voided=0""",(e["id"],))["total"]
            self.employees.insert("","end",iid=e["id"],values=(e["employee_no"],e["name"],e["project_name"],e["position"],e["class"],money(daily),money(int((Decimal(daily)/8).quantize(Decimal('1'),rounding=ROUND_HALF_UP))),money(max(0,outstanding)),e["state"]))
        archived=self.db.all("""SELECT e.*,p.name project_name FROM employees e
            JOIN projects p ON p.id=e.project_id WHERE e.active=0 ORDER BY e.name COLLATE NOCASE""")
        for e in archived:self.archived_employees.insert("","end",iid=e["id"],values=(e["employee_no"],
            e["name"],e["project_name"],e["position"],money(employee_daily_rate(e)),
            e["archived_at"] or "Legacy archive",e["archive_reason"] or "Not recorded"))
        attendance=self.db.all(f"""SELECT a.*,e.name,
            COALESCE(cb.closure_ref,'') closure_ref,COALESCE(pb.batch_ref,'') weekly_ref
            FROM attendance a JOIN employees e ON e.id=a.employee_id
            LEFT JOIN attendance_closure_batches cb ON cb.id=a.closure_batch_id
            LEFT JOIN payroll_batches pb ON pb.id=a.payroll_batch_id
            WHERE 1=1{attendance_project_filter} ORDER BY a.clock_in DESC""",employee_params)
        for r in attendance:
            workflow=(f"Weekly: {r['weekly_ref']}" if r["payroll_batch_id"] else
                      "Weekly accumulating" if r["closure_batch_id"] else
                      "Awaiting daily close" if r["clock_out"] else "Clocked in")
            self.attendance.insert("","end",iid=r["id"],values=(r["name"],r["clock_in"][:10],
                r["clock_in"].replace("T"," "),r["clock_out"].replace("T"," "),r["lunch_hours"],
                r["regular_hours"],r["overtime_hours"],money(r["gross_cents"]),r["source"],
                r["closure_ref"] or "—",workflow,r["revision_count"]))
        batches=self.db.all(f"""SELECT b.*,COUNT(a.id) attendance_count,COALESCE(h.name,'Legacy / not recorded') head FROM payroll_batches b LEFT JOIN attendance a ON a.payroll_batch_id=b.id LEFT JOIN project_heads h ON h.id=b.authorized_by_head_id WHERE 1=1{batch_project_filter} GROUP BY b.id ORDER BY b.created_at DESC,b.id DESC""",employee_params)
        for b in batches:self.batches.insert("","end",iid=b["id"],values=(b["batch_ref"],b["period_start"],b["period_end"],b["attendance_count"],money(b["gross_cents"]),money(b["deduction_cents"]),money(b["adjustment_cents"]),money(b["net_cents"]),b["head"],b["created_at"]))
        advances=self.db.all(f"""SELECT a.*,e.name employee,COALESCE(b.batch_ref,'Individual') batch_ref,
            COALESCE((SELECT SUM(t.amount_cents) FROM cash_advance_transactions t WHERE t.advance_id=a.id AND t.posted=1 AND t.voided=0 AND t.txn_type<>'Advance'),0) recovered
            FROM cash_advances a JOIN employees e ON e.id=a.employee_id
            LEFT JOIN cash_advance_batches b ON b.id=a.batch_id
            WHERE a.voided=0{advance_project_filter} ORDER BY a.advance_date DESC,a.id DESC""",employee_params)
        advanced=recovered_total=0
        for a in advances:
            net=max(0,a["original_cents"]-a["recovered"]); status="Settled" if net==0 else "Partially Recovered" if a["recovered"] else "Outstanding"; advanced+=a["original_cents"];recovered_total+=a["recovered"]
            self.advances.insert("","end",iid=a["id"],values=(a["advance_date"],a["batch_ref"],
                a["system_reference"] or f"CA-LEGACY-{a['id']:06d}",a["employee"],
                money(a["original_cents"]),money(a["recovered"]),money(net),a["method"],
                a["repayment_plan"],status,a["reason"]))
        txns=self.db.all(f"""SELECT t.*,a.original_cents,e.name employee,COALESCE(h.name,'Legacy / not recorded') head FROM cash_advance_transactions t JOIN cash_advances a ON a.id=t.advance_id JOIN employees e ON e.id=a.employee_id LEFT JOIN project_heads h ON h.id=t.authorized_by_head_id WHERE a.voided=0 AND t.voided=0{advance_project_filter} ORDER BY t.txn_date,t.id""",employee_params);balances={}
        for t in txns:
            balances.setdefault(t["advance_id"],0);balances[t["advance_id"]]+=t["amount_cents"] if t["txn_type"]=="Advance" else (-t["amount_cents"] if t["posted"] else 0)
            self.advance_transactions.insert("","end",iid=t["id"],values=(t["txn_date"],t["employee"],t["txn_type"]+(" (Pending)" if not t["posted"] else ""),money(t["amount_cents"]),t["method"],t["reference"],t["head"],money(max(0,balances[t["advance_id"]]))))
        uncommitted=[r for r in attendance if r["clock_out"] and r["closure_batch_id"] and not r["payroll_batch_id"]]; running=sum(r["gross_cents"] for r in uncommitted); open_count=sum(1 for r in attendance if not r["clock_out"])
        self.running_value.config(text=money(running))
        if uncommitted:
            period_start=min(r["clock_in"][:10] for r in uncommitted);period_end=max(r["clock_in"][:10] for r in uncommitted)
            self.period_value.config(text=period_start if period_start==period_end else f"{period_start} to {period_end}")
        else:self.period_value.config(text="No weekly payroll accumulating")
        self.open_value.config(text=str(open_count))
        if batches:self.last_value.config(text=money(batches[0]["net_cents"]));self.last_date_value.config(text=batches[0]["created_at"][:10])
        else:self.last_value.config(text="0.00");self.last_date_value.config(text="None")
        self.advance_summary.config(text=f"Advanced {money(advanced)}  |  Recovered {money(recovered_total)}  |  Outstanding {money(max(0,advanced-recovered_total))}")
        self.refresh_weekly()


class LegacyRemittancesTab(BaseTab):
    FIELDS = [
        ("type", "Type", ["Deposit", "Withdrawal"]), ("amount", "Amount"),
        ("txn_date", "Date (YYYY-MM-DD)"), ("purpose", "Purpose"),
        ("care_of", "C/O (team head)"), ("signature", "Signature / acknowledgement"),
        ("notes", "Notes"),
    ]

    def __init__(self, app):
        super().__init__(app)
        header = ttk.Frame(self); header.pack(fill="x")
        ttk.Label(header, text="Client remittances and withdrawals", style="Title.TLabel").pack(side="left")
        self.summary = ttk.Label(header); self.summary.pack(side="right")
        self.progress = ttk.Progressbar(self, maximum=100); self.progress.pack(fill="x", pady=(8, 10))
        bar = ttk.Frame(self); bar.pack(fill="x")
        ttk.Button(bar, text="＋ Add Transaction", command=self.add).pack(side="left")
        ttk.Button(bar, text="Edit", command=self.edit).pack(side="left", padx=5)
        ttk.Button(bar, text="Void / Restore", command=self.void).pack(side="left")
        self.tree = make_tree(self, [
            ("date", "Date", 95), ("type", "Type", 100), ("amount", "Amount", 110),
            ("purpose", "Purpose", 210), ("care", "C/O", 150),
            ("authorized", "Authorized by", 140), ("status", "Status", 70),
        ])

    def add(self):
        if not self.require_project():
            return
        data = dialog(self, "Remittance Transaction", self.FIELDS,
                      {"txn_date": date.today().isoformat()},
                      required_keys=("type", "amount", "txn_date", "purpose"))
        if data:
            try:
                amount = cents(data["amount"])
                if amount <= 0:
                    raise ValueError("Amount must be greater than zero.")
                head = self.app.authorize(
                    f"Record {data['type'].lower()}",
                    f"{money(amount)} — {data['purpose'] or 'No purpose supplied'}"
                )
                if not head: return
                self.db.execute(
                    """INSERT INTO remittances(project_id,type,amount_cents,txn_date,purpose,
                       care_of,signature,notes,authorized_by_head_id) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (self.project_id, data["type"], amount, valid_date(data["txn_date"], True),
                     data["purpose"], data["care_of"], data["signature"], data["notes"], head["id"]),
                )
                self.db.audit(self.project_id, "REMITTANCE_ADDED",
                              f"{data['type']} {money(amount)} authorized by {head['name']}")
                self.app.refresh_all()
            except ValueError as exc:
                messagebox.showerror(APP_TITLE, str(exc))

    def edit(self):
        record_id = self.selected_id(self.tree)
        if not record_id:
            return
        row = self.db.one("SELECT * FROM remittances WHERE id=?", (record_id,))
        initial = dict(row)
        initial["amount"] = money(row["amount_cents"])
        data = dialog(
            self, "Edit Remittance Transaction", self.FIELDS, initial,
            required_keys=("type", "amount", "txn_date", "purpose"),
        )
        if data:
            try:
                amount = cents(data["amount"])
                if amount <= 0:
                    raise ValueError("Amount must be greater than zero.")
                self.db.execute(
                    """UPDATE remittances SET type=?,amount_cents=?,txn_date=?,purpose=?,
                       care_of=?,signature=?,notes=? WHERE id=?""",
                    (data["type"], amount, valid_date(data["txn_date"], True), data["purpose"],
                     data["care_of"], data["signature"], data["notes"], record_id),
                )
                self.db.audit(self.project_id, "REMITTANCE_EDITED", f"#{record_id} {money(amount)}")
                self.app.refresh_all()
            except ValueError as exc:
                messagebox.showerror(APP_TITLE, str(exc))

    def void(self):
        record_id = self.selected_id(self.tree)
        if record_id and messagebox.askyesno(
            APP_TITLE, "Void or restore the selected transaction?\n\nThe audit history will be retained."
        ):
            self.db.execute(
                "UPDATE remittances SET voided=CASE voided WHEN 1 THEN 0 ELSE 1 END WHERE id=?",
                (record_id,),
            )
            self.db.audit(self.project_id, "REMITTANCE_VOID_TOGGLED", str(record_id))
            self.app.refresh_all()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        if not self.project_id:
            self.progress["value"] = 0
            return
        rows = self.db.all(
            """SELECT r.*,COALESCE(h.name,'') authorized_by FROM remittances r
               LEFT JOIN project_heads h ON h.id=r.authorized_by_head_id
               WHERE r.project_id=? ORDER BY r.txn_date DESC,r.id DESC""", (self.project_id,))
        deposits = withdrawals = 0
        for row in rows:
            if not row["voided"]:
                if row["type"] == "Deposit":
                    deposits += row["amount_cents"]
                else:
                    withdrawals += row["amount_cents"]
            self.tree.insert("", "end", iid=row["id"], values=(
                row["txn_date"], row["type"], money(row["amount_cents"]), row["purpose"],
                row["care_of"], row["authorized_by"] or "Legacy / not recorded",
                "VOID" if row["voided"] else "Active",
            ))
        contract = self.db.one("SELECT contract_value_cents FROM projects WHERE id=?",
                               (self.project_id,))["contract_value_cents"]
        percent = min(100, round(deposits * 100 / contract)) if contract else 0
        self.progress["value"] = percent
        self.summary.config(
            text=f"Deposited {money(deposits)}  |  Withdrawn {money(withdrawals)}  |  Balance {money(deposits-withdrawals)}  |  {percent}% funded"
        )


class BankAccountDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Enroll Bank Account"); self.resizable(False, False); self.result = None
        self.vars = {key: tk.StringVar() for key in ("bank_name", "account_name", "account_number", "notes")}
        self.widgets = {}
        body = ttk.Frame(self, padding=20); body.pack(fill="both", expand=True)
        ttk.Label(body, text="Enroll a shared bank account", style="DialogTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        specs = [("bank_name", "Bank name"), ("account_name", "Account name"),
                 ("account_number", "Account number / reference"), ("notes", "Notes")]
        for row, (key, label) in enumerate(specs, 1):
            required = key in {"bank_name", "account_number"}
            ttk.Label(body, text=label + (" *" if required else "")).grid(
                row=row, column=0, sticky="w", padx=(0, 12), pady=5)
            widget = ttk.Entry(body, textvariable=self.vars[key], width=40)
            widget.grid(row=row, column=1, pady=5); self.widgets[key] = widget
        footer = ttk.Frame(body); footer.grid(row=5, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(footer, text="Cancel", style="Secondary.TButton", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="Enroll Account", style="Primary.TButton", command=self.save).pack(side="right")
        self.transient(parent); self.grab_set()

    def save(self):
        values = {key: var.get().strip() for key, var in self.vars.items()}
        if flash_missing_fields(self, self.vars, self.widgets, ("bank_name", "account_number")):
            return
        self.result = values; self.destroy()


class RemittancesTab(BaseTab):
    """Shared bank accounts with project-attributed deposits and withdrawals."""
    def __init__(self, app):
        super().__init__(app)
        header = ttk.Frame(self); header.pack(fill="x")
        ttk.Label(header, text="Remittances, banks and project budgets", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="+ Enroll Bank", style="Primary.TButton", command=self.enroll_bank).pack(side="right")
        ttk.Button(header, text="+ Add Transaction", style="Primary.TButton", command=self.add).pack(side="right", padx=6)
        ttk.Button(header, text="Transfer Between Banks", command=self.transfer_between_banks).pack(
            side="right", padx=(0, 2))
        cards = ttk.Frame(self); cards.pack(fill="x", pady=(12, 8))
        self.deposit_card, self.deposit_value = metric_card(cards, "Deposited", GREEN)
        self.withdraw_card, self.withdraw_value = metric_card(cards, "Net withdrawn", ORANGE)
        self.transfer_card, self.transfer_value = metric_card(cards, "Bank transfers", RED)
        self.bank_card, self.bank_value = metric_card(cards, "Bank balance", NAVY_ACTIVE)
        self.contract_card, self.contract_value = metric_card(cards, "Total project contract value", INK)
        self.budget_card, self.budget_value = metric_card(cards, "Project budget remaining", INK)
        layout_metric_cards(cards, (
            self.contract_card, self.deposit_card, self.withdraw_card,
            self.transfer_card, self.bank_card, self.budget_card,
        ))
        self.budget_note = ttk.Label(self, style="Muted.TLabel")
        self.budget_note.pack(anchor="w", fill="x", pady=(0, 7))
        filters = ttk.Frame(self); filters.pack(fill="x")
        self.project_filter = tk.StringVar(value="All Projects"); self.bank_filter = tk.StringVar(value="All Banks")
        filters.columnconfigure(1, weight=1); filters.columnconfigure(3, weight=1)
        ttk.Label(filters, text="Project").grid(row=0, column=0, sticky="w")
        self.project_combo = ttk.Combobox(filters, textvariable=self.project_filter, state="readonly", width=27)
        self.project_combo.grid(row=0, column=1, sticky="ew", padx=(4, 12)); self.project_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        ttk.Label(filters, text="Bank account").grid(row=0, column=2, sticky="w")
        self.bank_combo = ttk.Combobox(filters, textvariable=self.bank_filter, state="readonly", width=34)
        self.bank_combo.grid(row=0, column=3, sticky="ew", padx=(4, 0)); self.bank_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        self.transaction_type_filter = tk.StringVar(value="All Transaction Types")
        self.transaction_status_filter = tk.StringVar(value="All Statuses")
        self.remit_date_from = tk.StringVar(); self.remit_date_to = tk.StringVar()
        self.reference_filter = tk.StringVar(); self.remit_search = tk.StringVar()
        extra = ttk.Frame(self); extra.pack(fill="x", pady=(5, 0))
        for label, variable, values, width in (
            ("Type", self.transaction_type_filter,
             ["All Transaction Types", "Deposit", "Withdrawal", "Inter-bank Transfer",
              "Bank Transfer", "Cash Redeposit", "Repayment"], 20),
            ("Status", self.transaction_status_filter, ["All Statuses", "Active", "VOID"], 12),
        ):
            ttk.Label(extra, text=label).pack(side="left", padx=(0, 4))
            combo = ttk.Combobox(extra, textvariable=variable, values=values, state="readonly", width=width)
            combo.pack(side="left", padx=(0, 8)); combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        for label, variable in (("From", self.remit_date_from), ("To", self.remit_date_to)):
            ttk.Label(extra, text=label).pack(side="left", padx=(2, 4))
            ttk.Entry(extra, textvariable=variable, width=10, state="readonly").pack(side="left")
            ttk.Button(extra, text="\U0001F4C5", width=3,
                       command=lambda current=variable: self.open_remittance_date(current)).pack(side="left", padx=(3, 7))
        ttk.Label(extra, text="Reference / Search").pack(side="left", padx=(2, 4))
        search = ttk.Entry(extra, textvariable=self.remit_search, width=22)
        search.pack(side="left", fill="x", expand=True)
        search.bind("<KeyRelease>", lambda _e: self.refresh())
        ttk.Button(extra, text="All Dates", command=self.clear_remittance_dates).pack(side="left", padx=(6, 0))

        self.ledger_split = ttk.Panedwindow(self, orient="vertical")
        self.ledger_split.pack(fill="both", expand=True, pady=(10, 0))
        bank_pane = ttk.Frame(self.ledger_split)
        transaction_pane = ttk.Frame(self.ledger_split)
        self.ledger_split.add(bank_pane, weight=1)
        self.ledger_split.add(transaction_pane, weight=4)

        bank_heading = ttk.Frame(bank_pane); bank_heading.pack(fill="x")
        ttk.Label(bank_heading, text="Enrolled bank balances", style="Section.TLabel").pack(side="left")
        ttk.Label(bank_heading, text="Drag the divider to resize", style="Muted.TLabel").pack(side="right")
        self.account_tree = make_tree(bank_pane, [("bank", "Bank", 150), ("account", "Account", 180),
            ("deposits", "Deposited", 100), ("withdrawals", "Gross Withdrawn", 105),
            ("redeposits", "Cash Redeposited", 105), ("net_withdrawals", "Net Withdrawn", 100),
            ("interbank_in", "Inter-bank In", 100), ("interbank_out", "Inter-bank Out", 105),
            ("transfers", "Expense Transfers", 110), ("recoveries", "Repayments", 100),
            ("balance", "Balance", 110)])
        self.account_tree.configure(height=4)

        transaction_heading = ttk.Frame(transaction_pane); transaction_heading.pack(fill="x")
        ttk.Label(transaction_heading, text="Incoming and outgoing transaction ledger", style="Section.TLabel").pack(side="left")
        ttk.Button(transaction_heading, text="Edit Transaction", command=self.edit).pack(side="right")
        ttk.Button(transaction_heading, text="Void / Restore", command=self.void).pack(side="right", padx=6)
        self.tree = make_tree(transaction_pane, [("time", "Date & Time", 145), ("reference", "System Reference", 145),
            ("project", "Project", 135), ("bank", "Bank account", 165),
            ("type", "Type", 100), ("amount", "Amount", 100),
            ("purpose", "Purpose", 180), ("care", "C/O", 120), ("authorized", "Authorized by", 120),
            ("status", "Status", 65)])
        self.tree.configure(height=12)

    def open_remittance_date(self, variable):
        popup = DatePickerPopup(self, variable)
        self.wait_window(popup)
        if self.remit_date_from.get() and self.remit_date_to.get() and self.remit_date_from.get() > self.remit_date_to.get():
            self.remit_date_to.set(self.remit_date_from.get())
        self.refresh()

    def clear_remittance_dates(self):
        self.remit_date_from.set(""); self.remit_date_to.set(""); self.refresh()

    def project_options(self):
        return {f"{row['name']} [#{row['id']}]": row["id"] for row in self.db.all(
            "SELECT id,name FROM projects ORDER BY name")}

    def bank_options(self):
        return {f"{row['bank_name']} — {row['account_name'] or row['account_number']} (••{row['account_number'][-4:]})": row["id"]
                for row in self.db.all("SELECT * FROM bank_accounts WHERE active=1 ORDER BY bank_name,account_name")}

    def enroll_bank(self):
        win = BankAccountDialog(self); self.wait_window(win)
        if not win.result: return
        try:
            self.db.enroll_bank_account(win.result)
            self.db.audit(None, "BANK_ACCOUNT_ENROLLED", f"{win.result['bank_name']} ••{win.result['account_number'][-4:]}")
            self.app.refresh_all()
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
        except sqlite3.IntegrityError as exc:
            messagebox.showerror(APP_TITLE, f"The bank account could not be enrolled:\n{exc}")

    def bank_transfer_form(self, initial=None):
        banks = self.bank_options()
        fields = [
            ("from_bank", "Source bank account", list(banks)),
            ("to_bank", "Destination bank account", list(banks)),
            ("amount", "Amount"), ("transfer_date", "Transfer date (YYYY-MM-DD)"),
            ("purpose", "Purpose"), ("notes", "Notes"),
        ]
        labels = list(banks)
        values = {
            "from_bank": labels[0] if labels else "",
            "to_bank": labels[1] if len(labels) > 1 else "",
            "transfer_date": date.today().isoformat(),
        }
        values.update(initial or {})
        win = FormDialog(
            self, "Transfer Funds Between Bank Accounts", fields, values,
            required_keys=("from_bank", "to_bank", "amount", "transfer_date", "purpose"),
        )
        self.wait_window(win)
        return win.result, banks

    def transfer_between_banks(self):
        banks = self.bank_options()
        if len(banks) < 2:
            messagebox.showinfo(
                APP_TITLE, "Enroll at least two active bank accounts before transferring funds.",
                parent=self,
            )
            return
        data, banks = self.bank_transfer_form()
        if not data:
            return
        try:
            source_id = banks.get(data["from_bank"])
            destination_id = banks.get(data["to_bank"])
            amount = cents(data["amount"])
            transfer_date = valid_date(data["transfer_date"], True)
            if not source_id or not destination_id:
                raise ValueError("Select both a source and destination bank account.")
            if source_id == destination_id:
                raise ValueError("Source and destination bank accounts must be different.")
            if amount <= 0:
                raise ValueError("Transfer amount must be greater than zero.")
            available = self.db.bank_balance(source_id)
            if amount > available:
                raise ValueError(
                    f"The source account only has {money(available)} available."
                )
            # The form is completed and validated before asking for the approving PIN.
            head = self.app.authorize_registered_head(
                "Transfer funds between bank accounts",
                f"{money(amount)} from {data['from_bank']} to {data['to_bank']}",
            )
            if not head:
                return
            result = self.db.create_bank_account_transfer(
                from_bank_account_id=source_id,
                to_bank_account_id=destination_id,
                amount_cents=amount,
                transfer_date=transfer_date,
                purpose=data["purpose"], notes=data["notes"],
                authorized_by_registry_id=head["id"],
            )
            self.app.refresh_all()
            messagebox.showinfo(
                APP_TITLE,
                f"Bank transfer recorded successfully.\nReference: {result['reference']}",
                parent=self,
            )
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)

    def transaction_form(self, initial=None):
        projects = {label: project_id for label, project_id in self.project_options().items()
                    if self.db.project_is_active(project_id)}
        banks = self.bank_options()
        fields = [("project", "Project", list(projects)), ("type", "Type", ["Deposit", "Withdrawal"]),
            ("bank", "Bank account", list(banks)), ("amount", "Amount"), ("txn_date", "Date"),
            ("purpose", "Purpose"), ("care_of", "C/O (team head)"),
            ("signature", "Signature / acknowledgement"), ("notes", "Notes")]
        values = {"txn_date": date.today().isoformat(), "type": "Deposit"}; values.update(initial or {})
        win = FormDialog(
            self, "Bank Remittance Transaction", fields, values,
            required_keys=("project", "type", "bank", "amount", "txn_date", "purpose"),
        )
        last_project = {"value": values.get("project") or next(iter(projects), "")}

        def update_project_state(_event=None):
            if win.vars["type"].get() == "Withdrawal":
                current = win.vars["project"].get()
                if current and current != SHARED_CASH_LABEL:
                    last_project["value"] = current
                win.vars["project"].set(SHARED_CASH_LABEL)
                win.widgets["project"].configure(state="disabled")
            else:
                win.widgets["project"].configure(state="readonly", values=list(projects))
                if win.vars["project"].get() not in projects:
                    win.vars["project"].set(last_project["value"] or next(iter(projects), ""))

        win.widgets["type"].bind("<<ComboboxSelected>>", update_project_state, add="+")
        update_project_state()
        self.wait_window(win)
        return win.result, projects, banks

    def add(self):
        if not self.bank_options():
            if messagebox.askyesno(APP_TITLE, "Enroll a bank account before recording remittances. Enroll one now?"):
                self.enroll_bank()
            if not self.bank_options(): return
        initial_project = next((label for label,pid in self.project_options().items() if pid == self.project_id), "")
        data, projects, banks = self.transaction_form({"project": initial_project})
        if not data: return
        is_withdrawal = data["type"] == "Withdrawal"
        project_id = projects.get(data["project"])
        if is_withdrawal:
            project_id = self.project_id or next(iter(projects.values()), None)
        bank_id = banks.get(data["bank"])
        try:
            amount = cents(data["amount"])
            if not project_id:
                raise ValueError("Create at least one project before recording bank activity.")
            if not bank_id or amount <= 0:
                raise ValueError("A bank account and positive amount are required.")
            if not is_withdrawal and data["project"] not in projects:
                raise ValueError("Select the project receiving this deposit.")
            if is_withdrawal and amount > self.db.bank_balance(bank_id):
                raise ValueError("Withdrawal exceeds the selected bank account's available balance.")
            if is_withdrawal:
                head = self.app.authorize_registered_head(
                    "Record shared cash withdrawal",
                    f"{money(amount)} using {data['bank']} for the shared cash pool",
                )
            else:
                head = self.app.authorize_for_project(
                    project_id, "Record deposit",
                    f"{money(amount)} using {data['bank']} for {data['project']}",
                )
            if not head: return
            txn_date = valid_date(data["txn_date"], True)
            reference = self.db._next_system_reference(
                "WD" if is_withdrawal else "BD", "remittances", "system_reference", txn_date
            )
            cursor = self.db.execute("""INSERT INTO remittances(project_id,type,amount_cents,txn_date,purpose,care_of,
                signature,notes,authorized_by_head_id,authorized_by_registry_id,bank_account_id,shared_cash,
                system_reference,transaction_time)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (project_id, data["type"], amount, txn_date, data["purpose"],
                 data["care_of"], data["signature"], data["notes"],
                 None if is_withdrawal else head["id"], head["id"] if is_withdrawal else None,
                 bank_id, 1 if is_withdrawal else 0, reference, local_timestamp()))
            self.db.audit(None if is_withdrawal else project_id, "REMITTANCE_ADDED",
                f"{reference} {data['type']} {money(amount)} from {data['bank']} authorized by {head['name']}")
            self.app.refresh_all()
            if is_withdrawal and messagebox.askyesno(
                APP_TITLE,
                "Withdrawal recorded in the shared cash pool.\n\nAllocate some or all of it to Petty Cash or Direct Procurement now?",
                parent=self,
            ):
                expenses = self.app.pages["Expenses"]
                self.app.show_page("Expenses")
                expenses.expense_notebook.select(expenses.cash_page)
                expenses.issue_cash_allocation(cursor.lastrowid)
        except (ValueError, sqlite3.Error) as exc: messagebox.showerror(APP_TITLE, str(exc))

    def edit(self):
        selected = self.tree.selection()
        if selected and str(selected[0]).startswith("interbank-"):
            messagebox.showinfo(
                APP_TITLE,
                "Inter-bank transfers keep an immutable audit reference. Void the transfer and record a corrected one instead.",
                parent=self,
            )
            return
        record_id = self.selected_remittance_id()
        if not record_id: return
        row = self.db.one("SELECT * FROM remittances WHERE id=?", (record_id,))
        projects, banks = self.project_options(), self.bank_options()
        initial = dict(row); initial["amount"] = money(row["amount_cents"])
        initial["project"] = next((label for label,pid in projects.items() if pid == row["project_id"]), "")
        initial["bank"] = next((label for label,bid in banks.items() if bid == row["bank_account_id"]), "")
        data, projects, banks = self.transaction_form(initial)
        if not data: return
        is_withdrawal = data["type"] == "Withdrawal"
        project_id = row["project_id"] if is_withdrawal else projects.get(data["project"])
        project_id = project_id or self.project_id or next(iter(projects.values()), None)
        bank_id = banks.get(data["bank"])
        try:
            amount = cents(data["amount"])
            if not project_id or not bank_id or amount <= 0:
                raise ValueError("A project record, bank account and positive amount are required.")
            if not is_withdrawal and data["project"] not in projects:
                raise ValueError("Select the project receiving this deposit.")
            allocated = self.db.one(
                """SELECT COALESCE(SUM(s.amount_cents),0) total
                   FROM cash_allocation_sources s JOIN cash_allocations a ON a.id=s.allocation_id
                   WHERE s.withdrawal_id=? AND a.voided=0""", (record_id,)
            )["total"] if row["type"] == "Withdrawal" else 0
            if allocated and not is_withdrawal:
                raise ValueError("A withdrawal with FIFO allocation history cannot be changed into a deposit.")
            if allocated and amount < allocated:
                raise ValueError(
                    f"This withdrawal already sources {money(allocated)} in allocations and cannot be reduced below it."
                )
            if allocated and bank_id != row["bank_account_id"]:
                raise ValueError("The source bank cannot be changed after a withdrawal funds cash allocations.")
            if is_withdrawal:
                available = self.db.bank_balance(bank_id)
                if row["type"] == "Withdrawal" and row["bank_account_id"] == bank_id and not row["voided"]:
                    available += row["amount_cents"]
                if amount > available:
                    raise ValueError("Withdrawal exceeds the selected bank account's available balance.")
            if is_withdrawal:
                head = self.app.authorize_registered_head(
                    "Edit shared cash withdrawal", f"Transaction #{record_id}"
                )
            else:
                head = self.app.authorize_for_project(
                    project_id, "Edit remittance transaction", f"Transaction #{record_id}"
                )
            if not head: return
            self.db.execute("""UPDATE remittances SET project_id=?,type=?,amount_cents=?,txn_date=?,purpose=?,
                care_of=?,signature=?,notes=?,bank_account_id=?,authorized_by_head_id=?,
                authorized_by_registry_id=?,shared_cash=? WHERE id=?""",
                (project_id, data["type"], amount, valid_date(data["txn_date"], True), data["purpose"],
                 data["care_of"], data["signature"], data["notes"], bank_id,
                 None if is_withdrawal else head["id"], head["id"] if is_withdrawal else None,
                 1 if is_withdrawal else 0, record_id))
            self.db.audit(None if is_withdrawal else project_id, "REMITTANCE_EDITED",
                          f"#{record_id} {money(amount)}"); self.app.refresh_all()
        except (ValueError, sqlite3.Error) as exc: messagebox.showerror(APP_TITLE, str(exc))

    def void(self):
        selected = self.tree.selection()
        if selected and str(selected[0]).startswith("interbank-"):
            transfer_id = int(str(selected[0]).split("-", 1)[1])
            row = self.db.one("SELECT * FROM bank_account_transfers WHERE id=?", (transfer_id,))
            if not row:
                return
            try:
                if row["voided"]:
                    if row["amount_cents"] > self.db.bank_balance(row["from_bank_account_id"]):
                        raise ValueError(
                            "This transfer cannot be restored because its source account no longer has enough funds."
                        )
                    action = "Restore inter-bank transfer"
                else:
                    if row["amount_cents"] > self.db.bank_balance(row["to_bank_account_id"]):
                        raise ValueError(
                            "This transfer cannot be voided because the destination account no longer holds enough funds."
                        )
                    action = "Void inter-bank transfer"
                if not messagebox.askyesno(
                    APP_TITLE,
                    f"{action} {row['reference']} for {money(row['amount_cents'])}?",
                    parent=self,
                ):
                    return
                head = self.app.authorize_registered_head(
                    action, f"{row['reference']} for {money(row['amount_cents'])}"
                )
                if not head:
                    return
                self.db.execute(
                    "UPDATE bank_account_transfers SET voided=CASE voided WHEN 1 THEN 0 ELSE 1 END WHERE id=?",
                    (transfer_id,),
                )
                self.db.audit(None, "BANK_ACCOUNT_TRANSFER_VOID_TOGGLED",
                              f"{row['reference']} by {head['name']}")
                self.app.refresh_all()
            except (ValueError, sqlite3.Error) as exc:
                messagebox.showerror(APP_TITLE, str(exc), parent=self)
            return
        record_id = self.selected_remittance_id()
        if record_id:
            row = self.db.one("SELECT type,voided,project_id FROM remittances WHERE id=?", (record_id,))
            if (row and row["type"] != "Withdrawal"
                    and not self.db.project_is_active(row["project_id"])):
                messagebox.showinfo(
                    APP_TITLE,
                    "This transaction belongs to a completed project and cannot be changed unless the project is reactivated.",
                    parent=self,
                )
                return
            linked = self.db.one(
                """SELECT COUNT(*) n FROM cash_allocation_sources s
                   JOIN cash_allocations a ON a.id=s.allocation_id
                   WHERE s.withdrawal_id=? AND a.voided=0""",
                (record_id,),
            )["n"]
            if row and row["type"] == "Withdrawal" and linked:
                messagebox.showerror(
                    APP_TITLE,
                    "This withdrawal has cash-allocation history and cannot be voided. Close its active allocations instead.",
                    parent=self,
                )
                return
        if record_id and messagebox.askyesno(APP_TITLE, "Void or restore this transaction? The audit history is retained."):
            self.db.execute("UPDATE remittances SET voided=CASE voided WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (record_id,))
            self.db.audit(None, "REMITTANCE_VOID_TOGGLED", str(record_id)); self.app.refresh_all()

    def selected_remittance_id(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo(APP_TITLE, "Select a transaction first.")
            return None
        record = str(selected[0])
        if record.startswith("payment-"):
            messagebox.showinfo(
                APP_TITLE,
                "This is an expense bank transfer. Manage its expense or payment from the Expenses tab.",
            )
            return None
        if record.startswith("recovery-"):
            messagebox.showinfo(APP_TITLE, "Manage employee advance recoveries from the Payroll tab.")
            return None
        if record.startswith("redeposit-"):
            messagebox.showinfo(
                APP_TITLE,
                "This is a surrendered-cash redeposit. Its immutable source history is managed from the Expenses petty-cash tab.",
            )
            return None
        if record.startswith("interbank-"):
            return None
        if record.startswith("remittance-"):
            return int(record.split("-", 1)[1])
        return int(record)

    def refresh(self):
        projects, banks = self.project_options(), self.bank_options()
        self.project_combo.configure(values=["All Projects"] + list(projects))
        self.bank_combo.configure(values=["All Banks"] + list(banks))
        if self.project_filter.get() not in self.project_combo["values"]: self.project_filter.set("All Projects")
        if self.bank_filter.get() not in self.bank_combo["values"]: self.bank_filter.set("All Banks")
        project_id, bank_id = projects.get(self.project_filter.get()), banks.get(self.bank_filter.get())
        self.account_tree.delete(*self.account_tree.get_children())
        account_where, account_params = ["active=1"], []
        if bank_id: account_where.append("id=?"); account_params.append(bank_id)
        account_rows = self.db.all(
            f"SELECT * FROM bank_accounts WHERE {' AND '.join(account_where)} ORDER BY bank_name,account_name",
            tuple(account_params),
        )
        for account in account_rows:
            remit_clause = " AND (project_id=? OR shared_cash=1)" if project_id else ""
            remit_params = (account["id"], project_id) if project_id else (account["id"],)
            totals = self.db.one(f"""SELECT
                COALESCE(SUM(CASE WHEN type='Deposit' THEN amount_cents ELSE 0 END),0) deposits,
                COALESCE(SUM(CASE WHEN type='Withdrawal' THEN amount_cents ELSE 0 END),0) withdrawals
                FROM remittances WHERE bank_account_id=? AND voided=0{remit_clause}""", remit_params)
            payment_clause = " AND e.project_id=?" if project_id else ""
            payment_params = (account["id"], project_id) if project_id else (account["id"],)
            transfers = self.db.one(f"""SELECT COALESCE(SUM(pay.amount_cents),0) total
                FROM payments pay JOIN expenses e ON e.id=pay.expense_id
                WHERE pay.bank_account_id=? AND e.voided=0
                  AND pay.accounting_excluded=0{payment_clause}""", payment_params)["total"]
            recovery_clause = " AND a.project_id=?" if project_id else ""
            recovery_params = (account["id"], project_id) if project_id else (account["id"],)
            repayments = self.db.one(f"""SELECT COALESCE(SUM(t.amount_cents),0) total
                FROM cash_advance_transactions t JOIN cash_advances a ON a.id=t.advance_id
                WHERE t.bank_account_id=? AND t.posted=1 AND t.voided=0 AND a.voided=0
                  AND t.txn_type IN ('Bank Repayment','Repayment')
                  AND LOWER(t.method) LIKE '%bank%'{recovery_clause}""",
                recovery_params)["total"]
            redeposits = self.db.one(
                """SELECT COALESCE(SUM(amount_cents),0) total FROM cash_redeposits
                   WHERE bank_account_id=? AND voided=0""", (account["id"],)
            )["total"]
            interbank_in = self.db.one(
                """SELECT COALESCE(SUM(amount_cents),0) total FROM bank_account_transfers
                   WHERE to_bank_account_id=? AND voided=0""", (account["id"],)
            )["total"]
            interbank_out = self.db.one(
                """SELECT COALESCE(SUM(amount_cents),0) total FROM bank_account_transfers
                   WHERE from_bank_account_id=? AND voided=0""", (account["id"],)
            )["total"]
            net_withdrawals = max(0, totals["withdrawals"] - redeposits)
            balance = self.db.bank_balance(account["id"])
            self.account_tree.insert("", "end", iid=account["id"], values=(account["bank_name"],
                f"{account['account_name']} ••{account['account_number'][-4:]}", money(totals["deposits"]),
                money(totals["withdrawals"]), money(redeposits), money(net_withdrawals),
                money(interbank_in), money(interbank_out), money(transfers), money(repayments),
                money(balance)))
        where, params = ["1=1"], []
        if project_id: where.append("(r.project_id=? OR r.shared_cash=1)"); params.append(project_id)
        if bank_id: where.append("r.bank_account_id=?"); params.append(bank_id)
        remittance_rows = self.db.all(f"""SELECT r.*,
            CASE WHEN r.shared_cash=1 OR r.type='Withdrawal' THEN '{SHARED_CASH_LABEL}' ELSE pr.name END project,
            COALESCE(b.bank_name || ' ••' || SUBSTR(b.account_number,-4),'Legacy / unassigned') bank,
            COALESCE(rh.name,h.name,'') authorized_by FROM remittances r
            LEFT JOIN projects pr ON pr.id=r.project_id
            LEFT JOIN bank_accounts b ON b.id=r.bank_account_id
            LEFT JOIN project_heads h ON h.id=r.authorized_by_head_id
            LEFT JOIN head_registry rh ON rh.id=r.authorized_by_registry_id
            WHERE {' AND '.join(where)} ORDER BY r.txn_date DESC,r.id DESC""", tuple(params))
        transfer_where, transfer_params = ["pay.bank_account_id IS NOT NULL", "pay.accounting_excluded=0"], []
        if project_id: transfer_where.append("e.project_id=?"); transfer_params.append(project_id)
        if bank_id: transfer_where.append("pay.bank_account_id=?"); transfer_params.append(bank_id)
        transfer_rows = self.db.all(f"""SELECT pay.id,pay.payment_date txn_date,pay.transaction_time,
            pay.system_reference,pr.name project,
            COALESCE(b.bank_name || ' ••' || SUBSTR(b.account_number,-4),'Legacy / unassigned') bank,
            pay.amount_cents,e.name || CASE WHEN TRIM(e.item)<>'' THEN ' / ' || e.item ELSE '' END purpose,
            e.supplier care_of,COALESCE(h.name,'Legacy / not recorded') authorized_by,e.voided
            FROM payments pay JOIN expenses e ON e.id=pay.expense_id
            JOIN projects pr ON pr.id=e.project_id
            LEFT JOIN bank_accounts b ON b.id=pay.bank_account_id
            LEFT JOIN project_heads h ON h.id=e.authorized_by_head_id
            WHERE {' AND '.join(transfer_where)}
            ORDER BY pay.payment_date DESC,pay.id DESC""", tuple(transfer_params))
        recovery_where, recovery_params = ["t.posted=1", "t.voided=0", "a.voided=0",
                                           "t.txn_type IN ('Cash Repayment','Bank Repayment','Repayment')"], []
        if project_id: recovery_where.append("a.project_id=?"); recovery_params.append(project_id)
        if bank_id: recovery_where.append("t.bank_account_id=?"); recovery_params.append(bank_id)
        recovery_rows = self.db.all(f"""SELECT t.id,t.txn_date,t.created_at transaction_time,
            COALESCE(NULLIF(t.reference,''),'REC-' || PRINTF('%06d',t.id)) system_reference,pr.name project,
            CASE WHEN LOWER(t.method) LIKE '%bank%' THEN
                COALESCE(b.bank_name || ' / ' || SUBSTR(b.account_number,-4),'Bank repayment')
                ELSE 'Shared cash on-hand' END bank,
            t.amount_cents,'Advance repayment - ' || e.name purpose,e.name care_of,
            COALESCE(h.name,'Legacy / not recorded') authorized_by,t.method,0 voided
            FROM cash_advance_transactions t JOIN cash_advances a ON a.id=t.advance_id
            JOIN employees e ON e.id=a.employee_id JOIN projects pr ON pr.id=a.project_id
            LEFT JOIN bank_accounts b ON b.id=t.bank_account_id
            LEFT JOIN project_heads h ON h.id=t.authorized_by_head_id
            WHERE {' AND '.join(recovery_where)} ORDER BY t.txn_date DESC,t.id DESC""",
            tuple(recovery_params))
        redeposit_where, redeposit_params = ["d.voided=0"], []
        if bank_id:
            redeposit_where.append("d.bank_account_id=?"); redeposit_params.append(bank_id)
        redeposit_rows = self.db.all(f"""SELECT d.id,d.deposit_date txn_date,d.transaction_time,
            d.reference system_reference,'{SHARED_CASH_LABEL}' project,
            b.bank_name || ' ..' || SUBSTR(b.account_number,-4) bank,d.amount_cents,
            'Deposit all surrendered cash' purpose,'' care_of,
            COALESCE(h.name,'System') authorized_by,d.voided
            FROM cash_redeposits d JOIN bank_accounts b ON b.id=d.bank_account_id
            LEFT JOIN head_registry h ON h.id=d.authorized_by_registry_id
            WHERE {' AND '.join(redeposit_where)} ORDER BY d.deposit_date DESC,d.id DESC""",
            tuple(redeposit_params))
        interbank_where, interbank_params = ["1=1"], []
        if bank_id:
            interbank_where.append("(t.from_bank_account_id=? OR t.to_bank_account_id=?)")
            interbank_params.extend((bank_id, bank_id))
        interbank_rows = self.db.all(f"""SELECT t.id,t.transfer_date txn_date,t.transaction_time,
            t.reference system_reference,'Shared Bank Funds' project,
            fb.bank_name || ' ..' || SUBSTR(fb.account_number,-4) || ' -> ' ||
                tb.bank_name || ' ..' || SUBSTR(tb.account_number,-4) bank,
            t.amount_cents,t.purpose,'' care_of,
            COALESCE(h.name,'Legacy / not recorded') authorized_by,t.voided,
            t.from_bank_account_id,t.to_bank_account_id,t.notes
            FROM bank_account_transfers t
            JOIN bank_accounts fb ON fb.id=t.from_bank_account_id
            JOIN bank_accounts tb ON tb.id=t.to_bank_account_id
            LEFT JOIN head_registry h ON h.id=t.authorized_by_registry_id
            WHERE {' AND '.join(interbank_where)}
            ORDER BY t.transfer_date DESC,t.id DESC""", tuple(interbank_params))
        self.tree.delete(*self.tree.get_children())
        deposits = sum(row["amount_cents"] for row in remittance_rows
                       if not row["voided"] and row["type"] == "Deposit")
        withdrawals = sum(row["amount_cents"] for row in remittance_rows
                          if not row["voided"] and row["type"] == "Withdrawal")
        ledger_rows = [("remittance", row) for row in remittance_rows]
        ledger_rows.extend(("payment", row) for row in transfer_rows)
        ledger_rows.extend(("recovery", row) for row in recovery_rows)
        ledger_rows.extend(("redeposit", row) for row in redeposit_rows)
        ledger_rows.extend(("interbank", row) for row in interbank_rows)
        ledger_rows.sort(key=lambda entry: (entry[1]["txn_date"], entry[1]["id"]), reverse=True)

        def include_ledger_row(kind, row):
            row_type = (row["type"] if kind == "remittance" else
                        "Bank Transfer" if kind == "payment" else
                        "Inter-bank Transfer" if kind == "interbank" else
                        "Cash Redeposit" if kind == "redeposit" else "Repayment")
            selected_type = self.transaction_type_filter.get()
            if selected_type != "All Transaction Types" and selected_type != row_type:
                return False
            status = "VOID" if row["voided"] else "Active"
            if self.transaction_status_filter.get() != "All Statuses" and self.transaction_status_filter.get() != status:
                return False
            if self.remit_date_from.get() and row["txn_date"] < self.remit_date_from.get():
                return False
            if self.remit_date_to.get() and row["txn_date"] > self.remit_date_to.get():
                return False
            reference = row["system_reference"] if "system_reference" in row.keys() else ""
            term = self.remit_search.get().strip().lower()
            haystack = " ".join(str(row[key]) for key in row.keys()).lower() + " " + str(reference).lower()
            return not term or all(part in haystack for part in term.split())

        for kind, row in ledger_rows:
            if not include_ledger_row(kind, row):
                continue
            occurred = (row["transaction_time"] if "transaction_time" in row.keys() and row["transaction_time"]
                        else row["txn_date"] + " 00:00:00")
            reference = row["system_reference"] if "system_reference" in row.keys() else ""
            if kind == "recovery":
                self.tree.insert("", "end", iid=f"recovery-{row['id']}", values=(
                    occurred, reference, row["project"], row["bank"], "Repayment",
                    money(row["amount_cents"]), row["purpose"], row["care_of"],
                    row["authorized_by"], "Active",
                ))
                continue
            if kind == "payment":
                self.tree.insert("", "end", iid=f"payment-{row['id']}", values=(
                    occurred, reference, row["project"], row["bank"], "Bank Transfer",
                    money(row["amount_cents"]), row["purpose"], row["care_of"], row["authorized_by"],
                    "VOID" if row["voided"] else "Active",
                ))
                continue
            if kind == "redeposit":
                self.tree.insert("", "end", iid=f"redeposit-{row['id']}", values=(
                    occurred, reference, row["project"], row["bank"], "Cash Redeposit",
                    money(row["amount_cents"]), row["purpose"], row["care_of"],
                    row["authorized_by"], "Active",
                ))
                continue
            if kind == "interbank":
                self.tree.insert("", "end", iid=f"interbank-{row['id']}", values=(
                    occurred, reference, row["project"], row["bank"], "Inter-bank Transfer",
                    money(row["amount_cents"]), row["purpose"], "", row["authorized_by"],
                    "VOID" if row["voided"] else "Active",
                ))
                continue
            self.tree.insert("", "end", iid=f"remittance-{row['id']}", values=(occurred, reference, row["project"], row["bank"],
                row["type"], money(row["amount_cents"]), row["purpose"], row["care_of"],
                row["authorized_by"] or "Legacy", "VOID" if row["voided"] else "Active"))
        payment_where, payment_params = ["e.voided=0", "pay.bank_account_id IS NOT NULL",
                                         "pay.accounting_excluded=0"], []
        if project_id: payment_where.append("e.project_id=?"); payment_params.append(project_id)
        if bank_id: payment_where.append("pay.bank_account_id=?"); payment_params.append(bank_id)
        bank_transfers = self.db.one(f"""SELECT COALESCE(SUM(pay.amount_cents),0) total
            FROM payments pay JOIN expenses e ON e.id=pay.expense_id
            WHERE {' AND '.join(payment_where)}""", tuple(payment_params))["total"]
        bank_recoveries = sum(row["amount_cents"] for row in recovery_rows
                              if "bank" in row["method"].lower())
        redeposit_total = sum(row["amount_cents"] for row in redeposit_rows if not row["voided"])
        net_withdrawals = max(0, withdrawals - redeposit_total)
        # A bank-to-bank transfer changes the two individual accounts but not the
        # combined enrolled-bank total. Use the shared balance calculator so both
        # the summary and account ledger always apply the same formula.
        bank_balance = sum(self.db.bank_balance(account["id"]) for account in account_rows)
        self.deposit_value.config(text=money(deposits)); self.withdraw_value.config(text=money(net_withdrawals))
        self.transfer_value.config(text=money(bank_transfers), fg=RED if bank_transfers else MUTED)
        self.bank_value.config(text=money(bank_balance), fg=GREEN if bank_balance >= 0 else RED)
        project_ids = [project_id] if project_id else list(projects.values())
        contract = sum(self.db.one("SELECT contract_value_cents FROM projects WHERE id=?", (pid,))["contract_value_cents"]
                       for pid in project_ids)
        commitment_rows = [self.db.project_commitment_budget(pid) for pid in project_ids]
        project_deposited = sum(row[0] for row in commitment_rows)
        committed = sum(row[1] for row in commitment_rows)
        budget = sum(row[2] for row in commitment_rows)
        self.contract_value.config(text=money(contract))
        self.budget_value.config(text=money(budget), fg=GREEN if budget > 0 else RED)
        if not project_id and not bank_id:
            payments_recorded = sum(self.db.project_budget(pid)[1] for pid in project_ids)
            outstanding = max(0, committed - payments_recorded)
            shared_cash = self.db.cash_summary()[2]
            explanation = (
                f"All-project reconciliation: bank balance {money(bank_balance)} + shared cash on hand "
                f"{money(shared_cash)} − outstanding commitments {money(outstanding)} = project budget "
                f"remaining {money(budget)}."
            )
        else:
            explanation = (
                "Bank balance is a physical-account view for the selected bank; project budget reserves all active "
                "expenses for the selected project scope, while withdrawn cash remains shared across projects."
            )
        self.budget_note.config(
            text=(f"Project budget: deposited {money(project_deposited)} − active expense commitments "
                  f"{money(committed)} = {money(budget)}. {explanation}")
        )


class CalendarTab(BaseTab):
    FIELDS = [
        ("type", "Type", ["Meeting", "Deadline", "Schedule", "Reminder"]),
        ("title", "Title"), ("event_date", "Date (YYYY-MM-DD)"),
        ("event_time", "Time (e.g. 09:30 AM)"), ("notes", "Notes"),
    ]

    def __init__(self, app):
        super().__init__(app)
        self.display_year, self.display_month = date.today().year, date.today().month
        header = ttk.Frame(self); header.pack(fill="x")
        ttk.Label(header, text="Project Calendar", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="+ Event", style="Primary.TButton", command=self.add).pack(side="right")
        ttk.Button(header, text="Delete", style="Secondary.TButton", command=self.delete).pack(side="right", padx=6)
        ttk.Button(header, text="Edit", style="Secondary.TButton", command=self.edit).pack(side="right")
        body = ttk.Panedwindow(self, orient="horizontal"); body.pack(fill="both", expand=True, pady=(12, 0))
        left = ttk.Frame(body); right = ttk.Frame(body, padding=(10, 0, 0, 0))
        body.add(left, weight=4); body.add(right, weight=2)
        monthbar = ttk.Frame(left); monthbar.pack(fill="x", pady=(0, 8))
        self.month_title = ttk.Label(monthbar, text="", style="Section.TLabel"); self.month_title.pack(side="left")
        ttk.Button(monthbar, text="‹", style="Secondary.TButton", command=lambda: self.shift_month(-1)).pack(side="right", padx=2)
        ttk.Button(monthbar, text="›", style="Secondary.TButton", command=lambda: self.shift_month(1)).pack(side="right")
        self.calendar_frame = tk.Frame(left, bg="#D8DEE8"); self.calendar_frame.pack(fill="both", expand=True)
        ttk.Label(right, text="Upcoming", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        self.tree = make_tree(right, [
            ("date", "Date", 90), ("type", "Type", 85), ("title", "Event", 210),
            ("time", "Time", 85), ("done", "Done", 55),
        ])

    def shift_month(self, delta):
        month = self.display_month + delta
        if month < 1: self.display_year -= 1; month = 12
        if month > 12: self.display_year += 1; month = 1
        self.display_month = month; self.refresh()

    def add(self):
        if not self.require_project():
            return
        data = dialog(
            self, "Calendar Event", self.FIELDS, {"event_date": date.today().isoformat()},
            required_keys=("type", "title", "event_date"),
        )
        if data:
            try:
                if not data["title"]:
                    raise ValueError("Title is required.")
                self.db.execute(
                    """INSERT INTO calendar_events(project_id,type,title,event_date,event_time,notes)
                       VALUES(?,?,?,?,?,?)""",
                    (self.project_id, data["type"], data["title"], valid_date(data["event_date"], True),
                     data["event_time"], data["notes"]),
                )
                self.app.refresh_all()
            except ValueError as exc:
                messagebox.showerror(APP_TITLE, str(exc))

    def edit(self):
        if not self.require_project():
            return
        record_id = self.selected_id(self.tree)
        if not record_id:
            return
        row = self.db.one("SELECT * FROM calendar_events WHERE id=?", (record_id,))
        data = dialog(
            self, "Calendar Event", self.FIELDS, dict(row),
            required_keys=("type", "title", "event_date"),
        )
        if data:
            try:
                self.db.execute(
                    """UPDATE calendar_events SET type=?,title=?,event_date=?,event_time=?,notes=? WHERE id=?""",
                    (data["type"], data["title"], valid_date(data["event_date"], True),
                     data["event_time"], data["notes"], record_id),
                )
                self.app.refresh_all()
            except ValueError as exc:
                messagebox.showerror(APP_TITLE, str(exc))

    def toggle(self):
        if not self.require_project():
            return
        record_id = self.selected_id(self.tree)
        if record_id:
            self.db.execute("UPDATE calendar_events SET completed=1-completed WHERE id=?", (record_id,))
            self.app.refresh_all()

    def delete(self):
        if not self.require_project():
            return
        record_id = self.selected_id(self.tree)
        if record_id and messagebox.askyesno(APP_TITLE, "Delete this event?"):
            self.db.execute("DELETE FROM calendar_events WHERE id=?", (record_id,))
            self.app.refresh_all()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for child in self.calendar_frame.winfo_children(): child.destroy()
        self.month_title.config(text=f"{calendar.month_name[self.display_month]} {self.display_year}")
        rows = self.db.all(
            "SELECT * FROM calendar_events WHERE project_id=? ORDER BY event_date,event_time,id",
            (self.project_id,),
        ) if self.project_id else []
        events_by_day = {}
        for row in rows:
            try:
                event_day = date.fromisoformat(row["event_date"])
                if event_day.year == self.display_year and event_day.month == self.display_month:
                    events_by_day.setdefault(event_day.day, []).append(row)
            except ValueError:
                pass
            self.tree.insert("", "end", iid=row["id"], values=(
                row["event_date"], row["type"], row["title"], row["event_time"],
                "Yes" if row["completed"] else "",
            ))
        for col, name in enumerate(("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")):
            tk.Label(self.calendar_frame, text=name, bg="#EEF1F5", fg=MUTED,
                     font=("Segoe UI", 9, "bold"), pady=8).grid(
                         row=0, column=col, sticky="nsew", padx=1, pady=1)
            self.calendar_frame.columnconfigure(col, weight=1, uniform="day")
        for week_index, week in enumerate(calendar.monthcalendar(self.display_year, self.display_month), 1):
            self.calendar_frame.rowconfigure(week_index, weight=1, uniform="week")
            for col, day in enumerate(week):
                cell = tk.Frame(self.calendar_frame, bg=WHITE, padx=6, pady=5)
                cell.grid(row=week_index, column=col, sticky="nsew", padx=1, pady=1)
                if day:
                    tk.Label(cell, text=str(day), bg=WHITE, fg=INK,
                             font=("Segoe UI", 9, "bold")).pack(anchor="ne")
                    for event in events_by_day.get(day, [])[:2]:
                        color = RED if event["type"] == "Deadline" else (
                            ORANGE if event["type"] == "Meeting" else NAVY_ACTIVE)
                        tk.Label(cell, text=event["title"][:18], bg=color, fg=WHITE,
                                 font=("Segoe UI", 8), padx=4, pady=2).pack(fill="x", anchor="w", pady=2)


class ContractorApp(tk.Tk):
    def __init__(self, db_path: Path = DB_PATH):
        super().__init__()
        self.bind_class("Toplevel", "<Map>", self._center_dialog_event, add="+")
        self.title(APP_TITLE)
        self.geometry("1240x760")
        self.minsize(1000, 650)
        self.db = Database(db_path)
        self.project_id = None
        self.project_lookup = {}
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        style = ttk.Style(self)
        if "clam" in style.theme_names(): style.theme_use("clam")
        self.configure(bg=SURFACE)
        style.configure("TFrame", background=SURFACE)
        style.configure("TLabel", background=SURFACE, foreground=INK, font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=SURFACE, foreground=INK, font=("Segoe UI", 20, "bold"))
        style.configure("DialogTitle.TLabel", background=SURFACE, foreground=INK, font=("Segoe UI", 17, "bold"))
        style.configure("Section.TLabel", background=SURFACE, foreground=INK, font=("Segoe UI", 13, "bold"))
        style.configure("Muted.TLabel", background=SURFACE, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("TButton", padding=(10, 7), font=("Segoe UI", 9, "bold"))
        style.configure("Primary.TButton", background=ORANGE, foreground=INK, borderwidth=0)
        style.map("Primary.TButton", background=[("active", "#FBBF24")])
        style.configure("Secondary.TButton", background=WHITE, foreground=INK, bordercolor="#CBD5E1")
        style.configure("Success.TButton", background=GREEN, foreground=WHITE, borderwidth=0)
        style.map("Success.TButton", background=[("active", "#059669")])
        style.configure("Treeview", background=WHITE, fieldbackground=WHITE, foreground=INK,
                        rowheight=36, borderwidth=0, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background="#EEF1F5", foreground=INK,
                        font=("Segoe UI", 9, "bold"), relief="flat")
        style.map("Treeview", background=[("selected", NAVY_ACTIVE)], foreground=[("selected", WHITE)])
        style.configure("TProgressbar", background=ORANGE, troughcolor="#E5E7EB")
        style.configure(
            "Required.TEntry", fieldbackground="#FEE2E2", bordercolor="#DC2626",
            lightcolor="#DC2626", darkcolor="#DC2626",
        )
        style.configure(
            "Required.TCombobox", fieldbackground="#FEE2E2", bordercolor="#DC2626",
            lightcolor="#DC2626", darkcolor="#DC2626", arrowcolor="#DC2626",
        )

        shell = tk.Frame(self, bg=SURFACE); shell.pack(fill="both", expand=True)
        sidebar = tk.Frame(shell, bg=NAVY, width=225); sidebar.pack(side="left", fill="y"); sidebar.pack_propagate(False)
        brand = tk.Frame(sidebar, bg=NAVY, padx=20, pady=24); brand.pack(fill="x")
        tk.Label(brand, text="ConTracktor", bg=NAVY, fg=WHITE,
                 font=("Segoe UI", 20, "bold")).pack(anchor="w")
        tk.Label(brand, text="PRO SUITE", bg=NAVY, fg=ORANGE,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        nav = tk.Frame(sidebar, bg=NAVY, pady=18); nav.pack(fill="x")
        self.nav_buttons = {}
        nav_items = [("Dashboard", "▦"), ("Completed Projects", "✓"),
                     ("Progress", "↗"), ("Expenses", "▣"), ("Inventory", "▨"),
                     ("Contacts", "▤"), ("Payroll", "▥"), ("Remittances", "▧"),
                     ("Calendar", "□")]
        for name, icon in nav_items:
            btn = tk.Button(nav, text=f"  {icon}   {name}", anchor="w", bg=NAVY, fg="#AAB4C5",
                            activebackground=NAVY_ACTIVE, activeforeground=WHITE, bd=0,
                            font=("Segoe UI", 10, "bold"), padx=14, pady=12,
                            command=lambda n=name: self.show_page(n))
            btn.pack(fill="x"); self.nav_buttons[name] = btn
        tk.Label(sidebar, text="Local • SQLite", bg=NAVY, fg="#6F7B91",
                 font=("Segoe UI", 9)).pack(side="bottom", anchor="w", padx=20, pady=18)

        body = tk.Frame(shell, bg=SURFACE); body.pack(side="left", fill="both", expand=True)
        header = tk.Frame(body, bg=WHITE, height=64, highlightthickness=1,
                          highlightbackground="#E5E7EB", padx=18, pady=11)
        header.pack(fill="x"); header.pack_propagate(False)
        tk.Label(header, text="Current project", bg=WHITE, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 8))
        self.project_var = tk.StringVar()
        self.project_combo = ttk.Combobox(header, textvariable=self.project_var, state="readonly", width=27)
        self.project_combo.pack(side="left")
        self.project_combo.bind("<<ComboboxSelected>>", self.combo_selected)
        self.edit_project_button = ttk.Button(
            header, text="Edit Project", style="Secondary.TButton",
            command=lambda: self.pages["Dashboard"].edit(),
        )
        self.edit_project_button.pack(side="left", padx=(10, 5))
        self.project_heads_button = ttk.Button(
            header, text="Project Heads", style="Secondary.TButton",
            command=self.manage_current_heads,
        )
        self.project_heads_button.pack(side="left")
        self.complete_project_button = ttk.Button(
            header, text="Complete Project", style="Success.TButton",
            command=lambda: self.pages["Dashboard"].complete_project(),
        )
        self.complete_project_button.pack(side="left", padx=(5, 0))
        ttk.Button(header, text="+ New Project", style="Primary.TButton",
                   command=lambda: self.pages["Dashboard"].add()).pack(side="right")
        tools = tk.Menubutton(header, text="Tools ▾", bg=WHITE, fg=INK, relief="solid", bd=1,
                              font=("Segoe UI", 9, "bold"), padx=12, pady=6)
        tools_menu = tk.Menu(tools, tearoff=False)
        tools_menu.add_command(label="Export project to TXT", command=self.export_text)
        tools_menu.add_command(label="Export filtered expenses to PDF",
                               command=lambda: self.pages["Expenses"].export_pdf())
        tools_menu.add_command(label="Backup SQLite database", command=self.backup)
        tools_menu.add_separator()
        tools_menu.add_command(label="Manage project heads", command=self.manage_current_heads)
        tools.configure(menu=tools_menu); tools.pack(side="right", padx=8)

        page_host = tk.Frame(body, bg=SURFACE)
        page_host.pack(fill="both", expand=True, padx=(18, 8), pady=16)
        self.page_scrollbar = ttk.Scrollbar(page_host, orient="vertical")
        self.page_scrollbar.pack(side="right", fill="y")
        self.page_canvas = tk.Canvas(
            page_host, bg=SURFACE, highlightthickness=0,
            yscrollcommand=self.page_scrollbar.set,
        )
        self.page_canvas.pack(side="left", fill="both", expand=True)
        self.page_scrollbar.configure(command=self.page_canvas.yview)
        self.notebook = tk.Frame(self.page_canvas, bg=SURFACE)
        self.page_window = self.page_canvas.create_window(
            (0, 0), window=self.notebook, anchor="nw",
        )
        # Give every tab enough vertical working room for its ledgers. The page
        # canvas remains scrollable when the application window is shorter.
        self.page_requested_height = 1000
        self.page_canvas.bind("<Configure>", self._resize_page_canvas)
        self.notebook.bind(
            "<Configure>",
            lambda _event: self.page_canvas.configure(scrollregion=self.page_canvas.bbox("all")),
        )
        self.tabs = [
            ("Dashboard", ProjectsTab(self)),
            ("Completed Projects", CompletedProjectsTab(self)),
            ("Progress", ProgressTab(self)),
            ("Expenses", ExpensesTab(self)), ("Inventory", InventoryTab(self)),
            ("Contacts", ContactsTab(self)),
            ("Payroll", PayrollTab(self)), ("Remittances", RemittancesTab(self)),
            ("Calendar", CalendarTab(self)),
        ]
        self.pages = dict(self.tabs)
        for label, tab in self.tabs:
            tab.place(x=0, y=0, relwidth=1, relheight=1)
        self.show_page("Dashboard")
        self.load_projects()

    def show_page(self, name):
        page = getattr(self, "pages", {}).get(name)
        if page:
            page.tkraise(); page.refresh()
            requested = page.requested_page_height() if hasattr(page, "requested_page_height") else 1000
            self.set_page_content_height(requested)
            self.page_canvas.yview_moveto(0)
        for label, button in getattr(self, "nav_buttons", {}).items():
            active = label == name
            button.configure(bg=NAVY_ACTIVE if active else NAVY,
                             fg=WHITE if active else "#AAB4C5")

    def _resize_page_canvas(self, event):
        page_height = max(event.height, self.page_requested_height, 1000)
        self.page_canvas.itemconfigure(self.page_window, width=event.width, height=page_height)
        self.notebook.configure(width=event.width, height=page_height)
        self.page_canvas.configure(scrollregion=(0, 0, event.width, page_height))

    def set_page_content_height(self, requested_height):
        """Let a page grow below the viewport while retaining whole-page scrolling."""
        self.page_requested_height = max(1000, int(requested_height))
        width = max(1, self.page_canvas.winfo_width())
        height = max(self.page_canvas.winfo_height(), self.page_requested_height)
        self.page_canvas.itemconfigure(self.page_window, width=width, height=height)
        self.notebook.configure(width=width, height=height)
        self.page_canvas.configure(scrollregion=(0, 0, width, height))

    def _center_dialog_event(self, event):
        window = event.widget
        if getattr(window, "_contractor_centered", False):
            return
        try:
            if window.attributes("-fullscreen"):
                return
        except tk.TclError:
            return
        window._contractor_centered = True
        window.after_idle(lambda: center_toplevel(window))

    def authorize(self, action: str, details: str):
        return self.authorize_for_project(self.project_id, action, details)

    def authorize_registered_head(self, action: str, details: str, registry_id: int | None = None):
        heads = self.db.registered_heads()
        if registry_id is not None:
            heads = [head for head in heads if head["id"] == registry_id]
        if not heads:
            messagebox.showerror(
                APP_TITLE, "The required registered project head is not active."
            )
            return None
        win = HeadAuthorizationDialog(self, heads, action, details)
        self.wait_window(win)
        return win.result

    def authorize_for_project(self, project_id: int | None, action: str, details: str):
        if not project_id:
            messagebox.showinfo(APP_TITLE, "Create or select a project first."); return None
        if not self.db.project_is_active(project_id):
            messagebox.showerror(
                APP_TITLE,
                "This project is completed and read-only. Reactivate it from Completed Projects before making changes."
            )
            return None
        heads = self.db.all(
            "SELECT * FROM project_heads WHERE project_id=? AND active=1 ORDER BY name", (project_id,))
        if not heads:
            if project_id == self.project_id and messagebox.askyesno(
                APP_TITLE, "This project has no project head yet. Add one now?"
            ):
                self.manage_current_heads()
                heads = self.db.all(
                    "SELECT * FROM project_heads WHERE project_id=? AND active=1 ORDER BY name", (project_id,))
        if not heads: return None
        win = HeadAuthorizationDialog(self, heads, action, details); self.wait_window(win)
        return win.result

    def authorize_all_heads(self, project_id: int, action: str, details: str,
                            allow_completed: bool = False):
        if not allow_completed and not self.db.project_is_active(project_id):
            messagebox.showerror(
                APP_TITLE,
                "This project is completed and read-only. Reactivate it before making changes."
            )
            return None
        heads = self.db.all(
            "SELECT * FROM project_heads WHERE project_id=? AND active=1 ORDER BY name", (project_id,))
        if not heads:
            messagebox.showerror(APP_TITLE, "This project has no active project heads to approve the edit.")
            return None
        win = AllHeadsAuthorizationDialog(self, heads, action, details); self.wait_window(win)
        return win.result

    def authorize_two_heads(self, project_id: int, action: str, details: str,
                            role_one="Issuer / approver", role_two="Receiver / reviewer",
                            head_ids=None):
        if not self.db.project_is_active(project_id):
            messagebox.showerror(APP_TITLE, "This project is completed and read-only.")
            return None
        heads = self.db.all(
            "SELECT * FROM project_heads WHERE project_id=? AND active=1 ORDER BY name", (project_id,)
        )
        if len(heads) < 2:
            messagebox.showerror(
                APP_TITLE, "This action requires at least two active project heads on the project."
            )
            return None
        if head_ids and any(int(head_id) not in {row["id"] for row in heads} for head_id in head_ids):
            messagebox.showerror(APP_TITLE, "One of the selected project heads is no longer active.")
            return None
        win = TwoHeadAuthorizationDialog(
            self, heads, action, details, role_one, role_two, head_ids=head_ids,
        )
        self.wait_window(win)
        return win.result

    def authorize_two_registered_heads(self, action: str, details: str,
                                       role_one="Issuer / approver",
                                       role_two="Receiver / reviewer", registry_ids=None):
        """Authenticate two global registry identities for shared-cash actions."""
        heads = self.db.registered_heads()
        if len(heads) < 2:
            messagebox.showerror(
                APP_TITLE, "This action requires at least two active registered project heads."
            )
            return None
        valid_ids = {row["id"] for row in heads}
        if registry_ids and any(int(head_id) not in valid_ids for head_id in registry_ids):
            messagebox.showerror(APP_TITLE, "One of the selected registered heads is no longer active.")
            return None
        win = TwoHeadAuthorizationDialog(
            self, heads, action, details, role_one, role_two, head_ids=registry_ids,
        )
        self.wait_window(win)
        return win.result

    def manage_current_heads(self):
        if not self.project_id:
            messagebox.showinfo(APP_TITLE, "Create or select a project first."); return
        if not self.db.project_is_active(self.project_id):
            messagebox.showinfo(
                APP_TITLE, "Completed projects are read-only. Reactivate the project before changing its heads."
            ); return
        win = ManageHeadsDialog(self, self.db, self.project_id); self.wait_window(win)

    def manage_head_registry(self):
        win = HeadRegistryDialog(self, self.db); self.wait_window(win)

    def load_projects(self, select_id=None):
        rows = self.db.all("SELECT id,name,status FROM projects ORDER BY name")
        self.project_lookup = {ALL_PROJECTS_LABEL: None}
        self.project_lookup.update({
            f"{'✓ ' if r['status']=='Completed' else ''}{r['name']}  [#{r['id']}]": r["id"]
            for r in rows
        })
        self.project_combo["values"] = list(self.project_lookup)
        valid_ids = {row["id"] for row in rows}
        if select_id is not None:
            self.project_id = select_id
        elif self.project_id not in valid_ids:
            self.project_id = None
        if self.project_id:
            label = next((name for name, pid in self.project_lookup.items() if pid == self.project_id), "")
            self.project_var.set(label)
        else:
            self.project_var.set(ALL_PROJECTS_LABEL)
        active_selected = bool(self.project_id and self.db.project_is_active(self.project_id))
        button_state = "normal" if active_selected else "disabled"
        self.edit_project_button.configure(state=button_state)
        self.project_heads_button.configure(state=button_state)
        self.complete_project_button.configure(state=button_state)
        self.refresh_all()

    def combo_selected(self, _event=None):
        self.select_project(self.project_lookup.get(self.project_var.get()))

    def select_project(self, project_id):
        self.project_id = project_id
        self.load_projects()

    def refresh_all(self):
        for _label, tab in self.tabs:
            tab.refresh()

    def backup(self):
        if not self.db.path.exists():
            messagebox.showinfo(APP_TITLE, "There is no database to back up yet.")
            return
        default = f"contractor_tracker_backup_{datetime.now():%Y%m%d_%H%M%S}.db"
        destination = filedialog.asksaveasfilename(
            title="Save Database Backup", initialfile=default,
            defaultextension=".db", filetypes=[("SQLite database", "*.db"), ("All files", "*.*")],
        )
        if destination:
            self.db.conn.commit()
            backup_conn = sqlite3.connect(destination)
            with backup_conn:
                self.db.conn.backup(backup_conn)
            backup_conn.close()
            messagebox.showinfo(APP_TITLE, f"Backup saved:\n{destination}")

    def export_text(self):
        if not self.project_id:
            messagebox.showinfo(APP_TITLE, "Create or select a project first.")
            return
        project = self.db.one("SELECT * FROM projects WHERE id=?", (self.project_id,))
        default = f"{project['name'].replace(' ', '_')}_{date.today():%Y%m%d}.txt"
        destination = filedialog.asksaveasfilename(
            title="Export Project Report", initialfile=default,
            defaultextension=".txt", filetypes=[("Text document", "*.txt")],
        )
        if not destination:
            return
        lines = [
            APP_TITLE, "=" * 72, f"Exported: {datetime.now():%Y-%m-%d %H:%M}",
            f"Project: {project['name']}", f"Client: {project['client']}",
            f"Address: {project['address']}",
            f"Contract value: {money(project['contract_value_cents'])}",
            f"Schedule: {project['start_date']} to {project['target_date']}",
            f"Notes: {project['notes']}", "",
        ]
        sections = [
            ("PROJECT HEADS",
             "SELECT name,position,active,created_at FROM project_heads WHERE project_id=? ORDER BY name"),
            ("PHASES & TASKS",
             """SELECT p.name phase,t.milestone,t.name,t.deadline,t.completed FROM phases p
                LEFT JOIN tasks t ON t.phase_id=p.id WHERE p.project_id=?
                ORDER BY p.sort_order,t.deadline,t.id"""),
            ("EXPENSES",
             """SELECT e.name,e.item,e.supplier,e.trade,e.expense_date,e.status,e.total_cents,e.voided,
                COALESCE(h.name,'Legacy / not recorded') authorized_by,
                COALESCE(SUM(pay.amount_cents),0) paid_cents,
                COALESCE((SELECT SUM(t.amount_cents) FROM cash_advances ca
                    JOIN cash_advance_transactions t ON t.advance_id=ca.id
                    WHERE ca.expense_id=e.id AND ca.voided=0 AND t.voided=0
                      AND t.posted=1 AND t.txn_type IN ('Cash Repayment','Bank Repayment','Repayment')),0) recovered_cents,
                e.total_cents-COALESCE((SELECT SUM(t.amount_cents) FROM cash_advances ca
                    JOIN cash_advance_transactions t ON t.advance_id=ca.id
                    WHERE ca.expense_id=e.id AND ca.voided=0 AND t.voided=0
                      AND t.posted=1 AND t.txn_type IN ('Cash Repayment','Bank Repayment','Repayment')),0) net_cents
                FROM expenses e
                LEFT JOIN payments pay ON pay.expense_id=e.id AND pay.accounting_excluded=0
                LEFT JOIN project_heads h ON h.id=e.authorized_by_head_id WHERE e.project_id=?
                GROUP BY e.id ORDER BY e.expense_date,e.id"""),
            ("CONTACTS", "SELECT name,role,company,phone,email,address FROM contacts WHERE project_id=? ORDER BY name"),
            ("EMPLOYEES",
             """SELECT employee_no,name,birthday,contact_number,position,class,pay_basis,
                daily_rate_cents,rate_cents,active FROM employees
                WHERE project_id=? ORDER BY name"""),
            ("ATTENDANCE",
             """SELECT e.name,a.clock_in,a.clock_out,a.lunch_hours,a.regular_hours,
                a.overtime_hours,a.regular_pay_cents,a.overtime_pay_cents,a.gross_cents,
                a.day_type,a.source,
                CASE WHEN a.committed_expense_id IS NULL THEN 'No' ELSE 'Yes' END committed
                FROM attendance a JOIN employees e ON e.id=a.employee_id
                WHERE e.project_id=? ORDER BY a.clock_in"""),
            ("PAYROLL BATCHES",
             """SELECT b.batch_ref,b.period_start,b.period_end,b.gross_cents,
                b.deduction_cents,b.net_cents,COALESCE(h.name,'Legacy / not recorded') authorized_by,
                b.created_at FROM payroll_batches b
                LEFT JOIN project_heads h ON h.id=b.authorized_by_head_id
                WHERE b.project_id=? ORDER BY b.created_at,b.id"""),
            ("EMPLOYEE CASH ADVANCES",
             """SELECT e.name employee,a.advance_date,a.original_cents,a.reason,a.method,
                COALESCE(SUM(CASE WHEN t.posted=1 AND t.voided=0 AND t.txn_type<>'Advance'
                    THEN t.amount_cents ELSE 0 END),0) recovered_cents,
                a.original_cents-COALESCE(SUM(CASE WHEN t.posted=1 AND t.voided=0
                    AND t.txn_type<>'Advance' THEN t.amount_cents ELSE 0 END),0) outstanding_cents,
                a.voided FROM cash_advances a JOIN employees e ON e.id=a.employee_id
                LEFT JOIN cash_advance_transactions t ON t.advance_id=a.id
                WHERE a.project_id=? GROUP BY a.id ORDER BY a.advance_date,a.id"""),
            ("CASH ADVANCE TRANSACTIONS",
             """SELECT e.name employee,t.txn_date,t.txn_type,t.amount_cents,t.method,
                t.reference,t.notes,CASE WHEN t.posted=1 THEN 'Posted' ELSE 'Pending payroll' END posting,
                COALESCE(h.name,'Legacy / not recorded') authorized_by,t.voided
                FROM cash_advance_transactions t JOIN cash_advances a ON a.id=t.advance_id
                JOIN employees e ON e.id=a.employee_id
                LEFT JOIN project_heads h ON h.id=t.authorized_by_head_id
                WHERE a.project_id=? ORDER BY t.txn_date,t.id"""),
            ("REMITTANCES",
             """SELECT r.txn_date,r.type,r.amount_cents,r.purpose,r.care_of,r.signature,
                CASE WHEN r.shared_cash=1 THEN 'Shared Cash Pool' ELSE 'Project Deposit' END scope,
                COALESCE(b.bank_name || ' - ' || b.account_name,'Legacy / unassigned') bank_account,
                COALESCE(rh.name,h.name,'Legacy / not recorded') authorized_by,r.voided
                FROM remittances r LEFT JOIN project_heads h ON h.id=r.authorized_by_head_id
                LEFT JOIN head_registry rh ON rh.id=r.authorized_by_registry_id
                LEFT JOIN bank_accounts b ON b.id=r.bank_account_id
                WHERE (r.project_id=? AND r.type='Deposit') OR r.shared_cash=1
                ORDER BY r.txn_date"""),
            ("CALENDAR",
             "SELECT event_date,event_time,type,title,completed,notes FROM calendar_events WHERE project_id=? ORDER BY event_date,event_time"),
            ("AUDIT LOG",
             "SELECT created_at,action,details FROM audit_log WHERE project_id=? ORDER BY created_at"),
        ]
        for title, sql in sections:
            lines += [title, "-" * 72]
            rows = self.db.all(sql, (self.project_id,))
            if not rows:
                lines.append("(none)")
            for row in rows:
                values = []
                for key in row.keys():
                    value = row[key]
                    if key.endswith("_cents"):
                        value = money(value)
                    elif key == "completed":
                        value = "Yes" if value else "No"
                    elif key == "voided":
                        value = "VOID" if value else "Active"
                    values.append(f"{key.replace('_', ' ').title()}: {value if value is not None else ''}")
                lines.append(" | ".join(values))
            lines.append("")
        Path(destination).write_text("\n".join(lines), encoding="utf-8")
        try:
            if sys.platform == "win32":
                subprocess.Popen(["notepad.exe", destination])
            else:
                messagebox.showinfo(APP_TITLE, f"Report saved:\n{destination}")
        except OSError:
            messagebox.showinfo(APP_TITLE, f"Report saved:\n{destination}")

    def on_close(self):
        self.db.close()
        self.destroy()


if __name__ == "__main__":
    APP_DIR.mkdir(parents=True, exist_ok=True)
    ContractorApp().mainloop()
