"""YOLO + ByteTrack zone presence, with webcam preview or Docker video replay."""
import argparse
import math
import signal
import time


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="0", help="Webcam index or local video filename")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default="yolo11n.pt")
    parser.add_argument("--zone", nargs=4, type=float, default=[.15,.15,.85,.95],
                        metavar=("LEFT","TOP","RIGHT","BOTTOM"), help="Normalized rectangle, 0 to 1")
    parser.add_argument("--headless", action="store_true", help="Send presence without opening a desktop window")
    parser.add_argument("--loop", action="store_true", help="Replay a local video repeatedly for the demo")
    parser.add_argument("--max-fps", type=float, default=5, help="Maximum inference rate; default 5 frames/s")
    args = parser.parse_args(argv)
    x0,y0,x1,y1 = args.zone
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        parser.error("Zone coordinates must describe a valid normalized rectangle")
    if not math.isfinite(args.max_fps) or not 0 < args.max_fps <= 60:
        parser.error("--max-fps must be between 0 and 60")
    if args.loop and args.source.isdigit():
        parser.error("--loop is for a recorded video, not a webcam")
    return args


def zone_presence(coordinates, confidences, zone):
    """A 2D bounding-box footpoint supplies occupancy, not physical distance."""
    present, confidence = False, 0.0
    for (left,top,right,bottom), conf in zip(coordinates, confidences):
        foot = ((left+right)/2, bottom)
        if zone[0] <= foot[0] <= zone[2] and zone[1] <= foot[1] <= zone[3]:
            present, confidence = True, max(confidence, float(conf))
    return present, confidence


def main():
    args = parse_args()
    def stop(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    # Optional dependencies stay outside the core safety/backend container.
    import cv2
    import httpx
    from ultralytics import YOLO

    source = int(args.source) if args.source.isdigit() else args.source
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError("Cannot open the requested video or webcam")
    client = httpx.Client(timeout=3, trust_env=False)
    x0,y0,x1,y1 = args.zone
    last_post, frame_in_pass = 0.0, False
    try:
        model = YOLO(args.model)  # download the weights before presenting
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        if not math.isfinite(video_fps) or video_fps <= 0:
            video_fps = 30.0
        stride = max(1, math.ceil(video_fps/args.max_fps)) if isinstance(source, str) else 1
        period = stride/video_fps if isinstance(source, str) else 1/args.max_fps
        while True:
            started = time.monotonic()
            ok, frame = cap.read()
            if not ok:
                if args.loop and frame_in_pass and cap.set(cv2.CAP_PROP_POS_FRAMES, 0):
                    frame_in_pass = False
                    continue
                break
            frame_in_pass = True
            height,width = frame.shape[:2]
            zone = (int(x0*width),int(y0*height),int(x1*width),int(y1*height))
            results = model.track(frame, persist=True, tracker="bytetrack.yaml", classes=[0], conf=.4, verbose=False)
            boxes = results[0].boxes
            present, confidence = zone_presence(
                boxes.xyxy.cpu().tolist() if boxes is not None else [],
                boxes.conf.cpu().tolist() if boxes is not None else [], zone)
            now = time.monotonic()
            if now-last_post >= .3:
                observation = {"present":present,"valid":True,"source":"vision","confidence":confidence}
                client.post(args.api.rstrip("/")+"/api/vision", json=observation).raise_for_status()
                if args.headless:
                    print("Zone presence:", present, "confidence:", round(confidence,3), flush=True)
                last_post = now
            if not args.headless:
                display = results[0].plot()
                cv2.rectangle(display,zone[:2],zone[2:],(0,140,255),2)
                cv2.putText(display,"MONITORED ZONE: "+("PERSON PRESENT" if present else "NO PERSON DETECTED"),
                            (15,25),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,140,255),2)
                cv2.imshow("PURVA SANKET | YOLO + ByteTrack",display)
                if cv2.waitKey(1)&0xFF == ord("q"):
                    break
            for _ in range(stride-1):
                if not cap.grab():
                    break
            time.sleep(max(0.0, period-(time.monotonic()-started)))
    finally:
        try:
            client.post(args.api.rstrip("/")+"/api/vision",json={"present":False,"valid":False,"source":"vision"})
        finally:
            cap.release()
            if not args.headless:
                cv2.destroyAllWindows()
            client.close()


if __name__ == "__main__":
    main()
