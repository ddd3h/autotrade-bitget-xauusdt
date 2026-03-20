import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from dataclasses import dataclass
from app.strategy.base import BaseStrategy

@dataclass
class StrategyParams:
    ema_fast: int = 12
    ema_mid: int = 26
    ema_trend: int = 50
    ema_base: int = 100
    atr_len: int = 14
    atr_min: float = 0.5
    pullback_bars: int = 5
    tp_usd: float = 10.0
    sl_usd: float = 5.0
    hold_max_minutes: int = 60
    strict_trigger: bool = False

class StrategyEngine(BaseStrategy):
    def __init__(self, params: StrategyParams):
        self.params = params

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators required for the strategy."""
        df = df.copy()
        
        # EMAs
        df['ema_fast'] = df['close'].ewm(span=self.params.ema_fast, adjust=False).mean()
        df['ema_mid'] = df['close'].ewm(span=self.params.ema_mid, adjust=False).mean()
        df['ema_trend'] = df['close'].ewm(span=self.params.ema_trend, adjust=False).mean()
        df['ema_base'] = df['close'].ewm(span=self.params.ema_base, adjust=False).mean()
        
        # ATR
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=self.params.atr_len).mean()
        
        return df

    def get_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate entry and exit signals."""
        df = self.calculate_indicators(df)
        
        # 1. Trend Condition
        df['trend_up'] = (df['ema_fast'] > df['ema_mid']) & \
                         (df['ema_mid'] > df['ema_trend']) & \
                         (df['ema_trend'] > df['ema_base']) & \
                         (df['close'] > df['ema_trend'])
                         
        df['trend_down'] = (df['ema_fast'] < df['ema_mid']) & \
                           (df['ema_mid'] < df['ema_trend']) & \
                           (df['ema_trend'] < df['ema_base']) & \
                           (df['close'] < df['ema_trend'])
                           
        # 2. Volatility Condition
        df['volatility_ok'] = df['atr'] >= self.params.atr_min
        
        # 3. Pullback Detection
        # Long Pullback: Recent Low reaches or goes below EMA_fast or EMA_mid
        df['recent_low'] = df['low'].rolling(window=self.params.pullback_bars).min()
        df['pullback_long'] = df['recent_low'] <= df[['ema_fast', 'ema_mid']].max(axis=1)
        
        # Short Pullback: Recent High reaches or goes above EMA_fast or EMA_mid
        df['recent_high'] = df['high'].rolling(window=self.params.pullback_bars).max()
        df['pullback_short'] = df['recent_high'] >= df[['ema_fast', 'ema_mid']].min(axis=1)
        
        # 4. Re-acceleration Trigger
        # Long Re-acceleration
        df['re_accel_long'] = (df['close'] > df['ema_fast']) & (df['close'] > df['open'])
        if self.params.strict_trigger:
            df['re_accel_long'] &= (df['close'] > df['high'].shift(1))
        else:
            df['re_accel_long'] &= (df['high'] > df['high'].shift(1))
            
        # Short Re-acceleration
        df['re_accel_short'] = (df['close'] < df['ema_fast']) & (df['close'] < df['open'])
        if self.params.strict_trigger:
            df['re_accel_short'] &= (df['close'] < df['low'].shift(1))
        else:
            df['re_accel_short'] &= (df['low'] < df['low'].shift(1))
            
        # Final Entry Signals
        df['entry_long'] = df['trend_up'] & df['volatility_ok'] & df['pullback_long'] & df['re_accel_long']
        df['entry_short'] = df['trend_down'] & df['volatility_ok'] & df['pullback_short'] & df['re_accel_short']
        
        return df

    def check_exit(self, position: Dict, current_candle: pd.Series, prev_candle: pd.Series) -> Optional[str]:
        """Check for exit conditions based on current position and market state."""
        side = position['side']
        entry_price = position['entry_price']
        current_price = current_candle['close']
        
        # PnL calculations (simplified for signal check)
        pnl = (current_price - entry_price) * position['quantity'] if side == 'long' else (entry_price - current_price) * position['quantity']
        
        if side == 'long':
            # Long Exit Conditions
            if current_price < current_candle['ema_fast']: return "price_below_ema_fast"
            if current_candle['ema_fast'] < current_candle['ema_mid']: return "ema_dead_cross"
            if current_price < prev_candle['low']: return "low_break"
            if pnl >= self.params.tp_usd: return "take_profit"
            if pnl <= -self.params.sl_usd: return "stop_loss"
            # Time limit check should be handled in execution loop
            
        elif side == 'short':
            # Short Exit Conditions
            if current_price > current_candle['ema_fast']: return "price_above_ema_fast"
            if current_candle['ema_fast'] > current_candle['ema_mid']: return "ema_golden_cross"
            if current_price > prev_candle['high']: return "high_break"
            if pnl >= self.params.tp_usd: return "take_profit"
            if pnl <= -self.params.sl_usd: return "stop_loss"
            
        return None
