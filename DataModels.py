from pydantic import BaseModel, Field
from typing_extensions import Annotated
from typing import Optional, Union, Literal


class CameraParameter(BaseModel):
    serial_number: Optional[int] = None
    ip_address: Optional[str] = None
    subnet_mask: Optional[str] = None

    pixel_type: Optional[Union[int, str]] = -1

    transmission_type: Optional[Literal["Unicast", "Multicast", "Broadcast"]] = None
    destination_ip_address: Optional[str] = None
    destination_port: Optional[Annotated[int, Field(strict=False, le=653535, ge=0)]] = None

    acquisition_mode: Optional[Literal["Continuous", "SingleFrame"]] = "SingleFrame"


class CameraPhotoParameter(CameraParameter):
    exposure_time_microseconds: Optional[int] = 10000
    timeout: Optional[int] = None  # milli seconds

    emulate_camera: bool = False
    # image
    format: Optional[str] = "jpeg"
    quality: Optional[Annotated[int, Field(strict=False,  le=100)]] = 85

