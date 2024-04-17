from pypylon import pylon
from timeit import default_timer
import contextlib
import logging

from typing import Union

from utils_env_vars import set_env_variable


def create_camera_with_ip_address(ip_address: str):  # -> SwigPyObject
    # create a factory
    factory = pylon.TlFactory.GetInstance()
    # Create the transport layer
    ptl = factory.CreateTl("BaslerGigE")
    # Create an empty GigE device info object
    empty_camera_info = ptl.CreateDeviceInfo()
    # Set the IP address of the (empty) device object
    empty_camera_info.SetIpAddress(ip_address)
    # TODO: set other parameter?
    # Create the camera device object
    camera_device = factory.CreateDevice(empty_camera_info)
    return camera_device


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
        ip_address: str = None,
        serial_number: int = None
) -> pylon.InstantCamera:
    if ip_address:
        # Connect to the camera using IP address
        logging.info(f"Connect to the camera using IP address: {ip_address}")
        device = create_camera_with_ip_address(ip_address.strip("'").strip('"'))
    elif serial_number:
        # Connect to the camera using serial number
        logging.info(f"Connect to the camera using serial number: {serial_number}")
        cam_info = get_camera_by_serial_number(serial_number)
        device = pylon.TlFactory.GetInstance().CreateDevice(cam_info)
        # device = pylon.InstantCamera()
    else:
        logging.info("Emulating a camera.")
        set_env_variable("PYLON_CAMEMU", 1)
        device = pylon.TlFactory.GetInstance().CreateFirstDevice()
    # access / build the camera
    return pylon.InstantCamera(device)


def set_camera_parameter(
        cam: pylon.InstantCamera,
        transmission_type: str = None,
        destination_ip: str = None,
        destination_port: int = None,
        acquisition_mode: str = "SingleFrame"  # "Continuous"
) -> bool:
    # Set parameters if provided

    # Transmission Type
    _transmission_type = cam.StreamGrabber.TransmissionType.GetValue()
    if transmission_type and (transmission_type != _transmission_type):
        logging.debug(f"Setting Transmission Type to {transmission_type}")
        cam.StreamGrabber.TransmissionType.SetValue(transmission_type)

    # parameter are only writable if transmission type is not unicast
    if transmission_type.lower() != "unicast":
        # Destination IP address
        _destination_ip = cam.StreamGrabber.DestinationAddr.GetValue()
        if destination_ip and (destination_ip != _destination_ip):
            print(f"Setting Destination Address to {destination_ip}")
            cam.StreamGrabber.DestinationAddr.SetValue(destination_ip)

        # Destination Port
        _destination_ip = cam.StreamGrabber.DestinationPort.GetValue()
        if destination_port and (destination_port != _destination_ip):
            print(f"Setting Destination Port to {destination_port}")
            cam.StreamGrabber.DestinationPort.SetValue(destination_port)

    # AcquisitionMode Mode
    _acquisition_mode = cam.AcquisitionMode.GetValue()
    if acquisition_mode and (transmission_type != _acquisition_mode):
        logging.debug(f"Setting Acquisition Mode to {acquisition_mode}")
        cam.AcquisitionMode.SetValue(acquisition_mode)

    # Bandwidth Optimization through compression. NOT AVAILABLE FOR ALL MODELS
    ## Enable lossless compression
    # self.camera.ImageCompressionMode.Value = "BaslerCompressionBeyond"
    # self.camera.ImageCompressionRateOption.Value = "Lossless"
    ## Set minimal (expected) compression rate so that the camera can increase the frame rate accordingly
    # self.camera.BslImageCompressionRatio.Value = 30

    return True


@contextlib.contextmanager
def open_camera(pypycam: pylon.InstantCamera) -> pylon.InstantCamera:
    try:
        pypycam.Open()
        yield pypycam
    except Exception as ex:
        raise ex
    finally:
        pypycam.Close()


class BaslerCamera:
    def __init__(
            self,
            ip_address: str = None,
            serial_number: int = None,
            timeout: int = 1000,
            transmission_type: str = "Unicast",
            destination_ip: str = None,
            destination_port: int = None
    ) -> None:
        self.ip_address = ip_address
        self.serial_number = serial_number
        self.timeout = timeout if timeout else 5000
        self.transmission_type = transmission_type
        self.destination_ip = destination_ip
        self.destination_port = destination_port
        self.camera = None

    def __repr__(self):
        keys = [
            "ip_address",
            "serial_number",
            "timeout",
            "transmission_type",
            "destination_ip",
            "destination_port"
        ]
        params = {ky: getattr(self, ky) for ky in keys if getattr(self, ky)}

        return f"BaslerCamera({', '.join([f'{ky}={vl}' for ky, vl in params.items()])})"

    def connect(self) -> bool:
        # create camera
        self.camera = create_camera(self.ip_address, self.serial_number)
        logging.info(f"{self}: {self.get_camera_info()}")
        return True

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

    def set_parameter(self) -> bool:

        with open_camera(self.camera) as cam:
            return set_camera_parameter(
                cam,
                transmission_type=self.transmission_type,
                destination_ip=self.destination_ip,
                destination_port=self.destination_port
            )

    def take_photo(self, exposure_time_microseconds: int = None):
        # create camara object if necessary
        if self.camera is None:
            self.connect()

        t = []
        t.append(("start", default_timer()))  # TIMING
        if self.camera is None:
            raise RuntimeError("Camera is not connected. Call connect() method first.")
        if not self.camera.IsOpen():
            self.camera.Open()
        t.append(("open camera", default_timer()))  # TIMING

        _exposure_time = self.camera.ExposureTimeAbs.GetValue()
        if exposure_time_microseconds and (exposure_time_microseconds != _exposure_time):
            self.camera.ExposureTimeAbs.SetValue(exposure_time_microseconds)
        t.append(("set exposure time", default_timer()))  # TIMING
        
        # Wait for a grab result
        print(f"take_photo(): self.timeout={self.timeout}") 
        t.append(("print info", default_timer()))  # TIMING
        grab_result = self.camera.GrabOne(self.timeout)
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
        print(f"take_photo() execution timing: {diff} ms")
        return img


# Example usage:
if __name__ == "__main__":
    # Create camera instance with IP address
    camera = BaslerCamera(
        ip_address="192.168.10.5",
        timeout=500,
        transmission_type="Multicast",
        destination_ip="192.168.10.221"
    )

    # Connect to the camera
    camera.connect()

    # Take a photo
    n = 4
    for i in range(n):
    	photo = camera.take_photo(100)

