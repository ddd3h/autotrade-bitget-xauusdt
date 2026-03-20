import asyncio
import ccxt.async_support as ccxt
from app.config import settings
from app.logger import export_logger as logger
from typing import Dict, List, Optional
import pandas as pd

class BitgetService:
    def __init__(self, use_demo: bool = False):
        self.use_demo = use_demo
        configs = {
            'apiKey': settings.BITGET_DEMO_API_KEY if use_demo else settings.BITGET_API_KEY,
            'secret': settings.BITGET_DEMO_API_SECRET if use_demo else settings.BITGET_API_SECRET,
            'password': settings.BITGET_DEMO_API_PASSPHRASE if use_demo else settings.BITGET_API_PASSPHRASE,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
            }
        }
        self.client = ccxt.bitget(configs)
        if use_demo:
            self.client.set_sandbox_mode(True)
            
        self.symbol = settings.SYMBOL
        self.pos_mode = settings.POSITION_MODE

    async def _resolve_ccxt_symbol(self, symbol: str) -> str:
        """Resolve a user symbol (e.g. XAUUSDT) to a CCXT symbol (e.g. XAU/USDT:USDT)."""
        if not self.client.markets:
            await self.client.load_markets()
            
        if symbol in self.client.markets:
            return symbol
            
        for s, market in self.client.markets.items():
            if market.get('id') == symbol:
                return s
        
        return symbol

    async def _ensure_pos_mode(self):
        """Ensure position mode is correctly set. 
        Note: We trust settings.POSITION_MODE as per user instructions.
        """
        logger.info(f"Using position mode: {self.pos_mode} (from config)")

    async def get_balance(self, coin: str = 'USDT') -> float:
        """Fetch total account equity for a specific coin in the swap account."""
        try:
            # Bitget V2 Mix specific call to get account equity
            # This is more reliable for 40% margin calculation
            pt_map = {
                "USDT-M": "USDT-FUTURES",
                "USDC-M": "USDC-FUTURES",
                "Coin-M": "COIN-FUTURES",
                "USDT-FUTURES": "USDT-FUTURES"
            }
            product_type = pt_map.get(settings.PRODUCT_TYPE, "USDT-FUTURES")
            
            response = await self.client.privateMixGetV2MixAccountAccounts({
                'productType': product_type
            })
            
            if response.get('code') == '00000' and response.get('data'):
                for account in response['data']:
                    if account.get('marginCoin') == coin:
                        # Use accountEquity for position sizing
                        return float(account.get('accountEquity', 0.0))
            
            # Fallback to standard CCXT fetch_balance
            balance = await self.client.fetch_balance({'type': 'swap'})
            return float(balance.get('total', {}).get(coin, 0.0))
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return 0.0

    async def set_leverage(self, symbol: str, leverage: int):
        """Set leverage for a symbol using Bitget V2 Mix API."""
        try:
            ccxt_symbol = await self._resolve_ccxt_symbol(symbol)
            market = self.client.market(ccxt_symbol)
            symbol_id = market['id']
            
            pt_map = {
                "USDT-M": "USDT-FUTURES",
                "USDC-M": "USDC-FUTURES",
                "Coin-M": "COIN-FUTURES",
                "USDT-FUTURES": "USDT-FUTURES"
            }
            product_type = pt_map.get(settings.PRODUCT_TYPE, "USDT-FUTURES")
            
            logger.info(f"Setting leverage to {leverage} mapping for {ccxt_symbol}")
            
            # Bitget V2 Mix: POST /api/v2/mix/account/set-leverage
            # For Hedge mode, we set it once for the symbol/productType
            params = {
                'symbol': symbol_id,
                'productType': product_type,
                'marginCoin': settings.MARGIN_COIN,
                'leverage': str(leverage)
            }
            
            # Note: In hedge mode, Bitget takes 'holdSide' as optional to set separately 
            # for long/short, but 'set-leverage' usually applies to both if not specified.
            response = await self.client.privateMixPostV2MixAccountSetLeverage(params)
            logger.info(f"Leverage set response: {response}")
            return response
        except Exception as e:
            logger.error(f"Error setting leverage: {e}")
            return None

    async def fetch_ohlcv(self, symbol: str, timeframe: str = '1m', limit: int = 1000, since: Optional[int] = None) -> pd.DataFrame:
        """Fetch historical candles and return as DataFrame."""
        try:
            ohlcv = await self.client.fetch_ohlcv(symbol, timeframe, since, limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            return df
        except Exception as e:
            logger.error(f"Error fetching OHLCV: {e}")
            raise

    async def close(self):
        await self.client.close()

    async def get_position(self, symbol: str) -> Optional[Dict]:
        """Get current position for a symbol."""
        try:
            ccxt_symbol = await self._resolve_ccxt_symbol(symbol)
            positions = await self.client.fetch_positions([ccxt_symbol])
            if positions:
                for pos in positions:
                    # Filter by the resolved CCXT symbol
                    if pos['symbol'] == ccxt_symbol:
                        contracts = float(pos.get('contracts', 0) or 0)
                        if contracts > 0:
                            # Found an active position
                            return pos
            return None
        except Exception as e:
            logger.error(f"Error fetching position for {symbol}: {e}")
            return None

    async def create_market_order(self, symbol: str, side: str, amount: float, params: Dict = {}):
        """Create a market order."""
        try:
            await self._ensure_pos_mode()
            ccxt_symbol = await self._resolve_ccxt_symbol(symbol)
            
            # Map product type for Bitget V2
            # USDT-M -> USDT-FUTURES, Coin-M -> COIN-FUTURES
            pt_map = {
                "USDT-M": "USDT-FUTURES",
                "USDC-M": "USDC-FUTURES",
                "Coin-M": "COIN-FUTURES",
                "USDT-FUTURES": "USDT-FUTURES"
            }
            product_type = pt_map.get(settings.PRODUCT_TYPE, "USDT-FUTURES")

            market = self.client.market(ccxt_symbol)
            clean_amount = float(amount)
            precise_amount_str = self.client.amount_to_precision(ccxt_symbol, clean_amount)
            final_amount = float(precise_amount_str)
            
            # Prepare V2 Mix params
            order_params = params.copy()
            
            if self.pos_mode == 'one-way':
                # Minimal params strictly as per user instruction
                v2_params = {
                    'productType': product_type,
                    'marginMode': settings.MARGIN_MODE,
                    'marginCoin': settings.MARGIN_COIN,
                }
                
                # Add reduceOnly ONLY if closing
                is_reduce = order_params.get('reduceOnly', False) in [True, 'YES']
                if is_reduce:
                    v2_params['reduceOnly'] = 'YES'
                
                # Remove all prohibited parameters
                for key in ['oneWayMode', 'posSide', 'tradeSide', 'reduceOnly']:
                    if key in order_params:
                        del order_params[key]
                
                # Merge with mandatory v2 params
                order_params.update(v2_params)
            else:
                # Hedge mode
                order_params.update({
                    'productType': product_type,
                    'marginMode': settings.MARGIN_MODE,
                    'marginCoin': settings.MARGIN_COIN,
                })
                
                is_reduce = order_params.get('reduceOnly', False) in [True, 'YES']
                
                if is_reduce:
                    # In Bitget V2 Hedge Mode, 'side' must match the position direction, NOT the trade action.
                    # CCXT passes 'buy' to close a 'short' position. We must flip it to 'sell' (the short position direction).
                    # Similarly, CCXT passes 'sell' to close a 'long' position. We must flip it to 'buy'.
                    side = 'sell' if side == 'buy' else 'buy'
                    order_params['tradeSide'] = 'close'
                else:
                    # For opening, CCXT 'buy' is 'buy' (Long) and 'sell' is 'sell' (Short).
                    order_params['tradeSide'] = 'open'
                
                # In Hedge Mode, posSide always matches the position direction (buy=long, sell=short)
                order_params['posSide'] = 'long' if side == 'buy' else 'short'
                
                # remove reduceOnly as it's for one-way only
                if 'reduceOnly' in order_params:
                    del order_params['reduceOnly']
                # remove CCXT-specific flags
                if 'oneWayMode' in order_params:
                    del order_params['oneWayMode']

            logger.info(f"Placing market order: {side} {final_amount} for {ccxt_symbol} (Mode: {self.pos_mode}, Params: {order_params})")
            
            order = await self.client.create_order(
                symbol=ccxt_symbol,
                type='market',
                side=side,
                amount=final_amount,
                params=order_params
            )
            
            logger.info(f"Order created: {order.get('id')}")
            
            # Verification: Fetch position immediately
            await asyncio.sleep(1) 
            pos = await self.get_position(ccxt_symbol)
            if pos:
                logger.info(f"Current Position after order: {pos.get('side')} {pos.get('contracts')}")
            else:
                logger.info("No open position detected after order.")

            return order
        except Exception as e:
            logger.error(f"Error creating market order: {e}")
            raise

    async def set_leverage(self, symbol: str, leverage: int):
        """Set leverage for a symbol."""
        try:
            await self.client.set_leverage(leverage, symbol)
            logger.info(f"Leverage set to {leverage} for {symbol}")
        except Exception as e:
            logger.warning(f"Error setting leverage: {e} (It might already be set)")

    async def fetch_funding_rate(self, symbol: str) -> float:
        """Fetch current funding rate."""
        try:
            funding = await self.client.fetch_funding_rate(symbol)
            return funding.get('fundingRate', 0.0)
        except Exception as e:
            logger.error(f"Error fetching funding rate: {e}")
            return 0.0
