# 🤖 GIA - XGBoost Training Pipeline

## 📋 نظرة عامة

نظام كامل لتدريب نموذج XGBoost على بيانات الذهب مع تقييم شامل.

---

## 📊 البيانات

### Features المستخدمة:
1. **OHLC** (Open, High, Low, Close)
2. **Technical Indicators:**
   - RSI (14)
   - EMA (9, 21, 50)
   - ATR (14)
   - MACD + Signal
3. **Market Context:**
   - Trend (-1, 0, +1)
4. **News Impact:**
   - News Sentiment
   - News Impact Score

### Labeling:
- **BUY**: صعود > 0.5%
- **SELL**: نزول > 0.5%
- **WAIT**: تذبذب (بين -0.5% و +0.5%)

---

## 🚀 كيفية الاستخدام

### 1️⃣ تثبيت المكتبات
```bash
cd backend
pip install -r requirements.txt
```

### 2️⃣ تشغيل Pipeline الكامل
```bash
python run_training_pipeline.py
```

هذا سيقوم بـ:
- ✅ بناء Dataset
- ✅ تدريب XGBoost
- ✅ تقييم النموذج
- ✅ Backtesting
- ✅ حفظ النموذج المدرب

---

## 📁 الملفات المنتجة

| الملف | الوصف |
|------|-------|
| `gold_dataset.csv` | Dataset كامل مع features و labels |
| `xgboost_model.pkl` | النموذج المدرب |
| `training_results.json` | نتائج التدريب |
| `backtest_results.json` | نتائج الاختبار الرجعي |
| `model_evaluation.json` | تقييم نهائي + توصيات |

---

## 📊 المقاييس

### Training Metrics:
- Accuracy
- Precision per Class
- Recall per Class
- F1-Score

### Backtesting Metrics:
- **Overall Accuracy**
- **Win Rate** (نسبة النجاح الإجمالية)
- **BUY Win Rate** (نسبة نجاح إشارات الشراء)
- **SELL Win Rate** (نسبة نجاح إشارات البيع)
- **Max Drawdown** (أقصى انخفاض)
- **Total Return** (العائد الإجمالي المحاكى)
- **Confusion Matrix**

---

## ⚠️ ملاحظات مهمة

### البيانات الحالية:
- ❌ البيانات الحالية **تجريبية** (mock data)
- ⚠️ مناسبة للاختبار فقط - **ليست للإنتاج**

### للحصول على بيانات حقيقية:

#### Option 1: Yahoo Finance (مجاني)
```python
import yfinance as yf
gold = yf.download("GC=F", start="2024-01-01", end="2025-01-01")
```

#### Option 2: Alpha Vantage
```python
from alpha_vantage.timeseries import TimeSeries
ts = TimeSeries(key='YOUR_KEY')
data, meta = ts.get_daily(symbol='XAUUSD', outputsize='full')
```

#### Option 3: Trading View / MetaTrader
- تصدير بيانات من منصة تداول

---

## 🔧 تحسين النموذج

### إذا كانت النتائج ضعيفة:

#### 1. زيادة البيانات
```python
dataset = build_dataset(days=180)  # بدلاً من 90
```

#### 2. إضافة Features جديدة
```python
# في dataset_builder.py
df['volume'] = ...
df['bb_upper'] = ...
df['bb_lower'] = ...
df['stochastic'] = ...
```

#### 3. تعديل Labeling Thresholds
```python
# في dataset_builder.py
if price_change > 0.7:  # بدلاً من 0.5
    df.loc[i, 'label'] = 'BUY'
elif price_change < -0.7:
    df.loc[i, 'label'] = 'SELL'
```

#### 4. ضبط XGBoost Parameters
```python
# في train_model.py
params = {
    'max_depth': 8,  # زيادة العمق
    'learning_rate': 0.05,  # تقليل LR
    'n_estimators': 300,  # زيادة العدد
}
```

---

## 📈 متى يكون النموذج جاهزاً؟

| المقياس | الحد الأدنى | جيد | ممتاز |
|---------|-------------|-----|-------|
| Accuracy | 50% | 60% | 70%+ |
| BUY Win Rate | 50% | 55% | 65%+ |
| SELL Win Rate | 50% | 55% | 65%+ |
| Max Drawdown | < 20% | < 15% | < 10% |

---

## 🎯 الخطوات التالية

بعد التدريب الناجح:
1. ✅ النموذج محفوظ في `xgboost_model.pkl`
2. ✅ يمكن استخدامه في `ml_model.py`
3. ✅ الشات سيستخدمه تلقائياً

---

## 💡 نصائح

- 🔄 أعد التدريب شهرياً على بيانات جديدة
- 📊 راقب الأداء في التداول الفعلي
- ⚠️ استخدمه كأداة مساعدة - ليس قرار نهائي
- 🧪 اختبر على حساب تجريبي أولاً

---

## 🆘 استكشاف الأخطاء

### خطأ: "بيانات غير كافية"
→ زود عدد الأيام في `build_dataset()`

### خطأ: "دقة منخفضة جداً"
→ راجع Features و Labeling

### خطأ: "Imbalanced Classes"
→ عدّل thresholds للحصول على توازن أفضل

---

**صُنع بـ ❤️ لـ GIA**
