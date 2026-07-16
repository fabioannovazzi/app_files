#!/bin/zsh
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
label="com.mparanza.outreach"
plist_path="${HOME}/Library/LaunchAgents/${label}.plist"
log_dir="${repo_dir}/data/outreach/logs"
stdout_path="${log_dir}/daily_outreach.out.log"
stderr_path="${log_dir}/daily_outreach.err.log"

mkdir -p "${HOME}/Library/LaunchAgents" "${log_dir}"

cat >"${plist_path}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>cd "${repo_dir}" && source .venv/bin/activate && python scripts/run_outreach_automation.py</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
  </array>
  <key>StandardOutPath</key>
  <string>${stdout_path}</string>
  <key>StandardErrorPath</key>
  <string>${stderr_path}</string>
  <key>WorkingDirectory</key>
  <string>${repo_dir}</string>
</dict>
</plist>
PLIST

launchctl unload "${plist_path}" >/dev/null 2>&1 || true
launchctl load "${plist_path}"

printf 'Installed %s\n' "${plist_path}"
printf 'Schedule: Monday-Friday at 08:00 local machine time\n'
printf 'Logs: %s and %s\n' "${stdout_path}" "${stderr_path}"
