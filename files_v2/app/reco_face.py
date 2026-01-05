# filepath: /media/ybouzid/Y2_3_Dat1/projet/pweb/Api_robot/Ams-Projet-/files_v2/app/reco_face.py

"""reco_face.py

Implements the Choregraphe flow:
- Start face detection
- Wait until a face is detected
- Take a picture
- Call localhost API /verify with the captured image

Notes:
- This script targets NAOqi (Pepper/NAO). It can run on-robot or from a remote machine.
- Configure NAO_IP/NAO_PORT via env vars or CLI args.
- Configure VERIFY_URL via env var.
"""

from __future__ import print_function

import argparse
import base64
import os
import sys
import time

try:
    import qi  # NAOqi Python SDK
except Exception as e:
    qi = None

try:
    import requests
except Exception:
    requests = None


DEFAULT_VERIFY_URL = os.environ.get("VERIFY_URL", "http://0.0.0.0:8000/verify")
DEFAULT_NAO_IP = "192.168.13.66"
DEFAULT_NAO_PORT = "9559"


class FaceRecoFlow(object):
    def __init__(self, session, verify_url=DEFAULT_VERIFY_URL, camera_id=0, resolution=2, color_space=11):
        self.session = session
        self.verify_url = verify_url
        self.camera_id = camera_id
        self.resolution = resolution
        self.color_space = color_space

        self.mem = session.service("ALMemory")
        self.face = session.service("ALFaceDetection")
        self.video = session.service("ALVideoDevice")

        self._subscriber_name = None

    def start_face_detection(self):
        # Face detection publishes to ALMemory key 'FaceDetected'
        # Enable detection and tracking (kept minimal)
        try:
            self.face.setRecognitionEnabled(False)
        except Exception:
            pass

        self._subscriber_name = "reco_face_{}".format(int(time.time()))
        sub = self.face.subscribe(self._subscriber_name, 500, 0.0)
        return sub

    def stop_face_detection(self):
        if self._subscriber_name:
            try:
                self.face.unsubscribe(self._subscriber_name)
            except Exception:
                pass
            self._subscriber_name = None

    def wait_for_face(self, timeout_s=15.0, poll_s=0.2):
        """Waits for FaceDetected memory entry to be non-empty."""
        deadline = time.time() + float(timeout_s)
        last = None
        while time.time() < deadline:
            try:
                val = self.mem.getData("FaceDetected")
            except Exception:
                val = None

            if val and val != last:
                # val is usually [TimeStamp, [FaceInfo...]]
                return val
            last = val
            time.sleep(poll_s)
        return None

    def take_picture(self):
        """Captures one frame and returns (jpg_bytes, meta_dict)."""
        client = None
        try:
            client = self.video.subscribeCamera(
                "reco_face_cam_{}".format(int(time.time())),
                int(self.camera_id),
                int(self.resolution),
                int(self.color_space),
                10,
            )

            img = self.video.getImageRemote(client)
            if not img or len(img) < 7:
                raise RuntimeError("Failed to capture image from camera")

            width, height = img[0], img[1]
            # img[6] is the image buffer as a Python str/bytes depending on NAOqi
            raw = img[6]
            if isinstance(raw, str):
                raw = raw.encode("latin-1")

            # Convert raw bytes to base64 payload; avoid on-robot heavy deps.
            # color_space=11 is kBGRColorSpace on NAOqi; raw is (w*h*3).
            # Many verify APIs accept base64 raw or base64-encoded JPEG.
            # Here we send raw bytes base64 with metadata.
            meta = {
                "width": int(width),
                "height": int(height),
                "camera_id": int(self.camera_id),
                "resolution": int(self.resolution),
                "color_space": int(self.color_space),
                "format": "raw_bgr" if int(self.color_space) == 11 else "raw",
            }
            return raw, meta
        finally:
            if client:
                try:
                    self.video.unsubscribe(client)
                except Exception:
                    pass

    def call_verify_api(self, image_bytes, meta=None, timeout_s=10.0):
        if requests is None:
            raise RuntimeError("The 'requests' library is required to call the verify API")

        payload = {
            "image": base64.b64encode(image_bytes).decode("ascii"),
        }
        if meta:
            payload["meta"] = meta

        resp = requests.post(self.verify_url, json=payload, timeout=float(timeout_s))
        resp.raise_for_status()
        # return json if possible
        ctype = resp.headers.get("Content-Type", "")
        if "application/json" in ctype:
            return resp.json()
        return {"status_code": resp.status_code, "text": resp.text}


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]

    parser = argparse.ArgumentParser(description="Face detection -> take picture -> call localhost /verify")
    parser.add_argument("--ip", default=DEFAULT_NAO_IP, help="Robot IP")
    parser.add_argument("--port", type=int, default=DEFAULT_NAO_PORT, help="Robot port")
    parser.add_argument("--verify-url", default=DEFAULT_VERIFY_URL, help="Verify API URL")
    parser.add_argument("--timeout", type=float, default=15.0, help="Seconds to wait for a face")
    parser.add_argument("--camera", type=int, default=0, help="Camera id (0=top, 1=bottom)")
    parser.add_argument("--resolution", type=int, default=2, help="NAOqi resolution (2=VGA)")
    parser.add_argument("--colorspace", type=int, default=11, help="NAOqi colorspace (11=kBGRColorSpace)")
    args = parser.parse_args(argv)

    if qi is None:
        raise RuntimeError("NAOqi 'qi' module not available. Run on robot or in a NAOqi SDK environment.")

    session = qi.Session()
    session.connect("tcp://{}:{}".format(args.ip, args.port))

    flow = FaceRecoFlow(
        session,
        verify_url=args.verify_url,
        camera_id=args.camera,
        resolution=args.resolution,
        color_space=args.colorspace,
    )

    flow.start_face_detection()
    try:
        face_data = flow.wait_for_face(timeout_s=args.timeout)
        if not face_data:
            print("No face detected within timeout")
            return 2

        image_bytes, meta = flow.take_picture()
        result = flow.call_verify_api(image_bytes, meta=meta)
        print("verify result:")
        print(result)
        return 0
    finally:
        flow.stop_face_detection()


if __name__ == "__main__":
    raise SystemExit(main())
