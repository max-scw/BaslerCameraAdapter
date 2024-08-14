import fastapi
from fastapi import FastAPI
# from fastapi_offline import FastAPIOffline as FastAPI
from prometheus_client import make_asgi_app, Counter, Gauge
from datetime import datetime
# versions / info
import sys


from typing import Union, Tuple, List, Dict, Any


DATETIME_INIT = datetime.now()


def default_fastapi_setup(
        title: str = None,
        summary: str = None,
        description: str = None,
        license_info: Union[str, Dict[str, Any]] = None,
        contact: Union[str, Dict[str, Any]] = None,
):

    app = FastAPI(
        title=title,
        summary=summary,
        description=description,
        contact=contact,
        license_info=license_info
    )

    # ----- home
    @app.get("/")
    async def home():
        return {
            "Title": title,
            "Description": summary,
            "Help": "see /docs for help (automatic docs with Swagger UI).",
            "Software": {
                "fastAPI": fastapi.__version__,
                "Python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            },
            "License": license_info,
            "Impress": contact,
            "Startup date": DATETIME_INIT
        }

    return app


def setup_prometheus_metrics(
        app: FastAPI,
        entrypoints_to_track: list
) -> Tuple[Dict[str, Counter], Dict[str, Counter], Dict[str, Gauge]]:
    # set up /metrics endpoint for prometheus
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # set up custom metrics
    execution_counter, exception_counter, execution_timing = dict(), dict(), dict()
    for ep in entrypoints_to_track:
        name = ep.strip("/").replace("/", "_").replace("-", "")
        execution_counter[ep] = Counter(
            name=name,
            documentation=f"Counts how often the entry point {ep} is called."
        )
        exception_counter[ep] = Counter(
            name=name + "_exception",
            documentation=f"Counts how often the entry point {ep} raises an exception."
        )
        execution_timing[ep] = Gauge(
            name=name + "_execution_time",
            documentation=f"Latest execution time of the entry point {ep}."
        )
    return execution_counter, exception_counter, execution_timing
