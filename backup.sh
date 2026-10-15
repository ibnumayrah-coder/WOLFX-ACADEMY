#!/bin/bash
# Daily backup of the database + uploaded videos. Keeps 14 days of database copies.
set -e
DEST=/var/backups/wolfx
mkdir -p "$DEST"
STAMP=$(date +%F)
sqlite3 /var/lib/wolfx/wolfx.db ".backup '$DEST/wolfx-$STAMP.db'"
rsync -a /var/lib/wolfx/uploads/ "$DEST/uploads/"
find "$DEST" -maxdepth 1 -name 'wolfx-*.db' -mtime +14 -delete
