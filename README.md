# المثبّت الذكي الشامل لنظام أوبونتو (Ubuntu Smart Package Installer)

تطبيق سطح مكتب رسومي حديث ومتكامل مبني بلغة **Python 3** ومكتبة **PyQt6**، صُمم لأتمتة تثبيت البرامج والتطبيقات المحمّلة على توزيعات **أوبونتو (Ubuntu 22.04 / 24.04)** ومشتقاتها مثل **لينكس مينت (Linux Mint 22+)** بضغطة زر واحدة وبأعلى معايير الأمان والاستقرار.

---

## 🌟 المزايا الرئيسية

1. **دعم شامل لمختلف صيغ التوزيع (V1):**
   - حزم دبيان: `.deb` (مع معالجة الاعتماديات التلقائية عبر APT وفحص المعمارية).
   - الأرشيفات المضغوطة: `.tar.gz`، `.tgz`، `.tar.xz`، `.tar.bz2`، `.zip`.
   - حزم البرامج المحمولة: `.AppImage`.
   - سكربتات التثبيت: `.sh`، `.run`، `.bin` (مع فحص Makeself وتشغيل آمن).
2. **نموذج أمان خالٍ من المخاطر:**
   - لا تتعامل الواجهة مع كلمة المرور إطلاقًا ولا تستخدم `sudo -S`.
   - مساعد جذر وحيد ومحصور (`privileged_helper.py`) يعمل عبر `pkexec` وبسياسة Polkit معتمدة.
   - قائمة بيضاء صارمة للعمليات المسموحة، وفحص أمني دقيق لكل المسارات لمنع أي تجاوز (Path Traversal).
   - فك ضغط الأرشيفات في بيئة تحضير معزولة كمستخدم عادي لحماية ملفات النظام.
3. **وضعان للتثبيت:**
   - **وضع النظام (System):** التثبيت داخل `/opt/<slug>` وربطه في `/usr/local/bin` واختصار في `/usr/share/applications` (يتطلب root مرة واحدة عبر pkexec).
   - **وضع المستخدم (User):** التثبيت داخل `~/.local/opt/<slug>` وربطه في `~/.local/bin` (الافتراضي لحزم AppImage بدون أي طلب لكلمة المرور).
4. **تكامل متقدم مع بيئة سطح المكتب:**
   - إنشاء اختصارات قياسية (`.desktop`) متوافقة مع مواصفات FreeDesktop 1.5.
   - التحقق التلقائي من صحة الاختصار عبر `desktop-file-validate` وتحديث قاعدة البيانات.
   - استخراج وتثبيت الأيقونات تلقائيًا في ثيم الأيقونات القياسي `hicolor`.
   - ربط البرنامج مباشرة بالطرفية ليُشغَّل باسمه المختصر.
5. **معالجة تلقائية لأعقد مشاكل لينكس الشائعة:**
   - **إصلاح `chrome-sandbox`:** ضبط تلقائي لـ `chmod 4755 root:root` لتطبيقات Electron على Ubuntu 24.04+.
   - **أقراص exFAT/NTFS:** التعامل الآمن مع الملفات المحمّلة على فلاشات أو أقراص مشتركة لا تقبل صلاحيات لينكس بنسخها أولًا إلى مسار نظامي.
   - **نقص `libfuse2`:** فحص مسبق مع خيار تثبيت `libfuse2t64` أو تفعيل وضع `APPIMAGE_EXTRACT_AND_RUN=1`.
   - **حل تعارض الأسماء:** فحص مسبق لأوامر النظام والمجلدات السابقة مع خيارات الترقية أو استخدام اسم بديل.
   - **تراجع تلقائي (Rollback):** عند حدوث أي خطأ أو إلغاء، يتم التراجع عن جميع الملفات والمجلدات التي تم إنشاؤها لضمان بقاء النظام نظيفًا تمامًا.
   - **إلغاء التثبيت النظيف (Uninstall):** تبويب مخصص لعرض كل البرامج المثبتة وإزالتها وحذف ملفاتها بالكامل بضغطة زر.

---

## 🛠 المتطلبات والتثبيت

### 1. المتطلبات الأساسية
- نظام **Ubuntu 22.04 LTS** أو **Ubuntu 24.04 LTS** (أو مشتقاتها الحديثة).
- بايثون **Python 3.10** أو أحدث.

### 2. تنزيل المشروع من GitHub
```bash
git clone https://github.com/MohZubiri/smart-instillation-linx.git
cd smart-instillation-linx
```

### 3. التثبيت التلقائي بنقرة واحدة
قم بتشغيل سكربت الإعداد التلقائي (يقوم بتثبيت متطلبات النظام ونسخ الملفات إلى `/opt/smart-installer` وضبط الصلاحيات وسياسة Polkit واختصار قائمة التطبيقات):
```bash
sudo ./setup_self.sh
```

> ⚠️ **مهم:** البرنامج المثبّت يعمل من النسخة الموجودة في `/opt/smart-installer` وليس من مجلد المشروع.
> بعد أي تعديل على الكود أو بعد `git pull` يجب إعادة تشغيل `sudo ./setup_self.sh` لنشر التعديلات، وإلا سيستمر تشغيل النسخة القديمة.
> للتأكد من تطابق النسختين:
> ```bash
> diff -rq core /opt/smart-installer/core | grep -v pycache && echo "النسخة المنشورة قديمة" || echo "النسخة المنشورة محدّثة"
> ```

أو تشغيله بدون sudo وسيطلب النظام التحقق تلقائيًا:
```bash
./setup_self.sh
```

### 4. إزالة التثبيت من النظام
لإزالة المثبت الذكي نفسه وكافة ملفاته وسياسات Polkit التابعة له:
```bash
sudo ./setup_self.sh --uninstall
```

---

## 🚀 كيفية الاستخدام

### من واجهة سطح المكتب
ابحث في قائمة التطبيقات عن **"المثبّت الذكي" (Smart Package Installer)**، أو افتح أي ملف حزمة باستخدام خيار "فتح بواسطة المثبت الذكي".

1. اسحب وأفلت ملف البرنامج (أو اضغط **Browse**).
2. سيقوم البرنامج بفحص الحزمة واشتقاق الاسم والمعرّف (`slug`) ووضع التثبيت تلقائيًا.
3. اضغط على زر **"تثبيت البرنامج الآن"**.
4. فور اكتمال التثبيت، ستظهر شاشة النتيجة وبها أمر الطرفية وزر **"تشغيل الآن"**.

### التشغيل من مجلد المشروع بدون تثبيت (للتطوير)
```bash
sudo apt install python3-pyqt6 desktop-file-utils policykit-1
python3 main.py
```
عند التشغيل من مجلد المشروع يستخدم البرنامج `privileged_helper.py` الموجود في المجلد نفسه.

### من الطرفية (CLI)
لتشغيل البرنامج مع فتح حزمة مباشرة:
```bash
smart-installer /path/to/package.tar.gz
```

### وضع الاختبار الجاف (Dry Run)
لعرض خطة التثبيت الكاملة كبيانات JSON دون تنفيذ أي تعديل على النظام (مفيد للتشخيص واختبارات CI/CD):
```bash
python3 main.py --dry-run /path/to/package.tar.gz
```

---

## ❓ الأسئلة الشائعة وحلول المشاكل (FAQ)

### 1. لماذا يطلب البرنامج صلاحيات عند تثبيت تطبيقات Electron في وضع المستخدم؟
تتطلب بيئة Electron على أوبونتو 24.04+ وجود ملف `chrome-sandbox` بصلاحية جذر محددة (`chmod 4755 root:root`). يقوم المثبت بإصلاح هذه الخطوة فقط عبر مساعد الجذر ليعمل البرنامج بأمان ودون الحاجة لتمرير الخيار الخطير `--no-sandbox`.

### 2. كيف يتعامل المثبت مع الملفات الموجودة على أقراص exFAT أو NTFS؟
أنظمة ملفات exFAT/NTFS الشائعة في وسائط التخزين الخارجية لا تدعم صلاحيات POSIX (`chmod +x`) أو الروابط الرمزية. يكتشف المثبت نوع نظام الملفات تلقائيًا عبر `findmnt` ويقوم بنسخ الملف أولًا إلى مجلد تحضير مؤقت على قرص النظام (ext4) قبل معالجته.

### 3. ماذا يحدث إذا كانت هناك عمليات تحديث تلقائية لنظام APT تعمل بالخلفية؟
في حال قفل مدير الحزم (`/var/lib/dpkg/lock-frontend`)، يقوم المثبت باكتشاف سبب التعليق وعرض تنبيه واضح للمستخدم بالانتظار حتى انتهاء التحديثات التلقائية، مع تراجع نظيف لمنع تجمّد الواجهة.

### 4. ما هو فحص FUSE لتطبيقات AppImage؟
في أوبونتو 24.04 تم استبدال مكتبة `libfuse2` القديمة بـ `libfuse2t64`. عند تشغيل حزمة AppImage غير مدمجة، يكتشف فاحص المتطلبات وجود المكتبة ويعرض تثبيتها أو يشغّلها مباشرة بوضع الاستخراج الآمن.

### 5. البرنامج ثُبّت لكنه لا يفتح، ما السبب؟
- **معمارية خاطئة:** تأكد أن اسم الملف المحمّل يحتوي `amd64` أو `x86_64` أو `x64` (وليس `arm64` أو `aarch64`). يرفض المثبّت تلقائيًا أي برنامج مبني لمعمارية لا تطابق جهازك ويعرض رسالة توضّح السبب. لمعرفة معمارية جهازك:
  ```bash
  uname -m
  ```
- **أداة طرفية بدون واجهة:** بعض البرامج (مثل `rar`) أدوات سطر أوامر فقط، فلا يُنشأ لها اختصار في قائمة التطبيقات، وتُشغَّل من الطرفية بالأمر الذي يظهر في شاشة النتيجة.
- **النسخة المنشورة قديمة:** أعد تشغيل `sudo ./setup_self.sh` (راجع قسم التثبيت).

### 6. أين أجد سجلات التثبيت ومعلومات البرامج المثبتة؟
| المحتوى | المسار |
|---|---|
| سجل كل عملية تثبيت | `~/.local/share/smart-installer/logs/` |
| سجلات برامج وضع النظام | `/var/lib/smart-installer/<slug>.json` |
| سجلات برامج وضع المستخدم | `~/.local/share/smart-installer/installs/<slug>.json` |

---

## 🧪 الاختبارات والتطوير (Testing)

لتشغيل فحص بنية الأكواد واختبارات الوحدة الآلية:
```bash
# توليد ملفات وحزم الاختبار
bash tests/fixtures/make_fixtures.sh

# تشغيل حزمة الاختبارات
python3 -m unittest discover -t . -s tests -v
```

---

## English Summary

**Ubuntu Smart Package Installer** is a graphical desktop utility written in Python 3 and PyQt6 that automates the installation of downloaded software archives and packages (`.deb`, `.tar.gz`, `.tar.xz`, `.tar.bz2`, `.zip`, `.AppImage`, `.sh`, `.run`, `.bin`) on Ubuntu 22.04, 24.04, and Linux Mint.

### Key Features:
- **Zero-Password UI & Polkit Security**: Employs a dedicated `privileged_helper.py` executed via `pkexec` with strict path validation and operation whitelisting. No `sudo -S` or plain-text credentials.
- **Dual Install Modes**: System `/opt` (multi-user) and User `~/.local/opt` (rootless for AppImages).
- **Desktop Integration**: Automatic FreeDesktop-compliant `.desktop` shortcut creation, icon extraction into hicolor theme, and CLI symlinking.
- **Self-Healing & Edge Cases**: Automates `chrome-sandbox` (chmod 4755) Electron fixes on Ubuntu 24.04, FUSE compatibility, exFAT/NTFS drive staging, conflict resolution, and automatic rollback on failure.
- **Uninstaller**: Built-in manifest manager to cleanly remove installed software with a single click.

### Installation:
```bash
git clone https://github.com/MohZubiri/smart-instillation-linx.git
cd smart-instillation-linx
sudo ./setup_self.sh
```
Re-run `sudo ./setup_self.sh` after every code change or `git pull`: the installed app runs from `/opt/smart-installer`, not from the project folder.

### Uninstallation:
```bash
sudo ./setup_self.sh --uninstall
```

