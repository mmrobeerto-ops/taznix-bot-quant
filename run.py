import socket

# Force Python socket to resolve IPv4 addresses only (bypasses dynamic IPv6 connection routes)
orig_getaddrinfo = socket.getaddrinfo
def getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    if family == 0 or family == socket.AF_UNSPEC:
        family = socket.AF_INET
    return orig_getaddrinfo(host, port, family, type, proto, flags)
socket.getaddrinfo = getaddrinfo_ipv4

import uvicorn
import os
import sys
from dotenv import load_dotenv

if __name__ == "__main__":
    load_dotenv()
    # Add the current directory to sys.path to ensure 'app' can be imported
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    print("Starting SFA-IFA Pro Quantitative Platform...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=False)
