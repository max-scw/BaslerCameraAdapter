# BaslerCameraAdapter

Provides a Python-based web-server REST API to connect to a Basler camera (using PyPylon)

It uses [*FastAPI*](https://fastapi.tiangolo.com/) to spin up a minimal web server that wraps the Python-package [pypylon](https://github.com/basler/pypylon) in a web-api.
(This again wraps the [*Pylon Camera Software Suite*](https://www2.baslerweb.com/en/downloads/software-downloads/) into a Python-package.)

The new sever can be packaged as a virtual (Docker) container. Find released images on [DockerHub](https://hub.docker.com) under https://hub.docker.com/r/maxscw/basler-camera-adapter.
The project also provides a frontend based on Python's [streamlit](https://streamlit.io/) (images are not published at docker hub.)

## Structure

The repository is structured as follows:
``` 
BaslerCameraAdapter
+-- docs <- auxiliary files for documentation (basically screenshots)
|-- app.py  <- streamlit server for the frontend
|-- BaslerCamera.py <- python code to interact with a Basler camera
|-- BaslerCameraAdapter.Dockerfile  <- Dockerfile for camera service (api)
|-- BaslerCameraThread.py  <- enables for continuous image acqusition by camera threading
|-- DataModels.py  <- pydantic data models
|-- docker-compose.yml  <- exemplatory docker-compose call
|-- Frontend.Dockerfile  <- Dockerfile for frontend
|-- LICENSE
|-- main.py  <- fastAPI server to communicate with the Basler camera
|-- README.md
|-- requirements.txt  <- pip requirements for api
|-- requirements_frontend.txt  <- pip requirements for frontend
|-- utils.py  <- helper functions that provide the ability to configure the server
|-- utils_fastapi.py <- wrapper functions that provide a standardized interface for fastapi
```

## Configuration

The default values to interact with a camera are configurable at startup by the following environment variables:

| Environment variable   | data type       | comment                                                              |
|------------------------|-----------------|----------------------------------------------------------------------|
| ACQUISITION_MODE       | string          | in ["SingleFrame", "Continuous"]                                     |
| CONVERT_TO_FORMAT      | string          | in ["RGB", "BGR", "Mono", "null"]                                    |
| DESTINATION_IP_ADDRESS | string          |                                                                      |
| DESTINATION_PORT       | integer         | in [0, 653535]                                                       |
| EXPOSURE_TIME          | integer         | > 500; in micro seconds                                              |
| FASTAPI_ROOT_PATH      | string          |                                                                      |
| FRAMES_PER_SECOND      | integer         | for continuous acquisition only                                      |
| IMAGE_FORMAT           | string          |                                                                      |
| IMAGE_QUALITY          | integer         | in [10, 100]; in percent                                             |
| IMAGE_ROI_LEFT         | integer / flot  | region of interest, left bound. In pixels or image fraction          |
| IMAGE_ROI_TOP          | integer / float | region of interest, upper bound. In pixels or image fraction         |
| IMAGE_ROI_RIGHT        | integer / float | region of interest, right bound. In pixels or image fraction         |
| IMAGE_ROI_BOTTOM       | integer / float | region of interest, lower bound. In pixels or image fraction         |
| IMAGE_ROTATION_ANGLE   | float           |                                                                      |
| IMAGE_ROTATION_EXPAND  | bool            |                                                                      |
| IP_ADDRESS             | string          |                                                                      |
| LOG_LEVEL              | string          | in ["DEBUG", "INFO", "WARNING", "ERROR", "FATAL"]                    |
| PIXEL_TYPE             | string          | see https://docs.baslerweb.com/pylonapi/net/T_Basler_Pylon_PixelType |
| PREFIX                 | string          | prefix of the environment variables                                  |
| SERIAL_NUMBER          | integer         |                                                                      |
| SSL_CERTIFICATE        | string          |                                                                      |
| SSL_KEYFILE            | string          |                                                                      |
| SUBNET_MASK            | string          |                                                                      |
| TEST_IMAGE             | string          | Path to image(s) that should be returned for emulated cameras        |
| TIMEOUT_MS             | integer         | > 200; in milli seconds                                              |
| TRANSMISSION_TYPE      | string          | in ["Unicast", "Multicast", "Broadcast"]                             |

Note: The configuration is done once when loading the data models (the module [DataModels.py](DataModels.py)), i.e. at startup of the uvicorn server.

## Usage

The default entrypoint (`/`) provides basic information but rather just assures that the server is up.

![BaslerCameraAdapter_DefaultEntrypoint.jpg](docs%2FBaslerCameraAdapter_DefaultEntrypoint.jpg)

See docs (endpoint `/docs`) for details. This endpoint is the charm of [*FastAPI*](https://fastapi.tiangolo.com/). 

![BaslerCameraAdapter_docs.jpg](docs%2FBaslerCameraAdapter_docs.jpg)

The documentation is automatically created with [Swagger](https://swagger.io/) and provides and overview of all available endpoints as well as the ability to try them out with a convenient interface.

![BaslerCameraAdapter_docs_take_photo.jpg](docs%2FBaslerCameraAdapter_docs_take_photo.jpg)

The frontend provides a nicer interface organizing the settings of the api in groups and offers the functionality to save images.

![BaslerCameraAdapter_Frontend1.jpg](docs%2FBaslerCameraAdapter_Frontend1.jpg)

### Installation

#### Python

````shell
python ./main.py
````
or use [uvicorn](https://www.uvicorn.org/) directly (always assuming that all package [requirements.txt](requirements.txt) are installed)
````shell
uvicorn main:app --host=0.0.0.0 --port=5051
````

For the frontend it is
````shell
streamlit run ./app.py
````

#### Docker

Use a virtualization engine like [docker](https://www.docker.com/) or [podman](https://podman.io/):

````shell
docker build --tag=camera-adapter -f BaslerCameraAdapter.Dockerfile .
````
or the corresponding compose plugins on the example file ([docker-compose.yml](docker-compose.yml)):

````shell
docker compose up -d
````

The docker-compose file starts the frontend, too.
See example file for configuration options via environment variables.

## Acknowledgments / Disclaimer

This project is no official project of [*Basler*](https://www.baslerweb.com).
It relies on the official [*pypylon*](https://pypi.org/project/pypylon/) package which is available under the [BSD 3-Clause License](https://github.com/basler/pypylon/blob/master/LICENSE).

## Author

 - max-scw

## Status

active