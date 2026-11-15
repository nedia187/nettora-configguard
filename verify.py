from deploy import load_inventory, connect

CHECKS = {
    "router": [
        "show ip interface brief",
        "show ip ospf neighbor",
        "show ip route ospf",
        "show access-lists WAN_IN",
    ],
    "switch": [
        "show vlan brief",
        "show interfaces trunk",
    ],
}

inventory = load_inventory()
for dev in inventory["devices"]:
    with connect(dev, inventory["defaults"]) as conn:
        for cmd in CHECKS[dev["role"]]:
            print(f"\n### {dev['name']} : {cmd}")
            print(conn.send_command(cmd))