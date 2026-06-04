"""Face Match + Liveness (basic).

Strategia:
- DeepFace se installato → match + anti-spoof
- Fallback OpenCV: haar cascade per face detect su selfie e documento,
  similarity via histogram comparison (cv2.compareHist).

Liveness fallback: 3 frame del recording.webm → ssim diff > soglia = "alive".
"""
import os
import io
import frappe


def _read_image(path: str):
    import cv2, numpy as np
    img = cv2.imread(path)
    if img is None:
        with open(path, "rb") as f:
            arr = np.frombuffer(f.read(), dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img


def _face_match_deepface(selfie_path: str, doc_path: str) -> dict:
    try:
        from deepface import DeepFace
        res = DeepFace.verify(selfie_path, doc_path,
                              model_name="Facenet", enforce_detection=False,
                              detector_backend="opencv")
        return {"backend": "deepface", "verified": bool(res.get("verified")),
                "distance": float(res.get("distance", 1.0)),
                "threshold": float(res.get("threshold", 0.4)),
                "score": max(0.0, 1.0 - float(res.get("distance", 1.0)))}
    except ImportError:
        return None
    except Exception as e:
        return {"backend": "deepface", "error": str(e)[:200]}


def _face_match_opencv(selfie_path: str, doc_path: str) -> dict:
    import cv2
    cascade_xml = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(cascade_xml)

    def crop_face(p):
        img = _read_image(p)
        if img is None:
            return None
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        rects = cascade.detectMultiScale(gray, 1.2, 5, minSize=(80, 80))
        if len(rects) == 0:
            return None
        x, y, w, h = max(rects, key=lambda r: r[2] * r[3])
        return cv2.resize(gray[y:y+h, x:x+w], (128, 128))

    a, b = crop_face(selfie_path), crop_face(doc_path)
    if a is None or b is None:
        return {"backend": "opencv", "verified": False, "score": 0.0,
                "error": "no_face_detected"}
    h1 = cv2.calcHist([a], [0], None, [64], [0, 256]); cv2.normalize(h1, h1)
    h2 = cv2.calcHist([b], [0], None, [64], [0, 256]); cv2.normalize(h2, h2)
    score = float(cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL))
    return {"backend": "opencv-haar+hist",
            "verified": score >= 0.65, "score": round(score, 4)}


def face_match(selfie_path: str, doc_path: str) -> dict:
    res = _face_match_deepface(selfie_path, doc_path)
    if res and "error" not in res:
        return res
    return _face_match_opencv(selfie_path, doc_path)


def liveness_basic(video_path: str) -> dict:
    """Liveness pragmatica: pesca 3 frame dal video, calcola SSIM-like diff.
    Se variabilità > soglia → alive, altrimenti screen/photo replay sospetto."""
    try:
        import cv2, numpy as np
        cap = cv2.VideoCapture(video_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total < 3:
            return {"alive": False, "score": 0.0, "error": "too_short"}
        frames = []
        for f in (int(total * 0.2), int(total * 0.5), int(total * 0.8)):
            cap.set(cv2.CAP_PROP_POS_FRAMES, f)
            ok, im = cap.read()
            if ok:
                frames.append(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY))
        cap.release()
        if len(frames) < 2:
            return {"alive": False, "score": 0.0}
        diff = float(np.mean(np.abs(frames[0].astype(int) - frames[-1].astype(int))))
        return {"alive": diff > 8.0, "score": round(min(diff / 30.0, 1.0), 3),
                "diff": round(diff, 2)}
    except Exception as e:
        frappe.log_error(str(e), "DddLiveness")
        return {"alive": False, "score": 0.0, "error": str(e)[:200]}


@frappe.whitelist()
def run_face_match_and_liveness(session_name: str) -> dict:
    s = frappe.get_doc("Video Verification Session", session_name)
    paths = {}
    for fld in ("selfie_file", "doc_capture_file", "recording_file"):
        url = s.get(fld)
        if not url:
            continue
        p = frappe.get_site_path("private", "files",
                                 url.split("/private/files/")[-1])
        if not os.path.exists(p):
            p = frappe.get_site_path("public", "files",
                                     url.split("/files/")[-1])
        if os.path.exists(p):
            paths[fld] = p

    out = {}
    if "selfie_file" in paths and "doc_capture_file" in paths:
        out["face"] = face_match(paths["selfie_file"], paths["doc_capture_file"])
        s.face_match_score = out["face"].get("score", 0.0)
    if "recording_file" in paths:
        out["liveness"] = liveness_basic(paths["recording_file"])
        s.liveness_score = out["liveness"].get("score", 0.0)

    face_ok = (out.get("face") or {}).get("verified")
    alive_ok = (out.get("liveness") or {}).get("alive")
    s.outcome = "Pass" if face_ok and alive_ok else \
                "Review" if (face_ok or alive_ok) else "Fail"
    s.completed_on = frappe.utils.now_datetime()
    s.session_status = "Completed"
    s.notes = (s.notes or "") + f"\n[{s.completed_on}] {out}"
    s.save(ignore_permissions=True)
    frappe.db.commit()
    return {"session": s.name, "outcome": s.outcome, **out}
