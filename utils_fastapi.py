import fastapi
from fastapi import FastAPI
from fastapi import HTTPException, Depends, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.openapi.docs import get_swagger_ui_html
# from fastapi_offline import FastAPIOffline as FastAPI
from prometheus_client import make_asgi_app, Counter, Gauge, generate_latest
from datetime import datetime
# versions / info
import sys

from utils import get_env_variable, set_env_variable


from typing import Union, Tuple, List, Dict, Any, Optional


DATETIME_INIT = datetime.now()
# List of correct access tokens
ACCESS_TOKENS = get_env_variable("ACCESS_TOKENS", [])
ACCESS_TOKENS = [ACCESS_TOKENS] if isinstance(ACCESS_TOKENS, str) else ACCESS_TOKENS

# Create a security scheme for checking access tokens
security_scheme = HTTPBearer()

# Function to check access tokens
async def check_access_token(token: Optional[str] = None):
    if (len(ACCESS_TOKENS) > 0) and (token not in ACCESS_TOKENS):
            raise HTTPException(status_code=401, detail="Invalid access token")


AccessToken: Optional[str] = Depends(check_access_token)


def default_fastapi_setup(
        title: str = None,
        summary: str = None,
        description: str = None,
        license_info: Union[str, Dict[str, Any]] = None,
        contact: Union[str, Dict[str, Any]] = None,
        lifespan=None,
):

    app = FastAPI(
        title=title,
        summary=summary,
        description=description,
        contact=contact,
        license_info=license_info,
        lifespan=lifespan,
        docs_url=None
    )

    # ----- home
    @app.get("/")
    async def home(token = AccessToken):
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

    @app.get("/health")
    async def health_check(token = AccessToken):
        return {"status": "ok"}

    # ----- SWAGGER
    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui(token = AccessToken):
        # Here you can implement logic to validate or use the token as needed
        return get_swagger_ui_html(openapi_url=app.openapi_url, title="Swagger UI")

    return app


def setup_prometheus_metrics(
        app: FastAPI,
        entrypoints_to_track: list
) -> Tuple[Dict[str, Counter], Dict[str, Counter], Dict[str, Gauge]]:
    # set up /metrics endpoint for prometheus
    # metrics_app = make_asgi_app()
    # app.mount("/metrics", metrics_app)
    @app.get("/metrics")
    async def metrics(token = AccessToken):
        return Response(generate_latest(), media_type="text/plain")

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


