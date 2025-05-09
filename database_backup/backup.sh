#!/bin/bash

# Charger les variables d'environnement depuis le fichier .env
set -a
source "$(dirname "$0")/.env"
set +a

# Variables
DATE=$(date +"%Y-%m-%d")
BACKUP_FILE="$BACKUP_DIR/save_$DATE.sql"

# Vérifier si le dossier de backup existe, sinon le créer
mkdir -p "$BACKUP_DIR"

# Exécuter la sauvegarde
mysqldump -u "$DB_USER" -p"$DB_PASS" -t --compact --extended-insert --net-buffer-length=4096 "$DB_NAME" > "$BACKUP_FILE"

# Ne garder que les 7 derniers backups pour éviter de remplir le stockage
find "$BACKUP_DIR" -type f -name "save_*.sql" -mtime +7 -exec rm {} \;
