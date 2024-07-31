from fastapi import FastAPI
# from fastapi_offline import FastAPIOffline as FastAPI
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
from BaslerCamera import BaslerCamera
from BaslerCameraThread import CameraThread
from utils_env_vars import get_env_variable, get_logging_level

from DataModels import (
    BaslerCameraSettings,
    BaslerCameraRequest,
    BaslerCameraParams,
    PhotoParams
)
from typing import Union

# store time stamp to display the startup time at default entry point
DATETIME_INIT = datetime.now()

T_SLEEP = 1 / get_env_variable("FRAMES_PER_SECOND", 10)
PIXEL_TYPE = get_env_variable("PIXEL_TYPE", None)


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
ENTRYPOINT_BASLER_SINGLE_FRAME = ENTRYPOINT_BASLER + "/single-frame-acquisition"
ENTRYPOINT_TAKE_PHOTO = ENTRYPOINT_BASLER_SINGLE_FRAME + "/take-photo"
ENTRYPOINT_CAMERA_INFO = ENTRYPOINT_BASLER_SINGLE_FRAME + "/get-camera-info"
ENTRYPOINT_BASLER_CONTINUOUS_FRAME = ENTRYPOINT_BASLER + "/continuous-acquisition"
ENTRYPOINT_GET_IMAGE = ENTRYPOINT_BASLER_CONTINUOUS_FRAME + "/get-image"
ENTRYPOINT_CLOSE = ENTRYPOINT_BASLER_CONTINUOUS_FRAME + "/close"

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


def stop_thread(thread) -> bool:
    thread.stop()
    thread.join()
    return True


def create_basler_camera(params: BaslerCameraParams) -> BaslerCamera:
    # get local logger + set logging level
    logging.getLogger().setLevel(LOG_LEVEL)
    t1 = default_timer()

    # "load" global variable
    global CAMERA

    if (
            (CAMERA is None)
            or
            (isinstance(CAMERA, BaslerCamera) and any(
                [val != getattr(CAMERA, ky) for ky, val in params.dict().items()]))
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


def process_input_variables(camera_params: BaslerCameraParams, photo_params: PhotoParams):
    # # get local logger + set logging level
    # logging.getLogger().setLevel(LOG_LEVEL)
    logging.debug(f"Process input variables: camera={camera_params}, photo={photo_params}")

    # add functionality to emulate a camera
    if photo_params.emulate_camera:
        camera_params.serial_number = None
        camera_params.ip_address = None

    if camera_params.ip_address:
        camera_params.ip_address = camera_params.ip_address.strip("'").strip('"')
    if camera_params.subnet_mask:
        camera_params.subnet_mask = camera_params.subnet_mask.strip("'").strip('"')

    logging.debug(f"Pixel type: {camera_params.pixel_type}, PIXEL_TYPE={PIXEL_TYPE}")
    if (camera_params.pixel_type.lower() == "undefined") and PIXEL_TYPE:
        camera_params.pixel_type = PIXEL_TYPE

    image_format = photo_params.format.strip(".")
    if image_format.lower() == "jpg":
        image_format = "jpeg"

    photo_params.format = image_format
    return camera_params, photo_params


def get_camera(camera_params: BaslerCameraParams, photo_params: PhotoParams) -> BaslerCamera:
    # # get local logger + set logging level
    # logging.getLogger().setLevel(LOG_LEVEL)

    # extract parameter for a CameraParameter object
    t0 = default_timer()
    cam_params = BaslerCameraParams(**{ky: getattr(camera_params, ky) for ky in BaslerCameraParams.model_fields})
    cam = create_basler_camera(cam_params)

    if photo_params.emulate_camera:
        p2img = get_test_image()

        if p2img is not None:
            # PNG images are required for pypylon on linux
            # convert image if it is the wrong format
            if p2img.suffix.lower() != ".png":
                # open image
                img = Image.open(p2img)
                # save as PNG
                p2img = Path("./testimage.png")
                img.save(p2img, format="PNG", quality=photo_params.quality)

            # set test picture to camera
            cam.set_test_picture(p2img)

    logging.debug(f"Getting camera object took {(default_timer() - t0) * 1000:.4g} ms")
    return cam


def take_picture(
        camera_params: BaslerCameraParams = Depends(),
        photo_params: PhotoParams = Depends(),
):
    t0 = default_timer()
    t = [("start", default_timer())]
    camera_params, photo_params = process_input_variables(camera_params, photo_params)
    t.append(("process_input_variables()", default_timer()))

    cam = get_camera(camera_params, photo_params)
    t.append(("get_camera()", default_timer()))

    if camera_params.acquisition_mode == "Continuous":
        # initialize control variable
        start_thread = False

        global CAMERA_THREAD
        if CAMERA_THREAD is None:
            start_thread = True
        elif (cam.camera != CAMERA_THREAD.camera) or (not CAMERA_THREAD.is_alive()):
            start_thread = True
            logging.debug(f"Restart new camera thread ({cam})")
            # stop camera thread
            stop_thread(CAMERA_THREAD)

        if start_thread:
            logging.debug(f"Starting new camera thread with {cam}.")
            # start camera thread
            CAMERA_THREAD = CameraThread(
                cam.camera,
                pixel_type=cam.pixel_type,
                dt_sleep=T_SLEEP,
                timeout=photo_params.timeout
            )
            CAMERA_THREAD.start()
            # wait for first image
            sleep(max(((photo_params.exposure_time_microseconds + 42000) / 1e6, 0.1, T_SLEEP)))

        # get image
        image_array, timestamp = CAMERA_THREAD.get_image()
    else:
        image_array = cam.take_photo(photo_params.exposure_time_microseconds)
    t.append(("take photo", default_timer()))

    if image_array is None:
        raise HTTPException(400, "No image retrieved.")

    # save image to an in-memory bytes buffer
    im = Image.fromarray(image_array)
    with io.BytesIO() as buf:
        im.save(buf, format=photo_params.format, quality=photo_params.quality)
        image_bytes = buf.getvalue()
    t.append(("Convert bytes to PIL image", default_timer()))

    diff = {t[i][0]: (t[i][1] - t[i - 1][1]) * 1000 for i in range(1, len(t))}
    logging.info(f"take_picture({camera_params}, {photo_params}) took {diff} ms "
                 f"(total {(default_timer() - t0) * 1000:.4g} ms).")

    return Response(
        content=image_bytes,
        media_type=f"image/{photo_params.format}"
    )


@app.get(ENTRYPOINT_TAKE_PHOTO)
async def take_single_photo(
        camera_params: BaslerCameraRequest = Depends(),
        photo_params: PhotoParams = Depends()
):
    # hardcode acquisition mode to single frame
    camera_params_ = BaslerCameraParams(
        **camera_params.dict(),
        acquisition_mode="SingleFrame"
    )

    return take_picture(camera_params_, photo_params)


@app.get(ENTRYPOINT_CAMERA_INFO)
def get_camera_info(
        serial_number: int = None,
        ip_address: str = None,
        subnet_mask: str = None
):
    cam = create_basler_camera(
        BaslerCameraParams(
            serial_number=serial_number,
            ip_address=ip_address,
            subnet_mask=subnet_mask
        )
    )
    return cam.get_camera_info()


@app.get(ENTRYPOINT_GET_IMAGE)
async def get_latest_photo(
        camera_params: BaslerCameraRequest = Depends(),
        photo_params: PhotoParams = Depends()
):
    # hardcode acquisition mode to continuous
    camera_params_ = BaslerCameraParams(
        **camera_params.dict(),
        acquisition_mode="Continuous"
    )

    return take_picture(camera_params_, photo_params)


@app.get(ENTRYPOINT_CLOSE)
def close_camera_thread():
    global CAMERA_THREAD
    if CAMERA_THREAD is not None:
        logging.debug("Camera thread was open.")
        stop_thread(CAMERA_THREAD)
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
