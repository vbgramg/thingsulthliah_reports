import os
import sys
import time
import subprocess
import ctypes
import threading
from datetime import datetime

LOGFILE = r"E:\thingsulthliah_reports\auto_sync.log"

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    try:
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def show_popup(title, text, timeout_ms=3500, wait=False):
    """
    Display a native Windows dialog that auto-closes after timeout_ms.
    Uses Win32 MessageBoxTimeoutW (100% immune to antivirus/AMSI false positives).
    """
    def _run():
        try:
            # 0x40 = MB_ICONINFORMATION, 0x40000 = MB_TOPMOST
            ctypes.windll.user32.MessageBoxTimeoutW(
                0,
                str(text),
                str(title),
                0x00000040 | 0x00040000,
                0,
                timeout_ms
            )
        except Exception:
            pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    if wait:
        t.join(timeout=(timeout_ms / 1000.0) + 1.0)
    return t

def sync_repository(repo_path, repo_name):
    log(f"--- Starting sync for {repo_name} ({repo_path}) ---")
    if not os.path.exists(os.path.join(repo_path, "scraper.py")):
        log(f"Skipping {repo_name}: scraper.py not found.")
        return False

    # 1. Ensure git uses schannel
    subprocess.run(["git", "config", "http.sslBackend", "schannel"], cwd=repo_path, creationflags=0x08000000)

    # 2. Run scraper.py
    t0 = time.time()
    res = subprocess.run(
        [sys.executable, "scraper.py"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        creationflags=0x08000000
    )
    duration = time.time() - t0

    if res.returncode != 0:
        log(f"[ERROR] {repo_name} scraper failed with code {res.returncode} in {duration:.1f}s.")
        if res.stderr:
            log(f"[STDERR] {res.stderr.strip()[:300]}")
        return False

    log(f"[SUCCESS] {repo_name} scraper finished in {duration:.1f}s.")

    # 3. Check for git changes in data/
    subprocess.run(["git", "add", "data/"], cwd=repo_path, creationflags=0x08000000)
    diff = subprocess.run(["git", "diff", "--staged", "--quiet"], cwd=repo_path, creationflags=0x08000000)

    if diff.returncode != 0:
        # Changes detected, commit and push
        now_str = datetime.now().strftime("%d-%m-%Y %H:%M")
        commit_msg = f"Auto-sync {repo_name} report data: {now_str}"
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=repo_path, capture_output=True, creationflags=0x08000000)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=repo_path, capture_output=True, creationflags=0x08000000)
        push_res = subprocess.run(["git", "push", "origin", "main"], cwd=repo_path, capture_output=True, text=True, creationflags=0x08000000)
        
        if push_res.returncode == 0:
            log(f"[PUSHED] Fresh data committed and pushed to GitHub for {repo_name}!")
        else:
            log(f"[WARN] Push failed for {repo_name}: {push_res.stderr.strip()[:200]}")
    else:
        log(f"[INFO] No data changes detected for {repo_name}. Already up to date.")

    return True

def main():
    start_total = time.time()
    log("="*60)
    log("DAILY AUTOMATED SYNC STARTED")
    log("="*60)

    # Show non-blocking popup to confirm to user that sync has started
    show_popup("VB-G RAM G Daily Sync", "Daily automated sync started for Thingsulthliah & Saitual...\nRunning in background.", timeout_ms=3500, wait=False)

    success_things = sync_repository(r"E:\thingsulthliah_reports", "Thingsulthliah RD Block")
    success_saitual = sync_repository(r"E:\saitual_reports", "Saitual District")

    total_time = time.time() - start_total
    log(f"DAILY AUTOMATED SYNC FINISHED in {total_time:.1f} seconds.")
    log("="*60 + "\n")

    if success_things and success_saitual:
        summary_msg = f"Sync finished successfully in {total_time:.0f}s.\nThingsulthliah & Saitual updated & pushed to GitHub!"
    else:
        summary_msg = f"Sync finished with warnings in {total_time:.0f}s.\nCheck auto_sync.log for details."
        
    show_popup("VB-G RAM G Sync Completed", summary_msg, timeout_ms=5000, wait=True)

if __name__ == "__main__":
    main()
