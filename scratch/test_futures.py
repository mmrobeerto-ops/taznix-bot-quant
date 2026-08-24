import os
import requests
import time
import hmac
import hashlib
import urllib.parse

os.environ["TESTING"] = "False"

import urllib3.util.connection
urllib3.util.connection.HAS_IPV6 = False

api_key = "SRODnwNyEMzYil8sLv3X7GoyLreLVK0ppiQq7q0R76a5j51xtxvmqYD1QZ3dgu3T"
secret = "IufA4yDKFFPEBzMUDN5Xj7nOoiuuMLE3kSfSz2R34O78F2vQHcOb8PTCDMu534Tc"

def send_signed_request(endpoint, params):
    params["timestamp"] = int(time.time() * 1000)
    query_string = urllib.parse.urlencode(params)
    signature = hmac.new(
        secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    full_query = f"{query_string}&signature={signature}"
    url = f"https://fapi.binance.com{endpoint}?{full_query}"
    
    headers = {
        "X-MBX-APIKEY": api_key,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    response = requests.get(url, headers=headers)
    return response

try:
    res = send_signed_request("/fapi/v2/account", {})
    print("Status:", res.status_code)
    if res.status_code == 200:
        data = res.json()
        print("USDT balance:", [a for a in data.get("assets", []) if a["asset"] == "USDT"])
    else:
        print("Response text:", res.text)
except Exception as e:
    print("Error:", e)
