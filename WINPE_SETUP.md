# دليل إعداد WinPE لـ OmniClone Universal Pro

## الخطوات المطلوبة لإنشاء صورة WinPE القابلة للإقلاع عبر PXE

---

### المتطلبات

- Windows 10/11 أو Windows Server
- [Windows ADK](https://docs.microsoft.com/en-us/windows-hardware/get-started/adk-install) + WinPE Add-on
- PowerShell بصلاحيات Administrator

---

### الخطوة 1: تثبيت Windows ADK

```
winget install Microsoft.WindowsADK
winget install Microsoft.WindowsADK.WinPE
```

---

### الخطوة 2: إنشاء بيئة WinPE

```cmd
:: افتح Windows Deployment Tools Command Prompt كمدير
copype amd64 C:\WinPE_amd64
```

---

### الخطوة 3: تركيب صورة WinPE وإضافة الوكيل

```cmd
:: ركّب الصورة
Dism /Mount-Image /ImageFile:"C:\WinPE_amd64\media\sources\boot.wim" /Index:1 /MountDir:"C:\mount"

:: انسخ وكيل OmniClone إلى الصورة
copy "dist\OmniClone_Agent.exe" "C:\mount\Windows\System32\OmniClone_Agent.exe"

:: أنشئ ملف Winpeshl.ini لتشغيل الوكيل تلقائياً عند الإقلاع
echo [LaunchApp] > C:\mount\Windows\System32\winpeshl.ini
echo AppPath = OmniClone_Agent.exe >> C:\mount\Windows\System32\winpeshl.ini

:: إلغاء تركيب الصورة وحفظها
Dism /Unmount-Image /MountDir:"C:\mount" /Commit
```

---

### الخطوة 4: نسخ ملفات الإقلاع إلى مجلد boot

```cmd
:: أنشئ مجلد boot إذا لم يكن موجوداً
mkdir omniclone\boot

:: انسخ ملفات PXE
copy "C:\WinPE_amd64\media\Boot\pxeboot.n12"         "omniclone\boot\pxelinux.0"
copy "C:\WinPE_amd64\media\Boot\pxeboot.n12"         "omniclone\boot\pxeboot.n12"
copy "C:\WinPE_amd64\media\sources\boot.wim"          "omniclone\boot\boot.wim"
copy "C:\WinPE_amd64\media\Boot\BCD"                  "omniclone\boot\BCD"
copy "C:\WinPE_amd64\media\bootmgr"                   "omniclone\boot\bootmgr"
copy "C:\WinPE_amd64\media\bootmgr.efi"               "omniclone\boot\bootmgr.efi"

:: للـ UEFI
xcopy "C:\WinPE_amd64\media\EFI" "omniclone\boot\EFI" /E /I /Y
```

---

### الخطوة 5: بناء الـ EXE

```cmd
cd omniclone
build.bat
```

---

### الخطوة 6: الاستخدام

1. **الجهاز المصدر**: شغّل `OmniClone_Universal_Pro.exe` كمدير
2. **الجهاز الهدف**: تأكد من ضبط BIOS/UEFI للإقلاع عبر الشبكة (PXE Boot)
3. **الكابل**: وصّل الجهازين بكابل Ethernet مباشر أو عبر سويتش
4. في البرنامج: اضغط **"تشغيل خدمات الشبكة"** ثم أقلع الجهاز الهدف
5. اختر القسم المصدر والهدف واضغط **"بدء النسخ الآن"**

---

### ملاحظات أمنية

- البرنامج يتطلب صلاحيات Administrator لأنه يقرأ ويكتب على مستوى القطاعات الخام
- القسم المصدر يُفتح بوضع **للقراءة فقط** — لا خطر على بياناتك
- جميع الأقسام الأخرى على الجهاز الهدف تُقفل تلقائياً قبل الكتابة
- MD5 checksum على كل بلوك يضمن سلامة البيانات 100%
