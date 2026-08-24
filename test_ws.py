import asyncio
import websockets
import json

async def test():
    uri = 'wss://fstream.binance.com/stream?streams=btcusdt@aggTrade/btcusdt@trade/btcusdt@depth5@100ms'
    try:
        async with websockets.connect(uri) as ws:
            print('Connected to Binance Combined Stream!')
            trades = 0
            while trades < 2:
                msg = await ws.recv()
                d = json.loads(msg)
                stream = d.get('stream', '')
                if 'trade' in stream.lower() or 'aggtrade' in stream.lower():
                    print('Recibido:', stream)
                    trades += 1
    except Exception as e:
        print("Error:", e)

asyncio.run(test())
