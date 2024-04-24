from fastapi import FastAPI
from fastapi.responses import FileResponse, Response

import uvicorn
from prometheus_fastapi_instrumentator import Instrumentator, metrics

from pathlib import Path
from random import shuffle
import io
from PIL import Image

# versions / info
import fastapi
import sys

# logging / timing
from timeit import default_timer
from datetime import datetime
import logging

# custom packages
from BaslerCamera import BaslerCamera
from utils_env_vars import (
    get_env_variable,
    cast_logging_level,
    set_env_variable
)

from typing import Union


# define endpoints
ENTRYPOINT_TEST = "/test"
ENTRYPOINT_TEST_IMAGE = ENTRYPOINT_TEST + "/image"

ENTRYPOINT_BASLER = "/basler"
ENTRYPOINT_TAKE_PHOTO = ENTRYPOINT_BASLER + "/take-photo"
ENTRYPOINT_CAMERA_INFO = ENTRYPOINT_BASLER + "/get-camera-info"


description = """
This [*FastAPI*](https://fastapi.tiangolo.com/) server provides REST endpoints to connect to [*Basler*](https://www.baslerweb.com) cameras 📷 using the Python project [*pypylon*](https://pypi.org/project/pypylon/) which wraps the [*Pylon Camera Software Suite*](https://www2.baslerweb.com/en/downloads/software-downloads/) to python. Both, the *Pylon Camera Software Suite* and *pypylon* are officially maintained by *Basler*. 
**This project is no official project of *Basler*.**
"""

app = FastAPI(
    title="BaslerCameraAdapter",
    description=description,
    summary="Camera Adapter for Basler cameras",
    # version="0.0.1",
    contact={
        "name": "max-scw",
        "url": "https://github.com/max-scw/BaslerCameraAdapter",
    },
    license_info={
        "name": "BSD 3-Clause License",
        "url": "https://github.com/max-scw/BaslerCameraAdapter/blob/main/LICENSE",
    }
)


# create endpoint for prometheus
instrumentator = Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    # should_instrument_requests_inprogress=True,
    excluded_handlers=["/test/*", "/metrics"],
    # should_respect_env_var=True,
    # env_var_name="ENABLE_METRICS",
    # inprogress_name="inprogress",
    # inprogress_labels=True,
)
# add metrics
instrumentator.add(
    metrics.request_size(
        should_include_handler=True,
        should_include_method=False,
        should_include_status=True,
        # metric_namespace="a",
        # metric_subsystem="b",
    )
)
instrumentator.add(
    metrics.response_size(
        should_include_handler=True,
        should_include_method=False,
        should_include_status=True,
        # metric_namespace="namespace",
        # metric_subsystem="subsystem",
    )
)
# expose app
instrumentator.instrument(app, metric_namespace="basler-camera-adapter").expose(app)


# setup level
logging.basicConfig(
    level=cast_logging_level(get_env_variable("LOGGING_LEVEL", logging.DEBUG)),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(Path(get_env_variable("LOGFILE", "log")).with_suffix(".log")),
        logging.StreamHandler(sys.stdout)
    ],
)


# ----- home
@app.get("/")
async def home():
    return {
        "Message": "This is a minimal website & webservice to interact with a Basler camera.",
        "docs": "/docs (automatic docs with Swagger UI)",
        "Software": f"fastAPI (Version {fastapi.__version__}); Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "Project": "https://github.com/max-scw/BaslerCameraAdapter",
        "Startup date": datetime.now()
    }

# ----- Interact with the Basler camera
# create global camera instance
CAMERA = None


def create_camera(**kwargs):
    global CAMERA
    if (
            (CAMERA is None)
            or
            (isinstance(CAMERA, BaslerCamera) and any([val != getattr(CAMERA, ky) for ky, val in kwargs.items()]))
    ):
        # disconnect camera if existing
        if isinstance(CAMERA, BaslerCamera):
            CAMERA.disconnect()

        # create new instance
        CAMERA = BaslerCamera(**kwargs)
        # Connect to the camera
        CAMERA.connect()
    return CAMERA


def get_test_image() -> Union[Path, None]:
    # get path to image or folder / name pattern
    image_path = get_env_variable("TEST_IMAGE_PATH", None)
    logging.debug(f"Return test image: TEST_IMAGE_PATH={image_path}")

    if image_path:
        if isinstance(image_path, list):
            images_ = [el for el in image_path if Path(el).is_file()]
        else:
            image_path = Path(image_path)
            if image_path.is_dir():
                images_ = image_path.glob("*")
            else:
                images_ = image_path.glob(image_path.name)
        images = list(images_)
        logging.debug(f"List of images: {', '.join([el.as_posix() for el in images])}")
        # shuffle list
        shuffle(images)
        # return first image that exists
        for p2img in images:
            if p2img.is_file():
                logging.debug(f"Return image: {p2img.as_posix()}")
                return p2img
    return None


@app.get(ENTRYPOINT_TAKE_PHOTO)
def take_photo(
        exposure_time_microseconds: int = None,
        serial_number: int = None,
        ip_address: str = None,
        emulate_camera: bool = False,
        timeout: int = None,
        transmission_type: str = None,
        destination_ip_address: str = None,
        destination_port: int = None
):
    port_max = 65535
    if destination_port and 1 < destination_port > port_max:
        raise ValueError(f"Destination port must be smaller than {port_max} but was destination_port={destination_port}")

    kwargs = {
        "serial_number": serial_number if not emulate_camera else None,
        "ip_address": ip_address if not emulate_camera else None,
        "timeout": timeout,
        "transmission_type": transmission_type,
        "destination_ip": destination_ip_address,
        "destination_port": destination_port
    }
    cam = create_camera(**kwargs)

    image_format = "bmp"  # default image format
    if emulate_camera:
        # PNG images are required for pypylon on linux
        image_format = "PNG"
        p2img = get_test_image()
        # convert image if it is th wrong format
        if p2img.suffix.lower() != f".{image_format}":
            # open image
            img = Image.open(p2img)
            # save as PNG
            p2img = Path("./testimage.png")
            img.save(p2img, image_format)
        # set test picture to camera
        cam.set_test_picture(p2img)

    logging.debug(f"take_photo({kwargs}): cam.take_photo({exposure_time_microseconds})")
    t = [("start", default_timer())]
    image_array = cam.take_photo(exposure_time_microseconds)
    t.append(("take photo", default_timer()))

    # save image to an in-memory bytes buffer
    im = Image.fromarray(image_array)
    with io.BytesIO() as buf:
        im.save(buf, format=image_format)
        image_bytes = buf.getvalue()
    t.append(("convert PIL", default_timer()))

    diff = {t[i][0]: (t[i][1] - t[i - 1][1]) * 1000 for i in range(1, len(t))}
    logging.debug(f"take_photo({kwargs}) took {diff} ms.")

    return Response(
        content=image_bytes,
        media_type="image/bmp"
    )


@app.get(ENTRYPOINT_CAMERA_INFO)
def get_camera_info(
        serial_number: int = None,
        ip_address: str = None
):
    cam = create_camera(serial_number=serial_number, ip_address=ip_address)
    return cam.get_camera_info()


# ----- TEST FUNCTIONS
@app.get(ENTRYPOINT_TEST)
def negate(boolean: bool):
    return not boolean


@app.get(ENTRYPOINT_TEST_IMAGE)
def return_test_image():
    p2img = get_test_image()
    if isinstance(p2img, Path):
        return FileResponse(
            p2img.as_posix(),
            media_type=f"image/{p2img.suffix.strip('.')}"
        )
    else:
        # return None otherwise
        return None


if __name__ == "__main__":
    # set_env_variable("LOGGING_LEVEL", logging.DEBUG)
    set_env_variable("TEST_IMAGE_PATH", "test_images")

    uvicorn.run(app=app, port=5051)
