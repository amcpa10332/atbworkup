"""
Single source of truth for combining subsidiary financials into a
consolidated view — reads subsidiaries, folds in eliminating/CTE entries
(both the legacy flat section-level kind and the account-level kind), and
computes the correctly-signed net income.

Both the interactive Consolidation window (ui/consolidation_window.py) and
the Excel export (exporter/review_package.py) call compute_combined() so
they can never compute two different answers for the same binder — that
divergence (export showing pre-elimination totals while the screen showed
post-elimination ones) was a real bug this module exists to prevent.
"""
from __future__ import annotations

from pathlib import Path

from atbworkup.models import consolidation_entries as ce_model
from atbworkup.data.tax_line_categories import CATEGORY_SCHEDULE_K
from atbworkup.models.consolidation_read import (
    SectionData, read_member_financials, read_member_account_index, merge_into,
)


def compute_combined(conn, job: dict) -> dict:
    """
    Returns a dict with every piece needed to render or export the combined
    financials:

        combined_bs, combined_pl        SectionData
        member_bs, member_pl            [(label, SectionData), ...]
        detail_bs, detail_pl            [(label, AccountDetail), ...]
        member_labels                   [label, ...]
        member_dicts                    [{"member_id","label","file_path"}, ...]
        label_to_member_id              {label: member_id}
        member_account_idx              {member_id: {account_id: meta}}
        elim_by_section, cte_by_section  {section: amount}  (display convention)
        elim_by_account, cte_by_account  {(member_id, account_id): amount}
        pl_base_ni, pl_elim_ni, pl_cte_ni  float  (P&L-only, raw-signed)
        combined_net_income              float  (pl_base_ni + pl_elim_ni + pl_cte_ni)
        sch_k_total_ni, has_sch_k        float, bool
        net_elim_total, net_cte_total     float  (BS-raw + P&L-signed, for
                                                   "Net Consolidated" totals)
        errors                           [str, ...]
    """
    job_id = job["job_id"]
    members = conn.execute(
        "SELECT member_id, member_name, member_code, file_path "
        "FROM consolidation_members WHERE job_id = ? ORDER BY sort_order",
        (job_id,),
    ).fetchall()
    elim_rows = conn.execute(
        "SELECT description, line_type, amount FROM workpaper_lines "
        "WHERE job_id = ? AND workpaper = 'elim' ORDER BY sort_order",
        (job_id,),
    ).fetchall()
    cte_rows = conn.execute(
        "SELECT description, line_type, amount FROM workpaper_lines "
        "WHERE job_id = ? AND workpaper = 'cte' ORDER BY sort_order",
        (job_id,),
    ).fetchall()
    acct_elim_lines = ce_model.get_all_lines_for_job(conn, job_id, "elim")
    acct_cte_lines  = ce_model.get_all_lines_for_job(conn, job_id, "cte")

    # Legacy flat section-level entries
    elim_by_section: dict[str, float] = {}
    elim_total = 0.0
    for row in elim_rows:
        amt = float(row["amount"])
        elim_total += amt
        sec = (row["line_type"] or "").strip()
        elim_by_section[sec] = elim_by_section.get(sec, 0.0) + amt

    cte_by_section: dict[str, float] = {}
    cte_total = 0.0
    for row in cte_rows:
        amt = float(row["amount"])
        cte_total += amt
        sec = (row["line_type"] or "").strip()
        cte_by_section[sec] = cte_by_section.get(sec, 0.0) + amt

    combined_bs: SectionData = {}
    combined_pl: SectionData = {}
    member_bs: list[tuple[str, SectionData]] = []
    member_pl: list[tuple[str, SectionData]] = []
    detail_bs: list[tuple[str, dict]] = []
    detail_pl: list[tuple[str, dict]] = []
    member_labels: list[str] = []
    member_dicts: list[dict] = []
    label_to_member_id: dict[str, str] = {}
    member_account_idx: dict[str, dict] = {}
    errors: list[str] = []

    for member in members:
        fp   = Path(member["file_path"])
        name = member["member_name"]
        code = (member["member_code"] or "").strip()
        label = code if code else name
        if not fp.exists():
            errors.append(f"{name}: file not found")
            continue
        try:
            bs_data, pl_data, bs_detail, pl_detail = read_member_financials(fp)
            member_bs.append((label, bs_data))
            member_pl.append((label, pl_data))
            detail_bs.append((label, bs_detail))
            detail_pl.append((label, pl_detail))
            member_labels.append(label)
            member_dicts.append({
                "member_id": member["member_id"], "label": label,
                "file_path": str(fp),
            })
            label_to_member_id[label] = member["member_id"]
            merge_into(combined_bs, bs_data)
            merge_into(combined_pl, pl_data)
            try:
                member_account_idx[member["member_id"]] = read_member_account_index(fp)
            except Exception:
                member_account_idx[member["member_id"]] = {}
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    # Fold account-level elimination/CTE lines into the same section buckets
    # the legacy flat entries use, so both mechanisms combine consistently.
    elim_by_account: dict[tuple[str, str], float] = {}
    cte_by_account:  dict[tuple[str, str], float] = {}

    def _fold_account_lines(lines: list[dict], by_section: dict[str, float],
                            by_account: dict[tuple[str, str], float]) -> float:
        added = 0.0
        for ln in lines:
            meta = member_account_idx.get(ln["member_id"], {}).get(ln["account_id"])
            if not meta:
                continue
            amt = float(ln["amount"])
            if meta["stmt"] != "BalanceSheet" and meta.get("normal_balance") == "Credit":
                amt = -amt
            sec = meta.get("section") or ""
            by_section[sec] = by_section.get(sec, 0.0) + amt
            key = (ln["member_id"], ln["account_id"])
            by_account[key] = by_account.get(key, 0.0) + amt
            added += amt
        return added

    elim_total += _fold_account_lines(acct_elim_lines, elim_by_section, elim_by_account)
    cte_total  += _fold_account_lines(acct_cte_lines, cte_by_section, cte_by_account)

    # Revenue and expense-type P&L sections are BOTH displayed as positive
    # numbers, so blindly summing every section's displayed total overstates
    # net income by adding expenses instead of subtracting them. The raw
    # DR+/CR- value self-cancels correctly: net income = -sum(raw).
    pl_base_ni = -sum(v.get("raw", v["final"])
                      for lines in combined_pl.values() for v in lines.values())
    pl_section_keys = {s.strip().lower() for s in combined_pl.keys()}

    def _ni_from_flat_rows(rows) -> float:
        return sum(-float(r["amount"]) for r in rows
                   if (r["line_type"] or "").strip().lower() in pl_section_keys)

    def _ni_from_account_lines(lines) -> float:
        total = 0.0
        for ln in lines:
            meta = member_account_idx.get(ln["member_id"], {}).get(ln["account_id"])
            if meta and meta["stmt"] != "BalanceSheet":
                total += -float(ln["amount"])
        return total

    pl_elim_ni = _ni_from_flat_rows(elim_rows) + _ni_from_account_lines(acct_elim_lines)
    pl_cte_ni  = _ni_from_flat_rows(cte_rows) + _ni_from_account_lines(acct_cte_lines)
    combined_net_income = pl_base_ni + pl_elim_ni + pl_cte_ni

    # Schedule K pass-through items (1065/1120S) mix income-type accounts
    # with deduction-type accounts in the SAME section, so a per-section
    # display sum can't correctly combine them. Compute Schedule K's own net
    # contribution from the stored category, not a section-name guess.
    sch_k_base_ni = -sum(
        v.get("raw", v["final"])
        for lines in combined_pl.values()
        for v in lines.values()
        if v.get("category") == CATEGORY_SCHEDULE_K
    )
    has_sch_k = any(
        v.get("category") == CATEGORY_SCHEDULE_K
        for lines in combined_pl.values() for v in lines.values()
    )

    def _is_sch_k_flat_row(sec: str) -> bool:
        return "schedule k" in sec.strip().lower()

    def _ni_from_flat_rows_sch_k(rows) -> float:
        return sum(-float(r["amount"]) for r in rows
                   if _is_sch_k_flat_row((r["line_type"] or "")))

    def _ni_from_account_lines_sch_k(lines) -> float:
        total = 0.0
        for ln in lines:
            meta = member_account_idx.get(ln["member_id"], {}).get(ln["account_id"])
            if meta and meta["stmt"] != "BalanceSheet" and meta.get("category") == CATEGORY_SCHEDULE_K:
                total += -float(ln["amount"])
        return total

    sch_k_elim_ni = _ni_from_flat_rows_sch_k(elim_rows) + _ni_from_account_lines_sch_k(acct_elim_lines)
    sch_k_cte_ni  = _ni_from_flat_rows_sch_k(cte_rows) + _ni_from_account_lines_sch_k(acct_cte_lines)
    sch_k_total_ni = sch_k_base_ni + sch_k_elim_ni + sch_k_cte_ni

    # BS-targeted elimination/CTE amounts never flip (Balance Sheet is always
    # shown raw), so pull them straight from the already-computed section
    # dicts. Combined with the correctly-signed P&L contribution, this gives
    # a single consistent total for "Net Consolidated" summary rows.
    bs_section_keys = {s.strip().lower() for s in combined_bs.keys()}
    bs_elim_raw = sum(amt for key, amt in elim_by_section.items()
                      if key.strip().lower() in bs_section_keys)
    bs_cte_raw  = sum(amt for key, amt in cte_by_section.items()
                      if key.strip().lower() in bs_section_keys)
    net_elim_total = bs_elim_raw + pl_elim_ni
    net_cte_total  = bs_cte_raw + pl_cte_ni

    return {
        "combined_bs": combined_bs, "combined_pl": combined_pl,
        "member_bs": member_bs, "member_pl": member_pl,
        "detail_bs": detail_bs, "detail_pl": detail_pl,
        "member_labels": member_labels, "member_dicts": member_dicts,
        "label_to_member_id": label_to_member_id,
        "member_account_idx": member_account_idx,
        "elim_by_section": elim_by_section, "cte_by_section": cte_by_section,
        "elim_by_account": elim_by_account, "cte_by_account": cte_by_account,
        "pl_base_ni": pl_base_ni, "pl_elim_ni": pl_elim_ni, "pl_cte_ni": pl_cte_ni,
        "combined_net_income": combined_net_income,
        "sch_k_total_ni": sch_k_total_ni, "has_sch_k": has_sch_k,
        "net_elim_total": net_elim_total, "net_cte_total": net_cte_total,
        "errors": errors,
    }
