import asyncio
from datetime import datetime
import pandas as pd
from typing import Optional, Dict
from app.services.bitget_service import BitgetService
from app.strategy.engine import StrategyEngine
from app.risk.manager import RiskManager
from app.services.notification_service import NotificationService
from app.storage.database import StorageService
from app.logger import export_logger as logger
from app.config import settings

class ExecutionEngine:
    def __init__(self, bitget: BitgetService, strategy: StrategyEngine, risk: RiskManager, notifier: NotificationService, storage: StorageService):
        self.bitget = bitget
        self.strategy = strategy
        self.risk = risk
        self.notifier = notifier
        self.storage = storage
        self.is_paper = settings.RUN_MODE == "paper"
        self.current_pos: Optional[Dict] = None
        self.paper_stats = {"total_pnl": 0.0, "trades": 0}

    async def sync_position(self):
        """Sync local position state with exchange (Real) or keep local state (Paper)."""
        if self.is_paper:
            if self.current_pos:
                logger.info(f"[PAPER] Current position: {self.current_pos['side']} {self.current_pos['size']} at {self.current_pos['entry_price']}")
            return

        pos = await self.bitget.get_position(settings.SYMBOL)
        if pos:
            self.current_pos = {
                'side': pos['side'], 
                'size': abs(float(pos['contracts'])),
                'entry_price': float(pos['entryPrice']),
                'unrealized_pnl': float(pos['unrealizedPnl'])
            }
            logger.info(f"Synced position ({settings.RUN_MODE}): {self.current_pos}")
        else:
            self.current_pos = None
            
        # Update equity from real-time balance
        balance = await self.bitget.get_balance(settings.MARGIN_COIN)
        if balance > 0:
            self.risk.equity = balance
            logger.info(f"Updated RiskManager equity: {self.risk.equity:.2f} {settings.MARGIN_COIN}")

    async def execute_cycle(self, df: pd.DataFrame):
        """Run one iteration of the trading loop."""
        if df.empty: return
        
        # 1. Update Signals & Indicators
        df = self.strategy.get_signals(df)
        current_bar = df.iloc[-1]
        prev_bar = df.iloc[-2] if len(df) > 1 else current_bar
        current_price = float(current_bar['close'])
        
        # 2. Sync Exchange State
        await self.sync_position()
        
        if self.current_pos:
            # 3. Emergency Check (Every cycle, e.g. every 5s if holding)
            exit_reason = self._check_emergency_exit(current_price)
            if exit_reason:
                logger.warning(f"🚨 Emergency Exit triggered: {exit_reason} @ {current_price}")
                await self._close(exit_reason, current_price)
                return
            
            # 4. Strategy Exit Check
            # Using Strategy's specific check_exit(pos, current, prev)
            signal = self.strategy.check_exit(self.current_pos, current_bar, prev_bar)
            if signal:
                logger.info(f"Strategy Exit signal: {signal}")
                await self._close(signal, current_price)
        else:
            # 5. Strategy Entry Check
            if not self.risk.check_daily_limit():
                return

            if current_bar['long_entry']:
                logger.info("Strategy Entry: LONG")
                await self._open('buy', current_price)
            elif current_bar['short_entry']:
                logger.info("Strategy Entry: SHORT")
                await self._open('sell', current_price)

        # Save current state for web dashboard
        self.storage.save_status("current_state", {
            "position": self.current_pos,
            "equity": self.risk.equity + (self.current_pos['unrealized_pnl'] if self.current_pos else 0),
            "paper_stats": self.paper_stats if self.is_paper else None,
            "last_update": datetime.now().isoformat()
        })

    def _check_emergency_exit(self, current_price: float) -> Optional[str]:
        """Check if position should be closed due to N% loss (ESL)."""
        if not settings.EMERGENCY_STOP_LOSS_ENABLED or not self.current_pos:
            return None
            
        entry_price = self.current_pos.get('entry_price', 0)
        if entry_price <= 0: return None
        
        side = self.current_pos.get('side')
        threshold = settings.EMERGENCY_STOP_LOSS_THRESHOLD
        
        if side == 'long':
            loss_pct = (entry_price - current_price) / entry_price
        else: # short
            loss_pct = (current_price - entry_price) / entry_price
            
        if loss_pct >= threshold:
            logger.warning(f"🚨 EMERGENCY STOP LOSS: {side} @ {current_price} (Entry: {entry_price}, Loss: {loss_pct*100:.2f}%, Threshold: {threshold*100:.2f}%)")
            return "EMERGENCY_STOP_LOSS"
            
        return None

    async def _open(self, side: str, price: float):
        # Calculate size based on configurable fraction of equity (margin)
        quantity = self.risk.calculate_position_size(price, settings.POSITION_FRACTION)
        if quantity <= 0: return
        
        if self.is_paper:
            logger.info(f"[PAPER] Opening {side} position: {quantity} at {price}")
            self.current_pos = {
                'side': 'long' if side == 'buy' else 'short',
                'size': quantity,
                'entry_price': price,
                'entry_time_str': datetime.now().isoformat(),
                'unrealized_pnl': 0.0
            }
            await self.notifier.notify_trade("OPEN", settings.SYMBOL, side, price, quantity)
            return

        try:
            # Ensure leverage is set
            await self.bitget.set_leverage(settings.SYMBOL, settings.LEVERAGE)
            
            logger.info(f"Issuing {side} order for {quantity} @ {price} ({settings.RUN_MODE})")
            order = await self.bitget.create_market_order(settings.SYMBOL, side, quantity)
            logger.info(f"Successfully opened {side} position: {order.get('id')}")
            
            # Update local state immediately
            self.current_pos = {
                'side': 'long' if side == 'buy' else 'short',
                'size': quantity,
                'entry_price': price,
                'unrealized_pnl': 0.0
            }
            
            await self.notifier.notify_trade("OPEN", settings.SYMBOL, side, price, quantity)
        except Exception as e:
            logger.error(f"Failed to open position: {e}")

    async def _close(self, reason: str, price: float):
        """Close position handling both Paper and Real."""
        if not self.current_pos: return

        if self.is_paper:
            await self._close_paper(price, reason)
            return

        try:
            logger.info(f"Closing {self.current_pos['side']} position @ {price} due to {reason}")
            side = 'sell' if self.current_pos['side'] == 'long' else 'buy'
            
            order = await self.bitget.create_market_order(
                settings.SYMBOL, 
                side, 
                self.current_pos['size'], 
                params={'reduceOnly': True}
            )
            logger.info(f"Successfully closed position: {order.get('id')}")
            
            self.risk.update_metrics(self.current_pos.get('unrealized_pnl', 0.0))
            
            await self.notifier.notify_trade(
                "CLOSE", settings.SYMBOL, self.current_pos['side'], 
                price, self.current_pos['size'], reason
            )
            
            # Save to DB
            self.storage.save_trade({
                "id": f"real_{int(datetime.now().timestamp())}",
                "symbol": settings.SYMBOL,
                "side": self.current_pos['side'],
                "entry_price": self.current_pos['entry_price'],
                "entry_time": datetime.now().isoformat(),
                "exit_price": price,
                "exit_time": datetime.now().isoformat(),
                "quantity": self.current_pos['size'],
                "gross_pnl": self.current_pos.get('unrealized_pnl', 0.0),
                "fee": price * self.current_pos['size'] * settings.FEE_RATE,
                "net_pnl": self.current_pos.get('unrealized_pnl', 0.0) - (price * self.current_pos['size'] * settings.FEE_RATE),
                "exit_reason": reason,
                "mode": settings.RUN_MODE
            })
            
            self.current_pos = None
        except Exception as e:
            logger.error(f"Failed to close position: {e}")

    async def _close_paper(self, price: float, reason: str):
        """Simulate closing a paper position."""
        pnl = (price - self.current_pos['entry_price']) * self.current_pos['size']
        if self.current_pos['side'] == 'short':
             pnl = -pnl
             
        self.paper_stats['total_pnl'] += pnl
        self.paper_stats['trades'] += 1
        
        logger.info(f"[PAPER] Closed {self.current_pos['side']} at {price}. Reason: {reason}. PnL: {pnl:.2f}")
        
        await self.notifier.notify_trade(
            "CLOSE", settings.SYMBOL, self.current_pos['side'], 
            price, self.current_pos['size'], reason
        )
        
        # Save to DB
        self.storage.save_trade({
            "id": f"paper_{int(datetime.now().timestamp())}",
            "symbol": settings.SYMBOL,
            "side": self.current_pos['side'],
            "entry_price": self.current_pos['entry_price'],
            "exit_price": price,
            "exit_time": datetime.now().isoformat(),
            "quantity": self.current_pos['size'],
            "gross_pnl": pnl,
            "net_pnl": pnl,
            "exit_reason": reason,
            "mode": settings.RUN_MODE
        })
        
        self.current_pos = None
