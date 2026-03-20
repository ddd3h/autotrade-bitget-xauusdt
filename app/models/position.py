from typing import Optional
from pydantic import BaseModel

class Position(BaseModel):
    symbol: str
    side: str  # "long", "short", or "none"
    size: float
    entry_price: float
    leverage: int
    unrealized_pnl: float = 0.0
    liquidation_price: Optional[float] = None
    
    @property
    def is_open(self) -> bool:
        return self.side != "none" and self.size > 0
