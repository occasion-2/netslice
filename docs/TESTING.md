# Testing

## Offline checks

```fish
make check
```

The suite tests CLI/argument forwarding, Bubblewrap/session behavior, literal
configuration parsing, readiness, numeric nft/ip output, exact resource ownership,
repeated initialization, partial failures, cleanup, and read-only diagnostics.
Helper commands and application execution are intercepted; unexpected calls fail.
Packaging tests use temporary paths and mock service activation. They check atomic
replacement, preserved configuration, installed links and legacy-unit refusal.
No real network/service mutation is performed by this target.

The human subsequently reported successful IPv4 egress in both launcher modes,
Spotify startup with D-Bus opt-in, enabled services and configured diagnostics.
These establish normal-operation evidence, not failure-injection or DNS privacy.

## Disposable VM fixture

`tests/integration/vm_kernel.py` is excluded from `make check`. It requires root,
a detected disposable VM, explicit opt-in, a current-boot marker, no existing
Netslice slice, and an invoker outside that slice. Containers are refused.
Verify independent console access and absence of valuable workloads first.

Run only inside a fresh Arch VM with the dependencies and repository:

```fish
cat /proc/sys/kernel/random/boot_id | sudo tee /run/netslice-disposable-vm
and sudo python3 -I tests/integration/vm_kernel.py --disposable-vm
```

The fixture verifies a distinct network-namespace inode before ip/nft mutations.
Its own systemd anchor/scopes use the VM's cgroup hierarchy; namespaces alone do
not isolate systemd/cgroups. Cleanup removes only its resources. Two workers keep
UDP sockets open across rule/route/mark loss, firewall replacement and TUN loss.
Postrouting observers check simulated TUN versus physical output, including
IPv6 and direct UDP DNS. Ordinary probes establish that the physical path works.
Dummy devices test route selection, not Xray, remote delivery, TCP or concurrent
reload safety. The fixture has not been executed by the coding agent.

## Integration matrix

Use a separate disposable VM with real Xray and controlled IPv4/IPv6 connectivity
for full lifecycle tests. Install with `make install` and `make enable`. Keep an
external packet collector and independent console. Distinguish protected direct
requests from Xray's legitimate outer transport. Keep existing clients transmitting
through each failure; restore only the exact tested resource and require proxy
connectivity to recover. Do not disable enforcement to restore connectivity.

All destructive operations below are VM-only specifications, not authorized host
commands. Confirm resource ownership before each case. Full failure, boot, DNS,
package and concurrent-load scenarios remain unexecuted.

| # | Case and required assertion | Evidence / next test |
| --- | --- | --- |
| 1 | Protected IPv4 uses TUN; ordinary IPv4 uses normal route | Human curl in both modes passed; collector/TCP/UDP checks pending |
| 2 | Multiple protected scopes; no duplicates | Offline idempotency; two-worker VM fixture pending |
| 3 | Xray unavailable; existing clients have no direct fallback | VM: separately kill, gracefully stop, and restart Xray; collect packets |
| 4 | TUN disappears; no direct egress | VM: delete only test TUN, recreate via Xray; kernel fixture pending |
| 5 | Missing policy route; no direct egress | VM: remove protocol-186 metric-10 default; verify repair and protected interval |
| 6 | Missing policy rule; no direct egress | VM: remove priority-10555 full-mask rule; verify repair and protected interval |
| 7 | Firewall initialization fails; launcher refuses execution | Offline failure checks; VM invalid-template/marker-command test pending |
| 8 | Firewall reload/restart/stop retains guard | VM continuous load through reload/restart/stop; failed transaction retains old rules |
| 9 | Xray/TUN recovers; protected connectivity returns | Mocked device recovery; real Xray lifecycle pending |
| 10 | IPv6-capable host; protected external IPv6 blocked | VM fixture with working ordinary IPv6; no bypass |
| 11 | IPv6 unavailable; no bypass | Human connection failed; capable/unavailable VM cases still required |
| 12 | DNS delegation limits correctly identified | Compare direct UDP/TCP DNS/DoT/DoH with NSS resolve/stub/D-Bus/outside localhost forwarding; identify actual sender |
| 13 | Default Bubblewrap preserves behavior | Offline identity/timezone/bus tests; human curl/Spotify startup passed |
| 14 | Routing-only preserves host integration | Offline tests and human IPv4 curl passed |
| 15 | D-Bus opt-in permits intended access | Offline arguments; human true/Spotify startup; real bus permission checks pending |
| 16 | Wayland/Electron desktop startup works | Environment fixture and reported Spotify startup; broader GUI tests pending |
| 17 | Repeated initialization has no duplicate resources | Offline exact-command/idempotency tests; kernel checks pending |
| 18 | Package upgrade has no unprotected transition | Staging/atomic installation tests; upgrade with transmitting clients pending |
| 19 | Package removal handles existing clients safely | Verify documented exit/retained-tools policy; pending VM test |
| 20 | Agent self-dependency does not disrupt development | Agent scope verified; only offline/repository work by agent; human deployed outside slice |

Additional gates: remove only mark_out rules and verify independent packet tagging
with TCP retransmits, UDP fragments, QUIC and socket-priority changes. Test boot
with Xray present/absent and shutdown ordering. Recreate the anchor/cgroup without
clients and require stale-ID launch refusal; with clients, their scopes must stay.
Privileged deletion of the guard can expose existing clients and is explicitly
outside the security guarantee; verify new-launch refusal without claiming that
existing clients remain protected. Exercise configuration/QoS conflicts separately.

The live development host was not used as a substitute for missing VM isolation.
A qemu executable or network namespace alone does not establish an isolated guest.
