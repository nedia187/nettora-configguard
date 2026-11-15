"""
watch.py - runs the monitor again and again, and refreshes the dashboard.

    python watch.py        -> one check every 60 seconds
    python watch.py 30     -> one check every 30 seconds
Stop it with Ctrl + C.
"""
import sys
import time
from datetime import datetime

from dashboard import build_dashboard
from monitor import print_report, run_checks, save_history

interval = int(sys.argv[1]) if len(sys.argv) > 1 else 60
print(f"Watching the network every {interval} s. Open reports/dashboard.html. Stop with Ctrl + C.")

try:
    while True:
        print(f"\n===== Check at {datetime.now():%H:%M:%S} =====")
        results = run_checks()
        print_report(results)
        save_history(results)
        build_dashboard()
        print(f"\nDashboard updated. Next check in {interval} s.")
        time.sleep(interval)
except KeyboardInterrupt:
    print("\nStopped.")