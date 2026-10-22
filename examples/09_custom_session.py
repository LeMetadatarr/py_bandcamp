"""09_custom_session — inject a custom session; optional curl_cffi for search.

Three patterns:
  1. Global set_session() — affects every subsequent call in the process.
  2. Per-instance BandCamp(session=...) — leaves global session untouched.
  3. curl_cffi via PYBANDCAMP_TRANSPORT env var or explicit default_session().
"""
import os
import requests as _requests

from py_bandcamp import BandCamp, set_session, get_session
from py_bandcamp.transport import default_session

TRACK_URL = "https://deadunicorn.bandcamp.com/track/astronaut-problems"

# --- 1. Global session replacement ---
custom = _requests.Session()
custom.headers["User-Agent"] = "my-ingestor/1.0"
set_session(custom)
print(f"Global session: {type(get_session()).__name__}")

# Verify a fetch still works through the new session
url = BandCamp.get_stream_url(TRACK_URL)
print(f"Stream URL (custom global session): {url[:60]}...")

# --- 2. Per-instance session ---
instance_session = _requests.Session()
instance_session.headers["User-Agent"] = "per-instance/1.0"
bc = BandCamp(session=instance_session)
release = bc.track_to_release(TRACK_URL)
print(f"\nPer-instance release title: {release.work.title}")

# --- 3. curl_cffi (for search pages blocked by Fastly) ---
# Requires: pip install "py_bandcamp[stealth]"
# With PYBANDCAMP_TRANSPORT=curl_cffi set, default_session() returns
# a curl_cffi session automatically. You can also build it explicitly:

if os.environ.get("PYBANDCAMP_TRANSPORT", "").lower() == "curl_cffi":
    try:
        stealth_session = default_session()
        print(f"\ncurl_cffi session: {type(stealth_session).__name__}")
        bc_stealth = BandCamp(session=stealth_session)
        for i, r in enumerate(bc_stealth.search_albums("black metal")):
            print(f"  [{i+1}] {r.work.title}  {r.uri}")
            if i >= 2:
                break
    except ImportError:
        print("\ncurl_cffi not installed; skipping stealth search demo.")
else:
    print("\nSet PYBANDCAMP_TRANSPORT=curl_cffi and install py_bandcamp[stealth]")
    print("to enable the curl_cffi search demo.")
