# 1-WEB-TIER  ->  Web-tier EC2 (public subnets)

Yahan **Nginx** hai. Ye internet se aane wali request leta hai, CSS/JS/logo seedha khud deta hai, aur baaki sab kuch
**internal load balancer -> app tier** ko bhej deta hai.

| File / folder | Kaam |
|---|---|
| `nginx.conf` | Nginx ki settings (`APP_ALB_DNS` ki jagah script aapka internal load balancer address bhar deti hai) |
| `connect-proxy.conf` | Proxy headers (asli IP, https wagairah app tak pahunchane ke liye) |
| `static/` | CSS, JavaScript, logo, favicon |
| `setup-web-tier.sh` | Launch Template ke **User data** me paste hone wali script |

Is server par database ya Python nahi chalta - sirf Nginx.
