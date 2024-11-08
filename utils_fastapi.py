import fastapi
from fastapi import FastAPI
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# from fastapi_offline import FastAPIOffline as FastAPI
from prometheus_client import make_asgi_app, Counter, Gauge
from datetime import datetime
# versions / info
import sys

from utils import get_env_variable, set_env_variable


from typing import Union, Tuple, List, Dict, Any, Optional


DATETIME_INIT = datetime.now()
# List of correct access tokens
# set_env_variable("ACCESS_TOKENS", "SDFjgsrfoja30uawpfkSDFJSLdof2")
ACCESS_TOKENS = get_env_variable("ACCESS_TOKENS", [])
ACCESS_TOKENS = [ACCESS_TOKENS] if isinstance(ACCESS_TOKENS, str) else ACCESS_TOKENS

# Create a security scheme for checking access tokens
security_scheme = HTTPBearer()

# Function to check access tokens
def check_access_token(token: HTTPAuthorizationCredentials = Depends(security_scheme)):
    print("check_access_token")
    if len(ACCESS_TOKENS) >= 0:
        print(f"Token={token.credentials} in {ACCESS_TOKENS}")
        if token.credentials not in ACCESS_TOKENS:
            raise HTTPException(status_code=401, detail="Invalid access token")
        return token.credentials
    # else:
    #     return True

AccessToken: Optional[HTTPAuthorizationCredentials] = Depends(check_access_token) if ACCESS_TOKENS else None


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
    )

    # ----- home
    @app.get("/")
    async def home(token: HTTPAuthorizationCredentials = AccessToken):
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

    # ----- SWAGGER
    if ACCESS_TOKENS:
        # Create a router for the Swagger endpoint
        from fastapi.openapi.docs import get_swagger_ui_html
        from fastapi.openapi.utils import get_openapi
        @app.get("/docs", dependencies=[AccessToken])
        async def get_docs():
            return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{title} docs")

        @app.get("/openapi.json", dependencies=[AccessToken])
        async def get_openapi():
            return get_openapi(routes=app.routes)

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


