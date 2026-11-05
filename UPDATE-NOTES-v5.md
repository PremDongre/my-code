# UPDATE v5 - Responsive website + Locked test (anti-cheat)

## Kya naya hai

### 1) Poori website phone / tablet / laptop ke hisaab se
- Phone (360-430 px): menu burger me, sidebar ek scroll hone wali line, **tables cards ban jaati hain**, form/buttons bade, iPhone me input zoom nahi hota.
- Tablet (768 px) aur laptop (1366 px) aur bade desktop (1920 px) par normal wide layout.
- Maine **real Chromium** me 5 screen sizes x 52 pages (visitor, student, company, owner) check kiye: kisi page me side-scroll nahi, koi JS error nahi.

### 2) Test ke time student ko lock karna
Student flow:
1. **Rules page** (timer abhi start nahi): time, warnings, saare rules + "I agree" tick. Tick ke bina Start nahi hota.
2. **Start** dabate hi timer chalu. Test page **full screen** me khulta hai (pehle "Enter full screen" button).
3. Test ke dauran: menu/links gayab, copy / paste / right-click / Ctrl+C,V,P,S,U / F12 / back button **block**, text select band, screen par student ka naam+email halka watermark.
4. Agar student **doosra tab/app/window kholta hai, full screen se bahar aata hai, ya page refresh karta hai** -> turant **warning** (screen par "Warning 1 of 3"), company ko dikhta hai.
5. **3rd warning par test apne aap submit** (jo answers tab tak diye the unka score). Company har test me warning limit (1-10) khud set kar sakti hai.
6. Time khatam -> apne aap submit. Answers har 15 sec save hote hain (late submit me sirf time ke andar save hue answers ginte hain).

Company ko kya dikhta hai: Tests -> Results me **Warnings** column + "Auto-submitted" tag, aur Details me poora log (kab kya kiya: `tab_hidden`, `window_blur`, `fullscreen_exit`, `reload`, `blocked_*`).
Test banate waqt: **Anti-cheat mode** checkbox (default ON) aur **Auto-submit when warnings reach** (default 3).

### Sach baat (limits) - students/companies ko bata dena
- Koi bhi website browser ke **bahar ke app ya website ko block nahi kar sakti**. Ye system "rok" nahi, **pakadta hai, warning deta hai, record karta hai aur auto-submit karta hai.** Isiliye rules page par likha hai "allowed nahi hai + warning milegi".
- **Doosra phone / kitab / kisi aur se poochna / photo-screenshot** ye pakde nahi ja sakte (watermark sirf darr ke liye).
- **iPhone Safari** full screen support nahi karta: waha tab/app badalna phir bhi pakda jata hai.
- Bahut serious exams ke liye webcam proctoring ya Safe Exam Browser jaisa app alag se chahiye (agla step ho sakta hai).

### 3) Andar ke badlav
- Database me naye columns (`tests.strict`, `tests.max_violations`, `attempts.violations/blocked/loads/violation_log/draft/forced`) **app restart par apne aap jud jaate hain** (SQLite aur RDS MySQL dono me). Purana data safe.
- CSS/JS ke naam ke saath version (`style.css?v=...`) lagta hai, isliye Nginx ke 7-din cache ke baad bhi users ko naya design turant milta hai.

## Chalte hue servers ko update kaise karein
`BUCKET` = `connect-prem-1234` (apna bucket naam). **Session Manager** se connect karke.

**Step A - S3:** is zip ke **`1-WEB-TIER`** aur **`2-APP-TIER`** folder dobara upload karo (S3 -> bucket -> Upload -> Add folder -> same naam, replace). Tumhari `2-APP-TIER/app.env` file ko ye zip **nahi chhoota** (zip me sirf `app.env.example` hai).

**Step B - App Server** (aur agar Auto Scaling ke servers chal rahe hain to har ek par, ya neeche AMI wala step):
```
sudo -s
aws s3 cp s3://BUCKET/2-APP-TIER/ /opt/connect --recursive --exclude "app.env"
chown -R connect:connect /opt/connect
systemctl restart connect-app
curl http://localhost:8000/health        # ok
curl http://localhost:8000/health/db     # ok (is baar naye columns bhi ban jaate hain)
```
Check (optional): `mysql -h RDS-ENDPOINT -u admin -p -e "USE connect_db; SHOW COLUMNS FROM attempts;"` -> `violations`, `draft`, `forced` dikhne chahiye.

**Step C - Web Server** (agar bana liya hai; sirf CSS/JS/logo badle, Nginx restart nahi chahiye):
```
sudo -s
aws s3 cp s3://BUCKET/1-WEB-TIER/static/ /var/www/connect/static --recursive
chown -R nginx:nginx /var/www/connect
```
Agar abhi web server bana hi nahi, to bas DEPLOY-STEPS-3TIER-STYLE.md ke hisaab se banao - wo nayi files hi uthayega.

**Step D - Auto Scaling (AMI) bana chuke ho to:** naye servers purane AMI se aate hain. Updated App-Server/Web-Server se **naya AMI** banao -> `App-LT` / `Web-LT` ka **new version** (naya AMI) -> ASG -> **Instance refresh**.

**Step E - Test:** browser me `Ctrl + F5`. Company login -> Tests -> New test (Anti-cheat dikhega). Student login -> Tasks -> test kholo (rules page aana chahiye).

## Maine kya test kiya
- 5 screen sizes x 52 pages x 4 roles: no sideways scroll (real Chromium), screenshots dekhe.
- Real browser me poora test flow: rules page -> Start -> full screen -> copy/paste block -> 3 warnings -> auto-submit -> result + DB me log.
- Server tests (SQLite **aur MySQL**): rules page timer start nahi karta, warnings, auto-submit, late submit, time-over, strict off test, company ko log, purani database me naye columns ka automatic upgrade, S3 uploads, saari purani features.
- Asli AWS par abhi tak deploy nahi hua (tumhare servers par chalega, wahi commands pehle bhi chale hain).
