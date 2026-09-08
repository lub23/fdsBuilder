#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d "agent_damage/checkpoints/split_models" ]]; then
  echo "ERROR: split models are missing under agent_damage/checkpoints/split_models." >&2
  exit 1
fi

if command -v uv >/dev/null 2>&1; then
  uv sync --dev
  uv run pyinstaller --noconfirm --clean fdsBuilder.spec
else
  python -m PyInstaller --noconfirm --clean fdsBuilder.spec
fi

STAGE="$ROOT/packaging/debroot"
rm -rf "$STAGE"
mkdir -p \
  "$STAGE/opt/fdsbuilder" \
  "$STAGE/opt/fdsbuilder/share/docs" \
  "$STAGE/usr/share/applications" \
  "$STAGE/DEBIAN"

install -m 0755 "dist/fdsBuilder" "$STAGE/opt/fdsbuilder/fdsBuilder"
install -m 0644 README.md "$STAGE/opt/fdsbuilder/share/docs/README.md"
if compgen -G "report/*.docx" >/dev/null; then
  install -m 0644 report/*.docx "$STAGE/opt/fdsbuilder/share/docs/"
fi
install -m 0644 packaging/linux/fdsbuilder.desktop \
  "$STAGE/usr/share/applications/fdsbuilder.desktop"
install -m 0644 packaging/linux/control "$STAGE/DEBIAN/control"
install -m 0755 packaging/linux/postinst "$STAGE/DEBIAN/postinst"
install -m 0755 packaging/linux/prerm "$STAGE/DEBIAN/prerm"

dpkg-deb --root-owner-group --build "$STAGE" dist/fdsbuilder_0.1.0_amd64.deb
echo "Built: $ROOT/dist/fdsbuilder_0.1.0_amd64.deb"
