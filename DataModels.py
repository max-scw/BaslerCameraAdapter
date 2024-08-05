from pydantic import BaseModel, Field
from typing_extensions import Annotated
from typing import Optional, Union, Literal

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


class BaslerCameraSettings(BaseModel):
    serial_number: Optional[int] = None
    ip_address: Optional[str] = None
    subnet_mask: Optional[str] = None

    transmission_type: Optional[TransmissionType] = "Unicast"
    destination_ip_address: Optional[str] = None
    destination_port: Optional[Annotated[int, Field(strict=False, le=653535, ge=0)]] = None

    convert_to_format: Optional[OutputImageFormat] = "null"
    pixel_type: Optional[PixelType] = "Undefined"


class BaslerCameraParams(BaslerCameraSettings):
    acquisition_mode: Optional[AcquisitionMode] = "SingleFrame"


class PhotoParams(BaseModel):
    exposure_time_microseconds: Optional[Annotated[int, Field(strict=False, ge=500)]] = 10000
    timeout: Optional[Annotated[int, Field(strict=False, ge=200)]] = 1000  # milli seconds

    emulate_camera: bool = False
    # image
    format: Optional[str] = "jpeg"
    quality: Optional[Annotated[int, Field(strict=False,  le=100, ge=10)]] = 85
