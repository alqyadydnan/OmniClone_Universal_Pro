# OmniClone Universal Pro — نظام النسخ الذكي

> نظام نسخ شامل لأنظمة Windows عبر الشبكة المباشرة (Ethernet)  
> مخصص لمهندسي تقنية المعلومات

---

## المميزات

| الميزة | التفاصيل |
|--------|----------|
| **واجهة عربية RTL** | PyQt6 كاملة من اليمين لليسار |
| **اختيار ذكي ثنائي الاتجاه** | المصدر يرى أقسام الهدف مباشرة |
| **قسم المصدر للقراءة فقط** | لا خطر على البيانات الأصلية |
| **قفل السلامة** | جميع الأقسام الأخرى على الهدف تُقفل تلقائياً |
| **نقل على مستوى القطاعات المستخدمة فقط** | تخطي المساحة الفارغة لأقصى سرعة |
| **ضغط lz4** | أسرع ضغط في الفئة مع أداء ممتاز |
| **MD5 لكل بلوك** | ضمان سلامة البيانات بنسبة 100% |
| **PXE + TFTP + DHCP مدمج** | لا تحتاج برامج خارجية |
| **إصلاح الإقلاع تلقائي** | يكتشف BIOS/UEFI ويشغّل bcdboot تلقائياً |
| **EXE مستقل** | لا يحتاج تثبيت Python أو أي مكتبة |

---

## هيكل المشروع

```
omniclone/
├── src/
│   ├── main.py                    # نقطة الدخول الرئيسية (جهاز المصدر)
│   ├── gui/
│   │   ├── main_window.py         # الواجهة الرئيسية العربية
│   │   └── progress_dialog.py     # نافذة التقدم المباشر
│   ├── engine/
│   │   ├── partition_reader.py    # قراءة القطاعات (للقراءة فقط)
│   │   ├── cloner.py              # محرك النسخ (lz4 + MD5)
│   │   └── boot_repair.py        # إصلاح الإقلاع (bcdboot)
│   ├── services/
│   │   ├── dhcp_server.py         # خادم DHCP مدمج
│   │   ├── tftp_server.py         # خادم TFTP مدمج
│   │   └── network_manager.py     # مدير الشبكة
│   └── protocol/
│       └── messages.py            # بروتوكول الاتصال
├── agent/
│   ├── main.py                    # وكيل الجهاز الهدف (WinPE)
│   ├── partition_scanner.py       # فحص الأقسام
│   ├── partition_writer.py        # كتابة البلوكات المضغوطة
│   └── lock_manager.py            # قفل الأقسام الأخرى
├── boot/                          # ملفات WinPE للإقلاع عبر PXE
├── resources/                     # الأيقونات والموارد
├── OmniClone_Source.spec          # مواصفات PyInstaller (المصدر)
├── OmniClone_Agent.spec           # مواصفات PyInstaller (الوكيل)
├── build.bat                      # سكريبت البناء الآلي
├── requirements.txt               # المتطلبات
└── WINPE_SETUP.md                 # دليل إعداد WinPE
```

---

## بناء الـ EXE (على Windows)

```cmd
git clone <repo> omniclone
cd omniclone
build.bat
```

### المتطلبات على جهاز البناء:
- Python 3.11+ (64-bit)
- pip install -r requirements.txt
- Windows 10/11 أو Windows Server (مطلوب لـ PyInstaller UWP manifest)

### الناتج:
```
dist\OmniClone_Universal_Pro.exe   ← الجهاز المصدر (GUI عربية)
dist\OmniClone_Agent.exe           ← الجهاز الهدف (يُدمج في WinPE)
```

---

## الاستخدام

### على جهاز المصدر:
1. انقر نقراً مزدوجاً على `OmniClone_Universal_Pro.exe`
2. قبل أي شيء: اضغط **"تشغيل خدمات الشبكة"**
3. اختر القسم المراد نسخه من الجهاز المصدر

### على الجهاز الهدف:
1. تأكد من تفعيل **PXE Boot** في BIOS/UEFI
2. وصّل كابل Ethernet بالجهاز المصدر
3. أقلع الجهاز — سيتصل تلقائياً

### في البرنامج:
4. ستظهر أقسام الهدف في الواجهة
5. اختر القسم الهدف بعناية
6. اضغط **"بدء النسخ الآن"** وأكد مرتين
7. انتظر اكتمال العملية وإصلاح الإقلاع

---

## البروتوكول التقني

```
جهاز المصدر                    جهاز الهدف
─────────────                  ──────────
DHCP Server     ──────────►   PXE Boot
TFTP Server     ──────────►   WinPE Load
                ◄──────────   HELLO + Partition List
SELECT_TARGET   ──────────►
                ◄──────────   SELECT_ACK + Lock Confirmation
START_CLONE     ──────────►
BLOCK (lz4+MD5) ──────────►
                ◄──────────   BLOCK_ACK per block
CLONE_DONE      ──────────►
BOOT_REPAIR     ──────────►   bcdboot
                ◄──────────   BOOT_DONE
```

---

## الأمان

- القسم المصدر: `GENERIC_READ` فقط — مستحيل الكتابة عليه
- جميع أقسام الهدف الأخرى: `FSCTL_DISMOUNT_VOLUME` — مقفلة تماماً
- MD5 checksum على كل بلوك — أي تلف يُعاد إرسال البلوك تلقائياً (حتى 5 محاولات)
- تأكيد مزدوج من المستخدم قبل بدء الكتابة

---

## ملاحظة مهمة

> لا يمكن إنشاء EXE لنظام Windows من Linux أو macOS.  
> يجب تشغيل `build.bat` على جهاز Windows حقيقي.  
> انظر `WINPE_SETUP.md` لتعليمات إعداد بيئة WinPE للإقلاع.
