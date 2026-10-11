# Netslice

Run selected Linux applications through an Xray TUN interface. Other applications
keep their normal routing. Protected external IPv6 is blocked; IPv4 uses the TUN.

## Install

Requirements: systemd with cgroup v2, nftables, iproute2, Bash, Python 3,
util-linux, sudo, OpenSSL, and Bubblewrap. Install and configure Xray separately
so its service creates the TUN device outside the Netslice slice.

```fish
sudo make install
```

Edit `/etc/netslice.conf` if your TUN differs from the defaults, then start Netslice:

```fish
sudo make enable
```

`install` copies files atomically, preserves existing configuration, and writes
`/etc/netslice.conf.example`. `enable` explicitly starts/enables the three Netslice
services and checks firewall/routing state. Both use `/usr/local` by default.

Already using the old combined routing/firewall service? Follow the
[one-time migration](docs/DEPLOYMENT.md#old-combined-service) first; the installer
refuses to overwrite a detected legacy routing unit. Refactored installations
can use `make install` directly. See [updates and recovery](docs/DEPLOYMENT.md).

## Use

```fish
netslice-launch [--routing-only] [--allow_dbus] [--] COMMAND [ARGS...]

netslice-launch firefox
netslice-launch --allow_dbus spotify-launcher
netslice-launch --routing-only -- curl -4 --noproxy '*' https://api.ipify.org
```

Default mode uses Bubblewrap, a persistent fake machine ID, a fake timezone,
and restricted session D-Bus access. It forwards desktop/session variables for
Wayland, X11 and Electron. `--allow_dbus` permits session D-Bus access;
`--routing-only` keeps ordinary host integration without Bubblewrap.
Fully quit an application before relaunching: an existing instance outside
Netslice may receive the new instance's request through IPC.

## Configuration

`/etc/netslice.conf` accepts literal `NAME=value` assignments, not shell code.
Default settings:

| Setting | Default |
| --- | --- |
| TUN | `xray_tun` |
| Slice | `system-netslice.slice` (fixed) |
| Firewall mark | `5555` / `0x15b3` |
| IPv4 routing table / rule priority | `101` / `10555` |
| TUN address | `10.255.255.1/24` |
| Reconciliation interval | 2 seconds |

Netslice reserves routing protocol `186` and packet priority `0x4e530001`
(`4e53:1`). Keep these resources separate from other routing and traffic shaping.
Changing routing identifiers on a running installation needs a reviewed migration.

## Status and checks

```fish
sudo make status
# Outside the repository:
sudo /usr/local/bin/netslice-control status

curl -4 --noproxy '*' --max-time 15 https://api.ipify.org
netslice-launch --routing-only -- curl -4 --noproxy '*' --max-time 15 https://api.ipify.org
```

Status is read-only and checks actual firewall rules, policy routing and TUN state.
An active service alone does not establish protection or remote proxy health.

The firewall remains installed when routing or Xray stops. Launches are rejected
when expected firewall rules cannot be verified. This protects ordinary sockets
created inside the slice; privileged firewall removal, outside-process DNS/local
forwarding, and inherited sockets are limitations. Bubblewrap is not complete
filesystem or telemetry isolation. See the [security model](docs/SECURITY.md).

## Development and packaging

```fish
make check
make DESTDIR=/tmp/netslice-stage install
```

`check` runs offline tests. `DESTDIR` installation only stages files. Arch packaging
uses `/usr` and `/usr/lib/systemd/system` and has no service activation hook.

[Testing](docs/TESTING.md)
