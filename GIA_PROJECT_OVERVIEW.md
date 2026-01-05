# 🦁 GIA: Global Institutional Advisor - Developer's Deep Dive
**Technical Architecture & Engineering Documentation v4.0**

هذا المستند موجه للمبرمجين لفهم هيكلية النظام (Architecture)، تدفق البيانات (Data Flow)، والتقنيات المستخدمة في بناء GIA.

---

## 🏗️ 1. Architecture Overview (الهيكلية)
يعتمد النظام على هيكلية **Decoupled Event-Driven Architecture**. تم فصل محرك التنفيذ عن محرك التحليل لضمان الاستقرار.

*   **Execution Layer (Twisted Engine):** يستخدم مكتبة `Twisted` لإدارة اتصالات الـ WebSocket مع cTrader OpenAPI بشكل غير متزامن (Asynchronous).
*   **Intelligence Layer (AI Inference):** يعمل كمحرك "عديم الحالة" (Stateless) يستقبل البيانات ويعطي القرار.
*   **Data Bridge (CSV Sync):** يعمل كمخزن بيانات مركزي (Shared Buffer) يربط بين سرعة الـ API وبين احتياجات الـ Dataframe في Pandas.

---

## 📡 2. Data Acquisition Pipeline (تدفق البيانات)
بدلاً من قراءة ملفات تصدير خارجية، قمنا ببناء **Autonomous Data Sync**:

1.  **Request Cycle:** يتم إرسال `ProtoOAGetTrendbarsReq` كل 10-15 ثانية لطلب فريمات (M1, M15, M30, H1).
2.  **Protocol Parsing:** يتم استقبال الـ `Trendbars` من نوع `Protobuf` وتصحيح الـ Price Deltas (علاقة الـ Low بالـ Open/High/Close) وتحويل الـ Timestamps من دقائق إلى `DATETIME`.
3.  **IO Sync:** يتم كتابة البيانات المستلمة فوراً في ملفات CSV داخل `C:\GIA_DATA` باستخدام `threading` لضمان عدم حجز الـ Main Loop.

---

## 🧠 3. Feature Engineering & AI (هندسة الميزات)
النظام لا يستخدم السعر الخام، بل يقوم بـ **Feature Transformation** لحظي:

*   **Multi-Timeframe Logic (MTF):** عند كل Trigger، يقوم الكود بجمع بيانات 3 فريمات زمنية، وعمل `merge_asof` (تزامن زمني ذكي) لبناء سطر بيانات واحد يحتوي على وضع الـ (M15, M30, H1).
*   **Indicator Fusion:** يتم حساب (RSI, ATR, MACD, Bollinger, EMA) لكل فريم، مع حساب "انحراف السعر عن المتوسطات" (Distance Mapping).
*   **Entropy & Velocity:** ميزات مؤسساتية تحسب سرعة السعر (Acceleration) ومدى عشوائية الحركة (Entropy) لتجنب التداول في الأسواق الضعيفة.
*   **XGBoost Inference:** يتم تمرير الميزات لنموذج XGBoost المدرب مسبقاً، والذي يعطي `predict_proba` (احتمالات الدخول).

---

## 🛡️ 4. Execution & Risk Management (التنفيذ والمخاطرة)
بمجرد صدور إشارة من الـ AI، تمر عبر **GIA Gatekeeper**:

1.  **NewsGuard (Web Scraper):** يقوم بجلب تقويم ForexFactory وفحصه برمجياً. إذا كان هناك خبر "High Impact" قريب، يتم عمل `Signal Block`.
2.  **Dynamic Lot Sizing:** يتم حساب اللوت برمجياً بناءً على: `Equity * Risk% / (Fixed_SL * Pip_Value)`.
3.  **Institutional Physics:** إضافة Latency متعمد في الباك تست لمحاكاة تأخر الشبكة، واستخدام `SpotEvents` في الـ Live للحصول على أدق سعر (Bid/Ask) قبل التنفيذ.

---

## � 5. Tech Stack Stack (المكونات التقنية)
*   **Language:** Python 3.10
*   **Async Framework:** `Twisted` (إدارة الـ WebSocket الوعرة).
*   **Serialization:** `Joblib` & `Pickle` (مع حقن `MockEncoder` في الـ `__main__` namespace لحل مشاكل الـ Deserialization).
*   **Data Science:** `Pandas` (Vectorized calculations), `NumPy` (Math logic), `Scikit-learn` (Label Encoding).
*   **API Protocol:** `Google Protobuf` (للتواصل مع OpenAPI).

---

## 🛠️ 6. Self-Healing & Logging (الاستقرار)
*   **Reconnect Logic:** محرك التنفيذ مبرمج بـ `While True` مع `Try-Except` شاملة. في حال سقوط الاتصال، يقوم الـ `Bridge` بإعادة الـ Handshake تلقائياً.
*   **Audit Log:** يتم تسجيل كل `Packet` وكل `Decision` في ملف `live_audit.log` بصيغة JSON-ready للتحليل لاحقاً.

---
*هذا النظام ليس مجرد سكربت، بل هو Enterprise Trading Environment مصغر يجمع بين علوم البيانات وهندسة الشبكات.*

🦁 **GIA: Engineered for Profit.**
