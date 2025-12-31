"""
GIA Master Launcher - Start the whole system properly.
"""
import sys
import os
import subprocess
import threading
import time

def start_backend():
    print("🚀 Starting GIA Backend Server...")
    os.chdir("backend")
    # Set PYTHONPATH to include current dir so imports work
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    subprocess.run([sys.executable, "api/main.py"], env=env)

if __name__ == "__main__":
    start_backend()
