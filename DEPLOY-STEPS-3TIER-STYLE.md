# Connect - 3-Tier Deployment Steps  (aapke trainer wali file ke style me)

Aapki file ka flow: VPC -> Security Groups -> S3 -> IAM Role (SSM) -> RDS -> App Server + Internal ALB -> Web Server + External ALB
-> ACM/HTTPS -> Route53 -> AMI -> Launch Template -> Auto Scaling. **Yahan bilkul wahi order hai.** Bas Node.js ki jagah hamari Python (Flask) app hai.

## Trainer ki file vs Connect (kya alag hai)

| Trainer ki 3-tier app | Connect (hamari app) |
|---|---|
| App tier = Node.js + PM2, port **4000** | App tier = **Python Flask + gunicorn**, port **8000** |
| Web tier = React `npm run build` + Nginx | Web tier = **Nginx** (static files + proxy). Koi build nahi |
| Credentials `DbConfig.js` me, S3 par wapas upload | Credentials **`app.env`** me, S3 par upload |
| `nginx.conf` me internal ALB DNS badalna | **Wahi**: `nginx.conf` me `APP_ALB_DNS` badalna |
| Health check `/health` | **Wahi**: `/health` (app) aur `/nginx-health` (web) |
| `CREATE DATABASE` + tables `mysql` me haath se | **Database `connect_db` haath se banate hain** (trainer jaisa, app server se). **Tables app khud banata hai** |
| `install.sh` S3 me | **Folders** `1-WEB-TIER` aur `2-APP-TIER` (zip nahi) + `app.env` |

> Region: **Mumbai (ap-south-1)** hi rakho. Trainer ke example password/endpoint (`admin / root123456`) **mat copy karna** - apna strong password banao.

---
## STEP 1 - VPC banao  (VPC and more)
VPC -> *Create VPC* -> **VPC and more**
- Name tag auto-generate: `connect`
- IPv4 CIDR: `192.168.0.0/16`, Tenancy Default
- Number of AZs: **2**
- Public subnets: **2**, Private subnets: **4**
- NAT gateways: **In 1 AZ** (Zonal)
- VPC endpoints: **None**
- *Create VPC*

Phir VPC -> Subnets -> 4 private subnets ke naam badlo (diagram ke hisaab se):
`private1` -> **APP1**, `private2` -> **APP2**, `private3` -> **DB1**, `private4` -> **DB2**. Public wale: **Public1**, **Public2**.

## STEP 2 - Security Groups (5)
Sab `connect-vpc` me. Source me security group chuno (ya trainer ki tarah `192.168.0.0/16`, jo testing me aasan hai par kam safe).

| Naam | Inbound |
|---|---|
| **WebALB-SG** | HTTP 80 aur HTTPS 443 from `0.0.0.0/0` |
| **Web-SG** | HTTP 80 from `WebALB-SG` |
| **AppALB-SG** | HTTP 80 from `Web-SG` |
| **App-SG** | **Custom TCP 8000** from `AppALB-SG`  (trainer ke Node app me 4000 tha, hamare me 8000) |
| **Database-SG** | MySQL/Aurora **3306** from `App-SG` |

## STEP 3 - S3 private bucket (code ke liye)
Trainer ki tarah **folders** upload honge (zip nahi).
1. S3 -> *Create bucket* -> name `connect-apnanaam-123` -> Mumbai -> Block all public access **ON**.
2. Zip extract karo. Bucket kholo -> *Upload* -> *Add folder*: **`1-WEB-TIER`** aur **`2-APP-TIER`** (dono folder poore). Upload.
3. **2 jagah code me badlav** (trainer ki file jaisa):
   - **App tier - `app.env`**: RDS ki details (Step 5 ke baad) bharke **`2-APP-TIER` folder ke andar** upload karo -> S3 me `2-APP-TIER/app.env` banega.
   - **Web tier - `nginx.conf`**: internal ALB ka DNS (Step 6 ke baad). Hum server par `sed` se badlenge, S3 me badalna zaroori nahi.

Bucket sahi bhara hai ya nahi, ye kisi bhi server se check kar sakte ho:
```
aws s3 ls s3://BUCKET/ 
aws s3 ls s3://BUCKET/2-APP-TIER/
```
Dikhna chahiye: `app.py`, `requirements.txt`, `connect-app.service`, `manage.py`, `app.env`, aur folders `static/`, `templates/`.

## STEP 4 - IAM Role (SSM se private server me connect)
Bastion ki jagah **Session Manager** use karenge (trainer jaisa).
1. IAM -> Policies -> Create policy -> JSON -> `0-NETWORK-AND-IAM/iam-policy-app-tier.json` paste (bucket naam badlo) -> name `connect-s3-policy`.
2. IAM -> Roles -> Create role -> Trusted entity **AWS service = EC2** -> permissions: **`AmazonSSMManagedInstanceCore`** + **`connect-s3-policy`** -> name **`connect-3tier-role`**.
   (Trainer demo me Admin lagata hai; hum sirf zaroori permission dete hain.)

## STEP 5 - RDS MySQL
1. RDS -> *Subnet groups* -> Create: name `connect-subnet-group`, VPC `connect-vpc`, AZ 1a + 1b, subnets **DB1 aur DB2**.
2. *Create database* -> Standard -> **MySQL 8.0.x** -> Dev/Test
   - DB identifier: `connect-db`
   - Master username: `admin`, password: **apna strong password** (likh ke rakho)
   - Instance: `db.t3.micro` (test)
   - VPC `connect-vpc`, DB subnet group `connect-subnet-group`, **Public access = No**, Security group **Database-SG**
   - **Initial database name: khaali chhodo** (database hum App Server se banayenge - trainer jaisa)
   - Backups: practice me OFF, live me 7 days ON. Encryption: Yes.
3. Available hone par **Endpoint** copy karo: `connect-db.xxxxxxxx.ap-south-1.rds.amazonaws.com`.

Ab laptop par `app.env` bharo (`2-APP-TIER/app.env.example` ko copy karke naam `app.env`):
```
SECRET_KEY=<python -c "import secrets;print(secrets.token_hex(32))" ka output>
DB_HOST=<RDS endpoint>
DB_PORT=3306
DB_NAME=connect_db
DB_USER=admin
DB_PASSWORD=<aapka RDS password>
S3_BUCKET=<aapka bucket naam>
AWS_REGION=ap-south-1
OWNER_EMAIL=<aapka email>
OWNER_PASSWORD=<aapka strong password>
SEED_DEMO=0
APP_ENV=production
PROXY_HOPS=3
COOKIE_SECURE=0
```
(`=` ke aas-paas space nahi, quotes nahi, aur `#` wali comment line sirf alag line me.)
-> S3 me **`2-APP-TIER/app.env`** upload karo.

## STEP 6 - App Server + Internal Load Balancer
**6A. Instance:** EC2 -> Launch -> name `App-Server`, **Amazon Linux 2023**, `t3.small` (t3.micro bhi chalega), key pair: *Proceed without* (SSM use hoga)
- Network: VPC `connect-vpc`, Subnet **APP1**, Auto-assign public IP **Disable**, Security group **App-SG**
- Advanced -> IAM instance profile: **`connect-3tier-role`**

**6B. Connect:** EC2 -> instance select -> *Connect* -> **Session Manager** -> Connect. (Na dikhe to 2-3 min ruko; role aur NAT check karo.)

**6C. Application setup** (Session Manager ke terminal me. `BUCKET` = apna bucket naam, `RDS-ENDPOINT` = Step 5 ka endpoint)

*(a) Tools install:*
```
sudo -s
cd /home/ec2-user
dnf install -y python3.11 python3.11-pip mariadb105
```
*(b) Database banao* (trainer ki file jaisa, mysql client se):
```
mysql -h RDS-ENDPOINT -u admin -p
```
Password type karo (screen par dikhega nahi), phir mysql me:
```
CREATE DATABASE connect_db CHARACTER SET utf8mb4;
SHOW DATABASES;
exit
```
`connect_db` list me dikhna chahiye. (Tables mat banao - app khud bana leta hai.)

*(c) Code S3 se laao:*
```
mkdir -p /opt/connect
aws s3 cp s3://BUCKET/2-APP-TIER/ /opt/connect --recursive
aws s3 cp s3://BUCKET/2-APP-TIER/app.env /etc/connect.env
chmod 600 /etc/connect.env
rm -f /opt/connect/app.env
ls /opt/connect
```
`ls` me ye dikhna chahiye: `app.py  connect-app.service  manage.py  requirements.txt  static  templates  uploads ...`
**Agar `app.py` nahi dikha, to aage mat badho** - S3 path galat hai (`aws s3 ls s3://BUCKET/2-APP-TIER/` se dekho).

Settings file ek baar check kar lo:
```
cat /etc/connect.env
```
`DB_HOST` = RDS endpoint, `DB_NAME=connect_db`, `DB_USER=admin`, `S3_BUCKET` sahi, koi extra space ya quote nahi.

*(d) Python libraries + user + service:*
```
python3.11 -m venv /opt/connect/venv
/opt/connect/venv/bin/pip install -r /opt/connect/requirements.txt

id connect || useradd --system --create-home --shell /sbin/nologin connect
chown -R connect:connect /opt/connect

cp /opt/connect/connect-app.service /etc/systemd/system/connect-app.service
systemctl daemon-reload
systemctl enable --now connect-app
```
**6D. Check** (trainer ka `curl .../health` wala step):
```
systemctl status connect-app --no-pager
curl http://localhost:8000/health         # ok
curl http://localhost:8000/health/db      # ok  (database se connect ho gaya)
journalctl -u connect-app -n 50 --no-pager   # error ho to yahan dikhega
```
Tables dekhne ho to: `mysql -h RDS-ENDPOINT -u admin -p -e "USE connect_db; SHOW TABLES;"`  (users, internships, courses ... dikhenge)

| `/health/db` ka jawab | Matlab |
|---|---|
| `ok` | Sab theek |
| error + log me `Unknown database` | `connect_db` banana bhool gaye -> (b) karo, phir `systemctl restart connect-app` |
| log me `Access denied` | `app.env` me `DB_USER` / `DB_PASSWORD` galat |
| log me `timed out` / `Can't connect` | `Database-SG` me `App-SG` se 3306 allowed nahi, ya `DB_HOST` galat |

**6E. Target Group:** EC2 -> Target Groups -> Create: Instances, name **`App-TG`**, HTTP **8000**, VPC `connect-vpc`, Health check path **`/health`** -> `App-Server` select -> *Include as pending below* -> Create.

**6F. Internal ALB:** Load Balancers -> Create -> Application LB
- name `app-internal-alb`, Scheme **Internal**, VPC `connect-vpc`
- AZ 1a = **APP1**, AZ 1b = **APP2**
- Security group **AppALB-SG**
- Listener HTTP **80** -> forward to `App-TG` -> Create
- Ban jaye to **DNS name** copy karo: `internal-app-internal-alb-xxxxxxx.ap-south-1.elb.amazonaws.com`

## STEP 7 - Web Server + External Load Balancer
**7A. Instance:** `Web-Server`, Amazon Linux 2023, `t3.micro`, Subnet **Public1**, Auto-assign public IP **Enable**, Security group **Web-SG**, IAM profile **`connect-3tier-role`**.

**7B. Session Manager me connect karke** (`BUCKET` = bucket naam, `INTERNAL-ALB-DNS` = Step 6F ka DNS, **bina `http://` ke**, jaise `internal-app-internal-alb-123456.ap-south-1.elb.amazonaws.com`):
```
sudo -s
cd /home/ec2-user

dnf install -y nginx

aws s3 cp s3://BUCKET/1-WEB-TIER/ /tmp/web-tier --recursive
ls /tmp/web-tier           # nginx.conf  connect-proxy.conf  static  ... dikhna chahiye

# CSS / JS / logo
mkdir -p /var/www/connect
cp -r /tmp/web-tier/static /var/www/connect/static
chown -R nginx:nginx /var/www/connect

# nginx config: internal ALB DNS bharo (trainer wala "nginx.conf update" step)
sed -i "s|APP_ALB_DNS|INTERNAL-ALB-DNS|g" /tmp/web-tier/nginx.conf
cp /tmp/web-tier/connect-proxy.conf /etc/nginx/connect-proxy.conf
cp /tmp/web-tier/nginx.conf /etc/nginx/nginx.conf     # default file ki jagah humari

nginx -t                                   # "syntax is ok" aur "test is successful"
systemctl enable --now nginx
systemctl restart nginx

curl http://localhost/nginx-health         # ok
curl -I http://localhost/                  # HTTP/1.1 200  (page app tier se aa raha hai)
```
Agar `curl -I` 502 de: `App-TG` healthy hai? `AppALB-SG` me `Web-SG` se port 80 allowed hai? `nginx.conf` me DNS sahi hai? (`grep set /etc/nginx/nginx.conf`)

**7C. Target Group:** `Web-TG`, HTTP **80**, Health check path **`/nginx-health`** (trainer ne `/` rakha tha, ye bhi chalega) -> `Web-Server` select -> Create.

**7D. External ALB:** name `app-external-alb`, Scheme **Internet-facing**, AZ 1a = **Public1**, AZ 1b = **Public2**, SG **WebALB-SG**, listener HTTP 80 -> `Web-TG`.

**7E. Test:** `http://<app-external-alb ka DNS name>` browser me kholo -> Connect ka home page (naya logo ke saath) aana chahiye. Owner login: `OWNER_EMAIL` / `OWNER_PASSWORD` (app.env wale).

## STEP 8 - HTTPS (ACM) + Route 53
1. **ACM** (Mumbai region) -> Request public certificate -> `yourdomain.com` aur `www.yourdomain.com` -> DNS validation -> (Route 53 me) *Create records* -> **Issued**.
2. `app-external-alb` -> Listeners and rules -> **Add listener** -> HTTPS **443** -> forward `Web-TG` -> certificate: ACM wala. Phir HTTP:80 listener -> **Redirect to HTTPS**.
3. **Route 53** -> Hosted zone -> Create record -> **A** -> Alias -> *Application and Classic Load Balancer* -> Mumbai -> `app-external-alb` (`www` ke liye bhi).
4. `https://yourdomain.com` kholo.
5. **Zaroori:** HTTPS chalne ke baad `app.env` me `COOKIE_SECURE=1` karo, S3 me `2-APP-TIER/app.env` par upload, aur App-Server me:
```
sudo -s
aws s3 cp s3://BUCKET/2-APP-TIER/app.env /etc/connect.env
chmod 600 /etc/connect.env
systemctl restart connect-app
```
(Auto Scaling ke baad ye AMI me bake hota hai - isliye ye step **AMI banane se pehle** kar lo.)

## STEP 9 - Auto Scaling (AMI -> Launch Template -> ASG)
Pehle dono servers theek chal rahe ho, tabhi AMI banao.

**9A. App tier**
1. EC2 -> `App-Server` select -> Actions -> Image and templates -> **Create image** -> name `Connect-App-AMI` -> Create. (*AMIs* me **Available** hone tak ruko.)
2. Launch Templates -> Create: name **`App-LT`**, AMI: *My AMIs* -> `Connect-App-AMI`, type `t3.small`, key pair: Don't include, **Subnet: don't include**, SG **App-SG**, Advanced -> IAM profile **`connect-3tier-role`**.
3. Auto Scaling Groups -> Create: name **`App-ASG`**, template `App-LT`, VPC `connect-vpc`, subnets **APP1 + APP2**, *Attach to an existing load balancer* -> target group **`App-TG`**, ELB health checks ON, Desired **2** / Min **2** / Max **4** (trainer: 4/2/6; practice me 1/1/2 rakho to cost kam), Target tracking **Average CPU 70%** -> Create.

**9B. Web tier**
1. `Web-Server` -> Create image -> **`Connect-Web-AMI`**.
2. Launch Template **`Web-LT`**: AMI `Connect-Web-AMI`, `t3.micro`, SG **Web-SG**, IAM profile `connect-3tier-role`, subnet: don't include. (Public IP chahiye: ASG subnets me *auto-assign public IP* ON hona chahiye - VPC wizard ke public subnets me default ON hota hai; na ho to Launch Template -> Network interface -> Auto-assign public IP = Enable.)
3. ASG **`Web-ASG`**: template `Web-LT`, subnets **Public1 + Public2**, attach target group **`Web-TG`**, ELB health ON, Desired 2 / Min 2 / Max 4, CPU 70% -> Create.

**9C. Safai:** jab ASG ke naye servers target groups me **healthy** ho jayen, purane manual `App-Server` aur `Web-Server` ko target group se *Deregister* karke **Terminate** kar do (warna extra cost).

## STEP 10 (optional, baad me) - CloudFront
CloudFront distribution -> Origin = `app-external-alb` (HTTPS). Default behaviour me **CachingDisabled** + cookies/headers forward (login, CSRF ke liye), aur sirf `/static/*` ke liye caching ON.

---
## Baad me code badalna ho to (jaise home page ka text)
1. Laptop par file badlo (jaise `2-APP-TIER/templates/index.html`) -> S3 me **usi folder me wahi file upload (replace)**.
2. Chalte hue App-Server par:
```
sudo -s
aws s3 cp s3://BUCKET/2-APP-TIER/ /opt/connect --recursive --exclude "app.env"
chown -R connect:connect /opt/connect
systemctl restart connect-app
```
(CSS/JS/logo badle ho to Web-Server par: `aws s3 cp s3://BUCKET/1-WEB-TIER/static/ /var/www/connect/static --recursive` aur `chown -R nginx:nginx /var/www/connect`.)
3. Auto Scaling ke baad: naye servers purane AMI se aate hain, isliye naya **AMI** banao -> `App-LT` ka **new version** -> `App-ASG` -> *Instance refresh*.

## Troubleshooting
| Dikkat | Check |
|---|---|
| Session Manager me instance nahi dikhta | Role me `AmazonSSMManagedInstanceCore`? Private server ka NAT route? 2-3 min ruko |
| `unzip` / `.zip` / `deploy/` wali file nahi milti | Is guide me zip nahi hai. Code S3 ke **folders** `1-WEB-TIER` / `2-APP-TIER` se `aws s3 cp ... --recursive` se aata hai |
| `curl localhost:8000/health` nahi chalta | `journalctl -u connect-app -n 50` ; `/etc/connect.env` me galti ; `connect_db` bana hai? |
| `/health/db` error | Database-SG me App-SG se 3306? DB_HOST/DB_PASSWORD sahi? RDS Available? |
| Browser me 502/504 | Dono target groups healthy? `nginx.conf` me internal ALB DNS sahi? `tail /var/log/nginx/error.log` |
| Login ke baad wapas login page | HTTP par `COOKIE_SECURE=1` hai -> HTTPS tak `0` |
| Resume/photo upload fail | Role me S3 policy? `S3_BUCKET` sahi? file 5 MB se chhoti? |
