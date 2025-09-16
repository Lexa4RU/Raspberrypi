#!/bin/bash

# Load the variables from the .env file
set -a
source "$(dirname "$0")/.env"
set +a

# Setting up the variables for the save
DATE=$(date +"%Y-%m-%d")
BACKUP_FILE="$BACKUP_DIR/save_$DATE.sql"

# Check if the backup folder exist, if not create it
mkdir -p "$BACKUP_DIR"

# Excecute the backup
mysqldump -u "$DB_USER" -p"$DB_PASS" -t --compact --extended-insert --net-buffer-length=4096 "$DB_NAME" > "$BACKUP_FILE"

# Delete the oldest backup if there is more than 7 to don't take to much space in the disk
find "$BACKUP_DIR" -type f -name "save_*.sql" -mtime +7 -exec rm {} \;
