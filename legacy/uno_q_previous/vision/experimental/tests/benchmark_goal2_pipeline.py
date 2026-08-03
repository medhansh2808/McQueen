#!/usr/bin/env python3

import time
from pathlib import Path

import depthai as dai
import numpy as np


MODEL_PATH = Path(
    "/home/arduino/McQueen/models/"
    "yolov6nr1_coco_512x288_openvino_2022.1_6shave.blob"
)

SNAPSHOT_PATH = Path(
    "/home/arduino/McQueen/vision/tests/"
    "full_fov_1080p.jpg"
)

TARGET_FPS = 30
TEST_SECONDS = 15.0

RGB_WIDTH = 1920
RGB_HEIGHT = 1080

NN_WIDTH = 512
NN_HEIGHT = 288


def apply_openvino_version(
    pipeline: dai.Pipeline,
) -> None:

    version = getattr(
        dai.OpenVINO.Version,
        "VERSION_2022_1",
        None,
    )

    if version is not None:
        pipeline.setOpenVINOVersion(
            version
        )

        print(
            "[CONFIG] OpenVINO 2022.1"
        )
    else:
        print(
            "[WARNING] OpenVINO 2022.1 "
            "enum unavailable"
        )


def create_pipeline() -> dai.Pipeline:
    pipeline = dai.Pipeline()

    apply_openvino_version(
        pipeline
    )

    # -------------------------------------------------
    # Full-sensor colour camera
    # -------------------------------------------------

    camera = pipeline.create(
        dai.node.ColorCamera
    )

    camera.setBoardSocket(
        dai.CameraBoardSocket.CAM_A
    )

    camera.setResolution(
        dai.ColorCameraProperties
        .SensorResolution
        .THE_4_K
    )

    camera.setFps(
        TARGET_FPS
    )

    # Native 4056x3040 ISP output scaled near 2K,
    # then letterboxed to 1920x1080.
    camera.setIspScale(
        1,
        2,
    )

    try:
        camera.setImageOrientation(
            dai.CameraImageOrientation
            .ROTATE_180_DEG
        )

        print(
            "[CONFIG] RGB rotation: 180 degrees"
        )

    except Exception as error:
        print(
            f"[WARNING] Rotation unavailable: "
            f"{error}"
        )

    # -------------------------------------------------
    # Full-view, no-crop 1920x1080 RGB output
    # -------------------------------------------------

    full_view = pipeline.create(
        dai.node.ImageManip
    )

    full_view.initialConfig.setResizeThumbnail(
        RGB_WIDTH,
        RGB_HEIGHT,
    )

    full_view.initialConfig.setFrameType(
        dai.RawImgFrame.Type.NV12
    )

    full_view.setMaxOutputFrameSize(
        RGB_WIDTH
        * RGB_HEIGHT
        * 3
        // 2
    )

    full_view.inputImage.setBlocking(
        False
    )

    full_view.inputImage.setQueueSize(
        1
    )

    camera.isp.link(
        full_view.inputImage
    )

    encoder = pipeline.create(
        dai.node.VideoEncoder
    )

    encoder.setDefaultProfilePreset(
        TARGET_FPS,
        dai.VideoEncoderProperties
        .Profile
        .MJPEG,
    )

    try:
        encoder.setQuality(90)
    except Exception:
        pass

    full_view.out.link(
        encoder.input
    )

    rgb_output = pipeline.create(
        dai.node.XLinkOut
    )

    rgb_output.setStreamName(
        "rgb_jpeg"
    )

    encoder.bitstream.link(
        rgb_output.input
    )

    # -------------------------------------------------
    # Same full view, letterboxed to YOLO input
    # -------------------------------------------------

    nn_manip = pipeline.create(
        dai.node.ImageManip
    )

    nn_manip.initialConfig.setResizeThumbnail(
        NN_WIDTH,
        NN_HEIGHT,
    )

    nn_manip.initialConfig.setFrameType(
        dai.RawImgFrame.Type.BGR888p
    )

    nn_manip.setMaxOutputFrameSize(
        NN_WIDTH
        * NN_HEIGHT
        * 3
    )

    nn_manip.inputImage.setBlocking(
        False
    )

    nn_manip.inputImage.setQueueSize(
        1
    )

    camera.isp.link(
        nn_manip.inputImage
    )

    network = pipeline.create(
        dai.node.NeuralNetwork
    )

    network.setBlobPath(
        str(MODEL_PATH)
    )

    network.setNumInferenceThreads(
        2
    )

    network.input.setBlocking(
        False
    )

    network.input.setQueueSize(
        1
    )

    nn_manip.out.link(
        network.input
    )

    nn_output = pipeline.create(
        dai.node.XLinkOut
    )

    nn_output.setStreamName(
        "nn"
    )

    network.out.link(
        nn_output.input
    )

    # -------------------------------------------------
    # Stereo depth
    # -------------------------------------------------

    left = pipeline.create(
        dai.node.MonoCamera
    )

    right = pipeline.create(
        dai.node.MonoCamera
    )

    left.setBoardSocket(
        dai.CameraBoardSocket.CAM_B
    )

    right.setBoardSocket(
        dai.CameraBoardSocket.CAM_C
    )

    left.setResolution(
        dai.MonoCameraProperties
        .SensorResolution
        .THE_400_P
    )

    right.setResolution(
        dai.MonoCameraProperties
        .SensorResolution
        .THE_400_P
    )

    left.setFps(
        TARGET_FPS
    )

    right.setFps(
        TARGET_FPS
    )

    stereo = pipeline.create(
        dai.node.StereoDepth
    )

    preset_default = getattr(
        dai.node.StereoDepth.PresetMode,
        "DEFAULT",
        None,
    )

    if preset_default is not None:
        stereo.setDefaultProfilePreset(
            preset_default
        )
    else:
        stereo.setDefaultProfilePreset(
            dai.node.StereoDepth
            .PresetMode
            .HIGH_DENSITY
        )

    stereo.setLeftRightCheck(
        True
    )

    stereo.setSubpixel(
        False
    )

    try:
        stereo.setDepthAlign(
            dai.CameraBoardSocket.CAM_A
        )

        print(
            "[CONFIG] Depth aligned to RGB"
        )

    except Exception as error:
        print(
            f"[WARNING] Depth alignment "
            f"unavailable: {error}"
        )

    try:
        stereo.setOutputSize(
            640,
            360,
        )

        print(
            "[CONFIG] Depth output: 640x360"
        )

    except Exception as error:
        print(
            f"[WARNING] Stereo output resize "
            f"unavailable: {error}"
        )

    left.out.link(
        stereo.left
    )

    right.out.link(
        stereo.right
    )

    depth_output = pipeline.create(
        dai.node.XLinkOut
    )

    depth_output.setStreamName(
        "depth"
    )

    stereo.depth.link(
        depth_output.input
    )

    return pipeline


def main() -> None:
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(
            MODEL_PATH
        )

    pipeline = create_pipeline()

    print()
    print(
        "[START] Opening complete Goal 2 pipeline"
    )

    print(
        "[TARGET] RGB=30 Hz, depth=30 Hz, "
        "YOLO target=30 Hz"
    )

    with dai.Device(
        pipeline,
        dai.UsbSpeed.HIGH,
    ) as device:

        print(
            "[DEVICE] OAK-D opened"
        )

        print(
            "[DEVICE] USB:",
            device.getUsbSpeed(),
        )

        rgb_queue = device.getOutputQueue(
            name="rgb_jpeg",
            maxSize=8,
            blocking=False,
        )

        depth_queue = device.getOutputQueue(
            name="depth",
            maxSize=8,
            blocking=False,
        )

        nn_queue = device.getOutputQueue(
            name="nn",
            maxSize=8,
            blocking=False,
        )

        rgb_count = 0
        depth_count = 0
        nn_count = 0

        snapshot_saved = False
        depth_checked = False
        nn_layers_printed = False

        start = time.monotonic()
        deadline = start + TEST_SECONDS

        while time.monotonic() < deadline:
            rgb_packet = rgb_queue.tryGet()

            if rgb_packet is not None:
                rgb_count += 1

                if not snapshot_saved:
                    jpeg_data = (
                        rgb_packet
                        .getData()
                        .tobytes()
                    )

                    SNAPSHOT_PATH.write_bytes(
                        jpeg_data
                    )

                    print(
                        f"[RGB] Saved snapshot: "
                        f"{SNAPSHOT_PATH}"
                    )

                    print(
                        f"[RGB] JPEG bytes: "
                        f"{len(jpeg_data)}"
                    )

                    snapshot_saved = True

            depth_packet = (
                depth_queue.tryGet()
            )

            if depth_packet is not None:
                depth_count += 1

                if not depth_checked:
                    depth_frame = (
                        depth_packet.getFrame()
                    )

                    valid = depth_frame[
                        depth_frame > 0
                    ]

                    print(
                        "[DEPTH] Shape:",
                        depth_frame.shape,
                    )

                    print(
                        "[DEPTH] Valid pixels:",
                        valid.size,
                    )

                    if valid.size:
                        print(
                            "[DEPTH] Range mm:",
                            int(valid.min()),
                            "to",
                            int(valid.max()),
                        )

                    depth_checked = True

            nn_packet = nn_queue.tryGet()

            if nn_packet is not None:
                nn_count += 1

                if not nn_layers_printed:
                    print(
                        "[YOLO] Output layers:"
                    )

                    for layer_name in (
                        nn_packet
                        .getAllLayerNames()
                    ):
                        values = (
                            nn_packet
                            .getLayerFp16(
                                layer_name
                            )
                        )

                        print(
                            f"  {layer_name}: "
                            f"{len(values)} values"
                        )

                    nn_layers_printed = True

            time.sleep(0.001)

        elapsed = (
            time.monotonic()
            - start
        )

        rgb_rate = rgb_count / elapsed
        depth_rate = depth_count / elapsed
        nn_rate = nn_count / elapsed

        print()
        print("=" * 68)
        print("GOAL 2 PIPELINE BENCHMARK")
        print("=" * 68)
        print(
            f"Elapsed:    {elapsed:.2f} s"
        )
        print(
            f"RGB JPEG:   {rgb_count} frames, "
            f"{rgb_rate:.2f} Hz"
        )
        print(
            f"Depth:      {depth_count} frames, "
            f"{depth_rate:.2f} Hz"
        )
        print(
            f"YOLO raw:   {nn_count} outputs, "
            f"{nn_rate:.2f} Hz"
        )
        print(
            f"Snapshot:   {SNAPSHOT_PATH}"
        )
        print("=" * 68)

        if not snapshot_saved:
            raise RuntimeError(
                "No RGB JPEG was received"
            )

        if not depth_checked:
            raise RuntimeError(
                "No depth frame was received"
            )

        if not nn_layers_printed:
            raise RuntimeError(
                "No YOLO output was received"
            )

        print(
            "COMBINED PIPELINE BENCHMARK PASSED"
        )


if __name__ == "__main__":
    main()
