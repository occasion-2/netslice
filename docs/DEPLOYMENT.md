# Installation and maintenance

Commands use fish, `/usr/local`, and the default configuration. Run each stage
separately and stop on errors. Network changes require a local console or an SSH
connection whose cgroup and route are independent of Netslice. The invoking
terminal or agent may itself depend on the proxy. Keep recovery commands offline.

## First installation

Configure Xray to create `xray_tun`; keep Xray outside the protected slice.

```fish
sudo make install
# Edit /etc/netslice.conf if needed.
sudo make enable
sudo make status
```

`install` writes files only. `enable` reloads systemd definitions, enables/starts
anchor, firewall and routing services, reconciles routing, and checks state.
It does not restart an already running service. A missing TUN results in degraded
routing; the launcher still requires an effective firewall.

Use `PREFIX=/usr` and `SYSTEMDDIR=/usr/lib/systemd/system` for packaged layouts.
Pass the same overrides to each make command. Local `/etc/systemd/system` units
take precedence over package units; inspect those overrides before switching.

## Updates

For the refactored architecture with unchanged routing identifiers, make a backup
and install the files:

```fish
sudo tools/netslice-maintenance backup /var/tmp/netslice-backup-(date +%Y%m%d-%H%M%S)
and sudo make install
```

Apply an update explicitly from the independent console. This can briefly
interrupt protected connections:

```fish
sudo systemctl daemon-reload
and sudo systemctl reload netslice-firewall.service
and sudo /usr/local/bin/netslice-control ready
and sudo systemctl restart netslice-routing.service
and sudo make status
```

Firewall replacement is atomic and routing cleanup retains it. The anchor is
kept running to preserve cgroup identity. Do not change the mark, table, TUN or
other ownership identifiers as an ordinary update. Package installation has no
activation hook; inspect distribution-wide hooks separately.

Check IPv4 with normal curl and both launcher modes. Test your desktop applications
and session D-Bus access. External IPv6 should fail; a host without usable IPv6
cannot demonstrate the IPv6-capable case. Successful curl does not prove DNS
privacy. Boot/shutdown and destructive failure scenarios need the isolated tests
in [TESTING.md](TESTING.md), not an unsupervised live reboot or failure injection.

## Recovery

Inspect before changing anything:

```fish
sudo /usr/local/bin/netslice-control status
sudo journalctl -u netslice-routing.service -u netslice-firewall.service -n 100 --no-pager -l
sudo ip -4 -j -N rule show
sudo ip -4 -j -N route show table 101
sudo nft -s -n -y list table inet netslice_guard
```

With valid protection and no conflicting resources, reconcile missing routing:

```fish
sudo /usr/local/bin/netslice-control ready
and sudo /usr/local/bin/netslice-control routing-once
and sudo systemctl start netslice-routing.service
and sudo make status
```

To restore a previous refactored version, retain the guard, restore the backed-up
files/configuration and apply the update sequence above. Review routing ownership
and any changed firewall schema first. Do not replay a whole saved host ruleset.

For temporary recovery to the old default IPv4 routing, stop the new supervisor:

```fish
sudo tools/netslice-maintenance rollback-routing /usr/local --approved-live --independent-recovery
```

After it succeeds, inspect table 101 and the policy rules. Run each addition below
only if its corresponding entry is absent and matches the backup:

```fish
read --prompt-str 'Backed-up IPv4 rule priority: ' netslice_priority4
sudo ip -4 route add default dev xray_tun table 101 proto boot
sudo ip -4 rule add priority "$netslice_priority4" fwmark 5555/0xffffffff lookup 101
sudo /usr/local/bin/netslice-control ready
```

Keep the new guard and launcher. This is temporary recovery; the new supervisor
refuses legacy ownership. Do not reboot into this mixed configuration. A full
return to the old implementation requires all protected clients to exit first,
including agents, and a review of its known cleanup defects.

## Removal

Stop new launches and exit all protected applications before removal. Check the
slice's descendants, not only its own `cgroup.procs`. Retain helper, configuration,
units and recovery files until the scopes are empty. Package removal leaves kernel
rules but removes management files; retained rules do not survive reboot.

`make uninstall` accepts only an absolute staging `DESTDIR`. Live removal requires
review of running scopes, boot enablement and specifically owned resources. Never
flush unrelated tables, stop the whole slice, or remove the guard while clients run.

## Old combined service

This is a one-time migration for installations whose routing unit also manages
nftables or flushes addresses/tables. Already-refactored installations skip it.

1. From an independent console, inspect configuration, Xray TUN ownership,
   active scopes, units/drop-ins, nftables rules and tc filters. Confirm that
   `/etc/nftables.conf` has no global `flush ruleset`. Back up before changing files:

   ```fish
   sudo tools/netslice-maintenance preflight
   sudo tools/netslice-maintenance backup /var/tmp/netslice-backup-(date +%Y%m%d-%H%M%S)
   make DESTDIR=/tmp/netslice-stage install
   ```

2. Install replacement protection alongside `inet netslice_cgroup`:

   ```fish
   sudo tools/netslice-maintenance firewall /tmp/netslice-stage /usr/local --approved-live --independent-recovery
   and sudo /usr/local/bin/netslice-control ready
   ```

3. Replace routing definitions and disable old cleanup before stopping the old unit:

   ```fish
   sudo tools/netslice-maintenance routing /tmp/netslice-stage /usr/local --approved-live --independent-recovery
   ```

   If this fails, inspect effective units and the temporary runtime override
   `90-netslice-migration.conf` before retrying. Do not stop the old unit directly.

4. Inspect exact rules and routes. Commands below apply only to one default per
   family through `xray_tun`, protocol `boot`, IPv6 metric 1024, mark 5555/table 101.
   Record the actual rule priorities; they are not fixed across installations:

   ```fish
   sudo ip -4 rule show
   sudo ip -6 rule show
   sudo ip -4 -j -N route show table 101
   sudo ip -6 -j -N route show table 101
   sudo ip -4 -j -N route show table 101 proto boot
   sudo ip -6 -j -N route show table 101 proto boot
   read --prompt-str 'Current Netslice IPv4 rule priority: ' netslice_priority4
   read --prompt-str 'Current Netslice IPv6 rule priority: ' netslice_priority6
   ```

   After confirming each exact entry, replace routing. Connectivity may pause:

   ```fish
   sudo ip -4 rule del priority "$netslice_priority4" fwmark 5555/0xffffffff lookup 101
   and sudo ip -6 rule del priority "$netslice_priority6" fwmark 5555/0xffffffff lookup 101
   and sudo ip -4 route del default dev xray_tun table 101 proto boot
   and sudo ip -6 route del default dev xray_tun table 101 proto boot metric 1024
   and sudo /usr/local/bin/netslice-control routing-once
   and sudo systemctl start netslice-routing.service
   and sudo /usr/local/bin/netslice-control status
   ```

   A failed command may leave a partly completed migration. Inspect before retrying;
   do not repeat deletions blindly or broaden them into a flush.

5. Install the launcher, test connectivity and then enable startup:

   ```fish
   sudo tools/netslice-maintenance launcher /tmp/netslice-stage /usr/local --approved-live --independent-recovery
   # Test normal/protected connectivity before the next command.
   sudo make enable
   ```

Keep the old `netslice_cgroup` table during initial verification. Removing it is
a separate reviewed cleanup after replacement protection is confirmed. No Xray
restart, legacy Xray routing restoration, or automatic security-disabling rollback
is part of this procedure.
