# Security model and lifecycle

## Supported boundary

Netslice protects ordinary IPv4 sockets created after an unprivileged application
enters the established cgroup in the host network namespace. Xray owns TUN
creation and proxy transport; it must stay outside the protected slice to avoid
recursive routing. Netslice owns the independent guard table and specifically
tagged IPv4 routing entries. Firewall installation is independent of Xray/TUN
availability.

Normal IPv4 packets are marked at route/output priority -150. At output priority
0, a separate socket/cgroup match sets packet priority `0x4e530001`. Postrouting
drops that tagged traffic if actual egress is neither loopback nor the configured
TUN. A routing-mark guard adds protection for packets retaining that mark.
Missing policy rules/routes, device loss, or missing marking rules are intended
to retain the priority guard. Removing both classification and enforcement is
outside this guarantee. The disposable-VM fixture must verify actual behavior.

External IPv6 from matching sockets is dropped at output, even if the TUN or
physical network later gains IPv6 connectivity. Loopback IPv6 remains allowed.
There is no new IPv6 policy rule or route. Migration removes the exact audited
old IPv6 entries only after replacement enforcement is installed.

The reserved packet priority may interact with qdisc classes, tc filters, or
other privileged packet processing. Do not overwrite it, route marked packets
through unrelated tunnels/VRFs, use the reserved mark for other software, or
send applications into another network namespace without separate integration
review. These are configuration prerequisites, not guarantees against arbitrary
system misconfiguration. Ordinary applications that deliberately use the
reserved metadata may be affected too.

## Launch checks and races

The launcher parses configuration as literal data, checks real kernel rules
before preparing its sandbox, then creates the scope. The fixed root helper
checks the complete stateless rule dump and current cgroup ID inside that scope
before executing fixed-path setpriv and the user command. Missing configuration,
missing slice, wrong scope, stale cgroup IDs, altered hooks/rules, dormant table
flags, and failed inspection cause exit 78. CLI syntax errors still return 2.

A bounded root-owned lock coordinates this implementation's firewall and routing
operations with readiness checks. A completed readiness check is a snapshot.
No userspace check and exec sequence is atomic with arbitrary privileged firewall
deletion. Continued protection of existing applications comes from persistent
kernel rules, not service state or the launch check. The helper checks a complete
normalized kernel dump; unknown nft output forms fail closed and require review.
It does not trust comments alone as proof that enforcement rules are effective.
The installed template must also match the supported schema fingerprint;
weakening that file cannot redefine successful readiness. Changes to the schema
require a reviewed helper fingerprint update and regression tests.

## Limitations

- Root, CAP_NET_ADMIN, sufficiently powerful BPF/tc changes, AF_PACKET/raw paths,
  other network namespaces, and kernel compromise are outside the supported
  unprivileged socket model. Netslice is not a boundary against administrators.
- Socket attribution follows the socket, not simply the calling process.
  Inherited connected sockets, socket activation, SCM_RIGHTS, sockets created
  before entering the slice, and descriptors owned by outside services are not
  promised protection. Fully quit existing app instances before relaunching.
- Loopback and local IPC remain functional. A localhost proxy, resolver, desktop
  service, or D-Bus recipient outside the slice can transmit externally on behalf
  of a protected app. Its sockets follow its own routing.
- Direct UDP/TCP DNS, application DoT, and DoH use application socket routing.
  NSS `resolve`, a local stub, D-Bus resolution, and other delegation may send
  DNS through a different process. Correct DNS answers and proxied curl results
  do not prove DNS transport privacy. This refactor does not replace host NSS
  configuration or impose a resolver architecture.
- Default Bubblewrap mode retains the existing host filesystem bind, timezone
  substitution, persistent fake machine ID, and session-bus masking. It is not
  complete telemetry isolation. `--allow_dbus` exposes the bus; routing-only mode
  exposes normal host integration. NoNewPrivileges inherited from a parent is
  retained; the launcher does not grant administrator access.
- Remote proxy failure may yield timeouts while packets still enter the TUN.
  Route presence, active units, and counter increments cannot prove proxy health.

## Deterministic lifecycle

| Event | Behavior |
| --- | --- |
| Boot | Firewall starts anchor, installs current-ID rules; routing is ordered after it and wants Xray. New launches require actual protection. |
| Xray absent/crashes/stops | Routing supervisor remains running, reports missing device, retains terminal unreachable route and guard. No BindsTo/PartOf dependency on Xray. |
| Xray/TUN recovers | Supervisor polls every configured 1–30 seconds, adds only missing address/rules/routes and brings the TUN up. |
| Missing rule or route | Guard remains; supervisor attempts exact repair. Conflicting/foreign state is refused. |
| Routing supervisor crashes | systemd restarts it after two seconds. ExecStopPost removes only owned routing entries; firewall persists. |
| Routing stops | Exact owned routes/rule removed; addresses and firewall remain. Existing clients lose routing while remaining guarded. |
| Firewall starts/reloads/restarts | One transaction installs/replaces the owned table. No stop action removes it. Routing wants, rather than binds to, firewall and stays available to reconcile afterward. |
| Firewall start/reload fails | Old transaction remains if present; new launches fail when current expected protection cannot be verified. |
| Firewall unit stops | Kernel rules persist. Service state alone says nothing about protection. |
| Anchor stops | Its sleeper stops; unrelated scopes remain. If scopes exist the slice stays; rules still reference it. Without scopes, recreated slice IDs require firewall reinstallation. |
| Privileged table deletion/global flush | Existing socket protection can disappear. New launches fail; routing supervisor reports degraded and does not claim to restore protection. |
| Host shutdown | Services stop without flushing firewall; rules last until kernel teardown. No persistence across reboot is assumed. |
| Package upgrade | No activation hook; units/files change only. Reviewed migration must handle loaded old stop actions and unit overrides. |
| Package removal | Rules persist in the kernel, but tools/configuration may disappear. Exit protected applications first, or retain the management files and guard until they exit. |

Commands are bounded by subprocess timeouts; there is no startup loop waiting
forever for a TUN. The supervisor's long-running polling is its service job,
not a blocking startup prerequisite. An active routing unit may be degraded;
read-only status distinguishes installed rules, routing configuration, device
state, and unverified remote reachability.
