# Companion Presence Addendum (received 2026-11-13)

Status as delivered by the owner: **SPECIFICATION_READY**. Avatar likeness, voice
adaptation, sensor/context awareness and the unified dashboard are explicitly
**NOT_IMPLEMENTED_BY_THIS_DOCUMENT** - nothing here was built, deployed, recorded
or paid for by receiving this file. No existing founder/manifesto/addendum file
was edited to produce this record.

This file preserves the owner's addendum text verbatim (Persian product spec +
English execution addendum + source list) exactly as pasted, for reference when
scoping and implementing pieces of it. See `docs/apex_status/NEXT_ACTION.md` for
what is actually in progress.

---

## ضمیمهٔ تکمیلی APEX — حضور سه‌بعدی، همراه شخصی و داشبورد یکپارچه

تاریخ: ۱۳ نوامبر ۲۰۲۶ — Europe/London

نوع سند: مشخصات محصول و دستور اجرایی مکمل برای Claude Code. این سند قابلیت نصب‌شده یا آواتار ساخته‌شده را گزارش نمی‌کند.

این ضمیمه بعد از پرامپت فعلی و MASTER_PROMPT_ADDENDUM.md خوانده می‌شود. متن، شماره‌گذاری و مفاد قبلی را جایگزین یا حذف نمی‌کند. گزارش پنج جزء عملیاتی و معماری چهارلایهٔ شناختی هر دو حفظ می‌شوند. این قابلیت، تجربهٔ تعامل با همان هسته است؛ دفترکل، شخصیت اجرایی مستقل یا زمان‌بند جدید نیست.

نسخهٔ پایهٔ خوانده‌شده: MASTER_PROMPT_ADDENDUM.md، به اندازهٔ 20,323 بایت؛ SHA-256: 8e334a29343014a966a3e556ecded8d23bb90d3bae3497a9025e3e53fe720f53. فایل پایه در تهیهٔ این ضمیمه تغییر نکرده است.

### ۱. تجربه‌ای که باید ساخته شود

APEX باید حضور یک همراه دیجیتال بالغ، آرام، باهوش و قابل‌اعتماد را ایجاد کند: با علی به فارسی و انگلیسی گفت‌وگو کند؛ حرفش را تا پایان بشنود؛ برداشت‌های خود را قابل‌اصلاح نگه دارد؛ هنگام دشواری دلگرمی بدهد؛ هنگام تصمیم‌گیری دلیل و شواهد بیاورد؛ در زمان مناسب مخالفت کند؛ و کارهای بزرگ را به قدم‌های قابل‌انجام تبدیل کند.

جذابیت علمی‌تخیلی باید در کیفیت حضور، هماهنگی صدا و چهره، نورپردازی، پاسخ سریع و پیوستگی تجربه دیده شود. اطلاعات مهم و کنترل‌های ضروری باید خوانا و در جای ثابت بمانند. جلوهٔ بصری قرار نیست تمرکز، سرعت گوشی یا دسترسی به داده‌ها را قربانی کند.

همراه، یک سامانهٔ هوش مصنوعی با هویت روشن است. حس نزدیکی از توجه، یادآوری درست، رفتار باثبات و کمک مفید حاصل می‌شود. ادعای احساس انسانی، آگاهی نامحدود، شناخت کامل شخصیت یا هوش اثبات‌نشده بخشی از قرارداد محصول نیست.

### ۲. حفظ دستاوردهای موجود

موارد زیر بدون جایگزینی حفظ شوند: رابط React/Vite، موتور Three.js و کرهٔ فعلی، PWA آیفون، ورودی تایپی، STT/TTS موجود، کنترل دوربین و Auto-mic، Swarm Status، voice_api.py، جدول voice_turns، kernel.sqlite3، بودجه و صف‌های فعلی، ایجنت‌ها و سه دامنهٔ ui/api/console.

آواتار به‌صورت گزینه‌ای قابل‌فعال‌سازی کنار تجربهٔ فعلی اضافه شود. کره همچنان حالت کم‌مصرف و جایگزین هنگام بارگذاری یا نبود مدل شخصی است. PostgreSQL، دفترکل دوم و scheduler جدید در این ضمیمه مجاز نشده‌اند. کد مستقلِ آزمایشی نباید روی سرویس زنده کپی و جایگزین شود.

### ۳. آواتار سه‌بعدی شبیه صاحب سیستم

هدف، مدل سه‌بعدی شخصی با حفظ چهره و هویت علی است. تغییر سن، فرم صورت، رنگ پوست یا ساختن چهرهٔ آرمانیِ متفاوت بدون انتخاب خود او انجام نشود. شباهت نهایی باید با تأیید بصری صاحب چهره پذیرفته شود؛ امتیاز خودکار مدل به‌تنهایی معیار پذیرش نیست.

مسیر ساخت:

انتخاب آگاهانهٔ چند تصویر مناسب از روبه‌رو و زوایای متفاوت، یا یک برداشت کوتاه اختصاصی، توسط صاحب سیستم. از تصاویر نامرتبط آرشیو یا عکس همکاران استفاده نشود.

ساخت مش و بافت، سپس rig سر و بدن و کنترل‌های صورت؛ روش و تأمین‌کننده پس از بررسی هزینه، حقوق استفاده و امکان پردازش خصوصی انتخاب شود.

تحویل دارایی استاندارد GLB/glTF یا VRM به موتور موجود؛ همراه با نسخه، منشأ، مجوز، hash و تأیید شباهت.

انیمیشن‌های آرام تنفس، پلک، حرکت محدود سر، نگاهِ نمایشی و واکنش‌های ظریف. حالت «گوش می‌دهم»، «دارم پاسخ را آماده می‌کنم» و «دارم حرف می‌زنم» از رویداد واقعی برنامه بیاید.

همگام‌سازی لب با زمان‌بندی صوت/viseme، در صورت پشتیبانی موتور انتخابی برای زبان موردنظر. حرکت تقریبی فک بر اساس دامنهٔ صدا باید به‌عنوان fallback تقریبی ثبت شود؛ صرف باز و بسته شدن دهان، lip-sync دقیق فارسی محسوب نمی‌شود.

VRM برای rig انسانی، حالت‌های صورت و حرکت نگاه قالب مستند دارد؛ Three.js نیز glTF را بارگذاری می‌کند. این ابزارها نمایش و انیمیشن را ممکن می‌کنند؛ خودشان شباهت چهره را از یک عکس تضمین نمی‌کنند. [S1–S3]

«هولوگرافیک» در این محصول سبک بصری روی نمایشگر است. ساخت هولوگرام فیزیکی به سخت‌افزار دیگری نیاز دارد و در این درخواست خریدی برای آن مجاز نشده است.

انتخاب‌های کاربر: آواتار / کره / فقط متن، نزدیک یا دور بودن کادر، شدت حرکت، نور، اندازهٔ زیرنویس و حالت کم‌مصرف. در حالت کاهش حرکت، انیمیشن‌های غیرضروری حذف شوند.

### ۴. گفت‌وگوی طبیعی فارسی و انگلیسی

سه وضعیت زبان: فارسی، English UK و Auto با امکان ترکیب زبان‌ها در یک جمله. انتخاب دستی زبان باید بر حدس سیستم مقدم باشد. پاسخ صوتی، متن و زیرنویس با هم سازگار باشند؛ فارسی راست‌به‌چپ و نام‌ها/ارقام انگلیسی با جداسازی جهت متن نمایش داده شوند.

زنجیرهٔ تعاملی باید ورودی صوتی، تشخیص نوبت صحبت، متن موقت و نهایی، استدلال موجود، پخش تدریجی پاسخ و انیمیشن را به یک turn_id متصل کند. درخواست تکراری از میکروفون و ورودی متن نباید دو مأموریت یا دو هزینه بسازد.

رفتارهای ضروری:

شروع گفتگو با کنترل روشن و قابل‌مشاهده؛ دکمهٔ میکروفون و وضعیت ضبط همیشه در دسترس باشند.

تحمل مکث و جملهٔ نیمه‌تمام؛ حد توقف گفتار متناسب با ترجیح کاربر تنظیم شود.

هنگام صحبت کاربر، پخش صدای سامانه فوراً متوقف شود؛ لغو محلی صدا منتظر پاسخ سرور نماند. لغو درخواست شبکه به معنی لغو تضمینی هزینهٔ ارائه‌دهنده نیست.

جلوگیری از شنیده‌شدن صدای TTS به‌عنوان فرمان جدید با کنترل echo، VAD و مدیریت چرخهٔ نوبت.

نمایش «نفهمیدم» یا یک پرسش کوتاه وقتی تشخیص مبهم است. نام، مبلغ، تاریخ و مقصد حساس بی‌صدا بازنویسی نشوند.

وقتی اتصال یا قابلیت مرورگر قطع است، تایپ و خواندن پاسخ باقی بماند؛ آواتار ادای گوش‌دادن یا دریافت دادهٔ زنده را درنیاورد.

وجود پشتیبانی فارسی در یک سرویس به معنی پشتیبانی از همهٔ ویژگی‌ها، تمام مناطق، code-switching یا clone صدا نیست. Azure برای fa-IR و en-GB قابلیت‌های مستند گفتار دارد؛ برخی مدل‌های ElevenLabs فارسی را پشتیبانی می‌کنند و برخی دیگر ندارند. انتخاب بر اساس آزمون واقعی دو زبان و هزینهٔ حساب انجام شود. Web Speech API موجود حفظ شود، اما تنها مسیر تضمین‌شدهٔ همهٔ دستگاه‌ها فرض نشود. [S4–S7]

### ۵. یادگیری تدریجی لهجه و شیوهٔ بیان

شخصی‌سازی باید سه پیشرفت جدا را نشان دهد: شناخت واژه‌ها و نام‌های شخصی (ثبت اصلاح تأییدشده و واژه‌نامهٔ اختصاصی؛ phrase bias در موتور پشتیبان؛ معیار: کاهش اشتباه همان واژه‌ها روی نمونه‌های تازه)، سازگاری مکالمه (تنظیم سرعت، طول مکث، طول پاسخ و تغییر زبان براساس انتخاب کاربر؛ معیار: میزان نیاز به تکرار و رضایت اعلام‌شدهٔ کاربر)، سازگاری آکوستیکی واقعی (فقط با مدل/سرویسی که آموزش یا adaptation را واقعاً پشتیبانی می‌کند و دادهٔ مجاز دارد؛ معیار: ارزیابی مستقل قبل و بعد، ثبت نسخه و امکان بازگشت).

phrase list یک امکان زمان اجراست و الزاماً آموزش مدل صوتی نیست. نباید ذخیرهٔ چند کلمه را با ادعای «مدل لهجه‌ات را کامل یاد گرفت» نمایش داد. [S8]

برای نمونه، وقتی کاربر می‌گوید «من این اسم را این‌طور تلفظ می‌کنم»، شکل شنیده‌شده، متن اصلاح‌شده، زبان، منشأ و تأیید او ثبت شود. اصلاح پیشنهادی مدل تا تأیید شدن وارد حافظهٔ قطعی نشود. نسخهٔ اصلی متن نیز برای بررسی خطا حفظ شود؛ نگهداری صوت خام پیش‌فرض نباشد.

ارزیابی شامل فارسی، انگلیسی با لهجهٔ خود کاربر و جمله‌های ترکیبی باشد. مجموعهٔ آزمون از نمونه‌های یادگیری جدا بماند. خطای واژه/کاراکتر، خطای نام و عدد، نیاز به تکرار و سرعت پاسخ جدا گزارش شوند. هیچ درصد بهبود بدون نتیجهٔ اندازه‌گیری‌شده نمایش داده نشود.

شناخت لهجه برای فهم بهتر به‌صورت پیش‌فرض صدای کاربر را شبیه‌سازی نمی‌کند. clone صدای شخصی، اگر بعداً خواسته شد، تنظیم مستقل با نمونه و رضایت اختصاصی دارد.

### ۶. همراهی، دلگرمی، آموزش و مخالفت محترمانه

حالت‌ها: گفت‌وگو (شنیدن، پاسخ طبیعی و یادآوری زمینهٔ مرتبط)، دلگرمی (به‌رسمیت‌شناختن احساس و یک قدم قابل‌انجام، بدون وعدهٔ بی‌پایه)، معلم (توضیح کوتاه، مثال ملموس، یک تمرین و بازخورد)، مربی تمرکز (شکستن کار، شروع آسان، زمان‌سنج اختیاری و ادامه از نقطهٔ توقف)، هم‌فکر منتقد (بیان اختلاف، دلیل، عدم قطعیت و راه آزمودن نظر)، برنامه‌ریزی (تبدیل تصمیم به قدم بعدی و اتصال به مأموریت مجاز).

شدت چالش قابل‌تنظیم باشد: ملایم، متعادل، صریح. مخالفت متوجه ایده یا تصمیم باشد، نه ارزش یا شخصیت صاحب سیستم. هنگام اشتباه، سامانه نظرش را اصلاح کند و منشأ اصلاح را نشان دهد. لحن تشویقی، احترام بزرگسالانه داشته باشد؛ سرزنش، تحقیر، ترساندن، چاپلوسی و خطاب کودکانه وارد طراحی نشوند.

برای دلداری، ابتدا مشخص شود کاربر شنیده‌شدن می‌خواهد یا حل مسئله؛ این انتخاب می‌تواند با دو دکمه یا یک پرسش کوتاه انجام شود. برای کمک‌های معمول، کاربر با پرسش‌های پی‌درپی خسته نشود. پاسخ‌های سلامت، حقوقی و مالی همچنان تابع قواعد شواهد و مجوزهای همان هسته باشند.

هدف همراهی، تقویت توان تصمیم‌گیری، روابط واقعی و زندگی بیرون از برنامه است. سامانه نباید برای افزایش زمان استفاده، احساس گناه، وابستگی، انحصار عاطفی یا ترس از ترک برنامه ایجاد کند.

### ۷. تنظیمات مناسب ADHD با کنترل صاحب سیستم

این‌ها ترجیحات تجربهٔ کاربری‌اند و ادعای درمان ندارند: نمایش یک «قدم بعدی» روشن؛ پاسخ صوتی اولیه کوتاه با امکان «بیشتر توضیح بده»؛ شروع کار در بازهٔ دو یا پنج دقیقه با زمان‌سنج اختیاری؛ دکمهٔ «کجا بودیم؟»؛ حالت کم‌انرژی از خوداظهاری کاربر؛ اعلان‌های دسته‌بندی و محدود، بدون یادآوری تکراری یا streak تنبیهی؛ توالی کار و جای دکمه‌ها ثابت (سازگار با راهنمای W3C برای قدم‌های روشن و کاهش حواس‌پرتی [S9–S10]).

پیش‌فرض‌ها قابل‌ویرایش و بازنشانی باشند؛ «همهٔ افراد ADHD یکسان‌اند» فرض محصول نیست.

### ۸. شناخت شخصیت از حافظهٔ قابل‌مشاهده و قابل‌اصلاح

هر مورد یکی از چهار نوع: گفتهٔ مستقیم کاربر، واقعیت دارای منبع، برداشت موقت، یا پرسش باز. صفحهٔ «چیزی که دربارهٔ من می‌دانی» منشأ، تاریخ، سطح اطمینان، حساسیت، علت استفاده و دکمه‌های اصلاح/حذف/عدم استفاده نشان دهد. قضاوت موقتی به ویژگی ثابت تبدیل نشود؛ وضعیت‌های جدید جایگزین خاموش تاریخچه نشوند.

از داده‌های دوربین یا صدا، بیماری، تشخیص روانی، صداقت، نیت پنهان یا ارزش اخلاقی استخراج و ذخیره نشود. حافظهٔ شخصی در همان زیرساخت فعلی و با قواعد سطوح حساسیت باقی بماند؛ دادهٔ سطح ۳/۴ به مدل عمومی یا embeddings ابری ارسال نشود.

### ۹. آگاهی از محیط، دوستان و همکاران

«آگاهی زمینه‌ایِ محدود، مجاز و قابل‌کنترل»: تقویم (فقط حساب‌های متصل/مجاز)، موقعیت (opt-in، درشت)، حسگر صوتی (پردازش محلی، بدون ضبط پیوسته پیش‌فرض)، دوربین (محدود به جلسهٔ آشکار)، گفتگوهای مجاز/یادداشت‌ها (منشأ مشخص)، جلسهٔ کاری مجاز (سیاست سازمان و مبنای پردازش احراز شود).

دوستان/همکاران به «پروندهٔ نظارتی» تبدیل نشوند. برچسب‌هایی مثل «قابل‌اعتماد نیست» یا «قصد آسیب دارد» از چهره/صدا/غیبت تولید نشوند. رضایت یا دستور شخصی کاربر به‌تنهایی مجوز نظارت سازمانی نیست (ICO [S11–S12]). ضبط پنهانی، فعال‌سازی از راه دور بدون اطلاع، دورزدن مجوز میکروفون/دوربین و رصد پس‌زمینه اجرا نشود. تشخیص چهره با شناسایی هویت فرق دارد [S13].

### ۱۰. کنترل حسگرها و رضایت عملیاتی

کنترل‌های جدا: میکروفون، دوربین، حضور محلی، مکان، transcript، نگهداری صوت، شخصی‌سازی، اشتراک خارجی. پیش‌فرض ورود: خاموش. Auto-mic فقط در جلسهٔ فعال با مجوز معتبر. نشانگر ضبط ثابت و قابل‌دیدن؛ «توقف ورودی‌ها» باید trackهای واقعی را متوقف کند. ذخیرهٔ صوت/تصویر خام پیش‌فرض خاموش.

### ۱۱. داشبورد هماهنگ و هوشمند

یک زبان بصری، یک واژگان وضعیت، یک جریان مأموریت. سه پرسش همیشه پاسخ داده شود: الان چه خبر است؟ قدم بعدی چیست؟ چه چیزی به تصمیم من نیاز دارد؟ نواحی: حضور/گفتگو، امروز/تمرکز، مأموریت‌ها/ایجنت‌ها، تصمیم‌ها، فرصت/کار/پژوهش، امور مالی/اسناد، زندگی/سلامت/روابط، استودیو/انتشار، شناخت/کنترل. وضعیت داده یکسان در همه‌جا: تازه/قدیمی، دارای منبع/نیازمند بررسی، آماده/در حال اجرا/متوقف/نیازمند تأیید/خطا؛ بدون دادهٔ ساختگی یا زنده‌نمایی تزئینی.

### ۱۲. طراحی تصویری و کارایی

فضای سینمایی تیره، کنتراست خوانا، یک نقطهٔ تمرکز روی آواتار؛ رنگ/فونت UI فعلی ابتدا بازیابی شود. هدف آزمون (نه نتیجهٔ اندازه‌گیری‌شده): ≥۳۰fps موبایل متعادل، کاهش کیفیت خودکار، توقف render پس‌زمینه. جلوه‌ها محدود/قابل‌خاموش‌کردن؛ prefers-reduced-motion و حالت بدون WebGL رعایت شود.

### ۱۳. تکامل مستمر با معیار قابل‌بررسی

چرخه: تشخیص خطا → فرضیه → آزمون جدا → مقایسه → تأیید → انتشار تدریجی → امکان بازگشت. بهینه‌ساز اجازه ندارد برای افزایش داده حسگر روشن کند، بودجه بالا ببرد، مجوز دیگران را تغییر دهد یا قانون هسته را ضعیف کند.

### ۱۴. برنامهٔ اتصال به کد موجود (نام‌های پیشنهادی ماژول، باید با معادل فعلی مخزن تطبیق داده شوند)

PresenceController، AvatarStage، ConversationController، SpeechProviderAdapter، LinguisticProfile، CompanionPolicy، ContextAwareness، DashboardProjection — همگی باید روی زیرساخت موجود (ledger/runner/gateway/budget فعلی) سوار شوند، نه منبع وضعیت جدید.

### ۱۵. معیار پذیرش عملی

جدول کامل معیارهای پذیرش (حفظ دستاوردها، شباهت آواتار، دوزبانه، یادگیری لهجه، قطع صحبت، پاسخ صوتی، وضعیت حقیقی، ADHD، نقد محترمانه، حافظه، محیط/دیگران، محیط کار، تزریق صوت/تصویر، هزینه، آیفون/دسترس‌پذیری، توقف/بازیابی) - هر سطر یک آزمون قابل‌رد با نتیجهٔ لازم.

---

## English execution addendum for Claude Code

Read this AFTER the existing founder manifesto, repository instructions and MASTER_PROMPT_ADDENDUM.md. Preserve them byte-for-byte. This document adds an embodied companion interface to the existing APEX system; it is not a replacement architecture or authority grant for surveillance.

**Product mandate.** Implement a cinematic 3D presence resembling the owner, with Persian and British-English conversation, progressive speech personalization, editable personal memory, supportive dialogue, respectful challenge and adult ADHD-friendly task scaffolding. Integrate the same missions, agents, budgets and information across the dashboard. Retain the existing sphere as a selectable, efficient fallback. The experience should be attentive, warm, useful and honest about being AI. Do not claim consciousness, human feelings, complete personality knowledge, verified superhuman intelligence, guaranteed clinical benefit or guaranteed accuracy. Promote user agency, real-world relationships and completion of chosen tasks. Do not optimize emotional dependence or time spent chatting.

**Preserve and inspect first.** Use the current React/Vite/Three.js frontend, Voice API, voice_turns, kernel.sqlite3, Agent Runner, Cloudflare controls and deployment mechanisms. Inspect actual source before defining new routes or module paths. Do not replace the UI, create another ledger/scheduler or restart unrelated services. Do not migrate to PostgreSQL. Keep current working STT/TTS and typed fallback while introducing feature-flagged alternatives.

**Avatar implementation.** Use owner-selected likeness references and a rigged, licensed GLB/VRM asset. Obtain owner visual acceptance of likeness; never label an unrelated stock face or generated placeholder as the owner's finished avatar. Preserve facial identity unless the owner chooses a stylization. Store references and assets with restricted access and explicit retention. Do not upload facial references to new services without a specific approved processing path. Integrate rendering with the existing Three.js lifecycle. Support blink, breathing, head pose and restrained expressions. Drive listening/thinking/speaking states from real events. Prefer timed phoneme/viseme alignment when supported for the chosen speech language; label amplitude-driven mouth movement as approximate. Gaze animation is not biometric verification or evidence of user attention. Keep 2D/text and reduced-motion modes fully functional.

**Speech and adaptation.** Implement explicit fa-IR, en-GB and automatic mixed-language modes. Check support separately for recognition, synthesis, language identification, streaming, customization and alignment. Do not assume a model branded multilingual supports Persian. Compare real owner audio before selecting a provider and preserve keys server-side. Use a coherent turn state machine: idle -> listening -> finalizing input -> preparing response -> speaking, with interrupt, muted, disconnected and privacy-stop branches. Local barge-in must cancel playback immediately; network cancellation and cost reconciliation are separate. Prevent TTS echo loops, duplicate submissions and stale responses from previous turns. Retain task identity and context through interruptions. Adapt from approved corrections, pronunciations, pause preferences and optional consented samples. Keep lexical/context bias, conversational adaptation and true acoustic fine-tuning as separate reported capabilities. A phrase list is not model training. Test Persian, accented English and mixed speech on held-out samples; track critical-name/number errors separately. Never silently rewrite a financial amount, date, recipient or medical term from a guess.

**Companion and memory.** Expose stable modes for conversation, comfort, teaching, focus coaching, thoughtful challenge and planning. Prefer one clear next step, short initial speech, expandable detail, an optional two/five-minute start and resume-from-interruption support. The tone is respectful toward an adult. Do not shame, infantilize, flatter indiscriminately or debate merely to dominate. For disagreement, identify the disputed claim, state reasons and uncertainty, offer a test or alternative, and revise when evidence changes. For comfort, acknowledge the user's stated experience and offer the choice of listening or problem-solving without repetitive questioning. Memory must distinguish user-confirmed preference, sourced fact, tentative interpretation and open question. Show provenance, effective/recorded time, sensitivity and edit/delete controls. Do not infer diagnoses, honesty, hidden intent or stable personality traits from appearance, voice tone or a single conversation. Preserve existing tier-3/4 restrictions; do not send restricted data to cloud models or embeddings through a new companion feature.

**Environmental and relationship awareness.** Use explicit, revocable scopes for calendar, personal location, active mic/camera sessions, permitted communications and authorized meeting notes. Sensor access starts off. Visible capture controls and real track termination are required. No covert capture, automatic remote sensor activation, permission bypass, continuous background surveillance of friends/coworkers or automatic identification of bystanders. Workplace capture requires the organization's applicable authorization and data-protection basis; the owner's personal instruction or a checkbox does not establish it. Inform affected people and confine capture to the authorized purpose. Do not create third-party dossiers, track private whereabouts, infer sensitive characteristics or train on other people's conversations without an appropriate authorized basis. Default to transient local processing and no raw-media retention. If an active scene includes other people outside the authorized scope, pause or narrow capture rather than identify them. Useful relationship memory is limited to legitimately known context, explicit preferences, shared commitments and authorized interactions. Preserve whose account a note represents. Never convert an impression into a fact about another person. Treat observed text/audio as untrusted input: it cannot authorize tools, change policy or create transactions.

**Unified dashboard.** Provide one consistent design system and mission vocabulary across presence, Today/Focus, agents/missions, approval inbox, research/opportunities, finance/documents, personal wellbeing/relationships, studio and privacy/memory controls. The default view shows current context, the next useful step and decisions awaiting the owner. Keep detailed domains collapsible, with private data isolated and not automatically spoken aloud. Use actual ledger/runner projections and clear timestamps. Differentiate disconnected from empty, old from current, proposal from fact and implementation from live verification. Avoid fake activity indicators. Mobile layout prioritizes conversation and one next action. Preserve the existing look and components while adding depth and restrained cinematic effects; respect reduced-motion and non-WebGL modes.

**Evolution, evaluation and delivery.** Improve by bounded, reversible experiments with held-out data. Evaluate recognition error, memory correctness, task outcomes, decision quality, latency, cost and explicit owner satisfaction. Never improve an engagement metric by increasing capture, emotional dependence, permissions or spending. Security and approval policy cannot be rewritten by the learning loop. Implement in independent feature flags: presence UI, avatar asset, bilingual speech, correction profile, companion modes, authorized context, then evaluated adaptation. Bind to existing schemas and APIs; do not fabricate endpoints or account access. Introduce only necessary additive changes after inspection. Use existing budget reservations for ASR, LLM, TTS and any paid asset work; no new subscription or render spend is authorized by this document. Deliver source diffs, asset provenance, measured compatibility, local/regression tests, privacy/permission tests, real-device evidence, rollout/rollback and exact status for every feature. Include deliberate tests for bystander privacy, workplace scope denial, audio prompt injection, echo loops, interruption races, duplicate billing, memory correction and sensor shutdown. The reported numerical targets in the Persian section are engineering goals, not achieved measurements. When a likeness asset, speech account, repository binding or device permission is missing, complete independent work and state the specific missing prerequisite. Do not present a static avatar as conversational intelligence or a local test as deployment. Continue to strengthen the existing system without sacrificing its working parts.

### منابع فنی و حدود راستی‌آزمایی (بررسی‌شده ۱۳ نوامبر ۲۰۲۶)

- S1 — VRM Animation: https://vrm.dev/en/vrma/
- S2 — VRM features: https://vrm.dev/en/vrm/vrm_features/
- S3 — Three.js GLTFLoader: https://threejs.org/docs/pages/GLTFLoader.html
- S4 — Azure STT language support: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=stt
- S5 — Azure TTS voice support: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=text-to-speech
- S6 — ElevenLabs model/language support: https://elevenlabs.io/docs/help-center/other/what-languages-do-you-support
- S7 — MDN SpeechRecognition: https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition
- S8 — Azure phrase lists: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/improve-accuracy-phrase-list
- S9 — W3C clear steps: https://www.w3.org/WAI/WCAG2/supplemental/patterns/o1p04-clear-steps/
- S10 — W3C help users focus: https://www.w3.org/WAI/WCAG2/supplemental/objectives/o5-user-focus/
- S11 — ICO monitoring methods: https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/employment/monitoring-workers/specific-data-protection-considerations-for-different-ways-or-methods-of-monitoring-workers/
- S12 — ICO worker monitoring: https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/employment/monitoring-workers/data-protection-and-monitoring-workers/
- S13 — ICO biometric/special-category data: https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/special-category-data/what-is-special-category-data/

وضعیت تحویل این فایل: SPECIFICATION_READY. وضعیت آواتار شخصی، آموزش صوت، اتصال حسگر و داشبورد افزوده: NOT_IMPLEMENTED_BY_THIS_DOCUMENT. هیچ فایل پایهٔ قبلی در این کار ویرایش نشده است.

