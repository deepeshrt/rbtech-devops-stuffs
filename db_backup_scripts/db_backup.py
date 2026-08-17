# Required Packages
# pip install boto3 python-dotenv

# Rename .env.example.python to .env and fill in the values

# For Postgre
# DB_TYPE=postgres
# DB_PORT=5432

# For MariaDB
# DB_TYPE=mariadb
# DB_PORT=3306

# For mongodb
# DB_TYPE=mariadb
# DB_PORT=3306

# Command to run
# python backup.py



import os
import gzip
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone

import boto3
from dotenv import load_dotenv


load_dotenv()


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

DB_TYPE = os.getenv("DB_TYPE", "").lower()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
S3_BUCKET = os.getenv("S3_BUCKET")
S3_PREFIX = os.getenv("S3_PREFIX", "database-backups")
S3_ENCRYPTION = os.getenv("S3_ENCRYPTION", "AES256")


# ---------------------------------------------------------
# Validation
# ---------------------------------------------------------

def validate_config():
    if DB_TYPE not in ("mariadb", "postgres", "mongodb"):
        raise ValueError(
            "DB_TYPE must be one of: mariadb, postgres, mongodb"
        )

    required = {
        "DB_NAME": DB_NAME,
        "DB_USER": DB_USER,
        "DB_PASSWORD": DB_PASSWORD,
        "S3_BUCKET": S3_BUCKET,
    }

    missing = [
        key for key, value in required.items()
        if not value
    ]

    if missing:
        raise ValueError(
            "Missing environment variables: "
            + ", ".join(missing)
        )


# ---------------------------------------------------------
# MariaDB backup
# ---------------------------------------------------------

def backup_mariadb(output_file):
    port = DB_PORT or "3306"

    print("Creating MariaDB backup...")

    env = os.environ.copy()

    # Password is provided through environment instead of
    # putting it directly in the command line.
    env["MYSQL_PWD"] = DB_PASSWORD

    command = [
        "mariadb-dump",
        "--host", DB_HOST,
        "--port", port,
        "--user", DB_USER,
        "--single-transaction",
        "--routines",
        "--triggers",
        "--events",
        DB_NAME,
    ]

    run_dump(command, output_file, env)

    print("MariaDB backup completed.")


# ---------------------------------------------------------
# PostgreSQL backup
# ---------------------------------------------------------

def backup_postgres(output_file):
    port = DB_PORT or "5432"

    print("Creating PostgreSQL backup...")

    env = os.environ.copy()

    # pg_dump reads PostgreSQL password from PGPASSWORD.
    env["PGPASSWORD"] = DB_PASSWORD

    command = [
        "pg_dump",
        "--host", DB_HOST,
        "--port", port,
        "--username", DB_USER,
        "--dbname", DB_NAME,
        "--format=plain",
        "--no-owner",
        "--no-acl",
    ]

    run_dump(command, output_file, env)

    print("PostgreSQL backup completed.")


# ---------------------------------------------------------
# MongoDB backup
# ---------------------------------------------------------

def backup_mongodb(output_file):
    port = DB_PORT or "27017"

    print("Creating MongoDB backup...")

    command = [
        "mongodump",
        "--host", DB_HOST,
        "--port", port,
        "--username", DB_USER,
        "--password", DB_PASSWORD,
        "--db", DB_NAME,
        "--archive=" + output_file,
    ]

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )

    except FileNotFoundError:
        raise RuntimeError(
            "mongodump was not found. "
            "Install MongoDB Database Tools."
        )

    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"MongoDB backup failed:\n{e.stderr}"
        )

    print("MongoDB backup completed.")


# ---------------------------------------------------------
# Generic dump runner
# ---------------------------------------------------------

def run_dump(command, output_file, env):
    try:
        with open(output_file, "wb") as output:
            subprocess.run(
                command,
                stdout=output,
                stderr=subprocess.PIPE,
                env=env,
                check=True,
            )

    except FileNotFoundError:
        raise RuntimeError(
            f"Backup command not found: {command[0]}"
        )

    except subprocess.CalledProcessError as e:
        error = e.stderr.decode(errors="replace")

        raise RuntimeError(
            f"Database backup failed:\n{error}"
        )


# ---------------------------------------------------------
# Gzip compression
# ---------------------------------------------------------

def compress_file(input_file, output_file):
    print("Compressing backup...")

    with open(input_file, "rb") as source:
        with gzip.open(output_file, "wb", compresslevel=6) as target:
            shutil.copyfileobj(source, target)

    print("Compression completed.")


# ---------------------------------------------------------
# Upload to S3
# ---------------------------------------------------------

def upload_to_s3(file_path, s3_key):
    print(f"Uploading to s3://{S3_BUCKET}/{s3_key}")

    s3 = boto3.client(
        "s3",
        region_name=AWS_REGION,
    )

    extra_args = {}

    if S3_ENCRYPTION:
        extra_args["ServerSideEncryption"] = S3_ENCRYPTION

    s3.upload_file(
        file_path,
        S3_BUCKET,
        s3_key,
        ExtraArgs=extra_args,
    )

    print("S3 upload completed.")


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():
    validate_config()

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d_%H-%M-%S"
    )

    if DB_TYPE == "mariadb":
        extension = "sql.gz"
        raw_extension = "sql"

    elif DB_TYPE == "postgres":
        extension = "sql.gz"
        raw_extension = "sql"

    elif DB_TYPE == "mongodb":
        extension = "archive.gz"
        raw_extension = "archive"

    filename = f"{DB_NAME}_{timestamp}.{extension}"

    s3_key = f"{S3_PREFIX}/{DB_TYPE}/{filename}"

    with tempfile.TemporaryDirectory() as temp_dir:

        raw_backup = os.path.join(
            temp_dir,
            f"backup.{raw_extension}"
        )

        compressed_backup = os.path.join(
            temp_dir,
            filename
        )

        # Create database backup
        if DB_TYPE == "mariadb":
            backup_mariadb(raw_backup)

        elif DB_TYPE == "postgres":
            backup_postgres(raw_backup)

        elif DB_TYPE == "mongodb":
            backup_mongodb(raw_backup)

        # Compress
        compress_file(
            raw_backup,
            compressed_backup
        )

        # Upload
        upload_to_s3(
            compressed_backup,
            s3_key
        )

    print()
    print("====================================")
    print("Backup completed successfully")
    print(f"Database : {DB_NAME}")
    print(f"Type     : {DB_TYPE}")
    print(f"S3       : s3://{S3_BUCKET}/{s3_key}")
    print("====================================")


if __name__ == "__main__":
    try:
        main()

    except Exception as e:
        print()
        print("BACKUP FAILED")
        print(str(e))
        raise
