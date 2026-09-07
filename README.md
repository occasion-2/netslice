# Netslice

Seamless, hardened per-application split-tunneling for Linux. Netslice routes specific GUI applications through a TUN interface using cgroups and nftables, while utilizing bubblewrap to completely quarantine the application from host telemetry, hardware fingerprints, and state leaks.

## The Problem
Traditional network namespaces break Wayland GUI applications by blocking socket access to the display server. While standard cgroup routing fixes the GUI issue, it leaves massive security and privacy gaps: advanced AI tools, compiled Electron binaries, and aggressive tracking systems bypass basic routing by utilizing IPv6 fallbacks, UDP QUIC blasts, or querying real-world hardware states directly via D-Bus and system locale files.

## The Solution
Netslice creates a mathematically proven quarantine cell using a two-pronged approach:

1. The Telemetry Gag (bwrap): Netslice launches the application using systemd-run and layers bubblewrap on top. It explicitly bind-mounts Wayland/X11 sockets so the GUI renders perfectly, but violently severs the IPC/D-Bus namespace, nullifies /etc/machine-id, and spoofs the system timezone. The application boots into a completely sterile, untainted state.

2. The Network Kill-Switch (nftables): Traffic from the isolated cgroup is marked and routed directly into your proxy's TUN interface. A strict nftables filter acts as a kill-switch: if the application attempts to bypass the TUN using an unhandled protocol (like IPv6 or raw UDP), the packet is instantly dropped before it can reach your physical network adapter.

## Prerequisites
- systemd
- util-linux (`/usr/bin/setpriv`)
- nftables
- bubblewrap
- iproute2
- A proxy client that provides a TUN interface and FakeDNS capabilities (e.g., Xray, Sing-box).

## Installation

### Arch Linux (AUR)
*(Coming soon)*

### Manual Installation

git clone https://github.com/occasion-2/netslice.git
cd netslice
sudo make install

## Configuration
Edit /etc/netslice.conf (or your custom SYSCONFDIR/netslice.conf) to match your proxy's TUN interface, routing mark, and gateway IP.

NETSLICE_TUN_DEV="xray_tun"
NETSLICE_GATEWAY_IP="10.255.255.1"
NETSLICE_FWMARK="0x100"
NETSLICE_TABLE="100"

Advanced Configuration: If you change NETSLICE_SLICE in the config, you must also update the Slice= directive in netslice-anchor.service to match. You can do this with:
sudo systemctl edit netslice-anchor.service

## Usage
Start the routing and quarantine service:

sudo systemctl enable --now netslice-routing.service

Launch any application straight into the quarantine cell:

netslice-launch antigravity-ide
# or
netslice-launch firefox

Host user session D-Bus access is blocked by default. Applications that require
it, such as Spotify, can be granted access explicitly:

netslice-launch --allow_dbus spotify-launcher

`--allow_dbus` exposes the user session-bus socket and its address to the
application, reducing isolation for that application only.


### Routing-only mode

For applications that need host access or administrator commands, explicitly opt
out of Bubblewrap while retaining the configured cgroup routing:

```bash
netslice-launch --routing-only codex-desktop
# Codex CLI (these permission flags belong to the CLI):
netslice-launch --routing-only codex --sandbox workspace-write --ask-for-approval on-request
```

This mode uses the same systemd slice, invoking user/group, and existing
nftables/TUN rules. Both modes initialize the invoking user's supplementary
groups with `setpriv --init-groups` before starting the application. This keeps
account memberships such as `wheel`, `video`, and `render` and avoids inheriting
sudo's root group. Group membership is loaded from the account database, so
recent account changes may differ from an older login session.

Routing-only mode does not hide the host session D-Bus socket, replace the
machine ID, or spoof the timezone, and does not require Bubblewrap or create a
fake machine ID. `--allow_dbus` is redundant when combined with `--routing-only`.
Put Netslice options before the application name; arguments after it are passed
unchanged to the application.

The application still runs as your normal user. Routing-only mode does not grant
root access or clear restrictions inherited from its parent. Launch it from a
normal host terminal. `sudo` still requires your normal authorization, and an
application's own sandbox or approval policy can still prevent escalation.
Commands delegated to services outside the Netslice cgroup are not covered by
its routing rules. The default Bubblewrap mode is unchanged.

After updating an existing installation, install only the launcher to preserve
your current routing configuration (default `/usr/local` installation):

```bash
netslice_tmp=$(mktemp)
sed 's|@@SYSCONFDIR@@|/etc|g' bin/netslice-launch > "$netslice_tmp"
sudo install -m755 "$netslice_tmp" /usr/local/bin/netslice-launch
rm "$netslice_tmp"
```

Fully quit an existing application instance before relaunching in the new mode.
To inspect the outer launch environment independently of an application sandbox:

```bash
netslice-launch --routing-only sh -c 'grep NoNewPrivs /proc/self/status; id; cat /proc/self/cgroup'
```

From an unrestricted host shell, expect `NoNewPrivs: 0`, your normal user ID,
and membership in the configured Netslice slice. An application may add its own
restrictions later.

### Launcher tests

Run `python3 -m unittest discover -s tests -v`. These tests capture the launcher
arguments using a fake `sudo`; they require no root access or running services.
