
import requests
import pandas as pd
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import os

class NewsGuard:
    """
    🦁 GIA News Guard (Institutional Edition)
    Fetches economic data and provides safety signals.
    """
    RSS_URL = "https://www.forexfactory.com/ff_calendar_thisweek.xml"
    CACHE_FILE = "news_cache.pkl"
    
    def __init__(self):
        self.news_df = pd.DataFrame()
        self.last_fetch = None
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.CACHE_FILE):
            try:
                self.news_df = pd.read_pickle(self.CACHE_FILE)
                self.last_fetch = datetime.fromtimestamp(os.path.getmtime(self.CACHE_FILE))
            except:
                self.news_df = pd.DataFrame()

    def fetch_news(self, force=False):
        """Fetches high-impact news from ForexFactory."""
        now = datetime.now()
        if not force and self.last_fetch and (now - self.last_fetch) < timedelta(hours=6):
            return self.news_df

        self.last_fetch = now # Set now to prevent spamming on failure
        try:
            response = requests.get(self.RSS_URL, timeout=5)
            if response.status_code != 200: return self.news_df

            tree = ET.fromstring(response.content)
            events = []
            for item in tree.findall('event'):
                event = {
                    'title': item.find('title').text,
                    'country': item.find('country').text,
                    'date': item.find('date').text,
                    'time': item.find('time').text,
                    'impact': item.find('impact').text,
                    'forecast': item.find('forecast').text if item.find('forecast') is not None else ""
                }
                
                # Parse datetime
                try:
                    dt_str = f"{event['date']} {event['time']}"
                    # ForexFactory RSS dates are usually like '01-02-2026' '10:00am'
                    dt = datetime.strptime(dt_str, "%m-%d-%Y %I:%M%p")
                    event['datetime'] = dt
                except:
                    continue
                
                events.append(event)

            self.news_df = pd.DataFrame(events)
            self.news_df.to_pickle(self.CACHE_FILE)
            print(f"✅ GIA News Center: Calendar Synchronized ({len(self.news_df)} events).")
            return self.news_df
        except Exception as e:
            print(f"⚠️ News Fetch Error: {e}")
            return self.news_df

    def check_safety(self, current_time=None):
        """
        Returns (is_safe, reason)
        Safe if no HIGH impact news within 15 mins.
        """
        if self.news_df.empty:
            self.fetch_news()
            if self.news_df.empty: return True, "No news data"

        now = current_time or datetime.now()
        is_naive = now.tzinfo is None
        
        # Filter for High Impact news relating to Gold (USD)
        danger_zone = self.news_df[
            (self.news_df['impact'] == 'High') & 
            (self.news_df['country'].isin(['USD', 'ALL']))
        ]
        
        for _, event in danger_zone.iterrows():
            event_dt = event['datetime']
            # Mirror the timezone state of 'now' to avoid subtraction errors
            if is_naive and event_dt.tzinfo is not None:
                event_dt = event_dt.replace(tzinfo=None)
            elif not is_naive and event_dt.tzinfo is None:
                event_dt = pytz.UTC.localize(event_dt)
                
            diff = (event_dt - now).total_seconds() / 60.0 # mins
            
            # 15 min buffer before and after
            if -15 <= diff <= 15:
                return False, f"High Impact News: {event['title']} ({event['country']}) at {event['time']}"
        
        return True, ""

if __name__ == "__main__":
    guard = NewsGuard()
    guard.fetch_news(force=True)
    is_safe, reason = guard.check_safety()
    print(f"Status: {'SAFE' if is_safe else 'DANGER'}")
    if not is_safe: print(f"Reason: {reason}")
