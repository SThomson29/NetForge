# NetForge

An Ansible-based configuration generator for Aruba AOS-CX switches. Define switch variables in YAML, run the playbook, and get complete `.ios` configuration files ready to apply.

Designed to be used alongside [NetForgeUI](https://github.com/SThomson29/NetForgeUI) — a web frontend that manages the variable files and drives generation — but can also be used standalone from the command line.

---

## Features

- Generates complete AOS-CX switch configurations from structured YAML variable files
- Supports all major AOS-CX features: L2/L3 interfaces, LAGs, SVIs, VRFs, OSPF (multi-instance, VRF-scoped), iBGP, VXLAN/EVPN, VSX, VSF, SNMP v2c/v3, RADIUS/dot1x, static routes, banners, syslog, sFlow
- Output is a single assembled `.ios` file per switch, or per-section partial files when using tags
- Partial generation via Ansible tags — generate only the sections you need

---

## Requirements

- Python 3.9+
- Ansible
- `ansible-playbook` on your PATH

Install Ansible:

```bash
pip install ansible
```

---

## Repository Structure

```
NetForge/
├── inventory/
│   ├── hosts.ini                    # Ansible inventory
│   ├── skeleton/
│   │   └── aoscx/                  # Default variable file templates
│   │       ├── general.yml
│   │       ├── interfaces.yml
│   │       └── ...
│   └── host_vars/
│       └── <hostname>/             # Per-switch variable files
│           ├── general.yml
│           ├── management.yml
│           ├── banner.yml
│           ├── snmp.yml
│           ├── aaa.yml
│           ├── vrfs.yml
│           ├── vlans.yml
│           ├── static_routes.yml
│           ├── interfaces.yml
│           ├── routing.yml
│           ├── vxlan.yml
│           ├── syslog.yml
│           ├── sflow.yml
│           ├── vsx.yml             # VSX only
│           └── vsf.yml             # VSF only
├── playbooks/
│   └── generate_configs.yml
└── roles/
    └── generate_config/
        ├── tasks/
        └── templates/              # Jinja2 templates (CX_*.j2)
```

---

## Quick Start

### 1. Clone the repo

```bash
git clone git@github.com:SThomson29/NetForge.git
cd NetForge
```

### 2. Add your switch to the inventory

Edit `inventory/hosts.ini` and add your switch to the appropriate group:

```ini
[cx_vsx]
core-01
core-02

[cx_vsf]
access-01

[cx]
dist-01

[cx:children]
cx_vsx
cx_vsf
```

| Group | Use for |
|---|---|
| `cx_vsx` | VSX pair members |
| `cx_vsf` | VSF stack |
| `cx` | Standalone switches |

### 3. Scaffold the variable files

Copy the skeleton files for your switch:

```bash
cp -r inventory/skeleton/aoscx inventory/host_vars/core-01
```

For VSX switches include `vsx.yml`; for VSF include `vsf.yml`. For all other switches these files can be omitted.

### 4. Fill in the variables

Edit the files in `inventory/host_vars/<hostname>/`. Each file is commented with available options. At minimum set `hostname` in `general.yml`.

### 5. Generate

```bash
ansible-playbook -i inventory/hosts.ini playbooks/generate_configs.yml \
  -e "config_output_dir=./generated_configs"
```

The generated `.ios` file appears at `generated_configs/<hostname>_FULL.ios`.

---

## Generating for a Single Switch

```bash
ansible-playbook -i inventory/hosts.ini playbooks/generate_configs.yml \
  -e "config_output_dir=./generated_configs" \
  --limit core-01
```

---

## Partial Generation (Tags)

Generate only specific sections using Ansible tags:

```bash
ansible-playbook -i inventory/hosts.ini playbooks/generate_configs.yml \
  -e "config_output_dir=./generated_configs" \
  --tags "ospf,interfaces"
```

Output is written as `<hostname>_PARTIAL_<tags>.ios`.

**Available tags:**

| Tag | Section |
|---|---|
| `full` | Every section (this is what a normal run uses) |
| `general` | Hostname, NTP, DNS, timezone |
| `management` | Management VRF, source interface, local users |
| `banner` | MOTD and exec banners |
| `snmp` | SNMP v2c/v3 |
| `aaa` | RADIUS, dot1x, dynamic authorisation |
| `vrfs` | VRF definitions |
| `vlans` | VLAN definitions |
| `staticroutes` | Static routes |
| `interfaces` | All interface types (groups, physical, LAG, loopback, SVI) |
| `interface_groups` | Interface group / speed split config only |
| `interfaces_physical` | Physical interfaces only |
| `interfaces_lag` | LAG interfaces only |
| `interfaces_loopback` | Loopback interfaces only |
| `interfaces_vlan` | VLAN interfaces (SVIs) only |
| `ospf` | OSPF instances |
| `ibgp` | iBGP |
| `routing` | VRFs + OSPF + iBGP combined |
| `vxlan` | VXLAN/VTEP |
| `vsx` | VSX stacking |
| `vsf` | VSF stacking |
| `syslog` | Syslog server |
| `sflow` | sFlow collector and agent |

---

## Variable File Reference

### general.yml

```yaml
hostname: core-01
platform: aoscx
profile: default
timezone: Europe/London
ntp_servers:
  - 10.0.0.123
dns:
  domain_name: corp.local
  name_servers:
    - 10.0.0.53
```

### interfaces.yml — routed physical interface

```yaml
physical_interfaces:
  - name: "1/1/1"
    description: "P2P to core-02"
    admin: up
    mtu: 9198
    routed: true
    port_type: routed
    vrf: ""
    ip_address: "10.254.0.0"
    ip_prefix: "31"
    ospf_area: "0.0.0.0"
    ospf_process_id: 1
```

### interfaces.yml — authenticated port (dot1x/MAC-auth)

```yaml
physical_interfaces:
  - name: "1/1/5"
    description: "NAC port"
    admin: up
    port_type: authenticated
    auth_default_vlan: "99"
```

`mtu` is deliberately absent — it is not applicable to an authenticated port and
is not rendered for `port_type: authenticated`, even if present in the file.

### syslog.yml

```yaml
syslog:
  server: "10.0.0.50"
  severity: "info"
```

Nothing is generated unless `server` is populated. Valid severities are
`emerg`, `alert`, `crit`, `err`, `warning`, `notice`, `info`, `debug`.

Leaving `severity` empty is safe — the keyword is omitted entirely rather than
rendering a `severity` with no value. Note that the switch then applies its own
default severity rather than none.

### sflow.yml

```yaml
sflow:
  collector_ip: "10.0.0.60"
  agent_ip: "10.255.0.1"
```

Nothing is generated unless `collector_ip` is populated. Leaving `agent_ip`
empty is safe — the `sflow agent-ip` line is omitted rather than rendered blank.

### routing.yml — multiple OSPF instances

```yaml
ospf_instances:
  - enabled: true
    process_id: 1
    router_id: "10.255.0.1"
    vrf: ""
    areas:
      - area_id: "0.0.0.0"
  - enabled: true
    process_id: 2
    router_id: "10.255.1.1"
    vrf: "PROD"
    areas:
      - area_id: "0.0.0.0"
```

### vsx.yml

```yaml
vsx:
  enabled: true
  role: primary          # primary or secondary
  system_mac: "00:01:00:00:00:01"
  isl_port: lag256
  keepalive:
    peer_ip: "192.168.255.2"
    src_ip: "192.168.255.1"
    vrf: mgmt
  peer_ip: "10.255.0.2"
```

---

## Testing

Template smoke tests (no Ansible required):

```bash
pip install pytest jinja2 pyyaml
pytest tests/test_generation.py::TestJinja2Templates -v
```

Full generation fixture tests (requires Ansible):

```bash
# First run — generate golden .ios files
UPDATE_FIXTURES=1 pytest tests/test_generation.py::test_update_fixtures -v -s
git add tests/fixtures/
git commit -m "Add generation test golden files"

# Subsequent runs — compare against golden files
pytest tests/test_generation.py -v
```

---

## Using with NetForgeUI

NetForgeUI clones this repo automatically on startup and drives generation via the web interface. No manual setup of `hosts.ini` or `host_vars` is needed — the UI manages all of that per project workspace.

See the [NetForgeUI repo](https://github.com/SThomson29/NetForgeUI) for deployment instructions.
