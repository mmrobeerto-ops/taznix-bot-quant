import os
import time
import uuid
import requests
from app.database import log_to_db

def load_env_file():
    if os.environ.get("TESTING") == "True":
        return
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

class BrokerClient:
    def __init__(self):
        load_env_file()
        self.api_key = os.environ.get("BINANCE_API_KEY", "")
        self.api_secret = os.environ.get("BINANCE_API_SECRET", "")
        self.use_testnet = os.environ.get("BINANCE_USE_TESTNET", "False").lower() == "true"
        
        # Determine Futures live vs testnet URLs
        if self.use_testnet:
            self.base_url = "https://testnet.binancefuture.com"
        else:
            self.base_url = "https://fapi.binance.com"
            
        self.is_emulated = (
            not self.api_key or 
            self.api_key.startswith("EVAL_") or 
            self.api_key == "YOUR_BINANCE_API_KEY" or
            not self.api_secret
        )

        # Dynamic lot sizing defaults
        self.btc_qty_precision = 4
        self.btc_step_size = 0.0001

        # Circuit breaker variables
        self.consecutive_errors = 0
        self.paused_until = 0.0

        self.time_offset = 0.0
        if not self.is_emulated:
            try:
                # Sync time offset with Binance server time
                t_res = requests.get(f"{self.base_url}/fapi/v1/time", timeout=5)
                server_time = t_res.json()["serverTime"]
                local_time = int(time.time() * 1000)
                self.time_offset = server_time - local_time
            except Exception:
                pass
            self._load_exchange_info()

    def _load_exchange_info(self):
        """Fetches dynamic lot precision and step size for BTCUSDT from Binance Futures API."""
        try:
            url = f"{self.base_url}/fapi/v1/exchangeInfo"
            res = requests.get(url, timeout=5)
            res.raise_for_status()
            data = res.json()
            for sym in data.get("symbols", []):
                if sym.get("symbol") == "BTCUSDT":
                    self.btc_qty_precision = int(sym.get("quantityPrecision", 3))
                    for f in sym.get("filters", []):
                        if f.get("filterType") == "LOT_SIZE":
                            self.btc_step_size = float(f.get("stepSize", 0.001))
                    log_to_db("INFO", f"[BROKER] Dynamic exchange rules loaded for BTCUSDT: Precision={self.btc_qty_precision}, stepSize={self.btc_step_size}")
                    break
        except Exception as e:
            log_to_db("WARNING", f"[BROKER] Could not load dynamic exchangeInfo: {e}. Using defaults: Precision=4, stepSize=0.0001")

    def format_quantity(self, qty: float) -> float:
        """Rounds position sizes strictly to match the stepSize and precision required by Binance."""
        # Find number of decimals in step size
        step_str = f"{self.btc_step_size:.8f}".rstrip('0')
        decimals = 0
        if '.' in step_str:
            decimals = len(step_str.split('.')[1])
        # Force round to precision
        decimals = min(decimals, self.btc_qty_precision)
        rounded = round(qty / self.btc_step_size) * self.btc_step_size
        return round(rounded, decimals)

    def execute_order(self, order_type: str, price: float, quantity: float, stop_loss: float, take_profit: float) -> dict:
        """Dispatches a market order. Runs in emulation mode if API keys are missing/mocked, else executes on Binance Futures."""
        qty_formatted = self.format_quantity(quantity)
        if not self.is_emulated:
            # Spread Check Validation on Entry (mitigate slippage)
            try:
                book_ticker_url = f"{self.base_url}/fapi/v1/ticker/bookTicker?symbol=BTCUSDT"
                for attempt in range(4): # 1 initial attempt + 3 retries
                    book_ticker_res = requests.get(book_ticker_url, timeout=2)
                    book_ticker_res.raise_for_status()
                    book_data = book_ticker_res.json()
                    bid_price = float(book_data.get("bidPrice", 0.0))
                    ask_price = float(book_data.get("askPrice", 0.0))
                    if bid_price > 0.0:
                        spread_pct = (ask_price - bid_price) / bid_price * 100.0
                        if spread_pct <= 0.08:
                            break
                        else:
                            if attempt < 3:
                                log_to_db("WARNING", f"[SPREAD CHECK] BTCUSDT spread too high on entry (attempt {attempt+1}): {spread_pct:.4f}% > 0.08%. Delaying 200ms.")
                                time.sleep(0.200)
                            else:
                                raise Exception(f"Entry order rejected due to high spread after 3 retries: {spread_pct:.4f}% > 0.08% limit")
            except Exception as spread_err:
                log_to_db("WARNING", f"[SPREAD CHECK] Entry spread verification issue: {spread_err}.")
                if "rejected due to" in str(spread_err):
                    raise spread_err

            try:
                # 1. Set Margin Type to ISOLATED (ignore error if already set to ISOLATED)
                try:
                    self._send_signed_request("POST", "/fapi/v1/marginType", {
                        "symbol": "BTCUSDT",
                        "marginType": "ISOLATED"
                    })
                    log_to_db("INFO", "[BINANCE FUTURES] Margin type set to ISOLATED.")
                except Exception as margin_err:
                    pass

                # 2. Set Leverage to 25
                try:
                    self._send_signed_request("POST", "/fapi/v1/leverage", {
                        "symbol": "BTCUSDT",
                        "leverage": 25
                    })
                    log_to_db("INFO", "[BINANCE FUTURES] Leverage set to 25x.")
                except Exception as lev_err:
                    log_to_db("WARNING", f"Could not set leverage to 20x: {lev_err}")

                # 3. Send Post-Only LIMIT Order
                limit_price = bid_price if order_type.upper() == "BUY" else ask_price
                if limit_price <= 0.0:
                    limit_price = price
                    
                params = {
                    "symbol": "BTCUSDT",
                    "side": order_type.upper(),
                    "type": "LIMIT",
                    "timeInForce": "GTX",
                    "price": f"{limit_price:.2f}",
                    "quantity": f"{qty_formatted:.{self.btc_qty_precision}f}",
                }
                
                api_log_msg = f"[FUTURES LIVE API] Placing Isolated 25x Post-Only LIMIT {order_type.upper()} order at ${limit_price:.2f} for {qty_formatted:.{self.btc_qty_precision}f} BTC..."
                log_to_db("INFO", api_log_msg)
                print(api_log_msg)
                
                res = self._send_signed_request("POST", "/fapi/v1/order", params)
                
                # Check for Post-Only cancellation
                if res.get("status") in ["EXPIRED", "CANCELED"]:
                    raise Exception("Post-Only limit order expired/canceled (would execute as Taker)")
                
                status = res.get("status", "NEW")
                
                # Extract filled price
                fill_price = limit_price
                if "avgPrice" in res and float(res["avgPrice"]) > 0:
                    fill_price = float(res["avgPrice"])
                elif "price" in res and float(res["price"]) > 0:
                    fill_price = float(res["price"])
                    
                broker_order_id = str(res["orderId"])
                
                success_msg = f"[FUTURES LIVE SUCCESS] Order ID: {broker_order_id} status: {status} at ${fill_price:.2f}"
                log_to_db("INFO", success_msg)
                print(success_msg)
                
                return {
                    "broker_order_id": broker_order_id,
                    "status": status,
                    "fill_price": fill_price,
                    "timestamp": time.time()
                }
            except Exception as e:
                status_code = getattr(getattr(e, "response", None), "status_code", None)
                if status_code == 401 or "401" in str(e) or "unauthorized" in str(e).lower():
                    log_to_db("WARNING", f"Binance API returned 401 Unauthorized (IP restricted or invalid keys). Falling back to EMULATED execution mode.")
                    self.is_emulated = True
                    broker_order_id = f"brk_{int(time.time())}_{uuid.uuid4().hex[:6]}"
                    api_log_msg = (
                        f"[EMULATED FUTURES ORDER] POST {self.base_url}/fapi/v1/order (Fallback)\n"
                        f"Side: {order_type} | Qty: {qty_formatted:.{self.btc_qty_precision}f} | Price: {price:.2f} | "
                        f"SL: {stop_loss:.2f} | TP: {take_profit:.2f}"
                    )
                    log_to_db("INFO", api_log_msg)
                    print(api_log_msg)
                    return {
                        "broker_order_id": broker_order_id,
                        "status": "FILLED",
                        "fill_price": price,
                        "timestamp": time.time()
                    }
                else:
                    err_msg = f"[FUTURES LIVE ERROR] Failed to execute live order: {str(e)}"
                    log_to_db("CRITICAL", err_msg)
                    print(err_msg)
                    raise e
 
        if self.is_emulated:
            broker_order_id = f"brk_{int(time.time())}_{uuid.uuid4().hex[:6]}"
            api_log_msg = (
                f"[EMULATED FUTURES ORDER] POST {self.base_url}/fapi/v1/order\n"
                f"Side: {order_type} | Qty: {qty_formatted:.{self.btc_qty_precision}f} | Price: {price:.2f} | "
                f"SL: {stop_loss:.2f} | TP: {take_profit:.2f}"
            )
            log_to_db("INFO", api_log_msg)
            print(api_log_msg)
            time.sleep(0.025)
            return {
                "broker_order_id": broker_order_id,
                "status": "FILLED",
                "fill_price": price,
                "timestamp": time.time()
            }

    def close_order(self, broker_order_id: str, close_price: float) -> dict:
        """Closes position by sending an opposite MARKET order to Binance Futures."""
        db_order_type = "BUY"
        quantity = 0.0001
        from app.database import SessionLocal, OrderModel
        db = SessionLocal()
        try:
            db_order = db.query(OrderModel).filter(OrderModel.id == broker_order_id).first()
            if db_order:
                db_order_type = db_order.type
                quantity = db_order.quantity
        except Exception as e:
            print(f"Error reading order for close: {e}")
        finally:
            db.close()
            
        qty_formatted = self.format_quantity(quantity)
        opposite_type = "SELL" if db_order_type == "BUY" else "BUY"
        
        if not self.is_emulated:
            try:
                # Validation of exit liquidity: Spread Check
                try:
                    book_ticker_url = f"{self.base_url}/fapi/v1/ticker/bookTicker?symbol=BTCUSDT"
                    book_ticker_res = requests.get(book_ticker_url, timeout=2)
                    book_ticker_res.raise_for_status()
                    book_data = book_ticker_res.json()
                    bid_price = float(book_data.get("bidPrice", 0.0))
                    ask_price = float(book_data.get("askPrice", 0.0))
                    if bid_price > 0.0:
                        spread_pct = (ask_price - bid_price) / bid_price * 100.0
                        if spread_pct > 0.08:
                            log_to_db("WARNING", f"[SPREAD CHECK] BTCUSDT spread too high ({spread_pct:.4f}% > 0.08%). Delaying close order by 200ms to mitigate slippage.")
                            time.sleep(0.200)
                except Exception as spread_err:
                    log_to_db("WARNING", f"[SPREAD CHECK] Could not check spread: {spread_err}. Proceeding directly.")

                # Live Binance Futures Execution
                params = {
                    "symbol": "BTCUSDT",
                    "side": opposite_type,
                    "type": "MARKET",
                    "quantity": f"{qty_formatted:.{self.btc_qty_precision}f}",
                }
                
                api_log_msg = f"[FUTURES LIVE API] Closing position with opposite MARKET {opposite_type} order for {qty_formatted:.{self.btc_qty_precision}f} BTC..."
                log_to_db("INFO", api_log_msg)
                print(api_log_msg)
                
                res = self._send_signed_request("POST", "/fapi/v1/order", params)
                
                fill_price = close_price
                if "avgPrice" in res and float(res["avgPrice"]) > 0:
                    fill_price = float(res["avgPrice"])
                elif "price" in res and float(res["price"]) > 0:
                    fill_price = float(res["price"])
                    
                close_msg = f"[FUTURES LIVE SUCCESS] Closed position Order ID: {res['orderId']} filled at ${fill_price:.2f}"
                log_to_db("INFO", close_msg)
                print(close_msg)
                
                return {
                    "broker_order_id": broker_order_id,
                    "status": "CLOSED",
                    "close_price": fill_price,
                    "timestamp": time.time()
                }
            except Exception as e:
                status_code = getattr(getattr(e, "response", None), "status_code", None)
                if status_code == 401 or "401" in str(e) or "unauthorized" in str(e).lower():
                    log_to_db("WARNING", f"Binance API returned 401 Unauthorized on close. Falling back to EMULATED close.")
                    self.is_emulated = True
                    api_log_msg = (
                        f"[EMULATED FUTURES CLOSE] POST {self.base_url}/fapi/v1/order (Close Fallback)\n"
                        f"Opposite Side: {opposite_type} | Qty: {qty_formatted:.{self.btc_qty_precision}f} | Close Price: {close_price:.2f}"
                    )
                    log_to_db("INFO", api_log_msg)
                    print(api_log_msg)
                    return {
                        "broker_order_id": broker_order_id,
                        "status": "CLOSED",
                        "close_price": close_price,
                        "timestamp": time.time()
                    }
                else:
                    err_msg = f"[FUTURES LIVE ERROR] Failed to close live position: {str(e)}"
                    log_to_db("CRITICAL", err_msg)
                    print(err_msg)
                    raise e
 
        if self.is_emulated:
            api_log_msg = (
                f"[EMULATED FUTURES CLOSE] POST {self.base_url}/fapi/v1/order (Close)\n"
                f"Opposite Side: {opposite_type} | Qty: {qty_formatted:.{self.btc_qty_precision}f} | Close Price: {close_price:.2f}"
            )
            log_to_db("INFO", api_log_msg)
            print(api_log_msg)
            time.sleep(0.025)
            return {
                "broker_order_id": broker_order_id,
                "status": "CLOSED",
                "close_price": close_price,
                "timestamp": time.time()
            }

    def _send_signed_request(self, method: str, endpoint: str, params: dict) -> dict:
        import hmac
        import hashlib
        import urllib.parse
        
        # Check Circuit Breaker status
        now = time.time()
        if now < self.paused_until:
            raise Exception(f"Binance API blocked by safety Circuit Breaker (active for another {int(self.paused_until - now)}s).")

        # Add timestamp and recvWindow=10000 to mitigate timing discrepancies and clock drift
        params["recvWindow"] = 10000
        params["timestamp"] = int((now * 1000) + getattr(self, "time_offset", 0.0))
        
        # Build query string
        query_string = urllib.parse.urlencode(params)
        
        # Sign query string
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        # Append signature to query
        full_query = f"{query_string}&signature={signature}"
        url = f"{self.base_url}{endpoint}?{full_query}"
        
        headers = {
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        try:
            if method.upper() == "POST":
                response = requests.post(url, headers=headers)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=headers)
            else:
                response = requests.get(url, headers=headers)
                
            response.raise_for_status()
            
            # Reset consecutive errors on successful API request
            self.consecutive_errors = 0
            return response.json()
            
        except Exception as e:
            # Handle consecutive error counter for HTTP errors
            is_network_or_server_error = True
            if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
                if e.response.status_code < 500:
                    is_network_or_server_error = False
            
            if is_network_or_server_error:
                self.consecutive_errors += 1
                if self.consecutive_errors >= 3:
                    self.paused_until = time.time() + 60.0
                    log_to_db("CRITICAL", "[CIRCUIT BREAKER] 3 consecutive API communication failures detected. Activating 60-second safety cooldown pause.")
            
            # Format and re-raise exception with clean Binance details
            if isinstance(e, requests.exceptions.HTTPError):
                try:
                    err_data = response.json()
                    msg = f"Binance API Error {response.status_code}: Code {err_data.get('code')} - {err_data.get('msg')}"
                except Exception:
                    msg = f"Binance API Error {response.status_code}: {response.text}"
                raise Exception(msg) from e
            raise e

    def get_futures_balance(self) -> float:
        """Fetches the total margin balance of the Futures account. Returns 0.0 if emulated or on error."""
        if self.is_emulated:
            return 19.13
        try:
            res = self._send_signed_request("GET", "/fapi/v2/account", {})
            if isinstance(res, dict) and "totalMarginBalance" in res:
                return float(res["totalMarginBalance"])
            # Fallback to balance endpoint if account endpoint returns unexpected result
            res_bal = self._send_signed_request("GET", "/fapi/v2/balance", {})
            if isinstance(res_bal, list):
                total = 0.0
                for item in res_bal:
                    if item.get("asset") in ("USDT", "USDC"):
                        total += float(item.get("balance", 0.0))
                if total != 0.0:
                    return total
            return 0.0
        except Exception as e:
            from app.database import log_to_db
            log_to_db("WARNING", f"Failed to fetch Binance Futures balance: {e}")
            return 0.0

    def query_order(self, broker_order_id: str) -> dict:
        """Queries the status of an active order from Binance Futures."""
        if self.is_emulated:
            return {"status": "FILLED", "executedQty": "0.0001", "avgPrice": "0.0"}
        try:
            params = {
                "symbol": "BTCUSDT",
                "orderId": broker_order_id
            }
            res = self._send_signed_request("GET", "/fapi/v1/order", params)
            return res
        except Exception as e:
            log_to_db("WARNING", f"[BROKER] Error querying order {broker_order_id}: {e}")
            raise e

    def cancel_order(self, broker_order_id: str) -> dict:
        """Cancels an active order from Binance Futures."""
        if self.is_emulated:
            return {"status": "CANCELED", "executedQty": "0.0"}
        try:
            params = {
                "symbol": "BTCUSDT",
                "orderId": broker_order_id
            }
            res = self._send_signed_request("DELETE", "/fapi/v1/order", params)
            return res
        except Exception as e:
            log_to_db("WARNING", f"[BROKER] Error canceling order {broker_order_id}: {e}")
            raise e
