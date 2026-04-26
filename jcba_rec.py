"""
JCBA Internet Simul Radio - Recorder
Usage: python jcba_rec.py <station_id> <duration_sec> <output_file>
Example: python jcba_rec.py fmtonami 1800 C:/RadioRec/fmtonami_20260502_1200.ogg
"""

import sys
import time
import json
import threading
import requests
import websocket

# ----------------------------------------------------------------
# Settings
# ----------------------------------------------------------------
API_BASE      = "https://www.jcbasimul.com/api"
# burst=5 for first connection (buffer), burst=0 for reconnections (no duplicate audio)
SELECT_STREAM = API_BASE + "/select_stream?station={station_id}&channel=0&quality=high&burst={burst}"
TOKEN_MARGIN  = 5      # refresh token N seconds before expiry
CONNECT_TIMEOUT = 10   # WebSocket connect timeout (sec)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/147.0.0.0 Safari/537.36",
    "Referer": "https://www.jcbasimul.com/",
    "Origin":  "https://www.jcbasimul.com",
}

# ----------------------------------------------------------------
# Token fetcher
# ----------------------------------------------------------------
def fetch_token(station_id, burst=0):
    url = SELECT_STREAM.format(station_id=station_id, burst=burst)
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 200:
        raise RuntimeError(f"API error: {data}")
    return data["location"], data["token"]


def decode_exp(token):
    """JWT exp field (no signature verification needed)."""
    import base64
    payload_b64 = token.split(".")[1]
    payload_b64 += "=" * (4 - len(payload_b64) % 4)
    payload = json.loads(base64.b64decode(payload_b64))
    return payload["exp"]


# ----------------------------------------------------------------
# Recorder
# ----------------------------------------------------------------
class JCBARecorder:
    def __init__(self, station_id, duration_sec, output_path):
        self.station_id   = station_id
        self.duration_sec = duration_sec
        self.output_path  = output_path
        self._stop        = False
        self._ws          = None
        self._outfile     = None
        self._bytes_recv  = 0
        self._lock        = threading.Lock()

    # ------ public ------
    def record(self):
        self._outfile = open(self.output_path, "wb")
        start = time.time()
        first_connection = True
        try:
            while not self._stop:
                elapsed = time.time() - start
                if elapsed >= self.duration_sec:
                    break

                # burst=5 on first connection only; 0 on reconnects to avoid duplicate audio
                burst = 5 if first_connection else 0
                location, token = fetch_token(self.station_id, burst=burst)
                first_connection = False

                exp = decode_exp(token)
                # how long this token is valid
                valid_for = exp - time.time() - TOKEN_MARGIN
                if valid_for < 1:
                    valid_for = 1

                # remaining recording time
                remaining = self.duration_sec - elapsed
                ws_duration = min(valid_for, remaining)

                print(f"[{self.station_id}] "
                      f"elapsed={elapsed:.0f}s  ws_window={ws_duration:.0f}s  "
                      f"recv={self._bytes_recv//1024}KB  burst={burst}",
                      flush=True)

                self._run_ws(location, token, ws_duration)

        finally:
            self._outfile.close()
            print(f"[{self.station_id}] Done. "
                  f"Total={self._bytes_recv//1024}KB  "
                  f"File={self.output_path}", flush=True)

    def stop(self):
        self._stop = True
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

    # ------ internal ------
    def _run_ws(self, location, token, duration_sec):
        deadline = time.time() + duration_sec
        done_event = threading.Event()

        def on_open(ws):
            # Send token as first text message (Radimo protocol)
            ws.send(token)

        def on_message(ws, message):
            if isinstance(message, bytes):
                with self._lock:
                    self._outfile.write(message)
                    self._bytes_recv += len(message)
            if time.time() >= deadline or self._stop:
                ws.close()

        def on_error(ws, error):
            print(f"[{self.station_id}] WS error: {error}", flush=True)

        def on_close(ws, code, msg):
            done_event.set()

        ws = websocket.WebSocketApp(
            location,
            header={k: v for k, v in HEADERS.items()
                    if k not in ("Origin",)},
            subprotocols=["listener.fmplapla.com"],
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        self._ws = ws

        t = threading.Thread(
            target=ws.run_forever,
            kwargs={
                "ping_interval": 0,
                "sslopt": {"check_hostname": False},
            },
            daemon=True,
        )
        t.start()
        done_event.wait(timeout=duration_sec + CONNECT_TIMEOUT)
        self._ws = None


# ----------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------
def main():
    if len(sys.argv) != 4:
        print("Usage: python jcba_rec.py <station_id> <duration_sec> <output_file>")
        sys.exit(1)

    station_id   = sys.argv[1]
    duration_sec = int(sys.argv[2])
    output_path  = sys.argv[3]

    print(f"[{station_id}] Start recording {duration_sec}s -> {output_path}", flush=True)
    rec = JCBARecorder(station_id, duration_sec, output_path)
    rec.record()


if __name__ == "__main__":
    main()
