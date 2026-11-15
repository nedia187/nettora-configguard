import yaml

with open("data/inventory.yaml") as f:
    inventory = yaml.safe_load(f)

for dev in inventory["devices"]:
    with open(f"data/devices/{dev['name']}.yaml") as f:
        config = yaml.safe_load(f)
    print(f"{dev['name']:4} {dev['host']:15} role={dev['role']:7} keys={list(config.keys())}")