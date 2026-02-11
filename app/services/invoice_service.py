from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.db_lock import db_connection, db_lock
from app.core.paths import app_dir
from app.services.backup_sender import send_backup
from app.services.purchase_service import PurchaseLine


@dataclass
class InvoiceSummary:
    invoice_id: int
    invoice_type: str
    created_at: str
    total_lines: int
    total_qty: int
    total_amount: float
    invoice_name: str | None
    admin_id: int | None
    admin_username: str | None


@dataclass
class InvoiceLine:
    product_name: str
    price: float
    quantity: int
    line_total: float
    cost_price: float = 0.0


@dataclass
class SalesLine:
    product_name: str
    price: float
    quantity: int
    cost_price: float


@dataclass
class ProductRenameResult:
    updated_lines: int = 0
    updated_invoice_ids: list[int] = field(default_factory=list)


class InvoiceService:
    def __init__(
        self,
        db_path: Path | None = None,
        backup_dir: Path | None = None,
    ) -> None:
        if db_path is None:
            db_path = app_dir() / "invoices.db"
        self.db_path = db_path
        self.backup_dir = backup_dir
        self._schema_signature: tuple[int, int, int] | None = None
        self._init_db()

    def _connect(self):
        return db_connection(self.db_path, row_factory=sqlite3.Row)

    def _db_signature(self) -> tuple[int, int, int] | None:
        try:
            stat = self.db_path.stat()
        except FileNotFoundError:
            return None
        return (stat.st_ino, stat.st_size, stat.st_mtime_ns)

    def _ensure_schema(self) -> None:
        current = self._db_signature()
        if current != self._schema_signature:
            self._init_db()
            self._schema_signature = self._db_signature()

    def _backup_db(self) -> None:
        if not self.db_path.exists():
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"invoices_backup_{timestamp}{self.db_path.suffix}"
        target_dir = self.backup_dir if self.backup_dir else self.db_path.parent
        backup_path = target_dir / backup_name
        with db_lock():
            shutil.copy2(self.db_path, backup_path)

    def set_backup_dir(self, backup_dir: Path | None) -> None:
        self.backup_dir = backup_dir

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS invoices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    total_lines INTEGER NOT NULL,
                    total_qty INTEGER NOT NULL,
                    total_amount REAL NOT NULL,
                    invoice_name TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS invoice_lines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice_id INTEGER NOT NULL,
                    product_name TEXT NOT NULL,
                    price REAL NOT NULL,
                    quantity INTEGER NOT NULL,
                    line_total REAL NOT NULL,
                    cost_price REAL NOT NULL DEFAULT 0,
                    FOREIGN KEY (invoice_id)
                        REFERENCES invoices(id)
                        ON DELETE CASCADE
                )
                """
            )
            columns = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(invoice_lines)"
                ).fetchall()
            }
            if "cost_price" not in columns:
                conn.execute(
                    "ALTER TABLE invoice_lines "
                    "ADD COLUMN cost_price REAL NOT NULL DEFAULT 0"
                )
            invoice_columns = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(invoices)"
                ).fetchall()
            }
            if "invoice_name" not in invoice_columns:
                conn.execute(
                    "ALTER TABLE invoices ADD COLUMN invoice_name TEXT"
                )
            if "admin_id" not in invoice_columns:
                conn.execute("ALTER TABLE invoices ADD COLUMN admin_id INTEGER")
            if "admin_username" not in invoice_columns:
                conn.execute(
                    "ALTER TABLE invoices ADD COLUMN admin_username TEXT"
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_invoice_lines_invoice_id "
                "ON invoice_lines(invoice_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_invoices_created_at "
                "ON invoices(created_at)"
            )
        self._schema_signature = self._db_signature()

    def create_purchase_invoice(
        self,
        lines: list[PurchaseLine],
        invoice_name: str | None = None,
        admin_id: int | None = None,
        admin_username: str | None = None,
    ) -> int:
        self._ensure_schema()
        total_qty = sum(line.quantity for line in lines)
        total_amount = sum(line.price * line.quantity for line in lines)
        created_at = datetime.now(ZoneInfo("Asia/Tehran")).isoformat(
            timespec="seconds"
        )

        self._backup_db()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO invoices (
                    invoice_type,
                    created_at,
                    total_lines,
                    total_qty,
                    total_amount,
                    invoice_name,
                    admin_id,
                    admin_username
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "purchase",
                    created_at,
                    len(lines),
                    total_qty,
                    total_amount,
                    invoice_name,
                    admin_id,
                    admin_username,
                ),
            )
            invoice_id = int(cursor.lastrowid)

            line_rows = [
                (
                    invoice_id,
                    line.product_name,
                    float(line.price),
                    int(line.quantity),
                    float(line.price * line.quantity),
                    float(line.price),
                )
                for line in lines
            ]
            conn.executemany(
                """
                INSERT INTO invoice_lines (
                    invoice_id,
                    product_name,
                    price,
                    quantity,
                    line_total,
                    cost_price
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                line_rows,
            )
        send_backup(
            reason="invoice_purchase_created",
            admin_username=admin_username,
        )
        return invoice_id

    def create_sales_invoice(
        self,
        lines: list[SalesLine],
        invoice_name: str | None = None,
        admin_id: int | None = None,
        admin_username: str | None = None,
        invoice_type: str = "sales",
    ) -> int:
        self._ensure_schema()
        total_qty = sum(line.quantity for line in lines)
        total_amount = sum(line.price * line.quantity for line in lines)
        created_at = datetime.now(ZoneInfo("Asia/Tehran")).isoformat(
            timespec="seconds"
        )

        self._backup_db()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO invoices (
                    invoice_type,
                    created_at,
                    total_lines,
                    total_qty,
                    total_amount,
                    invoice_name,
                    admin_id,
                    admin_username
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice_type,
                    created_at,
                    len(lines),
                    total_qty,
                    total_amount,
                    invoice_name,
                    admin_id,
                    admin_username,
                ),
            )
            invoice_id = int(cursor.lastrowid)

            line_rows = [
                (
                    invoice_id,
                    line.product_name,
                    float(line.price),
                    int(line.quantity),
                    float(line.price * line.quantity),
                    float(line.cost_price),
                )
                for line in lines
            ]
            conn.executemany(
                """
                INSERT INTO invoice_lines (
                    invoice_id,
                    product_name,
                    price,
                    quantity,
                    line_total,
                    cost_price
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                line_rows,
            )
        send_backup(
            reason="invoice_sales_created",
            admin_username=admin_username,
        )
        return invoice_id

    def list_invoices(
        self, limit: int = 200, offset: int = 0
    ) -> list[InvoiceSummary]:
        self._ensure_schema()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    invoice_type,
                    created_at,
                    total_lines,
                    total_qty,
                    total_amount,
                    invoice_name,
                    admin_id,
                    admin_username
                FROM invoices
                ORDER BY id DESC
                LIMIT ?
                OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [
            InvoiceSummary(
                invoice_id=row["id"],
                invoice_type=row["invoice_type"],
                created_at=row["created_at"],
                total_lines=row["total_lines"],
                total_qty=row["total_qty"],
                total_amount=row["total_amount"],
                invoice_name=row["invoice_name"],
                admin_id=row["admin_id"],
                admin_username=row["admin_username"],
            )
            for row in rows
        ]

    def list_invoices_between(
        self,
        start_iso: str,
        end_iso: str,
        product_filter: str | None = None,
        fuzzy: bool = False,
        id_from: int | None = None,
        id_to: int | None = None,
    ) -> list[InvoiceSummary]:
        self._ensure_schema()
        with self._connect() as conn:
            conditions = ["i.created_at >= ?", "i.created_at <= ?"]
            params: list[object] = [start_iso, end_iso]
            if id_from is not None:
                conditions.append("i.id >= ?")
                params.append(id_from)
            if id_to is not None:
                conditions.append("i.id <= ?")
                params.append(id_to)
            where_clause = " AND ".join(conditions)
            if product_filter:
                if fuzzy:
                    product_value = f"%{product_filter}%"
                    op = "LIKE"
                else:
                    product_value = product_filter
                    op = "="
                params.append(product_value)
                rows = conn.execute(
                    f"""
                    SELECT DISTINCT
                        i.id,
                        i.invoice_type,
                        i.created_at,
                        i.total_lines,
                        i.total_qty,
                        i.total_amount,
                        i.invoice_name,
                        i.admin_id,
                        i.admin_username
                    FROM invoices i
                    JOIN invoice_lines il ON i.id = il.invoice_id
                    WHERE {where_clause} AND il.product_name {op} ?
                    ORDER BY i.id DESC
                    """,
                    params,
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""
                    SELECT
                        i.id,
                        i.invoice_type,
                        i.created_at,
                        i.total_lines,
                        i.total_qty,
                        i.total_amount,
                        i.invoice_name,
                        i.admin_id,
                        i.admin_username
                    FROM invoices i
                    WHERE {where_clause}
                    ORDER BY i.id DESC
                    """,
                    params,
                ).fetchall()
        return [
            InvoiceSummary(
                invoice_id=row["id"],
                invoice_type=row["invoice_type"],
                created_at=row["created_at"],
                total_lines=row["total_lines"],
                total_qty=row["total_qty"],
                total_amount=row["total_amount"],
                invoice_name=row["invoice_name"],
                admin_id=row["admin_id"],
                admin_username=row["admin_username"],
            )
            for row in rows
        ]

    def get_invoice(self, invoice_id: int) -> InvoiceSummary | None:
        self._ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    id,
                    invoice_type,
                    created_at,
                    total_lines,
                    total_qty,
                    total_amount,
                    invoice_name,
                    admin_id,
                    admin_username
                FROM invoices
                WHERE id = ?
                """,
                (invoice_id,),
            ).fetchone()
        if row is None:
            return None
        return InvoiceSummary(
            invoice_id=row["id"],
            invoice_type=row["invoice_type"],
            created_at=row["created_at"],
            total_lines=row["total_lines"],
            total_qty=row["total_qty"],
            total_amount=row["total_amount"],
            invoice_name=row["invoice_name"],
            admin_id=row["admin_id"],
            admin_username=row["admin_username"],
        )

    def update_invoice_lines(
        self,
        invoice_id: int,
        invoice_type: str,
        lines: list[InvoiceLine],
        invoice_name: str | None,
        admin_username: str | None = None,
    ) -> None:
        self._ensure_schema()
        total_qty = sum(line.quantity for line in lines)
        total_amount = sum(line.price * line.quantity for line in lines)
        self._backup_db()
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM invoice_lines WHERE invoice_id = ?",
                (invoice_id,),
            )
            line_rows = [
                (
                    invoice_id,
                    line.product_name,
                    float(line.price),
                    int(line.quantity),
                    float(line.price * line.quantity),
                    float(
                        line.cost_price
                        if invoice_type.startswith("sales")
                        else line.price
                    ),
                )
                for line in lines
            ]
            conn.executemany(
                """
                INSERT INTO invoice_lines (
                    invoice_id,
                    product_name,
                    price,
                    quantity,
                    line_total,
                    cost_price
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                line_rows,
            )
            conn.execute(
                """
                UPDATE invoices
                SET total_lines = ?, total_qty = ?, total_amount = ?, invoice_name = ?
                WHERE id = ?
                """,
                (len(lines), total_qty, total_amount, invoice_name, invoice_id),
            )
        send_backup(reason="invoice_updated", admin_username=admin_username)

    def update_invoice_name(
        self,
        invoice_id: int,
        invoice_name: str | None,
        admin_username: str | None = None,
    ) -> None:
        self._ensure_schema()
        self._backup_db()
        with self._connect() as conn:
            conn.execute(
                "UPDATE invoices SET invoice_name = ? WHERE id = ?",
                (invoice_name, invoice_id),
            )
        send_backup(reason="invoice_updated", admin_username=admin_username)

    def rename_products(
        self,
        name_changes: list[tuple[str, str]],
        admin_username: str | None = None,
    ) -> ProductRenameResult:
        self._ensure_schema()
        if not name_changes:
            return ProductRenameResult()
        rename_map: dict[str, str] = {}
        for old_name, new_name in name_changes:
            old_value = str(old_name or "").strip()
            new_value = str(new_name or "").strip()
            if not old_value or not new_value:
                continue
            if old_value == new_value:
                continue
            rename_map[old_value] = new_value
        if not rename_map:
            return ProductRenameResult()
        self._backup_db()
        updated = 0
        updated_by_invoice: dict[int, int] = {}
        with self._connect() as conn:
            for old_value, new_value in rename_map.items():
                rows = conn.execute(
                    "SELECT invoice_id FROM invoice_lines WHERE product_name = ?",
                    (old_value,),
                ).fetchall()
                if not rows:
                    continue
                for row in rows:
                    invoice_id = int(row["invoice_id"])
                    updated_by_invoice[invoice_id] = (
                        updated_by_invoice.get(invoice_id, 0) + 1
                    )
                conn.execute(
                    "UPDATE invoice_lines SET product_name = ? WHERE product_name = ?",
                    (new_value, old_value),
                )
                updated += len(rows)
        if updated:
            send_backup(reason="invoice_updated", admin_username=admin_username)
        return ProductRenameResult(
            updated_lines=updated,
            updated_invoice_ids=sorted(updated_by_invoice),
        )

    def delete_invoice(
        self, invoice_id: int, admin_username: str | None = None
    ) -> None:
        self._ensure_schema()
        self._backup_db()
        with self._connect() as conn:
            conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
        send_backup(reason="invoice_deleted", admin_username=admin_username)

    def count_invoices(self) -> int:
        self._ensure_schema()
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()
        return int(row[0] if row else 0)

    def get_invoice_stats(self) -> tuple[int, float]:
        self._ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM invoices"
            ).fetchone()
        if not row:
            return 0, 0.0
        return int(row[0]), float(row[1])

    def get_invoice_lines(self, invoice_id: int) -> list[InvoiceLine]:
        self._ensure_schema()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT product_name, price, quantity, line_total, cost_price
                FROM invoice_lines
                WHERE invoice_id = ?
                ORDER BY id ASC
                """,
                (invoice_id,),
            ).fetchall()
        return [
            InvoiceLine(
                product_name=row["product_name"],
                price=row["price"],
                quantity=row["quantity"],
                line_total=row["line_total"],
                cost_price=row["cost_price"],
            )
            for row in rows
        ]

    def get_monthly_summary(self, limit: int = 12) -> list[dict[str, float]]:
        self._ensure_schema()
        with self._connect() as conn:
            rows = conn.execute(
                """
                WITH invoice_months AS (
                    SELECT
                        substr(created_at, 1, 7) AS month,
                        SUM(CASE WHEN invoice_type = 'purchase'
                            THEN total_amount ELSE 0 END) AS purchase_total,
                        SUM(CASE WHEN invoice_type LIKE 'sales%'
                            THEN total_amount ELSE 0 END) AS sales_total,
                        COUNT(*) AS invoice_count
                    FROM invoices
                    GROUP BY month
                ),
                sales_profit AS (
                    SELECT
                        substr(i.created_at, 1, 7) AS month,
                        SUM(il.line_total - il.cost_price * il.quantity)
                            AS profit
                    FROM invoices i
                    JOIN invoice_lines il ON i.id = il.invoice_id
                    WHERE i.invoice_type LIKE 'sales%'
                    GROUP BY month
                )
                SELECT
                    im.month,
                    im.purchase_total,
                    im.sales_total,
                    COALESCE(sp.profit, 0) AS profit,
                    im.invoice_count
                FROM invoice_months im
                LEFT JOIN sales_profit sp ON sp.month = im.month
                ORDER BY im.month DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
