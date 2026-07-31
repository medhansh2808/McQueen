#!/usr/bin/env python3

import depthai as dai


FRAME_COUNT = 30
FPS = 10


pipeline = dai.Pipeline()

# Colour camera
rgb = pipeline.create(dai.node.ColorCamera)
rgb.setBoardSocket(dai.CameraBoardSocket.CAM_A)
rgb.setPreviewSize(640, 360)
rgb.setInterleaved(False)
rgb.setFps(FPS)

# Left mono camera
left = pipeline.create(dai.node.MonoCamera)
left.setBoardSocket(dai.CameraBoardSocket.CAM_B)
left.setResolution(
    dai.MonoCameraProperties.SensorResolution.THE_400_P
)
left.setFps(FPS)

# Right mono camera
right = pipeline.create(dai.node.MonoCamera)
right.setBoardSocket(dai.CameraBoardSocket.CAM_C)
right.setResolution(
    dai.MonoCameraProperties.SensorResolution.THE_400_P
)
right.setFps(FPS)

# Stereo depth
stereo = pipeline.create(dai.node.StereoDepth)
stereo.setDefaultProfilePreset(
    dai.node.StereoDepth.PresetMode.HIGH_DENSITY
)
stereo.setLeftRightCheck(True)
stereo.setSubpixel(False)
stereo.setExtendedDisparity(False)

left.out.link(stereo.left)
right.out.link(stereo.right)

# USB outputs
rgb_out = pipeline.create(dai.node.XLinkOut)
rgb_out.setStreamName("rgb")
rgb.preview.link(rgb_out.input)

depth_out = pipeline.create(dai.node.XLinkOut)
depth_out.setStreamName("depth")
stereo.depth.link(depth_out.input)


print("Opening OAK-D with RGB + stereo depth...")

with dai.Device(
    pipeline,
    dai.UsbSpeed.HIGH,
) as device:

    print("OAK-D opened")
    print("USB speed:", device.getUsbSpeed())

    rgb_queue = device.getOutputQueue(
        name="rgb",
        maxSize=1,
        blocking=True,
    )

    depth_queue = device.getOutputQueue(
        name="depth",
        maxSize=1,
        blocking=True,
    )

    latest_rgb = None
    latest_depth = None

    for frame_number in range(1, FRAME_COUNT + 1):
        latest_rgb = rgb_queue.get().getFrame()
        latest_depth = depth_queue.get().getFrame()

        if frame_number in (1, 10, 20, 30):
            print(
                f"Frame {frame_number}/{FRAME_COUNT}: "
                f"RGB={latest_rgb.shape}, "
                f"Depth={latest_depth.shape}"
            )

    valid_depth = latest_depth[latest_depth > 0]

    print()
    print("RGB dimensions:", latest_rgb.shape)
    print("Depth dimensions:", latest_depth.shape)
    print("Valid depth pixels:", valid_depth.size)

    if valid_depth.size > 0:
        print(
            "Depth range:",
            int(valid_depth.min()),
            "to",
            int(valid_depth.max()),
            "millimetres",
        )
    else:
        raise RuntimeError(
            "Depth frame was received but contained no valid distances"
        )

print()
print("RGB + DEPTH TEST PASSED")
