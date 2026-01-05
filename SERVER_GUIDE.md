# 🦁 GIA: Server Deployment Guide (DigitalOcean / Linux)
**How to run GIA in the background like a Hedge Fund**

بما أنك قررت الانتقال للاحتراف وتشغيل البوت على سيرفر DigitalOcean، إليك الخطوات التقنية:

### 1. تجهيز السيرفر (Environment Setup)
قم بتنفيذ هذه الأوامر على السيرفر (Linux/Ubuntu):
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip screen -y
sudo mkdir -p /var/gia_data
sudo chmod 777 /var/gia_data
```

### 2. نقل الكود (Transferring Code)
أسهل طريقة هي ضغط مجلد `GIA_v1` ورفعه للسيرفر، أو استخدام `SCP`:
`scp -r C:\Users\yonsy\OneDrive\Desktop\GIA_v1 root@YOUR_SERVER_IP:/root/`

### 3. تشغيل البوت في الخلفية (The Screen Method)
هذه الطريقة تضمن استمرار العمل بعد إغلاقك للـ Terminal:
1. انشئ شاشة جديدة: `screen -S gia`
2. ادخل للمجلد: `cd GIA_v1`
3. ثبت المكتبات: `pip install pandas numpy twisted colorama joblib scikit-learn pytz`
4. شغّل البوت: `python3 run_live_demo.py`
5. **الخروج الآمن:** اضغط `Ctrl + A` ثم `D`.

### 4. المراقبة (Monitoring)
* للعودة للبوت: `screen -r gia`
* لرؤية العمليات من الخارج: `tail -f live_audit.log`
* لرؤية البيانات المحفوظة: `tail -f /var/gia_data/XAUUSD_M15.csv`

---
🦁 **GIA: Always Awake. Always Trading.**
