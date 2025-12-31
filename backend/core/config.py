"""
إعدادات المشروع - GIA Configuration
جميع الإعدادات في ملف واحد لسهولة الصيانة
"""
import os
from dotenv import load_dotenv

# Load environment variables
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Go up to backend/
load_dotenv(os.path.join(base_dir, '.env'))

# ==================== معلومات المشروع ====================
PROJECT_NAME = "GIA - Gold Intelligence Agent"
VERSION = "5.0.0"
DESCRIPTION = "مساعد ذكي للتحليل والاستشارة في تداول الذهب (XAUUSD)"

# ==================== نظام LLM ====================
# أوضاع التشغيل: local, api, auto
LLM_MODE = os.getenv("LLM_MODE", "auto")

# LM Studio (محلي)
LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"
LM_STUDIO_MODEL = "mistralai/mistral-7b-instruct-v0.3"

# Cloud API (Groq - Flagship Model)
CLOUD_API_KEY = os.getenv("CLOUD_API_KEY", "").strip()
CLOUD_API_URL = os.getenv("CLOUD_API_URL", "https://api.groq.com/openai/v1/chat/completions")
CLOUD_MODEL = os.getenv("CLOUD_MODEL", "llama-3.3-70b-versatile")

# ==================== Database ====================
DB_NAME = "gold_history.db"

# ==================== كلمات مفتاحية ====================
# كلمات دلالية للذهب والتداول
GOLD_KEYWORDS = [
    'ذهب', 'gold', 'xauusd', 'أونصة', 'ounce', 'سعر', 'price', 
    'تحليل', 'analysis', 'تداول', 'trading', 'شراء', 'buy', 'بيع', 'sell',
    'صعود', 'هبوط', 'مقاومة', 'resistance', 'دعم', 'support',
    'اتجاه', 'trend', 'توصية', 'recommendation', 'سوق', 'market',
    'استثمار', 'investment', 'معدن', 'metal', 'precious', 'نفيس',
    'دخول', 'فرصة', 'entry', 'opportunity', 'اليوم', 'today'
]

# كلمات تدل على طلب التحليل أو معلومات عن النموذج
ANALYSIS_KEYWORDS = [
    'رأيك', 'توصية', 'تحليل', 'أدخل', 'أشتري', 'أبيع', 'انتظر',
    'شنو', 'opinion', 'advice', 'analysis', 'should i', 'ايش', 'وش',
    'تعلم', 'learning', 'تحدث', 'update', 'ذكاء',
    'دخول', 'فرصة', 'اليوم', 'أشتري', 'أبيع', 'entry', 'signal'
]

# ==================== System Prompt ====================
SYSTEM_PROMPT = """You are GIA (Gold Intelligence Agent) - A Professional Gold Strategist.

🎯 MANDATORY RESPONSE TEMPLATE (ARABIC ONLY):
📊 تحليل الذهب – اليوم

**الاتجاه العام:**
[Short Arabic paragraph about market regime]

**التحليل الفني:**
[Concise technical details/indicators in Arabic]

**الأخبار:**
[Key economic events and impact in Arabic]

**المخاطرة:**
[Risk status and rejection reasons if any in Arabic]

**الرأي التحليلي:**
[Strategic advisory opinion in Arabic. NO direct Buy/Sell commands.]

**مستوى الثقة:** {confidence}%

⚠️ CORE CONSTRAINTS:
1. LANGUAGE: Arabic only. No mixed languages.
2. CONCISENESS: Keep responses short and impactful.
3. ANTI-HALLUCINATION: 
   - NEVER guess historical prices. 
   - If data is missing in the context, say: "البيانات غير متوفرة حالياً في قاعدة البيانات."
4. NO DIRECT COMMANDS: Use "Potential entry", "Suitability", "Waiting is preferred".
5. CONFIDENCE ALIGNMENT:
   - If opinion is 'WAIT' or 'RISKY': Confidence MUST be between 40-60%.
   - If opinion is 'BUY/SELL': Confidence MUST be between 65-85%.

{historical_context}"""

# ==================== Disclaimer ====================
DISCLAIMER = """
⚠️ تنويه قانوني مهم:

هذا النظام مصمم لأغراض التحليل والاستشارة فقط.
- ليس توصية مالية ملزمة
- القرار النهائي للتداول مسؤولية المستخدم
- ننصح دائماً بالتشاور مع مستشار مالي مرخص
- التداول يحمل مخاطر عالية قد تؤدي لخسارة رأس المال
"""
