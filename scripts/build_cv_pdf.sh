#!/usr/bin/env bash
# Compile the CV the way Overleaf does: XeLaTeX, BibTeX, then XeLaTeX twice.
#
# Usage: scripts/build_cv_pdf.sh <project directory> [main document, default cv.tex]
#
# Every .aux that asks for a bibliography gets a BibTeX run: the main one, and
# one per multibib \newcites list (proc.aux for the conference papers).
#
# Overleaf carries on past most LaTeX errors and still produces a PDF, and the
# CV is written against that, so this does too: LaTeX errors, undefined
# citations, glyphs missing from a font and BibTeX's complaints are reported
# as warnings on the Actions run. Two things stop it instead, because the PDF
# would then be missing text that Overleaf shows: no PDF at all, and a font
# that could not be found. The PDF already on the site stays until it is fixed.
set -uo pipefail

dir=${1:?usage: build_cv_pdf.sh <project directory> [main.tex]}
main=${2:-cv.tex}
main=${main%.tex}
cd "$dir" || exit 1

# One message per log line, so the checks below see whole messages.
export max_print_line=10000

warn_each() {  # prefix; lines on stdin, at most ten of them, each once
  sort -u | head -n 10 | while IFS= read -r line; do
    echo "::warning::$1$line"
  done
}

run_xelatex() {
  xelatex -interaction=nonstopmode -file-line-error "$main.tex" > /dev/null
}

rm -f "$main.pdf"
run_xelatex
for aux in *.aux; do
  if [ -e "$aux" ] && grep -q '^\\bibdata' "$aux"; then
    bibtex "${aux%.aux}" > /dev/null
    grep -E '^Warning--|error message' "${aux%.aux}.blg" | warn_each "BibTeX (${aux%.aux}): "
  fi
done
run_xelatex
run_xelatex

grep -E '^[^ :]+:[0-9]+: ' "$main.log" | warn_each "LaTeX: "
grep -E 'Citation .* undefined' "$main.log" | warn_each "LaTeX: "
grep -E '^Missing character' "$main.log" | warn_each "XeTeX: "

if [ ! -s "$main.pdf" ]; then
  echo "::error::XeLaTeX produced no PDF from $main.tex. The end of its log:"
  tail -n 30 "$main.log"
  exit 1
fi
if grep -q -E 'The font .* cannot be found|in font nullfont!' "$main.log"; then
  echo "::error::A font the CV uses was not found, so the PDF would be missing text. It was not published."
  grep -E 'The font .* cannot be found' "$main.log" | sort -u | head -n 5
  exit 1
fi
echo "Built $main.pdf ($(wc -c < "$main.pdf") bytes)"
