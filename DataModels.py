from pydantic import BaseModel, Field

from utils import default_from_env , set_env_variable

from typing import Optional, Annotated, Literal, Any, Union, List, Tuple, Dict


# define new data types
PixelType = Literal[
    'BGR10V1packed',
    'BGR10V2packed',
    'BGR10packed',
    'BGR12packed',
    'BGR8packed',
    'BGRA8packed',
    'BayerBG10',
    'BayerBG10p',
    'BayerBG12',
    'BayerBG12Packed',
    'BayerBG12p',
    'BayerBG16',
    'BayerBG8',
    'BayerGB10',
    'BayerGB10p',
    'BayerGB12',
    'BayerGB12Packed',
    'BayerGB12p',
    'BayerGB16',
    'BayerGB8',
    'BayerGR10',
    'BayerGR10p',
    'BayerGR12',
    'BayerGR12Packed',
    'BayerGR12p',
    'BayerGR16',
    'BayerGR8',
    'BayerRG10',
    'BayerRG10p',
    'BayerRG12',
    'BayerRG12Packed',
    'BayerRG12p',
    'BayerRG16',
    'BayerRG8',
    'Confidence16',
    'Confidence8',
    'Coord3D_ABC32f',
    'Coord3D_C16',
    'Coord3D_C8',
    'Data16',
    'Data16s',
    'Data32',
    'Data32f',
    'Data32s',
    'Data64',
    'Data64f',
    'Data64s',
    'Data8',
    'Data8s',
    'Double',
    'Mono10',
    'Mono10p',
    'Mono10packed',
    'Mono12',
    'Mono12p',
    'Mono12packed',
    'Mono16',
    'Mono1packed',
    'Mono2packed',
    'Mono4packed',
    'Mono8',
    'Mono8signed',
    'RGB10packed',
    'RGB10planar',
    'RGB12V1packed',
    'RGB12packed',
    'RGB12planar',
    'RGB16packed',
    'RGB16planar',
    'RGB8packed',
    'RGB8planar',
    'RGBA8packed',
    'Undefined',
    'YCbCr420_8_YY_CbCr_Semiplanar',
    'YCbCr422_8_YY_CbCr_Semiplanar',
    'YUV411packed',
    'YUV420planar',
    'YUV422_YUYV_Packed',
    'YUV422packed',
    'YUV422planar',
    'YUV444packed',
    'YUV444planar'
]
OutputImageFormat = Literal["RGB", "BGR", "Mono", "null"]
AcquisitionMode = Literal["SingleFrame", "Continuous"]
TransmissionType = Literal["Unicast", "Multicast", "Broadcast"]
TriggerMode = Literal["FrameStart", "FrameEnd", "FrameActive", "AcquisitionStart", "FrameBurstEnd", "FrameBurstActive", "ExposureStart", "ExposureEnd", "ExposureActive", "LineStart", "Start", "End", "Active"]
TriggerActivation = Literal["RisingEdge", "FallingEdge", "AnyEdge", "LevelHigh", "LevelLow"]


def get_not_none_values(params: BaseModel) -> Dict[str, Any]:
    """returns the parameter of a Data Model but ignores keys that indicate undefined values."""
    return {
        ky: vl for ky, vl in params.model_dump().items()
        if not ((vl is None) or (isinstance(vl, str) and vl in ("null", "None", "Undefined")))
    }


class BaslerCameraAtom(BaseModel):
    serial_number: Optional[int] = default_from_env("SERIAL_NUMBER", None)
    ip_address: Optional[str] = default_from_env("IP_ADDRESS", None)

    # emulate_camera: bool = default_from_env("EMULATE_CAMERA", False)


class CameraCommunication(BaseModel):
    transmission_type: Optional[TransmissionType] = default_from_env("TRANSMISSION_TYPE", "Unicast")
    destination_ip_address: Optional[str] = default_from_env("DESTINATION_IP_ADDRESS", None)
    destination_port: Optional[
        Annotated[int, Field(strict=False, le=653535, ge=26)]  # dynamic ports 49152-65535
    ] = default_from_env("DESTINATION_PORT", None)
    subnet_mask: Optional[str] = default_from_env("SUBNET_MASK", None)


class CameraSettings(BaslerCameraAtom):
    convert_to_format: Optional[OutputImageFormat] = default_from_env("CONVERT_TO_FORMAT", "null")
    pixel_format: Optional[PixelType] = default_from_env("PIXEL_TYPE", "Mono8")

    timeout_ms: Optional[
        Annotated[int, Field(strict=False, ge=200)]
    ] = default_from_env("TIMEOUT_MS", 5000)  # milli seconds


class CameraImageAcquisition(BaseModel):
    exposure_time_microseconds: Optional[
            Annotated[int, Field(strict=False, ge=500)]
    ] = default_from_env(["EXPOSURE_TIME", "EXPOSURE_TIME_MICROSECONDS"], 1000)  # micro seconds

    acquisition_mode: Optional[AcquisitionMode] = default_from_env("ACQUISITION_MODE", "SingleFrame")


class BaslerCameraSettings(CameraCommunication, CameraSettings, CameraImageAcquisition):
    pass


class BaslerCameraParams(BaslerCameraSettings):
    pass
# TODO: validator pixel format

# --- Image parameter
class ImageParamsFormat(BaseModel):
    # image format
    format: Optional[str] = default_from_env("IMAGE_FORMAT", "jpeg")
    quality: Optional[
        Annotated[int, Field(strict=False, le=100, ge=10)]
    ] = default_from_env("IMAGE_QUALITY", 100)


class ImageParamsProcessing(BaseModel):
    # image processing: rotation
    rotation_angle: Optional[float] = default_from_env("IMAGE_ROTATION_ANGLE", 0)  # degree
    rotation_expand: Optional[bool] = False
    # image processing: crop
    roi_left: Optional[
        Annotated[float, Field(strict=False, ge=0)]
    ] = default_from_env("IMAGE_ROI_LEFT", 0)
    roi_top: Optional[
        Annotated[float, Field(strict=False, ge=0)]
    ] = default_from_env("IMAGE_ROI_TOP", 0)
    roi_right: Optional[
        Annotated[float, Field(strict=False, ge=0)]
    ] = default_from_env("IMAGE_ROI_RIGHT", 1)
    roi_bottom: Optional[
        Annotated[float, Field(strict=False, ge=0)]
    ] = default_from_env("IMAGE_ROI_BOTTOM", 1)


class ImageParams(ImageParamsFormat, ImageParamsProcessing):
    pass
