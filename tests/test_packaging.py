"""Inspect and exercise file-only installation in a disposable staging directory."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_staging_manifest_and_configuration_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            (stage / 'etc').mkdir()
            original = 'NETSLICE_GATEWAY_IP="10.255.255.2"\n'
            (stage / 'etc/netslice.conf').write_text(original)
            result = subprocess.run(['/usr/bin/make', 'install', 'DESTDIR=' + directory,
                'PREFIX=/usr', 'SYSCONFDIR=/etc', 'SYSTEMDDIR=/usr/lib/systemd/system'],
                cwd=ROOT, capture_output=True, text=True, timeout=20,
                env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((stage / 'etc/netslice.conf').read_text(), original)
            for name in ['usr/bin/netslice-control', 'usr/bin/netslice-launch',
                         'etc/netslice.conf.example', 'etc/nftables/netslice.nft',
                         'usr/share/doc/netslice/netslice-maintenance',
                         'usr/share/doc/netslice/docs/DEPLOYMENT.md',
                         'usr/lib/systemd/system/netslice-anchor.service',
                         'usr/lib/systemd/system/netslice-firewall.service',
                         'usr/lib/systemd/system/netslice-routing.service']:
                self.assertTrue((stage / name).is_file(), name)
                if name.endswith('.service') or '/bin/' in name:
                    self.assertNotIn('@@', (stage / name).read_text())
            self.assertTrue(os.access(stage / 'usr/bin/netslice-control', os.X_OK))
            self.assertIn('ExecStart=/usr/bin/netslice-control',
                          (stage / 'usr/lib/systemd/system/netslice-firewall.service').read_text())
            docs = stage / 'usr/share/doc/netslice'
            self.assertFalse((docs / 'docs/development').exists())
            for reference in re.findall(r'\]\(([^)]+)\)', (docs / 'README.md').read_text()):
                self.assertTrue((docs / reference.split('#')[0]).is_file(), reference)

    def test_default_install_replaces_files_atomically_and_preserves_config(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            command = ['/usr/bin/make', 'install', 'DESTDIR=' + directory]
            options = {'cwd': ROOT, 'capture_output': True, 'text': True, 'timeout': 20,
                       'env': {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}}
            first = subprocess.run(command, **options)
            self.assertEqual(first.returncode, 0, first.stderr)
            config = stage / 'etc/netslice.conf'
            config.write_text('NETSLICE_TUN_DEV="custom_tun"\n')
            helper = stage / 'usr/local/bin/netslice-control'
            with helper.open('rb') as old_file:
                old_bytes = old_file.read()
                old_inode = os.fstat(old_file.fileno()).st_ino
                second = subprocess.run(command, **options)
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertNotEqual(helper.stat().st_ino, old_inode)
                old_file.seek(0)
                self.assertEqual(old_file.read(), old_bytes)
            self.assertEqual(config.read_text(), 'NETSLICE_TUN_DEV="custom_tun"\n')
            self.assertEqual(helper.read_bytes(), old_bytes)
            self.assertFalse(list(stage.rglob('*.new.*')))
            self.assertIn('ExecStart=/usr/local/bin/netslice-control',
                          (stage / 'etc/systemd/system/netslice-routing.service').read_text())

    def test_live_install_refuses_legacy_unit_before_writing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            units = root / 'units'
            units.mkdir()
            legacy = units / 'netslice-routing.service'
            original = '[Service]\nExecStop=/usr/bin/ip route flush table 101\n'
            legacy.write_text(original)
            result = subprocess.run(['/usr/bin/make', 'install', 'PREFIX=' + str(root / 'usr'),
                'SYSCONFDIR=' + str(root / 'etc'), 'SYSTEMDDIR=' + str(units)],
                cwd=ROOT, capture_output=True, text=True, timeout=20,
                env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Legacy routing unit', result.stderr)
            self.assertEqual(legacy.read_text(), original)
            self.assertFalse((root / 'usr').exists())

    def test_staged_enable_is_refused_before_host_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(['/usr/bin/make', 'enable', 'DESTDIR=' + directory],
                cwd=ROOT, capture_output=True, text=True, timeout=10,
                env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('without DESTDIR', result.stderr)

    def test_explicit_enable_uses_mocked_services_and_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commands = root / 'commands'
            prefix = root / 'prefix'
            units = root / 'units'
            commands.mkdir()
            (prefix / 'bin').mkdir(parents=True)
            units.mkdir()
            (units / 'netslice-routing.service').write_text(
                '[Service]\nExecStart=' + str(prefix / 'bin/netslice-control') + ' routing-watch\n')
            log = root / 'calls'
            for path, body in [(commands / 'id', '#!/bin/sh\n[ "$1" = -u ] || exit 99\necho 0\n'),
                               (commands / 'systemctl', '#!/bin/sh\nprintf "systemctl %s\\n" "$*" >> "$TEST_LOG"\n'),
                               (prefix / 'bin/netslice-control', '#!/bin/sh\nprintf "control %s\\n" "$*" >> "$TEST_LOG"\n')]:
                path.write_text(body)
                path.chmod(0o755)
            # Unit recognition is tested separately; do not inspect host overrides here.
            result = subprocess.run(['/usr/bin/make', 'enable', 'PREFIX=' + str(prefix),
                                     'SYSTEMDDIR=' + str(units), 'CHECK_LEGACY=:'],
                cwd=ROOT, capture_output=True, text=True, timeout=10,
                env={'PATH': str(commands) + ':/usr/bin:/bin', 'LC_ALL': 'C', 'TEST_LOG': str(log)})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(log.read_text().splitlines(), [
                'systemctl daemon-reload',
                'systemctl enable --now netslice-anchor.service netslice-firewall.service netslice-routing.service',
                'control ready', 'control routing-once', 'control status'])

    def test_service_ownership_and_packaging_have_no_activation_hooks(self):
        firewall = (ROOT / 'systemd/netslice-firewall.service').read_text()
        routing = (ROOT / 'systemd/netslice-routing.service').read_text()
        self.assertNotIn('\nExecStop=', firewall)
        self.assertNotIn('xray.service', firewall)
        for text in [firewall, routing]:
            self.assertNotIn('BindsTo=', text)
            self.assertNotIn('PartOf=', text)
            self.assertNotIn('flush ', text)
        pkgbuild = (ROOT / 'PKGBUILD').read_text()
        self.assertNotIn('install=', pkgbuild)
        self.assertNotIn('systemctl', pkgbuild)
        self.assertNotIn('git+file:', pkgbuild)
        self.assertIn("'python'", pkgbuild)
        self.assertIn("'sudo'", pkgbuild)
        self.assertIn("'openssl'", pkgbuild)
