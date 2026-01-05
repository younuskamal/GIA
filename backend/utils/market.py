
from datetime import datetime, time, timedelta
import pytz

class MarketGuard:
    """
    🦁 GIA Market Guard (Institutional Edition)
    Handles market sessions, gap protection, and opening/closing rituals.
    """
    
    def __init__(self, timezone="UTC"):
        self.tz = pytz.timezone(timezone)

    def _sync_time(self, dt):
        """Ensures input time matches the guard's timezone state."""
        if dt is None: return datetime.now(self.tz)
        # If input is naive, we treat internal targets as naive too for subtraction
        return dt

    def is_market_open(self, current_time=None):
        """Checks if Gold (XAUUSD) market is active."""
        now = self._sync_time(current_time)
        
        # Weekend Check: Friday 22:00 to Sunday 23:00 UTC
        weekday = now.weekday() # 0=Mon, 4=Fri, 5=Sat, 6=Sun
        
        # Friday Close
        if weekday == 4 and now.time() >= time(22, 0):
            return False
        # Saturday
        if weekday == 5:
            return False
        # Sunday Open
        if weekday == 6 and now.time() < time(23, 0):
            return False
            
        # Daily Break: 22:00 - 23:00 UTC
        if now.time() >= time(22, 0) and now.time() < time(23, 0):
            return False
            
        return True

    def check_gap_risk(self, current_time=None):
        """
        Returns (is_safe, reason)
        Prevents trading 30m before close and 30m after open.
        """
        now = self._sync_time(current_time)
        is_naive = now.tzinfo is None
        weekday = now.weekday()
        curr_time = now.time()
        
        # 1. Friday Close Gap Protection (30 mins before 22:00)
        if weekday == 4:
            close_time = datetime.combine(now.date(), time(22, 0))
            if not is_naive: close_time = close_time.replace(tzinfo=self.tz)
            
            if (close_time - now) < timedelta(minutes=30):
                return False, "Market Closing Gap (Friday)"
                
        # 2. Daily Close Gap Protection (30 mins before 22:00)
        if curr_time >= time(21, 30) and curr_time < time(22, 0):
            return False, "Daily Market Closing Gap"
            
        # 3. Sunday Open Gap Protection (5 mins after 23:00)
        if weekday == 6:
            open_time = datetime.combine(now.date(), time(23, 0))
            if not is_naive: open_time = open_time.replace(tzinfo=self.tz)

            if now >= open_time and (now - open_time) < timedelta(minutes=5):
                return False, "Market Opening Volatility (Sunday)"
                
        # 4. Daily Open Gap Protection (5 mins after 23:00)
        if curr_time >= time(23, 0) and curr_time < time(23, 5):
            return False, "Daily Market Opening Volatility"

        return True, ""

if __name__ == "__main__":
    guard = MarketGuard()
    open_status = guard.is_market_open()
    safe_status, reason = guard.check_gap_risk()
    print(f"Market Open: {open_status}")
    print(f"Safety Status: {safe_status} | Reason: {reason}")
