# Future AUR package

Do not submit an AUR package until a public tagged source release exists. Use a
normal source archive package named `linux-why` with these fields:

- `pkgver=0.1.1`, `pkgrel=1`, `arch=('any')`, `license=('MIT')`.
- `depends=('python>=3.12' 'pacman' 'python-textual>=6.12' 'python-textual<7' 'python-pyfiglet')`.
  Verify availability/version compatibility of these Python packages before submission.
- `makedepends=('python-build' 'python-installer' 'python-hatchling')`.
- `checkdepends=('python-pytest' 'python-pytest-asyncio' 'python-jsonschema')`.
- `optdepends=('expac: package metadata cross-check' 'iproute2: interface addresses'
  'kmod: module metadata' 'systemd: unit provenance')`.
- Set `url` and `source` to the actual published repository and tagged archive.
- Generate real `sha256sums`; do not use SKIP for release archives.
- `build()`: `python -m build --wheel --no-isolation` in the extracted source.
- `check()`: `pytest -m 'not integration'`.
- `package()`: `python -m installer --destdir="$pkgdir" dist/*.whl`, then install
  LICENSE to `"$pkgdir/usr/share/licenses/$pkgname/LICENSE"`.

Review the resulting package with namcap and test in a clean Arch chroot. Generate
`.SRCINFO` with `makepkg --printsrcinfo`. Publication is a separate maintainer action.
