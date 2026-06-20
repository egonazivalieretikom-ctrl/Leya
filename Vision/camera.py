import cv2
import time

from Vision.object_vision import ObjectVision

class CameraEye:

    def __init__(self, brain, camera_id=0):

        self.brain = brain
        self.cap = cv2.VideoCapture(camera_id)

        self.last_frame_time = 0
        self.vision = ObjectVision(brain)
        print("[CAMERA INIT] opened:", self.cap.isOpened())

    def capture(self):

        ret, frame = self.cap.read()

        if not ret:
            return

        frame = cv2.resize(frame, (320, 240))

        raw_objects = self.vision.process(frame)

        enriched = self.brain.perception.ingest_objects(raw_objects)

        scene = self.brain.perception.summarize_scene(enriched)

        self.brain.workspace.add(
            source="vision",
            kind="scene",
            content=scene,
            priority=0.3 + scene["novelty"]
        )

        dominant = scene["dominant"]

        if dominant:

            self.brain.state.attention_focus = "scene"
            self.brain.state.attention_strength = scene["novelty"]

    def _detect_motion(self, frame):

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if not hasattr(self, "prev"):
            self.prev = gray
            return 0.0

        diff = cv2.absdiff(self.prev, gray)

        self.prev = gray

        return float(diff.mean())

    def _priority(self, brightness, motion):

        # простая эвристика значимости
        return min(1.0, (motion / 50.0) + 0.2)