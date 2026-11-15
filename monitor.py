"""
monitor.py - checks that the network matches the source of truth (YAML)
and follows basic security rules.

It only READS from the devices: it never changes anything.
Each finding comes with a proposed fix, which is NOT applied automatically.
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml

from deploy import connect, load_inventory
from render import render_device

HISTORY_DIR = Path("reports/history")
IGNORED_LINES = {"no shutdown"}   # not shown in running-config; interface status is checked separately

# Connectivity tests, run from a router: (router, target, source IP, label)
PING_TESTS = [
    ("R1", "192.168.20.10", "192.168.10.1", "VLAN 10 -> PC2 (VLAN 20)"),
    ("R1", "192.168.30.1", "192.168.10.1", "VLAN 10 -> remote site (R2)"),
]


def result(device, check, status, detail, fix=None):
    """One line of the report. status is OK, WARN or ISSUE."""
    return {"device": device, "check": check, "status": status, "detail": detail, "fix": fix or []}


# ---------------------------------------------------------------- parsing helpers
def normalize(line):
    """Compare lines without ACL sequence numbers and extra spaces:
    '10 deny   tcp any ...' -> 'deny tcp any ...'."""
    line = re.sub(r"^\d+\s+(?=permit|deny|remark)", "", line.strip())
    return " ".join(line.split())


def parse_blocks(text):
    """Turn a config into {parent line: {normalized child: original child}}."""
    blocks, parent = {}, None
    for raw in text.splitlines():
        if not raw.strip() or raw.startswith("!"):
            parent = None
            continue
        if raw.startswith(" ") and parent:
            blocks[parent][normalize(raw)] = raw.strip()
        else:
            parent = raw.strip()
            blocks.setdefault(parent, {})
    return blocks


def parse_ip_brief(text):
    """'show ip interface brief' -> {interface: (status, protocol)}."""
    status = {}
    for line in text.splitlines():
        m = re.match(r"^(\S+)\s+\S+\s+\S+\s+\S+\s+(administratively down|up|down)\s+(up|down)", line)
        if m:
            status[m.group(1)] = (m.group(2), m.group(3))
    return status


def parse_vlans(text):
    """'show vlan brief' -> {vlan id: name}."""
    vlans = {}
    for line in text.splitlines():
        m = re.match(r"^(\d+)\s+(\S+)\s+(active|suspended|act/\S+)", line)
        if m:
            vlans[int(m.group(1))] = m.group(2)
    return vlans


# ---------------------------------------------------------------- checks
def check_drift(name, intended_text, running_text):
    """Every line the YAML asks for must be in the running-config."""
    intended = parse_blocks(intended_text)
    running = parse_blocks(running_text)
    found = []
    for parent, children in intended.items():
        if parent.startswith("vlan "):   # VLANs are checked with 'show vlan brief'
            continue
        wanted = {n: o for n, o in children.items() if n not in IGNORED_LINES}
        if parent not in running:
            found.append(result(name, "drift", "ISSUE", f"missing block: {parent}",
                                [parent] + [" " + o for o in wanted.values()]))
            continue
        missing = [o for n, o in wanted.items() if n not in running[parent]]
        if missing:
            found.append(result(name, "drift", "ISSUE", f"{parent}: missing '{'; '.join(missing)}'",
                                [parent] + [" " + o for o in missing]))
    return found or [result(name, "drift", "OK", "running-config matches the YAML")]


def expected_interfaces(data):
    names = []
    for intf in data.get("interfaces", []):
        names.append(intf["name"])
        names += [sub["name"] for sub in intf.get("subinterfaces", [])]
    names += [p["name"] for p in data.get("access_ports", [])]
    names += [t["name"] for t in data.get("trunks", [])]
    return names


def check_interfaces(name, data, ip_brief):
    status = parse_ip_brief(ip_brief)
    found = []
    for intf in expected_interfaces(data):
        state = status.get(intf)
        if state is None:
            found.append(result(name, "interfaces", "ISSUE", f"{intf} not found on the device"))
        elif state != ("up", "up"):
            found.append(result(name, "interfaces", "ISSUE", f"{intf} is {state[0]}/{state[1]}",
                                [f"interface {intf}", " no shutdown"]))
    return found or [result(name, "interfaces", "OK", "all expected interfaces are up/up")]


def check_ospf(name, show_neighbor):
    full = [line for line in show_neighbor.splitlines() if "FULL" in line]
    if full:
        return result(name, "ospf", "OK", f"{len(full)} neighbor(s) FULL")
    return result(name, "ospf", "ISSUE", "no OSPF neighbor in FULL state (link down or config mismatch)")


def check_vlans(name, data, show_vlan):
    present = parse_vlans(show_vlan)
    found = []
    for v in data.get("vlans", []):
        fix = [f"vlan {v['id']}", f" name {v['name']}"]
        if v["id"] not in present:
            found.append(result(name, "vlans", "ISSUE", f"VLAN {v['id']} ({v['name']}) is missing", fix))
        elif present[v["id"]] != v["name"]:
            found.append(result(name, "vlans", "WARN",
                                f"VLAN {v['id']} is named {present[v['id']]} instead of {v['name']}", fix))
    ids = ", ".join(str(v["id"]) for v in data.get("vlans", []))
    return found or [result(name, "vlans", "OK", f"VLANs {ids} present with the right names")]


def check_security(name, data, blocks, show_trunk=None):
    found = []

    # Rule 1: remote access must be SSH only (no Telnet)
    for parent, children in blocks.items():
        if parent.startswith("line vty"):
            transports = [c for c in children if c.startswith("transport input")]
            if any("telnet" in t or t.endswith(" all") for t in transports):
                found.append(result(name, "security", "ISSUE", f"{parent}: Telnet is allowed",
                                    [parent, " transport input ssh"]))
            elif not transports:
                found.append(result(name, "security", "WARN",
                                    f"{parent}: no 'transport input' set (default may allow Telnet)",
                                    [parent, " transport input ssh"]))

    # Rule 2: the WAN ACL must be applied (blocks SSH from the WAN)
    for acl in data.get("acls", []):
        intf = f"interface {acl['apply_on']}"
        applied = f"ip access-group {acl['name']} {acl['direction']}"
        if applied not in blocks.get(intf, {}):
            found.append(result(name, "security", "ISSUE",
                                f"ACL {acl['name']} not applied on {acl['apply_on']}: SSH from the WAN is open",
                                [intf, " " + applied]))

    # Rule 3: trunks should not use native VLAN 1 (VLAN hopping risk)
    if show_trunk:
        for line in show_trunk.splitlines():
            m = re.match(r"^(\S+)\s+\S+\s+\S+\s+trunking\s+(\d+)", line)
            if m and m.group(2) == "1":
                found.append(result(name, "security", "WARN",
                                    f"trunk {m.group(1)} uses native VLAN 1 (VLAN hopping risk)",
                                    [f"interface {m.group(1)}", " switchport trunk native vlan 999"]))

    return found or [result(name, "security", "OK", "security rules passed")]


def check_ping(conn, name, target, source, label):
    out = conn.send_command(f"ping {target} source {source} repeat 3", read_timeout=30)
    m = re.search(r"Success rate is (\d+) percent", out)
    rate = int(m.group(1)) if m else 0
    status = "OK" if rate >= 60 else "ISSUE"
    return result(name, "ping", status, f"{label}: {rate}% success")


# ---------------------------------------------------------------- main loop
def run_checks():
    inventory = load_inventory()
    results = []
    for dev in inventory["devices"]:
        name, role = dev["name"], dev["role"]
        with open(f"data/devices/{name}.yaml") as f:
            data = yaml.safe_load(f)
        intended = render_device(name, role)
        try:
            with connect(dev, inventory["defaults"]) as conn:
                running = conn.send_command("show running-config")
                blocks = parse_blocks(running)
                results += check_drift(name, intended, running)
                results += check_interfaces(name, data, conn.send_command("show ip interface brief"))
                if role == "router":
                    if "ospf" in data:
                        results.append(check_ospf(name, conn.send_command("show ip ospf neighbor")))
                    results += check_security(name, data, blocks)
                    for router, target, source, label in PING_TESTS:
                        if router == name:
                            results.append(check_ping(conn, name, target, source, label))
                else:
                    results += check_vlans(name, data, conn.send_command("show vlan brief"))
                    results += check_security(name, data, blocks, conn.send_command("show interfaces trunk"))
        except Exception as e:
            results.append(result(name, "reachability", "ISSUE", f"cannot connect: {e.__class__.__name__}"))
    return results


def print_report(results):
    print(f"\n{'DEVICE':6} {'CHECK':12} {'STATUS':6} DETAIL")
    print("-" * 95)
    for r in results:
        print(f"{r['device']:6} {r['check']:12} {r['status']:6} {r['detail']}")
    to_review = [r for r in results if r["status"] != "OK"]
    print("-" * 95)
    print(f"{len(results)} checks: {len(results) - len(to_review)} OK, {len(to_review)} to review")
    for r in to_review:
        if r["fix"]:
            print(f"\nProposed fix for {r['device']} ({r['check']}) - NOT applied:")
            for line in r["fix"]:
                print(f"    {line}")
    return to_review


def save_history(results):
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    path = HISTORY_DIR / f"{now:%Y-%m-%d_%H-%M-%S}.json"
    path.write_text(json.dumps({"time": now.isoformat(timespec="seconds"), "results": results}, indent=2),
                    encoding="utf-8")
    return path


if __name__ == "__main__":
    results = run_checks()
    to_review = print_report(results)
    print(f"\nSaved to {save_history(results)}")
    sys.exit(1 if to_review else 0)