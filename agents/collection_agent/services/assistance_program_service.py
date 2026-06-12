"""Helpers for loaded assistance-program state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class AssistanceProgramService:
    """Filters assistance programs already loaded into state."""

    @staticmethod
    def get_programs(source: dict[str, Any]) -> list[dict[str, Any]]:
        programs = source.get("assistance_programs")
        return [dict(item) for item in programs if isinstance(item, dict)] if isinstance(programs, list) else []

    @staticmethod
    def match_programs(
        *,
        programs: list[dict[str, Any]],
        product: str | None = None,
        hardship_reason: str | None = None,
        loan_id: str | None = None,
        program_type: str | None = None,
    ) -> list[dict[str, Any]]:
        matched: list[dict[str, Any]] = []
        normalized_product = str(product or "").strip().lower()
        normalized_reason = str(hardship_reason or "").strip().lower()
        normalized_loan_id = str(loan_id or "").strip().upper()
        normalized_program_type = str(program_type or "").strip().lower()
        for program in programs:
            current_program_type = str(program.get("program_type", "")).strip().lower()
            eligible_products = [
                str(item).strip().lower()
                for item in program.get("eligible_products", [])
                if str(item).strip()
            ] if isinstance(program.get("eligible_products"), list) else []
            eligible_loan_ids = [
                str(item).strip().upper()
                for item in program.get("eligible_loan_ids", [])
                if str(item).strip()
            ] if isinstance(program.get("eligible_loan_ids"), list) else []
            hardship_reasons = [
                str(item).strip().lower()
                for item in program.get("hardship_reasons", [])
                if str(item).strip()
            ] if isinstance(program.get("hardship_reasons"), list) else []
            if normalized_program_type and current_program_type != normalized_program_type:
                continue
            if normalized_product and eligible_products and normalized_product not in eligible_products:
                continue
            if normalized_loan_id and eligible_loan_ids and normalized_loan_id not in eligible_loan_ids:
                continue
            if normalized_reason and hardship_reasons and normalized_reason not in hardship_reasons:
                continue
            matched.append(dict(program))
        return matched
