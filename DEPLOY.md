# رفع موقع WOLFX على سيرفر (من الصفر)

الخطة: **دومين + سيرفر VPS (Ubuntu) + nginx + gunicorn + HTTPS مجاني**.
كل الأوامر دي بتتكتب على **السيرفر** (إلا اللي مكتوب جنبه "على جهازك").

---

## 0) اللي تجهّزه
1. **دومين** (مثلًا wolfxacademy.com) من أي موقع بيبيع دومينات.
2. **سيرفر VPS** بنظام **Ubuntu 24.04**، بحد أدنى 1 GB رام (يفضّل 2 GB)، ومساحة 40 GB+ عشان الفيديوهات.
   - بعد الشراء هتاخد: **عنوان IP** + **باسورد root** (أو مفتاح SSH).
3. باسورد أدمن قوي + `SECRET_KEY` عشوائي (هنولّده تحت).

## 1) ادخل على السيرفر (على جهازك – PowerShell أو cmd)
```
ssh root@IP_السيرفر
```
اكتب `yes` أول مرة، وبعدها الباسورد.

## 2) حدّث السيرفر ونزّل البرامج
```
apt update && apt upgrade -y
apt install -y python3-venv nginx unzip sqlite3 rsync ufw certbot python3-certbot-nginx
```

## 3) ارفع المشروع
**على جهازك** (في فولدر الـzip):
```
scp wolfx-flask.zip root@IP_السيرفر:/root/
```
**على السيرفر:**
```
adduser --system --group --home /opt/wolfx wolfx
mkdir -p /var/lib/wolfx/uploads /etc/wolfx
unzip -q /root/wolfx-flask.zip -d /tmp/
cp -r /tmp/wolfx/. /opt/wolfx/
python3 -m venv /opt/wolfx/venv
/opt/wolfx/venv/bin/pip install -r /opt/wolfx/requirements.txt
```

## 4) الإعدادات والأسرار
```
cp /opt/wolfx/deploy/wolfx.env.example /etc/wolfx/wolfx.env
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
nano /etc/wolfx/wolfx.env
```
- الصق القيمة اللي طلعت مكان `SECRET_KEY`، واكتب باسورد الأدمن مكان `ADMIN_PASSWORD`.
- احفظ: `Ctrl+O` ثم Enter ثم `Ctrl+X`.
```
chown root:wolfx /etc/wolfx/wolfx.env && chmod 640 /etc/wolfx/wolfx.env
chown -R wolfx:wolfx /var/lib/wolfx /opt/wolfx
```
> لو الباسورد أو الـSECRET_KEY ضعيف، الموقع **هيرفض يشتغل** (ده مقصود).

## 5) شغّل الموقع كخدمة (بيشتغل لوحده بعد أي ريستارت)
```
cp /opt/wolfx/deploy/wolfx.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now wolfx
systemctl status wolfx
```
لازم تشوف `active (running)`. لو لأ: `journalctl -u wolfx -n 50` وابعتلي الناتج.

## 6) اربط الدومين
في لوحة الشركة اللي اشتريت منها الدومين، أضف **سجلين A**:
- الاسم `@` ← القيمة: IP السيرفر
- الاسم `www` ← القيمة: IP السيرفر

استنى من دقايق لساعات لحد ما ينتشر. للتأكد (على جهازك): `ping دومينك.com` ويظهر IP السيرفر.

## 7) nginx
```
cp /opt/wolfx/deploy/nginx-wolfx.conf /etc/nginx/sites-available/wolfx
sed -i 's/YOUR_DOMAIN/دومينك.com/g' /etc/nginx/sites-available/wolfx
ln -s /etc/nginx/sites-available/wolfx /etc/nginx/sites-enabled/wolfx
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```
(غيّر `دومينك.com` باسم دومينك الحقيقي، من غير www.)

## 8) HTTPS مجاني
```
certbot --nginx -d دومينك.com -d www.دومينك.com
```
اكتب إيميلك، ووافق على الشروط، واختار تحويل HTTP لـHTTPS. التجديد بيحصل تلقائيًا.

## 9) جدار الحماية
```
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw enable
```

## 10) نسخ احتياطي يومي
```
chmod +x /opt/wolfx/deploy/backup.sh
echo '0 3 * * * root /opt/wolfx/deploy/backup.sh' > /etc/cron.d/wolfx-backup
```
بيعمل نسخة من قاعدة البيانات والفيديوهات كل يوم 3 الفجر في `/var/backups/wolfx`.
> النسخ دي على **نفس السيرفر**. لو السيرفر اتمسح هتروح معاه، فنزّل نسخة على جهازك من وقت لوقت، أو فعّل Snapshots/Backups عند شركة الاستضافة.

## 11) اختبر
- `https://دومينك.com` يفتح، والبرامج والمدربين والمؤسسين يظهروا.
- سجّل بيانات تجريبية، وادخل `https://دومينك.com/admin` وشوفها، وامسح التجريبي.
- ارفع فيديو صغير Public وتأكد إنه بيشتغل.

## تحديث الموقع بعد كده
على جهازك: `scp wolfx-flask.zip root@IP:/root/` ثم على السيرفر:
```
unzip -qo /root/wolfx-flask.zip -d /tmp/
rsync -a --exclude venv --exclude uploads --exclude '*.db' /tmp/wolfx/ /opt/wolfx/
chown -R wolfx:wolfx /opt/wolfx
systemctl restart wolfx
```
البيانات والفيديوهات في `/var/lib/wolfx` فمش بتتأثر بالتحديث.

## مشاكل شائعة
- **502 Bad Gateway:** الخدمة واقفة. `systemctl status wolfx` و`journalctl -u wolfx -n 50`.
- **رفع فيديو بيفشل:** تأكد إن `client_max_body_size` في nginx أكبر من `MAX_UPLOAD_MB`.
- **الدومين مش بيفتح:** سجلات A لسه ما انتشرتش، أو IP غلط.
