pkgname=netslice-git
pkgver=r1.03d7051
pkgrel=2
pkgdesc="Selective per-application TUN routing with persistent nftables protection"
arch=('any')
url="https://github.com/occasion-2/netslice"
license=('MIT')
depends=('bash' 'python' 'nftables' 'bubblewrap' 'iproute2' 'systemd' 'util-linux' 'sudo' 'openssl')
makedepends=('git' 'make')
provides=('netslice')
conflicts=('netslice')
source=("git+https://github.com/occasion-2/netslice.git")
md5sums=('SKIP')
backup=('etc/netslice.conf' 'etc/nftables/netslice.nft')

pkgver() {
  cd "$srcdir/${pkgname%-git}"
  printf "r%s.%s" "$(git rev-list --count HEAD)" "$(git rev-parse --short HEAD)"
}

package() {
  cd "$srcdir/${pkgname%-git}"
  make DESTDIR="$pkgdir/" PREFIX=/usr SYSCONFDIR=/etc SYSTEMDDIR=/usr/lib/systemd/system install
}
