"""
validate.py - tests a proposed fix in the LAB before anyone uses it in production.
 
  1. run the monitor BEFORE and pick a proposed fix
  2. back up the device
  3. apply the fix in the lab
  4. run the monitor AFTER and compare
  5. PASS -> ask a person to approve (save) or refuse (roll back)
     FAIL -> roll back automatically
 
    python validate.py              test the first fix proposed by the monitor
    python validate.py --bad-demo   test a deliberately WRONG fix, to show the rollback
"""
import re
import sys
import time
from datetime import datetime
from pathlib import Path
 
from deploy import ERRORS, backup, connect, load_inventory
from monitor import parse_blocks, run_checks
 
REPORT_DIR = Path("reports/validations")
SETTLE_SECONDS = 40   # spanning tree and OSPF need time after a change
 
BAD_DEMO_FIX = {
    "device": "SW1", "check": "demo", "status": "ISSUE",
    "detail": "demo: a WRONG fix that removes VLAN 20 from the trunk",
    "fix": ["interface Ethernet0/3", " switchport trunk allowed vlan 10"],
}
 
 
def key(r):
    return (r["device"], r["check"], r["detail"])
 
 
def problems(results):
    """Every result that is not OK, by key."""
    return {key(r): r["status"] for r in results if r["status"] != "OK"}
 
 
def pick_fix(results):
    for r in results:
        if r["status"] != "OK" and r["fix"]:
            return r
    return None
 
 
def full_name(parent):
    """'interface Et0/3' (from show commands) -> 'interface Ethernet0/3' (as in running-config)."""
    return re.sub(r"^interface Et(\d)", r"interface Ethernet\1", parent)
 
 
def rollback_commands(fix, backup_text):
    """Commands that put the block back as it was in the backup."""
    parent = full_name(fix[0])
    if parent.startswith("vlan "):                       # the fix created a VLAN -> delete it
        return ["no " + parent]
    previous = list(parse_blocks(backup_text).get(parent, {}).values())
    undo = [parent]
    for line in (c.strip() for c in fix[1:]):
        if line.startswith("no "):                        # 'no shutdown' -> 'shutdown'
            undo.append(" " + line[3:])
            continue
        prefix = " ".join(line.split()[:-1])              # 'switchport trunk native vlan'
        if not any(p.startswith(prefix) for p in previous):
            undo.append(" no " + line)                    # the setting did not exist before
    undo += [" " + p for p in previous]                   # re-apply what was there before
    return undo
 
 
def write_report(lines):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{datetime.now():%Y-%m-%d_%H-%M-%S}.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
 
 
def main():
    bad_demo = "--bad-demo" in sys.argv
    inventory = load_inventory()
    devices = {d["name"]: d for d in inventory["devices"]}
 
    print("[1/5] Monitor BEFORE the fix ...")
    before = run_checks()
    finding = BAD_DEMO_FIX if bad_demo else pick_fix(before)
    if not finding:
        raise SystemExit("Nothing to test: the monitor found no problem with a proposed fix.")
 
    dev = devices[finding["device"]]
    print(f"\nFinding : {finding['device']} / {finding['check']} - {finding['detail']}")
    print("Fix to test in the LAB:")
    for line in finding["fix"]:
        print(f"    {line}")
    if input("\nApply this fix to the LAB device? Type YES to continue: ") != "YES":
        raise SystemExit("Cancelled. Nothing was sent.")
 
    with connect(dev, inventory["defaults"]) as conn:
        print("[2/5] Backup ...")
        backup_path = backup(conn, dev["name"])
        backup_text = backup_path.read_text(encoding="utf-8")
        print(f"      saved -> {backup_path}")
        print("[3/5] Applying the fix in the lab ...")
        conn.send_config_set(finding["fix"], error_pattern=ERRORS)
    print(f"      waiting {SETTLE_SECONDS} s for the network to settle ...")
    time.sleep(SETTLE_SECONDS)
 
    print("[4/5] Monitor AFTER the fix ...")
    after = run_checks()
    before_p, after_p = problems(before), problems(after)
    resolved = key(finding) not in after_p
    new = {k: s for k, s in after_p.items() if k not in before_p}
    passed = resolved and not new
 
    report = [
        "NETTORA CONFIGGUARD - LAB VALIDATION",
        f"Time      : {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Device    : {finding['device']}",
        f"Finding   : {finding['check']} - {finding['detail']}",
        "Fix tested:", *[f"    {line}" for line in finding["fix"]],
        f"Backup    : {backup_path}",
        f"Before    : {len(before_p)} problem(s)",
        f"After     : {len(after_p)} problem(s)",
        f"Finding resolved : {'yes' if resolved else 'no'}",
        f"New problems     : {len(new)}",
        *[f"    {s}: {d} / {c} - {t}" for (d, c, t), s in new.items()],
        f"RESULT    : {'PASS' if passed else 'FAIL'}",
    ]
 
    rollback_needed = not passed
    if passed:
        print("\n[5/5] PASS: the finding is resolved and nothing else broke.")
        answer = input("Approve this fix? YES = keep it and save, anything else = roll back: ")
        if answer == "YES":
            with connect(dev, inventory["defaults"]) as conn:
                conn.save_config()
            report.append("DECISION  : APPROVED by a person - fix kept and saved (write memory)")
            report.append("NEXT STEP : add the fix to the YAML so it becomes part of the source of truth")
            print("Approved and saved. Next: add it to the YAML (source of truth).")
        else:
            report.append("DECISION  : REFUSED by a person - rolled back")
            rollback_needed = True
    else:
        print("\n[5/5] FAIL: " + ("the finding is still there. " if not resolved else "")
              + (f"{len(new)} new problem(s) appeared." if new else ""))
        for (d, c, t), s in new.items():
            print(f"      NEW {s}: {d} / {c} - {t}")
 
    if rollback_needed:
        undo = rollback_commands(finding["fix"], backup_text)
        print("Rolling back with:")
        for line in undo:
            print(f"    {line}")
        try:
            with connect(dev, inventory["defaults"]) as conn:
                conn.send_config_set(undo, error_pattern=ERRORS)
        except Exception as e:
            report.append(f"ROLLBACK  : FAILED ({e.__class__.__name__}) - restore manually from {backup_path}")
            print(f"ROLLBACK FAILED - restore manually from {backup_path}")
        else:
            print(f"      waiting {SETTLE_SECONDS} s, then checking again ...")
            time.sleep(SETTLE_SECONDS)
            final_p = problems(run_checks())
            restored = set(final_p) == set(before_p)
            report.append("ROLLBACK  : done - network " + ("back to its state before the test"
                                                         if restored else "NOT exactly as before, check the monitor"))
            print("Rollback done: " + ("network back to its state before the test." if restored
                                       else "network differs from before, run monitor.py"))
 
    print(f"\nReport -> {write_report(report)}")
 
 
if __name__ == "__main__":
    main()
 