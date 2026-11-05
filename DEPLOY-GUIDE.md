# DEPLOY-GUIDE: Connect ko AWS par 3-tier me deploy karna (step by step)

> Region: upar right me **Asia Pacific (Mumbai) ap-south-1** chuno (India ke users ke liye fast).
> Diagram me us-east-1 hai - steps bilkul same hain, bas region alag. **Har step usi region me karna.**
> Time: pehli baar me ~2 ghante. Cost: neeche "Cost" section padho.

Naam jo hum use karenge (isi naam rakho, to guide aasan rahegi):

| Cheez | Naam |
|---|---|
| VPC | `connect-vpc` (CloudFormation banayega) |
| Key pair | `connect-key` |
| S3 bucket | `connect-<apnanaam>-<number>` (unique hona chahiye) |
| IAM roles | `connect-app-role`, `connect-web-role` |
| Database (RDS) | `connect-db` |
| Internal load balancer / target group | `connect-app-alb` / `connect-app-tg` |
| Public load balancer / target group | `connect-public-alb` / `connect-web-tg` |
| Launch templates | `connect-app-lt`, `connect-web-lt` |
| Auto Scaling groups | `connect-app-asg`, `connect-web-asg` |

---
## STEP 0 - Tayyari
1. AWS account me login karo, region **Mumbai** chuno.
2. **Key pair banao:** EC2 -> *Key Pairs* -> *Create key pair* -> name `connect-key`, type RSA, format `.pem` -> Create. File download hogi, sambhal ke rakho.
3. Apna public IP pata karo (Google: "what is my ip"), jaise `49.36.10.5`. Aage `49.36.10.5/32` likhna hoga.

---
## STEP 1 - Network banao (VPC, subnets, NAT, security groups)
Ye aapke diagram wala poora network ek click me banata hai.
1. Console -> **CloudFormation** -> *Create stack* -> *With new resources* -> **Upload a template file** -> `0-NETWORK-AND-IAM/connect-network.yml` -> Next.
2. Stack name: `connect-network`. Parameter **MyIpCidr** = `49.36.10.5/32` (apna IP). Next -> Next -> Submit.
3. 4-5 minute baad status **CREATE_COMPLETE**. *Outputs* tab me saari IDs dikhengi.

Ye ban gaya: VPC `10.0.0.0/16`, public subnets `10.0.0.0/20` & `10.0.16.0/20` (web), private app subnets `10.0.128.0/20` & `10.0.144.0/20`, private DB subnets `10.0.160.0/20` & `10.0.176.0/20`, Internet Gateway, NAT Gateway, `public-rtb`, `private-rtb`, aur security groups `bastion-sg`, `alb-public-sg`, `webserver-sg`, `alb-internal-sg`, `appserver-sg`, `database-sg`.

---
## STEP 2 - S3 bucket (code + resume/photo/certificate yahin rahenge)
1. Console -> **S3** -> *Create bucket* -> name `connect-apnanaam-123` (sab chhote letters, unique) -> region Mumbai.
2. **Block all public access = ON** (default hai, mat badalna). Default encryption = SSE-S3 (default). *Create bucket*.
3. Bucket kholo -> *Create folder* -> `deploy`.

---
## STEP 3 - IAM roles (servers ko S3 padhne/likhne ki permission)
1. IAM -> *Policies* -> *Create policy* -> **JSON** tab -> `0-NETWORK-AND-IAM/iam-policy-app-tier.json` ka content paste karo, `YOUR-BUCKET-NAME` ki jagah apna bucket naam likho -> name `connect-app-s3-policy` -> Create.
2. Wahi `iam-policy-web-tier.json` ke saath -> name `connect-web-s3-policy`.
3. IAM -> *Roles* -> *Create role* -> *AWS service* -> **EC2** -> policies attach karo: `connect-app-s3-policy` **aur** `AmazonSSMManagedInstanceCore` -> role name `connect-app-role` -> Create.
4. Dobara: `connect-web-s3-policy` + `AmazonSSMManagedInstanceCore` -> role name `connect-web-role`.

---
## STEP 4 - Database (RDS MySQL)
1. Console -> **RDS** -> *Create database* -> **Standard create** -> engine **MySQL** -> version **8.0.x**.
2. Template: *Dev/Test* (ya Free tier). DB instance identifier: `connect-db`.
3. Master username: `connect_app`. Master password: ek strong password (likh ke rakho - aage `app.env` me lagega).
4. Instance class: `db.t3.micro` (test) / `db.t3.small` ya bada (live). Storage: gp3, 20 GB.
5. **Connectivity:** VPC `connect-vpc`, DB subnet group `connect-db-subnet-group`, **Public access: No**, VPC security group: **`database-sg`** (default wala hata do).
6. *Additional configuration* kholo -> **Initial database name: `connect_db`**. Backup retention 7 days rehne do.
7. *Create database*. 8-10 minute me **Available** hoga. Database kholo -> **Endpoint** copy karo (jaise `connect-db.abcd1234.ap-south-1.rds.amazonaws.com`).

> Live/production ke liye "Multi-AZ (standby instance)" ON karna better hai (cost zyada).

---
## STEP 5 - Settings file (`app.env`) bharo aur S3 me upload karo
1. `2-APP-TIER/app.env.example` ko copy karke naam do **`app.env`** aur Notepad/VS Code me bharo:
   - `SECRET_KEY` = random lamba text. Banane ke liye laptop par: `python -c "import secrets;print(secrets.token_hex(32))"`
   - `DB_HOST` = RDS endpoint, `DB_USER` = `connect_app`, `DB_PASSWORD` = step 4 ka master password, `DB_NAME` = `connect_db`
   - `S3_BUCKET` = apna bucket naam, `AWS_REGION` = `ap-south-1`
   - `OWNER_EMAIL` / `OWNER_PASSWORD` = aapka (PremTech owner) login - pehli baar isi se owner account banega
   - `SEED_DEMO=0`, `PROXY_HOPS=3`, `COOKIE_SECURE=0` (HTTPS ke baad 1 karenge)
2. S3 bucket -> `deploy` folder -> **Upload** karo ye 3 files:
   - `ready-to-upload/app-tier.zip`
   - `ready-to-upload/web-tier.zip`
   - `app.env` (aapki bhari hui)

---
## STEP 6 - Bastion host (private servers me ghusne ka darwaza)
1. EC2 -> *Launch instance* -> name `connect-bastion` -> AMI **Amazon Linux 2023** -> type `t3.micro` -> key pair `connect-key`.
2. *Network settings* -> Edit: VPC `connect-vpc`, subnet **`connect-public-subnet-1`**, Auto-assign public IP **Enable**, security group: existing -> **`bastion-sg`**.
3. Launch. Instance ka **Public IPv4** note karo.

(Bina bastion ke bhi ja sakte ho: EC2 -> instance -> *Connect* -> **Session Manager**. Roles me SSM policy isi liye lagayi thi.)

---
## STEP 7 - Internal load balancer + APP TIER
**7A. Target group:** EC2 -> *Target Groups* -> *Create* -> type **Instances** -> name `connect-app-tg` -> HTTP, port **8000** -> VPC `connect-vpc` -> Health check path **`/health`** -> Next -> (koi instance register mat karo) -> Create.

**7B. Internal load balancer:** EC2 -> *Load Balancers* -> *Create* -> **Application Load Balancer**:
- name `connect-app-alb`, Scheme **Internal**
- VPC `connect-vpc`, subnets: **`connect-private-subnet-1-app`** aur **`connect-private-subnet-2-app`** (dono AZ)
- Security group: **`alb-internal-sg`** (default hata do)
- Listener **HTTP : 80** -> forward to `connect-app-tg`
- Create. Phir load balancer kholo -> **DNS name** copy karo (`internal-connect-app-alb-....elb.amazonaws.com`). **Ye Step 9 me chahiye.**

**7C. Launch Template (app):** EC2 -> *Launch Templates* -> *Create launch template*:
- name `connect-app-lt`, AMI **Amazon Linux 2023**, instance type `t3.small`, key pair `connect-key`
- Security groups: **`appserver-sg`** (subnet yahan mat chuno)
- *Advanced details* -> IAM instance profile: **`connect-app-role`**
- *Advanced details* -> **User data**: `2-APP-TIER/setup-app-tier.sh` ka poora content paste karo. Upar ki 2 lines edit karo: `S3_BUCKET` aur `AWS_REGION`.
- Create.

**7D. Auto Scaling group (app):** EC2 -> *Auto Scaling Groups* -> *Create*:
- name `connect-app-asg`, launch template `connect-app-lt` -> Next
- VPC `connect-vpc`, subnets: **`connect-private-subnet-1-app`** + **`connect-private-subnet-2-app`** -> Next
- *Attach to an existing load balancer* -> target group **`connect-app-tg`**; Health checks: **Turn on Elastic Load Balancing health checks** -> Next
- Desired **1**, Min **1**, Max **3**. Scaling policy: *Target tracking*, Average CPU **60** -> Next -> Create.

Server ko ~5 minute lagte hain (install hota hai). EC2 -> Target Groups -> `connect-app-tg` -> *Targets* -> status **healthy** hona chahiye.

---
## STEP 8 - Check karo ki App tier + Database sahi chal rahe hain (bastion se)
Laptop par `C:\Users\<aapka-naam>\.ssh\config` file banao (VS Code se) aur ye likho (IP badlo):
```
Host connect-bastion
  HostName <BASTION-PUBLIC-IP>
  User ec2-user
  IdentityFile C:\Users\<aapka-naam>\.ssh\connect-key.pem

Host connect-app
  HostName <APP-SERVER-PRIVATE-IP>
  User ec2-user
  IdentityFile C:\Users\<aapka-naam>\.ssh\connect-key.pem
  ProxyJump connect-bastion
```
(App server ka Private IP: EC2 -> Instances -> connect-app wala instance.)

Agar "UNPROTECTED PRIVATE KEY FILE" error aaye, PowerShell me:
```
icacls $env:USERPROFILE\.ssh\connect-key.pem /inheritance:r /grant:r "$($env:USERNAME):R"
```
Phir:
```
ssh connect-app
curl localhost:8000/health        # ok aana chahiye
curl localhost:8000/health/db     # ok aana chahiye (matlab database se connect ho gaya)
sudo systemctl status connect-app
sudo journalctl -u connect-app -n 50 --no-pager      # error ho to yahan dikhega
sudo tail -n 40 /var/log/cloud-init-output.log        # install ke logs
```
`/health/db` par error aaye to: `database-sg` me `appserver-sg` se port 3306 allowed hai? `app.env` me DB_HOST/DB_PASSWORD sahi hai? (Galti sudharni ho to Step 12 dekho.)

---
## STEP 9 - Public load balancer + WEB TIER
**9A. Target group:** EC2 -> *Target Groups* -> *Create* -> Instances -> `connect-web-tg` -> HTTP **80** -> VPC `connect-vpc` -> Health check path **`/nginx-health`** -> Next -> Create.

**9B. Public load balancer:** *Create load balancer* -> Application Load Balancer:
- name `connect-public-alb`, Scheme **Internet-facing**
- VPC `connect-vpc`, subnets: **`connect-public-subnet-1`** aur **`connect-public-subnet-2`**
- Security group: **`alb-public-sg`**
- Listener **HTTP : 80** -> forward to `connect-web-tg` -> Create. **DNS name** note karo.

**9C. Launch Template (web):** name `connect-web-lt`, AMI Amazon Linux 2023, `t3.micro`, key pair `connect-key`, security group **`webserver-sg`**, IAM instance profile **`connect-web-role`**, **User data** = `1-WEB-TIER/setup-web-tier.sh` ka content. Upar ki 3 lines edit karo:
`S3_BUCKET`, `AWS_REGION`, aur **`APP_ALB_DNS`** = Step 7B me copy kiya hua **internal** load balancer ka DNS name.

**9D. Auto Scaling group (web):** name `connect-web-asg`, template `connect-web-lt`, subnets: **`connect-public-subnet-1`** + **`connect-public-subnet-2`**, attach target group **`connect-web-tg`**, ELB health checks ON, Desired 1 / Min 1 / Max 3, CPU 60 target tracking -> Create.

~3 minute baad `connect-web-tg` me target **healthy** hona chahiye.

---
## STEP 10 - Website kholo
Browser me: `http://<connect-public-alb ka DNS name>` -> **Connect** ka home page (naya logo ke saath) dikhega.
- Owner login: `OWNER_EMAIL` aur `OWNER_PASSWORD` (jo `app.env` me daale the). Login ke baad **Settings -> Password** se password badal lo.
- Test: student account banao -> resume/photo upload karo (S3 me jaayega: S3 -> bucket -> `uploads/` folder me file dikhni chahiye).

---
## STEP 11 - Domain + HTTPS (premtech wala apna URL)
1. Domain khareedo (Route 53 ya GoDaddy/Namecheap). Route 53 me *Hosted zone* banao; doosre registrar se kharida ho to wahan nameservers Route 53 wale kar do.
2. **Certificate:** *AWS Certificate Manager* (same region Mumbai) -> *Request* -> Public certificate -> `yourdomain.com` aur `www.yourdomain.com` -> **DNS validation** -> *Create records in Route 53* -> thodi der me **Issued**.
3. EC2 -> Load Balancers -> `connect-public-alb` -> *Listeners* -> **Add listener**: HTTPS **443** -> forward to `connect-web-tg` -> Certificate: ACM wala. Phir HTTP:80 listener edit karo -> **Redirect to HTTPS (443)**.
4. Route 53 -> hosted zone -> *Create record* -> type **A** -> **Alias** -> *Alias to Application and Classic Load Balancer* -> Mumbai -> `connect-public-alb`. (`www` ke liye bhi.)
5. `https://yourdomain.com` khol ke dekho.
6. Ab `app.env` me **`COOKIE_SECURE=1`** karo, S3 `deploy/` me dobara upload karo, aur Step 12 ka "Instance refresh" (app ASG) chalao.

---
## STEP 12 - Baad me badlav karna ho to
- **Code / HTML / CSS badla:** folder ke andar ki saari files select karke naya zip banao (folder ko nahi, uske *andar ki files* ko) -> S3 `deploy/` me wahi naam (`app-tier.zip` ya `web-tier.zip`) se upload (overwrite).
- **`app.env` badla:** S3 me naya `app.env` upload karo.
- Phir EC2 -> *Auto Scaling Groups* -> `connect-app-asg` (ya web) -> **Instance refresh** tab -> *Start instance refresh* -> Minimum healthy **0%** (test) ya **50%** (2+ servers). Naye servers nayi files ke saath aa jaate hain.
- **Server ek hi bar test karna ho:** SSH karke `sudo systemctl restart connect-app`.

---
## Extra: database ke liye alag (kam permission wala) user - recommended
Abhi app RDS ka master user use kar raha hai. Zyada safe ke liye, jab sab chal jaye:
1. `ssh connect-app` karo aur ye chalao (`MASTERPASS` = RDS master password, `NEWPASS` = naye user ka naya password):
```
sudo bash -c 'DB_ADMIN_USER=connect_app DB_ADMIN_PASSWORD="MASTERPASS" DB_USER=connect_rw DB_PASSWORD="NEWPASS" /opt/connect/venv/bin/python /opt/connect/manage.py create-db-user --env /etc/connect.env'
```
   "OK: database ... and user 'connect_rw' are ready." aana chahiye.
2. Apne `app.env` me `DB_USER=connect_rw` aur `DB_PASSWORD=NEWPASS` karo, S3 `deploy/` me dobara upload karo.
3. `connect-app-asg` ka **Instance refresh** chalao (Step 12). Ye user sirf `connect_db` me kaam kar sakta hai.

---
## Problem aaye to (Troubleshooting)

| Dikkat | Kaaran / Solution |
|---|---|
| Browser me **502 / 503 Bad Gateway** | Web ya app target **unhealthy**. Target Groups me status dekho. Web server par `sudo tail -n 40 /var/log/nginx/error.log`; `APP_ALB_DNS` sahi hai? |
| `connect-app-tg` target **unhealthy** | App server par `curl localhost:8000/health`. Na chale to `sudo journalctl -u connect-app -n 50`. Aksar `app.env` me galti ya DB connect nahi ho raha |
| `/health/db` error | `database-sg` me `appserver-sg` se 3306 allowed? DB_HOST/DB_USER/DB_PASSWORD sahi? RDS status Available? |
| Server ne kuch install hi nahi kiya | `sudo tail -n 80 /var/log/cloud-init-output.log`. Aksar S3 bucket naam galat, ya IAM role attach nahi, ya zip `deploy/` me nahi |
| Private server se internet nahi (pip fail) | NAT Gateway chal raha hai? `private-rtb` me `0.0.0.0/0 -> NAT` hai? (CloudFormation ye bana deta hai) |
| Login ho ke wapas login page aa jata hai | HTTP par `COOKIE_SECURE=1` hai. HTTPS lagne tak `0` rakho |
| Resume/photo upload fail | `connect-app-role` me S3 policy hai? `S3_BUCKET` naam sahi? 5 MB se bada to nahi? |
| "Session expired" (400) baar-baar | Alag app servers par alag `SECRET_KEY`. Sab jagah `app.env` wahi ek hona chahiye |
| Site ka naya CSS nahi dikh raha | Browser me `Ctrl + F5`; web tier ka naya `web-tier.zip` upload + instance refresh |

---
## Cost (andaza - AWS rates badalte rehte hain)
Ye setup 24x7 chalu rakhoge to lagbhag **$90-130 / mahina (~Rs 8,000-11,000)** lag sakta hai: NAT Gateway, 2 load balancers, RDS, 2-3 EC2.
**Sirf practice kar rahe ho to kaam ke baad sab delete kar do.**

### Delete karne ka sahi order
1. Auto Scaling groups `connect-web-asg`, `connect-app-asg` delete (servers khud hat jaate hain)
2. Load balancers `connect-public-alb`, `connect-app-alb`, phir target groups
3. RDS `connect-db` (test ho to "final snapshot" na lo)
4. Bastion instance terminate
5. S3 bucket pehle *Empty*, phir *Delete*
6. CloudFormation stack `connect-network` delete (NAT Gateway, subnets sab hat jaate hain)
7. IAM roles/policies, Route 53 records, ACM certificate (agar chahiye na ho)
