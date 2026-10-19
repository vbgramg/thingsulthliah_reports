"""
Cross-check all Wagelist Numbers and Worker Job Cards against authoritative
eMR muster roll sheets to resolve the TRUE physical working period and month
for all payments in data/passbook.json.
"""

import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LATEST_JSON = os.path.join(BASE_DIR, "data", "latest.json")
PASSBOOK_JSON = os.path.join(BASE_DIR, "data", "passbook.json")
WL_CACHE_FILE = os.path.join(BASE_DIR, "data", "wagelist_work_cache.json")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

def clean_jc(s):
    if not s:
        return ""
    m = re.search(r'(MZ-[0-9]{2}-[0-9]{3}-[0-9]{3}-[0-9]{3}/[0-9]+)', s)
    if m:
        return m.group(1).strip()
    return re.sub(r'[^A-Za-z0-9/_-]', '', s).strip()

def parse_emr_sheet(m):
    url = m.get('link', '')
    if not url:
        return None
        
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=14) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
                soup = BeautifulSoup(html, 'html.parser')
                
                s_from = soup.find('span', id='ContentPlaceHolder1_lbldatefrom')
                d_from = s_from.get_text(strip=True) if s_from else m.get('date_from', '')
                s_to = soup.find('span', id='ContentPlaceHolder1_lbldateto')
                d_to = s_to.get_text(strip=True) if s_to else m.get('date_to', '')
                
                # Derive month
                mon = 'Other'
                parts = d_from.split('/')
                if len(parts) == 3:
                    try:
                        dt = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
                        mon = dt.strftime('%B %Y')
                    except Exception:
                        mon = m.get('work_month', 'Other')
                else:
                    mon = m.get('work_month', 'Other')
                    
                w_period = f"{d_from} – {d_to}" if d_to else d_from
                
                emr_info = {
                    "muster_roll_no": m.get('muster_roll_no', ''),
                    "gp": m.get('gp', ''),
                    "block": m.get('block', 'THINGSULTHLIAH'),
                    "work_name": m.get('work_name', ''),
                    "work_code": m.get('work_code', ''),
                    "date_from": d_from,
                    "date_to": d_to,
                    "work_period": w_period,
                    "work_month": mon,
                    "link": url
                }
                
                # Extract workers and wagelists from rows
                worker_wls = []
                unique_wls = set()
                for tr in soup.find_all('tr'):
                    text = tr.get_text(separator=' ')
                    found_wls = re.findall(r'(220100[0-9A-Za-z]+WL\d+)', text)
                    found_jcs = re.findall(r'(MZ-[0-9]{2}-[0-9]{3}-[0-9]{3}-[0-9]{3}/[0-9]+)', text)
                    for wl in found_wls:
                        unique_wls.add(wl)
                    if found_wls and found_jcs:
                        for j in found_jcs:
                            for wl in found_wls:
                                worker_wls.append((j, wl))
                                
                return emr_info, list(unique_wls), worker_wls
        except Exception:
            if attempt < 2:
                time.sleep(1.0)
    return None

def main():
    print("=" * 60)
    print("  RESOLVING PASSBOOK WORKING PERIODS FROM eMR WAGELISTS")
    print("=" * 60)
    
    with open(LATEST_JSON, "r", encoding="utf-8") as f:
        latest_data = json.load(f)
        
    with open(PASSBOOK_JSON, "r", encoding="utf-8") as f:
        passbook_data = json.load(f)
        
    emrs = latest_data.get('muster_rolls', [])
    print(f"Loaded {len(emrs)} eMR muster rolls.")
    
    # Check if cache exists
    wl_cache = {}
    if os.path.exists(WL_CACHE_FILE):
        try:
            with open(WL_CACHE_FILE, "r", encoding="utf-8") as f:
                wl_cache = json.load(f)
            print(f"Loaded existing cache with {len(wl_cache.get('wagelist_to_work', {}))} Wagelist mappings.")
        except Exception:
            wl_cache = {}
            
    wagelist_to_work = wl_cache.get('wagelist_to_work', {})
    worker_wl_to_work = wl_cache.get('worker_wl_to_work', {})
    
    # Check if we need to scrape
    # Get all wagelist numbers in passbook
    passbook_wls = set()
    worker_passbook = passbook_data.get('worker_passbook', {})
    for jc, w in worker_passbook.items():
        for p in w.get('payments', []):
            wl = p.get('wagelist_no', '').strip()
            if wl:
                passbook_wls.add(wl)
                
    missing_wls = [wl for wl in passbook_wls if wl not in wagelist_to_work]
    print(f"Passbook has {len(passbook_wls)} unique Wagelist IDs. Missing from cache: {len(missing_wls)}")
    
    if len(missing_wls) > 0 or len(wagelist_to_work) < 50:
        print(f"Scanning all {len(emrs)} eMR sheets to build comprehensive Wagelist index...")
        start_t = time.time()
        completed = 0
        total = len(emrs)
        
        with ThreadPoolExecutor(max_workers=30) as executor:
            futures = [executor.submit(parse_emr_sheet, m) for m in emrs]
            for fut in as_completed(futures):
                res = fut.result()
                if res:
                    emr_info, unique_wls, worker_wls = res
                    for wl in unique_wls:
                        if wl not in wagelist_to_work:
                            wagelist_to_work[wl] = emr_info
                    for j, wl in worker_wls:
                        key = f"{j}___{wl}"
                        worker_wl_to_work[key] = emr_info
                completed += 1
                if completed % 100 == 0 or completed == total:
                    elapsed = time.time() - start_t
                    rate = completed / elapsed if elapsed > 0 else 0
                    print(f"  [{completed}/{total}] parsed ({rate:.1f} eMR/s, found {len(wagelist_to_work)} WLs)...")
                    
        # Save cache
        wl_cache = {
            "wagelist_to_work": wagelist_to_work,
            "worker_wl_to_work": worker_wl_to_work
        }
        with open(WL_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(wl_cache, f, ensure_ascii=False)
        print(f"Wagelist cache created with {len(wagelist_to_work)} Wagelists and {len(worker_wl_to_work)} worker pairs.")

    # Now enrich all worker payments in passbook.json
    matched_exact = 0
    matched_wl = 0
    fallback = 0
    month_distribution = {}
    
    for jc, w in worker_passbook.items():
        c_jc = clean_jc(jc)
        for p in w.get('payments', []):
            wl = p.get('wagelist_no', '').strip()
            
            # Preserve original payment voucher / transaction date
            tx_date = p.get('transaction_date') or p.get('work_period', '')
            p['payment_date'] = tx_date
            
            match = None
            if c_jc and wl:
                key = f"{c_jc}___{wl}"
                match = worker_wl_to_work.get(key)
                if match:
                    matched_exact += 1
                    
            if not match and wl:
                match = wagelist_to_work.get(wl)
                if match:
                    matched_wl += 1
                    
            if match:
                p['work_month'] = match['work_month']
                p['work_period'] = match['work_period']
                p['date_from'] = match['date_from']
                p['date_to'] = match['date_to']
                p['work_name'] = match['work_name']
                p['work_code'] = match['work_code']
                p['muster_roll_no'] = match['muster_roll_no']
                p['emr_link'] = match['link']
                p['wl_matched'] = True
                
                mon = match['work_month']
                month_distribution[mon] = month_distribution.get(mon, 0) + 1
            else:
                fallback += 1
                p['wl_matched'] = False
                # If transaction date is present, preserve it
                if tx_date and '/' in tx_date:
                    parts = tx_date.split('/')
                    if len(parts) == 3:
                        try:
                            dt = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
                            p['work_month'] = dt.strftime('%B %Y')
                        except Exception:
                            pass
                month_distribution[p.get('work_month', 'Other')] = month_distribution.get(p.get('work_month', 'Other'), 0) + 1

    print("=" * 60)
    print(f"Enrichment Results:")
    print(f"  Exact (Worker + Wagelist) Matches: {matched_exact}")
    print(f"  Wagelist Batch Matches           : {matched_wl}")
    print(f"  Total Matched to True Work Period: {matched_exact + matched_wl}")
    print(f"  Fallback to Payment Date         : {fallback}")
    print(f"True Physical Work Month Distribution in Passbook:")
    for mon, count in sorted(month_distribution.items(), key=lambda x: str(x[0])):
        print(f"  {mon}: {count} payments")
    print("=" * 60)
    
    # Sort payments in decreasing order of work month / date
    def payment_sort_key(p):
        d_from = p.get('date_from', '')
        if d_from and '/' in d_from:
            parts = d_from.split('/')
            if len(parts) == 3:
                try:
                    return datetime(int(parts[2]), int(parts[1]), int(parts[0])).timestamp()
                except Exception:
                    pass
        w_mon = p.get('work_month', '')
        if w_mon and w_mon != 'Other':
            try:
                return datetime.strptime(w_mon, '%B %Y').timestamp()
            except Exception:
                pass
        alt = p.get('payment_date') or p.get('transaction_date') or ''
        if alt and '/' in alt:
            parts = alt.split('/')
            if len(parts) == 3:
                try:
                    return datetime(int(parts[2]), int(parts[1]), int(parts[0])).timestamp()
                except Exception:
                    pass
        return 0

    for w in passbook_data.get('worker_passbook', {}).values():
        if 'payments' in w and isinstance(w['payments'], list):
            w['payments'].sort(key=payment_sort_key, reverse=True)

    with open(PASSBOOK_JSON, "w", encoding="utf-8") as f:
        json.dump(passbook_data, f, ensure_ascii=False, separators=(',', ':'))
    print(f"[SUCCESS] Updated {PASSBOOK_JSON} successfully!")

if __name__ == '__main__':
    main()
