
import os
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.broker import BrokerClient

def clean_all():
    print('Starting Binance Cleanup...')
    try:
        broker = BrokerClient()
        if broker.is_emulated:
            print('Broker is in EMULATED mode, no live keys available.')
            return
            
        print('Canceling all open orders for BTCUSDT...')
        try:
            broker._send_signed_request('DELETE', '/fapi/v1/allOpenOrders', {'symbol': 'BTCUSDT'})
            print('Orders canceled.')
        except Exception as e:
            print('Error canceling orders:', e)
            
        print('Fetching position risk...')
        positions = broker._send_signed_request('GET', '/fapi/v2/positionRisk', {'symbol': 'BTCUSDT'})
        for p in positions:
            if p.get('symbol') == 'BTCUSDT':
                pos_amt = float(p.get('positionAmt', 0.0))
                if pos_amt != 0:
                    print(f'Found active position: {pos_amt} BTC. Closing...')
                    side = 'SELL' if pos_amt > 0 else 'BUY'
                    params = {
                        'symbol': 'BTCUSDT',
                        'side': side,
                        'type': 'MARKET',
                        'quantity': str(abs(pos_amt))
                    }
                    broker._send_signed_request('POST', '/fapi/v1/order', params)
                    print('Position closed successfully.')
                else:
                    print('No active position on BTCUSDT.')
    except Exception as e:
        print('Error during cleanup:', e)

if __name__ == '__main__':
    clean_all()
