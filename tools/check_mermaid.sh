#!/usr/bin/env bash
# AC-M10-4: every Mermaid flow in the repo compiles with @mermaid-js/mermaid-cli, without an embedded syntax error.
# The sample .mmd files are byte-identical to packages/flow_renderer output (tests/m10), so this covers the renderer.
# Usage: tools/check_mermaid.sh            (needs Node 20+; downloads mermaid-cli through npx)
set -euo pipefail
out="$(mktemp -d)"
config="$out/puppeteer.json"
echo '{"args": ["--no-sandbox"]}' > "$config"  # CI runners have no user namespace sandbox
status=0
while IFS= read -r f; do
  svg="$out/$(echo "$f" | tr '/' '_').svg"
  if ! npx -y @mermaid-js/mermaid-cli@11 -q -p "$config" -i "$f" -o "$svg"; then
    echo "FAILED to render: $f"; status=1; continue
  fi
  if grep -qi "syntax error" "$svg"; then
    echo "Syntax error in: $f"; status=1; continue
  fi
  echo "ok: $f"
done < <(git ls-files '*.mmd')
exit $status
