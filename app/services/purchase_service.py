from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class PurchaseLine:
    product_name: str
    price: float
    quantity: int


@dataclass
class PurchaseSummary:
    total_lines: int
    updated: int
    created: int
    errors: int


class PurchaseService:
    def apply_purchases(
        self,
        lines: list[PurchaseLine],
        inventory_df: pd.DataFrame,
        allow_create: bool = True,
    ) -> tuple[pd.DataFrame, PurchaseSummary, list[str]]:
        updated_df = inventory_df.copy()
        if "last_buy_price" not in updated_df.columns:
            updated_df["last_buy_price"] = 0.0
        name_to_index = {
            str(name).strip().lower(): idx
            for idx, name in updated_df["product_name"].items()
        }

        errors: list[str] = []
        updated = 0
        created = 0

        for line in lines:
            key = line.product_name.strip().lower()
            if key in name_to_index:
                idx = name_to_index[key]
                old_qty = int(updated_df.at[idx, "quantity"])
                old_avg = float(updated_df.at[idx, "avg_buy_price"])

                effective_qty = old_qty if old_qty > 0 else 0
                effective_avg = old_avg if old_avg > 0 else float(line.price)

                new_qty = effective_qty + line.quantity
                new_avg = (
                    effective_avg * effective_qty + line.price * line.quantity
                ) / new_qty

                updated_df.at[idx, "quantity"] = new_qty
                updated_df.at[idx, "avg_buy_price"] = round(new_avg, 4)
                updated_df.at[idx, "last_buy_price"] = round(line.price, 4)
                updated += 1
            else:
                if not allow_create:
                    errors.append(line.product_name)
                    continue
                new_row = {
                    "product_name": line.product_name,
                    "quantity": line.quantity,
                    "avg_buy_price": round(line.price, 4),
                    "last_buy_price": round(line.price, 4),
                }
                updated_df = pd.concat(
                    [updated_df, pd.DataFrame([new_row])], ignore_index=True
                )
                name_to_index[key] = updated_df.index[-1]
                created += 1

        summary = PurchaseSummary(
            total_lines=len(lines),
            updated=updated,
            created=created,
            errors=len(errors),
        )
        return updated_df, summary, errors
