#!/usr/bin/env bash
set -euo pipefail

label="${1:?usage: build-gcamdata.sh <label>}"
case "$label" in
  *[!A-Za-z0-9._-]*)
    echo "label may contain only letters, digits, dot, underscore, and hyphen" >&2
    exit 2
    ;;
esac

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
gcamdata_root="$(cd "$script_dir/.." && pwd)"
rscript="${RSCRIPT:-Rscript}"
snapshot="$gcamdata_root/xml-$label"
log_dir="$script_dir/logs"
log_file="$log_dir/build-$label.log"

if [ -e "$snapshot" ]; then
  echo "refusing to overwrite existing snapshot: $snapshot" >&2
  exit 1
fi

command -v "$rscript" >/dev/null 2>&1 || {
  echo "Rscript executable not found: $rscript" >&2
  exit 1
}

python3 "$script_dir/verify.py"
python3 "$script_dir/generation/regenerate.py"
python3 "$script_dir/deploy.py"

mkdir -p "$log_dir"
cd "$gcamdata_root"
export RENV_CONFIG_AUTOLOADER_ENABLED=FALSE

"$rscript" -e 'devtools::load_all(".", quiet=TRUE)' -e 'driver_drake()' 2>&1 | tee "$log_file"

if [ ! -d xml ]; then
  echo "gcamdata build did not produce the xml directory" >&2
  exit 1
fi
cp -a xml "$snapshot"
xml_count="$(find "$snapshot" -maxdepth 1 -type f -name '*.xml' | wc -l)"
if [ "$xml_count" -ne 226 ]; then
  echo "expected 226 XML files, found $xml_count in $snapshot" >&2
  exit 1
fi
python3 "$script_dir/verify.py" --xml-snapshot "$snapshot"
echo "built $xml_count XML files: $snapshot"
