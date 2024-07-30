import threading

import numpy as np
from pypylon import pylon
import logging
from datetime import datetime

from BaslerCamera import create_camera, get_image, set_exposure_time, get_image

from time import sleep

from typing import Union, Tuple, Dict, Any


class CameraThread(threading.Thread):
    def __init__(
            self,
            cam: pylon.InstantCamera,
            pixel_type: int = pylon.PixelType_Undefined,
            dt_sleep: float = 0.01,  # Set CPU to sleep to avoid excessive usage
            timeout: int = 1000,  # milli seconds
            exposure_time_microseconds: int = None
    ):
        # threading.Thread.__init__(self)
        super().__init__()

        # store input variables
        self.camera = cam
        self.pixel_type = pixel_type
        self.dt_sleep = dt_sleep if dt_sleep > 0 else 0.01
        self.timeout = timeout if timeout > 500 else 500

        # threading
        # event object. This is more or less a flag
        self.exit_event = threading.Event()
        self.lock = threading.Lock()
        self._counter = 0

        self.set_exposure_time(exposure_time_microseconds)

        # local variables
        self.latest_image = None
        # build image converter
        if self.pixel_type == pylon.PixelType_Undefined:
            converter = None
        else:
            converter = pylon.ImageFormatConverter()
            converter.OutputPixelFormat = self.pixel_type
            converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
            # Sets the alignment of the bits in the target pixel type if the target bit depth is greater than
            # the source bit depth, e.g., if you are converting from a 10-bit to a 16-bit format.

        self.converter = converter

        # process input
        if not self.camera.IsOpen():
            logging.info("Open camera.")
            self.camera.Open()

    @property
    def counter(self) -> int:
        return self._counter

        # local functions
    def set_exposure_time(self, exposure_time_microseconds: int = None):
        # wrap function to local method
        if isinstance(exposure_time_microseconds, int) and exposure_time_microseconds > 100:
            set_exposure_time(self.camera, exposure_time_microseconds)

    def run(self):
        # set camera to grabbing mode
        self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
        logging.info("Start grabbing.")

        while not self.exit_event.is_set():
            self._counter += 1
            if self.camera.IsGrabbing():
                grab_result = self.camera.RetrieveResult(self.timeout, pylon.TimeoutHandling_ThrowException)
                logging.debug(f"Grab result succeeded: {grab_result.GrabSucceeded() if grab_result else None}.")

                if grab_result and grab_result.GrabSucceeded():
                    img = get_image(grab_result, self.converter)

                    logging.debug(f"Grabbed image: {img.shape}, type: {type(img)}")
                    with self.lock:
                        timestamp = datetime.now()
                        self.latest_image = {"image": img, "timestamp": timestamp, "counter": self.counter}
                        logging.debug(f"Image set as latest image at {timestamp.isoformat()}.")
                grab_result.Release()
            sleep(self.dt_sleep)  # To avoid excessive CPU usage

    def stop(self):
        logging.info("Stopping camera.")
        self.exit_event.set()
        self.camera.StopGrabbing()
        self.camera.Close()

    def get_image_info(self) -> Union[Dict[str, Any], None]:
        return {
            "shape": self.latest_image['image'].shape,
            "timestamp": self.latest_image['timestamp'].isoformat(),
            "counter": self.latest_image['counter']
        } if isinstance(self.latest_image, dict) else None

    def get_latest_image(self) -> Tuple[Union[np.ndarray, None], Union[datetime, None]]:
        logging.debug(f"Getting latest image: {self.get_image_info()} ({self.counter}).")

        with self.lock:
            if self.latest_image is None:
                img, timestamp = None, None
            else:
                img = self.latest_image["image"]
                timestamp = self.latest_image["timestamp"]
            return img, timestamp

    def get_image(self, t_wait_min: float = 0.1):
        logging.debug(f"Get image: {self.get_image_info()}.")

        # time to wait
        times = (self.dt_sleep, self.camera.ExposureTimeAbs.GetValue() / 1e6)
        dt_min = max((min(times), t_wait_min))
        dt_max = max(times)

        n_max = int(dt_max // dt_min + 2)
        logging.debug(f"Times: {times}, min: {dt_min}, max: {dt_max} | {n_max}")

        counter = -1
        for i in range(n_max):
            if (counter < 0) and (self.latest_image is not None):
                counter = self.latest_image["counter"]

            sleep(dt_min)  # seconds

            if self.latest_image is not None:
                counter_new = self.latest_image["counter"]
                if counter != counter_new:
                    logging.debug(f"Most recent image: {self.get_image_info()}.")
                    return self.latest_image["image"]

        logging.debug(f"No image found: {self.counter} ({i}).")
        return None


class TestThread(threading.Thread):
    def __init__(
            self,
            dt_sleep: float = 0.01,  # Set CPU to sleep to avoid excessive usage
    ):
        # threading.Thread.__init__(self)
        super().__init__()

        self.dt_sleep = dt_sleep if dt_sleep > 0 else 0.01

        # threading
        # event object. This is more or less a flag
        self.exit_event = threading.Event()
        self.lock = threading.Lock()
        self._counter = 0

    def run(self):
        while not self.exit_event.is_set():
            self._counter += 1
            sleep(self.dt_sleep)  # To avoid excessive CPU usage

    def stop(self):
        logging.info("Stopping.")
        self.exit_event.set()

    def get_counter(self) -> int:
        return self._counter
