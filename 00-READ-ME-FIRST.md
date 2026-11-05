# Connect - AWS 3-Tier package  (PremTech)

> **NAYA (v5):** responsive website + test ke time anti-cheat lock. Chalte servers ko update karne ke commands: **UPDATE-NOTES-v5.md**

Is zip me website ko aapke diagram jaisi **3-tier architecture** me AWS par chalane ki sab files hain.

## Kaun si folder kahan jaati hai

| Folder | Kahan jaata hai (AWS me) | Kya hai |
|---|---|---|
| **0-NETWORK-AND-IAM** | CloudFormation + IAM | VPC, 6 subnets, NAT, route tables, security groups ka template + IAM policies |
| **1-WEB-TIER** | **Web-tier EC2** (public subnets, Auto Scaling) | Nginx + CSS/JS/logo. Internet se aayi request yahan aati hai |
| **2-APP-TIER** | **App-tier EC2** (private subnets, Auto Scaling) | Poora Flask application (Python + HTML templates) |
| **3-DATABASE-TIER** | **RDS MySQL** (private DB subnets) | Sirf reference: schema. Tables app khud bana leta hai |
| **ready-to-upload** | **S3 bucket -> `deploy/` folder** | `app-tier.zip` aur `web-tier.zip` (servers inhe S3 se khud download karte hain) |

## Traffic ka raasta (aapke diagram jaisa)

```
User ──▶ Internet Gateway ──▶ PUBLIC Load Balancer ──▶ WEB TIER (Nginx, public subnet 1 & 2)
                                                           │
                                                           ▼
                                        INTERNAL Load Balancer ──▶ APP TIER (Flask, private subnet 1 & 2)
                                                                       │            │
                                                                       ▼            ▼
                                                              RDS MySQL (DB tier)   S3 (resume/photo/certificate)
 Bastion host (public subnet) ── SSH ──▶ private servers          NAT Gateway: private servers ka internet (updates)
```

## Do guide hain - koi ek follow karo
- **DEPLOY-STEPS-3TIER-STYLE.md**  -> aapke trainer wali file jaisa (VPC wizard, SSM, S3 me **folders** upload, manual server setup, AMI, ASG). **Pehli baar ke liye yahi best.** (zip use nahi hota)
- **DEPLOY-GUIDE.md** -> CloudFormation + bastion + user-data wala tareeka (isme `ready-to-upload` ke 2 zip S3 `deploy/` me jaate hain).

## Ek nazar me kya karna hai (poora detail guide me)
1. CloudFormation se network banao (0-NETWORK-AND-IAM/connect-network.yml)
2. S3 bucket banao + IAM roles banao
3. RDS MySQL banao
4. `app.env` bharo, aur `ready-to-upload` ki 2 zip + `app.env` S3 ke `deploy/` me upload karo
5. Internal load balancer + **App tier** (Launch Template + Auto Scaling) banao
6. Public load balancer + **Web tier** (Launch Template + Auto Scaling) banao
7. Browser me load balancer ka address kholo -> website live. Phir domain + HTTPS lagao.

> Laptop par pehle test karna ho to `2-APP-TIER/README-APP-TIER.md` dekho (AWS ke bina chalta hai).
