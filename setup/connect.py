#!/usr/bin/env python3
"""
Second Brain — Integration Setup Wizard
Manages MCP server connections in ~/.claude/settings.json
"""
import getpass
import json
import subprocess
import sys
from pathlib import Path

SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
CATALOG_PATH = Path(__file__).parent / "integrations.json"

TIER_LABELS = {
    "cloud-oauth": "☁️  Cloud OAuth  (no token needed)",
    "cloud-api":   "☁️  Cloud + API key",
    "npm":         "📦 npm package  (needs Node.js)",
    "info":        "📖 Instructions only",
}

TRANSFORMS = {
    # Notion's MCP server expects the full Authorization header as a JSON string
    "notion_headers": lambda v: json.dumps({
        "Authorization": f"Bearer {v}",
        "Notion-Version": "2022-06-28",
    })
}

def load_json(path):
    with open(path) as f:
        return json.load(f)

def load_settings():
    if SETTINGS_PATH.exists():
        return load_json(SETTINGS_PATH)
    return {}

def save_settings(data):
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        json.dump(data, f, indent=2)

def configured_keys(settings):
    return set(settings.get("mcpServers", {}).keys())

def ask(label, secret=False):
    try:
        if secret:
            return getpass.getpass(f"  {label}: ").strip()
        return input(f"  {label}: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n\n  Cancelled.")
        sys.exit(0)

def check_npx():
    try:
        r = subprocess.run(["npx", "--version"], capture_output=True)
        return r.returncode == 0
    except FileNotFoundError:
        return False

def fill(template, creds):
    """Recursively replace {{KEY}} placeholders in a template dict/list/str."""
    if isinstance(template, dict):
        return {k: fill(v, creds) for k, v in template.items()}
    if isinstance(template, list):
        return [fill(v, creds) for v in template]
    if isinstance(template, str):
        for k, v in creds.items():
            template = template.replace(f"{{{{{k}}}}}", v)
    return template

def do_setup(integration, settings):
    tier = integration.get("tier", "npm")
    key = integration["server_key"]

    print(f"\n{'─' * 56}")
    print(f"  {integration['name']}")
    print(f"  {integration['description']}")
    print(f"  {TIER_LABELS.get(tier, tier)}")
    print(f"{'─' * 56}")

    if tier == "info":
        print(f"\n{integration.get('instructions', '')}\n")
        input("  Press Enter to go back...")
        return settings

    notes = integration.get("setup_notes", "")
    if notes:
        print(f"\n📋 How to get credentials:\n")
        for line in notes.strip().splitlines():
            print(f"   {line}")
        print()

    if tier == "npm" and not check_npx():
        print("  ❌ Node.js / npx not found.")
        print("     Install from https://nodejs.org then re-run this wizard.\n")
        input("  Press Enter to go back...")
        return settings

    creds = {}
    for cred in integration.get("credentials", []):
        hint = cred.get("hint", "")
        if hint:
            print(f"  💡 {hint}")
        val = ask(cred["label"], secret=cred.get("secret", True))
        if not val:
            print("  ⚠️  No value entered — setup cancelled.\n")
            input("  Press Enter to go back...")
            return settings
        transform = cred.get("transform")
        if transform and transform in TRANSFORMS:
            val = TRANSFORMS[transform](val)
        creds[cred["key"]] = val

    config = fill(integration["config_template"], creds)
    settings.setdefault("mcpServers", {})[key] = config
    save_settings(settings)

    print(f"\n  ✅ '{integration['name']}' saved (key: {key})")
    if tier == "cloud-oauth":
        print("  💡 Restart Claude Code — it will open a browser to authorize on first use.")
    elif tier == "npm":
        print("  💡 Restart Claude Code to activate. npx will auto-install the package.")
    else:
        print("  💡 Restart Claude Code to activate.")
    print()
    input("  Press Enter to continue...")
    return settings

def do_remove(integrations, settings):
    keys = configured_keys(settings)
    removable = [i for i in integrations if i["server_key"] in keys and not i["server_key"].startswith("_")]
    if not removable:
        print("\n  Nothing to remove.\n")
        input("  Press Enter to go back...")
        return settings

    print(f"\n{'─' * 56}")
    print("  Remove an integration")
    print(f"{'─' * 56}\n")
    for i, intg in enumerate(removable, 1):
        print(f"  {i}. {intg['name']}  ({intg['server_key']})")
    print("\n   0. Cancel\n")

    choice = ask("Remove which?", secret=False)
    if choice == "0" or not choice:
        return settings
    try:
        intg = removable[int(choice) - 1]
    except (ValueError, IndexError):
        print("  Invalid choice.")
        return settings

    confirm = ask(f"  Remove '{intg['name']}'? (y/N)", secret=False)
    if confirm.lower() != "y":
        return settings

    del settings["mcpServers"][intg["server_key"]]
    save_settings(settings)
    print(f"\n  ✅ Removed '{intg['server_key']}'\n")
    input("  Press Enter to continue...")
    return settings

def print_menu(integrations, configured):
    print("\n" + "═" * 56)
    print("  🔌  Second Brain — Integration Wizard")
    print("═" * 56 + "\n")

    for i, intg in enumerate(integrations, 1):
        k = intg["server_key"]
        tier = intg.get("tier", "")
        if tier == "info":
            status = "📖"
        elif k in configured:
            status = "✅"
        else:
            status = "⬜"
        tier_short = {"cloud-oauth": "cloud", "cloud-api": "cloud+key", "npm": "npm", "info": "info"}.get(tier, "")
        print(f"  {i:2}. {status} {intg['name']:<30} [{tier_short}]")

    print()
    print("   r. Remove an integration")
    print("   0. Exit")
    print()

def main():
    if not CATALOG_PATH.exists():
        print(f"❌ Catalog not found: {CATALOG_PATH}")
        sys.exit(1)

    catalog = load_json(CATALOG_PATH)
    integrations = catalog["integrations"]

    while True:
        settings = load_settings()
        configured = configured_keys(settings)
        print_menu(integrations, configured)

        try:
            choice = input("Select: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\n\n👋 Done.\n")
            break

        if choice in ("0", "q", ""):
            print("\n👋 Done.\n")
            break

        if choice == "r":
            settings = do_remove(integrations, settings)
            continue

        try:
            intg = integrations[int(choice) - 1]
        except (ValueError, IndexError):
            print("  Invalid choice.")
            continue

        k = intg["server_key"]
        if k in configured:
            confirm = ask(f"\n  '{intg['name']}' is already configured. Reconfigure? (y/N)", secret=False)
            if confirm.lower() != "y":
                continue

        settings = do_setup(intg, settings)

if __name__ == "__main__":
    main()
