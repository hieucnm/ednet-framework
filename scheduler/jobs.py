# scheduler/jobs.py

import schedule
import time
from datetime import date
from modules.analytics.kpi_engine import KPIEngine


def compute_kpis():
    print("⏰ Scheduled KPI computation started...")
    engine = KPIEngine()
    results = engine.compute_all(
        network_id=1,
        period_start=date(2023, 1, 1),
        period_end=date.today(),
    )
    print(f"✔ KPI computation complete. {len(results)} indicators updated.")


# Run daily at 02:00
schedule.every().day.at("02:00").do(compute_kpis)

# Also run once immediately on startup
compute_kpis()

print("📅 Scheduler running. KPIs will recompute daily at 02:00.")
while True:
    schedule.run_pending()
    time.sleep(60)