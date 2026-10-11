#!/usr/bin/python3 -I
"""DESTRUCTIVE VM ONLY: real socket/cgroup/nft tests in a disposable network namespace.
Not discovered by the offline unittest runner. See docs/TESTING.md.
"""
import argparse
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import select
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
NS = 'netslice-test-' + str(os.getpid())
ANCHOR = 'netslice-test-anchor-' + str(os.getpid())
CGROUP = Path('/sys/fs/cgroup/system.slice/system-netslice.slice')


def command(*args, input=None, check=True):
    return subprocess.run(list(args), input=input, capture_output=True, text=True,
                          check=check, timeout=20, env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})


def namespace(*args, **kwargs):
    return command('/usr/bin/ip', 'netns', 'exec', NS, *args, **kwargs)


def ip(*args):
    return namespace('/usr/bin/ip', *args)


def gate(approved):
    if not approved or os.geteuid() != 0:
        raise RuntimeError('Requires root and --disposable-vm; never run on the development host')
    if command('/usr/bin/systemd-detect-virt', '--vm', check=False).returncode:
        raise RuntimeError('An identifiable VM is required; containers are insufficient')
    if not command('/usr/bin/systemd-detect-virt', '--container', check=False).returncode:
        raise RuntimeError('Refusing a container, even inside a VM')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if Path('/run/netslice-disposable-vm').read_text().strip() != boot:
        raise RuntimeError('Missing current-boot disposable-VM marker')
    if 'system-netslice.slice' in Path('/proc/self/cgroup').read_text() or CGROUP.exists():
        raise RuntimeError('Existing protected slice or protected invoking client; use a fresh VM')


WORKER = '''import socket,sys
sockets = {4: socket.socket(socket.AF_INET, socket.SOCK_DGRAM), 6: socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)}
print('READY', flush=True)
for line in sys.stdin:
 family, port = map(int, line.split())
 try:
  sockets[family].sendto(b'netslice-integration', ('203.0.113.10' if family == 4 else '2001:db8::10', port))
 except OSError:
  pass
 print('SENT', flush=True)
'''


def worker():
    return subprocess.Popen(['/usr/bin/systemd-run', '--quiet', '--scope', '--slice=system-netslice.slice',
        '/usr/bin/ip', 'netns', 'exec', NS, '/usr/bin/setpriv', '--reuid=65534', '--regid=65534',
        '--clear-groups', '--inh-caps=-all', '--ambient-caps=-all', '--', '/usr/bin/python3', '-I', '-c', WORKER],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def response(proc, expected):
    if not select.select([proc.stdout], [], [], 10)[0]:
        raise RuntimeError('Protected scope timed out')
    actual = proc.stdout.readline().strip()
    if actual != expected:
        raise RuntimeError('Scope response: ' + actual)


def counters():
    data = json.loads(namespace('/usr/bin/nft', '-j', 'list', 'table', 'inet', 'test_observer').stdout)
    result = {}
    for item in data['nftables']:
        rule = item.get('rule', {})
        if 'comment' in rule:
            result[rule['comment']] = next(expr['counter']['packets'] for expr in rule['expr'] if 'counter' in expr)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable-vm', action='store_true')
    args = parser.parse_args()
    gate(args.disposable_vm)  # No mutations occur before this completes.
    workers = []
    created = False
    anchor = False
    try:
        command('/usr/bin/ip', 'netns', 'add', NS)
        created = True
        host_namespace = Path('/proc/self/ns/net').stat().st_ino
        isolated = int(namespace('/usr/bin/python3', '-I', '-c',
            'import os; print(os.stat("/proc/self/ns/net").st_ino)').stdout)
        if isolated == host_namespace:
            raise RuntimeError('Network namespace isolation was not established')
        command('/usr/bin/systemd-run', '--quiet', '--unit=' + ANCHOR,
                '--slice=system-netslice.slice', '/usr/bin/sleep', 'infinity')
        anchor = True
        deadline = time.monotonic() + 10
        while not CGROUP.exists():
            if time.monotonic() > deadline:
                raise RuntimeError('cgroup creation timed out')
            time.sleep(0.1)
        ip('link', 'set', 'lo', 'up')
        ip('link', 'add', 'phys', 'type', 'dummy')
        ip('link', 'set', 'phys', 'up')
        ip('-4', 'addr', 'add', '192.0.2.1/24', 'dev', 'phys')
        ip('-6', 'addr', 'add', '2001:db8:1::1/64', 'dev', 'phys', 'nodad')
        ip('-4', 'route', 'add', 'default', 'dev', 'phys')
        ip('-6', 'route', 'add', 'default', 'dev', 'phys')
        ip('link', 'add', 'xray_tun', 'type', 'dummy')
        ip('-6', 'addr', 'add', '2001:db8:2::1/64', 'dev', 'xray_tun', 'nodad')
        namespace('/usr/bin/nft', '-f', '-', input='''table inet test_observer {
 chain out {
  type filter hook postrouting priority 100; policy accept;
  meta nfproto ipv4 oifname "phys" meta l4proto udp counter comment "physical4"
  meta nfproto ipv6 oifname "phys" meta l4proto udp counter comment "physical6"
  meta nfproto ipv4 oifname "xray_tun" meta l4proto udp counter comment "tun4"
 }
}''')
        loader = importlib.machinery.SourceFileLoader('control', str(ROOT / 'bin/netslice-control'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        control = importlib.util.module_from_spec(spec)
        loader.exec_module(control)
        control.TEMPLATE = ROOT / 'nftables/netslice.nft'
        # All helper network commands are executed through the verified namespace.
        def isolated_run(tool, *values, input=None, optional=False):
            return namespace(control.COMMANDS[tool], *map(str, values), input=input, check=not optional)
        control.run = isolated_run
        c = control.DEFAULTS.copy()
        control.firewall_apply(c)
        control.routing_reconcile(c)
        control.routing_reconcile(c)
        control.firewall_apply(c)
        control.firewall_ready(c)  # Exercises actual dump canonicalization.
        for _ in range(2):
            proc = worker()
            workers.append(proc)
            response(proc, 'READY')

        def probe(label, family=4, expected='tun4', port=40555):
            before = counters()
            for proc in workers:
                proc.stdin.write(f'{family} {port}\n')
                proc.stdin.flush()
                response(proc, 'SENT')
            after = counters()
            changed = {k: after[k] - before[k] for k in after}
            if expected:
                assert changed[expected] == len(workers), (label, changed)
            else:
                assert all(value == 0 for value in changed.values()), (label, changed)
            assert changed['physical4'] == 0 and changed['physical6'] == 0, (label, changed)
            print('PASS:', label, flush=True)

        # Demonstrate that an ordinary process reaches the physical output hook.
        before = counters()
        namespace('/usr/bin/python3', '-I', '-c', 'import socket; socket.socket(socket.AF_INET,socket.SOCK_DGRAM).sendto(b"ordinary", ("203.0.113.10",40555))')
        assert counters()['physical4'] > before['physical4']
        before = counters()
        namespace('/usr/bin/python3', '-I', '-c', 'import socket; socket.socket(socket.AF_INET6,socket.SOCK_DGRAM).sendto(b"ordinary", ("2001:db8::10",40555))')
        assert counters()['physical6'] > before['physical6']
        probe('multiple protected IPv4 sockets')
        probe('direct UDP DNS stays on TUN', port=53)
        probe('IPv6 blocked despite IPv6 physical and TUN addresses', family=6, expected=None)
        ip('-4', 'route', 'del', 'default', 'dev', 'xray_tun', 'table', '101', 'proto', '186', 'metric', '10')
        probe('missing TUN policy route, existing sockets', expected=None)
        control.routing_reconcile(c)
        ip('-4', 'rule', 'del', *control.rule_args(c))
        probe('missing policy rule, existing sockets', expected=None)
        probe('direct DNS blocked with missing rule', expected=None, port=53)
        control.routing_reconcile(c)
        namespace('/usr/bin/nft', 'flush', 'chain', 'inet', 'netslice_guard', 'mark_out')
        probe('missing marking rules, independent priority guard', expected=None)
        control.firewall_apply(c)
        for _ in range(3):
            control.firewall_apply(c)
            probe('atomic firewall reload retains normal routing')
        ip('link', 'delete', 'xray_tun')
        control.routing_reconcile(c)
        probe('TUN disappearance, existing sockets', expected=None)
        ip('link', 'add', 'xray_tun', 'type', 'dummy')
        control.routing_reconcile(c)
        probe('TUN recreation restores route')
        ip('-6', 'route', 'del', 'default', 'dev', 'phys')
        probe('IPv6 unavailable', family=6, expected=None)
        control.routing_stop(c)
        control.firewall_ready(c)
        probe('routing cleanup retains firewall protection', expected=None)
        print('Kernel fixture passed. Dummy devices do not validate real Xray, TCP, DNS delegation, or systemd lifecycle.')
    finally:
        # Terminate only workers created here; never stop the slice.
        for proc in workers:
            if proc.stdin:
                proc.stdin.close()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.terminate()
                proc.wait(timeout=5)
        if anchor:
            command('/usr/bin/systemctl', 'stop', ANCHOR + '.service', check=False)
        if created:
            command('/usr/bin/ip', 'netns', 'delete', NS, check=False)


if __name__ == '__main__':
    main()
