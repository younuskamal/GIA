
import sys
import os
import time
import threading
from twisted.internet import reactor
from ctrader_open_api import Client, Protobuf, TcpProtocol, EndPoints

# Add paths
sys.path.append(os.getcwd())
try:
    from backend.config.secrets import CTRADER_CLIENT_ID, CTRADER_SECRET, CTRADER_ACCESS_TOKEN, CTRADER_ACCOUNT_ID, CTRADER_ENV
except ImportError:
    print("Failed to import secrets")
    sys.exit(1)

def on_connected(client):
    print("Connected!")
    reactor.stop()

def on_disconnected(client, reason):
    print(f"Disconnected: {reason}")
    if reactor.running:
        reactor.stop()

def on_message(client, message):
    pass

def test_connect():
    host = EndPoints.PROTOBUF_LIVE_HOST if CTRADER_ENV == "LIVE" else EndPoints.PROTOBUF_DEMO_HOST
    port = 5035
    print(f"Connecting to {host}:{port}...")
    
    client = Client(host, port, TcpProtocol)
    client.setConnectedCallback(on_connected)
    client.setDisconnectedCallback(on_disconnected)
    client.setMessageReceivedCallback(on_message)
    
    client.startService()
    reactor.run()

if __name__ == "__main__":
    test_connect()
