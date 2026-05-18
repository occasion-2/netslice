pkgname=netslice-git
pkgver=r1.03d7051
pkgrel=1
pkgdesc="Seamless per-application network isolation routing via cgroups, nftables, and bubblewrap"
arch=('any')
url="https://github.com/yourusername/netslice"
license=('MIT')
depends=('bash' 'nftables' 'bubblewrap' 'iproute2' 'systemd')
makedepends=('git' 'make')
provides=('netslice')
conflicts=('netslice')
source=("git+file:///home/denis/Documents/temp/netslice")
md5sums=('SKIP')
backup=('etc/netslice.conf')

pkgver() {
  cd "$srcdir/${pkgname%-git}"
  printf "r%s.%s" "$(git rev-list --count HEAD)" "$(git rev-parse --short HEAD)"
}

package() {
  cd "$srcdir/${pkgname%-git}"
  make DESTDIR="$pkgdir/" PREFIX=/usr SYSCONFDIR=/etc SYSTEMDDIR=/usr/lib/systemd/system install
}
