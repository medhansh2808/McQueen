#!/usr/bin/env python3

import cv2
import depthai as dai
import numpy as np
import os
import json
import time
from datetime import datetime

# ---- Setup logging directories ----
SESSION_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_DIR = f"logs/{SESSION_ID}"
IMG_DIR = f"{LOG_DIR}/images"
DEPTH_DIR = f"{LOG_DIR}/depth_raw"
LABEL_DIR = f"{LOG_DIR}/labels"

os.makedirs(IMG_DIR, exist_ok=True)
os.makedirs(DEPTH_DIR, exist_ok=True)
os.makedirs(LABEL_DIR, exist_ok=True)

metadataFile = open(f"{LOG_DIR}/metadata.jsonl", "a")

modelDescription = dai.NNModelDescription("yolov6-nano")
size = (640, 400)
fps = 20

LOG_EVERY_N_FRAMES = 5  # tune this — don't need to log every single frame

class SpatialVisualizer(dai.node.HostNode):
    def __init__(self):
        dai.node.HostNode.__init__(self)
        self.sendProcessingToPipeline(True)
        self.frameCount = 0

    def build(self, depth, detections, rgb):
        self.link_args(depth, detections, rgb)

    def process(self, depthPreview, detections, rgbPreview):
        depthFrame = depthPreview.getCvFrame()
        rgbFrame = rgbPreview.getCvFrame()
        depthFrameColor = self.processDepthFrame(depthFrame)

        self.displayResults(rgbFrame, depthFrameColor, detections.detections)

        self.frameCount += 1
        if self.frameCount % LOG_EVERY_N_FRAMES == 0:
            self.logFrame(rgbFrame, depthFrame, detections.detections)

    def processDepthFrame(self, depthFrame):
        depthDownscaled = depthFrame[::4]
        minDepth = 0 if np.all(depthDownscaled == 0) else np.percentile(depthDownscaled[depthDownscaled != 0], 1)
        maxDepth = np.percentile(depthDownscaled, 99)
        depthFrameColor = np.interp(depthFrame, (minDepth, maxDepth), (0, 255)).astype(np.uint8)
        return cv2.applyColorMap(depthFrameColor, cv2.COLORMAP_HOT)

    def displayResults(self, rgbFrame, depthFrameColor, detections):
        h, w, _ = rgbFrame.shape
        for detection in detections:
            self.drawDetections(rgbFrame, detection, w, h)
        cv2.imshow("Depth frame", depthFrameColor)
        cv2.imshow("Color frame", rgbFrame)
        if cv2.waitKey(1) == ord('q'):
            self.stopPipeline()

    def drawDetections(self, frame, detection, frameWidth, frameHeight):
        x1, x2 = int(detection.xmin * frameWidth), int(detection.xmax * frameWidth)
        y1, y2 = int(detection.ymin * frameHeight), int(detection.ymax * frameHeight)
        color = (255, 255, 255)
        cv2.putText(frame, detection.labelName, (x1 + 10, y1 + 20), cv2.FONT_HERSHEY_TRIPLEX, 0.5, color)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)

    def logFrame(self, rgbFrame, depthFrame, detections):
        timestamp = time.time()
        frameId = f"{self.frameCount:06d}"

        # 1. Save RGB image (this becomes your training image)
        imgPath = f"{IMG_DIR}/{frameId}.jpg"
        cv2.imwrite(imgPath, rgbFrame)

        # 2. Save raw depth as .npy (16-bit, full precision — useful for depth-aware training later)
        depthPath = f"{DEPTH_DIR}/{frameId}.npy"
        np.save(depthPath, depthFrame)

        # 3. Save YOLO-format label file (class x_center y_center width height, all normalized 0-1)
        # This lets you directly reuse this data to retrain/finetune a YOLO model later
        labelPath = f"{LABEL_DIR}/{frameId}.txt"
        with open(labelPath, "w") as labelFile:
            for det in detections:
                xCenter = (det.xmin + det.xmax) / 2
                yCenter = (det.ymin + det.ymax) / 2
                width = det.xmax - det.xmin
                height = det.ymax - det.ymin
                labelFile.write(f"{det.label} {xCenter:.6f} {yCenter:.6f} {width:.6f} {height:.6f}\n")

        # 4. Save rich metadata (spatial coords, confidence, timestamps) — not needed for YOLO training
        # but crucial for anything involving distance/motion (e.g. training a driving policy later)
        detectionsMeta = []
        for det in detections:
            detectionsMeta.append({
                "label": det.labelName,
                "labelId": det.label,
                "confidence": round(det.confidence, 4),
                "bbox_normalized": {
                    "xmin": det.xmin, "ymin": det.ymin,
                    "xmax": det.xmax, "ymax": det.ymax
                },
                "spatial_mm": {
                    "x": det.spatialCoordinates.x,
                    "y": det.spatialCoordinates.y,
                    "z": det.spatialCoordinates.z
                }
            })

        record = {
            "frame_id": frameId,
            "timestamp": timestamp,
            "image_path": imgPath,
            "depth_path": depthPath,
            "label_path": labelPath,
            "num_detections": len(detections),
            "detections": detectionsMeta
        }
        metadataFile.write(json.dumps(record) + "\n")
        metadataFile.flush()  # write immediately, don't lose data on crash

with dai.Pipeline() as p:
    camRgb = p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A, sensorFps=fps)
    monoLeft = p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_B, sensorFps=fps)
    monoRight = p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_C, sensorFps=fps)

    stereo = p.create(dai.node.StereoDepth)
    stereo.setExtendedDisparity(True)
    monoLeft.requestOutput(size).link(stereo.left)
    monoRight.requestOutput(size).link(stereo.right)

    spatialDetectionNetwork = p.create(dai.node.SpatialDetectionNetwork).build(camRgb, stereo, modelDescription)
    spatialDetectionNetwork.input.setBlocking(False)
    spatialDetectionNetwork.setDepthLowerThreshold(100)
    spatialDetectionNetwork.setDepthUpperThreshold(5000)

    visualizer = p.create(SpatialVisualizer)
    visualizer.build(spatialDetectionNetwork.passthroughDepth, spatialDetectionNetwork.out, spatialDetectionNetwork.passthrough)

    print(f"Logging session: {SESSION_ID}")
    print(f"Saving to: {LOG_DIR}")
    p.run()

metadataFile.close()
