from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import AppConfig
from app.services.backend_client import BackendAPIError, BackendClient
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
    ) -> None:
        _ = db_path
        config = AppConfig.load()
        self._client = BackendClient(config.backend_url)

    def create_purchase_invoice(
        self,
        lines: list[PurchaseLine],
        invoice_name: str | None = None,
        admin_id: int | None = None,
        admin_username: str | None = None,
    ) -> int:
        _ = admin_id
        payload = {
            "invoice_name": invoice_name,
            "admin_username": admin_username,
            "lines": [
                {
                    "product_name": line.product_name,
                    "price": float(line.price),
                    "quantity": int(line.quantity),
                }
                for line in lines
            ],
        }
        try:
            response = self._client.post(
                "/api/v1/invoices/purchase", json_body=payload
            )
        except BackendAPIError as exc:
            raise RuntimeError(str(exc)) from exc
        return int(response.get("invoice_id", 0))

    def create_sales_invoice(
        self,
        lines: list[SalesLine],
        invoice_name: str | None = None,
        admin_id: int | None = None,
        admin_username: str | None = None,
        invoice_type: str = "sales",
    ) -> int:
        _ = admin_id
        payload = {
            "invoice_name": invoice_name,
            "admin_username": admin_username,
            "invoice_type": invoice_type,
            "lines": [
                {
                    "product_name": line.product_name,
                    "price": float(line.price),
                    "quantity": int(line.quantity),
                }
                for line in lines
            ],
        }
        try:
            response = self._client.post(
                "/api/v1/invoices/sales", json_body=payload
            )
        except BackendAPIError as exc:
            raise RuntimeError(str(exc)) from exc
        return int(response.get("invoice_id", 0))

    def list_invoices(
        self, limit: int = 200, offset: int = 0
    ) -> list[InvoiceSummary]:
        try:
            payload = self._client.get(
                "/api/v1/invoices",
                params={"limit": limit, "offset": offset},
            )
        except BackendAPIError as exc:
            raise RuntimeError(str(exc)) from exc
        items = payload.get("items", []) if isinstance(payload, dict) else []
        return [
            self._to_summary(item) for item in items if isinstance(item, dict)
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
        params: dict[str, object] = {
            "start": start_iso,
            "end": end_iso,
            "fuzzy": str(bool(fuzzy)).lower(),
        }
        if product_filter:
            params["product_filter"] = product_filter
        if id_from is not None:
            params["id_from"] = id_from
        if id_to is not None:
            params["id_to"] = id_to
        try:
            payload = self._client.get("/api/v1/invoices/range", params=params)
        except BackendAPIError as exc:
            raise RuntimeError(str(exc)) from exc
        items = payload.get("items", []) if isinstance(payload, dict) else []
        return [
            self._to_summary(item) for item in items if isinstance(item, dict)
        ]

    def get_invoice(self, invoice_id: int) -> InvoiceSummary | None:
        try:
            payload = self._client.get(f"/api/v1/invoices/{invoice_id}")
        except BackendAPIError as exc:
            if "not found" in str(exc).lower():
                return None
            raise RuntimeError(str(exc)) from exc
        invoice = payload.get("invoice") if isinstance(payload, dict) else None
        if not isinstance(invoice, dict):
            return None
        return self._to_summary(invoice)

    def update_invoice_lines(
        self,
        invoice_id: int,
        invoice_type: str,
        lines: list[InvoiceLine],
        invoice_name: str | None,
        admin_username: str | None = None,
    ) -> None:
        _ = invoice_type
        _ = admin_username
        payload = {
            "invoice_name": invoice_name,
            "lines": [
                {
                    "product_name": line.product_name,
                    "price": float(line.price),
                    "quantity": int(line.quantity),
                    "line_total": float(line.price) * int(line.quantity),
                    "cost_price": float(line.cost_price),
                }
                for line in lines
            ],
        }
        try:
            self._client.patch(
                f"/api/v1/invoices/{invoice_id}/lines",
                json_body=payload,
            )
        except BackendAPIError as exc:
            raise RuntimeError(str(exc)) from exc

    def update_invoice_name(
        self,
        invoice_id: int,
        invoice_name: str | None,
        admin_username: str | None = None,
    ) -> None:
        _ = admin_username
        try:
            self._client.patch(
                f"/api/v1/invoices/{invoice_id}/name",
                json_body={"invoice_name": invoice_name},
            )
        except BackendAPIError as exc:
            raise RuntimeError(str(exc)) from exc

    def rename_products(
        self,
        name_changes: list[tuple[str, str]],
        admin_username: str | None = None,
    ) -> ProductRenameResult:
        _ = admin_username
        changes = [[old, new] for old, new in name_changes]
        try:
            payload = self._client.post(
                "/api/v1/invoices/rename-products",
                json_body={"changes": changes},
            )
        except BackendAPIError as exc:
            raise RuntimeError(str(exc)) from exc
        updated_ids = (
            payload.get("updated_invoice_ids", [])
            if isinstance(payload, dict)
            else []
        )
        return ProductRenameResult(
            updated_lines=int(payload.get("updated_lines", 0)),
            updated_invoice_ids=[int(item) for item in updated_ids],
        )

    def delete_invoice(
        self, invoice_id: int, admin_username: str | None = None
    ) -> None:
        _ = admin_username
        try:
            self._client.delete(f"/api/v1/invoices/{invoice_id}")
        except BackendAPIError as exc:
            raise RuntimeError(str(exc)) from exc

    def count_invoices(self) -> int:
        count, _ = self.get_invoice_stats()
        return count

    def get_invoice_stats(self) -> tuple[int, float]:
        try:
            payload = self._client.get("/api/v1/invoices/stats")
        except BackendAPIError as exc:
            raise RuntimeError(str(exc)) from exc
        return int(payload.get("count", 0)), float(
            payload.get("total_amount", 0.0)
        )

    def get_invoice_lines(self, invoice_id: int) -> list[InvoiceLine]:
        try:
            payload = self._client.get(f"/api/v1/invoices/{invoice_id}")
        except BackendAPIError as exc:
            raise RuntimeError(str(exc)) from exc
        lines = payload.get("lines", []) if isinstance(payload, dict) else []
        result: list[InvoiceLine] = []
        for line in lines:
            if not isinstance(line, dict):
                continue
            price = float(line.get("price", 0.0) or 0.0)
            qty = int(line.get("quantity", 0) or 0)
            result.append(
                InvoiceLine(
                    product_name=str(line.get("product_name", "")),
                    price=price,
                    quantity=qty,
                    line_total=float(
                        line.get("line_total", price * qty) or (price * qty)
                    ),
                    cost_price=float(line.get("cost_price", 0.0) or 0.0),
                )
            )
        return result

    def get_monthly_summary(self, limit: int = 12) -> list[dict[str, float]]:
        try:
            payload = self._client.get(
                "/api/v1/analytics/monthly",
                params={"limit": limit},
            )
        except BackendAPIError as exc:
            raise RuntimeError(str(exc)) from exc
        items = payload.get("items", []) if isinstance(payload, dict) else []
        return [item for item in items if isinstance(item, dict)]

    @staticmethod
    def _to_summary(raw: dict[str, object]) -> InvoiceSummary:
        return InvoiceSummary(
            invoice_id=int(raw.get("id", 0) or 0),
            invoice_type=str(raw.get("invoice_type", "")),
            created_at=str(raw.get("created_at", "")),
            total_lines=int(raw.get("total_lines", 0) or 0),
            total_qty=int(raw.get("total_qty", 0) or 0),
            total_amount=float(raw.get("total_amount", 0.0) or 0.0),
            invoice_name=(
                None
                if raw.get("invoice_name") in {None, ""}
                else str(raw.get("invoice_name"))
            ),
            admin_id=(
                None
                if raw.get("admin_id") is None
                else int(raw.get("admin_id", 0) or 0)
            ),
            admin_username=(
                None
                if raw.get("admin_username") in {None, ""}
                else str(raw.get("admin_username"))
            ),
        )
