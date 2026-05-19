# Netslice

Seamless, per-application split-tunneling for Linux. Routes specific GUI apps through a TUN interface using cgroups and nftables, while keeping Wayland and D-Bus fully intact via `bubblewrap`.

## The Problem
Traditional network namespaces break Wayland GUI applications by blocking socket access to the display server and D-Bus. Existing cgroup routing solutions often face similar IPC isolation issues.

## The Solution
Netslice uses `systemd-run` to place an application into a dedicated cgroup slice for network isolation. Crucially, it layers `bubblewrap` (bwrap) on top to explicitly bind-mount the host's `/` and pass through necessary Wayland, X11, and D-Bus sockets. `nftables` then marks the cgroup's traffic, and `iproute2` routes it through your proxy's TUN interface.

## Prerequisites
- `systemd`
- `nftables`
- `bubblewrap`
- `iproute2`
- A proxy client that provides a TUN interface (e.g., Xray, Sing-box, Clash, WireGuard)

## Installation

### Arch Linux (AUR)
*(Coming soon)*

### Manual Installation
```bash
git clone https://github.com/occasion-2/netslice.git
cd netslice
sudo make install
```

## Configuration
Edit `/etc/netslice.conf` (or your custom `SYSCONFDIR/netslice.conf`) to match your proxy's TUN interface and gateway IP.

```ini
NETSLICE_TUN_DEV="tun0"
NETSLICE_GATEWAY_IP="10.255.255.1"
```

> [!TIP]
> **Advanced Configuration:** If you change `NETSLICE_SLICE` in the config, you must also update the `Slice=` directive in `netslice-anchor.service` to match. You can do this with:
> `sudo systemctl edit netslice-anchor.service`

## Usage
Start the routing service:
```bash
sudo systemctl enable --now netslice-routing.service
```

Launch an application through the proxy:
```bash
netslice-launch firefox
```
