"""Offline tests: block subprocess execution, including absolute executable paths."""
import copy
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('netslice_control', str(ROOT / 'bin/netslice-control'))
spec = importlib.util.spec_from_loader(loader.name, loader)
control = importlib.util.module_from_spec(spec)
loader.exec_module(control)


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / 'netslice.conf'
        self.config.write_text((ROOT / 'configs/netslice.conf').read_text())
        self.c = control.config(self.config)
        cg = self.root / 'slice'
        cg.mkdir()
        (cg / 'cgroup.controllers').touch()
        self.membership = self.root / 'self-cgroup'
        self.membership.write_text('0::/system.slice/system-netslice.slice/test.scope\n')
        for name, value in [('CONFIG', self.config), ('TEMPLATE', ROOT / 'nftables/netslice.nft'),
                            ('CGROUP', cg), ('SELF_CGROUP', self.membership),
                            ('LOCK', self.root / 'control.lock')]:
            self.enterContext(patch.object(control, name, value))
        self.enterContext(patch('subprocess.run', side_effect=AssertionError('host command forbidden')))
        self.enterContext(patch.object(control.os, 'execv', side_effect=AssertionError('unmocked application execution forbidden')))
        self.calls = []
        self.rules, self.routes = [], []
        self.addresses = [{'addr_info': [{'local': '192.0.2.1', 'prefixlen': 32}]}]
        self.link = True
        self.firewall = control.render(self.c)
        self.exists = True
        self.fail = None
        self.enterContext(patch.object(control, 'run', side_effect=self.fake_run))

    def fake_run(self, command, *args, input=None, optional=False):
        args = list(map(str, args))
        self.calls.append((command, args, input))
        if self.fail and self.fail(command, args):
            raise control.Error('injected command failure')
        output, code, error = '', 0, ''
        if command == 'nft':
            if args == ['-j', 'list', 'tables']:
                output = json.dumps({'nftables': [{'table': {'family': 'inet', 'name': control.TABLE}}] if self.exists else []})
            elif args == ['-s', '-n', '-y', 'list', 'table', 'inet', control.TABLE]:
                if not self.exists:
                    raise control.Error('table missing')
                output = self.firewall
            elif args == ['-f', '-']:
                self.exists = True
                self.firewall = input.split('delete table inet netslice_guard\n')[-1]
            else:
                raise AssertionError(('unexpected nft command', args))
        elif command == 'systemctl':
            self.assertEqual(args[0], 'is-active')
            output = 'active\n'
        elif command == 'ip':
            clean = [v for v in args if v not in ('-j', '-N', '-4')]
            if clean[:2] == ['rule', 'show']:
                output = json.dumps(self.rules)
            elif clean[:2] == ['route', 'show']:
                output = json.dumps(self.routes)
            elif clean[:2] == ['link', 'show']:
                code = 0 if self.link else 1
                output = json.dumps([{'flags': ['UP']}]) if self.link else ''
            elif clean[:2] == ['address', 'show']:
                output = json.dumps(self.addresses)
            elif clean[:2] == ['rule', 'add']:
                self.rules.append(self.owned_rule())
            elif clean[:2] == ['rule', 'del']:
                self.rules.clear()
            elif clean[:2] == ['route', 'add']:
                route = {'dst': 'default', 'protocol': 186, 'metric': int(clean[-1]), 'flags': []}
                if 'dev' in clean:
                    route['dev'] = clean[clean.index('dev')+1]
                else:
                    route['type'] = 'unreachable'
                self.routes.append(route)
            elif clean[:2] == ['route', 'del']:
                metric = int(clean[-1])
                self.routes = [r for r in self.routes if r['metric'] != metric]
            elif clean[:2] == ['address', 'add']:
                value = clean[2].split('/')
                self.addresses[0]['addr_info'].append({'local': value[0], 'prefixlen': int(value[1])})
            elif clean[:2] == ['link', 'set']:
                pass
            else:
                raise AssertionError(('unexpected ip command', args))
        else:
            raise AssertionError(command)
        return subprocess.CompletedProcess([command, *args], code, output, error)

    def owned_rule(self):
        return {'priority': 10555, 'src': 'all', 'fwmark': '0x15b3', 'table': 101, 'protocol': 186}

    def mutations(self):
        return [(cmd, args) for cmd, args, _ in self.calls if any(v in args for v in ('add', 'del', 'set', '-f'))]

    def test_configuration_rejects_shell_execution_and_bad_values(self):
        for text in ['NETSLICE_TABLE=$(touch /tmp/bad)', 'source /etc/other',
                     'UNKNOWN=value', 'NETSLICE_TABLE=254', 'NETSLICE_FWMARK=0',
                     'NETSLICE_TUN_DEV=lo', 'NETSLICE_SLICE=other.slice',
                     'NETSLICE_TZ=../UTC', 'NETSLICE_TABLE=101\nNETSLICE_TABLE=102']:
            with self.subTest(text=text):
                self.config.write_text(text)
                with self.assertRaises((control.Error, ValueError)):
                    control.config(self.config)
        self.assertFalse(self.calls)

    def test_configuration_missing_fails_without_commands(self):
        self.config.unlink()
        with self.assertRaises(OSError):
            control.config(self.config)
        self.assertFalse(self.calls)

    def test_weakened_template_does_not_redefine_protection(self):
        template = self.root / 'damaged.nft'
        template.write_text(control.TEMPLATE.read_text().replace('counter drop', 'counter accept'))
        with patch.object(control, 'TEMPLATE', template):
            with self.assertRaises(control.Error):
                control.firewall_ready(self.c)
            with self.assertRaises(control.Error):
                control.firewall_apply(self.c)
        self.assertFalse(self.mutations())

    def test_absent_kernel_table_is_initialized_but_permission_failure_is_not(self):
        original = self.fake_run
        def missing_table(cmd, *args, **kwargs):
            if cmd == 'ip' and list(args)[-5:] == ['-4', 'route', 'show', 'table', '101'] and not self.routes:
                return subprocess.CompletedProcess([], 2, '[]', 'Error: ipv4: FIB table does not exist.\nDump terminated\n')
            return original(cmd, *args, **kwargs)
        with patch.object(control, 'run', side_effect=missing_table):
            control.routing_reconcile(self.c)
        self.assertEqual(len(self.routes), 2)
        self.calls.clear()
        def denied(cmd, *args, **kwargs):
            if cmd == 'ip' and 'route' in args and 'show' in args:
                return subprocess.CompletedProcess([], 1, '', 'Operation not permitted')
            return original(cmd, *args, **kwargs)
        with patch.object(control, 'run', side_effect=denied):
            with self.assertRaises(control.Error):
                control.routing_reconcile(self.c)
        self.assertFalse(self.mutations())

    def test_firewall_readiness_checks_hooks_rules_identity_and_order(self):
        good = self.firewall
        control.firewall_ready(self.c)
        for old, new in [('priority -150', 'priority -149'), ('counter drop', 'counter accept'),
                         ('level 2', 'level 1'), ('policy accept', 'policy drop'),
                         ('xray_tun', 'eth0'), ('meta mark set 5555', 'meta mark set 5556'),
                         ('meta nfproto ipv4', 'meta nfproto 10'),
                         ('meta nfproto ipv6', 'meta nfproto 2')]:
            with self.subTest(old=old):
                self.firewall = good.replace(old, new)
                with self.assertRaises(control.Error):
                    control.firewall_ready(self.c)
        self.firewall = good.replace('chain guard_out', 'flags dormant\nchain guard_out')
        with self.assertRaises(control.Error):
            control.firewall_ready(self.c)
        self.assertFalse(self.mutations())

    def test_nft_dump_canonicalization(self):
        inode = str(control.cgroup_id())
        self.firewall = self.firewall.replace('level 2 ' + inode, 'level 2 "system.slice/system-netslice.slice"')
        self.firewall = self.firewall.replace('set 5555', 'set 0x000015b3').replace('meta mark 5555', 'meta mark 0x000015b3')
        self.firewall = self.firewall.replace('counter', 'counter packets 11 bytes 500')
        self.firewall = self.firewall.replace('0x4e530001', '4e53:1')
        self.firewall = self.firewall.replace('meta nfproto ipv4', 'meta nfproto 2')
        self.firewall = self.firewall.replace('meta nfproto ipv6', 'meta nfproto 10')
        control.firewall_ready(self.c)

    def test_numeric_family_normalization_is_expression_specific(self):
        self.assertEqual(control.tokens('meta nfproto 2 meta nfproto 10 socket cgroupv2 level 2 10 priority 2'),
                         ['meta', 'nfproto', 'ipv4', 'meta', 'nfproto', 'ipv6',
                          'socket', 'cgroupv2', 'level', '2', '10', 'priority', '2'])

    def test_human_supplied_kernel_dump_matches_expected_firewall(self):
        self.firewall = (ROOT / 'tests/fixtures/nft-numeric-dump.nft').read_text()
        with patch.object(control, 'cgroup_id', return_value=812):
            control.firewall_ready(self.c)
        self.assertFalse(self.mutations())

    def test_stale_cgroup_identity_is_rejected(self):
        self.firewall = self.firewall.replace(str(control.cgroup_id()), '987654321')
        with self.assertRaises(control.Error):
            control.firewall_ready(self.c)

    def test_readiness_mismatch_reports_expected_and_actual_without_mutation(self):
        self.firewall = self.firewall.replace('priority -150', 'priority -149')
        with self.assertRaisesRegex(control.Error, r"expected \['-150'.*actual \['-149'"):
            control.firewall_ready(self.c)
        self.assertFalse(self.mutations())

    def test_atomic_firewall_initialization_repeated_and_first_start(self):
        self.exists = False
        control.firewall_apply(self.c)
        control.firewall_apply(self.c)
        control.firewall_apply(self.c)
        transactions = [text for cmd, args, text in self.calls if cmd == 'nft' and args == ['-f', '-']]
        self.assertEqual(len(transactions), 3)
        self.assertFalse(transactions[0].startswith('delete'))
        self.assertTrue(all(s.startswith('delete table inet netslice_guard\n') for s in transactions[1:]))
        self.assertTrue(all('flush ruleset' not in s and 'netslice_cgroup' not in control.tokens(s) for s in transactions))

    def test_partial_owned_firewall_can_be_repaired(self):
        self.firewall = self.firewall.replace('meta mark set 5555 counter', 'counter')
        control.firewall_apply(self.c)
        control.firewall_ready(self.c)

    def test_foreign_firewall_table_is_not_overwritten(self):
        self.firewall = 'table inet netslice_guard {}'
        with self.assertRaises(control.Error):
            control.firewall_apply(self.c)
        self.assertFalse(self.mutations())

    def test_failed_transaction_retains_old_firewall(self):
        before = self.firewall
        self.fail = lambda cmd, args: cmd == 'nft' and '-f' in args
        with self.assertRaises(control.Error):
            control.firewall_apply(self.c)
        self.assertEqual(before, self.firewall)

    def test_firewall_list_permission_failure_does_not_apply(self):
        self.fail = lambda cmd, args: cmd == 'nft' and 'tables' in args
        with self.assertRaises(control.Error):
            control.firewall_apply(self.c)
        self.assertFalse(self.mutations())

    def test_repeated_routing_reconciliation_no_duplicates_no_flush(self):
        for _ in range(3):
            control.routing_reconcile(self.c)
        self.assertEqual(len(self.rules), 1)
        self.assertEqual(len(self.routes), 2)
        self.assertEqual(len(self.mutations()), 4)
        self.assertNotIn('flush', [v for _, args, _ in self.calls for v in args])
        self.assertIn({'local': '192.0.2.1', 'prefixlen': 32}, self.addresses[0]['addr_info'])

    def test_human_supplied_numeric_routes_are_owned_without_recreation(self):
        self.rules = [{'priority': 10555, 'src': 'all', 'fwmark': '0x15b3',
                       'table': '101', 'protocol': '186'}]
        self.routes = [{'dst': 'default', 'dev': 'xray_tun', 'protocol': '186',
                        'scope': '253', 'metric': 10, 'flags': []},
                       {'type': '7', 'dst': 'default', 'protocol': '186',
                        'metric': 32760, 'flags': []}]
        self.addresses = [{'addr_info': [{'local': '10.255.255.1', 'prefixlen': 24}]}]
        control.routing_reconcile(self.c)
        self.assertFalse(self.mutations())
        with patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(control.status(self.c), 0)
        self.assertEqual(json.loads(output.getvalue())['routing'], 'configured')
        self.assertFalse(self.mutations())
        control.routing_stop(self.c)
        deletions = self.mutations()
        self.assertEqual(len(deletions), 3)
        self.assertIn(('ip', ['-4', 'route', 'del', 'unreachable', 'default',
                             'table', '101', 'proto', '186', 'metric', '32760']), deletions)
        self.assertEqual(self.routes, [])
        self.assertEqual(self.rules, [])

    def test_numeric_route_types_preserve_ownership_refusals(self):
        for numeric in ('1', 1):
            self.routes = [{'type': numeric, 'dst': 'default', 'dev': 'xray_tun',
                            'protocol': '186', 'metric': 10, 'flags': []}]
            self.assertEqual(control.routing_state(self.c)[1][0]['type'], 'unicast')
        good = {'type': '7', 'dst': 'default', 'protocol': '186', 'metric': 32760, 'flags': []}
        for changes in ({'type': '6'}, {'type': '8'}, {'protocol': '3'},
                        {'metric': 10}, {'dev': 'other'}, {'gateway': '192.0.2.1'}):
            with self.subTest(changes=changes):
                self.routes = [dict(good, **changes)]
                with self.assertRaises(control.Error):
                    control.routing_reconcile(self.c)
                self.assertFalse(self.mutations())

    def test_missing_tun_keeps_terminal_route_then_recovers(self):
        self.link = False
        self.assertIn('degraded', control.routing_reconcile(self.c))
        self.assertEqual(len(self.rules), 1)
        self.assertEqual([r['type'] for r in self.routes], ['unreachable'])
        self.link = True
        control.routing_reconcile(self.c)
        self.assertEqual(len(self.routes), 2)

    def test_missing_rule_or_route_is_restored(self):
        control.routing_reconcile(self.c)
        self.rules.clear()
        control.routing_reconcile(self.c)
        self.routes.clear()
        control.routing_reconcile(self.c)
        self.assertEqual(len(self.rules), 1)
        self.assertEqual(len(self.routes), 2)

    def test_routing_never_starts_without_firewall(self):
        self.exists = False
        with self.assertRaises(control.Error):
            control.routing_reconcile(self.c)
        self.assertFalse(self.mutations())

    def test_conflicting_resources_and_duplicate_rules_refused(self):
        for rules, routes in [([dict(self.owned_rule(), protocol=4)], []),
                              ([self.owned_rule(), self.owned_rule()], []),
                              ([], [{'dst': '192.0.2.0/24', 'dev': 'other', 'protocol': 186}]),
                              ([dict(self.owned_rule(), uidrange='0-1000')], [])]:
            with self.subTest(rules=rules, routes=routes):
                self.rules, self.routes = copy.deepcopy(rules), copy.deepcopy(routes)
                with self.assertRaises(control.Error):
                    control.routing_reconcile(self.c)
                self.assertFalse(self.mutations())

    def test_routing_failure_leaves_firewall(self):
        before = self.firewall
        self.fail = lambda cmd, args: cmd == 'ip' and 'rule' in args and 'add' in args
        with self.assertRaises(control.Error):
            control.routing_reconcile(self.c)
        self.assertEqual(before, self.firewall)
        self.assertEqual(self.routes[0]['type'], 'unreachable')

    def test_cleanup_removes_only_owned_routes_and_rule(self):
        control.routing_reconcile(self.c)
        self.calls.clear()
        before = copy.deepcopy(self.addresses)
        control.routing_stop(self.c)
        self.assertEqual(self.rules, [])
        self.assertEqual(self.routes, [])
        self.assertEqual(self.addresses, before)
        self.assertTrue(all(cmd == 'ip' for cmd, _, _ in self.calls))
        control.firewall_ready(self.c)

    def test_address_prefix_conflict_does_not_replace_address(self):
        self.addresses = [{'addr_info': [{'local': '10.255.255.1', 'prefixlen': 32}]}]
        with self.assertRaises(control.Error):
            control.routing_reconcile(self.c)
        self.assertFalse(any('address' in args and 'add' in args for _, args in self.mutations()))

    def test_exec_rechecks_scope_and_rules_before_application(self):
        with patch.object(control.os, 'geteuid', return_value=0), patch.object(control.os, 'execv') as execute:
            self.assertEqual(control.main(['exec', '--', '/usr/bin/setpriv', '--reuid=1000', '--', 'app']), 0)
            execute.assert_called_once()
            execute.reset_mock()
            self.membership.write_text('0::/system.slice/unprotected.scope\n')
            with patch('sys.stderr', new_callable=io.StringIO):
                self.assertEqual(control.main(['exec', '--', '/usr/bin/setpriv', '--', 'app']), 78)
            execute.assert_not_called()
            self.membership.write_text('0::/system.slice/system-netslice.slice/test.scope\n')
            self.exists = False
            with patch('sys.stderr', new_callable=io.StringIO):
                self.assertEqual(control.main(['exec', '--', '/usr/bin/setpriv', '--', 'app']), 78)
            execute.assert_not_called()

    def test_status_is_read_only_and_reports_degraded_routing(self):
        with patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(control.status(self.c), 1)
        report = json.loads(output.getvalue())
        self.assertTrue(report['firewall'].startswith('protected:'))
        self.assertEqual(report['routing'], 'degraded')
        self.assertEqual(report['remote_proxy'], 'unverified')
        self.assertFalse(self.mutations())

    def test_status_requires_complete_routes_and_address_and_not_service_state(self):
        control.routing_reconcile(self.c)
        self.calls.clear()
        with patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(control.status(self.c), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report['tun_address'], 'configured')
        self.assertEqual(report['remote_proxy'], 'unverified')
        self.routes = [r for r in self.routes if 'dev' in r]
        with patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(control.status(self.c), 1)
        self.assertEqual(json.loads(output.getvalue())['routing'], 'degraded')
        self.assertFalse(self.mutations())
