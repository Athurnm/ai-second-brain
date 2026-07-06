import os
import subprocess
import datetime
import re

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
DASHBOARD_PATH = os.path.join(BASE_DIR, 'Dashboard.md')
GCAL_MANAGER = os.path.join(BASE_DIR, '.agent/skills/google-calendar-connector/gcal_manager.py')
GDRIVE_MANAGER = os.path.join(BASE_DIR, '.agent/skills/work-drive-connector/gdrive_manager.py')
SLACK_CLIENT = os.path.join(BASE_DIR, '.agent/skills/slack-connector/scripts/slack_client.py')

def run_cmd(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
        return result.stdout
    except Exception as e:
        print(f"Error running command {cmd}: {e}")
        return ""

def get_calendar():
    print("Fetching Calendar...")
    return run_cmd(f"python3 {GCAL_MANAGER} sweep --profile work --output markdown")

def sync():
    now = datetime.datetime.now().strftime("%b %d, %Y")
    print(f"Starting Dashboard Sync for {now}...")

    # 1. Fetch Calendar
    cal_focus = get_calendar()
    if not cal_focus:
        cal_focus = "### [WORK] 📅 Calendar Focus\n\nNo events found or sync failed."

    # 2. Update Dashboard.md
    if os.path.exists(DASHBOARD_PATH):
        with open(DASHBOARD_PATH, 'r') as f:
            content = f.read()

        # Update Last Updated Date
        content = re.sub(r'\(Last Updated: [^\)]+\)', f'(Last Updated: {datetime.datetime.now().strftime("%b %d, %H:%M")})', content)

        # Update Calendar Section
        # This is a simplified replacement for the purpose of the skill demo
        cal_pattern = r'## 📅 Calendar Focus.*?(?=##|$)'
        new_cal_section = f"## 📅 Calendar Focus\n*(Last Updated: {datetime.datetime.now().strftime('%b %d, %H:%M')})*\n\n{cal_focus}\n\n"
        content = re.sub(cal_pattern, new_cal_section, content, flags=re.DOTALL)

        with open(DASHBOARD_PATH, 'w') as f:
            f.write(content)
        
        print("Dashboard.md successfully updated.")
    else:
        print(f"Dashboard.md not found at {DASHBOARD_PATH}")

if __name__ == "__main__":
    sync()
