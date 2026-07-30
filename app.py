"""Contractor Project Tracker - local Tkinter + SQLite prototype.

Run with: python app.py
No third-party packages are required.
"""

from __future__ import annotations

import hashlib
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
        self.conn.commit()

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


class ProjectsTab(BaseTab):
    FIELDS = [
        ("name", "Project name"), ("client", "Client"), ("contract_value", "Contract value"),
        ("start_date", "Start date (YYYY-MM-DD)"), ("target_date", "Target date (YYYY-MM-DD)"),
        ("notes", "Notes"),
    ]

    def __init__(self, app):
        super().__init__(app)
        welcome = ttk.Label(self, text="Welcome — start by creating a project", style="Title.TLabel")
        welcome.pack(anchor="w")
        ttk.Label(
            self, text="Each project keeps its own phases, expenses, people, payroll, funds and calendar."
        ).pack(anchor="w", pady=(2, 12))
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Button(bar, text="＋ Create Project", command=self.add).pack(side="left")
        ttk.Button(bar, text="Edit Project", command=self.edit).pack(side="left", padx=6)
        self.summary = ttk.Label(self, text="")
        self.summary.pack(anchor="w", pady=14)
        self.tree = make_tree(self, [
            ("name", "Project", 230), ("client", "Client", 190), ("contract", "Contract Value", 130),
            ("start", "Start", 100), ("target", "Target", 100),
        ])
        self.tree.bind("<Double-1>", self.choose)

    def add(self):
        data = dialog(self, "Create Project", self.FIELDS, {"start_date": date.today().isoformat()})
        if not data:
            return
        try:
            if not data["name"]:
                raise ValueError("Project name is required.")
            project_id = self.db.create_project(data)
            self.app.load_projects(project_id)
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror(APP_TITLE, str(exc))

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
            self.summary.config(
                text=f"Selected: {row['name']}     Task progress: {progress}%     Paid expenses: {money(paid)}"
            )
        else:
            self.summary.config(text="No project selected.")


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

    def save_values(self, data, expense_id=None):
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
                   unit_price_cents,total_cents,phase_id,area,trade,expense_date,due_date,invoice_no,notes)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (self.project_id,) + values
            )
            self.db.audit(self.project_id, "EXPENSE_ADDED", data["name"])

    def add(self):
        if not self.require_project():
            return
        data = self.expense_form({"qty": "1", "expense_date": date.today().isoformat()})
        if data:
            try:
                self.save_values(data)
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
        if expense_id:
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
            """SELECT e.*,COALESCE(ph.name,'') phase,COALESCE(SUM(p.amount_cents),0) paid
               FROM expenses e LEFT JOIN phases ph ON ph.id=e.phase_id
               LEFT JOIN payments p ON p.expense_id=e.id
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
        clock = ttk.LabelFrame(self, text="Employee time clock", padding=8)
        clock.pack(fill="x", pady=6)
        ttk.Label(clock, text="Employee no.").pack(side="left")
        self.employee_no = tk.StringVar()
        ttk.Entry(clock, textvariable=self.employee_no, width=16).pack(side="left", padx=5)
        ttk.Label(clock, text="PIN").pack(side="left")
        self.pin = tk.StringVar()
        ttk.Entry(clock, textvariable=self.pin, show="•", width=12).pack(side="left", padx=5)
        ttk.Button(clock, text="Time In / Time Out", command=self.clock).pack(side="left", padx=5)
        self.summary = ttk.Label(clock)
        self.summary.pack(side="right")
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

    def clock(self):
        if not self.require_project():
            return
        employee = self.db.one("SELECT * FROM employees WHERE project_id=? AND employee_no=? AND active=1",
                               (self.project_id, self.employee_no.get().strip()))
        if not employee or not verify_pin(self.pin.get(), employee["pin_salt"], employee["pin_hash"]):
            messagebox.showerror(APP_TITLE, "Employee number or PIN is incorrect.")
            return
        open_row = self.db.one("SELECT * FROM attendance WHERE employee_id=? AND clock_out=''",
                               (employee["id"],))
        now = datetime.now()
        if not open_row:
            self.db.execute("INSERT INTO attendance(employee_id,clock_in) VALUES(?,?)",
                            (employee["id"], now.isoformat(timespec="seconds")))
            messagebox.showinfo(APP_TITLE, f"Time in recorded for {employee['name']} at {now:%I:%M %p}.")
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
                APP_TITLE, f"Time out recorded for {employee['name']}.\nHours: {hours}\nGross: {money(gross)}"
            )
        self.pin.set("")
        self.app.refresh_all()

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
        batch = datetime.now().strftime("%Y%m%d-%H%M%S")
        with self.db.conn:
            cur = self.db.conn.execute(
                """INSERT INTO expenses(project_id,name,item,supplier,qty,unit,unit_price_cents,
                   total_cents,trade,expense_date,due_date,payroll_batch,notes)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self.project_id, f"Payroll {date.today():%Y-%m-%d}", "Closed attendance payroll",
                 "Payroll", "1", "batch", total, total, "Labor", date.today().isoformat(),
                 date.today().isoformat(), batch, f"{len(rows)} attendance record(s)"),
            )
            expense_id = cur.lastrowid
            self.db.conn.executemany(
                "UPDATE attendance SET committed_expense_id=? WHERE id=?",
                [(expense_id, r["id"]) for r in rows],
            )
        self.db.audit(self.project_id, "PAYROLL_COMMITTED", f"{batch}: {money(total)}")
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
            ("purpose", "Purpose", 210), ("care", "C/O", 150), ("signature", "Signature", 170),
            ("status", "Status", 70),
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
                self.db.execute(
                    """INSERT INTO remittances(project_id,type,amount_cents,txn_date,purpose,
                       care_of,signature,notes) VALUES(?,?,?,?,?,?,?,?)""",
                    (self.project_id, data["type"], amount, valid_date(data["txn_date"], True),
                     data["purpose"], data["care_of"], data["signature"], data["notes"]),
                )
                self.db.audit(self.project_id, "REMITTANCE_ADDED", f"{data['type']} {money(amount)}")
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
        if record_id:
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
        rows = self.db.all("SELECT * FROM remittances WHERE project_id=? ORDER BY txn_date DESC,id DESC",
                           (self.project_id,))
        deposits = withdrawals = 0
        for row in rows:
            if not row["voided"]:
                if row["type"] == "Deposit":
                    deposits += row["amount_cents"]
                else:
                    withdrawals += row["amount_cents"]
            self.tree.insert("", "end", iid=row["id"], values=(
                row["txn_date"], row["type"], money(row["amount_cents"]), row["purpose"],
                row["care_of"], row["signature"], "VOID" if row["voided"] else "Active",
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
        ("type", "Type", ["Appointment", "Reminder", "Deadline"]),
        ("title", "Title"), ("event_date", "Date (YYYY-MM-DD)"),
        ("event_time", "Time (e.g. 09:30 AM)"), ("notes", "Notes"),
    ]

    def __init__(self, app):
        super().__init__(app)
        ttk.Label(self, text="Calendar planner", style="Title.TLabel").pack(anchor="w")
        bar = ttk.Frame(self); bar.pack(fill="x", pady=(10, 0))
        ttk.Button(bar, text="＋ Add Event", command=self.add).pack(side="left")
        ttk.Button(bar, text="Edit", command=self.edit).pack(side="left", padx=5)
        ttk.Button(bar, text="✓ Toggle Complete", command=self.toggle).pack(side="left")
        ttk.Button(bar, text="Delete", command=self.delete).pack(side="left", padx=5)
        self.tree = make_tree(self, [
            ("done", "Done", 55), ("date", "Date", 100), ("time", "Time", 100),
            ("type", "Type", 110), ("title", "Title", 260), ("notes", "Notes", 300),
        ])

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
        if self.project_id:
            for row in self.db.all(
                "SELECT * FROM calendar_events WHERE project_id=? ORDER BY event_date,event_time,id",
                (self.project_id,),
            ):
                self.tree.insert("", "end", iid=row["id"], values=(
                    "✓" if row["completed"] else "", row["event_date"], row["event_time"],
                    row["type"], row["title"], row["notes"],
                ))


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
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("TButton", padding=(8, 5))
        header = ttk.Frame(self, padding=(12, 9))
        header.pack(fill="x")
        ttk.Label(header, text=APP_TITLE, font=("Segoe UI", 17, "bold")).pack(side="left")
        ttk.Label(header, text="Current project:").pack(side="left", padx=(28, 5))
        self.project_var = tk.StringVar()
        self.project_combo = ttk.Combobox(header, textvariable=self.project_var, state="readonly", width=33)
        self.project_combo.pack(side="left")
        self.project_combo.bind("<<ComboboxSelected>>", self.combo_selected)
        ttk.Button(header, text="Export TXT", command=self.export_text).pack(side="right")
        ttk.Button(header, text="Backup Database", command=self.backup).pack(side="right", padx=6)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.tabs = [
            ("Projects", ProjectsTab(self)), ("Progress", ProgressTab(self)),
            ("Expenses", ExpensesTab(self)), ("Contacts", ContactsTab(self)),
            ("Attendance / Payroll", PayrollTab(self)), ("Remittances", RemittancesTab(self)),
            ("Calendar", CalendarTab(self)),
        ]
        for label, tab in self.tabs:
            self.notebook.add(tab, text=label)
        self.load_projects()

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
        if not DB_PATH.exists():
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
            ("PHASES & TASKS",
             """SELECT p.name phase,t.milestone,t.name,t.deadline,t.completed FROM phases p
                LEFT JOIN tasks t ON t.phase_id=p.id WHERE p.project_id=?
                ORDER BY p.sort_order,t.deadline,t.id"""),
            ("EXPENSES",
             """SELECT e.name,e.item,e.supplier,e.trade,e.expense_date,e.total_cents,e.voided,
                COALESCE(SUM(pay.amount_cents),0) paid_cents FROM expenses e
                LEFT JOIN payments pay ON pay.expense_id=e.id WHERE e.project_id=?
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
             """SELECT txn_date,type,amount_cents,purpose,care_of,signature,voided
                FROM remittances WHERE project_id=? ORDER BY txn_date"""),
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
