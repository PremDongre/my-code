# 3-DATABASE-TIER  ->  AWS RDS (MySQL)

Is folder ki koi file kisi EC2 par nahi daalni. Database **AWS RDS MySQL** hota hai, aap use console me banate ho
(DEPLOY-GUIDE.md ka Step 4). Tables app khud bana leta hai jab pehli baar start hota hai.

| File | Kaam |
|---|---|
| `schema.sql` | Sirf dekhne ke liye: saari tables ka structure (MySQL). App ise khud chalata hai, aapko chalana zaroori nahi. |
| `create-app-user.sql` | Optional: sirf `connect_db` ke andar kaam karne wala alag DB user banane ki SQL. |

RDS settings jo aapko chunni hain: MySQL **8.0.x**, `db.t3.micro` (test) / `db.t3.small`+ (live), Public access **No**,
Security group **database-sg**, DB subnet group **connect-db-subnet-group**, Initial database name **connect_db**.
