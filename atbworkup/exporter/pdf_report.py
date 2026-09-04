"""
PDF export for financial statements (Balance Sheet + Profit & Loss).

Uses QPrinter + QTextDocument — no external dependencies beyond PySide6.
Output: letter-size, LANDSCAPE, 0.5" margins — a multi-column workpaper-style
export needs the width; portrait strangled the label column down to nothing
and wrapped every account name letter-by-letter (see _colgroup_html()).

Columns exported mirror whichever are currently visible in the in-app Report
tab (report_tab.py) — "hidden in the report view" carries over to the PDF —
plus the same "Hide Account Numbers" toggle. Defaults to every column when
called without visible_cols (e.g. from a script), matching "all columns show
by default."
"""
from __future__ import annotations

import html as _html
from pathlib import Path

from PySide6.QtGui import QTextDocument, QPageLayout, QPageSize
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtCore import QMarginsF
from PySide6.QtWidgets import QFileDialog, QWidget

from atbworkup.reports.builder import FinancialReport, ReportLine, ReportSection
from atbworkup.data.tax_line_categories import (
    CATEGORY_REVENUE, CATEGORY_COGS, CATEGORY_OPEX, CATEGORY_SCHEDULE_K,
)

# ── Column definitions ─────────────────────────────────────────────────────────
# (key, header label, attribute suffix). Order matches the in-app Report tab.
# Header labels are short on purpose — Qt's HTML table engine doesn't size
# columns reliably from font-size/colgroup width, and a header even slightly
# wider than its column bleeds into the next one with no clipping. Full
# names (UNADJ BOOK, RECLASS JE, ...) still label the in-app Report tab;
# this is a print-only abbreviation to fit inside whatever column width Qt
# actually gives it.
_PDF_COL_DEFS = [
    ("unadj",    "UNADJ",  "pbc"),
    ("aje",      "BK JE",  "aje"),
    ("adj",      "ADJ",    "adj"),
    ("rje",      "RC JE",  "rje"),
    ("final",    "RECL'D", "final"),
    ("ftje",     "TX JE",  "ftje"),
    ("ftax",     "ADJ TX", "ftax"),
    ("py_final", "PY",     "py_final"),
    ("py_ftax",  "PY TX",  "py_ftax"),
]
_ALL_COL_KEYS = [k for k, _, _ in _PDF_COL_DEFS]


def _line_attr(suffix: str) -> str:
    return f"display_{suffix}"


def _agg_attr(prefix: str, suffix: str) -> str:
    # ReportSection.subtotal / FinancialReport.total_assets / .net_income are
    # all bare (no "_final" suffix) for the RECLASSED column — every other
    # column follows the regular "{prefix}_{suffix}" pattern.
    return prefix if suffix == "final" else f"{prefix}_{suffix}"


# ── Public entry point ────────────────────────────────────────────────────────

def export_statements_pdf(
    parent: QWidget,
    report_bs: FinancialReport,
    report_pl: FinancialReport,
    entity_name: str,
    tax_year: int,
    groups: list[dict],
    group_map: dict[str, str],
    default_dir: str = "",
    visible_cols: list[str] | None = None,
    show_acct_num: bool = True,
) -> str | None:
    """
    Show a Save dialog, write BS + P&L to PDF, return path or None if cancelled.
    """
    safe = entity_name.replace("/", "-").replace("\\", "-").strip() or "Entity"
    default_name = f"{safe} {tax_year} Financial Statements.pdf"
    filename, _ = QFileDialog.getSaveFileName(
        parent,
        "Export Financial Statements",
        str(Path(default_dir) / default_name),
        "PDF Files (*.pdf)",
    )
    if not filename:
        return None

    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(filename)
    printer.setPageLayout(QPageLayout(
        QPageSize(QPageSize.PageSizeId.Letter),
        QPageLayout.Orientation.Landscape,
        QMarginsF(36, 36, 36, 36),   # 0.5 inch at 72 pt/in
    ))

    cols = [c for c in _PDF_COL_DEFS if c[0] in (visible_cols or _ALL_COL_KEYS)]
    gby = {g["group_id"]: g for g in groups}
    html_src = _build_html(report_bs, report_pl, entity_name, tax_year, gby, group_map,
                           cols, show_acct_num)

    doc = QTextDocument()
    doc.setHtml(html_src)

    # Let QPrinter drive pagination
    doc.print_(printer)
    return filename


# ── HTML builder ──────────────────────────────────────────────────────────────

_CSS = """
* { margin: 0; padding: 0; }
body {
    font-family: "Calibri", "Segoe UI", sans-serif;
    font-size: 10pt;
    color: #1A1A1A;
}
table { width: 100%; border-collapse: collapse; table-layout: fixed; }
td    { vertical-align: middle; overflow: hidden; }
.h-entity { text-align: center; font-size: 14pt; font-weight: bold; padding: 4pt 0 2pt 0; }
.h-title  { text-align: center; font-size: 11pt; font-weight: bold; padding: 2pt 0; }
.h-period { text-align: center; font-size: 9pt;  color: #666666; padding: 1pt 0 10pt 0; }
.num      { text-align: right; font-family: "Courier New", monospace; font-size: 9pt;
            white-space: nowrap; padding: 1pt 5pt; border-right: 1px solid #E5E5E5; }
.category { font-size: 11pt; font-weight: bold; color: #1A2B4C;
            padding: 8pt 4pt 2pt 0; }
.sec-hdr  { font-weight: bold; padding: 3pt 4pt; white-space: nowrap; overflow: hidden;
            text-overflow: ellipsis; }
.grp      { font-weight: bold; }
.acct     { padding: 2pt 4pt 2pt 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.subtotal { font-weight: bold; padding: 2pt 4pt; white-space: nowrap; overflow: hidden;
            text-overflow: ellipsis; }
.grandtotal { font-weight: bold; font-size: 11pt; padding: 4pt 4pt; white-space: nowrap; }
.spacer   { font-size: 1pt; height: 10pt; }
.rule-row { font-size: 1pt; height: 1pt; }
.status   { text-align: center; font-style: italic; padding: 6pt 0; }
"""

_HTML_OPEN = f"<html><head><style>{_CSS}</style></head><body>"
_HTML_CLOSE = "</body></html>"


def _e(s: str) -> str:
    return _html.escape(str(s))


def _fmt(v: float) -> str:
    if abs(v) < 0.005:
        return "&#8212;"
    if v < 0:
        return f"({abs(v):,.2f})"
    return f"{v:,.2f}"


def _colspan(cols: list[tuple]) -> int:
    return 1 + len(cols)


def _display_section_name(sec: ReportSection) -> str:
    """Schedule K pass-through items read to a client as "Other Income" —
    matches the same rename in report_tab.py; the underlying tax-line
    section name is untouched everywhere else."""
    if _section_category(sec) == CATEGORY_SCHEDULE_K:
        return "Other Income"
    return sec.name


def _section_category(sec: ReportSection) -> str:
    counts: dict[str, int] = {}
    for ln in sec.lines:
        if ln.category:
            counts[ln.category] = counts.get(ln.category, 0) + 1
    if not counts:
        return ""
    return max(counts, key=counts.get)


def _build_html(
    bs: FinancialReport,
    pl: FinancialReport,
    entity_name: str,
    tax_year: int,
    gby: dict,
    group_map: dict,
    cols: list[tuple[str, str, str]],
    show_acct_num: bool,
) -> str:
    label_pct, amt_pct = _col_widths_pct(len(cols))
    parts = [_HTML_OPEN]

    # ── Balance Sheet ──────────────────────────────────────────────────────
    parts += _header_rows(entity_name, "Balance Sheet", f"As of December 31, {tax_year}")
    parts += _col_header_row(cols, label_pct, amt_pct)
    parts += _bs_rows(bs, pl, group_map, gby, cols, show_acct_num, label_pct, amt_pct)

    # ── Page break ─────────────────────────────────────────────────────────
    parts.append('<div style="page-break-before: always;"></div>')

    # ── Profit & Loss ──────────────────────────────────────────────────────
    parts += _header_rows(entity_name, "Profit & Loss",
                          f"For the Year Ended December 31, {tax_year}")
    parts += _col_header_row(cols, label_pct, amt_pct)
    parts += _pl_rows(pl, group_map, gby, cols, show_acct_num, label_pct, amt_pct)

    parts.append(_HTML_CLOSE)
    return "".join(parts)


def _col_widths_pct(n_cols: int) -> tuple[float, float]:
    """(label_col_pct, each_amount_col_pct) as HTML width-attribute values
    (0-100, no unit — Qt's HTML table engine expects the legacy HTML4-style
    percentage on the width ATTRIBUTE, not a CSS width/min-width/max-width
    style property, and not <colgroup><col width=...>; both of those are
    silently ignored and Qt falls back to auto-sizing each column from that
    column's own data content instead. An account with no AJE/RJE/FTJE
    entries shows "—" in those columns, so a column that's mostly "—" gets
    shrunk to fit a single dash, and that column's (wider) header label then
    overflows into its neighbor with no clipping (overflow:hidden on <td>
    is ignored too). The only thing that actually held the layout stable
    was the width="X%" HTML attribute, repeated on every single <td> in a
    column — header and data alike, not just the header.

    The label column is weighted as 3 "amount column units" so it stays
    readable whether 1 or 9 amount columns are showing.
    """
    units = n_cols + 3
    label_pct = round(300 / units, 2)
    amt_pct = round(100 / units, 2)
    return label_pct, amt_pct


def _label_td_attrs(label_pct: float, style: str = "", css_class: str = "") -> str:
    cls = f' class="{css_class}"' if css_class else ""
    return f'width="{label_pct}%"{cls} style="{style}"'


def _num_td(text: str, amt_pct: float, css_class: str = "num", style: str = "") -> str:
    return f'<td width="{amt_pct}%" class="{css_class}" style="{style}">{text}</td>'


def _header_rows(entity_name: str, title: str, period: str) -> list[str]:
    return [
        f'<p class="h-entity">{_e(entity_name)}</p>',
        f'<p class="h-title">{_e(title)}</p>',
        f'<p class="h-period">{_e(period)}</p>',
        '<table>',
    ]


def _col_header_row(cols: list[tuple[str, str, str]], label_pct: float, amt_pct: float) -> list[str]:
    base = "background-color:#1A2B4C;color:#FFFFFF;font-weight:bold;font-size:7.5pt;white-space:nowrap;"
    cells = [f'<td {_label_td_attrs(label_pct, base)}></td>']
    for _, label, _ in cols:
        cells.append(_num_td(_e(label), amt_pct, style=base))
    return [f'<tr>{"".join(cells)}</tr>']


# ── Balance Sheet renderer ────────────────────────────────────────────────────

def _bs_rows(report: FinancialReport, pl: FinancialReport, group_map: dict, gby: dict,
            cols: list[tuple[str, str, str]], show_acct_num: bool,
            label_pct: float, amt_pct: float) -> list[str]:
    rows: list[str] = []

    # ASSETS
    rows += _cat_row("ASSETS", cols)
    for sec in report.asset_sections:
        rows += _section_rows(sec, group_map, gby, cols, show_acct_num, label_pct, amt_pct)

    rows += _heavy_rule(cols)
    rows += _grandtotal_row(
        "Total Assets",
        {s: getattr(report, _agg_attr("total_assets", s)) for _, _, s in cols},
        cols, label_pct, amt_pct,
    )
    rows += _spacer(cols)

    # LIABILITIES & EQUITY
    rows += _cat_row("LIABILITIES & EQUITY", cols)
    for sec in report.liability_equity_sections:
        rows += _section_rows(sec, group_map, gby, cols, show_acct_num, label_pct, amt_pct)

    # A working TB only carries income/expense on the P&L, so equity is
    # understated by exactly the current year's net income until it's
    # injected here — same fix as report_tab.py's in-app preview. Without
    # this, every entity with nonzero net income prints an understated
    # "Total Liabilities & Equity" and a false "Out of Balance" banner.
    #
    # Note: ni/adj_le here use the FULL (unfiltered by `cols`) net_income and
    # total_liabilities_equity attributes for the balance-check math — a
    # hidden RECLASSED column must not silently change whether the statement
    # reports as balanced. `cols`-filtered dicts are only for what gets
    # printed on the "Current Year Net Income" / grand-total rows.
    ni = pl.net_income
    if abs(ni) >= 0.005:
        ni_vals = {s: getattr(pl, _agg_attr("net_income", s)) for _, _, s in cols}
        rows.append(
            f'<tr class="subtotal">'
            + f'<td {_label_td_attrs(label_pct, "padding-left:4pt;")}>Current Year Net Income</td>'
            + "".join(_num_td(_fmt(ni_vals[s]), amt_pct) for _, _, s in cols)
            + '</tr>'
        )
    adj_le_vals = {
        s: getattr(report, _agg_attr("total_liabilities_equity", s))
           + getattr(pl, _agg_attr("net_income", s))
        for _, _, s in cols
    }
    adj_le = report.total_liabilities_equity + ni

    rows += _heavy_rule(cols)
    rows += _grandtotal_row("Total Liabilities & Equity", adj_le_vals, cols, label_pct, amt_pct)
    rows += _spacer(cols)

    # Balance check
    diff = report.total_assets - adj_le
    if abs(diff) < 0.005:
        rows.append(
            f'<tr><td colspan="{_colspan(cols)}" class="status" style="color:#1A7A1A;">'
            '&#10003;&nbsp; In Balance</td></tr>'
        )
    else:
        rows.append(
            f'<tr><td colspan="{_colspan(cols)}" class="status" style="color:#CC0000;">'
            f'&#9888;&nbsp; Out of Balance &mdash; difference: {_fmt(diff)}</td></tr>'
        )

    rows.append("</table>")
    return rows


# ── P&L renderer ──────────────────────────────────────────────────────────────

def _pl_rows(report: FinancialReport, group_map: dict, gby: dict,
            cols: list[tuple[str, str, str]], show_acct_num: bool,
            label_pct: float, amt_pct: float) -> list[str]:
    rows: list[str] = []

    section_cats = [_section_category(sec) for sec in report.sections]
    rev_secs  = [s for s, c in zip(report.sections, section_cats) if c == CATEGORY_REVENUE]
    cogs_secs = [s for s, c in zip(report.sections, section_cats) if c == CATEGORY_COGS]
    opex_secs = [s for s, c in zip(report.sections, section_cats) if c == CATEGORY_OPEX]
    last_cogs_index = max(
        (i for i, c in enumerate(section_cats) if c == CATEGORY_COGS), default=-1
    )
    last_opex_index = max(
        (i for i, c in enumerate(section_cats) if c == CATEGORY_OPEX), default=-1
    )

    def _gp(suffix: str) -> float:
        attr = _agg_attr("subtotal", suffix)
        return (sum(getattr(s, attr) for s in rev_secs)
                - sum(getattr(s, attr) for s in cogs_secs))

    def _oi(suffix: str) -> float:
        attr = _agg_attr("subtotal", suffix)
        return _gp(suffix) - sum(getattr(s, attr) for s in opex_secs)

    for i, sec in enumerate(report.sections):
        rows += _section_rows(sec, group_map, gby, cols, show_acct_num, label_pct, amt_pct)
        if i == last_cogs_index and rev_secs:
            rows += _grandtotal_row("Gross Profit", {s: _gp(s) for _, _, s in cols}, cols, label_pct, amt_pct)
            rows += _spacer(cols)
        if i == last_opex_index:
            rows += _grandtotal_row("Operating Income", {s: _oi(s) for _, _, s in cols}, cols, label_pct, amt_pct)
            rows += _spacer(cols)

    rows += _heavy_rule(cols)
    rows += _grandtotal_row(
        "Net Income / (Loss)",
        {s: getattr(report, _agg_attr("net_income", s)) for _, _, s in cols},
        cols, label_pct, amt_pct,
    )
    rows.append("</table>")
    return rows


# ── Section ───────────────────────────────────────────────────────────────────

def _section_rows(
    sec: ReportSection,
    group_map: dict,
    gby: dict,
    cols: list[tuple[str, str, str]],
    show_acct_num: bool,
    label_pct: float,
    amt_pct: float,
    indent: int = 0,
) -> list[str]:
    rows: list[str] = []
    bg = "background-color:#F2F4F6;"
    name = _display_section_name(sec)

    rows.append(
        f'<tr>'
        + f'<td {_label_td_attrs(label_pct, bg + f"padding-left:{indent + 4}pt;", "sec-hdr")}>{_e(name)}</td>'
        + "".join(
            _num_td(_fmt(getattr(sec, _agg_attr("subtotal", s))), amt_pct, "num sec-hdr", bg)
            for _, _, s in cols
        )
        + '</tr>'
    )

    # Split accounts into grouped / ungrouped
    grouped: dict[str, list[ReportLine]] = {}
    ungrouped: list[ReportLine] = []
    for ln in sec.lines:
        gid = group_map.get(ln.account_id)
        if gid and gid in gby:
            grouped.setdefault(gid, []).append(ln)
        else:
            ungrouped.append(ln)

    # Collect ancestor group IDs so parent nodes render even if they hold
    # only child-group accounts (no direct members)
    all_gids: set[str] = set(grouped.keys())
    for gid in list(all_gids):
        g = gby.get(gid)
        while g and g.get("parent_id"):
            all_gids.add(g["parent_id"])
            g = gby.get(g["parent_id"])

    root_gids = sorted(
        [g for g in all_gids if gby.get(g, {}).get("parent_id") not in all_gids],
        key=lambda g: gby.get(g, {}).get("sort_order", 0),
    )
    for gid in root_gids:
        rows += _group_rows(gid, gby, grouped, all_gids, cols, show_acct_num,
                            label_pct, amt_pct, indent=indent + 8)

    for ln in ungrouped:
        rows.append(_acct_row(ln, cols, show_acct_num, label_pct, amt_pct, indent=indent + 8))

    # Subtotal
    rows.append(
        f'<tr class="subtotal">'
        + f'<td {_label_td_attrs(label_pct, f"padding-left:{indent + 4}pt;border-top:1px solid #AAAAAA;")}>Total {_e(name)}</td>'
        + "".join(
            _num_td(_fmt(getattr(sec, _agg_attr("subtotal", s))), amt_pct,
                    style="border-top:1px solid #AAAAAA;")
            for _, _, s in cols
        )
        + '</tr>'
    )
    rows += _spacer(cols, 4)
    return rows


# ── Group ─────────────────────────────────────────────────────────────────────

def _group_rows(
    gid: str,
    gby: dict,
    grouped: dict,
    all_gids: set,
    cols: list[tuple[str, str, str]],
    show_acct_num: bool,
    label_pct: float,
    amt_pct: float,
    indent: int,
) -> list[str]:
    group = gby.get(gid)
    if not group:
        return []
    all_lines = _collect(gid, gby, grouped, all_gids)
    if not all_lines:
        return []

    totals = {s: sum(getattr(ln, _line_attr(s)) for ln in all_lines) for _, _, s in cols}
    rows: list[str] = []
    rows.append(
        f'<tr class="grp">'
        + f'<td {_label_td_attrs(label_pct, f"padding-left:{indent}pt;padding-top:2pt;padding-bottom:2pt;")}>'
        f'{_e(group["name"])}</td>'
        + "".join(_num_td(_fmt(totals[s]), amt_pct) for _, _, s in cols)
        + '</tr>'
    )

    # Child groups first
    child_gids = sorted(
        [g for g in all_gids if gby.get(g, {}).get("parent_id") == gid],
        key=lambda g: gby.get(g, {}).get("sort_order", 0),
    )
    for cid in child_gids:
        rows += _group_rows(cid, gby, grouped, all_gids, cols, show_acct_num,
                            label_pct, amt_pct, indent=indent + 8)

    # Direct members
    for ln in grouped.get(gid, []):
        rows.append(_acct_row(ln, cols, show_acct_num, label_pct, amt_pct, indent=indent + 8))

    return rows


# ── Account row ───────────────────────────────────────────────────────────────

def _acct_row(ln: ReportLine, cols: list[tuple[str, str, str]],
             show_acct_num: bool, label_pct: float, amt_pct: float, indent: int) -> str:
    prefix = f"{ln.account_number}  " if (show_acct_num and ln.account_number) else ""
    warn = "&#9888;&nbsp; " if ln.has_open_notes else ""
    name = f"{prefix}{warn}{_e(ln.account_name)}"
    color = "#B07800" if ln.has_open_notes else "#1A1A1A"
    cells = "".join(_num_td(_fmt(getattr(ln, _line_attr(s))), amt_pct) for _, _, s in cols)
    return (
        f'<tr class="acct">'
        + f'<td {_label_td_attrs(label_pct, f"padding-left:{indent}pt;color:{color};")}>{name}</td>'
        + f'{cells}'
        + '</tr>'
    )


# ── Structural rows ───────────────────────────────────────────────────────────

def _cat_row(label: str, cols: list[tuple[str, str, str]]) -> list[str]:
    return [
        f'<tr><td colspan="{_colspan(cols)}" class="category">{_e(label)}</td></tr>'
    ]


def _grandtotal_row(label: str, values: dict[str, float],
                    cols: list[tuple[str, str, str]],
                    label_pct: float, amt_pct: float) -> list[str]:
    cells = "".join(
        _num_td(_fmt(values[s]), amt_pct, style="border-top:2px solid #333333;padding-top:4pt;")
        for _, _, s in cols
    )
    return [
        f'<tr class="grandtotal">'
        + f'<td {_label_td_attrs(label_pct, "border-top:2px solid #333333;padding-top:4pt;")}>{_e(label)}</td>'
        + f'{cells}'
        + '</tr>'
    ]


def _heavy_rule(cols: list[tuple[str, str, str]]) -> list[str]:
    return [
        f'<tr class="rule-row">'
        f'<td colspan="{_colspan(cols)}" style="border-top:2px solid #333333;font-size:1pt;">&nbsp;</td>'
        '</tr>'
    ]


def _spacer(cols: list[tuple[str, str, str]], h: int = 8) -> list[str]:
    return [f'<tr class="spacer"><td colspan="{_colspan(cols)}" style="height:{h}pt;">&nbsp;</td></tr>']


# ── Group collection helper (mirrors report_tab._collect) ─────────────────────

def _collect(gid: str, gby: dict, grouped: dict, all_gids: set) -> list[ReportLine]:
    lines: list[ReportLine] = list(grouped.get(gid, []))
    for g in all_gids:
        if gby.get(g, {}).get("parent_id") == gid:
            lines.extend(_collect(g, gby, grouped, all_gids))
    return lines
