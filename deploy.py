import os
import sys
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv
from netmiko import ConnectHandler

from render import render_device

load_dotenv()
USER = os.getenv("NETTORA_USER")
PASSWORD = os.getenv("NETTORA_PASS")
if not USER or not PASSWORD:
    raise SystemExit("Missing NETTORA_USER or NETTORA_PASS in .env")

BACKUP_DIR = Path("backups")
ERRORS = r"% Invalid|% Incomplete|% Ambiguous"   # Cisco error messages


def load_inventory():
    with open("data/inventory.yaml") as f:
        return yaml.safe_load(f)


def connect(dev, defaults):
    return ConnectHandler(
        device_type=defaults["device_type"],
        host=dev["host"],
        username=USER,
        password=PASSWORD,
    )


def backup(conn, name):
    running = conn.send_command("show running-config")
    folder = BACKUP_DIR / name
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = folder / f"{stamp}.cfg"
    path.write_text(running, encoding="utf-8")
    return path


def deploy_device(dev, defaults, dry_run):
    config = render_device(dev["name"], dev["role"])
    commands = [line for line in config.splitlines() if line.strip()]
    print(f"\n========== {dev['name']} ({dev['host']}) : {len(commands)} commands ==========")

    if dry_run:
        print(config)
        return

    with connect(dev, defaults) as conn:
        path = backup(conn, dev["name"])
        print(f"  backup saved   -> {path}")
        conn.send_config_set(commands, error_pattern=ERRORS)
        print("  config pushed  -> OK")
        conn.save_config()
        print("  config saved   -> OK (write memory)")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith("--")]

    inventory = load_inventory()
    targets = [d for d in inventory["devices"] if not only or d["name"] in only]

    if not dry_run:
        names = ", ".join(d["name"] for d in targets)
        answer = input(f"Push configuration to {names}? Type YES to continue: ")
        if answer != "YES":
            raise SystemExit("Cancelled. Nothing was sent.")

    for dev in targets:
        deploy_device(dev, inventory["defaults"], dry_run)