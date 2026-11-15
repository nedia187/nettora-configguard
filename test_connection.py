import os
import yaml
from dotenv import load_dotenv
from netmiko import ConnectHandler

load_dotenv()
USER = os.getenv("NETTORA_USER")
PASSWORD = os.getenv("NETTORA_PASS")
if not USER or not PASSWORD:
    raise SystemExit("Missing NETTORA_USER or NETTORA_PASS in .env")

with open("data/inventory.yaml") as f:
    inventory = yaml.safe_load(f)

for dev in inventory["devices"]:
    params = {
        "device_type": inventory["defaults"]["device_type"],
        "host": dev["host"],
        "username": USER,
        "password": PASSWORD,
    }
    print(f"--- Connecting to {dev['name']} ({dev['host']}) ---")
    with ConnectHandler(**params) as conn:
        print(conn.send_command("show version | include uptime"))