import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

env = Environment(
    loader=FileSystemLoader("templates"),
    trim_blocks=True,        # removes the empty line after {% ... %}
    lstrip_blocks=True,      # removes spaces before {% ... %}
    undefined=StrictUndefined,  # error if a YAML key is missing (catches typos)
)

# Which templates each role uses, and which YAML key each one needs
TEMPLATES = {
    "router": [("interfaces.j2", "interfaces"), ("ospf.j2", "ospf"), ("acls.j2", "acls")],
    "switch": [("switch.j2", "vlans")],
}

def render_device(name, role):
    with open(f"data/devices/{name}.yaml") as f:
        data = yaml.safe_load(f)
    parts = []
    for template_name, needed_key in TEMPLATES[role]:
        if needed_key in data:                      # R2 has no 'acls' → skip acls.j2
            parts.append(env.get_template(template_name).render(**data))
    return "\n".join(parts)

if __name__ == "__main__":
    with open("data/inventory.yaml") as f:
        inventory = yaml.safe_load(f)
    for dev in inventory["devices"]:
        print(f"\n========== {dev['name']} ==========")
        print(render_device(dev["name"], dev["role"]))