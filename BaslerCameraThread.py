import threading

import numpy as np
from pypylon import pylon
import logging

from BaslerCamera import create_camera, get_image, set_exposure_time

from time import sleep


from typing import Union


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
        self.timeout = timeout if dt_sleep > 500 else 500

        # threading
        # event object. This is more or less a flag
        self.exit_event = threading.Event()
        self.lock = threading.Lock()

        self.set_exposure_time(exposure_time_microseconds)

        # local variables
        self.latest_image = None
        # process input
        if not self.camera.IsOpen():
            logging.info("Open camera.")
            self.camera.Open()

        # local functions
    def set_exposure_time(self, exposure_time_microseconds: int = None):
        # wrap function to local method
        if isinstance(exposure_time_microseconds, int) and exposure_time_microseconds > 100:
            set_exposure_time(self.camera, exposure_time_microseconds)

    def run(self):
        # set camera to grabbing mode
        self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
        logging.info("Start grabbing.")
        # build image converter
        converter = pylon.ImageFormatConverter()
        converter.OutputPixelFormat = self.pixel_type
        converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
        # Sets the alignment of the bits in the target pixel type if the target bit depth is greater than
        # the source bit depth, e.g., if you are converting from a 10-bit to a 16-bit format.

        while not self.exit_event.is_set():
            if self.camera.IsGrabbing():
                grab_result = self.camera.RetrieveResult(self.timeout, pylon.TimeoutHandling_ThrowException)
                logging.debug(f"Grab result succeeded: {grab_result.GrabSucceeded()}.")

                if grab_result.GrabSucceeded():
                    image = converter.Convert(grab_result)
                    img = image.GetArray()

                    logging.debug(f"Grabbed image: {img.shape}")
                    with self.lock:
                        self.latest_image = img
                grab_result.Release()
            sleep(self.dt_sleep)  # To avoid excessive CPU usage

    def stop(self):
        logging.info("Stopping camera.")
        self.exit_event.set()
        self.camera.StopGrabbing()
        self.camera.Close()

    def get_latest_image(self) -> Union[np.ndarray, None]:
        logging.debug(f"Getting latest image.")
        with self.lock:
            return self.latest_image
