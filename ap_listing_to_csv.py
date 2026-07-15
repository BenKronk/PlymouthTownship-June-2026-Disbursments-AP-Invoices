#!/usr/bin/env python3
"""
Convert a Charter Township of Plymouth "AP Invoice Listing - Board Report" PDF
into a tidy, one-row-per-GL-line-item CSV suitable for Power BI or Tableau.

Usage:
    python ap_listing_to_csv.py INPUT.pdf [OUTPUT.csv]

If OUTPUT.csv is omitted, it is written next to the input with a .csv extension.

Output columns:
    Vendor, Invoice_Number, Invoice_Description, Check_Date,
    Invoice_Amount, GL_Account, Line_Description, Line_Amount

Notes / assumptions (verified against the 6/23/2026 board packet layout):
  * The report is a hierarchical layout, not a table. Each vendor block has one
    invoice (vendor, invoice #, check date, total) and one or more GL line items.
  * Words are separated by ~2.6pt gaps, below pdfplumber's default x_tolerance,
    so x_tolerance is lowered to 1.2 to split words correctly.
  * Descriptions truncated in the source PDF are kept exactly as printed; the
    script does not attempt to reconstruct them.
  * Invoice numbers are emitted as text so leading zeros / alphanumerics survive.
  * If the township changes the report layout, the column x-bands and the
    skip/classification rules below are the things to revisit.
"""

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import pdfplumber

DEBUG = "--debug" in sys.argv   # dump raw lines for non-reconciling invoices

# --- layout constants (points; from the township board-report template) -------
X_TOLERANCE = 1.2          # split words on the ~2.6pt inter-word gap
Y_TOLERANCE = 1.0          # keep digits from vertically-adjacent rows apart
LINE_GAP = 1.0             # start a new line when top jumps more than this
GL_RE = re.compile(r"^\d{3}-\d{3}-\d+\.\d+$")      # e.g. 101-336-773.000
DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
MONEY_RE = re.compile(r"^\(?[\d,]+\.\d{2}\)?$")    # 1,373.13 or (203.25) credits
INV_MARKERS = ("INV.", "INV#")
DESC_X_MIN, DESC_X_MAX = 285, 500   # line-item description column band
LEFT_X_MAX = 200                    # vendor / header text lives left of this
MONEY_X_MIN = 450                   # money values sit to the right of this
RIGHT_X_MIN = 395                   # Invoice Amount / Check Date column starts here
HEADER_X = 40                       # vendor name & invoice header start near x=24

# header/footer noise to ignore (matched against the joined line text, upper)
SKIP_SUBSTRINGS = (
    "CHARTER TOWNSHIP", "AP INVOICE LISTING", "BOARD REPORT",
    "VENDOR INFORMATION", "INVOICE INFORMATION", "PACKET PAGE", "PAGE:",
)


def group_lines(words):
    """Cluster words into visual lines, starting a new line whenever the top
    coordinate jumps by more than LINE_GAP. This keeps a page-bottom data row
    separate from the slightly-lower 'Packet Page X of 168' footer."""
    lines = []
    cur, cur_top = [], None
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if cur_top is None or abs(w["top"] - cur_top) <= LINE_GAP:
            cur.append(w)
            cur_top = w["top"] if cur_top is None else cur_top
        else:
            lines.append(sorted(cur, key=lambda w: w["x0"]))
            cur, cur_top = [w], w["top"]
    if cur:
        lines.append(sorted(cur, key=lambda w: w["x0"]))
    return lines


def line_text(ws):
    return " ".join(w["text"] for w in ws)


def is_noise(ws):
    txt = line_text(ws).upper()
    if any(s in txt for s in SKIP_SUBSTRINGS):
        return True
    # page-footer line like "6/23/2026 BOARD"
    if len(ws) <= 2 and txt.endswith("BOARD"):
        return True
    return False


def money(tok):
    tok = tok.replace("$", "").replace(",", "").strip()
    if tok.startswith("(") and tok.endswith(")"):   # accounting-style credit
        return -float(tok[1:-1])
    return float(tok)


def parse_header(tokens):
    """From left/middle header tokens, return (invoice_number, description).

    Handles 'INV# 12345 desc...', 'INV. 12345 desc...', and the variant where
    the line begins with a '#id' instead of an INV marker (e.g. APEX '#334139').
    """
    if not tokens:
        return "", ""
    if tokens[0] in INV_MARKERS:
        number = tokens[1] if len(tokens) > 1 else ""
        rest = tokens[2:]
    elif tokens[0].startswith("#"):
        number = tokens[0].lstrip("#")
        rest = tokens[1:]
        if rest and rest[0] == "-":      # drop a leading separator dash
            rest = rest[1:]
    else:
        number = ""
        rest = tokens
    return number, " ".join(rest)


def parse_pdf(path):
    rows = []
    vendor_buf = []          # vendor tokens seen before this invoice's $ line
    cur = {}                 # current invoice context
    awaiting_header = False  # True between the $ line and its INV/desc line
    inv_seq = 0              # unique id per invoice (numbers can be blank/repeat)
    debug = {}               # seq -> list of raw line reprs (for --debug)

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=X_TOLERANCE,
                                       y_tolerance=Y_TOLERANCE,
                                       keep_blank_chars=False)
            for ws in group_lines(words):
                if not ws or is_noise(ws):
                    continue

                if DEBUG and inv_seq:
                    debug.setdefault(inv_seq, []).append(
                        " | ".join(f"{round(w['x0'])}:{w['text']}" for w in ws))

                first = ws[0]["text"]

                # 1. GL line item -------------------------------------------
                if GL_RE.match(first):
                    desc = " ".join(
                        w["text"] for w in ws
                        if DESC_X_MIN <= w["x0"] < DESC_X_MAX)
                    amt_toks = [w["text"] for w in ws
                                if w["x0"] >= MONEY_X_MIN and MONEY_RE.match(w["text"])]
                    rows.append({
                        "Invoice_ID": cur.get("seq", ""),
                        "Vendor": cur.get("vendor", ""),
                        "Invoice_Number": cur.get("inv_number", ""),
                        "Invoice_Description": cur.get("inv_desc", ""),
                        "Check_Date": cur.get("check_date", ""),
                        "Invoice_Amount": cur.get("amount", ""),
                        "GL_Account": first,
                        "Line_Description": desc,
                        "Line_Amount": money(amt_toks[-1]) if amt_toks else None,
                    })
                    continue

                # 2. capture check date wherever it appears (own line or
                #    merged onto the invoice-header line, always right-aligned)
                if any(w["text"] == "Date:" for w in ws):
                    dt = [w["text"] for w in ws
                          if w["x0"] >= RIGHT_X_MIN and DATE_RE.match(w["text"])]
                    if dt:
                        cur["check_date"] = dt[0]

                # 3. invoice amount line -> begins a new invoice record ------
                dollar = [w["text"] for w in ws if w["text"].startswith("$")]
                if dollar:
                    left_vendor = [w["text"] for w in ws if w["x0"] < LEFT_X_MAX]
                    vendor = " ".join(vendor_buf + left_vendor).strip()
                    vendor_buf = []
                    inv_seq += 1
                    cur = {"vendor": vendor, "amount": money(dollar[-1]),
                           "seq": inv_seq}
                    awaiting_header = True
                    continue

                # 4. left-aligned line: invoice header, or vendor (continued)
                if ws[0]["x0"] < HEADER_X:
                    header_toks = [w["text"] for w in ws if w["x0"] < RIGHT_X_MIN]
                    if not header_toks:
                        continue
                    if awaiting_header:
                        cur["inv_number"], cur["inv_desc"] = parse_header(header_toks)
                        awaiting_header = False
                    else:
                        vendor_buf.extend(header_toks)

    return rows, debug


def to_iso(d):
    """Convert M/D/YYYY -> YYYY-MM-DD; leave anything unexpected untouched."""
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", d or "")
    if not m:
        return d
    mo, da, yr = m.groups()
    return f"{yr}-{int(mo):02d}-{int(da):02d}"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit("Usage: python ap_listing_to_csv.py INPUT.pdf [OUTPUT.csv] [--debug]")
    src = Path(args[0])
    out = Path(args[1]) if len(args) > 1 else src.with_suffix(".csv")

    rows, debug = parse_pdf(src)
    for r in rows:
        r["Check_Date"] = to_iso(r["Check_Date"])

    fields = ["Invoice_ID", "Vendor", "Invoice_Number", "Invoice_Description",
              "Check_Date", "Invoice_Amount", "GL_Account", "Line_Description",
              "Line_Amount"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # reconciliation: group by the unique Invoice_ID so that distinct invoices
    # with blank or repeated invoice numbers are never collapsed together.
    by_inv = {}
    for r in rows:
        sid = r["Invoice_ID"]
        g = by_inv.setdefault(sid, {"sum": 0.0, "amount": r["Invoice_Amount"],
                                    "vendor": r["Vendor"],
                                    "number": r["Invoice_Number"], "seq": sid})
        g["sum"] += r["Line_Amount"] or 0
    mismatches = [
        g for g in by_inv.values()
        if g["amount"] != "" and abs(round(g["sum"], 2) - float(g["amount"])) > 0.01
    ]

    print(f"Wrote {len(rows)} line items across {len(by_inv)} invoices -> {out}")
    if mismatches:
        print(f"WARNING: {len(mismatches)} invoice(s) did not reconcile:")
        for g in mismatches:
            num = g["number"] or "(no number)"
            print(f"  {g['vendor']} [{num}]: "
                  f"line items sum {round(g['sum'], 2)} != invoice total {g['amount']}")
        if DEBUG:
            print("\n===== RAW LINES FOR NON-RECONCILING INVOICES =====")
            for g in mismatches:
                print(f"\n--- Invoice_ID {g['seq']}: {g['vendor']} "
                      f"[{g['number'] or 'no number'}] (total {g['amount']}) ---")
                for ln in debug.get(g["seq"], []):
                    print("   ", ln)
        else:
            print("Re-run with --debug to dump the raw lines for these invoices.")
    else:
        print("All invoices reconcile (line items sum to invoice totals).")


if __name__ == "__main__":
    main()
