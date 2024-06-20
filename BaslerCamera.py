from pypylon import pylon
from timeit import default_timer
from pathlib import Path

import logging

from typing import Union

from utils_env_vars import set_env_variable


def create_camera_with_ip_address(ip_address: str, subnet_mask: str = None):  # -> SwigPyObject
    # create a Transport Layer instance
    factory = pylon.TlFactory.GetInstance()

    # Create the transport layer
    ptl = factory.CreateTl("BaslerGigE")
    # Create an empty GigE device info object
    device_info = ptl.CreateDeviceInfo()
    # Set the IP address of the (empty) device object
    device_info.SetIpAddress(ip_address)
    # Set subnet mask
    if (subnet_mask is not None) and (subnet_mask != ""):
        device_info.SetSubnetMask(subnet_mask)

    # Create the camera device object
    device = factory.CreateDevice(device_info)
    return device


def get_camera_by_serial_number(serial_number: int = 24339728):  # -> SwigPyObject
    # Pypylon get camera by serial number
    info = None
    for dev in pylon.TlFactory.GetInstance().EnumerateDevices():
        if dev.GetSerialNumber() == str(serial_number):
            info = dev
            break

    if info is None:
        msg = f"No connection to camera could be established. No camera with serial number {serial_number} found."
        n_digits = len(str(serial_number))
        if n_digits != 8:
            msg += f" Serial numbers for Basler cameras usually have 8 digits. The input had {n_digits} digits."
        raise ValueError(msg)
    return info


def create_camera(
        serial_number: int = None,
        ip_address: str = None,
        subnet_mask: str = None
) -> pylon.InstantCamera:

    if ip_address:
        # Connect to the camera using IP address
        logging.info(f"Connect to the camera using IP address: {ip_address}")
        device = create_camera_with_ip_address(ip_address, subnet_mask)
    elif serial_number:
        # Connect to the camera using serial number
        logging.info(f"Connect to the camera using serial number: {serial_number}")
        cam_info = get_camera_by_serial_number(serial_number)
        device = pylon.TlFactory.GetInstance().CreateDevice(cam_info)
        # device = pylon.InstantCamera()
    else:
        logging.info("Emulating a camera.")
        set_env_variable("PYLON_CAMEMU", 1)  # set how many cameras should be emulated
        device = pylon.TlFactory.GetInstance().CreateFirstDevice()
    # access / build the camera
    return pylon.InstantCamera(device)


def get_device_info(device: Union[pylon.InstantCamera, pylon.DeviceInfo]) -> dict:
    if isinstance(device, pylon.InstantCamera):
        device_info = device.GetDeviceInfo()
    elif isinstance(device, pylon.DeviceInfo):
        device_info = device
    else:
        raise TypeError(f"Unexpected input type {type(device)}. An 'InstantCamera' or 'DeviceInfo' object was expected.")

    _, keys = device_info.GetPropertyNames()

    info = dict()
    for ky in keys:
        _, info[ky] = device_info.GetPropertyValue(ky)
    return info


def get_parameter(cam: pylon.InstantCamera) -> dict:
    if not cam.IsOpen():
        raise Exception("Open camera first.")

    info = {
        "Transmission Type": cam.StreamGrabber.TransmissionType.GetValue(),
        "Destination Address": cam.StreamGrabber.DestinationAddr.GetValue(),
        "Destination Port": cam.StreamGrabber.DestinationPort.GetValue(),
        "Driver Type": cam.StreamGrabber.Type.GetValue(),
        "Acquisition Mode": cam.AcquisitionMode.GetValue(),
        }
    return info


def set_camera_parameter(
        cam: pylon.InstantCamera,
        transmission_type: str = None,
        destination_ip_address: str = None,
        destination_port: int = None,
        acquisition_mode: str = "SingleFrame"  # "Continuous"
) -> bool:
    """Set parameters if provided"""
    if not cam.IsOpen():
        raise Exception("Open camera first.")

    # Transmission Type
    _transmission_type = cam.StreamGrabber.TransmissionType.GetValue()
    if transmission_type and (transmission_type != _transmission_type):
        logging.debug(f"Setting Transmission Type to {transmission_type} (was {_transmission_type}).")
        cam.StreamGrabber.TransmissionType.SetValue(transmission_type)

    # parameter are only writable if transmission type is Multicast
    if transmission_type.lower() == "multicast":
        # Destination IP address
        _destination_ip = cam.StreamGrabber.DestinationAddr.GetValue()
        if destination_ip and (destination_ip != _destination_ip):
            logging.debug(f"Setting Destination Address to {destination_ip} (was {_destination_ip}).")
            cam.StreamGrabber.DestinationAddr.SetValue(destination_ip)

    # Destination Port
    _destination_port = cam.StreamGrabber.DestinationPort.GetValue()
    if destination_port and (destination_port != _destination_port):
        logging.debug(f"Setting Destination Port to {destination_port} (was {_destination_port}).")
        cam.StreamGrabber.DestinationPort.SetValue(destination_port)

    # AcquisitionMode Mode
    _acquisition_mode = cam.AcquisitionMode.GetValue()
    if acquisition_mode and (transmission_type != _acquisition_mode):
        logging.debug(f"Setting Acquisition Mode to {acquisition_mode} (was {_acquisition_mode}).")
        cam.AcquisitionMode.SetValue(acquisition_mode)

    # Bandwidth Optimization through compression. NOT AVAILABLE FOR ALL MODELS
    ## Enable lossless compression
    # self.camera.ImageCompressionMode.Value = "BaslerCompressionBeyond"
    # self.camera.ImageCompressionRateOption.Value = "Lossless"
    ## Set minimal (expected) compression rate so that the camera can increase the frame rate accordingly
    # self.camera.BslImageCompressionRatio.Value = 30

    return True


def take_picture(cam: pylon.InstantCamera, exposure_time_microseconds: int = None, timeout_milliseconds: int = 400):

    t = [("start", default_timer())]

    # set time how long the camera sensor is exposed to light
    _exposure_time = cam.ExposureTimeAbs.GetValue()
    if (exposure_time_microseconds and
            (exposure_time_microseconds >= 100) and
            (exposure_time_microseconds != _exposure_time)):
        # set exposure time
        cam.ExposureTimeAbs.SetValue(exposure_time_microseconds)
    t.append(("set exposure time", default_timer()))  # TIMING

    # convert exposure time from micro-seconds to milliseconds
    t_expose_ms = (exposure_time_microseconds / 1000) if exposure_time_microseconds is not None else 1
    # timeout should not be shorter than the exposure time or 11 ms
    timeout = max((timeout_milliseconds, t_expose_ms + 1, 11))

    # Wait for a grab result
    t.append(("print info", default_timer()))  # TIMING
    grab_result = cam.GrabOne(timeout)  # timeout in milliseconds
    t.append(("grab image", default_timer()))  # TIMING

    if grab_result.GrabSucceeded():
        # Convert the grabbed image to PIL Image object
        img = grab_result.GetArray()
        t.append(("get array", default_timer()))  # TIMING
        grab_result.Release()
        t.append(("release", default_timer()))  # TIMING
    else:
        raise RuntimeError("Failed to grab an image")

    diff = {t[i][0]: (t[i][1] - t[i - 1][1]) * 1000 for i in range(1, len(t))}
    logging.debug(f"take_photo() execution timing: {diff} ms")
    return img


class BaslerCamera:
    def __init__(
            self,
            serial_number: int = None,
            ip_address: str = None,
            subnet_mask: str = None,
            timeout: int = 1000,  # milli seconds
            transmission_type: str = "Unicast",
            destination_ip_address: str = None,
            destination_port: int = None
    ) -> None:
        self.serial_number = serial_number
        self.ip_address = ip_address
        self.subnet_mask = subnet_mask
        self.timeout = timeout if timeout else 1000
        self.transmission_type = transmission_type
        self.destination_ip_address = destination_ip_address
        self.destination_port = destination_port
        self.camera = None
        logging.debug(f"Init {self}")

    def __repr__(self):
        keys = [
            "ip_address",
            "serial_number",
            "timeout",
            "transmission_type",
            "destination_ip_address",
            "destination_port"
        ]
        params = {ky: getattr(self, ky) for ky in keys if getattr(self, ky)}
        text_input_params = ", ".join([f"{ky}={vl}" for ky, vl in params.items()])
        return f"BaslerCamera({text_input_params})"

    def connect(self) -> bool:
        # create camera
        self.camera = create_camera(
            serial_number=self.serial_number,
            ip_address=self.ip_address,
            subnet_mask=self.subnet_mask
        )
        logging.debug(f"Camera info: {self.get_camera_info()}")

        self.camera.Open()
        self.set_parameter()
        logging.info(f"{self}: {self.get_camera_info()}")
        return True

    def disconnect(self) -> bool:
        if self.camera is not None:
            self.camera.Close()
            logging.debug("Camera disconnected.")
        return True

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def get_camera_info(self) -> dict:
        if self.camera:
            cam_info = self.camera.GetDeviceInfo()
            info = {
                "Name": cam_info.GetModelName(),
                "IP": cam_info.GetIpAddress(),
                "MAC": cam_info.GetMacAddress()
            }
        else:
            info = {"Error": "No camera created yet."}
        return info

    def get_device_info(self) -> dict:
        if self.camera:
            device_info = get_device_info(self.camera)
        else:
            device_info = {"Error": "No camera created yet."}
        return device_info

    def set_parameter(self) -> bool:
        if self.ip_address or self.serial_number:
            logging.debug(
                f"Setting Parameter: transmission_type={self.transmission_type}, "
                f"destination_ip_address={self.destination_ip_address}, "
                f"destination_port={self.destination_port}"
            )
            return set_camera_parameter(
                self.camera,
                transmission_type=self.transmission_type,
                destination_ip_address=self.destination_ip_address,
                destination_port=self.destination_port
            )
        else:
            logging.debug("Camera is emulated. No parameters set.")
            return False

    def set_test_picture(self, path_to_image: Union[Path, str] = None) -> bool:
        if path_to_image and (Path(path_to_image).exists()):
            self.camera.ImageFilename.SetValue(Path(path_to_image).as_posix())
            logging.debug(f"Test image of emulated camera was set to {self.camera.ImageFilename.GetValue()}.")
            # enable image file test pattern
            self.camera.ImageFileMode = "On"
            # disable test pattern [image file is "real-image"]
            self.camera.TestImageSelector = "Off"
            return True
        else:
            return False

    def take_photo(self, exposure_time_microseconds: int = None):
        # create camara object if necessary
        if self.camera is None:
            self.connect()
            # raise RuntimeError("Camera is not connected. Call connect() method first.")

        if not self.camera.IsOpen():
            self.camera.Open()

        return take_picture(self.camera, exposure_time_microseconds, timeout_milliseconds=self.timeout)


# Example usage:
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
#        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # Create camera instance with IP address
    camera = BaslerCamera(
        # ip_address="192.168.10.5",
        timeout=1000,
        # transmission_type="Multicast",
        # destination_ip="192.168.10.221"
    )

    # Connect to the camera
    camera.connect()

    for _ in range(10):
        photo = camera.take_photo(100)
    camera.disconnect()
