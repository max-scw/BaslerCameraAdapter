from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
import uvicorn
from prometheus_fastapi_instrumentator import Instrumentator

from pathlib import Path
from random import shuffle
import io
from imageio import v3 as iio
from PIL import Image
import cv2
# versions / info
import fastapi
import sys

# logging / timing
from timeit import default_timer
from datetime import datetime
import logging

# custom packages
from BaslerCamera import BaslerCamera
from utils_env_vars import get_env_variable


ENTRYPOINT_TEST = "/test"
ENTRYPOINT_TEST_IMAGE = ENTRYPOINT_TEST + "/image"

ENTRYPOINT_BASLER = "/basler"
ENTRYPOINT_TAKE_PHOTO = ENTRYPOINT_BASLER + "/take-photo"
ENTRYPOINT_CAMERA_INFO = ENTRYPOINT_BASLER + "/get-camera-info"


PATH_TO_TEMPORARY_FILES = Path("tmp")
MAX_NUM_TEMP_FILES = get_env_variable("MAX_NUM_TEMP_FILES", 10)

if not PATH_TO_TEMPORARY_FILES.exists():
    print(f"Creating folder {PATH_TO_TEMPORARY_FILES.as_posix()}.")
    PATH_TO_TEMPORARY_FILES.mkdir()

app = FastAPI()
app.mount("/temporary", StaticFiles(directory=PATH_TO_TEMPORARY_FILES), name="static")
PATH_TO_TEMPORARY_FILES.mkdir(exist_ok=True)
# create endpoint for prometheus
Instrumentator().instrument(app).expose(app)  # produces a False in the console every time a valid entrypoint is called


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
        # create new instance
        CAMERA = BaslerCamera(**kwargs)
        # Connect to the camera
        CAMERA.connect()
    return CAMERA


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
    # elements = {ky: val for ky, val in kwargs.items() if val}
    cam = create_camera(**kwargs)

    t0 = default_timer()
    image_array = cam.take_photo(exposure_time_microseconds)
    with io.BytesIO() as buf:
        iio.imwrite(buf, image_array, plugin="pillow", format="bmp")
        image_bytes = buf.getvalue()

    # save image to an in-memory bytes buffer
    im = Image.fromarray(image_array)
    with io.BytesIO() as buf:
        im.save(buf, format='bmp')
        image_bytes = buf.getvalue()

    success, im = cv2.imencode('.bmp', image_array)
    image_bytes = im.tobytes()


    # except ValueError as ve:
    #     raise HTTPException(status_code=449, detail=ve.args)
    dt = default_timer() - t0
    msg = f"Taking a photo took {dt} seconds. take_photo({kwargs})"
    logging.debug(msg)
    print(msg)

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
def return_test_image(
        exposure_time_microseconds: int = None,
        serial_number: int = None,
        ip_address: str = None,
        emulate_camera: bool = False,
        timeout: int = None,
        transmission_type: str = None,
        destination_ip_address: str = None,
        destination_port: int = None,
):
    # load file
    image_path = get_env_variable("TEST_IMAGE", None)
    if image_path:
        image_path = Path(image_path)
        images = list(image_path.parent.glob(image_path.name))
        # shuffle list
        shuffle(images)
        # return first image that exists
        for p2img in images:
            if p2img.is_file():
                return FileResponse(
                    p2img.as_posix(),
                    media_type=f"image/{p2img.suffix.strip('.')}"
                )
    # return None otherwise
    return None


if __name__ == "__main__":
    uvicorn.run(app=app, port=5051)
