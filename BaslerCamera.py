import numpy as np
from pypylon import pylon
from timeit import default_timer
from pathlib import Path
from PIL import Image

import re

from typing import Union, Literal, Any, List, Dict, Tuple

from DataModels import (
    PixelType,
    OutputImageFormat,
    AcquisitionMode,
    TransmissionType,
    TriggerMode,
    TriggerActivation
)
from utils import set_env_variable, setup_logging


# Setup logging
logger = setup_logging(__name__)


re_pixel_type = re.compile(r"(pylon\.)?(PixelType_)?[a-zA-Z]\w+", re.ASCII | re.IGNORECASE)
re_pixel_type_prefix = re.compile(r"PixelType_", re.ASCII | re.IGNORECASE)


def cast_basler_pixe_type(pixel_type: str) -> int:
    """
    Casts strings representing a Basler pixel type into their corresponding integer code.

    :param pixel_type: string like PixelType_Mono8 or Mono8 or just mono8
    :return:
    """
    # strip leading / tailing characters input
    pixel_type = pixel_type.strip().strip("'").strip('"')

    # default value
    pixel_type_code = pylon.PixelType_Undefined

    m = re_pixel_type.search(pixel_type)
    if m:
        string = m.group()
        # strip prefix
        m = re_pixel_type_prefix.search(string)
        # build attribute name
        if m:
            attribute = m.group()
        else:
            attribute = f"PixelType_{string[0].upper()}{string[1:]}"

        if hasattr(pylon, attribute):
            pixel_type_code = getattr(pylon, attribute)  # FIXME: this is a security risk!
    return pixel_type_code


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
    t0 = default_timer()
    if ip_address:
        # Connect to the camera using IP address
        logger.info(f"Connecting to the camera using IP address {ip_address} and subnet mask {subnet_mask}")
        device = create_camera_with_ip_address(ip_address, subnet_mask)
    elif serial_number:
        # Connect to the camera using serial number
        logger.info(f"Connect to the camera using serial number: {serial_number}")
        cam_info = get_camera_by_serial_number(serial_number)
        device = pylon.TlFactory.GetInstance().CreateDevice(cam_info)
    else:
        logger.info("Emulating a camera.")
        set_env_variable("PYLON_CAMEMU", 1)  # set how many cameras should be emulated
        device = pylon.TlFactory.GetInstance().CreateFirstDevice()

    t1 = default_timer()
    logger.debug(f"Getting camera device object took {(t1 - t0) * 1000:.4g} ms")

    # access / build the camera
    cam = pylon.InstantCamera(device)
    t2 = default_timer()
    logger.debug(f"Creating a Pylon InstantCamera instance took {(t2 - t1) * 1000:.4g} ms")
    return cam


def get_device_info(device: Union[pylon.InstantCamera, pylon.DeviceInfo]) -> dict:
    if isinstance(device, pylon.InstantCamera):
        device_info = device.GetDeviceInfo()
    elif isinstance(device, pylon.DeviceInfo):
        device_info = device
    else:
        raise TypeError(
            f"Unexpected input type {type(device)}. An 'InstantCamera' or 'DeviceInfo' object was expected.")

    _, keys = device_info.GetPropertyNames()

    info = dict()
    for ky in keys:
        _, info[ky] = device_info.GetPropertyValue(ky)
    return info


def get_value_from_camera(cam: pylon.InstantCamera, name: str) -> Any:
    try:
        return getattr(cam, name).GetValue()
    except AttributeError as ex:
        Exception(f"{cam} does not has an attribute {name}. {ex}")
    except pylon.AccessException as ex:
        raise Exception(f"Attribute {name} could not be accessed. Is the camera connected? {ex}")


def get_parameter(cam: pylon.InstantCamera) -> dict:
    """Reads parameters from the camera and returns them as a dictionary"""
    if not cam.IsOpen():
        raise Exception("Open camera first.")

    info = {
        "Transmission Type": cam.StreamGrabber.TransmissionType.GetValue(),
        "Destination Address": cam.StreamGrabber.DestinationAddr.GetValue(),
        "Destination Port": cam.StreamGrabber.DestinationPort.GetValue(),
        "Driver Type": cam.StreamGrabber.Type.GetValue(),
        "Acquisition Mode": cam.AcquisitionMode.GetValue(),
        "Pixel Format": cam.PixelFormat.GetValue()
    }
    return info


def get_image(grab_result, converter: pylon.ImageFormatConverter = None) -> Union[np.ndarray, None]:
    """Pylon grab result object to numpy.ndarray object like an image in OpenCV."""
    img = None
    if grab_result.GrabSucceeded():
        # Convert the grabbed image to numpy.ndarray object
        if converter is None:
            img = grab_result.GetArray()
        else:
            img = converter.Convert(grab_result).GetArray()
    else:
        raise logger.error("Failed to grab an image.")
    # release object
    grab_result.Release()

    logger.debug(f"Get image: {img.shape if isinstance(img, np.ndarray) else img}")
    return img


def build_image_format_converter(
        convert_to_format: Literal["RGB", "BGR", "Mono", "null"] = "null"
) -> Union[pylon.ImageFormatConverter, None]:
    # build image converter
    logger.debug(f"Setting image format converter to {convert_to_format}.")
    converter = None
    if (convert_to_format is not None) and (convert_to_format.lower() != "null"):
        try:
            converter = pylon.ImageFormatConverter()
            if convert_to_format == "Mono":
                converter.OutputPixelFormat = pylon.PixelType_Mono8
            elif convert_to_format == "RGB":
                converter.OutputPixelFormat = pylon.PixelType_RGB8packed
            elif convert_to_format == "BGR":
                converter.OutputPixelFormat = pylon.PixelType_BGR8packed
            else:
                raise ValueError(f"Unrecognized convert_to: {convert_to_format}")

            converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
            # Sets the alignment of the bits in the target pixel type if the target bit depth is greater than
            # the source bit depth, e.g., if you are converting from a 10-bit to a 16-bit format.

        except Exception as ex:
            logger.error(f"Setting up an Image Format Converter failed with {ex}. Proceeding without a converter.")
    return converter


class BaslerCamera:
    __attr_exposure_time = None
    __attr_trigger_delay = None

    def __init__(
            self,# *BaslerCameraParams
            serial_number: int = None,
            ip_address: str = None,
            subnet_mask: str = None,
            timeout_ms: int = 5000,  # milli seconds
            transmission_type: str = "Unicast",
            destination_ip_address: str = None,
            destination_port: int = None,
            acquisition_mode: AcquisitionMode = "SingleFrame",
            pixel_format: PixelType = "Undefined",
            convert_to_format: OutputImageFormat = "null",
            exposure_time_microseconds: int = None,
    ) -> None:
        self.serial_number = serial_number
        self.ip_address = ip_address
        self.subnet_mask = subnet_mask
        self.timeout_ms = timeout_ms if timeout_ms else 1000
        self.convert_to_format = convert_to_format
        # build converter
        self.converter = build_image_format_converter(convert_to_format)
        # initialize camera attribute
        self._camera = None
        # properties
        self._transmission_type = transmission_type
        self._destination_ip_address = destination_ip_address
        self._destination_port = destination_port
        self._acquisition_mode = acquisition_mode
        self._pixel_format = pixel_format

        self._exposure_time_microseconds = exposure_time_microseconds

        logger.debug(f"Init {self}")

    def __dict__(self) -> Dict[str, Any]:
        # key map from (local) attributes to better-readable names (that exist as properties)
        key_map_gige = {
            "_transmission_type": "transmission_type",
            "_destination_ip_address": "destination_ip_address",
            "_destination_port": "destination_port",
        }
        key_map = {
            "serial_number": "serial_number",
            "ip_address": "ip_address",
            "subnet_mask": "subnet_mask",
            "timeout_ms": "timeout_ms",
            "_acquisition_mode": "acquisition_mode",
            "_pixel_format": "pixel_format",

        } | key_map_gige if self.is_gige else {}
        return {vl: getattr(self, ky) for ky, vl in key_map.items()}

    def __repr__(self):
        txt = ", ".join([f"{ky}={vl}" for ky, vl in self.__dict__().items() if vl])
        return f"BaslerCamera({txt})"

    def __bool__(self) -> bool:
        return self._camera is not None

    # def __eq__(self, other):
    #     for ky, vl in dict(self).items():
    #
    #     other.dict().items()

    def open(self) -> bool:
        if self:
            if not self.is_open:
                self._camera.Open()
                logger.debug("Camera opened.")
        else:
            raise Exception("No camera created yet")

        return self.is_open

    @property
    def is_open(self) -> bool:
        return self._camera.IsOpen() if self else False

    def close(self) -> bool:
        if self._camera is not None:
            self.stop_grabbing()
            # close camera
            self._camera.Close()
            logger.debug("Camera closed.")
        return not self.is_open

    def __check_camera_type(self, char: str) -> bool | None:
        # examples = [
        #     "r2L2048-58gm",
        #     "boA4504-100cm",
        #     "acA2440-75umMED",
        #     "a2A5328-4gcPRO",
        #     "a2A5328-35cm",
        #     "a2A2840-48umUV",
        #     "a2A2840-67g5mBAS",
        #     "a2A2448-120cc"
        # ]
        name = self.name
        if isinstance(name, str):
            re_com_type = re.compile("-\d+[a-z]", re.ASCII)

            m = re_com_type.search(name)
            if m:
                return m.group()[-1] == char
        else:
            return None

    @property
    def is_gige(self) -> bool | None:
        return self.__check_camera_type("g")

    @property
    def is_usb(self) -> bool | None:
        return self.__check_camera_type("c")

    def create_camera(self):  # -> BaslerCamera
        t0 = default_timer()
        self._camera = create_camera(
            serial_number=self.serial_number,
            ip_address=self.ip_address,
            subnet_mask=self.subnet_mask
        )
        t1 = default_timer()
        logger.debug(f"Creating BaslerInstantCamera object took {(t1 - t0) * 1000:.4g} ms")
        return self

    def connect(self) -> bool:
        # create camera object if not exists
        if not self:
            logger.debug("Camera was not created yet. Calling create_camera() method first.")
            self.create_camera()
        # open connection to camera
        self.open()

        # set pixel format
        self.pixel_format = self._pixel_format

        if not self.is_emulated:
            # camera is not emulated
            # set parameters
            if self.is_gige:
                # GigE-specific configs. Attributes do not exist for USB cameras
                self.transmission_type = self._transmission_type
                self.destination_ip_address = self._destination_ip_address
                self.destination_port = self._destination_port
            # set default acquisition mode
            self.acquisition_mode = self._acquisition_mode
            # set default exposure time
            self.exposure_time = self._exposure_time_microseconds

        return self.is_open

    def disconnect(self) -> bool:
        self.close()
        logger.debug("Camera disconnected.")
        return not self.is_open

    def reconnect(self) -> bool:
        self.disconnect()
        return self.connect()

    def start_grabbing(self, grab_strategy: int = pylon.GrabStrategy_LatestImageOnly):
        """wraps the StartGrabbing method of a pylon.InstantCamera object"""
        if not self.is_grabbing:
            self._camera.StartGrabbing(grab_strategy)

    def stop_grabbing(self):
        """wraps the StopGrabbing method of a pylon.InstantCamera object"""
        if self.is_grabbing:
            self._camera.StopGrabbing()

    @property
    def is_grabbing(self) -> bool:
        return self._camera.IsGrabbing()

    def retrieve_result(self, timeout_handling: int = pylon.TimeoutHandling_ThrowException):
        # TODO add retry strategy
        return self._camera.RetrieveResult(self.timeout_ms, timeout_handling)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()

    @property
    def is_emulated(self) -> bool:
        """Flag whether a camera is emulated"""
        return (self.serial_number is None) and (self.ip_address is None)

    def _get_attribute_key(self, attributes: List[str]) -> str:
        """wrapper function to access attributes of the pylon camera object because they differ depending on the camera"""
        attr_name = None
        for attr in attributes:
            try:
                camera_hasattr = hasattr(self._camera, attr)
            except pylon.GenericException:
                camera_hasattr = False

            if camera_hasattr:
                attr_name = attr
                break

        if attr_name:
            return attr_name
        else:
            raise AttributeError(f"Camera has not attribute {' or '.join(attributes)}.")

    # exposure time
    @property
    def exposure_time(self):
        """Gets the exposure time in micro-seconds"""

        if self.__attr_exposure_time is None:
            self.__attr_exposure_time = self._get_attribute_key(["ExposureTimeAbs", "ExposureTime"])

        return getattr(self._camera, self.__attr_exposure_time).GetValue()

    @exposure_time.setter
    def exposure_time(self, value: float | None):
        """Sets the exposure time in micro-seconds"""
        if value is not None:
            if not isinstance(value, (float, int)):
                raise TypeError(f"Invalid exposure time type: {value} (micro-seconds). Must be an Integer or Float.")
            elif value < 0:
                raise ValueError(f"Exposure time must be a positive value but was: {value} (micro-seconds).")

            if value != self.exposure_time:
                logger.debug(f"Setting Exposure Time to {value}.")
                getattr(self._camera, self.__attr_exposure_time).SetValue(float(value))

    # Transmission type
    @property
    def transmission_type(self) -> TransmissionType | None:
        """Gets the transmission type value"""
        if self.is_emulated:
            return None
        else:
            self.open()
            return self._camera.StreamGrabber.TransmissionType.GetValue()

    @transmission_type.setter
    def transmission_type(self, value: TransmissionType):
        """Sets the transmission type of the camera"""
        if not isinstance(value, str):
            raise TypeError(f"Invalid transmission type: {value}. Must be an string.")

        # self.open()
        if value != self.transmission_type:
            logger.debug(f"Setting Transmission Type to {value}.")
            self._camera.StreamGrabber.TransmissionType.SetValue(value)

    # Destination IP Address
    @property
    def destination_ip_address(self) -> str | None:
        """Gets the destination IP address"""
        if self.is_emulated:
            return None
        else:
            self.open()
            return self._camera.StreamGrabber.DestinationAddr.GetValue()

    @destination_ip_address.setter
    def destination_ip_address(self, value: str | None):
        """Sets the value of the destination IP address. (ONLY if transmission type is Multicast)"""
        if value:
            if not isinstance(value, str):
                raise TypeError(f"Invalid destination ip address: {value}. Must be an string.")

            # parameter are only writable if transmission type is Multicast
            if self.transmission_type == "Multicast":
                if value != self.destination_ip_address:
                    logger.debug(f"Setting Destination IP Address to {value}.")
                    self._camera.StreamGrabber.DestinationAddr.SetValue(value)
            else:
                raise Exception(f"Transmission type must be 'Multicast' to set a destination IP address"
                                f" but was {self.transmission_type}.")

    # Destination Port
    @property
    def destination_port(self) -> int | None:
        """Gets the value of the destination port"""
        if self.is_emulated:
            return None
        else:
            self.open()
            return self._camera.StreamGrabber.DestinationPort.GetValue()

    @destination_port.setter
    def destination_port(self, value: int | None):
        """Sets the destination port"""
        if value is not None:
            if not isinstance(value, int):
                raise TypeError(f"Invalid destination port: {value}. Must be an integer.")

            # self.open()
            if value != self.destination_port:
                logger.debug(f"Setting Destination Port to {value}.")
                self._camera.StreamGrabber.DestinationPort.SetValue(int(value))

    # AcquisitionMode Mode
    @property
    def acquisition_mode(self) -> AcquisitionMode:
        """Gets the current value of the acquisition mode"""
        self.open()
        return self._camera.AcquisitionMode.GetValue()

    @acquisition_mode.setter
    def acquisition_mode(self, value: AcquisitionMode):
        # self.open()
        if value != self.acquisition_mode:
            logger.debug(f"Setting Acquisition Mode to {value}.")
            self._camera.AcquisitionMode.SetValue(value)

    # Pixel Format / Pixel Type
    @property
    def pixel_format(self) -> PixelType:
        """Gets the current value of the pixel format"""
        self.open()
        return self._camera.PixelFormat.GetValue()

    @pixel_format.setter
    def pixel_format(self, value: PixelType):
        """Sets the pixel format"""
        if not isinstance(value, str):
            raise TypeError(f"Invalid pixel type: {value}. Must be a string.")

        if value != self.pixel_format:
            if value != "Undefined":
                logger.debug(f"Setting Pixel Format to {value}.")
                self._camera.PixelFormat.SetValue(value)
            else:
                logger.warning("Pixel Format cannot be set to to 'Undefined'. Please choose a valid pixel format.")

    def get_camera_info(self) -> dict:
        if self._camera:
            cam_info = self._camera.GetDeviceInfo()

            info = {"Name": cam_info.GetModelName()}
            if self.is_usb:
                pass
            else:
                info["IP"] = cam_info.GetIpAddress()
                info["MAC"] = cam_info.GetMacAddress()
        else:
            info = {"Error": "No camera created yet."}
        return info

    @property
    def name(self) -> str | None:
        """Wrapper to return the model name of the camera"""
        if self._camera:
            cam_info = self._camera.GetDeviceInfo()
            return cam_info.GetModelName()
        else:
            return None

    @property
    def info_string(self) -> str | None:
        """Wrapper to provide a nicely formated model name"""
        if self._camera:
            info = self.get_camera_info()
            if "Name" in info:
                return "#".join(list(info.values()))
            else:
                return None

    @property
    def device_info(self) -> dict:
        info = dict()
        if self._camera:
            device_info = self._camera.GetDeviceInfo()

            # create dictionary from properties
            _, keys = device_info.GetPropertyNames()

            for ky in keys:
                _, info[ky] = device_info.GetPropertyValue(ky)
        return info

    # Test picture
    @property
    def test_picture(self) -> str:
        """Gets the current value of the current test picture"""
        return self._camera.ImageFilename.GetValue()

    @test_picture.setter
    def test_picture(self, image: Union[Path, str] = None) -> None:
        re_test_picture = re.compile("^Testimage[1-6]$", re.ASCII)
        if isinstance(image, str) and re_test_picture.match(image):
            pass
        elif image and (Path(image).exists()):
            self._camera.ImageFilename.SetValue(Path(image).as_posix())
            logger.debug(f"Test image of emulated camera was set to {self.test_picture}.")

            # enable image file test pattern
            self._camera.ImageFileMode = "On"
            # disable test pattern [image file is "real-image"]
            self._camera.TestImageSelector = "Off"

            # adjust image width and height
            img = Image.open(image)
            self.size = img.size

    # width / height / size
    @property
    def width(self) -> int | None:
        """Wrapper to get the width of the image that the camera returns"""
        return self._camera.Width if self._camera else None

    @width.setter
    def width(self, value: int | None) -> None:
        """Wrapper to set the width of the image that the camera returns"""
        if self._camera and value and value > 0:
            logger.debug(f"Setting Width to {value} px.")
            self._camera.Width = value

    @property
    def height(self) -> int | None:
        """Wrapper to get the height of the image that the camera returns"""
        return self._camera.Height if self._camera else None

    @height.setter
    def height(self, value: int | None) -> None:
        """Wrapper to set the height of the image that the camera returns"""
        if self._camera and value and value > 0:
            logger.debug(f"Setting Height to {value} px.")
            self._camera.Height = value

    @property
    def size(self):
        """Wrapper to get the (width, height) of the image that the camera returns"""
        return self.width, self.height

    @size.setter
    def size(self, value: Tuple[int, int]) -> None:
        """Wrapper to set the (width, height) of the image that the camera returns"""
        if value and len(value) >= 2:
            logger.debug(f"Setting Size to {value} px.")
            self.width, self.height = value

    # --- trigger
    @property
    def trigger_source(self) -> str:
        """Wrapper to get the trigger source property"""
        return self._camera.TriggerSource.GetValue()

    @trigger_source.setter
    def trigger_source(self, value: TriggerMode) -> None:
        """Wrapper to set trigger source property"""
        if value != self.trigger_source:
            logger.debug(f"Setting Trigger Source to {value}.")
            self._camera.TriggerSource.SetValue(value)

    @property
    def trigger_mode_on(self) -> bool:
        """Wrapper to get the trigger mode property"""
        return self.__trigger_mode_converter(self._camera.TriggerSource.GetValue())

    @staticmethod
    def __trigger_mode_converter(value: bool | str) -> bool | str:
        if isinstance(value, bool):
            return "On" if value else "Off"
        elif isinstance(value, str):
            return True if value == "On" else False
        else:
            raise TypeError(f"Invalid trigger mode: {value}. Must be a boolean or string.")

    @trigger_mode_on.setter
    def trigger_mode_on(self, value: bool) -> None:
        """Wrapper to set trigger source property"""
        if value != self.trigger_mode_on:
            value_ = self.__trigger_mode_converter(value)
            logger.debug(f"Setting Trigger Mode to {value_}.")
            self._camera.TriggerMode.SetValue(value_)

    @property
    def trigger_activation(self) -> TriggerActivation:
        """Wrapper to get the trigger activation property"""
        return self._camera.TriggerActivation.GetValue()

    @trigger_activation.setter
    def trigger_activation(self, value: TriggerActivation) -> None:
        """Wrapper to set trigger activation property"""
        if value != self.trigger_activation:
            logger.debug(f"Setting Trigger Activation to {value}.")
            self._camera.TriggerActivation.SetValue(value)

    @property
    def trigger_delay(self) -> int:
        """Wrapper to get the trigger delay micro-seconds"""

        if self.__attr_trigger_delay is None:
            self.__attr_trigger_delay = self._get_attribute_key(["TriggerDelayAbs", "TriggerDelay"])

        return getattr(self._camera, self.__attr_trigger_delay).GetValue()

    @trigger_delay.setter
    def trigger_delay(self, value: Union[int, float]) -> None:
        """Wrapper to set trigger delay in micro-seconds"""
        if value:
            if not isinstance(value, (float, int)):
                raise TypeError(f"Invalid trigger delay time type: {value} (micro-seconds). Must be an Integer or Float.")

            if value != self.trigger_delay:
                logger.debug(f"Setting Trigger delay to {value} micro-seconds.")
                getattr(self._camera, self.__attr_trigger_delay).SetValue(float(value))


    # ---- photo
    def take_photo(
            self,
            exposure_time_microseconds: int = None,
            timeout_handling: int = pylon.TimeoutHandling_ThrowException
    ):
        logger.debug(f"BaslerCamera.take_photo({exposure_time_microseconds})")
        t0 = default_timer()

        self.connect()

        # set time how long the camera sensor is exposed to light
        self.exposure_time = exposure_time_microseconds

        # timeout in milliseconds
        if self.timeout_ms < (self.exposure_time / 1000):
            raise ValueError(f"Exposure time is larger than the camera timeout.")

        self.stop_grabbing()

        # Wait for a grab result
        logger.debug(f"BaslerCamera.take_photo(): GrabOne({self.timeout_ms}) (milli-seconds)")
        grab_result = self._camera.GrabOne(self.timeout_ms, timeout_handling)  # timeout in milliseconds

        logger.debug(f"BaslerCamera.take_photo(): GrabOne({self.timeout_ms}) succeeded: {grab_result.GrabSucceeded()}")
        img = get_image(grab_result, self.converter)

        logger.debug(f"BaslerCamera.take_photo() took {(default_timer() - t0) * 1000:.4g} ms.")
        return img


# Example usage:
if __name__ == "__main__":

    # Create camera instance with IP address
    camera = BaslerCamera(
        # ip_address="192.168.10.5",
        timeout_ms=1000,
        # transmission_type="Multicast",
        # destination_ip="192.168.10.221"
    )

    # Connect to the camera
    camera.connect()

    for _ in range(10):
        photo = camera.take_photo(100)
    camera.disconnect()
    camera.take_photo()
