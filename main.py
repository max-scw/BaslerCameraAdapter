from fastapi import Depends, HTTPException, FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPAuthorizationCredentials
from contextlib import asynccontextmanager

import uvicorn

from pathlib import Path
from random import shuffle
import io
from PIL import Image

import signal

from pypylon.pylon import TimeoutException

from time import sleep

# logging / timing
from timeit import default_timer

# custom packages
from BaslerCamera import BaslerCamera
from BaslerCameraThread import CameraThread
from utils import default_from_env, setup_logging, set_env_variable
# set_env_variable("LOGGING_LEVEL", "DEBUG")  # FIXME: for debugging only
from utils_fastapi import setup_prometheus_metrics, default_fastapi_setup, AccessToken

from DataModels import (
    BaslerCameraSettings,
    BaslerCameraParams,
    ImageParams,
    BaslerCameraAtom,
    OutputImageFormat,
    get_not_none_values, ImageParams
)
from typing import Union

# set_env_variable("TEST_IMAGE", "./test_images")  # FIXME: for debugging only
T_SLEEP = 1 / default_from_env("FRAMES_PER_SECOND", 10)
PIXEL_FORMAT = default_from_env("PIXEL_TYPE", None)

# create global camera instance
CAMERA: BaslerCamera = None
CAMERA_THREAD: CameraThread = None

# Setup logging
logger = setup_logging(__name__)

# lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting FastAPI ...")
    yield
    logger.info("Shutting down ...")
    close_cameras()


# define endpoints
ENTRYPOINT_TEST = "/test"
ENTRYPOINT_TEST_IMAGE = ENTRYPOINT_TEST + "/image"
ENTRYPOINT_TEST_NEGATE = ENTRYPOINT_TEST + "/negate"

ENTRYPOINT_BASLER = "/basler"
ENTRYPOINT_TAKE_PHOTO = ENTRYPOINT_BASLER + "/take-photo"
ENTRYPOINT_CAMERA_INFO = ENTRYPOINT_BASLER + "/get-camera-info"
ENTRYPOINT_BASLER_CLOSE = ENTRYPOINT_BASLER + "/close"

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

# setup of fastAPI server
app = default_fastapi_setup(
    title,
    summary,
    description,
    license_info,
    contact,
    lifespan=lifespan,
    root_path=default_from_env(["FASTAPI_ROOT_PATH", "ROOT_PATH"], None)
)
# set up /metrics endpoint for prometheus
EXECUTION_COUNTER, EXCEPTION_COUNTER, EXECUTION_TIMING = setup_prometheus_metrics(
    app,
    entrypoints_to_track=[
        ENTRYPOINT_TAKE_PHOTO,
        ENTRYPOINT_CAMERA_INFO
    ]
)


# ----- Interact with the Basler camera
def stop_camera_thread() -> bool:
    CAMERA_THREAD.stop()
    CAMERA_THREAD.join()
    # reset
    # CAMERA_THREAD = None
    return True


def start_camera_thread(
        camera,
        exposure_time_microseconds: int = 0
) -> bool:
    global CAMERA_THREAD

    CAMERA_THREAD = CameraThread(camera, dt_sleep=T_SLEEP)
    CAMERA_THREAD.start()
    # wait for first image
    sleep(max(((exposure_time_microseconds / 1e6 + 0.05), 0.1, T_SLEEP)))

    return True


def get_basler_camera(params: BaslerCameraParams) -> BaslerCamera:
    t1 = default_timer()

    flag_create_camera = False
    # "load" global variable
    global CAMERA

    if CAMERA is None:
        logger.debug("No camera object exists yet.")
        flag_create_camera = True
    elif isinstance(CAMERA, BaslerCamera):
        try:
            if not CAMERA:
                logger.debug("Camera not yet created and connected.")
                flag_create_camera = True
            elif any([vl != getattr(CAMERA, ky) for ky, vl in params.model_dump().items() if ky not in ["exposure_time", "exposure_time_microseconds"]]):
                changed_params = {
                    ky: (vl, getattr(CAMERA, ky))
                    for ky, vl in params.model_dump().items() if vl != getattr(CAMERA, ky)
                }
                logger.debug(f"Parameter(s) differ: {changed_params}")
                flag_create_camera = True
        except Exception as ex:
            logger.error(f"Retrieving the camera object failed with {ex}")
            flag_create_camera = True

    if flag_create_camera:
        # disconnect camera if existing
        if isinstance(CAMERA, BaslerCamera):
            CAMERA.disconnect()

        t2 = default_timer()
        # create new instance
        CAMERA = BaslerCamera(**params.model_dump())
        t3 = default_timer()
        logger.debug(f"Creating BaslerCamera object took {(t3 - t2) * 1000:.4g} ms")

        # create camera
        CAMERA.create_camera()
        t4 = default_timer()
        logger.debug(f"Creating a camera reference took {(t4 - t3) * 1000:.4g} ms")

        # Connect to the camera
        CAMERA.connect()
        t5 = default_timer()
        logger.debug(f"Connecting to camera took {(t5 - t4) * 1000:.4g} ms")

    return CAMERA


def get_test_image() -> Union[Path, None]:

    # get path to image or folder / name pattern
    image_path = default_from_env("TEST_IMAGE", "/home/app/test")
    logger.debug(f"Return test image: TEST_IMAGE={image_path}")

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
        logger.debug(f"List of images: {', '.join([el.as_posix() for el in images])}")
        # shuffle list
        shuffle(images)
        # return first image that exists
        for p2img in images:
            if p2img.is_file():
                logger.debug(f"Return image: {p2img.as_posix()}")
                return p2img
    return None


def process_input_variables(
        camera_params: BaslerCameraParams,
        image_params: ImageParams
):

    logger.debug(f"Process input variables: camera={camera_params}, image={image_params}")

    # # add functionality to emulate a camera
    # if camera_params.emulate_camera:
    #     camera_params.serial_number = None
    #     camera_params.ip_address = None

    if camera_params.ip_address:
        camera_params.ip_address = camera_params.ip_address.strip("'").strip('"')
    if camera_params.subnet_mask:
        camera_params.subnet_mask = camera_params.subnet_mask.strip("'").strip('"')

    if (camera_params.pixel_format == "Undefined") and PIXEL_FORMAT:
        camera_params.pixel_format = PIXEL_FORMAT

    image_format = image_params.format.strip(".")
    if image_format.lower() == "jpg":
        image_format = "jpeg"

    image_params.format = image_format
    return camera_params, image_params


def get_camera(
        camera_params: BaslerCameraParams,
        image_params: ImageParams
) -> BaslerCamera:

    # extract parameter for a CameraParameter object
    t0 = default_timer()
    cam_params = BaslerCameraParams(
        **{ky: getattr(camera_params, ky) for ky in BaslerCameraParams.model_fields}
    )
    cam = get_basler_camera(cam_params)

    if (camera_params.serial_number is None) and (camera_params.ip_address is None):
        p2img = get_test_image()

        if p2img is not None:
            # PNG images are required for pypylon on linux
            # convert image if it is the wrong format
            if p2img.suffix.lower() != ".png":
                # open image
                img = Image.open(p2img)
                # save as PNG
                p2img = Path("./testimage.png")
                img.save(p2img, format="PNG", quality=image_params.quality)

            # set test picture to camera
            cam.test_picture = p2img

    logger.debug(f"Getting camera object took {(default_timer() - t0) * 1000:.4g} ms")
    return cam


def take_picture(
        camera_params: BaslerCameraParams = Depends(),
        image_params: ImageParams = Depends(),
):
    logger.debug(f"take_picture({camera_params}, {image_params})")

    t0 = default_timer()
    t = [("start", default_timer())]
    camera_params, image_params = process_input_variables(camera_params, image_params)
    t.append(("process_input_variables()", default_timer()))

    cam = get_camera(camera_params, image_params)
    t.append(("get_camera()", default_timer()))

    t1 = default_timer()
    image_array = None
    if camera_params.acquisition_mode == "Continuous":
        # initialize control variable
        start_thread = False

        global CAMERA_THREAD
        if (CAMERA_THREAD is None) or \
                (isinstance(CAMERA_THREAD, CameraThread) and not CAMERA_THREAD.is_alive()):
            start_thread = True
        elif cam != CAMERA_THREAD.camera:
            logger.debug(f"Restart new camera thread ({cam})")
            start_thread = True
            # stop camera thread
            stop_camera_thread()

        if start_thread:
            logger.debug(f"Starting new camera thread with {cam}.")
            # start camera thread
            start_camera_thread(cam, camera_params.exposure_time_microseconds)

        # get image
        try:
            image_array, timestamp = CAMERA_THREAD.get_image()
        except TimeoutException as ex:
            stop_camera_thread()
            logger.error(f"TimeoutException: CAMERA_THREAD.get_image() at {cam} with {ex}")

    else:
        try:
            logger.debug(f"try cam.take_photo({camera_params.exposure_time_microseconds})")
            image_array = cam.take_photo(camera_params.exposure_time_microseconds)
        except TimeoutException as ex:
            cam.reconnect()
            logger.error(f"TimeoutException: cam.take_photo({camera_params.exposure_time_microseconds}) at {cam} with {ex}")
        except Exception as ex:
            cam.disconnect()
            logger.error(f"Exception: cam.take_photo({camera_params.exposure_time_microseconds}) at {cam} with {ex}")
    logger.debug(f"Taking a photo took {(default_timer() - t1) * 1000:.4g} ms")
    t.append(("take photo", default_timer()))

    if image_array is None:
        logger.error(f"No image was retrieved from camera: {cam}")
        raise HTTPException(400, "No image retrieved.")

    # save image to an in-memory bytes buffer
    im = Image.fromarray(image_array)
    logger.debug(f"Image.size: {im.size}")

    # crop image to region of interest (before rotating the image)
    if (image_params.roi_left > 0) or (image_params.roi_right != 1) or (image_params.roi_top > 0) or (image_params.roi_bottom != 0):
        dimensions = [image_params.roi_left, image_params.roi_top, image_params.roi_right, image_params.roi_bottom]
        sz = im.size * 2

        # to absolute dimensions
        dimensions_abs = [
            int(0 if d < 0 else d * s if d <= 1 else d)
            for d, s in zip(dimensions, sz)
        ]
        logger.debug(f"Cropping image to {dimensions_abs}.")
        im = im.crop(dimensions_abs)
        # add timing
        t.append(("Crop image", default_timer()))

    # rotate image
    if image_params.rotation_angle != 0:
        rotate_map = {
            90: Image.ROTATE_90,
            180: Image.ROTATE_180,
            270: Image.ROTATE_270
        }
        if image_params.rotation_angle in rotate_map:
            im = im.transpose(rotate_map[int(image_params.rotation_angle)])
        else:
            # general rotation
            im = im.rotate(angle=image_params.rotation_angle, expand=image_params.rotation_expand)

        logger.debug(f"Image.size (rotate={image_params.rotation_angle}, expand={image_params.rotation_expand}): {im.size}")
        # add timing
        t.append(("Rotate image", default_timer()))

    # image to bytes
    with io.BytesIO() as buf:
        im.save(buf, format=image_params.format, quality=image_params.quality)
        image_bytes = buf.getvalue()
    t.append(("Convert bytes to PIL image", default_timer()))

    diff = {t[i][0]: f"{(t[i][1] - t[i - 1][1]) * 1000:.4g} ms" for i in range(1, len(t))}
    logger.info(
        f"take_picture({camera_params}, {image_params}) took {(default_timer() - t0) * 1000:.4g} ms ({diff})."
    )

    return Response(
        content=image_bytes,
        media_type=f"image/{image_params.format}"
    )


# ----- define entrypoints
@app.get(ENTRYPOINT_TAKE_PHOTO)
@EXECUTION_TIMING[ENTRYPOINT_TAKE_PHOTO].time()
@EXCEPTION_COUNTER[ENTRYPOINT_TAKE_PHOTO].count_exceptions()
def take_photo(
        camera_params: BaslerCameraSettings = Depends(),
        image_params: ImageParams = Depends(),
        token = AccessToken
):
    camera_params_ = BaslerCameraParams(
        **get_not_none_values(camera_params),
    )
    # increment counter for /metrics endpoint
    EXECUTION_COUNTER[ENTRYPOINT_TAKE_PHOTO].inc()
    # function return
    return take_picture(camera_params_, image_params)


@app.get(ENTRYPOINT_CAMERA_INFO)
# @EXECUTION_TIMING[ENTRYPOINT_CAMERA_INFO].time()
# @EXCEPTION_COUNTER[ENTRYPOINT_CAMERA_INFO].count_exceptions()
def get_camera_info(
    camera_params: BaslerCameraAtom = Depends(),
    token = AccessToken
):
    with (EXECUTION_TIMING[ENTRYPOINT_CAMERA_INFO].time() and
          EXCEPTION_COUNTER[ENTRYPOINT_CAMERA_INFO].count_exceptions()):
        add_params = dict()
        global CAMERA
        if CAMERA is not None:
            add_params = {
                ky: getattr(CAMERA, ky) for ky in BaslerCameraParams.model_fields
                if ky not in BaslerCameraAtom.model_fields
            }

        cam = get_basler_camera(
            BaslerCameraParams(
                **camera_params.model_dump(),
                **add_params
            )
        )
    # increment counter for /metrics endpoint
    EXECUTION_COUNTER[ENTRYPOINT_CAMERA_INFO].inc()
    # function return
    return cam.get_camera_info()


@app.get(ENTRYPOINT_BASLER_CLOSE)
def close_cameras(token = AccessToken):
    global CAMERA
    if isinstance(CAMERA, BaslerCamera) and CAMERA.is_open:
        logger.debug("Camera was open.")
        CAMERA.disconnect()
        CAMERA = None

    global CAMERA_THREAD
    if isinstance(CAMERA, CameraThread) and CAMERA_THREAD.is_alive():
        logger.debug("Camera thread was open.")
        stop_camera_thread()
        # reset camera thread
        CAMERA_THREAD = None
    return True


# ----- TEST FUNCTIONS
@app.get(ENTRYPOINT_TEST_NEGATE)
def negate(boolean: bool, token = AccessToken):
    # global COUNTER
    EXECUTION_COUNTER[ENTRYPOINT_TEST_NEGATE].inc()
    return not boolean


@app.get(ENTRYPOINT_TEST_IMAGE)
def return_test_image(token = AccessToken):
    p2img = get_test_image()
    if isinstance(p2img, Path):
        return FileResponse(
            p2img.as_posix(),
            media_type=f"image/{p2img.suffix.strip('.')}"
        )
    else:
        # return None otherwise
        return None


# ---------- graceful stop
# Signal handler to ensure cleanup on kill signals
def signal_handler(signal, frame):
    logger.info("Signal received, closing camera.")
    close_cameras()


# Setup signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


if __name__ == "__main__":

    try:
        uvicorn.run(
            app=app,
            port=5050,
            host="0.0.0.0",
            access_log=True,
            log_config=None,  # Uses the logging configuration in the application
            ssl_keyfile=default_from_env("SSL_KEYFILE", None), # "server.key"
            ssl_certfile=default_from_env("SSL_CERTIFICATE", None),  # "server.crt"
        )
    except Exception as ex:
        close_cameras()
        raise ex
