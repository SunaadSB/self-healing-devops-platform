from pathlib import Path
import re

app_path = Path("dashboard/dashboard_app.py")
source = app_path.read_text(encoding="utf-8")

import_line = "from recovery.recovery_metrics import calculate_recovery_metrics"
if import_line not in source:
    anchor = "from fastapi.staticfiles import StaticFiles"
    if anchor not in source:
        raise SystemExit("Could not find dashboard import anchor; no API changes made.")
    source = source.replace(anchor, anchor + "\n\n" + import_line, 1)

pattern = re.compile(r'        "recovery": \{.*?\n        \},\n    \}', re.S)
replacement = '''        "recovery": {
            **calculate_recovery_metrics(AUDIT_PATH),
            "rate_percent": calculate_recovery_metrics(AUDIT_PATH)["recovery_rate_percent"],
            "note": (
                "Rate is based on completed live attempts with recorded recovery outcomes. "
                "Dry runs are excluded."
                if calculate_recovery_metrics(AUDIT_PATH)["eligible_attempts"]
                else "Not yet measured: no completed, eligible live recovery outcomes."
            ),
        },
    }'''

updated, count = pattern.subn(replacement, source, count=1)
if count != 1:
    raise SystemExit("Could not locate the overview recovery block; API file left unchanged.")
app_path.write_text(updated, encoding="utf-8")

html_path = Path("dashboard/static/index.html")
html = html_path.read_text(encoding="utf-8")

old = '$("recoverydetail").textContent=`${rec.verified_successes||0} verified / ${rec.eligible_attempts||0} eligible audit events`;'
new = '$("recoverydetail").textContent=`${rec.verified_successes||0} verified successes / ${rec.eligible_attempts||0} eligible attempts · ${rec.live_attempts||0} live attempts · ${rec.dry_run_operations||0} dry runs`;'

if old not in html:
    raise SystemExit("Could not find recovery detail UI expression; HTML file left unchanged.")

html = html.replace(old, new, 1)
html_path.write_text(html, encoding="utf-8")

print("Dashboard API and recovery detail UI updated.")
