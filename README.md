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
