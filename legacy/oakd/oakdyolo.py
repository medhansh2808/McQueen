import cv2
import depthai as dai
import numpy as np

modelDescription = dai.NNModelDescription("yolov6-nano")
size = (640, 400)
fps = 20

class SpatialVisualizer(dai.node.HostNode):
    def __init__(self):
        dai.node.HostNode.__init__(self)
        self.sendProcessingToPipeline(True)

    def build(self, depth, detections, rgb):
        self.link_args(depth, detections, rgb)

    def process(self, depthPreview, detections, rgbPreview):
        depthPreview = depthPreview.getCvFrame()
        rgbPreview = rgbPreview.getCvFrame()
        depthFrameColor = self.processDepthFrame(depthPreview)
        self.displayResults(rgbPreview, depthFrameColor, detections.detections)

    def processDepthFrame(self, depthFrame):
        depthDownscaled = depthFrame[::4]
        minDepth = 0 if np.all(depthDownscaled == 0) else np.percentile(depthDownscaled[depthDownscaled != 0], 1)
        maxDepth = np.percentile(depthDownscaled, 99)
        depthFrameColor = np.interp(depthFrame, (minDepth, maxDepth), (0, 255)).astype(np.uint8)
        return cv2.applyColorMap(depthFrameColor, cv2.COLORMAP_HOT)

    def displayResults(self, rgbFrame, depthFrameColor, detections):
        height, width, _ = rgbFrame.shape
        for detection in detections:
            self.drawBoundingBoxes(depthFrameColor, detection)
            self.drawDetections(rgbFrame, detection, width, height)
        cv2.imshow("Depth frame", depthFrameColor)
        cv2.imshow("Color frame", rgbFrame)
        if cv2.waitKey(1) == ord('q'):
            self.stopPipeline()

    def drawBoundingBoxes(self, depthFrameColor, detection):
        roi = detection.boundingBoxMapping.roi.denormalize(depthFrameColor.shape[1], depthFrameColor.shape[0])
        cv2.rectangle(depthFrameColor, (int(roi.topLeft().x), int(roi.topLeft().y)),
                      (int(roi.bottomRight().x), int(roi.bottomRight().y)), (255, 255, 255), 1)

    def drawDetections(self, frame, detection, frameWidth, frameHeight):
        x1, x2 = int(detection.xmin * frameWidth), int(detection.xmax * frameWidth)
        y1, y2 = int(detection.ymin * frameHeight), int(detection.ymax * frameHeight)
        color = (255, 255, 255)
        cv2.putText(frame, detection.labelName, (x1 + 10, y1 + 20), cv2.FONT_HERSHEY_TRIPLEX, 0.5, color)
        cv2.putText(frame, "{:.2f}".format(detection.confidence * 100), (x1 + 10, y1 + 35), cv2.FONT_HERSHEY_TRIPLEX, 0.5, color)
        cv2.putText(frame, f"X: {int(detection.spatialCoordinates.x)} mm", (x1 + 10, y1 + 50), cv2.FONT_HERSHEY_TRIPLEX, 0.5, color)
        cv2.putText(frame, f"Y: {int(detection.spatialCoordinates.y)} mm", (x1 + 10, y1 + 65), cv2.FONT_HERSHEY_TRIPLEX, 0.5, color)
        cv2.putText(frame, f"Z: {int(detection.spatialCoordinates.z)} mm", (x1 + 10, y1 + 80), cv2.FONT_HERSHEY_TRIPLEX, 0.5, color)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)

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

    print("Starting pipeline")
    p.run()
