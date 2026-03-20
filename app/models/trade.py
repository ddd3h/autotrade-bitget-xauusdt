from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class Trade(BaseModel):
    id: Optional[str] = None
    symbol: str
    side: str  # "buy" or "sell"
    entry_price: float
    entry_time: datetime
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    quantity: float
    leverage: int = 20
    
    # PnL Breakdown
    gross_pnl: float = 0.0
    fee: float = 0.0
    slippage: float = 0.0
    funding: float = 0.0
    net_pnl: float = 0.0
    
    exit_reason: Optional[str] = None

    def calculate_net_pnl(self):
        self.net_pnl = self.gross_pnl - self.fee - self.slippage - self.funding
        return self.net_pnl
