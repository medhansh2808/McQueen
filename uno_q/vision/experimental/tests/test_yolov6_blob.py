#!/usr/bin/env python3

import time
from pathlib import Path

import depthai as dai


MODEL_PATH = Path(
    "/home/arduino/McQueen/models/"
    "yolov6nr1_coco_512x288_openvino_2022.1_6shave.blob"
)

TIMEOUT_SECONDS = 30.0
REQUIRED_PACKETS = 3


if not MODEL_PATH.is_file():
    raise FileNotFoundError(
        f"Model not found: {MODEL_PATH}"
    )

pipeline = dai.Pipeline()

openvino_version = getattr(
    dai.OpenVINO.Version,
    "VERSION_2022_1",
    None,
)

if openvino_version is not None:
    pipeline.setOpenVINOVersion(
        openvino_version
    )

    print(
        "Pipeline OpenVINO version: 2022.1"
    )
else:
    print(
        "WARNING: Explicit OpenVINO 2022.1 "
        "enum was not found"
    )

camera = pipeline.create(
    dai.node.ColorCamera
)

camera.setBoardSocket(
    dai.CameraBoardSocket.CAM_A
)

camera.setResolution(
    dai.ColorCameraProperties
    .SensorResolution
    .THE_1080_P
)

camera.setPreviewSize(
    512,
    288,
)

camera.setPreviewKeepAspectRatio(
    False
)

camera.setInterleaved(False)

camera.setColorOrder(
    dai.ColorCameraProperties
    .ColorOrder
    .BGR
)

camera.setFps(15)

network = pipeline.create(
    dai.node.NeuralNetwork
)

network.setBlobPath(
    str(MODEL_PATH)
)

network.setNumInferenceThreads(2)
network.input.setBlocking(False)
network.input.setQueueSize(1)

camera.preview.link(
    network.input
)

nn_output = pipeline.create(
    dai.node.XLinkOut
)

nn_output.setStreamName("nn")

network.out.link(
    nn_output.input
)

print("Model:", MODEL_PATH)
print("Model size:", MODEL_PATH.stat().st_size)
print("Opening OAK-D in forced USB2 mode...")

with dai.Device(
    pipeline,
    dai.UsbSpeed.HIGH,
) as device:

    print("OAK-D opened")
    print("USB speed:", device.getUsbSpeed())

    queue = device.getOutputQueue(
        name="nn",
        maxSize=4,
        blocking=False,
    )

    deadline = (
        time.monotonic()
        + TIMEOUT_SECONDS
    )

    packet_count = 0

    while (
        packet_count < REQUIRED_PACKETS
        and time.monotonic() < deadline
    ):
        packet = queue.tryGet()

        if packet is None:
            time.sleep(0.01)
            continue

        packet_count += 1

        print()
        print(
            f"NN packet {packet_count}/"
            f"{REQUIRED_PACKETS}"
        )

        layer_names = (
            packet.getAllLayerNames()
        )

        print("Layers:", layer_names)

        for layer_name in layer_names:
            values = packet.getLayerFp16(
                layer_name
            )

            print(
                f"{layer_name}: "
                f"{len(values)} FP16 values"
            )

    if packet_count < REQUIRED_PACKETS:
        raise TimeoutError(
            "No reliable NN output within "
            f"{TIMEOUT_SECONDS} seconds"
        )

print()
print("YOLOV6 BLOB TEST PASSED")
