#python version used: 3.12.3

import os
import sys
import tarfile
import subprocess
from datetime import datetime

import boto3
from dotenv import load_dotenv


# ============================================================
# Configuration
# ============================================================

# Load AWS credentials from .env
# load_dotenv("./.env")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))

JENKINS_HOME = "/var/lib/jenkins"
BACKUP_DIR = "/opt/jenkins-backup"
BUCKET_NAME = "rb-jenkins-backup"
AWS_REGION = os.getenv("AWS_DEFAULT_REGION")

# Directories that don't need to be included in the
# Jenkins disaster-recovery backup.
EXCLUDE_DIRS = {
    "workspace",
    ".npm",
    "caches",
    "tools",
}


# ============================================================
# Validation
# ============================================================

if not AWS_REGION:
    print("ERROR: AWS_DEFAULT_REGION is not set in .env")
    sys.exit(1)

if not os.path.isdir(JENKINS_HOME):
    print(f"ERROR: Jenkins home does not exist: {JENKINS_HOME}")
    sys.exit(1)

try:
    os.makedirs(BACKUP_DIR, exist_ok=True)
except OSError as e:
    print(f"ERROR: Cannot create backup directory: {e}")
    sys.exit(1)


# ============================================================
# Backup filename
# ============================================================

date = datetime.now().strftime("%Y-%m-%d")

backup_file = os.path.join(
    BACKUP_DIR,
    f"jenkins-{date}.tar.gz"
)


# ============================================================
# Tar filter
# ============================================================

def tar_filter(tarinfo):
    """
    Exclude unnecessary Jenkins directories from the backup.

    Examples:
        jenkins/workspace/...
        jenkins/.npm/...
        jenkins/caches/...
        jenkins/tools/...
    """

    parts = tarinfo.name.split("/")

    if len(parts) > 1 and parts[1] in EXCLUDE_DIRS:
        return None

    return tarinfo


# ============================================================
# Stop Jenkins
# ============================================================

jenkins_stopped = False

try:
    print("Stopping Jenkins...")

    subprocess.run(
        ["systemctl", "stop", "jenkins"],
        check=True
    )

    jenkins_stopped = True

    print("Jenkins stopped successfully.")

except subprocess.CalledProcessError as e:
    print(f"ERROR: Failed to stop Jenkins: {e}")
    sys.exit(1)

except Exception as e:
    print(f"ERROR: Unexpected error while stopping Jenkins: {e}")
    sys.exit(1)


# ============================================================
# Create Backup
# ============================================================

backup_success = False

try:
    print("Creating Jenkins backup...")
    print(f"Source: {JENKINS_HOME}")
    print(f"Destination: {backup_file}")

    print("Excluded directories:")
    for directory in sorted(EXCLUDE_DIRS):
        print(f"  - {directory}")

    with tarfile.open(backup_file, "w:gz") as tar:
        tar.add(
            JENKINS_HOME,
            arcname="jenkins",
            filter=tar_filter
        )

    backup_success = True

    print("Backup created successfully.")

except (tarfile.TarError, OSError) as e:
    print(f"ERROR: Failed to create backup: {e}")

except Exception as e:
    print(f"ERROR: Unexpected error while creating backup: {e}")

finally:
    # ========================================================
    # Always start Jenkins again
    # ========================================================

    if jenkins_stopped:
        try:
            print("Starting Jenkins...")

            subprocess.run(
                ["systemctl", "start", "jenkins"],
                check=True
            )

            print("Jenkins started successfully.")

        except subprocess.CalledProcessError as e:
            print(
                f"CRITICAL ERROR: Failed to start Jenkins: {e}"
            )
            sys.exit(1)

        except Exception as e:
            print(
                "CRITICAL ERROR: Unexpected error while "
                f"starting Jenkins: {e}"
            )
            sys.exit(1)


# ============================================================
# Check backup result
# ============================================================

if not backup_success:
    print("Backup failed.")

    # Remove incomplete backup
    if os.path.exists(backup_file):
        try:
            os.remove(backup_file)
            print("Incomplete backup file removed.")
        except OSError as e:
            print(
                f"WARNING: Could not remove incomplete backup: {e}"
            )

    sys.exit(1)


# ============================================================
# Verify backup file
# ============================================================

if not os.path.isfile(backup_file):
    print("ERROR: Backup file was not created.")
    sys.exit(1)

backup_size = os.path.getsize(backup_file)

if backup_size == 0:
    print("ERROR: Backup file is empty.")
    sys.exit(1)

backup_size_mb = backup_size / (1024 * 1024)

print(f"Backup size: {backup_size_mb:.2f} MB")


# ============================================================
# Upload to S3
# ============================================================

try:
    print("Uploading backup to S3...")

    s3 = boto3.client(
        "s3",
        region_name=AWS_REGION
    )

    s3_key = (
        f"jenkins-backups/{os.path.basename(backup_file)}"
    )

    s3.upload_file(
        backup_file,
        BUCKET_NAME,
        s3_key
    )

    print("Backup uploaded successfully.")
    print(f"S3 location: s3://{BUCKET_NAME}/{s3_key}")

except Exception as e:
    print(f"ERROR: Failed to upload backup to S3: {e}")

    # Keep the local backup so it can be uploaded again.
    print(
        f"Local backup is still available at: {backup_file}"
    )

    sys.exit(1)


# ============================================================
# Success
# ============================================================

print()
print("==============================================")
print("Jenkins backup completed successfully.")
print(f"Local backup : {backup_file}")
print(f"Backup size  : {backup_size_mb:.2f} MB")
print(f"S3 bucket    : {BUCKET_NAME}")
print(f"S3 key       : {s3_key}")
print("==============================================")

sys.exit(0)