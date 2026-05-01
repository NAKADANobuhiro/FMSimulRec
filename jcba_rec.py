"""
JCBA Internet Simul Radio - Recorder
Usage: python jcba_rec.py <station_id> <duration_sec> <output_file>
Example: python jcba_rec.py fmtonami 1800 C:/RadioRec/fmtonami_20260502_1200.ogg
"""

import sys
import time
import json
import struct
import threading
import requests
import websocket

# ----------------------------------------------------------------
# Settings
# ----------------------------------------------------------------
API_BASE      = "https://www.jcbasimul.com/api"
SELECT_STREAM = API_BASE + "/select_stream?station={station_id}&channel=0&quality=high&burst={burst}"
TOKEN_MARGIN    = 5    # close WebSocket N seconds before token expiry
PREFETCH_BEFORE = 1    # start pre-fetching next token N seconds before window ends
RECONNECT_BURST = 2    # burst seconds on reconnection; OGGStitcher removes the overlap
CONNECT_TIMEOUT = 10   # WebSocket connect timeout (sec)
FETCH_RETRY_WAIT = 5   # seconds to wait before retrying after token fetch error

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/147.0.0.0 Safari/537.36",
    "Referer": "https://www.jcbasimul.com/",
    "Origin":  "https://www.jcbasimul.com",
}


# ----------------------------------------------------------------
# OGG Stitcher — eliminates reconnection gaps
# ----------------------------------------------------------------
class OGGStitcher:
    """
    Buffers raw WebSocket bytes and writes complete OGG pages to a file,
    skipping pages whose granule position is already covered by the previous
    stream.  This allows using burst>0 on reconnection so the new stream
    overlaps the old one; duplicate audio is dropped automatically.

    Same-CDN reconnection (same serial number):
      Granule comparison per serial filters the burst overlap correctly.

    Cross-CDN reconnection (new serial number, ~3.7h granule base difference):
      Granule comparison cannot be used across serials.  Instead, the wall-clock
      gap between the last written audio page and the first page of the new stream
      is measured, and a per-serial skip threshold is computed so only audio after
      the gap is kept.  This eliminates the ~1.1s repetition that occurred at each
      CDN node switch.
    """

    SAMPLE_RATE = 48_000   # Opus standard sample rate (Hz)

    def __init__(self, outfile, reconnect_burst=2):
        self._out                   = outfile
        self._buf                   = b''
        self._last_granule          = {}    # serial → highest granule written for that serial
        self._current_serial        = None
        self._audio_started         = set() # serials that have had ≥1 audio page written
        self._last_audio_write_time = None  # wall-clock time of last written audio page
        self._reconnect_burst       = reconnect_burst
        self.pages_written          = 0
        self.pages_skipped          = 0

    def feed(self, data: bytes):
        """Accept raw bytes from the WebSocket on_message callback."""
        self._buf += data
        self._drain()

    def _drain(self):
        buf = self._buf
        while True:
            if len(buf) < 27:
                break
            if buf[:4] != b'OggS':
                idx = buf.find(b'OggS')
                if idx == -1:
                    buf = b''
                    break
                buf = buf[idx:]
                continue
            num_segs   = buf[26]
            header_end = 27 + num_segs
            if len(buf) < header_end:
                break
            body_size = sum(buf[27:header_end])
            total     = header_end + body_size
            if len(buf) < total:
                break
            self._write_page(buf[:total])
            buf = buf[total:]
        self._buf = buf

    def _write_page(self, page: bytes):
        granule = struct.unpack_from('<Q', page, 6)[0]
        serial  = struct.unpack_from('<I', page, 14)[0]
        htype   = page[5]
        MAX64   = 0xFFFFFFFFFFFFFFFF

        # BOS (beginning of stream): register the serial and always write.
        if htype & 0x02:
            self._current_serial = serial
            if serial not in self._last_granule:
                self._last_granule[serial] = 0
            self._out.write(page)
            self.pages_written += 1
            return

        # Header / continuation pages (granule 0 or MAX64): always write.
        if granule == 0 or granule == MAX64:
            self._out.write(page)
            self.pages_written += 1
            return

        # Audio page: first occurrence of a new serial after a reconnection?
        # Set the skip threshold based on measured wall-clock gap so the burst
        # overlap from a cross-CDN switch is filtered out.
        if serial not in self._audio_started:
            self._audio_started.add(serial)
            if self._last_audio_write_time is not None:
                gap = time.time() - self._last_audio_write_time
                skip_samples = max(0, int(
                    (self._reconnect_burst - gap) * self.SAMPLE_RATE))
                self._last_granule[serial] = granule + skip_samples
                # Fall through to the normal granule check below.

        # Audio page: write only if it advances the per-serial granule cursor.
        last = self._last_granule.get(serial, 0)
        if granule > last:
            self._last_granule[serial] = granule
            self._last_audio_write_time = time.time()
            self._out.write(page)
            self.pages_written += 1
        else:
            self.pages_skipped += 1   # duplicate from burst overlap, discard


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
    """Extract JWT exp field without signature verification."""
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
        self._stitcher    = None
        self._bytes_recv  = 0
        self._lock        = threading.Lock()

    # ------ public ------
    def record(self):
        self._outfile  = open(self.output_path, "wb")
        self._stitcher = OGGStitcher(self._outfile, reconnect_burst=RECONNECT_BURST)
        start          = time.time()
        first_connection = True
        prefetched     = None   # (location, token) pre-fetched in background

        try:
            while not self._stop:
                elapsed = time.time() - start
                if elapsed >= self.duration_sec:
                    break

                # Use pre-fetched token if ready; otherwise fetch now
                if prefetched is not None:
                    location, token = prefetched
                    prefetched = None
                else:
                    burst = 5 if first_connection else RECONNECT_BURST
                    try:
                        location, token = fetch_token(self.station_id, burst=burst)
                    except Exception as e:
                        print(f"[{self.station_id}] Token fetch error: {e} "
                              f"-- retrying in {FETCH_RETRY_WAIT}s", flush=True)
                        time.sleep(FETCH_RETRY_WAIT)
                        continue
                first_connection = False

                exp       = decode_exp(token)
                valid_for = exp - time.time() - TOKEN_MARGIN
                if valid_for < 1:
                    valid_for = 1

                remaining   = self.duration_sec - elapsed
                ws_duration = min(valid_for, remaining)

                st = self._stitcher
                print(f"[{self.station_id}] "
                      f"elapsed={elapsed:.0f}s  ws_window={ws_duration:.0f}s  "
                      f"recv={self._bytes_recv//1024}KB  "
                      f"skip={st.pages_skipped}pg",
                      flush=True)

                # Pre-fetch the next token in background PREFETCH_BEFORE seconds
                # before this window ends, so reconnection overhead is near zero
                prefetch_result = [None]
                prefetch_error  = [None]

                def _prefetch(delay):
                    time.sleep(delay)
                    if self._stop:
                        return
                    try:
                        prefetch_result[0] = fetch_token(
                            self.station_id, burst=RECONNECT_BURST)
                    except Exception as e:
                        prefetch_error[0] = e

                prefetch_delay = max(0, ws_duration - PREFETCH_BEFORE)
                pf_thread = threading.Thread(
                    target=_prefetch, args=(prefetch_delay,), daemon=True)
                pf_thread.start()

                # Run the WebSocket for this window
                self._run_ws(location, token, ws_duration)

                # Wait briefly for prefetch to finish if it hasn't yet
                pf_thread.join(timeout=CONNECT_TIMEOUT)

                if prefetch_result[0] is not None:
                    prefetched = prefetch_result[0]
                elif prefetch_error[0] is not None:
                    print(f"[{self.station_id}] Prefetch error: {prefetch_error[0]} "
                          f"-- will retry at reconnect", flush=True)

        finally:
            self._outfile.close()
            st = self._stitcher
            print(f"[{self.station_id}] Done. "
                  f"Total recv={self._bytes_recv//1024}KB  "
                  f"Pages written={st.pages_written}  skipped={st.pages_skipped}  "
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
        deadline   = time.time() + duration_sec
        done_event = threading.Event()

        def on_open(ws):
            # Send token as first text message (Radimo protocol)
            ws.send(token)

        def on_message(ws, message):
            if isinstance(message, bytes):
                with self._lock:
                    self._stitcher.feed(message)
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
