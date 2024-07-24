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

from time import sleep

# versions / info
import fastapi
import sys

# logging / timing
from timeit import default_timer
from datetime import datetime
import logging

# custom packages
from BaslerCamera import BaslerCamera, basler_pixe_type
from BaslerCameraThread import CameraThread
from utils_env_vars import (
    get_env_variable,
    cast_logging_level,
    set_env_variable,
    get_logging_level
)

from DataModels import CameraParameter, CameraPhotoParameter
from typing import Union

DATETIME_INIT = datetime.now()

# setup level
log_file = get_env_variable("LOGFILE", None)
LOG_LEVEL = get_logging_level("LOGGING_LEVEL", logging.DEBUG)

# configure logging
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)] +
             [logging.FileHandler(Path(log_file).with_suffix(".log"))] if log_file is not None else [],
    )

# first logging message
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
CAMERA: BaslerCamera = None
CAMERA_THREAD: CameraThread = None
USE_CONTINUOUS_ACQUISTITION: bool = True


def create_basler_camera(params: CameraParameter):
    # get local logger + set logging level
    logging.getLogger().setLevel(LOG_LEVEL)

    t0 = default_timer()
    global CAMERA
    t1 = default_timer()
    logging.debug(f"Load global variable CAMERA={CAMERA} took {(t1 - t0) * 1000:.4g} ms")

    if (
            (CAMERA is None)
            or
            (isinstance(CAMERA, BaslerCamera) and any([val != getattr(CAMERA, ky) for ky, val in params.dict().items()]))
    ):
        # disconnect camera if existing
        if isinstance(CAMERA, BaslerCamera):
            CAMERA.disconnect()
        t2 = default_timer()
        logging.debug(f"Disconnect ({isinstance(CAMERA, BaslerCamera)}) took {(t2 - t1) * 1000:.4g} ms")

        # create new instance
        CAMERA = BaslerCamera(**params.dict())
        t3 = default_timer()
        logging.debug(f"Creating BaslerCamera object took {(t3 - t2) * 1000:.4g} ms")

        # Connect to the camera
        CAMERA.connect()
        t4 = default_timer()
        logging.debug(f"Connecting to camera took {(t4 - t3) * 1000:.4g} ms")

    return CAMERA


def get_test_image() -> Union[Path, None]:
    # get local logger + set logging level
    logging.getLogger().setLevel(LOG_LEVEL)

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
    # get local logger + set logging level
    logging.getLogger().setLevel(LOG_LEVEL)

    t0 = default_timer()
    t = [("start", default_timer())]
    # add functionality to emulate a camera
    if params.emulate_camera:
        params.serial_number = None
        params.ip_address = None

    if params.ip_address:
        params.ip_address = params.ip_address.strip("'").strip('"')
    if params.subnet_mask:
        params.subnet_mask = params.subnet_mask.strip("'").strip('"')

    if isinstance(params.pixel_type, str):
        params.pixel_type = basler_pixe_type(params.pixel_type)

    image_format = params.format.strip(".")
    if image_format.lower() == "jpg":
        image_format = "jpeg"

    image_quality = params.quality

    # hardcode acquisition mode to continuous
    params.acquisition_mode = "Continuous"

    t.append(("Input parameter", default_timer()))

    cam_params = CameraParameter(**{ky: getattr(params, ky) for ky in CameraParameter.model_fields})
    t.append(("Create CameraParameter object", default_timer()))
    cam = create_basler_camera(cam_params)
    t.append(("Create camera", default_timer()))

    if params.emulate_camera:
        p2img = get_test_image()

        if p2img is not None:
            # PNG images are required for pypylon on linux
            # convert image if it is the wrong format
            if p2img.suffix.lower() != ".png":
                # open image
                img = Image.open(p2img)
                # save as PNG
                p2img = Path("./testimage.png")
                img.save(p2img, format="PNG", quality=image_quality)

            # set test picture to camera
            cam.set_test_picture(p2img)
    t.append(("Emulate camera", default_timer()))

    logging.debug(f"take_photo({params}): cam.take_photo({params.exposure_time_microseconds})")

    if USE_CONTINUOUS_ACQUISTITION:
        dt_sleep = 0.5  # FIXME: from env variables
        global CAMERA_THREAD
        if CAMERA_THREAD is None:
            logging.debug(f"Starting new camera thread with {cam}.")
            # start camera thread
            CAMERA_THREAD = CameraThread(cam.camera, cam.pixel_type, dt_sleep=dt_sleep)
            CAMERA_THREAD.start()
            # wait for first image
            sleep((params.exposure_time_microseconds + 25000) / 1e6)
        elif (cam.camera != CAMERA_THREAD.camera) or (not CAMERA_THREAD.is_alive()):
            logging.debug(f"Camera instances: {cam.camera} != {CAMERA_THREAD.camera}")

            logging.debug(f"Restart new camera thread ({cam})")
            # stop camera thread
            CAMERA_THREAD.stop()
            CAMERA_THREAD.join()
            # start camera thread
            CAMERA_THREAD = CameraThread(cam.camera, cam.pixel_type, dt_sleep=dt_sleep)
            CAMERA_THREAD.start()
            # wait for first image
            sleep((params.exposure_time_microseconds + 14000) / 1e6)

        image_array, timestamp = CAMERA_THREAD.get_latest_image()
    else:
        image_array = cam.take_photo(params.exposure_time_microseconds)
    t.append(("take photo", default_timer()))

    if image_array is None:
        raise HTTPException(400, "No image retrieved.")

    # save image to an in-memory bytes buffer
    im = Image.fromarray(image_array)
    with io.BytesIO() as buf:
        im.save(buf, format=image_format, quality=image_quality)
        image_bytes = buf.getvalue()
    t.append(("Convert bytes to PIL image", default_timer()))

    diff = {t[i][0]: (t[i][1] - t[i - 1][1]) * 1000 for i in range(1, len(t))}
    logging.info(f"take_photo({params}) took {diff} ms (total {(default_timer() - t0) * 1000:.4g} ms).")

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
    cam = create_basler_camera(
        CameraParameter(
            serial_number=serial_number,
            ip_address=ip_address,
            subnet_mask=subnet_mask
        )
    )
    return cam.get_camera_info()


@app.get("/close-camera")
def close_camera_thread():
    global CAMERA_THREAD
    if CAMERA_THREAD is not None:
        logging.debug("Camera thread was open.")
        CAMERA_THREAD.stop()
        CAMERA_THREAD.join()
        # reset camera thread object
        CAMERA_THREAD = None
    return True


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
    # set_env_variable("TEST_IMAGE_PATH", "test_images")  # FIXME: for testing only

    # get logger
    logger = logging.getLogger("uvicorn")
    logger.setLevel(LOG_LEVEL)
    logger.debug(f"logger.level={logger.level}")

    logger.debug("====> Starting uvicorn server <====")
    try:
        uvicorn.run(app=app, port=5051, log_level=LOG_LEVEL)
    except:
        logging.info("Stopping camera thread...")
        if CAMERA_THREAD is not None:
            CAMERA_THREAD.stop()
            CAMERA_THREAD.join()
