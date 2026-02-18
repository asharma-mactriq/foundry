import time
from datetime import datetime

def mono():
    return time.monotonic()

def wall_ts():
    return datetime.now()

def wall_str():
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S:%f")[:-3]
