# CX-ConfigGen

Ansible project for generating AOS-CX switch configurations from structured
host variables using Jinja2 templates. Intended for use with the
[Network-Tools](https://github.com/Network-Team-Repository/Network-Tools)
web service, which provides a browser-based editor for host variables and
drives config generation via this repo.

---

## Directory Structure

```
CX-ConfigGen/
├── .gitignore
├── ansible.cfg
├── requirements.txt
├── requirements.yml
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
│   │   │   ├── vsx.yml              # only copied for cx_vsx group
│   │   │   └── vsf.yml              # only copied for cx_vsf group
│   │   ├── extreme_exos/            # Extreme EXOS — placeholder, not yet implemented
│   │   └── extreme_voss/            # Extreme VOSS — placeholder, not yet implemented
│   └── host_vars/
│       ├── <hostname>/
│       │   ├── general.yml          # hostname, NTP, DNS, timezone
│       │   ├── management.yml       # local users, SSH/HTTPS VRF, source interface
│       │   ├── banner.yml           # MOTD and exec banners
│       │   ├── snmp.yml             # SNMP version, community, v3 users
│       │   ├── aaa.yml              # RADIUS servers, group, dynamic auth
│       │   ├── vrfs.yml             # VRF definitions
│       │   ├── vlans.yml            # VLAN database
│       │   ├── static_routes.yml    # Static route table
│       │   ├── interfaces.yml       # Physical, LAG, loopback and VLAN interfaces
│       │   ├── routing.yml          # OSPF instances and iBGP/EVPN
│       │   ├── vxlan.yml            # VTEP loopback and VNI map
│       │   ├── vsx.yml              # VSX role, ISL, keepalive
│       │   └── vsf.yml              # VSF member IDs and ISL links
│       └── ...
├── scripts/
│   └── provision_host_vars.py       # scaffolds host_vars from skeleton
├── playbooks/
│   └── generate_configs.yml
└── roles/
    └── generate_config/
        ├── defaults/main.yml
        ├── meta/main.yml
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

## Installation

### Prerequisites

- Python 3.9 or later
- pip

It is recommended to use a virtual environment to keep project dependencies
isolated:

```bash
python3 -m venv .venv
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate           # Windows
```

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Install Ansible Galaxy collections

```bash
ansible-galaxy install -r requirements.yml
```

---

## Intended Workflow

This repo is designed to be used alongside the Network-Tools web service.
The service clones this repo, manages host_vars files via a browser-based
editor, and drives the Ansible playbook to generate configs. Direct manual
use is also supported for users comfortable working with YAML directly.

### Manual workflow (without the service)

1. Add devices to `hosts.ini` under the correct group
2. Run the provisioning script to scaffold `host_vars` directories from the skeleton
3. Edit the YAML files directly
4. Run the playbook to generate configs

```bash
python scripts/provision_host_vars.py
ansible-playbook -i inventory/hosts.ini playbooks/generate_configs.yml
```

---

## Quick Start — Provisioning a New Buildout

### Step 1 — Add devices to hosts.ini

```ini
[cx_vsx]
cx-core-01
cx-core-02

[cx_vsf]
cx-access-01
cx-access-02

[cx:children]
cx_vsx
cx_vsf
```

### Step 2 — Scaffold host_vars directories

```bash
# Scaffold all new hosts at once
python scripts/provision_host_vars.py

# Preview what would be created without writing any files
python scripts/provision_host_vars.py --dry-run

# Scaffold a single host only
python scripts/provision_host_vars.py --host cx-core-01
```

### Step 3 — Fill in host variables

All skeleton files default to empty values — nothing renders until you
explicitly populate a field. The hostname is the only value pre-filled
automatically (from the hosts.ini entry).

| File | What to fill in |
|---|---|
| `general.yml` | Hostname (pre-filled), NTP servers, DNS, timezone |
| `management.yml` | Local users, SSH/HTTPS VRF, source interface |
| `banner.yml` | MOTD and exec banner text |
| `snmp.yml` | Version, community (v2c) or v3 users |
| `aaa.yml` | RADIUS servers, group name, keys |
| `interfaces.yml` | Physical, LAG, loopback and VLAN interfaces |
| `routing.yml` | OSPF instances, iBGP/EVPN |
| `vsx.yml` or `vsf.yml` | Enable and configure whichever stacking technology applies |

### Step 4 — Generate configs

```bash
# All devices
ansible-playbook -i inventory/hosts.ini playbooks/generate_configs.yml

# A single device
ansible-playbook -i inventory/hosts.ini playbooks/generate_configs.yml \
  --limit cx-core-01
```

Output: `generated_configs/<hostname>_FULL.ios`

---

## Variable Model

All variables are defined per-device under `inventory/host_vars/<hostname>/`.
Variables are split into one file per configuration domain. Ansible loads all
`.yml` files in the directory automatically — no imports or includes are
required.

### Template guards

Each template only renders output when meaningful data is present. Empty or
unpopulated skeleton files produce no output. The guards work as follows:

| Template | Renders when |
|---|---|
| `CX_general.j2` | `hostname` is set |
| `CX_management.j2` | At least one of: local users defined, VRF set, source interface set |
| `CX_snmp.j2` | `community` populated (v2c) or `v3_users` has entries (v3) |
| `CX_aaa.j2` | `radius_servers` list has at least one entry |
| `CX_banner.j2` | `banner.motd` or `banner.exec` is populated |
| `CX_vxlan.j2` | `loopback_ip` is set |
| `CX_ospf.j2` | `ospf_instances` list has at least one entry |
| All others | Corresponding list is non-empty |

---

## Interface Types

Physical interfaces support four port types controlled by the `port_type` field:

| Type | Description |
|---|---|
| `access` | L2 access port — set `access_vlan` |
| `trunk` | L2 trunk port — set `trunk_allowed_vlans` and `trunk_native_vlan` |
| `routed` | L3 routed port — set `ip_address`, `ip_prefix`, optionally `vrf`, `ospf_area`, `ospf_process_id` |
| `authenticated` | 802.1X/MAC-auth port — full dot1x + mac-auth config rendered automatically. Set `auth_default_vlan`. VLAN list for loop-protect is pulled automatically from `vlans.yml` |

LAG interfaces support `lacp_mode: off` for static LAGs — the `lacp mode`
line is suppressed entirely when set to `off`.

Loopback interfaces always use `/32` — the prefix is not configurable.

---

## OSPF

OSPF is configured as a list of instances, supporting multiple processes with
separate VRFs:

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
    vrf: "TENANT_A"
    areas:
      - area_id: "0.0.0.1"
```

Leave `vrf` empty to run the instance in the default VRF. OSPF area and
process ID can also be set per-interface on physical, LAG, loopback and
VLAN interfaces.

---

## Sensitive Values

Sensitive values such as RADIUS keys, SNMP community strings, and local user
passwords are stored as plain text in host_vars files. This project is used
for offline config generation rather than direct device deployment, so there
are no live credentials used at runtime.

If encryption is required, Ansible Vault can be layered on top — replace any
plain text sensitive value with an encrypted string using
`ansible-vault encrypt_string` and supply `--vault-password-file` when running
the playbook.

---

## Generating Configurations

### Generate configs for all devices

```bash
ansible-playbook -i inventory/hosts.ini playbooks/generate_configs.yml
```

Output: `generated_configs/<hostname>_FULL.ios`

### Generate configs for a group or single device

```bash
# All CX switches
ansible-playbook -i inventory/hosts.ini playbooks/generate_configs.yml \
  --limit cx

# A single device
ansible-playbook -i inventory/hosts.ini playbooks/generate_configs.yml \
  --limit cx-core-01
```

### Generate a specific section

```bash
# Single section
ansible-playbook -i inventory/hosts.ini playbooks/generate_configs.yml \
  --tags vxlan

# Multiple sections
ansible-playbook -i inventory/hosts.ini playbooks/generate_configs.yml \
  --tags "ibgp,vxlan,vrfs"
```

Output for partial runs: `generated_configs/<hostname>_PARTIAL_<tags>.ios`

### Available tags

| Tag | Section rendered |
|---|---|
| `full` | Everything (default when no `--tags` supplied) |
| `staticroutes` | Static routes |
| `management` | Local users, SSH/HTTPS VRF, source interface |
| `general` | Hostname, NTP, DNS, timezone, spanning-tree |
| `snmp` | SNMP server config |
| `aaa` | RADIUS servers, AAA groups, dot1x and mac-auth policies |
| `banner` | MOTD and exec banners |
| `vrfs` | VRF definitions |
| `vlans` | VLAN database |
| `interface_groups` | System interface-groups |
| `interfaces_physical` | Physical interfaces |
| `interfaces_lag` | LAG interfaces |
| `interfaces_loopback` | Loopback interfaces |
| `interfaces_vlan` | VLAN interfaces (SVIs) |
| `ospf` | OSPF instance config |
| `ibgp` | iBGP / EVPN route reflector config |
| `vxlan` | VTEP loopback, VXLAN interface, EVPN |
| `vsx` | VSX pairing, ISL and keepalive |
| `vsf` | VSF member and ISL link config |

**Group tags:**

| Tag | Sections included |
|---|---|
| `interfaces` | interface_groups, interfaces_physical, interfaces_lag, interfaces_loopback, interfaces_vlan |
| `routing` | vrfs, ospf, ibgp |

### Override the output directory

```bash
ansible-playbook -i inventory/hosts.ini playbooks/generate_configs.yml \
  -e config_output_dir=/tmp/review
```

### Dry run

```bash
ansible-playbook -i inventory/hosts.ini playbooks/generate_configs.yml \
  --check
```

---

## Handling Empty Sections

After all sections are rendered, a cleanup task deletes any section file
containing only whitespace before the assemble step runs. Empty sections
never appear as blank blocks in the final config.

---

## Group Naming Convention

| Group | Platform | Stacking file copied |
|---|---|---|
| `cx_vsx` | AOS-CX | `vsx.yml` only |
| `cx_vsf` | AOS-CX | `vsf.yml` only |
| `cx` | AOS-CX | neither |

> **Future platforms:** Extreme EXOS (`exos`) and Extreme VOSS (`voss`) are
> planned but not yet implemented. Skeleton directories exist as placeholders.
> Templates and task entries will be added in a future release.

---

## Adding a New Vendor

Support for Extreme EXOS and Extreme VOSS is planned for a future release.
Skeleton directories already exist as placeholders. When implementing a new
platform:

1. Populate `inventory/skeleton/<platform>/` with the required var files
2. Add the platform prefix to `PLATFORM_MAP` in `scripts/provision_host_vars.py`
3. Add devices to `hosts.ini` under the appropriate group
4. Create templates using the appropriate vendor prefix
5. Add tasks for the new templates to the task file
6. Set `platform: <platform>` in the host's `general.yml`
