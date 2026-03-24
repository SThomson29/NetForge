"""
Config generation fixture tests for NetForge.

These tests run ansible-playbook against pre-built host_vars fixture sets
and assert that the generated .ios output matches expected golden files.

Run with:
    pytest tests/test_generation.py -v

Requirements:
    - ansible-playbook on PATH (or set ANSIBLE_BIN env var)
    - Python 3.9+
    - pytest, pyyaml

Structure:
    tests/
        test_generation.py          (this file)
        fixtures/
            <scenario_name>/
                hosts.ini
                host_vars/
                    <hostname>/
                        *.yml
                expected/
                    <hostname>_FULL.ios
"""

import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import pytest
import yaml


ANSIBLE_BIN = os.environ.get('ANSIBLE_BIN', 'ansible-playbook')
REPO_ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAYBOOK    = os.path.join(REPO_ROOT, 'playbooks', 'generate_configs.yml')
ROLES_PATH  = os.path.join(REPO_ROOT, 'roles')
FIXTURES    = os.path.join(os.path.dirname(__file__), 'fixtures')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_playbook(hosts_ini, host_vars_dir, output_dir, limit=None, tags=None):
    """Run ansible-playbook and return (returncode, stdout)."""
    env = os.environ.copy()
    env['ANSIBLE_ROLES_PATH'] = ROLES_PATH
    env['ANSIBLE_STDOUT_CALLBACK'] = 'default'
    env['ANSIBLE_FORCE_COLOR'] = '0'

    cmd = [
        ANSIBLE_BIN,
        '-i', hosts_ini,
        PLAYBOOK,
        '-e', f'config_output_dir={output_dir}',
    ]
    if limit:
        cmd += ['--limit', limit]
    if tags:
        cmd += ['--tags', tags]

    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout + result.stderr


def normalise(text):
    """Normalise generated config for comparison:
    - Strip trailing whitespace from each line
    - Collapse multiple blank lines to one
    - Strip leading/trailing blank lines
    """
    lines = [line.rstrip() for line in text.splitlines()]
    # Collapse consecutive blank lines
    result = []
    prev_blank = False
    for line in lines:
        if line == '':
            if not prev_blank:
                result.append(line)
            prev_blank = True
        else:
            result.append(line)
            prev_blank = False
    return '\n'.join(result).strip()


def load_fixture(scenario):
    """Return (hosts_ini_path, host_vars_base, expected_dir) for a fixture scenario."""
    scenario_dir = os.path.join(FIXTURES, scenario)
    hosts_ini    = os.path.join(scenario_dir, 'hosts.ini')
    host_vars    = os.path.join(scenario_dir, 'host_vars')
    expected     = os.path.join(scenario_dir, 'expected')
    return hosts_ini, host_vars, expected


def get_scenarios():
    """Discover all fixture scenarios."""
    if not os.path.isdir(FIXTURES):
        return []
    return [
        d for d in os.listdir(FIXTURES)
        if os.path.isdir(os.path.join(FIXTURES, d))
        and not d.startswith('.')
    ]


# ---------------------------------------------------------------------------
# Core generation test
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not shutil.which(ANSIBLE_BIN),
    reason=f'ansible-playbook not found at {ANSIBLE_BIN}'
)
@pytest.mark.parametrize('scenario', get_scenarios() or ['__no_fixtures__'])
def test_generate_scenario(scenario, tmp_path):
    """
    For each fixture scenario:
    1. Run ansible-playbook against the fixture host_vars
    2. For each expected .ios file, compare generated output to golden file
    """
    if scenario == '__no_fixtures__':
        pytest.skip('No fixture scenarios found in tests/fixtures/')

    hosts_ini, host_vars_base, expected_dir = load_fixture(scenario)

    if not os.path.isfile(hosts_ini):
        pytest.fail(f'Missing hosts.ini for scenario {scenario}')

    # Create a temporary host_vars symlink structure
    output_dir = str(tmp_path / 'output')
    os.makedirs(output_dir)

    # Copy host_vars into the repo's inventory so Ansible can find them
    # (Ansible resolves host_vars relative to the inventory file)
    with tempfile.TemporaryDirectory() as inv_dir:
        # Copy hosts.ini
        shutil.copy(hosts_ini, os.path.join(inv_dir, 'hosts.ini'))
        # Copy host_vars
        if os.path.isdir(host_vars_base):
            shutil.copytree(host_vars_base, os.path.join(inv_dir, 'host_vars'))

        inv_file = os.path.join(inv_dir, 'hosts.ini')
        rc, output = run_playbook(inv_file, inv_dir, output_dir)

    if rc != 0:
        pytest.fail(
            f'ansible-playbook failed for scenario {scenario} (rc={rc}):\n{output}'
        )

    # Compare generated configs to expected golden files
    if not os.path.isdir(expected_dir):
        pytest.skip(f'No expected/ directory for scenario {scenario} — run with --update-fixtures to create')

    expected_files = [f for f in os.listdir(expected_dir) if f.endswith('.ios')]
    if not expected_files:
        pytest.skip(f'No .ios files in expected/ for scenario {scenario}')

    failures = []
    for expected_file in expected_files:
        expected_path   = os.path.join(expected_dir, expected_file)
        generated_path  = os.path.join(output_dir, expected_file)

        if not os.path.exists(generated_path):
            failures.append(f'  MISSING: {expected_file} not generated')
            continue

        with open(expected_path) as f:
            expected_content = normalise(f.read())
        with open(generated_path) as f:
            generated_content = normalise(f.read())

        if expected_content != generated_content:
            # Show a diff
            import difflib
            diff = '\n'.join(difflib.unified_diff(
                expected_content.splitlines(),
                generated_content.splitlines(),
                fromfile=f'expected/{expected_file}',
                tofile=f'generated/{expected_file}',
                lineterm='',
            ))
            failures.append(f'  DIFF for {expected_file}:\n{textwrap.indent(diff, "    ")}')

    if failures:
        pytest.fail(f'Generation mismatch for scenario {scenario}:\n' + '\n'.join(failures))


# ---------------------------------------------------------------------------
# Fixture update helper
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not shutil.which(ANSIBLE_BIN),
    reason=f'ansible-playbook not found at {ANSIBLE_BIN}'
)
def test_update_fixtures(tmp_path):
    """
    Run with: pytest tests/test_generation.py::test_update_fixtures -v -s
    Updates all golden .ios files from the current generation output.
    Use this after intentional template changes to update the baseline.
    """
    if not os.environ.get('UPDATE_FIXTURES'):
        pytest.skip('Set UPDATE_FIXTURES=1 to run fixture update')

    scenarios = get_scenarios()
    if not scenarios:
        pytest.skip('No scenarios found')

    for scenario in scenarios:
        hosts_ini, host_vars_base, expected_dir = load_fixture(scenario)
        if not os.path.isfile(hosts_ini):
            continue

        output_dir = str(tmp_path / scenario / 'output')
        os.makedirs(output_dir)

        with tempfile.TemporaryDirectory() as inv_dir:
            shutil.copy(hosts_ini, os.path.join(inv_dir, 'hosts.ini'))
            if os.path.isdir(host_vars_base):
                shutil.copytree(host_vars_base, os.path.join(inv_dir, 'host_vars'))
            inv_file = os.path.join(inv_dir, 'hosts.ini')
            rc, output = run_playbook(inv_file, inv_dir, output_dir)

        if rc != 0:
            print(f'SKIP {scenario}: playbook failed\n{output}')
            continue

        os.makedirs(expected_dir, exist_ok=True)
        for fname in os.listdir(output_dir):
            if fname.endswith('.ios'):
                shutil.copy(
                    os.path.join(output_dir, fname),
                    os.path.join(expected_dir, fname),
                )
        print(f'Updated fixtures for scenario: {scenario}')


# ---------------------------------------------------------------------------
# Built-in minimal fixture — L3 routed interface + loopback
# ---------------------------------------------------------------------------

@pytest.fixture(scope='session', autouse=True)
def create_minimal_fixtures():
    """
    Create a minimal built-in fixture scenario so there's always something
    to run even before any hand-crafted fixtures exist.
    """
    scenario_dir = os.path.join(FIXTURES, 'minimal_l3')
    os.makedirs(os.path.join(scenario_dir, 'host_vars', 'core-01'), exist_ok=True)

    # hosts.ini
    with open(os.path.join(scenario_dir, 'hosts.ini'), 'w') as f:
        f.write('[cx]\ncore-01\n\n[cx:children]\n')

    host_vars = {
        'general.yml': textwrap.dedent("""\
            hostname: core-01
            platform: aoscx
            profile: default
            config_output_dir: ./generated_configs
            timezone: Europe/London
            ntp_servers:
              - 10.0.0.123
            aruba:
              central:
                disabled: false
            dns:
              domain_name: lab.local
              name_servers:
                - 10.0.0.53
        """),
        'management.yml': textwrap.dedent("""\
            management:
              vrf: mgmt
              source_interface: loopback0
            local_users:
              - username: admin
                group: administrators
                password: "AES256:somehash"
        """),
        'banner.yml': "banner:\n  motd: 'Authorised access only'\n  exec:\n",
        'snmp.yml': textwrap.dedent("""\
            snmp:
              version: v2c
              vrf: mgmt
              system_description: Lab Core Switch
              location: Lab
              contact: noc@lab.local
              community: public
              v3_users: []
        """),
        'aaa.yml': textwrap.dedent("""\
            radius_server_key:
            radius_group_name: RADIUS_GROUP
            dynamic_authorization: false
            radius_servers: []
        """),
        'vrfs.yml': textwrap.dedent("""\
            vrfs:
              - name: mgmt
        """),
        'vlans.yml': textwrap.dedent("""\
            vlans:
              - id: 100
                name: Management
              - id: 200
                name: Production
        """),
        'static_routes.yml': "static_routes: []\n",
        'interfaces.yml': textwrap.dedent("""\
            interface_groups: []
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
              - name: "1/1/48"
                description: "Access port"
                admin: up
                mtu: 9198
                routed: false
                port_type: access
                access_vlan: "100"
                trunk_allowed_vlans: ""
                trunk_native_vlan: 1
            lag_interfaces: []
            loopback_interfaces:
              - name: loopback0
                description: "Router ID"
                ip_address: "10.255.0.1"
                ip_prefix: "32"
                vrf: ""
                ospf_area: "0.0.0.0"
                ospf_process_id: 1
            vlan_interfaces:
              - name: vlan100
                description: "Management SVI"
                admin: up
                vrf: mgmt
                ip_address: "10.100.0.1"
                ip_prefix: 24
                helper_addresses: []
                ospf_area: ""
                ospf_process_id: 1
                ospf_passive: true
                active_gateway_ip: ""
                active_gateway_mac: ""
                mtu_jumbo: false
        """),
        'routing.yml': textwrap.dedent("""\
            ospf_instances:
              - enabled: true
                process_id: 1
                router_id: "10.255.0.1"
                vrf: ""
                areas:
                  - area_id: "0.0.0.0"
            device_role: spine
            bgp:
              asn:
              router_id:
              neighbors: []
        """),
        'vxlan.yml': textwrap.dedent("""\
            loopback_interface: loopback1
            loopback_ip:
            ospf_area: 0.0.0.0
            vxlan:
              vni_map: []
        """),
    }

    hv_dir = os.path.join(scenario_dir, 'host_vars', 'core-01')
    for fname, content in host_vars.items():
        fpath = os.path.join(hv_dir, fname)
        if not os.path.exists(fpath):
            with open(fpath, 'w') as f:
                f.write(content)

    yield

    # Don't clean up — fixtures are part of the repo


# ---------------------------------------------------------------------------
# Template smoke tests (no Ansible required)
# ---------------------------------------------------------------------------

class TestJinja2Templates:
    """
    Smoke test the Jinja2 templates directly without running Ansible.
    These catch template syntax errors immediately.
    """

    TEMPLATES_DIR = os.path.join(REPO_ROOT, 'roles', 'generate_config', 'templates')

    @pytest.fixture
    def jinja_env(self):
        """Create a Jinja2 environment pointed at the templates directory."""
        try:
            from jinja2 import Environment, FileSystemLoader, StrictUndefined
        except ImportError:
            pytest.skip('jinja2 not installed')
        env = Environment(
            loader=FileSystemLoader(self.TEMPLATES_DIR),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        return env

    @pytest.fixture
    def minimal_vars(self):
        """Minimal variable set that all templates should handle gracefully."""
        return {
            'hostname': 'test-switch',
            'timezone': 'Europe/London',
            'ntp_servers': [],
            'aruba': {'central': {'disabled': False}},
            'dns': {'domain_name': '', 'name_servers': []},
            'management': {'vrf': '', 'source_interface': 'loopback0'},
            'local_users': [],
            'banner': {'motd': '', 'exec': ''},
            'snmp': {
                'version': 'v2c', 'vrf': '', 'system_description': '',
                'location': '', 'contact': '', 'community': '', 'v3_users': [],
            },
            'radius_server_key': '',
            'radius_group_name': 'RADIUS_GROUP',
            'dynamic_authorization': False,
            'radius_servers': [],
            'vrfs': [],
            'vlans': [],
            'static_routes': [],
            'interface_groups': [],
            'physical_interfaces': [],
            'lag_interfaces': [],
            'loopback_interfaces': [],
            'vlan_interfaces': [],
            'ospf_instances': [],
            'device_role': '',
            'bgp': {'asn': '', 'router_id': '', 'neighbors': []},
            'loopback_interface': 'loopback1',
            'loopback_ip': '',
            'ospf_area': '0.0.0.0',
            'vxlan': {'vni_map': []},
        }

    @pytest.mark.skipif(
        not os.path.isdir(os.path.join(REPO_ROOT, 'roles', 'generate_config', 'templates')),
        reason='Templates directory not found — ensure NetForge repo is cloned'
    )
    def test_all_templates_render_with_empty_vars(self, jinja_env, minimal_vars):
        """All templates should render without errors given minimal/empty variables."""
        template_files = [
            f for f in os.listdir(self.TEMPLATES_DIR)
            if f.endswith('.j2')
        ]
        assert template_files, 'No .j2 templates found'
        errors = []
        for tfile in sorted(template_files):
            try:
                tmpl = jinja_env.get_template(tfile)
                tmpl.render(**minimal_vars)
            except Exception as e:
                errors.append(f'{tfile}: {e}')
        if errors:
            pytest.fail('Template render errors:\n' + '\n'.join(errors))

    @pytest.mark.skipif(
        not os.path.isdir(os.path.join(REPO_ROOT, 'roles', 'generate_config', 'templates')),
        reason='Templates directory not found'
    )
    def test_general_template_outputs_hostname(self, jinja_env, minimal_vars):
        minimal_vars['hostname'] = 'my-switch'
        tmpl = jinja_env.get_template('CX_general.j2')
        output = tmpl.render(**minimal_vars)
        assert 'my-switch' in output

    @pytest.mark.skipif(
        not os.path.isdir(os.path.join(REPO_ROOT, 'roles', 'generate_config', 'templates')),
        reason='Templates directory not found'
    )
    def test_ospf_template_with_instance(self, jinja_env, minimal_vars):
        minimal_vars['ospf_instances'] = [{
            'enabled': True,
            'process_id': 1,
            'router_id': '10.255.0.1',
            'vrf': '',
            'areas': [{'area_id': '0.0.0.0'}],
        }]
        tmpl = jinja_env.get_template('CX_ospf.j2')
        output = tmpl.render(**minimal_vars)
        assert 'router ospf' in output.lower() or 'ospf' in output.lower()

    @pytest.mark.skipif(
        not os.path.isdir(os.path.join(REPO_ROOT, 'roles', 'generate_config', 'templates')),
        reason='Templates directory not found'
    )
    def test_interfaces_template_with_loopback(self, jinja_env, minimal_vars):
        minimal_vars['loopback_interfaces'] = [{
            'name': 'loopback0',
            'description': 'Router ID',
            'ip_address': '10.255.0.1',
            'ip_prefix': '32',
            'vrf': '',
            'ospf_area': '0.0.0.0',
            'ospf_process_id': 1,
        }]
        tmpl = jinja_env.get_template('CX_interfaces_loopback.j2')
        output = tmpl.render(**minimal_vars)
        assert 'loopback0' in output
        assert '10.255.0.1' in output

    @pytest.mark.skipif(
        not os.path.isdir(os.path.join(REPO_ROOT, 'roles', 'generate_config', 'templates')),
        reason='Templates directory not found'
    )
    def test_none_values_do_not_cause_iteration_errors(self, jinja_env, minimal_vars):
        """Templates should handle None values without 'NoneType not iterable' errors."""
        minimal_vars['ntp_servers'] = None
        minimal_vars['vrfs'] = None
        minimal_vars['vlans'] = None
        minimal_vars['physical_interfaces'] = None
        tmpl = jinja_env.get_template('CX_general.j2')
        # Should not raise
        tmpl.render(**minimal_vars)
