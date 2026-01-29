#!/bin/bash
# connect rtpmidid iPad port to alsa midi through (by name, not number)

ACONNECT=/usr/bin/aconnect
TARGET_PORT="14:0"
SLEEP_TIME=1

while true; do
  # rtpmidid client number
  RTP_CLIENT=$($ACONNECT -l | awk -F: "/'rtpmidid'/{print \$1}" | awk '{print $2}')

  # first iPad port number under rtpmidid (matches lines like: "    3 'iPad            '")
  RTP_PORT=$(
    $ACONNECT -l | awk -v c="$RTP_CLIENT" '
      $1=="client" && $2==c":" {in_client=1; next}
      in_client && $1=="client" {exit}
      in_client && $2 ~ /'\''iPad/ {print $1; exit}
    ' | tr -d :
  )

  if [ -n "$RTP_CLIENT" ] && [ -n "$RTP_PORT" ]; then
    # already connected?
    if $ACONNECT -l | grep -q "$RTP_CLIENT:$RTP_PORT -> $TARGET_PORT"; then
      exit 0
    fi

    $ACONNECT "$RTP_CLIENT:$RTP_PORT" "$TARGET_PORT"
    exit 0
  fi

  sleep "$SLEEP_TIME"
done

