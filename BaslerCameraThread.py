import threading

import numpy as np
from pypylon import pylon
from datetime import datetime
from time import sleep

from typing import Union, Tuple, Dict, Any, Literal

from BaslerCamera import BaslerCamera, get_image
from utils import setup_logging


# Setup logging
logger = setup_logging(__name__)


class CameraThread(threading.Thread):
    def __init__(
            self,
            cam: BaslerCamera,
            dt_sleep: float = 0.01,  # Set CPU to sleep to avoid excessive usage
            # timeout: int = 1000,  # milliseconds
            exposure_time_microseconds: int = None,
            max_retries: int = 3
    ):
        # threading.Thread.__init__(self)
        super().__init__()
        self._max_retries = max_retries
        self._backoff_factor = 5

        # store input variables
        self.camera = cam
        self.dt_sleep = dt_sleep if dt_sleep > 0 else 0.01
        # self.timeout = timeout if timeout > 500 else 500

        # threading
        # event object. This is more or less a flag
        self.exit_event = threading.Event()
        self.lock = threading.Lock()
        self._counter = 0

        self.camera.exposure_time = exposure_time_microseconds

        # local variables
        self.latest_image = None

        self.camera.open()

    def stop(self):
        """Stops the thread."""
        logger.info("Stopping camera thread.")
        self.exit_event.set()
        self.camera.close()

    @property
    def counter(self) -> int:
        """Accesses an internal integer variable that serves as counter."""
        return self._counter

    @counter.setter
    def counter(self, value: int) -> None:
        self._counter = value

    # local functions
    def run(self):
        """Continuously runs in the thread. Retrieves images from the Basler camera and stores them for later access."""
        # set camera to grabbing mode
        self.camera.start_grabbing(pylon.GrabStrategy_LatestImageOnly)
        logger.info("Start grabbing.")

        while not self.exit_event.is_set():
            self._counter += 1
            if self.camera.is_grabbing:
                grab_result = self._retrieve_result()

                if grab_result and grab_result.GrabSucceeded():
                    img = get_image(grab_result, self.camera.converter)

                    with self.lock:
                        timestamp = datetime.now()
                        self.latest_image = {"image": img, "timestamp": timestamp, "counter": self.counter}
                        logger.debug(f"Image set as latest image at {timestamp.isoformat()}.")
                grab_result.Release()
            sleep(self.dt_sleep)  # To avoid excessive CPU usage

    def _retrieve_result(self):
        """wrapper to implement a retry mechanism for timeouts"""
        retries = 0
        while retries < self._max_retries:
            try:
                # Simulating device data processing
                grab_result = self.camera.retrieve_result()
                logger.debug(f"Grab result succeeded: {grab_result.GrabSucceeded() if grab_result else None}.")

                break  # Exit the loop if successful
            except pylon.TimeoutException as e:  # TimeoutError
                retries += 1
                wait_time = 0.01 * self._backoff_factor * retries
                logger.warning(f"Timeout occurred: {e}. Retrying in {wait_time} seconds ...")
                sleep(wait_time)
        else:
            msg = "Max retries reached. Unable to retrieve grab result."
            logger.error(msg)
            self.stop()
            raise pylon.TimeoutException(msg)
        return grab_result

    def get_image_info(self) -> Union[Dict[str, Any], None]:
        """Returns basic information about the currently stored image"""
        return {
            "shape": self.latest_image['image'].shape,
            "timestamp": self.latest_image['timestamp'].isoformat(),
            "counter": self.latest_image['counter']
        } if isinstance(self.latest_image, dict) else None

    def get_latest_image(self) -> Tuple[Union[np.ndarray, None], Union[datetime, None]]:
        """Returns the currently stored image"""
        logger.debug(f"Getting latest image: {self.get_image_info()} ({self.counter}).")

        with self.lock:
            if self.latest_image is None:
                img, timestamp = None, None
            else:
                img = self.latest_image["image"]
                timestamp = self.latest_image["timestamp"]
        return img, timestamp

    def get_image(self, t_wait_min: float = 0.1):
        """Returns a new image"""
        logger.debug(f"Get image: {self.get_image_info()}.")

        # time to wait
        times = (self.dt_sleep, self.camera.exposure_time / 1e6)
        dt_min = max((min(times), t_wait_min))
        dt_max = max(times)

        n_max = int(dt_max // dt_min + 2)
        logger.debug(f"Times: {times}, min: {dt_min}, max: {dt_max} | {n_max}")

        counter = -1
        for i in range(n_max):
            if (counter < 0) and (self.latest_image is not None):
                counter = self.latest_image["counter"]

            sleep(dt_min)  # seconds

            if self.latest_image is not None:
                counter_new = self.latest_image["counter"]
                if counter != counter_new:
                    logger.debug(f"Most recent image: {self.get_image_info()}.")
                    return self.latest_image["image"], self.latest_image["timestamp"]

        logger.debug(f"No image found: {self.counter} ({i}).")
        return None, None
