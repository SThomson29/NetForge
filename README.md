# NetForge

Ansible-based network configuration generator. Produces switch configuration
files from structured YAML host variables using Jinja2 templates. Currently
supports Aruba AOS-CX, with a platform-agnostic structure designed to
accommodate additional vendors in future.

Intended for use with [NetForgeUI](https://github.com/SThomson29/NetForgeUI),
a web-based frontend that manages host variables and drives config generation.
Can also be used standalone by editing YAML files directly.

---

## Directory Structure

```
NetForge/
├── inventory/
│   ├── hosts.ini
│   ├── skeleton/                    # baseline var files per platform
│   │   ├── aoscx/                   # AOS-CX skeleton files
│   │   │   ├── general.yml
│   │   │   ├── management.yml
│   │   │   ├── banner.yml
│   │   │   ├── snmp.yml
│   │   │   ├── aaa.yml
│   │   │   ├── vrfs.yml
│   │   │   ├── vlans.yml
│   │   │   ├── static_routes.yml
│   │   │   ├── interfaces.yml
│   │   │   ├── routing.yml
│   │   │   ├── vxlan.yml
│   │   │   ├── vsx.yml
│   │   │   └── vsf.yml
│   │   ├── extreme_exos/            # Extreme EXOS — planned, not yet implemented
│   │   └── extreme_voss/            # Extreme VOSS — planned, not yet implemented
│   └── host_vars/
│       └── <hostname>/
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
│           ├── vsx.yml
│           └── vsf.yml
├── scripts/
│   └── provision_host_vars.py
├── playbooks/
│   └── generate_configs.yml
└── roles/
    └── generate_config/
        ├── defaults/main.yml
        ├── tasks/main.yml
        └── templates/
            ├── CX_staticroutes.j2
            ├── CX_management.j2
            ├── CX_general.j2
            ├── CX_snmp.j2
            ├── CX_aaa.j2
            ├── CX_banner.j2
            ├── CX_vrfs.j2
            ├── CX_vlans.j2
            ├── CX_interface_groups.j2
            ├── CX_interfaces_physical.j2
            ├── CX_interfaces_lag.j2
            ├── CX_interfaces_loopback.j2
            ├── CX_interfaces_vlan.j2
            ├── CX_ospf.j2
            ├── CX_ibgp.j2
            ├── CX_vxlan.j2
            ├── CX_vsx.j2
            └── CX_vsf.j2
```

---

## Requirements

- Python 3.9 or later
- pip

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
ansible-galaxy install -r requirements.yml
```

---

## Quick Start

### 1. Add devices to hosts.ini

```ini
[cx_vsx]
core-01
core-02

[cx_vsf]
access-01

[cx:children]
cx_vsx
cx_vsf
```

### 2. Scaffold host_vars

```bash
python scripts/provision_host_vars.py
```

This copies the correct skeleton files for each host based on its group.
The hostname is pre-filled automatically. All other values default to empty
and only render in the output when explicitly populated.

### 3. Fill in host variables

Edit the YAML files in `inventory/host_vars/<hostname>/`. Each file covers
one configuration domain — only populate what you need, the rest will not
render.

### 4. Generate configs

```bash
# All devices
ansible-playbook -i inventory/hosts.ini playbooks/generate_configs.yml

# Single device
ansible-playbook -i inventory/hosts.ini playbooks/generate_configs.yml \
  --limit core-01
```

Output: `generated_configs/<hostname>_FULL.ios`

---

## Template Guards

Each template only renders when meaningful data is present. Empty skeleton
files produce no output.

| Template | Renders when |
|---|---|
| `CX_general.j2` | `hostname` is set |
| `CX_management.j2` | Local users defined, VRF set, or source interface set |
| `CX_snmp.j2` | `community` populated (v2c) or `v3_users` has entries (v3) |
| `CX_aaa.j2` | `radius_servers` list has at least one entry |
| `CX_banner.j2` | `banner.motd` or `banner.exec` is populated |
| `CX_vxlan.j2` | `loopback_ip` is set |
| `CX_ospf.j2` | `ospf_instances` list has at least one entry |
| All others | Corresponding list is non-empty |

---

## Interface Types

Physical interfaces support four port types via the `port_type` field:

| Type | Description |
|---|---|
| `access` | L2 access port |
| `trunk` | L2 trunk port |
| `routed` | L3 routed port — supports `ospf_area` and `ospf_process_id` |
| `authenticated` | Full 802.1X and MAC-auth config — VLAN list for loop-protect pulled automatically from `vlans.yml` |

LAG interfaces support `lacp_mode: off` for static LAGs — the `lacp mode`
line is suppressed entirely. Loopback interfaces always use `/32`.

---

## OSPF

OSPF is configured as a list of instances, supporting multiple processes
with separate VRFs:

```yaml
ospf_instances:
  - enabled: true
    process_id: 1
    router_id: "10.255.0.1"
    vrf: ""
    areas:
      - area_id: "0.0.0.0"
```

Leave `vrf` empty to run in the default VRF. OSPF area and process ID can
be set per-interface on physical, LAG, loopback and VLAN interfaces.

---

## Generating Specific Sections

Use `--tags` to render only the sections you need:

```bash
ansible-playbook -i inventory/hosts.ini playbooks/generate_configs.yml \
  --tags "interfaces,ospf"
```

Output for partial runs: `generated_configs/<hostname>_PARTIAL_<tags>.ios`

### Available tags

| Tag | Section |
|---|---|
| `staticroutes` | Static routes |
| `management` | Local users, SSH/HTTPS VRF, source interface |
| `general` | Hostname, NTP, DNS, timezone |
| `snmp` | SNMP config |
| `aaa` | RADIUS, AAA groups, dot1x and mac-auth |
| `banner` | MOTD and exec banners |
| `vrfs` | VRF definitions |
| `vlans` | VLAN database |
| `interfaces` | All interface types |
| `interfaces_physical` | Physical interfaces only |
| `interfaces_lag` | LAG interfaces only |
| `interfaces_loopback` | Loopback interfaces only |
| `interfaces_vlan` | VLAN interfaces (SVIs) only |
| `ospf` | OSPF instances |
| `ibgp` | iBGP / EVPN |
| `vxlan` | VTEP loopback, VXLAN interface, EVPN |
| `vsx` | VSX pairing and ISL |
| `vsf` | VSF members and ISL |
| `routing` | vrfs + ospf + ibgp |

---

## Group Naming Convention

The group a host belongs to in `hosts.ini` controls which skeleton files are
copied during provisioning:

| Group | Platform | Stacking file |
|---|---|---|
| `cx_vsx` | AOS-CX | `vsx.yml` |
| `cx_vsf` | AOS-CX | `vsf.yml` |
| `cx` | AOS-CX | none |

---

## Adding a New Platform

Support for Extreme EXOS and VOSS is planned. To add a new platform:

1. Populate `inventory/skeleton/<platform>/` with the required var files
2. Add the platform prefix to `PLATFORM_MAP` in `scripts/provision_host_vars.py`
3. Create templates using an appropriate vendor prefix
4. Add tasks for the new templates in the task file
5. Set `platform: <platform>` in the host's `general.yml`
