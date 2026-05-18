PREFIX ?= /usr/local
SYSCONFDIR ?= /etc
SYSTEMDDIR ?= /etc/systemd/system

all:
	@echo "Run 'make install' to install netslice."

install:
	install -Dm755 bin/netslice-launch $(DESTDIR)$(PREFIX)/bin/netslice-launch
	install -Dm644 configs/netslice.conf $(DESTDIR)$(SYSCONFDIR)/netslice.conf
	install -Dm644 nftables/netslice.nft $(DESTDIR)$(SYSCONFDIR)/nftables/netslice.nft
	install -Dm644 systemd/netslice-anchor.service $(DESTDIR)$(SYSTEMDDIR)/netslice-anchor.service
	install -Dm644 systemd/netslice-routing.service $(DESTDIR)$(SYSTEMDDIR)/netslice-routing.service
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
