"""
إدارة قاعدة البيانات للأسعار التاريخية للذهب
"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import random

# مسار قاعدة البيانات
DB_PATH = Path(__file__).parent.parent / "gold_history.db"

def init_database():
    """إنشاء قاعدة البيانات والجداول"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # إنشاء جدول الأسعار التاريخية
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gold_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # إنشاء جدول الأخبار الاقتصادية
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS news_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            sentiment INTEGER NOT NULL,
            impact TEXT NOT NULL,
            category TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, title)
        )
    """)
    
    conn.commit()
    conn.close()

def populate_sample_data():
    """ملء البيانات التجريبية (آخر 90 يوم)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    current_date = datetime.now()
    
    # Check if price data exists
    cursor.execute("SELECT COUNT(*) FROM gold_prices")
    count = cursor.fetchone()[0]
    
    if count == 0:
        print("📊 Generating sample price data...")
        
        # Generation for last 90 days
        base_price = 2050.0
        
        for i in range(90, 0, -1):
            date = current_date - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            
            # Generate realistic prices
            daily_change = random.uniform(-30, 30)
            open_price = base_price + random.uniform(-5, 5)
            close_price = open_price + daily_change
            high_price = max(open_price, close_price) + random.uniform(5, 15)
            low_price = min(open_price, close_price) - random.uniform(5, 15)
            
            try:
                cursor.execute("""
                    INSERT INTO gold_prices (date, open, high, low, close)
                    VALUES (?, ?, ?, ?, ?)
                """, (date_str, round(open_price, 2), round(high_price, 2), 
                      round(low_price, 2), round(close_price, 2)))
                base_price = close_price
            except sqlite3.IntegrityError:
                pass
        
        conn.commit()
        print(f"✅ Added {90} days of sample price data.")
    
    # Check if news events exist
    cursor.execute("SELECT COUNT(*) FROM news_events")
    news_count = cursor.fetchone()[0]
    
    if news_count == 0:
        print("📰 Generating sample economic news...")
        
        sample_news = [
            # أخبار إيجابية للذهب (sentiment = +1)
            {
                "date": (current_date - timedelta(days=5)).strftime("%Y-%m-%d"),
                "title": "ارتفاع معدل التضخم الأمريكي إلى 4.5%",
                "description": "البيانات تشير إلى زيادة الضغوط التضخمية",
                "sentiment": 1,
                "impact": "HIGH",
                "category": "Inflation"
            },
            {
                "date": (current_date - timedelta(days=10)).strftime("%Y-%m-%d"),
                "title": "الفيدرالي يشير لاحتمالية خفض الفائدة",
                "description": "تصريحات FOMC تدعم المعادن الثمينة",
                "sentiment": 1,
                "impact": "HIGH",
                "category": "Interest Rate"
            },
            {
                "date": (current_date - timedelta(days=15)).strftime("%Y-%m-%d"),
                "title": "تراجع الدولار الأمريكي أمام العملات الرئيسية",
                "description": "ضعف الدولار يدعم أسعار الذهب",
                "sentiment": 1,
                "impact": "MEDIUM",
                "category": "Currency"
            },
            {
                "date": (current_date - timedelta(days=20)).strftime("%Y-%m-%d"),
                "title": "توترات جيوسياسية في الشرق الأوسط",
                "description": "المستثمرون يتجهون للملاذات الآمنة",
                "sentiment": 1,
                "impact": "HIGH",
                "category": "Geopolitical"
            },
            
            # أخبار سلبية للذهب (sentiment = -1)
            {
                "date": (current_date - timedelta(days=3)).strftime("%Y-%m-%d"),
                "title": "بيانات الوظائف الأمريكية أقوى من المتوقع",
                "description": "NFP يسجل 250 ألف وظيفة جديدة",
                "sentiment": -1,
                "impact": "HIGH",
                "category": "NFP"
            },
            {
                "date": (current_date - timedelta(days=7)).strftime("%Y-%m-%d"),
                "title": "الفيدرالي يثبت أسعار الفائدة عند 5.5%",
                "description": "استمرار السياسة النقدية المتشددة",
                "sentiment": -1,
                "impact": "HIGH",
                "category": "Interest Rate"
            },
            {
                "date": (current_date - timedelta(days=12)).strftime("%Y-%m-%d"),
                "title": "تحسن مؤشرات الثقة الاقتصادية الأمريكية",
                "description": "بيانات إيجابية تقلل الطلب على الملاذات الآمنة",
                "sentiment": -1,
                "impact": "MEDIUM",
                "category": "Economic Data"
            },
            
            # أخبار محايدة (sentiment = 0)
            {
                "date": (current_date - timedelta(days=2)).strftime("%Y-%m-%d"),
                "title": "مؤشر CPI يأتي متوافقاً مع التوقعات",
                "description": "التضخم عند 3.2% كما هو متوقع",
                "sentiment": 0,
                "impact": "MEDIUM",
                "category": "CPI"
            },
            {
                "date": (current_date - timedelta(days=8)).strftime("%Y-%m-%d"),
                "title": "البنوك المركزية الآسيوية تحتفظ باحتياطيات الذهب",
                "description": "استقرار في الطلب المؤسسي على الذهب",
                "sentiment": 0,
                "impact": "LOW",
                "category": "Central Banks"
            },
            {
                "date": (current_date - timedelta(days=18)).strftime("%Y-%m-%d"),
                "title": "إنتاج الذهب العالمي مستقر في Q4",
                "description": "لا تغييرات كبيرة في العرض",
                "sentiment": 0,
                "impact": "LOW",
                "category": "Supply"
            }
        ]
        
        for news in sample_news:
            try:
                cursor.execute("""
                    INSERT INTO news_events (date, title, description, sentiment, impact, category)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (news["date"], news["title"], news["description"], 
                      news["sentiment"], news["impact"], news["category"]))
            except sqlite3.IntegrityError:
                pass
        
        conn.commit()
        print(f"✅ Added {len(sample_news)} sample news events.")
    
    conn.close()

def get_price_by_date(date_str: str):
    """الحصول على سعر الذهب في تاريخ محدد"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT date, open, high, low, close
        FROM gold_prices
        WHERE date = ?
    """, (date_str,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            "date": result[0],
            "open": result[1],
            "high": result[2],
            "low": result[3],
            "close": result[4]
        }
    return None

def get_price_range(start_date: str = None, end_date: str = None, limit: int = 30):
    """الحصول على نطاق من الأسعار"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    query = "SELECT date, open, high, low, close FROM gold_prices"
    params = []
    
    if start_date and end_date:
        query += " WHERE date BETWEEN ? AND ?"
        params = [start_date, end_date]
    elif start_date:
        query += " WHERE date >= ?"
        params = [start_date]
    elif end_date:
        query += " WHERE date <= ?"
        params = [end_date]
    
    query += " ORDER BY date DESC LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()
    
    return [
        {
            "date": row[0],
            "open": row[1],
            "high": row[2],
            "low": row[3],
            "close": row[4]
        }
        for row in results
    ]

def get_latest_price():
    """الحصول على آخر سعر مسجل"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT date, open, high, low, close
        FROM gold_prices
        ORDER BY date DESC
        LIMIT 1
    """)
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            "date": result[0],
            "open": result[1],
            "high": result[2],
            "low": result[3],
            "close": result[4]
        }
    return None

# ==================== News Events Functions ====================
def get_recent_news(days: int = 7, limit: int = 10):
    """الحصول على الأخبار الأخيرة"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    cursor.execute("""
        SELECT date, title, description, sentiment, impact, category
        FROM news_events
        WHERE date >= ?
        ORDER BY date DESC
        LIMIT ?
    """, (cutoff_date, limit))
    
    results = cursor.fetchall()
    conn.close()
    
    return [
        {
            "date": row[0],
            "title": row[1],
            "description": row[2],
            "sentiment": row[3],
            "impact": row[4],
            "category": row[5]
        }
        for row in results
    ]

def get_news_by_date(date_str: str):
    """الحصول على أخبار يوم محدد"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT date, title, description, sentiment, impact, category
        FROM news_events
        WHERE date = ?
        ORDER BY 
            CASE impact
                WHEN 'HIGH' THEN 1
                WHEN 'MEDIUM' THEN 2
                WHEN 'LOW' THEN 3
            END
    """, (date_str,))
    
    results = cursor.fetchall()
    conn.close()
    
    return [
        {
            "date": row[0],
            "title": row[1],
            "description": row[2],
            "sentiment": row[3],
            "impact": row[4],
            "category": row[5]
        }
        for row in results
    ]

def get_high_impact_news(days: int = 30):
    """الحصول على الأخبار عالية التأثير فقط"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    cursor.execute("""
        SELECT date, title, description, sentiment, impact, category
        FROM news_events
        WHERE date >= ? AND impact = 'HIGH'
        ORDER BY date DESC
    """, (cutoff_date,))
    
    results = cursor.fetchall()
    conn.close()
    
    return [
        {
            "date": row[0],
            "title": row[1],
            "description": row[2],
            "sentiment": row[3],
            "impact": row[4],
            "category": row[5]
        }
        for row in results
    ]

# تهيئة قاعدة البيانات عند الاستيراد
init_database()
populate_sample_data()
