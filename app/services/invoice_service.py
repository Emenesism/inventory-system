from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.services.purchase_service import PurchaseLine


@dataclass
class InvoiceSummary:
    invoice_id: int
    invoice_type: str
    created_at: str
    total_lines: int
    total_qty: int
    total_amount: float


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


class InvoiceService:
    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is None:
            db_path = Path(__file__).resolve().parents[2] / "invoices.db"
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _backup_db(self) -> None:
        if not self.db_path.exists():
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"invoices_backup_{timestamp}{self.db_path.suffix}"
        backup_path = self.db_path.with_name(backup_name)
        shutil.copy2(self.db_path, backup_path)

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
                    total_amount REAL NOT NULL
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
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_invoice_lines_invoice_id "
                "ON invoice_lines(invoice_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_invoices_created_at "
                "ON invoices(created_at)"
            )

    def create_purchase_invoice(self, lines: list[PurchaseLine]) -> int:
        total_qty = sum(line.quantity for line in lines)
        total_amount = sum(line.price * line.quantity for line in lines)
        created_at = datetime.now().isoformat(timespec="seconds")

        self._backup_db()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO invoices (
                    invoice_type,
                    created_at,
                    total_lines,
                    total_qty,
                    total_amount
                ) VALUES (?, ?, ?, ?, ?)
                """,
                ("purchase", created_at, len(lines), total_qty, total_amount),
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
            return invoice_id

    def create_sales_invoice(self, lines: list[SalesLine]) -> int:
        total_qty = sum(line.quantity for line in lines)
        total_amount = sum(line.price * line.quantity for line in lines)
        created_at = datetime.now().isoformat(timespec="seconds")

        self._backup_db()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO invoices (
                    invoice_type,
                    created_at,
                    total_lines,
                    total_qty,
                    total_amount
                ) VALUES (?, ?, ?, ?, ?)
                """,
                ("sales", created_at, len(lines), total_qty, total_amount),
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
            return invoice_id

    def list_invoices(self, limit: int = 200) -> list[InvoiceSummary]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    invoice_type,
                    created_at,
                    total_lines,
                    total_qty,
                    total_amount
                FROM invoices
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            InvoiceSummary(
                invoice_id=row["id"],
                invoice_type=row["invoice_type"],
                created_at=row["created_at"],
                total_lines=row["total_lines"],
                total_qty=row["total_qty"],
                total_amount=row["total_amount"],
            )
            for row in rows
        ]

    def get_invoice_lines(self, invoice_id: int) -> list[InvoiceLine]:
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
        with self._connect() as conn:
            rows = conn.execute(
                """
                WITH invoice_months AS (
                    SELECT
                        substr(created_at, 1, 7) AS month,
                        SUM(CASE WHEN invoice_type = 'purchase'
                            THEN total_amount ELSE 0 END) AS purchase_total,
                        SUM(CASE WHEN invoice_type = 'sales'
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
                    WHERE i.invoice_type = 'sales'
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
