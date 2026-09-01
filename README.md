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
- Deploys generated config to live switches with a diff-first dry run, an on-box
  checkpoint and a dead-man's-switch rollback
- Pushes AOS-CX firmware to a chosen partition and boots to it, optionally
  permitting non-failsafe subcomponent updates

---

## Requirements

Config generation needs only Ansible:

- Python 3.9+
- `ansible-core` and `ansible-playbook` on your PATH

```bash
pip install ansible-core
```

The deploy and firmware playbooks additionally need the AOS-CX collection and,
for the REST modules, `pyaoscx`:

```bash
pip install pyaoscx
ansible-galaxy install -r requirements.yml
```

`requirements.yml` pins the collection version. NetForgeUI installs the same
version in its image — keep the two in step.

Only `aoscx_config` and `aoscx_command` use SSH; every other module in the
collection, including both firmware modules, uses the REST API. A single play
cannot mix the two, which is why the firmware playbook is split into three.

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
│   ├── generate_configs.yml    # render host_vars into .ios files
│   ├── deploy_dryrun.yml       # diff generated config against running config
│   ├── deploy_push.yml         # push config with checkpoint + rollback
│   └── firmware_upgrade.yml    # upload image, optionally permit non-failsafe
│                               #   updates, boot to partition
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

### interfaces.yml — OSPF authentication

`ospf_auth_key` enables OSPF MD5 authentication on an interface. Valid on
routed physical interfaces, routed LAGs and SVIs. Leave it empty (or omit it)
for no authentication — the key ID is fixed at 1.

```yaml
physical_interfaces:
  - name: "1/1/1"
    routed: true
    port_type: routed
    ip_address: "10.254.0.0"
    ip_prefix: "31"
    ospf_area: "0.0.0.0"
    ospf_process_id: 1
    ospf_auth_key: "SharedAreaZeroKey"
```

Renders as:

```
    ip ospf 1 area 0.0.0.0
    ip ospf authentication message-digest
    ip ospf message-digest-key 1 md5 plaintext SharedAreaZeroKey
```

Not applicable to loopback interfaces.

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

## Deploy and Firmware Playbooks

These talk to live switches. NetForgeUI drives them and passes the extra-vars
below; they can also be run directly.

### deploy_dryrun.yml — diff only

Shows what would change without applying anything.

| Extra-var | Required | Description |
|---|---|---|
| `deploy_username` / `deploy_password` | yes | switch credentials |
| `config_dir` | yes | directory holding generated configs |
| `deploy_config_file` | no | explicit file to deploy (default `<config_dir>/<hostname>_FULL.ios`) |
| `results_file` | yes | directory to write per-host JSON into |

### deploy_push.yml — apply with rollback

Takes an on-box checkpoint, schedules a rollback job, pushes the config, then
cancels the rollback only once the switch is confirmed reachable. Same
extra-vars as the dry run, plus:

| Extra-var | Required | Description |
|---|---|---|
| `rollback_timeout` | no | rollback timer in minutes (default 5) |

### firmware_upgrade.yml — upload and boot

Three plays, because a play cannot mix REST and SSH modules: upload (REST),
permit non-failsafe updates (SSH, only if asked), boot (REST).

| Extra-var | Required | Description |
|---|---|---|
| `deploy_username` / `deploy_password` | yes | switch credentials |
| `firmware_file` | yes | path to the `.swi` image on the controller |
| `firmware_partition` | no | `primary` or `secondary` (default `secondary`) |
| `allow_unsafe` | no | permit non-failsafe subcomponent updates (default `false`) |
| `unsafe_window_mins` | no | how long to permit them for, 1–120 (default 30) |
| `results_file` | yes | directory to write per-host JSON into |

```bash
ansible-playbook -i inventory/hosts.ini playbooks/firmware_upgrade.yml \
  -e deploy_username=admin -e deploy_password=secret \
  -e firmware_file=/images/ArubaOS-CX_6400-6300_10_16_0002.swi \
  -e firmware_partition=secondary \
  -e results_file=/tmp/fwresults
```

**On `allow_unsafe`.** Some releases include firmware updates for programmable
subcomponents that will not apply without explicit permission. The command has
no REST equivalent, so it is issued over SSH, and it was renamed in 10.15.1010
— the playbook reads `show version` and picks `allow-non-failsafe-updates` or
`allow-unsafe-updates` to match the release the switch is currently running,
not the one being installed. The permission is a countdown timer, so it is set
after the upload rather than before it.

The upload polls for up to ten minutes, and the boot allows fifteen minutes for
the switch to return, since a non-failsafe update can involve several reboots.

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

NetForgeUI clones this repo automatically on startup and drives generation, deploy and firmware via the web interface. No manual setup of `hosts.ini` or `host_vars` is needed — the UI manages all of that per project workspace.

Generation runs in a sandboxed ephemeral container, because it renders
user-authored Jinja. Deploy and firmware run in the NetForgeUI container
itself, since they render nothing and need network access to the switches.

See the [NetForgeUI repo](https://github.com/SThomson29/NetForgeUI) for deployment instructions.
