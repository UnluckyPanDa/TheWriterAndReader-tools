#!/bin/zsh

set -u

ROOT="/Volumes/SN7100/Projects/TheWriterAndReader-tools"
TWR="/Users/johnny/.local/bin/twr"
URL="http://127.0.0.1:8765/"
LOG_DIR="$HOME/Library/Logs"
LOG_FILE="$LOG_DIR/TWR-web.log"

cd "$ROOT" || exit 1

if ! /usr/bin/curl -fsS --max-time 1 "$URL" >/dev/null 2>&1; then
  /bin/mkdir -p "$LOG_DIR"
  /usr/bin/nohup "$TWR" web --no-open >>"$LOG_FILE" 2>&1 &

  ready=0
  for _ in {1..30}; do
    if /usr/bin/curl -fsS --max-time 1 "$URL" >/dev/null 2>&1; then
      ready=1
      break
    fi
    /bin/sleep 1
  done

  if (( ! ready )); then
    /usr/bin/open -a Terminal "$LOG_FILE"
    exit 1
  fi
fi

/usr/bin/open "$URL"
