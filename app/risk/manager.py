from app.config import settings
from app.logger import export_logger as logger

class RiskManager:
    def __init__(self, initial_equity: float):
        self.equity = initial_equity
        self.daily_loss = 0.0
        self.consecutive_losses = 0

    def calculate_position_size(self, entry_price: float, margin_fraction: float = 0.4) -> float:
        """
        Calculate quantity based on fixed margin fraction:
        Total Notional = Equity * MarginFraction * Leverage
        Quantity = Total Notional / EntryPrice
        """
        if entry_price <= 0:
            return 0.0
            
        # 40% of equity as margin, multiplied by leverage
        total_notional = self.equity * margin_fraction * settings.LEVERAGE
        quantity = total_notional / entry_price
        
        logger.info(f"Position Size Calculation: Equity={self.equity:.2f}, Margin={margin_fraction*100}%, Leverage={settings.LEVERAGE}, Notional={total_notional:.2f}, Qty={quantity:.4f}")
        
        return quantity

    def check_daily_limit(self) -> bool:
        if self.equity <= 0:
            logger.warning("Equity is 0. Trading halted.")
            return False
            
        limit = self.equity * settings.DAILY_LOSS_LIMIT
        if self.daily_loss >= limit:
            logger.warning(f"Daily loss limit reached: {self.daily_loss} / {limit}")
            return False
        return True

    def update_metrics(self, pnl: float):
        if pnl < 0:
            self.daily_loss += abs(pnl)
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
            
    def reset_daily(self):
        self.daily_loss = 0.0
