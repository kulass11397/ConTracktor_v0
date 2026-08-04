"""Contractor Project Tracker - local Tkinter + SQLite prototype.

Run with: python app.py
No third-party packages are required.
"""

from __future__ import annotations

import hashlib
import calendar
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "Contractor Project Tracker"
APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "contractor_tracker.db"
DEFAULT_PHASES = [
    "Pre-Construction", "Site Preparation", "Foundation", "Structural",
    "Roofing", "Electrical", "Plumbing", "Finishes", "Inspection & Handover",
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


def qty_decimal(value: str) -> Decimal:
    try:
        result = Decimal(value.strip() or "0")
        if result < 0:
            raise ValueError
        return result
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Quantity must be a non-negative number.") from exc


def valid_date(value: str, required: bool = False) -> str:
    value = value.strip()
    if not value and not required:
        return ""
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Dates must use YYYY-MM-DD format.") from exc
    return value


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
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._create_schema()

    def _create_schema(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, client TEXT NOT NULL DEFAULT '',
            contract_value_cents INTEGER NOT NULL DEFAULT 0, start_date TEXT NOT NULL DEFAULT '',
            target_date TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
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
            notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
        CREATE TABLE IF NOT EXISTS remittances (
            id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            type TEXT NOT NULL CHECK(type IN ('Deposit','Withdrawal')), amount_cents INTEGER NOT NULL,
            txn_date TEXT NOT NULL, purpose TEXT NOT NULL DEFAULT '', care_of TEXT NOT NULL DEFAULT '',
            signature TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            voided INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            type TEXT NOT NULL, title TEXT NOT NULL, event_date TEXT NOT NULL,
            event_time TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            completed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY, project_id INTEGER, action TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_expenses_project ON expenses(project_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_phase ON tasks(phase_id);
        CREATE INDEX IF NOT EXISTS idx_events_project_date ON calendar_events(project_id, event_date);
        """)
        self._ensure_column("expenses", "authorized_by_head_id", "INTEGER")
        self._ensure_column("remittances", "authorized_by_head_id", "INTEGER")
        self.conn.commit()

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

    def audit(self, project_id: int | None, action: str, details: str = ""):
        self.execute(
            "INSERT INTO audit_log(project_id, action, details) VALUES(?,?,?)",
            (project_id, action, details),
        )

    def create_project(self, values: dict) -> int:
        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO projects(name,client,contract_value_cents,start_date,target_date,notes)
                   VALUES(?,?,?,?,?,?)""",
                (values["name"], values["client"], cents(values["contract_value"]),
                 valid_date(values["start_date"]), valid_date(values["target_date"]), values["notes"]),
            )
            project_id = cur.lastrowid
            self.conn.executemany(
                "INSERT INTO phases(project_id,name,sort_order) VALUES(?,?,?)",
                [(project_id, name, index) for index, name in enumerate(DEFAULT_PHASES)],
            )
            for head in values.get("heads", []):
                salt, digest = hash_pin(head["pin"])
                self.conn.execute(
                    """INSERT INTO project_heads(project_id,name,position,pin_salt,pin_hash)
                       VALUES(?,?,?,?,?)""",
                    (project_id, head["name"], head["position"], salt, digest),
                )
            self.conn.execute(
                "INSERT INTO audit_log(project_id,action,details) VALUES(?,?,?)",
                (project_id, "PROJECT_CREATED", values["name"]),
            )
        return project_id

    def close(self):
        self.conn.close()


class FormDialog(tk.Toplevel):
    def __init__(self, parent, title: str, fields: list[tuple], initial: dict | None = None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result = None
        self.vars = {}
        initial = initial or {}
        body = ttk.Frame(self, padding=14)
        body.grid(sticky="nsew")
        for row, spec in enumerate(fields):
            key, label = spec[0], spec[1]
            choices = spec[2] if len(spec) > 2 else None
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
            var = tk.StringVar(value=str(initial.get(key, "")))
            self.vars[key] = var
            if choices:
                widget = ttk.Combobox(body, textvariable=var, values=choices, state="readonly", width=38)
                if not var.get() and choices:
                    var.set(choices[0])
            else:
                widget = ttk.Entry(body, textvariable=var, width=41)
            widget.grid(row=row, column=1, sticky="ew", pady=4)
        buttons = ttk.Frame(body)
        buttons.grid(row=len(fields), column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Save", command=self.save).pack(side="right")
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self.save())
        self.transient(parent)
        self.grab_set()
        self.wait_visibility()
        self.focus_force()

    def save(self):
        self.result = {key: var.get().strip() for key, var in self.vars.items()}
        self.destroy()


def dialog(parent, title, fields, initial=None):
    win = FormDialog(parent, title, fields, initial)
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
        body = ttk.Frame(self, padding=20); body.pack(fill="both", expand=True)
        ttk.Label(body, text="Project head", style="DialogTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        labels = [("name", "Full name", False), ("position", "Position", False),
                  ("pin", "Private PIN", True), ("confirm", "Confirm PIN", True)]
        for row, (key, label, secret) in enumerate(labels, 1):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
            ttk.Entry(body, textvariable=self.vars[key], show="*" if secret else "", width=34).grid(
                row=row, column=1, pady=5)
        ttk.Label(body, text="PINs are hashed and are never displayed again.", style="Muted.TLabel").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(6, 12))
        buttons = ttk.Frame(body); buttons.grid(row=6, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Cancel", style="Secondary.TButton", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Add Head", style="Primary.TButton", command=self.save).pack(side="right")
        self.transient(parent); self.grab_set(); self.bind("<Escape>", lambda _e: self.destroy())

    def save(self):
        values = {key: var.get().strip() for key, var in self.vars.items()}
        if not values["name"] or not values["position"]:
            messagebox.showerror(APP_TITLE, "Name and position are required.", parent=self); return
        if values["pin"] != values["confirm"]:
            messagebox.showerror(APP_TITLE, "The PIN confirmation does not match.", parent=self); return
        try:
            hash_pin(values["pin"])
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self); return
        self.result = {"name": values["name"], "position": values["position"], "pin": values["pin"]}
        self.destroy()


class ProjectDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Create New Project")
        self.geometry("760x610")
        self.minsize(700, 560)
        self.result = None
        self.heads = []
        self.vars = {key: tk.StringVar() for key in
                     ("name", "client", "contract_value", "start_date", "target_date", "notes")}
        self.vars["start_date"].set(date.today().isoformat())
        body = ttk.Frame(self, padding=22); body.pack(fill="both", expand=True)
        ttk.Label(body, text="Create a new project", style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(body, text="Project heads will authorize protected financial activity.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 14))
        fields = ttk.Frame(body); fields.pack(fill="x")
        specs = [("name", "Project name"), ("client", "Client"),
                 ("contract_value", "Contract value"), ("start_date", "Start date (YYYY-MM-DD)"),
                 ("target_date", "Target date (YYYY-MM-DD)"), ("notes", "Notes")]
        for index, (key, label) in enumerate(specs):
            row, col = divmod(index, 2)
            cell = ttk.Frame(fields); cell.grid(row=row, column=col, sticky="ew", padx=(0 if col == 0 else 8, 8 if col == 0 else 0), pady=5)
            ttk.Label(cell, text=label).pack(anchor="w")
            ttk.Entry(cell, textvariable=self.vars[key]).pack(fill="x", pady=(3, 0))
        fields.columnconfigure(0, weight=1); fields.columnconfigure(1, weight=1)
        headbar = ttk.Frame(body); headbar.pack(fill="x", pady=(18, 6))
        ttk.Label(headbar, text="Project heads", style="Section.TLabel").pack(side="left")
        ttk.Button(headbar, text="+ Add Head", style="Primary.TButton", command=self.add_head).pack(side="right")
        ttk.Button(headbar, text="Remove", style="Secondary.TButton", command=self.remove_head).pack(side="right", padx=6)
        self.tree = ttk.Treeview(body, columns=("name", "position"), show="headings", height=7)
        self.tree.heading("name", text="NAME"); self.tree.heading("position", text="POSITION")
        self.tree.column("name", width=280); self.tree.column("position", width=260)
        self.tree.pack(fill="both", expand=True)
        footer = ttk.Frame(body); footer.pack(fill="x", pady=(16, 0))
        ttk.Button(footer, text="Cancel", style="Secondary.TButton", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="Create Project", style="Primary.TButton", command=self.save).pack(side="right")
        self.transient(parent); self.grab_set(); self.bind("<Escape>", lambda _e: self.destroy())

    def add_head(self):
        win = HeadEditorDialog(self); self.wait_window(win)
        if win.result:
            self.heads.append(win.result); self.refresh_heads()

    def remove_head(self):
        selected = self.tree.selection()
        if selected:
            self.heads.pop(int(selected[0])); self.refresh_heads()

    def refresh_heads(self):
        self.tree.delete(*self.tree.get_children())
        for index, head in enumerate(self.heads):
            self.tree.insert("", "end", iid=str(index), values=(head["name"], head["position"]))

    def save(self):
        values = {key: var.get().strip() for key, var in self.vars.items()}
        try:
            if not values["name"]: raise ValueError("Project name is required.")
            cents(values["contract_value"])
            valid_date(values["start_date"]); valid_date(values["target_date"])
            if not self.heads: raise ValueError("Add at least one project head with a private PIN.")
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self); return
        values["heads"] = list(self.heads); self.result = values; self.destroy()


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


class ManageHeadsDialog(tk.Toplevel):
    def __init__(self, parent, db, project_id):
        super().__init__(parent)
        self.title("Manage Project Heads"); self.geometry("610x420")
        self.db, self.project_id = db, project_id
        body = ttk.Frame(self, padding=20); body.pack(fill="both", expand=True)
        ttk.Label(body, text="Project heads", style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(body, text="Heads can authorize expenses, remittances and payroll commitments.", style="Muted.TLabel").pack(anchor="w", pady=(2, 12))
        bar = ttk.Frame(body); bar.pack(fill="x")
        ttk.Button(bar, text="+ Add Head", style="Primary.TButton", command=self.add).pack(side="left")
        ttk.Button(bar, text="Remove Selected", style="Secondary.TButton", command=self.remove).pack(side="left", padx=6)
        self.tree = ttk.Treeview(body, columns=("name", "position"), show="headings")
        self.tree.heading("name", text="NAME"); self.tree.heading("position", text="POSITION")
        self.tree.pack(fill="both", expand=True, pady=10)
        ttk.Button(body, text="Done", style="Primary.TButton", command=self.destroy).pack(anchor="e")
        self.refresh(); self.transient(parent); self.grab_set()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for row in self.db.all("SELECT * FROM project_heads WHERE project_id=? AND active=1 ORDER BY name", (self.project_id,)):
            self.tree.insert("", "end", iid=row["id"], values=(row["name"], row["position"]))

    def add(self):
        win = HeadEditorDialog(self); self.wait_window(win)
        if win.result:
            salt, digest = hash_pin(win.result["pin"])
            self.db.execute("INSERT INTO project_heads(project_id,name,position,pin_salt,pin_hash) VALUES(?,?,?,?,?)",
                            (self.project_id, win.result["name"], win.result["position"], salt, digest))
            self.refresh()

    def remove(self):
        selected = self.tree.selection()
        count = self.db.one("SELECT COUNT(*) n FROM project_heads WHERE project_id=? AND active=1", (self.project_id,))["n"]
        if not selected: return
        if count <= 1:
            messagebox.showerror(APP_TITLE, "A project must keep at least one active head.", parent=self); return
        if messagebox.askyesno(APP_TITLE, "Remove this project head?", parent=self):
            self.db.execute("UPDATE project_heads SET active=0 WHERE id=?", (int(selected[0]),)); self.refresh()


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
        return True

    def selected_id(self, tree):
        selected = tree.selection()
        if not selected:
            messagebox.showinfo(APP_TITLE, "Select a record first.")
            return None
        return int(selected[0])


def make_tree(parent, columns: list[tuple[str, str, int]]):
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=True, pady=(8, 0))
    tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", selectmode="browse")
    for key, label, width in columns:
        tree.heading(key, text=label)
        tree.column(key, width=width, anchor="w")
    scroll_y = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    scroll_x = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
    tree.grid(row=0, column=0, sticky="nsew")
    scroll_y.grid(row=0, column=1, sticky="ns")
    scroll_x.grid(row=1, column=0, sticky="ew")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    return tree


def metric_card(parent, title: str, accent: str = ORANGE):
    card = tk.Frame(parent, bg=WHITE, highlightbackground="#D8DEE8", highlightthickness=1, padx=16, pady=13)
    tk.Label(card, text=title.upper(), bg=WHITE, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w")
    value = tk.Label(card, text="—", bg=WHITE, fg=accent, font=("Segoe UI", 22, "bold"))
    value.pack(anchor="w", pady=(7, 0))
    return card, value


class ProjectsTab(BaseTab):
    FIELDS = [
        ("name", "Project name"), ("client", "Client"), ("contract_value", "Contract value"),
        ("start_date", "Start date (YYYY-MM-DD)"), ("target_date", "Target date (YYYY-MM-DD)"),
        ("notes", "Notes"),
    ]

    def __init__(self, app):
        super().__init__(app)
        header = ttk.Frame(self); header.pack(fill="x")
        title = ttk.Frame(header); title.pack(side="left")
        ttk.Label(title, text="Dashboard Overview", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title, text="Real-time project metrics and upcoming activity.", style="Muted.TLabel").pack(anchor="w")
        ttk.Button(header, text="+ New Project", style="Primary.TButton", command=self.add).pack(side="right")
        ttk.Button(header, text="Project Heads", style="Secondary.TButton", command=self.manage_heads).pack(side="right", padx=7)
        ttk.Button(header, text="Edit Project", style="Secondary.TButton", command=self.edit).pack(side="right")
        cards = ttk.Frame(self); cards.pack(fill="x", pady=(18, 14))
        self.contract_card, self.contract_value = metric_card(cards, "Total Contract Value", INK)
        self.paid_card, self.paid_value = metric_card(cards, "Paid Expenses", GREEN)
        self.outstanding_card, self.outstanding_value = metric_card(cards, "Outstanding", RED)
        self.progress_card, self.progress_value = metric_card(cards, "Overall Progress", ORANGE)
        for card in (self.contract_card, self.paid_card, self.outstanding_card, self.progress_card):
            card.pack(side="left", fill="x", expand=True, padx=(0, 9))
        lower = ttk.Panedwindow(self, orient="horizontal"); lower.pack(fill="both", expand=True)
        projects = ttk.Frame(lower, padding=(0, 0, 8, 0)); events = ttk.Frame(lower, padding=(8, 0, 0, 0))
        lower.add(projects, weight=3); lower.add(events, weight=2)
        ttk.Label(projects, text="Projects", style="Section.TLabel").pack(anchor="w", pady=(0, 5))
        self.tree = make_tree(projects, [
            ("name", "Project", 230), ("client", "Client", 190), ("contract", "Contract Value", 130),
            ("start", "Start", 100), ("target", "Target", 100),
        ])
        self.tree.bind("<Double-1>", self.choose)
        ttk.Label(events, text="Upcoming Events", style="Section.TLabel").pack(anchor="w", pady=(0, 5))
        self.events = make_tree(events, [("date", "Date", 95), ("event", "Event", 230), ("type", "Type", 90)])

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
        data = dialog(self, "Edit Project", self.FIELDS, initial)
        if not data:
            return
        try:
            if not data["name"]:
                raise ValueError("Project name is required.")
            self.db.execute(
                """UPDATE projects SET name=?,client=?,contract_value_cents=?,start_date=?,
                   target_date=?,notes=? WHERE id=?""",
                (data["name"], data["client"], cents(data["contract_value"]),
                 valid_date(data["start_date"]), valid_date(data["target_date"]),
                 data["notes"], self.project_id),
            )
            self.db.audit(self.project_id, "PROJECT_EDITED", data["name"])
            self.app.load_projects(self.project_id)
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def choose(self, _event=None):
        selected = self.tree.selection()
        if selected:
            self.app.select_project(int(selected[0]))

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self.events.delete(*self.events.get_children())
        for row in self.db.all("SELECT * FROM projects ORDER BY created_at DESC"):
            self.tree.insert("", "end", iid=row["id"], values=(
                row["name"], row["client"], money(row["contract_value_cents"]),
                row["start_date"], row["target_date"],
            ))
        if self.project_id:
            row = self.db.one("SELECT * FROM projects WHERE id=?", (self.project_id,))
            tasks = self.db.one(
                """SELECT COUNT(*) total, COALESCE(SUM(completed),0) done FROM tasks
                   WHERE phase_id IN (SELECT id FROM phases WHERE project_id=?)""", (self.project_id,)
            )
            paid = self.db.one(
                """SELECT COALESCE(SUM(p.amount_cents),0) total FROM payments p
                   JOIN expenses e ON e.id=p.expense_id WHERE e.project_id=? AND e.voided=0""",
                (self.project_id,),
            )["total"]
            progress = round(tasks["done"] * 100 / tasks["total"]) if tasks["total"] else 0
            outstanding = self.db.one(
                """SELECT COALESCE(SUM(e.total_cents),0)-COALESCE(SUM(x.paid),0) total
                   FROM expenses e LEFT JOIN (SELECT expense_id,SUM(amount_cents) paid FROM payments GROUP BY expense_id) x
                   ON x.expense_id=e.id WHERE e.project_id=? AND e.voided=0""", (self.project_id,)
            )["total"]
            self.contract_value.config(text=money(row["contract_value_cents"]))
            self.paid_value.config(text=money(paid))
            self.outstanding_value.config(text=money(outstanding))
            self.progress_value.config(text=f"{progress}%")
            for event in self.db.all(
                """SELECT * FROM calendar_events WHERE project_id=? AND completed=0 AND event_date>=?
                   ORDER BY event_date,event_time LIMIT 8""", (self.project_id, date.today().isoformat())):
                self.events.insert("", "end", iid=event["id"], values=(event["event_date"], event["title"], event["type"]))
        else:
            for label in (self.contract_value, self.paid_value, self.outstanding_value, self.progress_value):
                label.config(text="—")


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
        data = dialog(self, "Add Phase", [("name", "Phase name")])
        if data and data["name"]:
            order = self.db.one("SELECT COALESCE(MAX(sort_order),0)+1 n FROM phases WHERE project_id=?",
                                (self.project_id,))["n"]
            self.db.execute("INSERT INTO phases(project_id,name,sort_order) VALUES(?,?,?)",
                            (self.project_id, data["name"], order))
            self.db.audit(self.project_id, "PHASE_ADDED", data["name"])
            self.app.refresh_all()

    def remove_phase(self):
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
        ], initial)

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


class ExpensesTab(BaseTab):
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
        return dialog(self, "Expense", fields, initial)

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
               LEFT JOIN payments p ON p.expense_id=e.id WHERE e.id=? GROUP BY e.id""", (expense_id,)
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
        ], {"amount": money(balance), "payment_date": date.today().isoformat()})
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
               LEFT JOIN payments p ON p.expense_id=e.id
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
        data = dialog(self, "Contact", self.FIELDS)
        if data and data["name"]:
            self.db.execute(
                """INSERT INTO contacts(project_id,name,role,company,phone,email,address,notes)
                   VALUES(?,?,?,?,?,?,?,?)""", (self.project_id,) + tuple(data[k] for k, *_ in self.FIELDS)
            )
            self.app.refresh_all()

    def edit(self):
        record_id = self.selected_id(self.tree)
        if not record_id:
            return
        row = self.db.one("SELECT * FROM contacts WHERE id=?", (record_id,))
        data = dialog(self, "Contact", self.FIELDS, dict(row))
        if data:
            self.db.execute(
                """UPDATE contacts SET name=?,role=?,company=?,phone=?,email=?,address=?,notes=? WHERE id=?""",
                tuple(data[k] for k, *_ in self.FIELDS) + (record_id,),
            )
            self.app.refresh_all()

    def delete(self):
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


class RemittancesTab(BaseTab):
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
                      {"txn_date": date.today().isoformat()})
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
        data = dialog(self, "Edit Remittance Transaction", self.FIELDS, initial)
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
        data = dialog(self, "Calendar Event", self.FIELDS, {"event_date": date.today().isoformat()})
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
        record_id = self.selected_id(self.tree)
        if not record_id:
            return
        row = self.db.one("SELECT * FROM calendar_events WHERE id=?", (record_id,))
        data = dialog(self, "Calendar Event", self.FIELDS, dict(row))
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
        record_id = self.selected_id(self.tree)
        if record_id:
            self.db.execute("UPDATE calendar_events SET completed=1-completed WHERE id=?", (record_id,))
            self.app.refresh_all()

    def delete(self):
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

        shell = tk.Frame(self, bg=SURFACE); shell.pack(fill="both", expand=True)
        sidebar = tk.Frame(shell, bg=NAVY, width=225); sidebar.pack(side="left", fill="y"); sidebar.pack_propagate(False)
        brand = tk.Frame(sidebar, bg=NAVY, padx=20, pady=24); brand.pack(fill="x")
        tk.Label(brand, text="ConTracktor", bg=NAVY, fg=WHITE,
                 font=("Segoe UI", 20, "bold")).pack(anchor="w")
        tk.Label(brand, text="PRO SUITE", bg=NAVY, fg=ORANGE,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        nav = tk.Frame(sidebar, bg=NAVY, pady=18); nav.pack(fill="x")
        self.nav_buttons = {}
        nav_items = [("Dashboard", "▦"), ("Progress", "↗"), ("Expenses", "▣"),
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
        self.project_combo = ttk.Combobox(header, textvariable=self.project_var, state="readonly", width=33)
        self.project_combo.pack(side="left")
        self.project_combo.bind("<<ComboboxSelected>>", self.combo_selected)
        ttk.Button(header, text="+ New Project", style="Primary.TButton",
                   command=lambda: self.pages["Dashboard"].add()).pack(side="right")
        tools = tk.Menubutton(header, text="Tools ▾", bg=WHITE, fg=INK, relief="solid", bd=1,
                              font=("Segoe UI", 9, "bold"), padx=12, pady=6)
        tools_menu = tk.Menu(tools, tearoff=False)
        tools_menu.add_command(label="Export project to TXT", command=self.export_text)
        tools_menu.add_command(label="Backup SQLite database", command=self.backup)
        tools_menu.add_separator()
        tools_menu.add_command(label="Manage project heads", command=self.manage_current_heads)
        tools.configure(menu=tools_menu); tools.pack(side="right", padx=8)

        self.notebook = tk.Frame(body, bg=SURFACE)
        self.notebook.pack(fill="both", expand=True, padx=18, pady=16)
        self.tabs = [
            ("Dashboard", ProjectsTab(self)), ("Progress", ProgressTab(self)),
            ("Expenses", ExpensesTab(self)), ("Contacts", ContactsTab(self)),
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
        if page: page.tkraise(); page.refresh()
        for label, button in getattr(self, "nav_buttons", {}).items():
            active = label == name
            button.configure(bg=NAVY_ACTIVE if active else NAVY,
                             fg=WHITE if active else "#AAB4C5")

    def authorize(self, action: str, details: str):
        if not self.project_id:
            messagebox.showinfo(APP_TITLE, "Create or select a project first."); return None
        heads = self.db.all(
            "SELECT * FROM project_heads WHERE project_id=? AND active=1 ORDER BY name", (self.project_id,))
        if not heads:
            if messagebox.askyesno(APP_TITLE, "This project has no project head yet. Add one now?"):
                self.manage_current_heads()
                heads = self.db.all(
                    "SELECT * FROM project_heads WHERE project_id=? AND active=1 ORDER BY name", (self.project_id,))
        if not heads: return None
        win = HeadAuthorizationDialog(self, heads, action, details); self.wait_window(win)
        return win.result

    def manage_current_heads(self):
        if not self.project_id:
            messagebox.showinfo(APP_TITLE, "Create or select a project first."); return
        win = ManageHeadsDialog(self, self.db, self.project_id); self.wait_window(win)

    def load_projects(self, select_id=None):
        rows = self.db.all("SELECT id,name FROM projects ORDER BY name")
        self.project_lookup = {f"{r['name']}  [#{r['id']}]": r["id"] for r in rows}
        self.project_combo["values"] = list(self.project_lookup)
        if select_id:
            self.project_id = select_id
        elif self.project_id not in self.project_lookup.values():
            self.project_id = rows[0]["id"] if rows else None
        if self.project_id:
            label = next((name for name, pid in self.project_lookup.items() if pid == self.project_id), "")
            self.project_var.set(label)
        else:
            self.project_var.set("")
        self.refresh_all()

    def combo_selected(self, _event=None):
        self.select_project(self.project_lookup.get(self.project_var.get()))

    def select_project(self, project_id):
        self.project_id = project_id
        self.load_projects(project_id)

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
             """SELECT e.name,e.item,e.supplier,e.trade,e.expense_date,e.total_cents,e.voided,
                COALESCE(h.name,'Legacy / not recorded') authorized_by,
                COALESCE(SUM(pay.amount_cents),0) paid_cents FROM expenses e
                LEFT JOIN payments pay ON pay.expense_id=e.id
                LEFT JOIN project_heads h ON h.id=e.authorized_by_head_id WHERE e.project_id=?
                GROUP BY e.id ORDER BY e.expense_date,e.id"""),
            ("CONTACTS", "SELECT name,role,company,phone,email,address FROM contacts WHERE project_id=? ORDER BY name"),
            ("EMPLOYEES",
             "SELECT employee_no,name,position,class,pay_basis,rate_cents FROM employees WHERE project_id=? ORDER BY name"),
            ("ATTENDANCE",
             """SELECT e.name,a.clock_in,a.clock_out,a.hours,a.gross_cents,
                CASE WHEN a.committed_expense_id IS NULL THEN 'No' ELSE 'Yes' END committed
                FROM attendance a JOIN employees e ON e.id=a.employee_id
                WHERE e.project_id=? ORDER BY a.clock_in"""),
            ("REMITTANCES",
             """SELECT r.txn_date,r.type,r.amount_cents,r.purpose,r.care_of,r.signature,
                COALESCE(h.name,'Legacy / not recorded') authorized_by,r.voided
                FROM remittances r LEFT JOIN project_heads h ON h.id=r.authorized_by_head_id
                WHERE r.project_id=? ORDER BY r.txn_date"""),
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
