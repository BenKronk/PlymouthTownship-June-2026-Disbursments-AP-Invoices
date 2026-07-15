# PlymouthTownship-June-2026-Disbursments-AP-Invoices
# Plymouth Township AP Disbursements Dashboard

An interactive Power BI dashboard as well as a static Tableau dashboard summarizing accounts-payable disbursements to vendors
for the Charter Township of Plymouth, Michigan, built from the township's public
Board of Trustees packet. The project covers the full pipeline: extracting structured
data from a layout-oriented PDF, validating it against the source, mapping municipal
account codes to readable names, and modeling it for interactive analysis.

---

## Overview

Michigan municipalities publish their accounts-payable activity in board meeting packets
as an **AP Invoice Listing / Board Report** a paginated PDF laid out for reading, not
for analysis. This project turns one of those reports (the packet for the June 23, 2026
Regular Meeting) into a clean dataset and a dashboard that lets a viewer explore where the
money went, by fund, by department, and by vendor.

All source data is public record. The dashboard presents it in an aggregated, analytical
form rather than a searchable ledger of individuals (see **Privacy handling** below).

---

## Features

- **Summary KPI cards** vendors, invoices, GL line items, total disbursements, and
  average invoice, all responsive to slicer selections.
- **Slicers** for Vendor, Fund, and Department, so any view can be filtered to a single
  entity or combination.
- **Disbursements by Department** horizontal bar ranking of spend by township activity.
- **Disbursements by Vendor** horizontal bar ranking of spend by payee.
- **Decomposition Tree** interactive drill-down from total â†’ Fund â†’ Department â†’ Vendor,
  the analytical centerpiece.
- **Disbursements by Fund** proportional breakdown across the township's funds
  (Water/Sewer, General, Solid Waste, and others).

---

## Data source

- **Document:** AP Invoice Listing â€“ Board Report, Charter Township of Plymouth Board of
  Trustees packet, Regular Meeting of June 23, 2026.
- **Nature:** Public financial record, published by the township.
- **Scope of this build:** 183 invoices, 492 GL line items, 95 vendors,
  **$967,729.53** total disbursed.

> The packet bundles three separate check runs (dated 6/10, 6/17, and 6/23). The dashboard
> reports them together as one period; the KPI cards make the composition explicit.

---

## Data pipeline

The report is a hierarchical layout (vendor | invoice | GL line items), not a table, so it
can't be read directly by a BI tool. The pipeline handles that:

1. **Extraction.** A custom Python parser (`pdfplumber`) reads the PDF and emits one tidy
   row per GL line item, with vendor, invoice number, check date, invoice total, GL
   account, line description, and line amount. The parser handles the report's quirks:
   sub-point word spacing, accounting-style credits shown in parentheses, and line items
   that collide with the page footer at page breaks.
2. **Validation.** A built-in reconciliation check confirms that each invoice's line items
   sum to its stated total, and that the sum of all invoice totals matches the document's
   own printed "Total Amount to be Disbursed." Both tie out to the penny
   (**$967,729.53**), so the dataset is provably complete nothing dropped or duplicated.
3. **Transformation.** The GL account (`101-336-773.000`) is split into its three segments â€”
   **Fund**, **Department/Activity**, and **Object** and each is joined to a lookup so the
   dashboard shows readable names instead of codes.
4. **Privacy handling.** Employee surnames appearing on credit-card reimbursement lines are
   masked to a neutral token, so the dashboard analyzes spending by category without
   surfacing named individuals.
5. **Model & visualize.** The cleaned CSV is loaded into Power BI, shaped in Power Query,
   and measured in DAX.

---

## Key design decisions

- **Grain guard.** The dataset is at line-item grain, so invoice totals repeat across an
  invoice's lines. All spend measures use `SUM(Line_Amount)`; invoice counts use
  `DISTINCTCOUNT(Invoice_ID)`. Summing the repeated invoice total would double-count.
- **Explicit averages.** "Average invoice" is defined as total Ã· distinct invoices, computed
  by iterating invoices not by averaging distinct dollar amounts (which would silently
  drop repeated values) and not by averaging per vendor (a different figure). The denominator
  is stated so the number isn't ambiguous.
- **Code mapping from the state standard.** Fund, department, and object names come from the
  **Michigan Uniform Chart of Accounts (UCA)**, which all local units are required to use.
  The three code sets are kept as **separate lookups** joined to separate segments because
  the same digits mean different things in different positions (e.g., `262` is the Federal
  Forfeiture *fund* but the Elections *activity*).

---

## Tech stack

- **Python** (`pdfplumber`) PDF extraction and reconciliation
- **Power BI** data model and visualization
- **Power Query (M)** shaping and name-masking transforms
- **DAX** measures
- **Michigan Uniform Chart of Accounts** code-to-name reference

---

## Reproducing the dataset

```bash
pip install pdfplumber
python ap_listing_to_csv.py "AP_Invoice_Listing.pdf"
```

The script writes a tidy CSV next to the input PDF and prints a reconciliation summary. If
any invoice fails to reconcile, it names the vendor and the dollar gap so the issue is
traceable rather than silent. Load the resulting CSV into Power BI to refresh the model.

---

## Notes & limitations

- **Public record.** All figures come from a published township document. This is an
  independent educational/portfolio project and is **not** an official township product or
  affiliated with the Charter Township of Plymouth.
- **Bundled period.** The build covers three check runs from June 2026 reported together;
  it is a point-in-time snapshot, not a running time series.
- **Locally defined codes.** The UCA leaves certain code ranges "OPEN" for local units to
  name themselves. A few of the township's codes are therefore locally defined and are
  labeled from the township's own usage rather than the state chart; these should be
  confirmed against the township's adopted budget before being treated as authoritative.
- **Non-departmental postings.** Some line items post to balance-sheet activity codes
  (payroll withholdings, union dues, retirement contributions) rather than to an operating
  department; these appear under the department view and are best read as non-departmental.

---

## License

Code released under the MIT License. Underlying financial data is public record of the
Charter Township of Plymouth.

