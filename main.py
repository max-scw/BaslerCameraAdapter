from fastapi import FastAPI
#from fastapi_offline import FastAPIOffline as FastAPI
from fastapi import Depends, HTTPException
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

from DataModels import CameraParameter, CameraPhotoParameter
from typing import Union

DATETIME_INIT = datetime.now()

# setup level
log_file = get_env_variable("LOGFILE", None)
LOG_LEVEL = get_env_variable("LOGGING_LEVEL", logging.DEBUG)
logging.basicConfig(
    level=cast_logging_level(LOG_LEVEL),
    # format="%(asctime)s [%(levelname)s] %(message)s",
    # handlers=[logging.StreamHandler(sys.stdout)] #+
    #          # [logging.FileHandler(Path(log_file).with_suffix(".log"))] if log_file is not None else [],
    )
logging.info(f"Logging configured: level={LOG_LEVEL}, file={log_file}")


# define endpoints
ENTRYPOINT_TEST = "/test"
ENTRYPOINT_TEST_IMAGE = ENTRYPOINT_TEST + "/image"

ENTRYPOINT_BASLER = "/basler"
ENTRYPOINT_TAKE_PHOTO = ENTRYPOINT_BASLER + "/take-photo"
ENTRYPOINT_CAMERA_INFO = ENTRYPOINT_BASLER + "/get-camera-info"

# set up fastAPI
title = "BaslerCameraAdapter"
summary = "Minimalistic server providing a REST api to interact with a Basler camera."
description = """
This [*FastAPI*](https://fastapi.tiangolo.com/) server provides REST endpoints to connect to [*Basler*](https://www.baslerweb.com) cameras 📷 using the Python project [*pypylon*](https://pypi.org/project/pypylon/) which wraps the [*Pylon Camera Software Suite*](https://www2.baslerweb.com/en/downloads/software-downloads/) to python. Both, the *Pylon Camera Software Suite* and *pypylon* are officially maintained by *Basler*. 
**This project is no official project of *Basler*.**
"""
contact = {
    "name": "max-scw",
    "url": "https://github.com/max-scw/BaslerCameraAdapter",
}
license_info = {
    "name": "BSD 3-Clause License",
    "url": "https://github.com/max-scw/BaslerCameraAdapter/blob/main/LICENSE",
}
app = FastAPI(
    title=title,
    description=description,
    summary=summary,
    # version="0.0.1",
    contact=contact,
    license_info=license_info
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


# ----- home
@app.get("/")
async def home():
    return {
            "Title": title,
            "Description": summary,
            "Help": "see /docs for help (automatic docs with Swagger UI).",
            "Software": {
                "fastAPI": f"version {fastapi.__version__}",
                "Python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            },
            "License": license_info,
            "Impress": contact,
            "Startup date": DATETIME_INIT
        }

# ----- Interact with the Basler camera
# create global camera instance
CAMERA = None


def create_camera(params: CameraParameter):
    global CAMERA
    if (
            (CAMERA is None)
            or
            (isinstance(CAMERA, BaslerCamera) and any([val != getattr(CAMERA, ky) for ky, val in params.dict().items()]))
    ):
        # disconnect camera if existing
        if isinstance(CAMERA, BaslerCamera):
            CAMERA.disconnect()

        # create new instance
        CAMERA = BaslerCamera(**params.dict())
        # Connect to the camera
        CAMERA.connect()

    return CAMERA


def get_test_image() -> Union[Path, None]:
    # get path to image or folder / name pattern
    image_path = get_env_variable("TEST_IMAGE_PATH", "/home/app/test")
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
async def take_photo(
        params: CameraPhotoParameter = Depends(),
):
    # add functionality to emulate a camera
    if params.emulate_camera:
        params.serial_number = None
        params.ip_address = None

    if params.ip_address:
        params.ip_address = params.ip_address.strip("'").strip('"')
    if params.subnet_mask:
        params.subnet_mask = params.subnet_mask.strip("'").strip('"')

    cam = create_camera(CameraParameter(**{ky: getattr(params, ky) for ky in CameraParameter.model_fields}))

    image_format = params.format.strip(".")
    if image_format.lower() == "jpg":
        image_format = "jpeg"

    image_quality = params.quality

    if params.emulate_camera:
        p2img = get_test_image()

        if p2img is not None:
            # PNG images are required for pypylon on linux
            image_format_test_image = "png"
            # convert image if it is the wrong format
            if p2img.suffix.lower() != f".{image_format_test_image}":
                # open image
                img = Image.open(p2img)
                # save as PNG
                p2test = Path(f"./testimage.{image_format_test_image}")
                img.save(p2test, format=image_format, quality=image_quality)

            # set test picture to camera
            cam.set_test_picture(p2img)

    logging.debug(f"take_photo({params}): cam.take_photo({params.exposure_time_microseconds})")
    t = [("start", default_timer())]
    image_array = cam.take_photo(params.exposure_time_microseconds)
    t.append(("take photo", default_timer()))

    # save image to an in-memory bytes buffer
    im = Image.fromarray(image_array)
    with io.BytesIO() as buf:
        im.save(buf, format=image_format, quality=image_quality)
        image_bytes = buf.getvalue()
    t.append(("convert PIL", default_timer()))

    diff = {t[i][0]: (t[i][1] - t[i - 1][1]) * 1000 for i in range(1, len(t))}
    logging.debug(f"take_photo({params}) took {diff} ms.")

    return Response(
        content=image_bytes,
        media_type=f"image/{image_format}"
    )


@app.get(ENTRYPOINT_CAMERA_INFO)
def get_camera_info(
        serial_number: int = None,
        ip_address: str = None,
        subnet_mask: str = None
):
    cam = create_camera(
        CameraParameter(
            serial_number=serial_number,
            ip_address=ip_address,
            subnet_mask=subnet_mask
        )
    )
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
    # set_env_variable("TEST_IMAGE_PATH", "test_images")

    uvicorn.run(app=app, port=5051, log_level=LOG_LEVEL)
