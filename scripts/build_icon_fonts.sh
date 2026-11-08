#!/usr/bin/env bash
# Rebuild the icon fonts the site serves, cut down to the glyphs it uses.
#
#   scripts/build_icon_fonts.sh
#
# Needs npm (to fetch the release packages) and fontTools' pyftsubset with
# Brotli (`pip install fonttools brotli`). Writes:
#   assets/webfonts/fa-solid-900.woff2   Font Awesome Free 6.5.2, solid
#   assets/webfonts/fa-brands-400.woff2  Font Awesome Free 6.5.2, brands
#   assets/fonts/academicons.woff2       Academicons 1.9.5
#
# The full fonts are 300 kB and every page loads them for a dozen icons. To
# use another icon, add its code point here and its rule to
# _sass/include/_icons.scss, then run this again. The code points are in each
# package's CSS (e.g. `.fa-sun::before { content: "\f185"; }`).
set -euo pipefail

# sun moon location-dot link id-card building-columns address-card calendar
# envelope camera
SOLID="U+F185,U+F186,U+F3C5,U+F0C1,U+F2C2,U+F19C,U+F2BB,U+F133,U+F0E0,U+F030"
# github x-twitter linkedin facebook bluesky
BRANDS="U+F09B,U+E61B,U+F08C,U+F09A,U+E671"
# google-scholar
ACADEMICONS="U+E9D4"

repo=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"
npm pack --silent @fortawesome/fontawesome-free@6.5.2 academicons@1.9.5 > /dev/null
for tgz in *.tgz; do mkdir "${tgz%.tgz}" && tar xzf "$tgz" -C "${tgz%.tgz}"; done

subset() {  # source, code points, destination
  pyftsubset "$1" --unicodes="$2" --flavor=woff2 --layout-features='*' \
    --name-IDs='*' --name-languages='*' --output-file="$3"
  echo "$(basename "$3"): $(wc -c < "$3") bytes"
}
fa=fortawesome-fontawesome-free-6.5.2/package/webfonts
subset "$fa/fa-solid-900.ttf" "$SOLID" "$repo/assets/webfonts/fa-solid-900.woff2"
subset "$fa/fa-brands-400.ttf" "$BRANDS" "$repo/assets/webfonts/fa-brands-400.woff2"
subset academicons-1.9.5/package/fonts/academicons.ttf "$ACADEMICONS" "$repo/assets/fonts/academicons.woff2"
