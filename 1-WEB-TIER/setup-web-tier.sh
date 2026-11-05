#!/bin/bash
# =====================================================================
#  CONNECT - WEB TIER startup script
#  Paste this whole file in:  Launch Template -> Advanced details -> User data
#  Edit ONLY the 3 lines below.
# =====================================================================
S3_BUCKET="connect-yourname-uploads"
AWS_REGION="ap-south-1"
# DNS name of the INTERNAL load balancer (app tier), e.g. internal-connect-app-alb-123456789.ap-south-1.elb.amazonaws.com
APP_ALB_DNS="internal-connect-app-alb-xxxxxxxxx.ap-south-1.elb.amazonaws.com"
# =====================================================================
set -euxo pipefail

dnf install -y nginx unzip

aws s3 cp "s3://${S3_BUCKET}/deploy/web-tier.zip" /tmp/web-tier.zip --region "${AWS_REGION}"
rm -rf /tmp/web-tier && mkdir -p /tmp/web-tier
unzip -o /tmp/web-tier.zip -d /tmp/web-tier

mkdir -p /var/www/connect
rm -rf /var/www/connect/static
cp -r /tmp/web-tier/static /var/www/connect/static
chown -R nginx:nginx /var/www/connect

cp /tmp/web-tier/connect-proxy.conf /etc/nginx/connect-proxy.conf
sed "s|APP_ALB_DNS|${APP_ALB_DNS}|g" /tmp/web-tier/nginx.conf > /etc/nginx/nginx.conf

nginx -t
systemctl enable --now nginx
systemctl restart nginx
