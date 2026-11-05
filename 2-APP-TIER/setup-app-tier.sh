#!/bin/bash
# =====================================================================
#  CONNECT - APP TIER startup script
#  Paste this whole file in:  Launch Template -> Advanced details -> User data
#  Edit ONLY the 2 lines below.
# =====================================================================
S3_BUCKET="connect-yourname-uploads"
AWS_REGION="ap-south-1"
# =====================================================================
set -euxo pipefail

dnf install -y python3.11 python3.11-pip unzip || dnf install -y python3 python3-pip unzip
PY=$(command -v python3.11 || command -v python3)

id connect &>/dev/null || useradd --system --create-home --shell /sbin/nologin connect
mkdir -p /opt/connect

# code + settings come from your private S3 bucket (uploaded by you in the guide, Step 3)
aws s3 cp "s3://${S3_BUCKET}/deploy/app-tier.zip" /tmp/app-tier.zip --region "${AWS_REGION}"
aws s3 cp "s3://${S3_BUCKET}/deploy/app.env" /etc/connect.env --region "${AWS_REGION}"
chmod 600 /etc/connect.env
unzip -o /tmp/app-tier.zip -d /opt/connect

$PY -m venv /opt/connect/venv
/opt/connect/venv/bin/pip install --upgrade pip
/opt/connect/venv/bin/pip install -r /opt/connect/requirements.txt
chown -R connect:connect /opt/connect

cp /opt/connect/connect-app.service /etc/systemd/system/connect-app.service
systemctl daemon-reload
systemctl enable --now connect-app
