#!/usr/bin/env bash

#===========================================================
# chmod +x get-jenkins-plugins.sh
# ./get-jenkins-plugins.sh
# it creates "jenkins-plugins.txt"
# if needed spesificy your location
# ./get-jenkins-plugins.sh /tmp/jenkins-plugins.txt
#
# if Jenkins is installed using a package/container with a different JENKINS_HOME
# JENKINS_HOME=/your/jenkins/home ./get-jenkins-plugins.sh
#===========================================================

set -euo pipefail

JENKINS_HOME="${JENKINS_HOME:-/var/lib/jenkins}"
PLUGIN_DIR="${JENKINS_HOME}/plugins"
OUTPUT_FILE="${1:-./jenkins-plugins.txt}"

echo "Jenkins home : ${JENKINS_HOME}"
echo "Plugin dir   : ${PLUGIN_DIR}"
echo "Output file  : ${OUTPUT_FILE}"
echo

if [[ ! -d "$PLUGIN_DIR" ]]; then
    echo "ERROR: Jenkins plugin directory not found:"
    echo "$PLUGIN_DIR"
    exit 1
fi

# Check unzip is available
if ! command -v unzip >/dev/null 2>&1; then
    echo "ERROR: unzip is not installed."
    echo "Install it with:"
    echo "  sudo apt install unzip"
    exit 1
fi

# Empty/create output file
> "$OUTPUT_FILE"

echo "# Jenkins plugins" >> "$OUTPUT_FILE"
echo "# Generated: $(date)" >> "$OUTPUT_FILE"
echo "#" >> "$OUTPUT_FILE"

count=0

for plugin_file in "$PLUGIN_DIR"/*.jpi "$PLUGIN_DIR"/*.hpi; do

    # Handle no matching files
    [[ -f "$plugin_file" ]] || continue

    filename="$(basename "$plugin_file")"

    # Remove .jpi / .hpi
    plugin_name="${filename%.jpi}"
    plugin_name="${plugin_name%.hpi}"

    # Read plugin version from MANIFEST.MF
    plugin_version="$(
        unzip -p "$plugin_file" META-INF/MANIFEST.MF 2>/dev/null \
        | tr -d '\r' \
        | awk -F': ' '
            /^Plugin-Version:/ {
                print $2
                exit
            }
        '
    )"

    # Fallback
    if [[ -z "$plugin_version" ]]; then
        plugin_version="unknown"
    fi

    echo "${plugin_name}:${plugin_version}" >> "$OUTPUT_FILE"

    printf "%-40s %s\n" "$plugin_name" "$plugin_version"

    ((count+=1))

done

# Sort plugins while keeping the header
{
    head -n 3 "$OUTPUT_FILE"
    tail -n +4 "$OUTPUT_FILE" | sort
} > "${OUTPUT_FILE}.tmp"

mv "${OUTPUT_FILE}.tmp" "$OUTPUT_FILE"

echo
echo "=========================================="
echo "Plugin inventory completed"
echo "=========================================="
echo "Plugins found : $count"
echo "Output file   : $OUTPUT_FILE"
echo
echo "Contents:"
cat "$OUTPUT_FILE"
