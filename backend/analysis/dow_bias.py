"""Category 15: Day of Week Bias (4%)"""

from datetime import date
import pandas as pd
from analysis.engine import CategoryScore

DOW_SCORES = {
    0: (5.5, "neutral"),   # Monday: mixed
    1: (7.0, "bullish"),   # Tuesday: historically strongest
    2: (6.0, "neutral"),   # Wednesday
    3: (6.5, "bullish"),   # Thursday: pre-employment data
    4: (5.0, "neutral"),   # Friday: window dressing, mixed
}


async def analyze(symbol: str, df: pd.DataFrame) -> CategoryScore:
    today = date.today()
    dow = today.weekday()
    score, direction = DOW_SCORES.get(dow, (5.0, "neutral"))
    signals = [{"name": "day_of_week", "dow": dow, "day_name": ["Mon","Tue","Wed","Thu","Fri"][dow]}]
    weight = 4.0
    return CategoryScore("dow_bias", weight, score, weight * score / 10, direction, signals,
                        f"DOW={['Mon','Tue','Wed','Thu','Fri'][dow]}, historical bias={'bullish' if direction=='bullish' else 'neutral'}")
