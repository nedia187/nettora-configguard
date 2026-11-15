# Nettora ConfigGuard

A Python tool for network automation, misconfiguration detection, and safe fix testing.

It configures routing, VLANs, IP addressing, and ACLs from a single source of truth,
detects when a device drifts from that source, proposes a fix, and tests every fix
in a lab **before** it is ever approved for production.

## How it works

1. **YAML files** (`data/`) describe the intended state of every device — interfaces,
   OSPF, ACLs, VLANs. This is the single source of truth.
2. **Jinja2 templates** (`templates/`) turn that YAML into real Cisco IOS commands.
3. **`deploy.py`** connects to each device over SSH (Netmiko), backs it up, and pushes
   the rendered configuration.
4. **`monitor.py`** only reads. It compares the running config against the YAML,
   checks OSPF neighbors, VLANs, security rules (SSH-only, ACL applied, no native
   VLAN 1), and connectivity. It never changes anything by itself.
5. **`dashboard.py`** / **`watch.py`** turn the results into a live HTML dashboard
   with a timeline of past checks.
6. **`validate.py`** is the core of the project: it tests a proposed fix in the lab.
   It runs the monitor before, backs up the device, applies the fix, waits for the
   network to settle, and runs the monitor again.
   - **PASS** (problem resolved, nothing new broken) → a person approves it.
   - **FAIL** → the tool restores the backup automatically.

## Project structure

| File | Role |
|---|---|
| `data/` | YAML source of truth (inventory + per-device config) |
| `templates/` | Jinja2 templates (interfaces, OSPF, ACLs, switch config) |
| `render.py` | Turns YAML + templates into Cisco commands |
| `deploy.py` | Pushes configuration to devices, with automatic backup |
| `monitor.py` | Read-only checks: drift, OSPF, VLANs, security, ping |
| `validate.py` | Tests a proposed fix in the lab; approves or rolls back |
| `dashboard.py` / `watch.py` | Live HTML status dashboard |
| `verify.py` | Quick manual verification commands per device |

## Lab topology

- **R1, R2**: Cisco routers (OSPF area 0, router-on-a-stick on R1)
- **SW1**: Layer 2 switch (VLAN 10 = users, VLAN 20 = servers)
- **PC1 / PC2**: end hosts for connectivity testing
- Built and tested on **Cisco Modeling Labs (CML)**

## Setup

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

Create a `.env` file (not committed) with:
```
NETTORA_USER=your_username
NETTORA_PASS=your_password
```

## Usage

```bash
python render.py              # preview generated configs
python deploy.py --dry-run    # preview what deploy would send
python deploy.py              # deploy for real (asks for confirmation)
python monitor.py             # run all checks once
python watch.py 30            # run checks every 30s + update dashboard
python validate.py            # test the first proposed fix in the lab
python validate.py --bad-demo # demo: test a wrong fix, watch it roll back
```

## Status

This is a **proof of concept**. It currently:
- Detects missing configuration (not extra/unexpected configuration)
- Has no user-change logging (who changed what) — planned next step
- Has no alerting yet — planned next step
- Covers OSPF, VLANs, ACLs, and basic SSH/Telnet security rules

## Author

Nadia Ben Afia — Network Security Engineer
