PREFIX ?= /usr/local
SYSCONFDIR ?= /etc
SYSTEMDDIR ?= /etc/systemd/system
PYTHON ?= python3

# Refuse the old combined service before changing files or starting services.
CHECK_LEGACY = for unit in '$(SYSTEMDDIR)/netslice-routing.service' /etc/systemd/system/netslice-routing.service; do \
	if test -f "$$unit" && ! grep -Eq '^ExecStart=[^[:space:]]*/netslice-control routing-watch$$' "$$unit"; then \
		echo "Legacy routing unit: $$unit. Follow docs/DEPLOYMENT.md before upgrading." >&2; exit 1; \
	fi; done

all:
	@echo "Install: sudo make install"
	@echo "First start: sudo make enable"

# Installation only writes files. It never runs systemctl, nft, ip, or package hooks.
# Existing configuration is retained; a new example is installed alongside it.
install:
	@set -eu; \
	if test -z '$(DESTDIR)'; then \
		$(CHECK_LEGACY); \
	fi; \
	put() { \
		source=$$1; target=$$2; mode=$$3; \
		install -d "$$(dirname "$$target")"; \
		temporary=$$(mktemp "$$target.new.XXXXXX"); \
		trap 'rm -f "$$temporary"' EXIT HUP INT TERM; \
		case "$$source" in \
			bin/*|systemd/*) sed -e 's|@@SYSCONFDIR@@|$(SYSCONFDIR)|g' -e 's|@@PREFIX@@|$(PREFIX)|g' "$$source" > "$$temporary" ;; \
			*) cat "$$source" > "$$temporary" ;; \
		esac; \
		chmod "$$mode" "$$temporary"; \
		mv -fT "$$temporary" "$$target"; \
		trap - EXIT HUP INT TERM; \
	}; \
	for name in netslice-launch netslice-control; do put "bin/$$name" '$(DESTDIR)$(PREFIX)/bin/'"$$name" 755; done; \
	put configs/netslice.conf '$(DESTDIR)$(SYSCONFDIR)/netslice.conf.example' 644; \
	if ! test -e '$(DESTDIR)$(SYSCONFDIR)/netslice.conf'; then put configs/netslice.conf '$(DESTDIR)$(SYSCONFDIR)/netslice.conf' 644; fi; \
	put nftables/netslice.nft '$(DESTDIR)$(SYSCONFDIR)/nftables/netslice.nft' 644; \
	for name in netslice-anchor netslice-firewall netslice-routing; do put "systemd/$$name.service" '$(DESTDIR)$(SYSTEMDDIR)/'"$$name.service" 644; done; \
	put README.md '$(DESTDIR)$(PREFIX)/share/doc/netslice/README.md' 644; \
	for source in docs/*.md; do put "$$source" '$(DESTDIR)$(PREFIX)/share/doc/netslice/'"$$source" 644; done; \
	put tools/netslice-maintenance '$(DESTDIR)$(PREFIX)/share/doc/netslice/netslice-maintenance' 755
	@if test -n '$(DESTDIR)'; then \
		echo 'Staged installation complete.'; \
	else \
		echo 'Installed. Configuration: $(SYSCONFDIR)/netslice.conf'; \
		echo 'First start: sudo make enable'; \
		echo 'Updates: see docs/DEPLOYMENT.md. Running services were not restarted.'; \
	fi

# Explicit activation; never invoked by install or package builds.
enable:
	@test -z '$(DESTDIR)' || { echo 'enable requires the live installation, without DESTDIR.' >&2; exit 1; }
	@test "$$(id -u)" = 0 || { echo 'Run sudo make enable.' >&2; exit 1; }
	@test -x '$(PREFIX)/bin/netslice-control' || { echo 'Run sudo make install first.' >&2; exit 1; }
	@test -f '$(SYSTEMDDIR)/netslice-routing.service' || { echo 'Run sudo make install with matching SYSTEMDDIR first.' >&2; exit 1; }
	@$(CHECK_LEGACY)
	systemctl daemon-reload
	systemctl enable --now netslice-anchor.service netslice-firewall.service netslice-routing.service
	'$(PREFIX)/bin/netslice-control' ready
	'$(PREFIX)/bin/netslice-control' routing-once
	'$(PREFIX)/bin/netslice-control' status

status:
	'$(PREFIX)/bin/netslice-control' status

check:
	bash -n bin/netslice-launch tools/netslice-maintenance
	$(PYTHON) -m unittest discover -s tests -v

# Retain configuration, runtime state, and kernel rules. No service shutdown.
# Active scopes must be handled using the package-removal procedure first.
uninstall:
	@$(PYTHON) -c 'import os,sys; p=sys.argv[1]; sys.exit(0 if p.startswith("/") and os.path.realpath(p) != "/" else 1)' '$(DESTDIR)' || { echo 'Live uninstall is gated: follow docs/DEPLOYMENT.md; use an absolute DESTDIR for staged removal.' >&2; exit 1; }
	rm -f $(DESTDIR)$(PREFIX)/bin/netslice-launch $(DESTDIR)$(PREFIX)/bin/netslice-control
	rm -f $(DESTDIR)$(SYSTEMDDIR)/netslice-anchor.service $(DESTDIR)$(SYSTEMDDIR)/netslice-firewall.service $(DESTDIR)$(SYSTEMDDIR)/netslice-routing.service
	rm -rf $(DESTDIR)$(PREFIX)/share/doc/netslice

.PHONY: all install enable status check uninstall
