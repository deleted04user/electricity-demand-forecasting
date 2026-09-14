"""Capture report-ready screenshots from the locally running React dashboard."""
import base64
import json
import time
import urllib.request
from pathlib import Path

import websocket

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "figures"
OUTPUT.mkdir(exist_ok=True)

pages = json.load(urllib.request.urlopen("http://127.0.0.1:9223/json"))
page = next(item for item in pages if item.get("url") == "http://127.0.0.1:5173/")
connection = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=20)
counter = 0


def command(method, params=None):
    global counter
    counter += 1
    connection.send(json.dumps({"id": counter, "method": method, "params": params or {}}))
    while True:
        response = json.loads(connection.recv())
        if response.get("id") == counter:
            return response


command("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 1000, "deviceScaleFactor": 1, "mobile": False})
for index, filename in ((2, "capture_performance_modele.png"), (3, "capture_prevision.png")):
    command("Runtime.evaluate", {"expression": f"document.querySelectorAll('button.tab')[{index}].click()"})
    time.sleep(5)
    shot = command("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    (OUTPUT / filename).write_bytes(base64.b64decode(shot["result"]["data"]))

connection.close()
