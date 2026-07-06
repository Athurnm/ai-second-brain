import os
import sys
import json
import requests
from requests.auth import HTTPBasicAuth

# Force UTF-8 on Windows stdout/stderr to prevent encoding crashes
try:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# Credentials come from env vars or a token.env next to this skill
# (token.env is gitignored from the public template; see token.env.example).
def _load_token_env():
    for candidate in (
        os.path.join(os.path.dirname(__file__), "..", "token.env"),
        os.path.join(os.path.dirname(__file__), "token.env"),
    ):
        if os.path.exists(candidate):
            with open(candidate) as fh:
                for line in fh:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip('"'))

_load_token_env()

EMAIL = os.environ.get("JIRA_EMAIL", "")
TOKEN = os.environ.get("JIRA_API_TOKEN", "")
if not EMAIL or not TOKEN:
    sys.exit("jira_client: set JIRA_EMAIL and JIRA_API_TOKEN (env or token.env)")
AUTH = HTTPBasicAuth(EMAIL, TOKEN)
HEADERS = {"Accept": "application/json"}

# 4 Work development boards map
BOARDS = {
    608: {
        "name": "E-commerce Core",
        "domain": "examplevendor.atlassian.net",
        "project_key": "MSP"
    },
    508: {
        "name": "B2C Super App",
        "domain": "examplevendor.atlassian.net",
        "project_key": "MBA"
    },
    674: {
        "name": "Storefront (Teammate)",
        "domain": "examplevendor.atlassian.net",
        "project_key": "STOR"
    },
    52: {
        "name": "Marketplace",
        "domain": "work-incentives.atlassian.net",
        "project_key": "MP"
    },
    76: {
        "name": "Platform Team",
        "domain": "work-incentives.atlassian.net",
        "project_key": "MPS"
    }
}

def standardize_status(status_name):
    """Maps custom Jira status names to a standard set for clear reporting."""
    s = status_name.upper().strip()
    if s in ["DONE", "CLOSED", "RESOLVED", "COMPLETED"]:
        return "DONE"
    if s in ["READY FOR REVIEW", "REVIEW IN PROGRESS", "REVIEW", "READY FOR TESTING", "QA IN PROGRESS", "UNDER REVIEW", "QA"]:
        return "UNDER REVIEW"
    if s in ["IN PROGRESS", "IN DEVELOPMENT", "DOING", "IMPLEMENTATION"]:
        return "IN PROGRESS"
    return "TO DO"

def fetch_board_active_sprint_and_issues(board_id, info):
    """Fetches details for active sprint and issues from a board."""
    domain = info["domain"]
    url = f"https://{domain}/rest/agile/1.0/board/{board_id}/sprint?state=active"
    
    try:
        resp = requests.get(url, headers=HEADERS, auth=AUTH, timeout=15)
        if resp.status_code == 404:
            return {"error": "Access Blocked / 404 Not Found (Permission Pending)"}
        if resp.status_code != 200:
            return {"error": f"API Error {resp.status_code}: {resp.text[:200]}"}
            
        sprints = resp.json().get("values", [])
        if not sprints:
            return {"error": "No active sprints found"}
            
        sprint = sprints[0]
        sprint_id = sprint["id"]
        sprint_name = sprint["name"]
        end_date = sprint.get("endDate", "N/A")[:10]
        
        # Query issues for the active sprint
        issues_url = f"https://{domain}/rest/agile/1.0/sprint/{sprint_id}/issue?maxResults=100&fields=summary,status,assignee,issuetype,parent"
        issues_resp = requests.get(issues_url, headers=HEADERS, auth=AUTH, timeout=25)
        if issues_resp.status_code != 200:
            return {"error": f"Sprint Issues API Error {issues_resp.status_code}"}
            
        issues_data = issues_resp.json()
        issues = issues_data.get("issues", [])
        
        return {
            "sprint_name": sprint_name,
            "end_date": end_date,
            "issues": issues,
            "total_count": len(issues)
        }
    except Exception as e:
        return {"error": f"Connection exception: {str(e)}"}

def verify_all_connections():
    """Runs a quick pre-flight connectivity verification for all configured boards."""
    print("=== Jira Connector Connectivity Verification ===")
    for bid, info in BOARDS.items():
        domain = info["domain"]
        url = f"https://{domain}/rest/agile/1.0/board/{bid}"
        try:
            r = requests.get(url, headers=HEADERS, auth=AUTH, timeout=10)
            if r.status_code == 200:
                print(f"✅ Board #{bid} ({info['name']}) connected successfully! Board Name: {r.json().get('name')}")
            elif r.status_code == 404:
                print(f"❌ Board #{bid} ({info['name']}) returned 404 (Access Pending on domain {domain})")
            else:
                print(f"❌ Board #{bid} ({info['name']}) returned error {r.status_code}: {r.text[:150]}")
        except Exception as e:
            print(f"⚠️ Board #{bid} ({info['name']}) failed with exception: {e}")

def generate_daily_digest():
    """Queries all active boards, compiles data, analyzes workload imbalances, and returns Markdown."""
    output = []
    output.append("### 🏃 Sprint Progress & Allocation")
    
    has_active_sprints = False
    
    for bid, info in BOARDS.items():
        output.append(f"#### 📦 {info['name']} (Board #{bid})")
        
        sprint_data = fetch_board_active_sprint_and_issues(bid, info)
        
        if "error" in sprint_data:
            err = sprint_data["error"]
            if "404" in err:
                output.append(f"> [!NOTE]\n> **Status**: Board is currently inaccessible. Access/permissions are pending for your account.\n")
            else:
                output.append(f"> [!WARNING]\n> **Status**: Failed to harvest sprint data: {err}\n")
            continue
            
        has_active_sprints = True
        
        sprint_name = sprint_data["sprint_name"]
        end_date = sprint_data["end_date"]
        issues = sprint_data["issues"]
        total_count = sprint_data["total_count"]
        
        # Summary calculations
        status_counts = {"TO DO": 0, "IN PROGRESS": 0, "UNDER REVIEW": 0, "DONE": 0}
        assignee_counts = {}
        assignee_statuses = {}
        epics = {}
        
        for issue in issues:
            fields = issue.get("fields", {})
            status_obj = fields.get("status", {})
            status_name = status_obj.get("name", "Unknown")
            std_status = standardize_status(status_name)
            status_counts[std_status] += 1
            
            assignee = fields.get("assignee")
            assignee_name = assignee.get("displayName", "Unassigned") if assignee else "Unassigned"
            assignee_counts[assignee_name] = assignee_counts.get(assignee_name, 0) + 1
            
            if assignee_name not in assignee_statuses:
                assignee_statuses[assignee_name] = {}
            assignee_statuses[assignee_name][std_status] = assignee_statuses[assignee_name].get(std_status, 0) + 1
            
            # Epic categorization
            parent = fields.get("parent")
            if parent:
                parent_key = parent.get("key", "No Epic")
                parent_summary = parent.get("fields", {}).get("summary", "No Epic Summary")
                epic_display = f"{parent_key}: {parent_summary}"
            else:
                epic_display = "Independent Tasks / No Epic"
                
            if epic_display not in epics:
                epics[epic_display] = {"total": 0, "done": 0}
            epics[epic_display]["total"] += 1
            if std_status == "DONE":
                epics[epic_display]["done"] += 1

        # Calculate completion rate
        done_review_count = status_counts["DONE"] + status_counts["UNDER REVIEW"]
        completion_pct = (done_review_count / total_count * 100) if total_count > 0 else 0
        
        output.append(f"- **Active Sprint**: `{sprint_name}` (Target End: `{end_date}`)")
        output.append(f"- **Total Sprint Items**: `{total_count}` tickets")
        output.append(f"- **Sprint Status Summary**: `DONE`: {status_counts['DONE']} · `UNDER REVIEW`: {status_counts['UNDER REVIEW']} · `IN PROGRESS`: {status_counts['IN PROGRESS']} · `TO DO`: {status_counts['TO DO']}")
        output.append(f"- **Functional Completion Rate**: `{completion_pct:.1f}%` (Done + Under Review)")
        
        # Check Workload Imbalance (Teammate-type bottleneck guardrail: >40%)
        bottlenecks = []
        for name, count in assignee_counts.items():
            if name == "Unassigned":
                continue
            allocation_pct = (count / total_count * 100) if total_count > 0 else 0
            if allocation_pct > 40.0:
                bottlenecks.append(f"**{name}** holds **{count} out of {total_count} tickets ({allocation_pct:.1f}%)**")
                
        if bottlenecks:
            output.append("\n> [!WARNING]")
            output.append("> **Workload Imbalance / Resource Bottleneck Alert**:")
            for b in bottlenecks:
                output.append(f"> - {b} -- represents an extreme risk for delivery delays.")
                
        # Assignee Breakdown Table
        output.append("\n| Assignee | Active Tickets | Status Distribution |")
        output.append("| :--- | :--- | :--- |")
        for name, count in sorted(assignee_counts.items(), key=lambda x: x[1], reverse=True):
            dist = assignee_statuses.get(name, {})
            dist_str = ", ".join([f"{k}: {v}" for k, v in dist.items()])
            output.append(f"| **{name}** | {count} | {dist_str} |")
            
        # Epic summary
        output.append("\n**Epic Progress Summary**:")
        for epic, meta in sorted(epics.items(), key=lambda x: x[1]["total"], reverse=True)[:5]:
            output.append(f"- *{epic}*: `{meta['done']}/{meta['total']}` tickets complete")
            
        output.append("") # Spacer between boards
        
    if not has_active_sprints:
        output.append("> [!NOTE]\n> No active sprints are currently harvestable. Access is pending or sprints are not started.")
        
    return "\n".join(output)

def create_issue(project_key, summary, issue_type="Story", priority="High", description_text="", assignee_account_id=None, domain="examplevendor.atlassian.net"):
    """Create a Jira issue. Returns (key, url) on success or raises on error."""
    url = f"https://{domain}/rest/api/3/issue"
    auth = HTTPBasicAuth(EMAIL, TOKEN)

    body = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
            "priority": {"name": priority},
        }
    }
    if description_text:
        body["fields"]["description"] = {
            "type": "doc", "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": description_text}]}]
        }
    if assignee_account_id:
        body["fields"]["assignee"] = {"accountId": assignee_account_id}

    resp = requests.post(url, json=body, headers=HEADERS, auth=auth, timeout=15)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Create issue failed ({resp.status_code}): {resp.text[:300]}")
    key = resp.json()["key"]
    return key, f"https://{domain}/browse/{key}"

def main():
    if len(sys.argv) > 1:
        action = sys.argv[1]
    else:
        action = "daily-digest"

    if action == "verify-connections":
        verify_all_connections()
    elif action == "daily-digest":
        digest = generate_daily_digest()
        print(digest)
    elif action == "create-issue":
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--project", required=True)
        parser.add_argument("--summary", required=True)
        parser.add_argument("--type", default="Story")
        parser.add_argument("--priority", default="High")
        parser.add_argument("--description", default="")
        parser.add_argument("--assignee", default=None)
        parser.add_argument("--domain", default="examplevendor.atlassian.net")
        args = parser.parse_args(sys.argv[2:])
        key, url = create_issue(args.project, args.summary, args.type, args.priority, args.description, args.assignee, args.domain)
        print(f"Created: {key} -> {url}")
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)

if __name__ == "__main__":
    main()
