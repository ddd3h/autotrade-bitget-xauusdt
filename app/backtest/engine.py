import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.strategy.engine import StrategyEngine, StrategyParams
from app.config import settings
from app.logger import export_logger as logger
from app.models.trade import Trade

class BacktestEngine:
    def __init__(self, df: pd.DataFrame, strategy: StrategyEngine):
        self.df = strategy.get_signals(df)
        self.strategy = strategy
        self.equity = settings.INITIAL_EQUITY
        self.current_position: Optional[Trade] = None
        self.trades: List[Trade] = []
        self.equity_curve = [self.equity]

    def run(self):
        logger.info("Starting backtest...")
        
        # We need a small lookback for indicators to stabilize
        start_idx = 50 
        
        for i in range(start_idx, len(self.df)):
            current_bar = self.df.iloc[i]
            prev_bar = self.df.iloc[i-1]
            timestamp = self.df.index[i]
            
            # 1. Check Emergency SL if position is open
            if self.current_position:
                if settings.EMERGENCY_STOP_LOSS_ENABLED:
                    side_str = self.current_position.side
                    entry_price = self.current_position.entry_price
                    curr_price = current_bar['close']
                    
                    if side_str == 'long':
                        loss_pct = (entry_price - curr_price) / entry_price
                    else: # short
                        loss_pct = (curr_price - entry_price) / entry_price
                        
                    if loss_pct >= settings.EMERGENCY_STOP_LOSS_THRESHOLD:
                        self._close_position(current_bar, timestamp, "EMERGENCY_STOP_LOSS")
                        continue

            # 2. Check for Strategy Exit
            if self.current_position:
                exit_reason = self.strategy.check_exit(self.current_position.model_dump(), current_bar, prev_bar)
                if exit_reason:
                    self._close_position(current_bar, timestamp, exit_reason)
                    continue

            # 3. Check for Strategy Entry
            if not self.current_position:
                if current_bar.get('entry_long'):
                    self._open_position(current_bar, timestamp, 'long')
                elif current_bar.get('entry_short'):
                    self._open_position(current_bar, timestamp, 'short')
            
            self.equity_curve.append(self.equity)
            
        logger.info(f"Backtest completed. Final equity: {self.equity:.2f}")
        return self.get_results()

    def _open_position(self, bar: pd.Series, timestamp: datetime, side: str):
        price = float(bar['close'])
        
        # Calculate quantity based on POSITION_FRACTION and LEVERAGE
        margin_used = self.equity * settings.POSITION_FRACTION
        quantity = (margin_used * settings.LEVERAGE) / price
        
        # Simulating slippage on entry
        slippage_pct = settings.SLIPPAGE_BPS / 10000
        entry_price = price * (1 + slippage_pct) if side == 'long' else price * (1 - slippage_pct)
        
        fee = entry_price * quantity * settings.FEE_RATE
        slippage_cost = abs(entry_price - price) * quantity
        
        self.current_position = Trade(
            symbol=settings.SYMBOL,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            entry_time=timestamp,
            fee=fee,
            slippage=slippage_cost
        )
        
        # Deduct entry costs
        self.equity -= (fee + slippage_cost)

    def _close_position(self, bar: pd.Series, timestamp: datetime, reason: str):
        if not self.current_position:
            return
            
        exit_price_raw = float(bar['close'])
        slippage_pct = settings.SLIPPAGE_BPS / 10000
        exit_price = exit_price_raw * (1 - slippage_pct) if self.current_position.side == 'long' else exit_price_raw * (1 + slippage_pct)
        
        self.current_position.exit_price = exit_price
        self.current_position.exit_time = timestamp
        self.current_position.exit_reason = reason
        
        # Calculate PnL
        if self.current_position.side == 'long':
            self.current_position.gross_pnl = (exit_price - self.current_position.entry_price) * self.current_position.quantity
        else:
            self.current_position.gross_pnl = (self.current_position.entry_price - exit_price) * self.current_position.quantity
            
        fee_exit = exit_price * self.current_position.quantity * settings.FEE_RATE
        slippage_exit = abs(exit_price - exit_price_raw) * self.current_position.quantity
        
        self.current_position.fee += fee_exit
        self.current_position.slippage += slippage_exit
        self.current_position.calculate_net_pnl()
        
        self.equity += self.current_position.gross_pnl - (fee_exit + slippage_exit)
        
        self.trades.append(self.current_position)
        self.current_position = None

    def get_results(self):
        if not self.trades:
            return {"msg": "No trades executed."}
            
        df_trades = pd.DataFrame([t.model_dump() for t in self.trades])
        
        net_pnl = df_trades['net_pnl'].sum()
        win_rate = len(df_trades[df_trades['net_pnl'] > 0]) / len(df_trades)
        max_drawdown = self._calculate_max_drawdown()
        total_trades = len(self.trades)
        
        verdict = self.get_verdict(net_pnl, win_rate, max_drawdown, total_trades)
        
        results = {
            "total_trades": total_trades,
            "win_rate": win_rate,
            "gross_pnl": df_trades['gross_pnl'].sum(),
            "fee_total": df_trades['fee'].sum(),
            "slippage_total": df_trades['slippage'].sum(),
            "funding_total": df_trades['funding'].sum(),
            "net_pnl": net_pnl,
            "final_equity": self.equity,
            "max_drawdown": max_drawdown,
            "avg_holding_time": df_trades.apply(lambda x: (x['exit_time'] - x['entry_time']).total_seconds() / 60, axis=1).mean(),
            "verdict": verdict
        }
        return results

    def get_verdict(self, net_pnl: float, win_rate: float, mdd: float, count: int) -> Dict[str, Any]:
        """Evaluate backtest results against specific criteria."""
        criteria = {
            "Net PnL > 0": net_pnl > 0,
            "Win Rate >= 55%": win_rate >= 0.55,
            "Max Drawdown <= 20%": abs(mdd) <= 0.20,
            "Trades Count >= 10": count >= 10
        }
        
        all_passed = all(criteria.values())
        return {
            "status": "合格 (PASS)" if all_passed else "不合格 (FAIL)",
            "details": criteria
        }

    def _calculate_max_drawdown(self):
        if not self.equity_curve: return 0
        series = pd.Series(self.equity_curve)
        roll_max = series.cummax()
        drawdown = (series - roll_max) / roll_max
        return drawdown.min()
