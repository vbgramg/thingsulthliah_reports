"""
Mizoram VB-G RAM G Data Scraper & Aggregator
Extracts, cleans, and cross-links:
1. Active Job Cards (filtering out deleted marked with '*')
2. Muster Rolls (eMR) with work periods across all target villages
3. Incomplete Works by GP
4. Financial Statements (GP Summary + Master Works with eMR links)
5. Individual FTO Salary Records (all 183 batches, with ABPS Account Holder Name and UTR)
Outputs unified data to data/latest.json
"""

import collections
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

# The 19 specific user-requested villages/Panchayats
TARGET_VILLAGES_CONFIG = [
    "phulmawi", "tlungvel", "darlawng",
    "thingsulthliah - i", "thingsulthliah i", "thingsulthliah 1", "thingsulthliah-i",
    "thingsulthliah ii", "thingsulthliah 2", "thingsulthliah-ii",
    "tlangnuam", "thingsul tlangnuam", "thingsul-tlangnuam",
    "seling",
    "sesawng i", "sesawng 1", "sesawng-i",
    "sesawng ii", "sesawng 2", "sesawng-ii",
    "sesawng iii", "sesawng 3", "sesawng-iii"
]

def normalize_village(name):
    """Normalize village name for flexible case- and symbol-insensitive matching."""
    if not name:
        return ""
    s = name.lower().replace('-', ' ').replace('_', ' ')
    s = re.sub(r'\(.*?\)', '', s)
    s = s.replace('thingsulthliah 1', 'thingsulthliah i').replace('thingsulthliah-i', 'thingsulthliah i')
    s = s.replace('thingsulthliah 2', 'thingsulthliah ii').replace('thingsulthliah-ii', 'thingsulthliah ii')
    s = s.replace('sesawng 1', 'sesawng i').replace('sesawng-i', 'sesawng i')
    s = s.replace('sesawng 2', 'sesawng ii').replace('sesawng-ii', 'sesawng ii')
    s = s.replace('sesawng 3', 'sesawng iii').replace('sesawng-iii', 'sesawng iii')
    return ' '.join(s.split())

TARGET_NORM_SET = {normalize_village(v) for v in TARGET_VILLAGES_CONFIG}

def is_target_village(gp_name):
    """Check if a given GP/Village is in the user's 10 target villages."""
    return normalize_village(gp_name) in TARGET_NORM_SET

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

COOKIE_JAR = urllib.request.HTTPCookieProcessor()
URL_OPENER = urllib.request.build_opener(COOKIE_JAR)

def fetch_html(url, referer=None, timeout=25):
    """Safely fetch HTML with headers, cookies, and retries."""
    headers = dict(HEADERS)
    if referer:
        headers['Referer'] = referer
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            with URL_OPENER.open(req, timeout=timeout) as resp:
                return resp.read().decode('utf-8', errors='ignore')
        except Exception as e:
            if attempt == 2:
                print(f"[ERROR] Failed to fetch {url[:80]}... : {e}")
                return None
            time.sleep(1.2)
    return None

def scrape_job_cards(block_urls=None):
    """Module 1: Scrape Active Job Cards for the 19 user-selected villages (filter out deleted '*')."""
    print("[1/5] Scraping Active Job Cards for target 10 villages...")
    
    if not block_urls:
        block_urls = [
            ('THINGSULTHLIAH', 'https://vbgramgrep.dord.gov.in/VBGRAMG/app_issue.aspx?payload=fI4dEjG_1mWWPFiVn21f1oAhG9ZcxuWx0hkxnlWX7MrdOydOdBeyJvjMjJwO5-6VVOYEXNYchzRauB0sdW5sy9ULPgmRwztAhGbuvw3j8wjtaxXJZtYtUilBVoyFXNGB040b0Xisw1BcGDdmOOLJRuGfA2wY7A1x3Z3xCj54Upn-dVpoK9tu2X_PSaD7jWtj0RMIVRykNXL_K2VsJCktjMR9lTR9-1vULK8Lxu4gTfUU_ncDl8Nirdnhok3BytTTpOOqnSD_2B0v8V5ri1Hojdqzx8yFxgh_LACNdU8RfMQ')
        ]
        
    gp_list = []
    base_url = "https://vbgramgrep.dord.gov.in/VBGRAMG/"
    for block_name, b_url in block_urls:
        html = fetch_html(b_url)
        if not html:
            continue
        soup = BeautifulSoup(html, 'html.parser')
        for tr in soup.find_all('tr'):
            cols = [c.get_text(strip=True) for c in tr.find_all(['th', 'td'])]
            a = tr.find('a')
            if a and len(cols) > 1 and cols[0].isdigit():
                gp_name = cols[1]
                if is_target_village(gp_name):
                    href = a.get('href', '')
                    if not href.startswith('javascript'):
                        full_gp_url = urllib.parse.urljoin(base_url, href)
                        gp_list.append((block_name, gp_name, full_gp_url))
                    
    print(f"      -> Filtered to {len(gp_list)} target Gram Panchayats matching your selected villages.")
    
    def scrape_single_gp(item):
        block, gp, gp_url = item
        html = fetch_html(gp_url, timeout=20)
        if not html:
            return []
        soup = BeautifulSoup(html, 'html.parser')
        cards = []
        for t in soup.find_all('table'):
            rows = t.find_all('tr')
            if len(rows) > 10:
                for tr in rows:
                    cols = [c.get_text(strip=True) for c in tr.find_all(['th', 'td'])]
                    a = tr.find('a')
                    if a and len(cols) > 2:
                        jc_no = a.get_text(strip=True)
                        # EXCLUDE DELETED WITH '*'
                        if '*' in jc_no:
                            continue
                        cards.append({
                            "sno": cols[0],
                            "job_card_no": jc_no,
                            "head_of_household": cols[2] if len(cols) > 2 else "",
                            "block": block,
                            "panchayat": gp,
                            "dossier_link": urllib.parse.urljoin(base_url, a.get('href', ''))
                        })
                break
        return cards

    all_jobcards = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(scrape_single_gp, gp_item) for gp_item in gp_list]
        for f in as_completed(futures):
            res = f.result()
            all_jobcards.extend(res)
            
    print(f"      -> Successfully scraped {len(all_jobcards)} active Job Cards across target Panchayats.")
    return all_jobcards

def scrape_financial_and_works(url_financial):
    """
    Module 4 & 2: Scrape official Gram Panchayat Financial Summaries,
    Master Works, and Muster Roll disbursements for all 10 villages.
    """
    print("[2/5] Scraping Financial Statements & Master Works across target villages...")
    html = fetch_html(url_financial)
    if not html:
        return {"summaries": [], "works": [], "emrs": []}
    
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table')
    if not tables:
        return {"summaries": [], "works": [], "emrs": []}
    
    t = tables[-1]
    gp_summaries = []
    must_links = []
    
    for r in t.find_all('tr'):
        cells = [c.get_text(strip=True) for c in r.find_all(['th', 'td'])]
        if len(cells) > 1 and is_target_village(cells[1]):
            p_name = cells[1]
            summary = {
                "panchayat": p_name,
                "opening_balance": cells[2] if len(cells) > 2 and cells[2] else "0",
                "release_curr_year": cells[3] if len(cells) > 3 else "0",
                "unskilled_wage_exp": cells[9] if len(cells) > 9 else "0",
                "semi_skilled_exp": cells[10] if len(cells) > 10 else "0",
                "material_exp": cells[11] if len(cells) > 11 else "0",
                "total_exp": cells[16] if len(cells) > 16 else "0",
                "balance": cells[17] if len(cells) > 17 else "0",
                "payment_due": cells[22] if len(cells) > 22 else "0"
            }
            gp_summaries.append(summary)
            for a in r.find_all('a'):
                href = a.get('href', '')
                if 'mustworkexpn' in href:
                    clean_href = re.sub(r'^(\.\./)+', '', href)
                    full_must_url = urllib.parse.urljoin("https://vbgramgrep.dord.gov.in/VBGRAMG/", clean_href)
                    must_links.append((p_name, full_must_url))
                    
    print(f"      -> Extracted {len(gp_summaries)} GP financial summaries. Fetching master works...")
    
    def fetch_gp_mustwork(item):
        p_name, url = item
        sub_html = fetch_html(url, referer=url_financial, timeout=20)
        if not sub_html:
            return [], []
        sub_soup = BeautifulSoup(sub_html, 'html.parser')
        works = []
        emrs = []
        current_work = None
        
        for table in sub_soup.find_all('table'):
            for tr in table.find_all('tr'):
                cells = [c.get_text(strip=True) for c in tr.find_all(['th', 'td'])]
                if not cells:
                    continue
                text_0 = cells[0]
                if 'Work Name:' in text_0:
                    raw_work = text_0.replace('Work Name:', '').strip()
                    m_code = re.search(r'\((22[0-9A-Za-z/_-]+)\)', raw_work)
                    if m_code:
                        w_code = m_code.group(1).strip()
                        w_name = raw_work[:m_code.start()].strip()
                    else:
                        w_code = ''
                        w_name = raw_work
                    current_work = {
                        "panchayat": p_name,
                        "work_code": w_code,
                        "work_name": w_name,
                        "sanctioned_amount": "N/A",
                        "wage_expenditure": 0,
                        "material_expenditure": "0",
                        "emr_links": []
                    }
                    works.append(current_work)
                elif current_work and len(cells) >= 3 and cells[0].isdigit():
                    ms_no = cells[0]
                    dt = cells[1]
                    amt = float(cells[2]) if cells[2].replace('.', '', 1).isdigit() else 0
                    current_work["wage_expenditure"] += amt
                    a_tag = tr.find('a')
                    raw_href = a_tag.get('href', '') if a_tag else ''
                    clean_href = re.sub(r'^(\.\./)+', '', raw_href)
                    link = urllib.parse.urljoin("https://vbgramgrep.dord.gov.in/VBGRAMG/", clean_href) if raw_href else ''
                    emr_obj = {
                        "label": f"eMR {ms_no}",
                        "muster_roll_no": ms_no,
                        "date_of_payment": dt,
                        "amount": cells[2],
                        "url": link
                    }
                    current_work["emr_links"].append(emr_obj)
                    emrs.append({
                        "muster_roll_no": ms_no,
                        "district": "AIZAWL",
                        "block": "THINGSULTHLIAH",
                        "gp": p_name,
                        "agency": "Gram Panchayat",
                        "link": link,
                        "work_code": current_work["work_code"],
                        "work_name": current_work["work_name"],
                        "date_from": dt,
                        "date_to": dt,
                        "work_month": dt,
                        "amount": cells[2]
                    })
        return works, emrs

    all_works = []
    all_emrs = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(fetch_gp_mustwork, it) for it in must_links]
        for f in as_completed(futs):
            w_list, e_list = f.result()
            all_works.extend(w_list)
            all_emrs.extend(e_list)
            
    print(f"      -> Successfully extracted {len(all_works)} Master Works and {len(all_emrs)} Muster Rolls across all 10 villages.")
    return {
        "summaries": gp_summaries,
        "works": all_works,
        "emrs": all_emrs
    }

def enrich_emr_working_dates(fin_data):
    """
    Enrich eMRs with authoritative working period dates ('date_from', 'date_to')
    scraped directly from official Musternew.aspx sheets, keyed by UNIQUE eMR URL.
    """
    cache_file = os.path.join(os.path.dirname(__file__), "data", "emr_url_dates_cache.json")
    cache = {}
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}
            
    emrs = fin_data.get('emrs', [])
    to_fetch = [m for m in emrs if m.get('link') and (m['link'] not in cache or not cache[m['link']].get('date_from'))]
    
    if to_fetch:
        print(f"      -> Fetching authoritative working period dates for {len(to_fetch)} new eMR URLs...")
        def fetch_date(item):
            url = item.get('link', '')
            if not url:
                return url, "", ""
            for attempt in range(3):
                try:
                    req = urllib.request.Request(url, headers=HEADERS)
                    with urllib.request.urlopen(req, timeout=12) as resp:
                        html = resp.read().decode('utf-8', errors='ignore')
                        soup = BeautifulSoup(html, 'html.parser')
                        s_from = soup.find('span', id='ContentPlaceHolder1_lbldatefrom')
                        s_to = soup.find('span', id='ContentPlaceHolder1_lbldateto')
                        d_from = s_from.get_text(strip=True) if s_from else ""
                        d_to = s_to.get_text(strip=True) if s_to else ""
                        if not d_from:
                            m = re.search(r'Date\s*From[^\d]*(\d{1,2}/\d{1,2}/\d{4})', html, re.I)
                            if m: d_from = m.group(1)
                        if not d_to:
                            m = re.search(r'Date\s*To[^\d]*(\d{1,2}/\d{1,2}/\d{4})', html, re.I)
                            if m: d_to = m.group(1)
                        return url, d_from, d_to
                except Exception:
                    if attempt < 2:
                        time.sleep(1.0)
            return url, "", ""
            
        with ThreadPoolExecutor(max_workers=20) as ex:
            futures = [ex.submit(fetch_date, m) for m in to_fetch]
            for fut in as_completed(futures):
                url, d_from, d_to = fut.result()
                if d_from:
                    cache[url] = {"date_from": d_from, "date_to": d_to}
                    
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)
        except Exception:
            pass

    # Enrich eMRs
    for m in emrs:
        url = m.get('link', '')
        c = cache.get(url, {})
        d_from = c.get('date_from', '')
        d_to = c.get('date_to', '')
        
        # Preserve payment voucher date
        if 'payment_date' not in m or not m['payment_date']:
            m['payment_date'] = m.get('date_from', '')
            
        if d_from:
            m['date_from'] = d_from
            m['date_to'] = d_to
            m['work_period'] = f"{d_from} – {d_to}" if d_to else d_from
            parts = d_from.split('/')
            if len(parts) == 3:
                try:
                    dt = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
                    m['work_month'] = dt.strftime('%B %Y')
                except Exception:
                    m['work_month'] = 'Other'
            else:
                m['work_month'] = 'Other'
        else:
            m['work_period'] = m.get('payment_date', '')
            m['work_month'] = 'Other'
            
    # Enrich financial_statement master works emr_links
    for w in fin_data.get('works', []):
        for l in w.get('emr_links', []):
            url = l.get('url', '')
            c = cache.get(url, {})
            if c and c.get('date_from'):
                l['date_from'] = c['date_from']
                l['date_to'] = c['date_to']
                l['work_period'] = f"{c['date_from']} – {c['date_to']}"

def scrape_incomplete_works(url):
    """Module 3: Scrape Incomplete Works by GP (Current FY and Total) with drilldown works."""
    print("[3/5] Scraping Incomplete Works & Ongoing Projects...")
    html = fetch_html(url)
    if not html:
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    works = []
    
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if len(rows) < 4:
            continue
        for row in rows:
            tds = row.find_all(['th', 'td'])
            cols = [c.get_text(strip=True) for c in tds]
            if len(cols) >= 22 and cols[0].isdigit():
                panchayat = cols[1]
                if not is_target_village(panchayat):
                    continue
                
                # Official VB-G RAM G Column Indices:
                # Cols 14-17: FY 2026-2027 (Current Year)
                # Cols 18-21: Cumulative Grand Total
                tot_started = cols[18]
                tot_completed = cols[19]
                tot_incomplete = cols[20]
                tot_rate = cols[21] if len(cols) > 21 else "0"

                fy_started = cols[14]
                fy_completed = cols[15]
                fy_incomplete = cols[16]
                fy_rate = cols[17] if len(cols) > 17 else "0"
                
                # Check for drill-down link (on incomplete count or row)
                a_tag = tds[16].find('a') if len(tds) > 16 and tds[16].find('a') else None
                if not a_tag and len(tds) > 20:
                    a_tag = tds[20].find('a')
                if not a_tag:
                    a_tag = row.find('a')
                link = urllib.parse.urljoin(url, a_tag.get('href', '')) if a_tag else ""
                
                works.append({
                    "sno": cols[0],
                    "panchayat": panchayat,
                    "works_started": tot_started,
                    "works_completed": tot_completed,
                    "not_completed": tot_incomplete,
                    "completion_rate": tot_rate,
                    "fy_started": fy_started,
                    "fy_completed": fy_completed,
                    "fy_incomplete": fy_incomplete,
                    "fy_rate": fy_rate,
                    "details_link": link,
                    "ongoing_works": []
                })

    # Fetch ongoing work items from drill-down links concurrently
    def fetch_drilldown(item):
        link = item.get("details_link")
        if not link:
            return
        b_html = fetch_html(link, referer=url, timeout=15)
        if not b_html:
            return
        b_soup = BeautifulSoup(b_html, 'html.parser')
        tables = b_soup.find_all('table')
        if not tables:
            return
        d_table = tables[-1]
        for r in d_table.find_all('tr'):
            cells = [c.get_text(strip=True) for c in r.find_all(['th', 'td'])]
            if cells and cells[0].isdigit():
                raw_name = cells[1] if len(cells) > 1 else ''
                status = cells[2] if len(cells) > 2 else ''
                agency = cells[3] if len(cells) > 3 else ''
                category = cells[4] if len(cells) > 4 else ''
                est_cost = cells[5] if len(cells) > 5 else '0'
                m_code = re.search(r'\((22[0-9A-Za-z/_-]+)\)', raw_name)
                code = m_code.group(1) if m_code else ''
                name = raw_name[:m_code.start()].strip() if m_code else raw_name
                item["ongoing_works"].append({
                    "sno": cells[0],
                    "work_name": name,
                    "work_code": code,
                    "status": status,
                    "agency": agency,
                    "category": category,
                    "estimated_cost_lakhs": est_cost
                })

    with ThreadPoolExecutor(max_workers=10) as ex:
        list(ex.map(fetch_drilldown, works))
                
    total_ongoing = sum(len(w.get('ongoing_works', [])) for w in works)
    print(f"      -> Successfully extracted {len(works)} Panchayat summaries and {total_ongoing} detailed ongoing projects.")
    return works

def scrape_fto_data(url, valid_jc_set=None):
    """
    Module 5: Scrape ALL 183 FTO batches, extract ABPS Account Holder Name,
    and index full payment passbook for workers across all 10 target villages.
    """
    print("[4/5] Scraping FTO Payment Records across all 183 batches...")
    html = fetch_html(url)
    if not html:
        return {"fto_batches": [], "worker_passbook": {}}
    
    soup = BeautifulSoup(html, 'html.parser')
    fto_batches = []
    
    # Locate FTO list table
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if len(rows) < 3:
            continue
        for row in rows:
            cols = [c.get_text(strip=True) for c in row.find_all(['th', 'td'])]
            a_tag = row.find('a')
            if a_tag and len(cols) >= 6 and cols[0].isdigit():
                fto_no = a_tag.get_text(strip=True)
                link = urllib.parse.urljoin(url, a_tag.get('href', ''))
                sign_date = cols[5] if len(cols) > 5 else ""
                fto_batches.append({
                    "sno": cols[0],
                    "fto_no": fto_no,
                    "sign_date": sign_date,
                    "link": link
                })
                
    print(f"      -> Discovered {len(fto_batches)} FTO batches. Parsing worker payments...")
    
    worker_passbook = {}  # Indexed by clean Job Card No
    
    def process_single_fto_batch(batch):
        b_html = fetch_html(batch['link'], referer=url, timeout=20)
        if not b_html:
            return []
        b_soup = BeautifulSoup(b_html, 'html.parser')
        tables = b_soup.find_all('table')
        if len(tables) < 2:
            return []
        w_table = tables[1]
        w_rows = w_table.find_all('tr')
        if not w_rows:
            return []
        headers = [c.get_text(strip=True) for c in w_rows[0].find_all(['th', 'td'])]
        records = []
        for r in w_rows[1:]:
            cols = [c.get_text(strip=True) for c in r.find_all(['th', 'td'])]
            if len(cols) < 12 or not cols[0].isdigit():
                continue
            row_dict = dict(zip(headers, cols))
            records.append((batch, row_dict))
        return records

    # Process all batches concurrently with 14 workers
    with ThreadPoolExecutor(max_workers=14) as executor:
        futures = [executor.submit(process_single_fto_batch, b) for b in fto_batches]
        for f in as_completed(futures):
            for batch, row_dict in f.result():
                raw_jc = row_dict.get('Job Card No.(Panchayat Name)', '')
                m_jc = re.search(r'([A-Za-z0-9/_-]+)(?:\(([^)]+)\))?', raw_jc)
                if m_jc:
                    clean_jc = m_jc.group(1).replace('*', '').strip()
                    panchayat = m_jc.group(2).strip() if m_jc.group(2) else ""
                else:
                    clean_jc = raw_jc.replace('*', '').strip()
                    panchayat = ""
                    
                # Filter to target villages only
                if valid_jc_set and clean_jc not in valid_jc_set:
                    if not is_target_village(panchayat):
                        continue
                elif not is_target_village(panchayat):
                    continue
                        
                worker_name = row_dict.get('Applicant Name', '')
                primary_holder = row_dict.get('Name of Primary Account Holder', '')
                
                # AUTHORITATIVE BENEFICIARY RECIPIENT:
                abp_recipient = row_dict.get('Paid in account of(in case of ABP)', '').strip()
                abp_bank = row_dict.get('Paid in Bank(in case of ABP)', '').strip()
                
                credited_to_name = abp_recipient if abp_recipient else primary_holder
                bank_name = abp_bank if abp_bank else row_dict.get('Postoffice/Bank Name', 'Mizoram Rural Bank')
                branch_name = row_dict.get('Branch Name', '')
                
                tx_date = row_dict.get('Transaction Date', '')
                processed_date = row_dict.get('Processed Date', '')
                amount = row_dict.get('Credit Amount(In Rs.)') or row_dict.get('Amount to be credited (In Rs.)', '0')
                status = row_dict.get('Status', 'Pending')
                utr_no = row_dict.get('UTR No.', '')
                wagelist_no = row_dict.get('Wagelist No.', '')
                ref_no = row_dict.get('Reference No.', '')
                rejection_reason = row_dict.get('Rejection Reason', '')
                
                work_month = ""
                if tx_date:
                    try:
                        dt = datetime.strptime(tx_date, '%d/%m/%Y')
                        work_month = dt.strftime('%B %Y')
                    except Exception:
                        work_month = tx_date
                        
                payment_record = {
                    "work_month": work_month,
                    "work_name": "VB-G RAM G Community Works",
                    "work_period": tx_date,
                    "amount": amount,
                    "status": status,
                    "processed_date": processed_date,
                    "transaction_date": tx_date,
                    "credited_to_name": credited_to_name,
                    "bank_name": bank_name,
                    "branch_name": branch_name,
                    "utr_no": utr_no,
                    "wagelist_no": wagelist_no,
                    "reference_no": ref_no,
                    "fto_no": batch['fto_no'],
                    "fto_link": batch['link'],
                    "rejection_reason": rejection_reason
                }
                
                if clean_jc not in worker_passbook:
                    worker_passbook[clean_jc] = {
                        "job_card_no": clean_jc,
                        "worker_name": worker_name,
                        "panchayat": panchayat,
                        "payments": []
                    }
                worker_passbook[clean_jc]["payments"].append(payment_record)
        
    print(f"      -> Built passbook for {len(worker_passbook)} unique workers across target villages.")
    return {"fto_batches": fto_batches, "worker_passbook": worker_passbook}

def clean_job_card_no(s):
    if not s:
        return ""
    m = re.search(r'(MZ-[0-9]{2}-[0-9]{3}-[0-9]{3}-[0-9]{3}/[0-9]+)', s)
    if m:
        return m.group(1).strip()
    return re.sub(r'[^A-Za-z0-9/_-]', '', s).strip()

def enrich_passbook_with_working_periods(passbook_map, fin_data=None):
    """
    For each payment record, resolve the authoritative Working Period and Work Month
    from the Wagelist No. and Worker Job Card (cross-checked against the eMR sheet data).
    Uses data/wagelist_work_cache.json.
    """
    cache_path = os.path.join(os.path.dirname(__file__), "data", "wagelist_work_cache.json")
    wl_cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                wl_cache = json.load(f)
        except Exception:
            wl_cache = {}

    wagelist_to_work = wl_cache.get('wagelist_to_work', {})
    worker_wl_to_work = wl_cache.get('worker_wl_to_work', {})

    matched_count = 0
    fallback_count = 0

    for jc, w in passbook_map.items():
        c_jc = clean_job_card_no(jc)
        for p in w.get('payments', []):
            wl = p.get('wagelist_no', '').strip()
            tx_date = p.get('transaction_date') or p.get('work_period', '')
            p['payment_date'] = tx_date

            match = None
            if c_jc and wl:
                key = f"{c_jc}___{wl}"
                match = worker_wl_to_work.get(key)

            if not match and wl:
                match = wagelist_to_work.get(wl)

            if match:
                p['work_month'] = match.get('work_month', '')
                p['work_period'] = match.get('work_period', '')
                p['date_from'] = match.get('date_from', '')
                p['date_to'] = match.get('date_to', '')
                p['work_name'] = match.get('work_name', '')
                p['work_code'] = match.get('work_code', '')
                p['muster_roll_no'] = match.get('muster_roll_no', '')
                p['emr_link'] = match.get('link', '')
                p['wl_matched'] = True
                matched_count += 1
            else:
                p['wl_matched'] = False
                fallback_count += 1
                if tx_date and '/' in tx_date:
                    parts = tx_date.split('/')
                    if len(parts) == 3:
                        try:
                            dt = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
                            p['work_month'] = dt.strftime('%B %Y')
                        except Exception:
                            pass

    print(f"      -> Wage-list cross-check: {matched_count} payments matched to true eMR working periods, {fallback_count} fell back to payment date.")

def run_pipeline():
    """Main pipeline executing all modules and saving to data/latest.json."""
    start_time = time.time()
    print("="*60)
    print("  THINGSULTHLIAH RD BLOCK VB-G RAM G DATA AGGREGATION")
    print(f"  Execution Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    URL_FINANCIAL = "https://vbgramgrep.dord.gov.in/VBGRAMG/citizen_html/funddisreport.aspx?payload=sg2yfjnF8VAQ2q5I7c2WaZWlLv5O14V_3Wo7_Iwq_Q8U1oJ0cLGKQqdc7Z01ElaL67iq0ABeG5-e-m8uGJKwJKnPeHvONhS7jvc6whDnquzxuYehRbnNKY4WU0vSEGRnugwlpb1n8I54fTx5OWs2P3MGIKHpGr5XWbbNfOIWSOA2Jl1uBEcy0AaUBly2sfqOqnjznPssQXHeNG263ysajjvRkIhVov0_tMcvNljeAUQ6X9KRIjh8Jt9v0UJ2s8Re"
    URL_INCOMPLETE = "https://vbgramgrep.dord.gov.in/VBGRAMG/takenup_compwrk.aspx?payload=G-UVLT1FagC8uTppD76rp3KLX3mBlBqVP4HqiCyIQ0PFnmqJLY4Arwf3Qi9AgPROExjireuM25o_uFzkeuUJPjlo367hlq8C0Nc0N6biZCUAHa5IXZFpAFmb0ttsQH_q_MPWtsjIU1FI9gYrErY4hMCV9B6nEGB14_QhK4404D7XptiefoCCR3fdovgR2__c3ZJwt16mI2N5G0A6qvMVBDW8VzbiR3rfIAzL4lxb2PxMDUEexADihqd8JjTh-2FLxOEBiSiQFEmztNmUtGUE_PeEm7uxF8qN8WjJbIPc1OA"
    URL_FTO = "https://vbgramgrep.dord.gov.in/VBGRAMG/FTO/fto_sign_detail.aspx?payload=S8PVx6KrcN2L5Sq7rfaKNG6IPaqZw0xKnH3rh0rZgwMMeThsr7eUZsNaHSOaEQn4hziUB86UyVLoSzs05ltekaM_T0kPqfLBQRRbFjaqeKcNam979FahxdEU153y3vKeSr6AUxK8rKtC0LESBe9OGcYaMPgcbPf3rCZtw8PiyYFJlYm-Q_HcJ_R2Cvn2vznkzKePxWJQS5J1I21GlZt8LJvGi7z0CSu-8VBmNlint_RHrsXyTolThpnMFZJ_1NXX82mwUU3rvvoII3YxwXWYlQyY71uO5Y7AIOyIGWCT-JLlAXfyH_uoOuvyV1-9qCBi"
    
    # Step 1: Active Job Cards across the 10 target Panchayats
    active_jcs = scrape_job_cards()
    valid_jc_set = {j['job_card_no'] for j in active_jcs}
    
    # Step 2: Financial Statements & Master Works & eMRs
    fin_data = scrape_financial_and_works(URL_FINANCIAL)
    enrich_emr_working_dates(fin_data)
    
    # Step 3: Incomplete Works
    incomplete_works = scrape_incomplete_works(URL_INCOMPLETE)
    
    # Step 4: FTO Payments across all 183 batches
    fto_data = scrape_fto_data(URL_FTO, valid_jc_set=valid_jc_set)

    # Step 4b: Cross-check every payment's Wagelist No. against eMR working periods
    # so the passbook shows the month of WORK, not the month of PAYMENT.
    enrich_passbook_with_working_periods(fto_data['worker_passbook'], fin_data)
    
    # Assemble core dashboard JSON payload (compact, sub-second load)
    core_data = {
        "metadata": {
            "title": "Mizoram VB-G RAM G Analytics Dashboard",
            "state": "MIZORAM",
            "district": "AIZAWL",
            "last_updated": datetime.now().isoformat(),
            "financial_year": "2026-2027",
            "stats": {
                "active_jobcards_count": len(active_jcs),
                "muster_rolls_count": len(fin_data['emrs']),
                "incomplete_works_count": len(incomplete_works),
                "financial_works_count": len(fin_data['works']),
                "indexed_workers_count": len(fto_data['worker_passbook']),
                "fto_batches_count": len(fto_data['fto_batches'])
            }
        },
        "job_cards": active_jcs,
        "muster_rolls": fin_data['emrs'],
        "incomplete_works": incomplete_works,
        "financial_summary": fin_data['summaries'],
        "financial_statement": fin_data['works']
    }

    # Extract deduplicated FTO links table for passbook
    fto_links = {}
    for batch in fto_data.get('fto_batches', []):
        if batch.get('fto_no') and batch.get('link'):
            fto_links[batch['fto_no']] = batch['link']

    passbook_data = {
        "fto_links": fto_links,
        "worker_passbook": fto_data['worker_passbook']
    }
    
    output_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(output_dir, exist_ok=True)
    latest_file = os.path.join(output_dir, "latest.json")
    passbook_file = os.path.join(output_dir, "passbook.json")
    
    with open(latest_file, "w", encoding="utf-8") as f:
        json.dump(core_data, f, ensure_ascii=False, separators=(',', ':'))

    with open(passbook_file, "w", encoding="utf-8") as f:
        json.dump(passbook_data, f, ensure_ascii=False, separators=(',', ':'))
        
    duration = time.time() - start_time
    print("="*60)
    print(f" [SUCCESS] Core data exported to {latest_file} ({os.path.getsize(latest_file)/1024/1024:.2f} MB)")
    print(f" [SUCCESS] Passbook data exported to {passbook_file} ({os.path.getsize(passbook_file)/1024/1024:.2f} MB)")
    print(f" [STATS] Active Cards: {len(active_jcs)} | eMRs: {len(fin_data['emrs'])} | Master Works: {len(fin_data['works'])} | Passbook Workers: {len(fto_data['worker_passbook'])}")
    print(f" [TIME] Completed in {duration:.2f} seconds.")
    print("="*60)

    # Automatically run wagelist work reconciliation and reverse chronological sorting
    print("[POST-PROCESS] Reconciling Wagelists & Sorting Worker Passbooks...")
    try:
        import sync_passbook_working_months
        sync_passbook_working_months.main()
    except Exception as e:
        print(f"[WARN] Error running sync_passbook_working_months: {e}")

if __name__ == "__main__":
    run_pipeline()
