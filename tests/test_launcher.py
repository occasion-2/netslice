import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        source = Path(__file__).resolve().parents[1] / 'bin/netslice-launch'
        script = source.read_text().replace('@@PREFIX@@', str(self.root))
        # Isolate identity files without changing the calling user's HOME.
        script = script.replace('$HOME/.config/netslice', str(self.root / 'identity'))
        self.launcher = self.root / 'launcher'
        self.launcher.write_text(script)
        (self.root / 'netslice.conf').write_text('NETSLICE_SLICE=system-netslice.slice\nNETSLICE_TZ=UTC\n')
        self.capture = self.root / 'args.json'
        fake = self.root / 'sudo'
        fake.write_text(f'''#!{sys.executable}
import json, os, sys
if sys.argv[-1] == 'ready':
    sys.exit(int(os.environ.get('TEST_READY_FAIL', '0')))
assert sys.argv[1] == '/usr/bin/systemd-run', sys.argv
with open(os.environ["TEST_CAPTURE"], "w") as f: json.dump(sys.argv[1:], f)
''')
        helper = self.root / 'bin/netslice-control'
        helper.parent.mkdir()
        helper.write_text((source.parent / 'netslice-control').read_text().replace('@@SYSCONFDIR@@', str(self.root)))
        helper.chmod(0o755)
        fake.chmod(0o755)
        self.env = dict(os.environ, PATH=f'{self.root}:/usr/bin:/bin',
                        TEST_CAPTURE=str(self.capture), TZ='Asia/Yekaterinburg',
                        DBUS_SESSION_BUS_ADDRESS='unix:path=/test/bus')

    def run_launcher(self, *args, code=0):
        result = subprocess.run(['/bin/bash', str(self.launcher), *args],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stderr)
        return json.loads(self.capture.read_text()) if self.capture.exists() else result.stdout

    def test_routing_only_preserves_command_and_scope(self):
        args = self.run_launcher('--routing-only', 'app with spaces', 'a b', '', '--allow_dbus', '$(literal)')
        self.assertEqual(args[0], '/usr/bin/systemd-run')
        for arg in ['--slice=system-netslice.slice', '--scope', f'--reuid={os.getuid()}', f'--regid={os.getgid()}']:
            self.assertIn(arg, args)
        self.assertEqual(args[args.index('/usr/bin/setpriv')+7:], ['app with spaces', 'a b', '', '--allow_dbus', '$(literal)'])
        self.assertNotIn('bwrap', args)
        self.assertIn('--setenv=DBUS_SESSION_BUS_ADDRESS=unix:path=/test/bus', args)
        self.assertIn('--setenv=TZ=Asia/Yekaterinburg', args)
        self.assertFalse((self.root / 'identity').exists())

    def test_default_retains_isolation(self):
        args = self.run_launcher('app', 'a b')
        self.assertIn('bwrap', args)
        self.assertIn('--setenv=TZ=UTC', args)
        self.assertIn('--unsetenv', args)
        self.assertIn('/dev/null', args)
        self.assertIn('/etc/machine-id', args)
        self.assertEqual(args[-3:], ['--', 'app', 'a b'])
        identity = self.root / 'identity/fake-machine-id'
        self.assertEqual(len(identity.read_text().strip()), 32)
        self.assertEqual(identity.stat().st_mode & 0o777, 0o600)
        before = identity.read_text()
        self.run_launcher('app')
        self.assertEqual(identity.read_text(), before)

    def test_dbus_opt_in(self):
        args = self.run_launcher('--allow_dbus', 'app')
        self.assertIn('bwrap', args)
        self.assertNotIn('/dev/null', args)
        self.assertIn(f'unix:path=/run/user/{os.getuid()}/bus', args)

    def test_combined_options_and_separator(self):
        args = self.run_launcher('--allow_dbus', '--routing-only', '--', 'app')
        self.assertNotIn('bwrap', args)
        self.assertEqual(args[-2:], ['--', 'app'])

    def test_routing_without_optional_environment_or_timezone_file(self):
        self.env.pop('TZ')
        self.env.pop('DBUS_SESSION_BUS_ADDRESS')
        (self.root / 'netslice.conf').write_text('NETSLICE_TZ=not/a/real/timezone\n')
        args = self.run_launcher('--routing-only', 'app')
        self.assertFalse(any(a.startswith('--setenv=TZ=') for a in args))
        self.assertFalse(any(a.startswith('--setenv=DBUS_SESSION_BUS_ADDRESS=') for a in args))
        self.assertFalse((self.root / 'identity').exists())

    def test_missing_command(self):
        self.run_launcher('--routing-only', code=2)
        self.assertFalse(self.capture.exists())

    def test_unknown_option(self):
        self.run_launcher('--unknown', code=2)
        self.assertFalse(self.capture.exists())

    def test_help(self):
        self.assertIn('--routing-only', self.run_launcher('--help'))
        self.assertFalse(self.capture.exists())

    def test_credentials_initialized_before_application_in_both_modes(self):
        for mode in [[], ['--routing-only']]:
            with self.subTest(mode=mode):
                args = self.run_launcher(*mode, 'app')
                boundary = args.index('/usr/bin/setpriv') - 1
                self.assertFalse(any(a.startswith(('--uid=', '--gid=')) for a in args[:boundary]))
                self.assertEqual(args[boundary+1:boundary+8], [
                    '/usr/bin/setpriv', f'--reuid={os.getuid()}',
                    f'--regid={os.getgid()}', '--init-groups',
                    '--inh-caps=-all', '--ambient-caps=-all', '--'])
                self.assertEqual(args[boundary+8], 'app' if mode else 'bwrap')

    def test_firewall_failure_prevents_scope_and_identity_creation(self):
        self.env['TEST_READY_FAIL'] = '78'
        self.run_launcher('app', code=78)
        self.assertFalse(self.capture.exists())
        self.assertFalse((self.root / 'identity').exists())

    def test_configuration_failure_prevents_sudo(self):
        (self.root / 'netslice.conf').unlink()
        self.run_launcher('--routing-only', 'app', code=78)
        self.assertFalse(self.capture.exists())

    def test_guard_executes_inside_scope_before_setpriv(self):
        args = self.run_launcher('--routing-only', 'app')
        boundary = args.index('--')
        self.assertEqual(args[boundary+1:boundary+4], [str(self.root / 'bin/netslice-control'), 'exec', '--'])
        self.assertEqual(args[boundary+4], '/usr/bin/setpriv')

    def test_desktop_environment_forwarded(self):
        self.env.update(WAYLAND_DISPLAY='wayland-1', XDG_RUNTIME_DIR='/run/user/test',
                        DISPLAY=':1', SSH_AUTH_SOCK='/tmp/test-ssh-agent')
        args = self.run_launcher('app')
        for item in ['--setenv=WAYLAND_DISPLAY=wayland-1', '--setenv=XDG_RUNTIME_DIR=/run/user/test',
                     '--setenv=DISPLAY=:1', '--setenv=SSH_AUTH_SOCK=/tmp/test-ssh-agent',
                     '--setenv=ELECTRON_OZONE_PLATFORM_HINT=auto']:
            self.assertIn(item, args)
