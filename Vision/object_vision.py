import cv2


class ObjectVision:

    def __init__(self, brain):
        self.brain = brain
        self.prev_frame = None

    def process(self, frame):

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (7, 7), 0)

        if self.prev_frame is None:
            self.prev_frame = gray
            return []

        diff = cv2.absdiff(self.prev_frame, gray)
        _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
        thresh = cv2.dilate(thresh, None, iterations=2)

        contours, _ = cv2.findContours(
            thresh,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        objects = []

        for c in contours:

            if cv2.contourArea(c) < 500:
                continue

            x, y, w, h = cv2.boundingRect(c)

            objects.append({
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "cx": x + w / 2,
                "cy": y + h / 2,
                "area": w * h
            })

        self.prev_frame = gray

        return objects