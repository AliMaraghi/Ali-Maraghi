# Apex v4.4 — بستهٔ واقعی شب اول، حساب شخصی

این یک **نمونهٔ اولیهٔ صادقانه** است، نه ادعای ساخت ۱۸ عامل یا مانیفست کامل.

## خروجی واقعی
- Python/FastAPI با مرکز فرمان سادهٔ فارسی، پاسخ `/healthz` و `/api/status`.
- PostgreSQL و Redis در Docker؛ هیچ‌یک پورت عمومی ندارند.
- رصد RSS عمومی arXiv با فاصلهٔ ۶ ساعت و ثبت در Postgres (در صورت دسترسی واقعی اینترنت).
- نمایش آخرین موارد در آیفون به‌شکل وب‌اپ؛ دسترسی امن فقط از Tailscale Serve.
- **هیچ API هوش مصنوعی و هیچ خرج خودکار** فعال نیست.
- **هیچ دادهٔ شخصی یا حساب شرکتی** لازم نیست.

## گام‌های کار روی لپ‌تاپ شخصی ASUS
1. وارد حساب **شخصی** خود در Hetzner Cloud شو و سرور Ubuntu 24.04 با حداقل ۸ گیگ RAM انتخاب کن. SSH key شخصی را در زمان ساخت سرور اضافه کن. هرگز کلید خصوصی را ارسال نکن.
2. بسته را روی ASUS در پوشه‌ای که متعلق به خودت است از حالت ZIP خارج کن.
3. با Windows Terminal از طریق SSH به سرور وصل شو. آدرس IP را از Hetzner بگیر.
4. Docker Engine و Compose را از مستندات رسمی Docker نصب کن:
   https://docs.docker.com/engine/install/ubuntu/
5. روی ASUS از PowerShell بستهٔ استخراج‌شده را به سرور منتقل کن (برای نمونه از scp استفاده کن):
   `scp -i "$env:USERPROFILE\.ssh\apex_hetzner" -r "C:\Users\YOUR_NAME\Downloads\APEX_4_4_NIGHT1_PRIVATE_BOOTSTRAP" root@YOUR_SERVER_IP:/root/`
   حتماً نام کاربری ویندوز، مسیر فایل و IP را جایگزین کن.
6. در SSH سرور:
   ```bash
   cd /root/APEX_4_4_NIGHT1_PRIVATE_BOOTSTRAP
   cp .env.example .env
   python3 - <<'PY'
   from pathlib import Path
   import secrets
   p=Path('.env')
   t=p.read_text().replace('REPLACE_WITH_48_CHARACTER_RANDOM_SECRET',secrets.token_urlsafe(48))
   p.write_text(t)
   p.chmod(0o600)
   PY
   sudo docker compose up -d --build
   sudo docker compose ps
   curl http://127.0.0.1:8080/healthz
   ```
   انتظار: JSON با `status=ok` و `database=connected`.
7. نصب Tailscale روی سرور طبق راهنمای رسمی: https://tailscale.com/docs/install/linux
   به‌صورت نمونه: `curl -fsSL https://tailscale.com/install.sh | sh` سپس `sudo tailscale up`؛ لینک ورود را با حساب شخصی باز کن.
8. در پنل Tailscale برای حساب خود MagicDNS و HTTPS certificates را فعال کن. سپس روی سرور:
   `sudo tailscale serve --bg http://127.0.0.1:8080`
   از `tailscale serve status` آدرس HTTPS خصوصی `*.ts.net` را بخوان.
9. اپ Tailscale را از App Store آیفون نصب کن و با همان حساب وارد شو. آدرس HTTPS را در Safari باز کن و با Share → Add to Home Screen، Apex را روی صفحهٔ اصلی بگذار.
10. در داشبورد باید نشان دهد `هزینه AI: صفر دلار` و در صورت موفقیت RSS، خبرهای علمی عمومی را نمایش دهد. این نشان‌دهندهٔ **فعالیت واقعی شبانه‌روزی زیرساخت پایه** است، نه فعال‌بودن مانیفست کامل.

## ملاحظات امنیتی
- هرگز فایل `.env`، رمز VPS، کلید خصوصی SSH یا توکن را در چت ارسال نکن.
- `Tailscale Serve` را با `Funnel` اشتباه نگیر؛ Funnel برنامه را در اینترنت عمومی قرار می‌دهد.
- `docker compose` پورت API را فقط روی loopback 127.0.0.1 باز می‌کند؛ عمومی‌اش نکن.
- پشتیبان‌گیری خارج از سرور، بازیابی آزمایشی، نظارت و بروزرسانی ضروری‌اند؛ یک VPS منفرد آپ‌تایم صددرصد ندارد.
- اگر نمی‌خواهی امروز سرور بخری، فایل‌ها محفوظ‌اند و می‌توانی فقط آزمون محلی را اجرا کنی.
- برای داده‌های سلامت و مالی، این نسخه مناسب نیست؛ هنوز لایهٔ مجوزدهی حرفه‌ای و رمزنگاری داده‌های خصوصی کامل نیست.
- این مخزن **با کد ساخته‌شده در حساب AMD یکی نیست** و هیچ فایل کد سازمانی در آن قرار ندارد.

## ادامه در Codex
همین پوشه را با Codex باز کن. گام بعدی: سیستم تأیید اقدامات، مدیریت واقعی بودجهٔ API، تاریخچهٔ وضعیت، افزودن n8n ایمن و آزمون بکاپ/بازیابی. هیچ چیز را بدون بررسی و آزمون «تکمیل» ننام.

## آزمون مستقل (بدون Docker)
در یک محیط Python با کتابخانه‌های `fastapi`, `httpx`, `pytest`, `psycopg`:
`PYTHONPATH=core pytest -q tests`.

نسخه‌های Container در این کیت بر اساس tag معرفی شده‌اند؛ قبل از محیط Production باید از رجیستری معتبر digest آن‌ها را استخراج و قفل کنید. این نمونهٔ اولیهٔ عملیاتی-آزمایشی است.
