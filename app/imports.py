"""Partner file import — delivery platform, supplier invoices, card acquirer.

BRD rules this module follows (section 5, External integration / Quality):
  * Each source has a named owner.
  * Failures must alert, never stop silently  -> every upload creates an
    ImportBatch row with a status, even when nothing could be loaded.
  * Re-runs must not duplicate data           -> the same file is refused by
    its SHA-256 fingerprint, and every row has a natural key that is
    checked before inserting (so overlapping files are safe too).
  * Failing records are quarantined, never silently loaded or dropped
                                              -> ImportRejection rows keep
    the raw row and the reason.

Files can be CSV or Excel (.xlsx). The first row must be the header.
"""
import csv
import hashlib
import io
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable

from sqlalchemy.orm import Session

from . import models

TOLERANCE = 1.0  # naira — allowed rounding difference in "net = gross - fees" style checks


# ---------------------------------------------------------------------------
# Source definitions
# ---------------------------------------------------------------------------
@dataclass
class Source:
    key: str
    label: str
    owner: str                     # BRD section 6
    columns: list[str]             # template order
    required: list[str]
    natural_key: Callable[[dict], tuple]
    validate: Callable[[dict, "Context"], list[str]] = None
    build: Callable[[dict, "Context", int], object] = None
    example: list[list] = field(default_factory=list)


@dataclass
class Context:
    db: Session
    locations: dict[str, int]      # location_code -> restaurant id
    order_ids: set[int]


# ---------- small parsing helpers ----------
def _num(v):
    if v is None or str(v).strip() == "":
        raise ValueError("empty")
    return float(str(v).replace(",", "").replace("₦", "").strip())


def _date(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"'{s}' is not a date (use YYYY-MM-DD or DD/MM/YYYY)")


def _check_number(row, col, errors, min_value=None):
    try:
        val = _num(row.get(col))
    except ValueError:
        errors.append(f"{col} must be a number")
        return None
    if min_value is not None and val < min_value:
        errors.append(f"{col} can't be below {min_value:g}")
    return val


def _check_date(row, col, errors):
    try:
        return _date(row.get(col))
    except ValueError as e:
        errors.append(f"{col}: {e}")
        return None


def _check_location(row, ctx, errors):
    code = (row.get("location_code") or "").strip().upper()
    if code not in ctx.locations:
        errors.append(f"location_code '{code}' is not a Chowly location ({', '.join(sorted(ctx.locations))})")
    return code


def _check_order(row, ctx, errors):
    raw = (row.get("chowly_order_id") or "").strip()
    if not raw:
        return None
    try:
        oid = int(float(raw))
    except ValueError:
        errors.append("chowly_order_id must be a whole number")
        return None
    if oid not in ctx.order_ids:
        errors.append(f"chowly_order_id {oid} doesn't exist in Chowly")
    return oid


def _supplier_key(name: str) -> str:
    return " ".join(name.lower().split())


# ---------- delivery platform ----------
def _validate_delivery(row, ctx):
    e = []
    _check_location(row, ctx, e)
    _check_order(row, ctx, e)
    _check_date(row, "order_date", e)
    _check_date(row, "settlement_date", e)
    gross = _check_number(row, "gross_amount", e, 0)
    comm = _check_number(row, "commission_amount", e, 0)
    net = _check_number(row, "net_amount", e)
    if None not in (gross, comm, net) and abs((gross - comm) - net) > TOLERANCE:
        e.append(f"net_amount {net:g} should equal gross_amount - commission_amount ({gross - comm:g})")
    return e


def _build_delivery(row, ctx, batch_id):
    return models.DeliverySettlement(
        batch_id=batch_id,
        platform_order_ref=row["platform_order_ref"].strip(),
        chowly_order_id=int(float(row["chowly_order_id"])) if (row.get("chowly_order_id") or "").strip() else None,
        restaurant_id=ctx.locations[row["location_code"].strip().upper()],
        order_date=_date(row["order_date"]),
        gross_amount=_num(row["gross_amount"]),
        commission_amount=_num(row["commission_amount"]),
        net_amount=_num(row["net_amount"]),
        settlement_date=_date(row["settlement_date"]),
        settlement_ref=row["settlement_ref"].strip(),
    )


# ---------- supplier invoices ----------
def _validate_supplier(row, ctx):
    e = []
    _check_location(row, ctx, e)
    _check_date(row, "invoice_date", e)
    try:
        if int(float(row.get("line_number"))) < 1:
            e.append("line_number must be 1 or more")
    except (TypeError, ValueError):
        e.append("line_number must be a whole number")
    qty = _check_number(row, "quantity", e)
    if qty is not None and qty <= 0:
        e.append("quantity must be more than 0")
    price = _check_number(row, "unit_price", e, 0)
    total = _check_number(row, "line_total", e, 0)
    if None not in (qty, price, total) and abs(qty * price - total) > TOLERANCE:
        e.append(f"line_total {total:g} should equal quantity x unit_price ({qty * price:g})")
    return e


def _build_supplier(row, ctx, batch_id):
    name = " ".join(row["supplier_name"].split())
    return models.SupplierInvoiceLine(
        batch_id=batch_id,
        supplier_name=name,
        supplier_key=_supplier_key(name),
        invoice_number=row["invoice_number"].strip(),
        invoice_date=_date(row["invoice_date"]),
        line_number=int(float(row["line_number"])),
        item_description=row["item_description"].strip(),
        quantity=_num(row["quantity"]),
        unit=(row.get("unit") or "").strip() or None,
        unit_price=_num(row["unit_price"]),
        line_total=_num(row["line_total"]),
        restaurant_id=ctx.locations[row["location_code"].strip().upper()],
    )


# ---------- card acquirer ----------
CARD_TYPES = {"sale", "refund", "chargeback"}


def _validate_card(row, ctx):
    e = []
    _check_location(row, ctx, e)
    _check_order(row, ctx, e)
    kind = (row.get("transaction_type") or "").strip().lower()
    if kind not in CARD_TYPES:
        e.append(f"transaction_type must be one of: {', '.join(sorted(CARD_TYPES))}")
    _check_date(row, "transaction_date", e)
    _check_date(row, "settlement_date", e)
    gross = _check_number(row, "gross_amount", e)
    fee = _check_number(row, "fee_amount", e, 0)
    net = _check_number(row, "net_amount", e)
    if None not in (gross, fee, net) and abs((gross - fee) - net) > TOLERANCE:
        e.append(f"net_amount {net:g} should equal gross_amount - fee_amount ({gross - fee:g})")
    if kind == "sale" and gross is not None and gross <= 0:
        e.append("a sale must have a positive gross_amount")
    if kind in ("refund", "chargeback") and gross is not None and gross >= 0:
        e.append(f"a {kind} must have a negative gross_amount (money going back)")
    return e


def _build_card(row, ctx, batch_id):
    return models.CardSettlement(
        batch_id=batch_id,
        transaction_reference=row["transaction_reference"].strip(),
        transaction_type=row["transaction_type"].strip().lower(),
        transaction_date=_date(row["transaction_date"]),
        settlement_date=_date(row["settlement_date"]),
        gross_amount=_num(row["gross_amount"]),
        fee_amount=_num(row["fee_amount"]),
        net_amount=_num(row["net_amount"]),
        chowly_order_id=int(float(row["chowly_order_id"])) if (row.get("chowly_order_id") or "").strip() else None,
        restaurant_id=ctx.locations[row["location_code"].strip().upper()],
    )


SOURCES: dict[str, Source] = {
    "delivery_platform": Source(
        key="delivery_platform",
        label="Delivery platform settlements",
        owner="Head of Operations",
        columns=["platform_order_ref", "chowly_order_id", "location_code", "order_date", "gross_amount",
                 "commission_amount", "net_amount", "settlement_date", "settlement_ref"],
        required=["platform_order_ref", "location_code", "order_date", "gross_amount",
                  "commission_amount", "net_amount", "settlement_date", "settlement_ref"],
        natural_key=lambda r: (r["platform_order_ref"].strip(), r["settlement_ref"].strip()),
        validate=_validate_delivery,
        build=_build_delivery,
        example=[["DP-88231", "", "LEK", "2026-10-01", "12500", "1875", "10625", "2026-10-03", "STL-2026-10-03"]],
    ),
    "supplier_invoice": Source(
        key="supplier_invoice",
        label="Supplier invoices",
        owner="Head Chef / Finance",
        columns=["supplier_name", "invoice_number", "invoice_date", "line_number", "item_description",
                 "quantity", "unit", "unit_price", "line_total", "location_code"],
        required=["supplier_name", "invoice_number", "invoice_date", "line_number", "item_description",
                  "quantity", "unit_price", "line_total", "location_code"],
        natural_key=lambda r: (_supplier_key(r["supplier_name"]), r["invoice_number"].strip(),
                               int(float(r["line_number"]))),
        validate=_validate_supplier,
        build=_build_supplier,
        example=[["Mama Put Foods Ltd", "INV-1042", "2026-10-01", "1", "Long grain rice", "5", "bag (50kg)",
                  "78000", "390000", "LEK"]],
    ),
    "card_acquirer": Source(
        key="card_acquirer",
        label="Card acquirer settlements",
        owner="Finance",
        columns=["transaction_reference", "transaction_type", "transaction_date", "settlement_date",
                 "gross_amount", "fee_amount", "net_amount", "chowly_order_id", "location_code"],
        required=["transaction_reference", "transaction_type", "transaction_date", "settlement_date",
                  "gross_amount", "fee_amount", "net_amount", "location_code"],
        natural_key=lambda r: (r["transaction_reference"].strip(), r["transaction_type"].strip().lower()),
        validate=_validate_card,
        build=_build_card,
        example=[["TXN-550193", "sale", "2026-10-01", "2026-10-02", "9000", "135", "8865", "", "IKJ"]],
    ),
}


def template_csv(source_key: str) -> str:
    src = SOURCES[source_key]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(src.columns)
    w.writerows(src.example)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Reading files
# ---------------------------------------------------------------------------
def _clean_header(h) -> str:
    return "_".join(str(h or "").strip().lower().split())


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def read_rows(filename: str, content: bytes) -> list[dict]:
    """Return the data rows as dicts keyed by cleaned header names."""
    if filename.lower().endswith(".xlsx"):
        from openpyxl import load_workbook
        ws = load_workbook(io.BytesIO(content), read_only=True, data_only=True).worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
    else:
        text = content.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    header = [_clean_header(h) for h in rows[0]]
    out = []
    for raw in rows[1:]:
        cells = [_cell(v) for v in raw]
        if not any(cells):
            continue  # ignore blank lines
        cells += [""] * (len(header) - len(cells))
        out.append(dict(zip(header, cells)))
    return out


# ---------------------------------------------------------------------------
# The import itself
# ---------------------------------------------------------------------------
class DuplicateFile(Exception):
    def __init__(self, batch):
        self.batch = batch


def _existing_keys(db: Session, source: Source) -> set[tuple]:
    if source.key == "delivery_platform":
        q = db.query(models.DeliverySettlement.platform_order_ref, models.DeliverySettlement.settlement_ref)
    elif source.key == "supplier_invoice":
        q = db.query(models.SupplierInvoiceLine.supplier_key, models.SupplierInvoiceLine.invoice_number,
                     models.SupplierInvoiceLine.line_number)
    else:
        q = db.query(models.CardSettlement.transaction_reference, models.CardSettlement.transaction_type)
    return {tuple(r) for r in q.all()}


def run_import(db: Session, source_key: str, filename: str, content: bytes, uploaded_by: str | None):
    source = SOURCES[source_key]
    digest = hashlib.sha256(content).hexdigest()

    already = db.query(models.ImportBatch).filter_by(source=source_key, file_sha256=digest).first()
    if already:
        raise DuplicateFile(already)

    batch = models.ImportBatch(source=source_key, filename=filename, file_sha256=digest,
                               uploaded_by=uploaded_by, status="failed")
    db.add(batch)
    db.flush()

    try:
        rows = read_rows(filename, content)
    except Exception as e:  # unreadable file: record it, don't crash
        batch.error = f"Could not read the file: {e}"
        db.commit()
        return batch

    batch.rows_total = len(rows)
    missing = [c for c in source.required if rows and c not in rows[0]] if rows else source.required
    if not rows:
        batch.error = "The file has no data rows."
        db.commit()
        return batch
    if missing:
        batch.error = f"Missing required column(s): {', '.join(missing)}. Download the template to see the expected header."
        batch.rows_rejected = len(rows)
        db.commit()
        return batch

    ctx = Context(
        db=db,
        locations={r.location_code: r.id for r in db.query(models.Restaurant).all() if r.location_code},
        order_ids={oid for (oid,) in db.query(models.Order.id).all()},
    )
    seen = _existing_keys(db, source)

    for n, row in enumerate(rows, start=2):  # row 1 is the header
        errors = [f"{c} is required" for c in source.required if not (row.get(c) or "").strip()]
        if not errors:
            errors = source.validate(row, ctx)
        if errors:
            db.add(models.ImportRejection(batch_id=batch.id, row_number=n,
                                          raw_row=json.dumps(row, ensure_ascii=False), errors="; ".join(errors)))
            batch.rows_rejected += 1
            continue
        key = source.natural_key(row)
        if key in seen:
            batch.rows_duplicate += 1   # already loaded (this file or an earlier one): skip, don't double count
            continue
        seen.add(key)
        db.add(source.build(row, ctx, batch.id))
        batch.rows_loaded += 1

    if batch.rows_rejected == 0:
        batch.status = "loaded"
    elif batch.rows_loaded or batch.rows_duplicate:
        batch.status = "partial"
    else:
        batch.status = "failed"
    db.commit()
    return batch
