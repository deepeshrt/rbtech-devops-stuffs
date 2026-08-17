#!/usr/bin/env bash

#==================================================
# chmod +x backup.sh
# ./backup.sh
#==================================================
set -Eeuo pipefail

# --------------------------------------------------
# Load .env
# --------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    echo "ERROR: .env file not found"
    exit 1
fi

set -a
source "$SCRIPT_DIR/.env"
set +a


# --------------------------------------------------
# Configuration
# --------------------------------------------------

DB_TYPE="${DB_TYPE:-}"

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-}"
DB_NAME="${DB_NAME:-}"
DB_USER="${DB_USER:-}"
DB_PASSWORD="${DB_PASSWORD:-}"

AWS_REGION="${AWS_REGION:-ap-south-1}"
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="${S3_PREFIX:-database-backups}"
S3_ENCRYPTION="${S3_ENCRYPTION:-AES256}"


# --------------------------------------------------
# Validation
# --------------------------------------------------

if [[ -z "$DB_TYPE" ]]; then
    echo "ERROR: DB_TYPE is required"
    exit 1
fi

if [[ -z "$DB_NAME" ]]; then
    echo "ERROR: DB_NAME is required"
    exit 1
fi

if [[ -z "$DB_USER" ]]; then
    echo "ERROR: DB_USER is required"
    exit 1
fi

if [[ -z "$DB_PASSWORD" ]]; then
    echo "ERROR: DB_PASSWORD is required"
    exit 1
fi

if [[ -z "$S3_BUCKET" ]]; then
    echo "ERROR: S3_BUCKET is required"
    exit 1
fi


# --------------------------------------------------
# Set default ports
# --------------------------------------------------

case "$DB_TYPE" in

    mariadb)
        DB_PORT="${DB_PORT:-3306}"
        ;;

    postgres)
        DB_PORT="${DB_PORT:-5432}"
        ;;

    mongodb)
        DB_PORT="${DB_PORT:-27017}"
        ;;

    *)
        echo "ERROR: Unsupported DB_TYPE: $DB_TYPE"
        echo "Supported: mariadb, postgres, mongodb"
        exit 1
        ;;
esac


# --------------------------------------------------
# Check required commands
# --------------------------------------------------

check_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "ERROR: '$1' is not installed"
        exit 1
    fi
}

check_command aws

case "$DB_TYPE" in
    mariadb)
        check_command mariadb-dump
        ;;
    postgres)
        check_command pg_dump
        ;;
    mongodb)
        check_command mongodump
        ;;
esac


# --------------------------------------------------
# Create temporary directory
# --------------------------------------------------

BACKUP_DIR="$(mktemp -d)"

cleanup() {
    rm -rf "$BACKUP_DIR"
}

trap cleanup EXIT


# --------------------------------------------------
# Timestamp
# --------------------------------------------------

TIMESTAMP="$(date -u '+%Y-%m-%d_%H-%M-%S')"


# --------------------------------------------------
# Create backup
# --------------------------------------------------

echo "=========================================="
echo "Database Backup"
echo "=========================================="
echo "Database : $DB_NAME"
echo "Type     : $DB_TYPE"
echo "Host     : $DB_HOST"
echo "Started  : $(date)"
echo "=========================================="


case "$DB_TYPE" in

    # ------------------------------------------
    # MariaDB
    # ------------------------------------------

    mariadb)

        BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.sql"

        echo "Creating MariaDB backup..."

        export MYSQL_PWD="$DB_PASSWORD"

        mariadb-dump \
            --host="$DB_HOST" \
            --port="$DB_PORT" \
            --user="$DB_USER" \
            --single-transaction \
            --routines \
            --triggers \
            --events \
            "$DB_NAME" \
            > "$BACKUP_FILE"

        unset MYSQL_PWD

        ;;


    # ------------------------------------------
    # PostgreSQL
    # ------------------------------------------

    postgres)

        BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.sql"

        echo "Creating PostgreSQL backup..."

        export PGPASSWORD="$DB_PASSWORD"

        pg_dump \
            --host="$DB_HOST" \
            --port="$DB_PORT" \
            --username="$DB_USER" \
            --dbname="$DB_NAME" \
            --format=plain \
            --no-owner \
            --no-acl \
            > "$BACKUP_FILE"

        unset PGPASSWORD

        ;;


    # ------------------------------------------
    # MongoDB
    # ------------------------------------------

    mongodb)

        BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.archive"

        echo "Creating MongoDB backup..."

        mongodump \
            --host="$DB_HOST" \
            --port="$DB_PORT" \
            --username="$DB_USER" \
            --password="$DB_PASSWORD" \
            --authenticationDatabase=admin \
            --db="$DB_NAME" \
            --archive="$BACKUP_FILE"

        ;;

esac


# --------------------------------------------------
# Verify backup
# --------------------------------------------------

if [[ ! -s "$BACKUP_FILE" ]]; then
    echo "ERROR: Backup file is empty"
    exit 1
fi

echo "Backup created:"
echo "$BACKUP_FILE"

echo "Backup size:"
du -h "$BACKUP_FILE"


# --------------------------------------------------
# Compress
# --------------------------------------------------

echo "Compressing backup..."

gzip "$BACKUP_FILE"

BACKUP_FILE="${BACKUP_FILE}.gz"

echo "Compressed backup:"
echo "$BACKUP_FILE"

echo "Compressed size:"
du -h "$BACKUP_FILE"


# --------------------------------------------------
# S3 path
# --------------------------------------------------

S3_KEY="${S3_PREFIX}/${DB_TYPE}/$(basename "$BACKUP_FILE")"

S3_PATH="s3://${S3_BUCKET}/${S3_KEY}"


# --------------------------------------------------
# Upload to S3
# --------------------------------------------------

echo
echo "Uploading backup to:"
echo "$S3_PATH"

AWS_ARGS=(
    s3 cp
    "$BACKUP_FILE"
    "$S3_PATH"
    --region "$AWS_REGION"
)

if [[ -n "$S3_ENCRYPTION" ]]; then
    AWS_ARGS+=(
        --sse "$S3_ENCRYPTION"
    )
fi

aws "${AWS_ARGS[@]}"


# --------------------------------------------------
# Complete
# --------------------------------------------------

echo
echo "=========================================="
echo "BACKUP COMPLETED SUCCESSFULLY"
echo "=========================================="
echo "Database : $DB_NAME"
echo "Type     : $DB_TYPE"
echo "S3       : $S3_PATH"
echo "Finished : $(date)"
echo "=========================================="
