# Mizoram VB-G RAM G Report Portal & Worker Passbook (Thingsulthliah RD Block)

A lightweight, automated web application and data aggregator for **Thingsulthliah RD Block (Aizawl District, Mizoram)**, designed to provide a fast, clean, and mobile-friendly community mirror for VB-G RAM G (MGNREGA) data.

---

## Target Villages (10 Panchayats)

The application and scraper are focused on the following 10 villages/Panchayats under Thingsulthliah RD Block:
> **Darlawng, Phulmawi, Seling, SESAWNG I, SESAWNG II, SESAWNG III, Thingsulthliah - I, Thingsulthliah II, Tlangnuam, Tlungvel.**

---

## Features

1. **Global Village Selector Bar (Controls All Tabs)**
   - Located at the top of the application.
   - Switch between **"All My 10 Villages (Combined)"** or any single village.
   - All tabs (Job Cards, Muster Rolls, Incomplete Works, Financials) dynamically filter and recalculate their KPIs and counters based on the selected village.

2. **Active Job Cards Register**
   - Automatically filters out all deleted job cards marked with an asterisk (`*`).
   - Fast client-side pagination (25, 50, 100, 250 per page) and instant search by Job Card No. or Household Head.
   - One-click access to official government dossiers and the embedded Worker Passbook.

3. **Integrated Worker Payment Passbook**
   - Click `[💳 View Passbook]` directly next to any active Job Card to launch the worker's payment history modal.
   - Tracks monthly wage disbursement status: 🟢 **Credited**, 🟡 **Pending**, or 🔴 **Rejected**.
   - Explicitly displays **`Paid in account of (in case of ABP)`** to confirm the Aadhaar-linked beneficiary receiving DBT funds.
   - Shows Bank Name, Branch, UTR Reference Number, Processed Date, and direct link to the official signed FTO.

4. **Muster Rolls (eMR)**
   - Searchable directory of official eMR slips with exact **Work Description**, **Work Code**, and **Labor Period** (`Date From` to `Date To` + `Month`).

5. **Incomplete Works Tracker**
   - Tracks works started vs. completed vs. incomplete across the 10 Panchayats with progress KPIs and official drill-down links.

6. **Financial Master Work Statements**
   - Overview of work sanction budgets, wage disbursements, and material expenditure with direct eMR references.

---

## Running Locally

To test the application locally:
1. Open terminal in this folder:
   ```bash
   pip install beautifulsoup4
   python scraper.py
   python sync_passbook_working_months.py
   ```
2. Start a local server:
   ```bash
   python -m http.server 8000
   ```
3. Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## Deployment & Automation (GitHub Actions + GitHub Pages)

1. Push this repository to GitHub.
2. In GitHub repository **Settings** $\rightarrow$ **Actions** $\rightarrow$ **General** $\rightarrow$ **Workflow permissions**, select **"Read and write permissions"** and Save.
3. In GitHub repository **Settings** $\rightarrow$ **Pages**, set **Source** to `Deploy from a branch`, choose branch `main` and folder `/ (root)`.
4. The workflow in `.github/workflows/daily-sync.yml` automatically triggers twice daily (00:25 and 12:25 UTC) to update all records.
