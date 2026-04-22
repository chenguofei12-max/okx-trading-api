"""
OKX交易所实盘对接API - FastAPI后端
使用ccxt库调用OKX API，支持下单、查余额、查订单等核心功能
"""

import os
import json
from datetime import datetime
from typing import Optional, List
from functools import wraps

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import ccxt

# ==================== 配置 ====================
app = FastAPI(
    title="OKX Trading API",
    description="OKX交易所实盘交易接口",
    version="1.0.0"
)

# CORS配置 - 允许扣子平台访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 初始化OKX交易所 ====================
def get_okx_exchange():
    """创建OKX交易所实例"""
    api_key = os.getenv("OKX_API_KEY")
    secret = os.getenv("OKX_SECRET_KEY")
    passphrase = os.getenv("OKX_PASSPHRASE")
    
    if not all([api_key, secret, passphrase]):
        raise HTTPException(
            status_code=500,
            detail="OKX API密钥未配置，请检查环境变量 OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE"
        )
    
    exchange = ccxt.okx({
        'apiKey': api_key,
        'secret': secret,
        'password': passphrase,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'spot',
        },
    })
    
    exchange.set_sandbox_mode(os.getenv("OKX_SANDBOX", "false").lower() == "true")
    
    return exchange


# ==================== 请求/响应模型 ====================
class OrderRequest(BaseModel):
    """下单请求模型"""
    symbol: str
    side: str
    order_type: str
    amount: float
    price: Optional[float] = None


class OrderResponse(BaseModel):
    """订单响应模型"""
    success: bool
    order_id: Optional[str] = None
    message: str
    data: Optional[dict] = None


# ==================== 工具函数 ====================
def handle_ccxt_error(func):
    """ccxt错误处理装饰器"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ccxt.AuthenticationError:
            raise HTTPException(status_code=401, detail="API认证失败，请检查API密钥")
        except ccxt.InsufficientFunds:
            raise HTTPException(status_code=400, detail="余额不足")
        except ccxt.InvalidOrder:
            raise HTTPException(status_code=400, detail="无效的订单参数")
        except ccxt.ExchangeError as e:
            raise HTTPException(status_code=400, detail=f"交易所错误: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")
    return wrapper


# ==================== API路由 ====================

@app.get("/")
async def root():
    """健康检查"""
    return {
        "status": "ok",
        "service": "OKX Trading API",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/status")
async def get_status():
    """获取API状态和配置"""
    try:
        exchange = get_okx_exchange()
        return {
            "exchange": "OKX",
            "sandbox": exchange.sandbox_mode,
            "status": "connected"
        }
    except HTTPException:
        return {
            "exchange": "OKX",
            "status": "not_configured",
            "message": "请配置环境变量"
        }


# ---------- 账户相关 ----------

@app.get("/api/balance")
@handle_ccxt_error
async def get_balance():
    """查询账户余额"""
    exchange = get_okx_exchange()
    balance = exchange.fetch_balance({'type': 'spot'})
    
    available = {}
    if 'free' in balance:
        for currency, amount in balance['free'].items():
            if amount and amount > 0:
                available[currency] = {
                    'free': amount,
                    'used': balance.get('used', {}).get(currency, 0),
                    'total': balance.get('total', {}).get(currency, amount)
                }
    
    return {
        "success": True,
        "data": {
            "total_value_usd": balance.get('total', {}).get('USDT', 0),
            "assets": available
        }
    }


@app.get("/api/balance/{symbol}")
@handle_ccxt_error
async def get_symbol_balance(symbol: str):
    """查询指定币种的余额"""
    exchange = get_okx_exchange()
    balance = exchange.fetch_balance({'type': 'spot'})
    
    symbol = symbol.upper().replace('-', '/')
    currency = symbol.split('/')[0] if '/' in symbol else symbol
    
    free = balance.get('free', {}).get(currency, 0)
    used = balance.get('used', {}).get(currency, 0)
    
    return {
        "success": True,
        "data": {
            "currency": currency,
            "free": free,
            "used": used,
            "total": free + used
        }
    }


# ---------- 市场数据 ----------

@app.get("/api/ticker/{symbol}")
@handle_ccxt_error
async def get_ticker(symbol: str):
    """获取交易对行情"""
    exchange = get_okx_exchange()
    symbol = symbol.upper().replace('-', '/')
    ticker = exchange.fetch_ticker(symbol)
    
    return {
    "success": True,
    "data": {
        "symbol": ticker.get('symbol'),
        "last": ticker.get('last'),
        "high": ticker.get('high'),
        "low": ticker.get('low'),
        "volume": ticker.get('baseVolume') or ticker.get('volume', 0),
        "bid": ticker.get('bid'),
        "ask": ticker.get('ask'),
        "change": ticker.get('change'),
        "change_percent": ticker.get('percentage'),
        "timestamp": ticker.get('timestamp')
    }
}


@app.get("/api/orderbook/{symbol}")
@handle_ccxt_error
async def get_orderbook(symbol: str, limit: int = 20):
    """获取订单簿（盘口数据）"""
    exchange = get_okx_exchange()
    symbol = symbol.upper().replace('-', '/')
    orderbook = exchange.fetch_order_book(symbol, limit)
    
    return {
        "success": True,
        "data": {
            "symbol": symbol,
            "bids": orderbook['bids'][:limit],
            "asks": orderbook['asks'][:limit],
            "timestamp": orderbook['timestamp']
        }
    }


# ---------- 交易相关 ----------

@app.post("/api/order", response_model=OrderResponse)
@handle_ccxt_error
async def create_order(order: OrderRequest):
    """下单"""
    exchange = get_okx_exchange()
    
    symbol = order.symbol.upper().replace('-', '/')
    if '/' not in symbol:
        symbol = f"{symbol}/USDT"
    
    side = order.side.lower()
    if side not in ['buy', 'sell']:
        return OrderResponse(success=False, message="side参数错误，只支持 buy 或 sell")
    
    order_type = order.order_type.lower()
    if order_type not in ['market', 'limit']:
        return OrderResponse(success=False, message="order_type参数错误，只支持 market 或 limit")
    
    params = {
        'symbol': symbol,
        'side': side,
        'type': order_type,
        'amount': order.amount,
    }
    
    if order_type == 'limit':
        if not order.price:
            return OrderResponse(success=False, message="限价单必须提供 price 参数")
        params['price'] = order.price
    
    try:
        result = exchange.create_order(**params)
        return OrderResponse(
            success=True,
            order_id=result.get('id'),
            message="订单提交成功",
            data={
                "id": result.get('id'),
                "symbol": result.get('symbol'),
                "type": result.get('type'),
                "side": result.get('side'),
                "price": result.get('price'),
                "amount": result.get('amount'),
                "filled": result.get('filled'),
                "status": result.get('status'),
                "timestamp": result.get('timestamp')
            }
        )
    except Exception as e:
        return OrderResponse(success=False, message=f"下单失败: {str(e)}")


@app.post("/api/order/market")
@handle_ccxt_error
async def market_buy(order: OrderRequest):
    """市价买入"""
    order.order_type = "market"
    order.side = "buy"
    return await create_order(order)


@app.post("/api/order/limit")
@handle_ccxt_error
async def limit_sell(order: OrderRequest):
    """限价卖出"""
    if not order.price:
        raise HTTPException(status_code=400, detail="限价单必须提供 price 参数")
    order.order_type = "limit"
    order.side = "sell"
    return await create_order(order)


@app.delete("/api/order/{order_id}")
@handle_ccxt_error
async def cancel_order(order_id: str, symbol: str = None):
    """取消订单"""
    exchange = get_okx_exchange()
    
    if not symbol:
        raise HTTPException(status_code=400, detail="需要提供 symbol 参数")
    
    symbol = symbol.upper().replace('-', '/')
    
    try:
        result = exchange.cancel_order(order_id, symbol)
        return {"success": True, "message": "订单取消成功", "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"取消订单失败: {str(e)}")


@app.get("/api/order/{order_id}")
@handle_ccxt_error
async def get_order(order_id: str, symbol: str = None):
    """查询订单状态"""
    exchange = get_okx_exchange()
    
    if not symbol:
        raise HTTPException(status_code=400, detail="需要提供 symbol 参数")
    
    symbol = symbol.upper().replace('-', '/')
    order = exchange.fetch_order(order_id, symbol)
    
    return {
        "success": True,
        "data": {
            "id": order.get('id'),
            "symbol": order.get('symbol'),
            "type": order.get('type'),
            "side": order.get('side'),
            "price": order.get('price'),
            "amount": order.get('amount'),
            "filled": order.get('filled'),
            "remaining": order.get('remaining'),
            "status": order.get('status'),
            "fee": order.get('fee'),
            "timestamp": order.get('timestamp'),
            "lastTradeTimestamp": order.get('lastTradeTimestamp')
        }
    }


@app.get("/api/orders")
@handle_ccxt_error
async def get_open_orders(symbol: str = None, limit: int = 100):
    """查询当前挂单"""
    exchange = get_okx_exchange()
    
    if symbol:
        symbol = symbol.upper().replace('-', '/')
        orders = exchange.fetch_open_orders(symbol=symbol, limit=limit)
    else:
        orders = exchange.fetch_open_orders(limit=limit)
    
    result = []
    for order in orders:
        result.append({
            "id": order.get('id'),
            "symbol": order.get('symbol'),
            "type": order.get('type'),
            "side": order.get('side'),
            "price": order.get('price'),
            "amount": order.get('amount'),
            "filled": order.get('filled'),
            "status": order.get('status'),
            "timestamp": order.get('timestamp')
        })
    
    return {"success": True, "count": len(result), "data": result}


@app.get("/api/trades")
@handle_ccxt_error
async def get_trade_history(symbol: str = None, limit: int = 50):
    """查询成交历史"""
    exchange = get_okx_exchange()
    
    if not symbol:
        raise HTTPException(status_code=400, detail="需要提供 symbol 参数")
    
    symbol = symbol.upper().replace('-', '/')
    trades = exchange.fetch_my_trades(symbol, limit=limit)
    
    result = []
    for trade in trades:
        result.append({
            "id": trade.get('id'),
            "order": trade.get('order'),
            "symbol": trade.get('symbol'),
            "side": trade.get('side'),
            "price": trade.get('price'),
            "amount": trade.get('amount'),
            "cost": trade.get('cost'),
            "fee": trade.get('fee'),
            "timestamp": trade.get('timestamp')
        })
    
    return {"success": True, "count": len(result), "data": result}


# ---------- 便捷交易对接口 ----------

@app.get("/api/positions")
@handle_ccxt_error
async def get_positions():
    """查询持仓（杠杆/合约）"""
    exchange = get_okx_exchange()
    balance = exchange.fetch_balance({'type': 'spot'})
    
    positions = []
    for currency, data in balance['total'].items():
        if data and data > 0 and currency != 'USDT':
            positions.append({
                "currency": currency,
                "amount": data,
                "value_usd": data
            })
    
    return {"success": True, "data": positions}


# ==================== 启动配置 ====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
