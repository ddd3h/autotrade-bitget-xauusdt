from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    class Config:
        from_attributes = True

class CandleSeries(BaseModel):
    symbol: str
    interval: str
    candles: List[Candle]

    def to_pandas(self):
        import pandas as pd
        df = pd.DataFrame([c.model_dump() for c in self.candles])
        df.set_index("timestamp", inplace=True)
        return df
