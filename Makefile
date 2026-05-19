PREFIX ?= /usr/local
SYSCONFDIR ?= /etc
SYSTEMDDIR ?= /etc/systemd/system

all:
	@echo "Run 'make install' to install netslice."

install:
	mkdir -p $(DESTDIR)$(PREFIX)/bin
	mkdir -p $(DESTDIR)$(SYSCONFDIR)/nftables
	mkdir -p $(DESTDIR)$(SYSTEMDDIR)
	
	sed "s|@@SYSCONFDIR@@|$(SYSCONFDIR)|g" bin/netslice-launch > bin/netslice-launch.inst
	install -Dm755 bin/netslice-launch.inst $(DESTDIR)$(PREFIX)/bin/netslice-launch
	rm bin/netslice-launch.inst
	
	install -Dm644 configs/netslice.conf $(DESTDIR)$(SYSCONFDIR)/netslice.conf
	install -Dm644 nftables/netslice.nft $(DESTDIR)$(SYSCONFDIR)/nftables/netslice.nft
	
	sed "s|@@SYSCONFDIR@@|$(SYSCONFDIR)|g" systemd/netslice-anchor.service > systemd/netslice-anchor.service.inst
	install -Dm644 systemd/netslice-anchor.service.inst $(DESTDIR)$(SYSTEMDDIR)/netslice-anchor.service
	rm systemd/netslice-anchor.service.inst
	
	sed "s|@@SYSCONFDIR@@|$(SYSCONFDIR)|g" systemd/netslice-routing.service > systemd/netslice-routing.service.inst
	install -Dm644 systemd/netslice-routing.service.inst $(DESTDIR)$(SYSTEMDDIR)/netslice-routing.service
	rm systemd/netslice-routing.service.inst

	@echo ""
	@echo "Installation complete."
	@echo "Please edit $(DESTDIR)$(SYSCONFDIR)/netslice.conf to match your proxy setup."
	@echo "Then enable the service: systemctl enable --now netslice-routing.service"

uninstall:
	rm -f $(DESTDIR)$(PREFIX)/bin/netslice-launch
	rm -f $(DESTDIR)$(SYSCONFDIR)/netslice.conf
	rm -f $(DESTDIR)$(SYSCONFDIR)/nftables/netslice.nft
	rm -f $(DESTDIR)$(SYSTEMDDIR)/netslice-anchor.service
	rm -f $(DESTDIR)$(SYSTEMDDIR)/netslice-routing.service
	@echo "Uninstalled successfully."
