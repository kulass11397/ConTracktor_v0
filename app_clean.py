"""ConTracktor clean-interface launcher.

This module deliberately leaves ``app.py`` and the SQLite schema untouched.  It
reuses every existing workflow and calculation, then reorganizes the visible
controls and installs consistent mouse-wheel routing across the application.
"""

from __future__ import annotations

import sqlite3
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk

import app as core


# The original tree factory has a widget-local wheel binding.  The clean UI
# replaces it with one global router, so remove the local handler from every
# current and future ledger to prevent a single wheel notch scrolling twice.
_original_make_tree = core.make_tree


def _clean_make_tree(*args, **kwargs):
    tree = _original_make_tree(*args, **kwargs)
    tree.unbind("<MouseWheel>")
    return tree


core.make_tree = _clean_make_tree


def create_startup_backup(db_path):
    """Create a transaction-safe SQLite snapshot before the clean UI opens."""
    source_path = Path(db_path)
    if not source_path.exists():
        return None
    backup_dir = source_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    destination = backup_dir / (
        f"{source_path.stem}_before_clean_ui_{datetime.now():%Y%m%d_%H%M%S}{source_path.suffix}"
    )
    source = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return destination


class CleanContractorApp(core.ContractorApp):
    """Presentation-only refinement of the existing ConTracktor application."""

    SCROLL_WIDGETS = (tk.Canvas, tk.Text, tk.Listbox, ttk.Treeview)

    def __init__(self, db_path=core.DB_PATH):
        super().__init__(db_path)
        self.title(f"{core.APP_TITLE} — Clean Interface")
        self._configure_clean_styles()
        self._clean_global_header()
        self._clean_dashboard()
        self._clean_expenses()
        self._clean_inventory()
        self._clean_progress()
        self._clean_contacts()
        self._clean_payroll()
        self._clean_remittances()
        self._clean_calendar()
        self._install_mousewheel_routing()
        self.after_idle(self._refresh_clean_project_actions)

    # ------------------------------------------------------------------
    # Shared clean-interface building blocks
    # ------------------------------------------------------------------
    def _configure_clean_styles(self):
        style = ttk.Style(self)
        style.configure("CleanToolbar.TFrame", background=core.SURFACE)
        style.configure("CleanSubtle.TButton", padding=(8, 5), font=("Segoe UI", 9, "bold"))
        style.configure("CleanPrimary.TButton", padding=(11, 6), font=("Segoe UI", 9, "bold"))

    @staticmethod
    def _walk(root):
        for child in root.winfo_children():
            yield child
            yield from CleanContractorApp._walk(child)

    @classmethod
    def _buttons(cls, root, text=None):
        matches = []
        for widget in cls._walk(root):
            if not isinstance(widget, (ttk.Button, tk.Button)):
                continue
            try:
                label = str(widget.cget("text"))
            except tk.TclError:
                continue
            if text is None or label == text:
                matches.append(widget)
        return matches

    @classmethod
    def _first_button(cls, root, text):
        matches = cls._buttons(root, text)
        return matches[0] if matches else None

    @classmethod
    def _container_with_labels(cls, root, required_labels):
        required = set(required_labels)
        for candidate in root.winfo_children():
            labels = set()
            for widget in cls._walk(candidate):
                if isinstance(widget, (ttk.Label, tk.Label)):
                    try:
                        labels.add(str(widget.cget("text")))
                    except tk.TclError:
                        pass
            if required.issubset(labels):
                return candidate
        return None

    @staticmethod
    def _forget(widget):
        if widget is None:
            return
        manager = widget.winfo_manager()
        if manager == "pack":
            widget.pack_forget()
        elif manager == "grid":
            widget.grid_remove()
        elif manager == "place":
            widget.place_forget()

    def _action_menu(self, parent, label, items, *, side="left", padx=(0, 6), disabled=False):
        button = tk.Menubutton(
            parent,
            text=f"{label} ▾",
            bg=core.WHITE,
            fg=core.INK,
            activebackground="#EEF2F7",
            activeforeground=core.INK,
            relief="solid",
            bd=1,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=5,
            anchor="w",
        )
        menu = tk.Menu(button, tearoff=False)
        for item in items:
            if item is None:
                menu.add_separator()
            else:
                item_label, command = item
                menu.add_command(label=item_label, command=command)
        button.configure(menu=menu, state="disabled" if disabled else "normal")
        button.pack(side=side, padx=padx)
        button.clean_menu = menu
        return button

    @staticmethod
    def _selection_controls(tree, *controls):
        def update(_event=None):
            state = "normal" if tree.selection() else "disabled"
            for control in controls:
                control.configure(state=state)
        tree.bind("<<TreeviewSelect>>", update, add="+")
        update()

    def _collapsible_section(self, parent, frames, *, title="Filters", summary=None,
                             before=None, collapsed=True):
        frames = [frame for frame in frames if frame is not None]
        if not frames:
            return None
        toolbar = ttk.Frame(parent, style="CleanToolbar.TFrame")
        pack_options = {"fill": "x", "pady": (2, 4)}
        if before is not None:
            pack_options["before"] = before
        else:
            pack_options["before"] = frames[0]
        toolbar.pack(**pack_options)
        summary_var = tk.StringVar(value=summary or "Open to refine the ledger")
        toggle_text = tk.StringVar()
        visible = tk.BooleanVar(value=not collapsed)

        ttk.Label(toolbar, textvariable=summary_var, style="Muted.TLabel").pack(
            side="left", fill="x", expand=True
        )

        def show_frames():
            anchor = toolbar
            for index, frame in enumerate(frames):
                frame.pack(fill="x", after=anchor, pady=(2 if index else 0, 0))
                anchor = frame

        def hide_frames():
            for frame in frames:
                frame.pack_forget()

        def toggle():
            visible.set(not visible.get())
            if visible.get():
                show_frames()
            else:
                hide_frames()
            toggle_text.set(f"Hide {title.lower()} ▴" if visible.get() else f"Show {title.lower()} ▾")

        ttk.Button(toolbar, textvariable=toggle_text, command=toggle,
                   style="CleanSubtle.TButton").pack(side="right")
        if collapsed:
            hide_frames()
        toggle_text.set(f"Hide {title.lower()} ▴" if visible.get() else f"Show {title.lower()} ▾")
        toolbar.summary_var = summary_var
        toolbar.toggle = toggle
        return toolbar

    @staticmethod
    def _clean_metrics(parent, primary_cards, detail_cards):
        """Show four principal figures and keep secondary values collapsible."""
        all_cards = list(primary_cards) + list(detail_cards)
        for card in all_cards:
            card.grid_forget()
        for column in range(6):
            parent.columnconfigure(column, weight=0, uniform="")
        for column, card in enumerate(primary_cards):
            parent.columnconfigure(column, weight=1, uniform="clean_metric_cards")
            card.grid(row=0, column=column, sticky="nsew", padx=(0, 8))
        for index, card in enumerate(detail_cards):
            card.grid(row=1, column=index * 2, columnspan=2, sticky="nsew",
                      padx=(0, 8), pady=(8, 0))
            card.grid_remove()

    def _metric_details_toggle(self, page, cards_parent, detail_cards, *, before):
        row = ttk.Frame(page)
        row.pack(fill="x", before=before, pady=(0, 5))
        shown = tk.BooleanVar(value=False)
        label = tk.StringVar(value="Show financial breakdown ▾")

        def toggle():
            shown.set(not shown.get())
            for card in detail_cards:
                if shown.get():
                    card.grid()
                else:
                    card.grid_remove()
            label.set("Hide financial breakdown ▴" if shown.get() else "Show financial breakdown ▾")
            self.after_idle(lambda: self.set_page_content_height(
                page.requested_page_height() if hasattr(page, "requested_page_height") else 1000
            ))

        ttk.Button(row, textvariable=label, command=toggle,
                   style="CleanSubtle.TButton").pack(side="right")
        ttk.Label(row, text="Primary operating figures are shown above.",
                  style="Muted.TLabel").pack(side="left")

    # ------------------------------------------------------------------
    # Global header and page-specific control consolidation
    # ------------------------------------------------------------------
    def _clean_global_header(self):
        header = self.project_combo.master
        for widget in self._walk(self):
            if isinstance(widget, tk.Label):
                try:
                    if str(widget.cget("text")) == "PRO SUITE":
                        widget.configure(text="PRO SUITE • CLEAN UI")
                        break
                except tk.TclError:
                    pass
        for button in (self.edit_project_button, self.project_heads_button,
                       self.complete_project_button):
            self._forget(button)
        self.project_actions = self._action_menu(header, "Project Actions", [
            ("Edit selected project", lambda: self.pages["Dashboard"].edit()),
            ("Manage project heads", self.manage_current_heads),
            ("Project-head registry", self.manage_head_registry),
            None,
            ("Complete selected project", lambda: self.pages["Dashboard"].complete_project()),
        ], side="left", padx=(10, 0), disabled=True)
        self.project_combo.bind("<<ComboboxSelected>>",
                                lambda _event: self.after_idle(self._refresh_clean_project_actions),
                                add="+")

    def load_projects(self, select_id=None):
        result = super().load_projects(select_id)
        self.after_idle(self._refresh_clean_project_actions)
        return result

    def _refresh_clean_project_actions(self):
        if not hasattr(self, "project_actions"):
            return
        active = bool(self.project_id)
        self.project_actions.configure(state="normal" if active else "disabled")

    def _clean_dashboard(self):
        page = self.pages["Dashboard"]
        self._forget(getattr(page, "add_project_head_button", None))

    def _clean_expenses(self):
        page = self.pages["Expenses"]
        cards = page.total_card.master
        primary = (page.total_card, page.payments_card, page.cash_card, page.budget_card)
        detail = (page.deposit_card, page.contract_card)
        self._clean_metrics(cards, primary, detail)
        self._metric_details_toggle(page, cards, detail, before=page.reconciliation_label)

        filters = self._container_with_labels(
            page.ledger_page, ("Project", "Status", "Verification", "MOP", "Area", "Supplier", "Search")
        )
        dates = self._container_with_labels(page.ledger_page, ("Funding source", "Expense date"))
        controls_button = self._first_button(page.ledger_page, "Edit (all heads)")
        controls = controls_button.master if controls_button else None
        filter_bar = self._collapsible_section(
            page.ledger_page, (filters, dates), title="Filters",
            summary="All expense filters and date controls", before=filters, collapsed=True,
        )

        if controls:
            for button in self._buttons(controls):
                self._forget(button)
            selected_actions = self._action_menu(controls, "Selected Expense", [
                ("View details", lambda: page.show_expense_details(int(page.tree.selection()[0]))
                 if page.tree.selection() else None),
                ("Edit expense (all heads)", page.edit),
                ("Record payment", page.pay),
                ("Verify selected", page.verify_selected),
                ("Batch verify all unverified", page.verify_all_unverified),
                None,
                ("Void / restore", page.void),
            ], disabled=True)
            self._action_menu(controls, "Reports", [("Export filtered PDF", page.export_pdf)],
                              side="right", padx=(6, 0))
            self._selection_controls(page.tree, selected_actions)

        cash_allocate = self._first_button(page.cash_page, "+ Allocate Withdrawal")
        if cash_allocate:
            toolbar = cash_allocate.master
            edit_button = self._first_button(toolbar, "Edit Selected Allocation")
            surrender_button = self._first_button(toolbar, "Surrender / Close")
            deposit_button = self._first_button(toolbar, "Deposit All Surrendered")
            return_button = self._first_button(toolbar, "Void / Restore Cash Return")
            for button in (edit_button, surrender_button, deposit_button, return_button):
                self._forget(button)
            cash_actions = self._action_menu(toolbar, "Selected Allocation", [
                ("Edit selected allocation", page.edit_cash_allocation),
                ("Surrender / close allocation", page.surrender_cash_allocation),
            ], side="right", padx=(0, 6))
            self._action_menu(toolbar, "Cash Returns", [
                ("Deposit all surrendered cash", page.deposit_surrendered_cash),
                ("Void / restore selected surrender or redeposit", page.void_restore_cash_return),
            ], side="right", padx=(0, 6))
            self._selection_controls(page.allocation_tree, cash_actions)

        if filter_bar:
            original_refresh = page.refresh
            def clean_refresh(*args, **kwargs):
                result = original_refresh(*args, **kwargs)
                parts = [page.project_selector.display_text(), page.status_selector.display_text()]
                if page.filter_var.get().strip():
                    parts.append(f"Search: {page.filter_var.get().strip()}")
                filter_bar.summary_var.set(" · ".join(parts))
                return result
            page.refresh = clean_refresh

    def _clean_inventory(self):
        page = self.pages["Inventory"]
        if not page.action_buttons:
            return
        actions = page.action_buttons[0].master
        for button in page.action_buttons:
            self._forget(button)
        ttk.Button(actions, text="+ Register Material / Tool", style="Primary.TButton",
                   command=page.register_item).pack(side="left", padx=(0, 6))
        self._action_menu(actions, "Inventory Actions", [
            ("Edit selected item", page.edit_item),
            ("Edit selected transaction", page.edit_inventory_transaction),
            None,
            ("Restock consumable", page.restock),
            ("Issue consumable", page.consume),
            ("Borrow tool", page.borrow),
            ("Return tool", page.return_tool),
        ])
        filters = self._container_with_labels(page, ("Type", "Search"))
        if filters:
            self._collapsible_section(page, (filters,), title="Filters",
                                      summary="Inventory type and search", collapsed=True)

    def _clean_progress(self):
        page = self.pages["Progress"]
        add_phase = self._first_button(page, "Add Phase")
        if not add_phase:
            return
        controls = add_phase.master
        for button in self._buttons(controls):
            self._forget(button)
        ttk.Button(controls, text="+ Add Task", style="Primary.TButton",
                   command=page.add_task).pack(side="left", padx=(10, 6))
        self._action_menu(controls, "Phase / Task Actions", [
            ("Add phase", page.add_phase),
            ("Remove selected phase", page.remove_phase),
            None,
            ("Edit selected task", page.edit_task),
            ("Toggle task complete", page.toggle),
        ])

    def _clean_contacts(self):
        page = self.pages["Contacts"]
        add_button = self._first_button(page, "＋ Add Contact")
        if not add_button:
            return
        bar = add_button.master
        for button in self._buttons(bar):
            self._forget(button)
        ttk.Button(bar, text="+ Add Contact", style="Primary.TButton",
                   command=page.add).pack(side="left", padx=(0, 6))
        selected = self._action_menu(bar, "Selected Contact", [
            ("Edit contact", page.edit),
            ("Delete contact", page.delete),
        ], disabled=True)
        self._selection_controls(page.tree, selected)

    def _clean_payroll(self):
        page = self.pages["Payroll"]
        add_button = self._first_button(page, "+ Add Employee")
        if not add_button:
            return
        actions = add_button.master
        for button in self._buttons(actions):
            self._forget(button)
        self._action_menu(actions, "+ Add Employee", [
            ("Create a new employee", page.add_employee),
            ("Add an existing employee to this project", page.deploy_existing_employee),
        ])
        employee_actions = self._action_menu(actions, "Employee Actions", [
            ("View employee profile", lambda: page.open_employee_profile(None)),
            ("Edit employee", page.edit_employee),
            ("Archive employee", page.archive_employee),
        ], disabled=True)
        self._action_menu(actions, "Attendance Actions", [
            ("Batch attendance", page.batch_attendance),
            ("Close daily attendance", page.close_daily_attendance),
            ("Edit attendance / pay", page.edit_selected_attendance),
        ])
        self._selection_controls(page.employees, employee_actions)

    def _clean_remittances(self):
        page = self.pages["Remittances"]
        header_add = self._first_button(page, "+ Add Transaction")
        if header_add:
            header = header_add.master
            for text in ("+ Add Transaction", "+ Enroll Bank", "Transfer Between Banks"):
                self._forget(self._first_button(header, text))
            ttk.Button(header, text="+ New Transaction", style="Primary.TButton",
                       command=page.add).pack(side="right", padx=(6, 0))
            self._action_menu(header, "Bank Actions", [
                ("Enroll bank account", page.enroll_bank),
                ("Transfer between banks", page.transfer_between_banks),
                ("Edit selected bank", page.edit_bank),
                None,
                ("Edit selected transaction", page.edit),
                ("Void / restore transaction", page.void),
            ], side="right", padx=(6, 0))

        for text in ("Edit Selected Bank", "Edit Transaction", "Void / Restore"):
            self._forget(self._first_button(page, text))

        cards = page.deposit_card.master
        primary = (page.deposit_card, page.withdraw_card, page.bank_card, page.budget_card)
        detail = (page.transfer_card, page.contract_card)
        self._clean_metrics(cards, primary, detail)
        self._metric_details_toggle(page, cards, detail, before=page.budget_note)

        filters = self._container_with_labels(page, ("Project", "Bank account"))
        extra = self._container_with_labels(page, ("Type", "Status", "Reference / Search"))
        filter_bar = self._collapsible_section(
            page, (filters, extra), title="Filters",
            summary="All projects · all banks · all transactions", collapsed=True,
        )
        if filter_bar:
            original_refresh = page.refresh
            def clean_refresh(*args, **kwargs):
                result = original_refresh(*args, **kwargs)
                parts = [page.project_filter.get(), page.bank_filter.get(),
                         page.transaction_type_filter.get()]
                if page.remit_search.get().strip():
                    parts.append(f"Search: {page.remit_search.get().strip()}")
                filter_bar.summary_var.set(" · ".join(parts))
                return result
            page.refresh = clean_refresh

    def _clean_calendar(self):
        page = self.pages["Calendar"]
        add_button = self._first_button(page, "+ Event")
        if not add_button:
            return
        header = add_button.master
        for text in ("Edit", "Delete"):
            self._forget(self._first_button(header, text))
        selected = self._action_menu(header, "Selected Event", [
            ("Edit event", page.edit),
            ("Mark complete / reopen", page.toggle),
            ("Delete event", page.delete),
        ], side="right", padx=(6, 0), disabled=True)
        self._selection_controls(page.tree, selected)

    # ------------------------------------------------------------------
    # Application-wide mouse-wheel routing
    # ------------------------------------------------------------------
    def _install_mousewheel_routing(self):
        self.bind_all("<MouseWheel>", self._route_mousewheel, add="+")
        self.bind_all("<Shift-MouseWheel>", self._route_shift_mousewheel, add="+")
        self.bind_all("<Button-4>", lambda event: self._route_linux_wheel(event, -1), add="+")
        self.bind_all("<Button-5>", lambda event: self._route_linux_wheel(event, 1), add="+")

    @staticmethod
    def _axis_view(widget, horizontal=False):
        try:
            view = widget.xview() if horizontal else widget.yview()
            if len(view) == 2:
                return float(view[0]), float(view[1])
        except (AttributeError, tk.TclError, TypeError, ValueError):
            pass
        return 0.0, 1.0

    @classmethod
    def _can_move(cls, widget, units, horizontal=False):
        first, last = cls._axis_view(widget, horizontal)
        if last - first >= 0.999:
            return False
        return first > 0.0001 if units < 0 else last < 0.9999

    @classmethod
    def _nearest_scrollable(cls, widget, units, horizontal=False):
        current = widget
        while current is not None:
            if isinstance(current, cls.SCROLL_WIDGETS) and cls._can_move(current, units, horizontal):
                return current
            try:
                parent_name = current.winfo_parent()
                current = current._nametowidget(parent_name) if parent_name else None
            except (KeyError, tk.TclError):
                current = None
        return None

    @classmethod
    def _visible_scroll_candidates(cls, root, units, horizontal=False):
        candidates = []
        for widget in cls._walk(root):
            if not isinstance(widget, cls.SCROLL_WIDGETS) or not widget.winfo_ismapped():
                continue
            if not cls._can_move(widget, units, horizontal):
                continue
            try:
                area = widget.winfo_width() * widget.winfo_height()
            except tk.TclError:
                area = 0
            candidates.append((area, widget))
        return [widget for _area, widget in sorted(candidates, key=lambda item: item[0], reverse=True)]

    def _scroll_target(self, event, units, horizontal=False):
        try:
            under_pointer = self.winfo_containing(event.x_root, event.y_root)
        except tk.TclError:
            under_pointer = None
        under_pointer = under_pointer or event.widget
        target = self._nearest_scrollable(under_pointer, units, horizontal)
        if target is not None:
            return target

        try:
            top = under_pointer.winfo_toplevel()
        except tk.TclError:
            top = self

        # On the main window, wheel movement outside a ledger scrolls the full
        # page.  This makes cards, filters and ledger headings reachable without
        # placing the pointer over the narrow scrollbar.
        if top == self and self._can_move(self.page_canvas, units, horizontal):
            return self.page_canvas

        candidates = self._visible_scroll_candidates(top, units, horizontal)
        return candidates[0] if candidates else None

    def _perform_scroll(self, event, units, horizontal=False):
        target = self._scroll_target(event, units, horizontal)
        if target is None:
            return None
        try:
            if horizontal:
                target.xview_scroll(units, "units")
            else:
                target.yview_scroll(units, "units")
            return "break"
        except (AttributeError, tk.TclError):
            return None

    def _route_mousewheel(self, event):
        if not event.delta:
            return None
        units = -max(1, abs(int(event.delta / 120))) if event.delta > 0 else max(1, abs(int(event.delta / 120)))
        return self._perform_scroll(event, units, horizontal=False)

    def _route_shift_mousewheel(self, event):
        if not event.delta:
            return None
        units = -max(1, abs(int(event.delta / 120))) if event.delta > 0 else max(1, abs(int(event.delta / 120)))
        return self._perform_scroll(event, units, horizontal=True)

    def _route_linux_wheel(self, event, units):
        return self._perform_scroll(event, units, horizontal=False)


if __name__ == "__main__":
    core.APP_DIR.mkdir(parents=True, exist_ok=True)
    create_startup_backup(core.DB_PATH)
    CleanContractorApp().mainloop()
