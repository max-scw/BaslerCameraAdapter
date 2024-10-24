import streamlit as st
import urllib.parse
import requests
from PIL import Image
from io import BytesIO
from pathlib import Path

from pydantic import BaseModel

import typing
from typing import Tuple

from DataModels import (
    CameraCommunication,
    CameraSettings,
    CameraImageAcquisition,
    ImageParamsFormat,
    ImageParamsProcessing
)
from utils import get_env_variable, setup_logging

# Setup logging
@st.cache_data
def get_logger():
    return setup_logging(__name__, "DEBUG")


def header(title: str, icon: str = None):
    # configure page => set favicon and page title
    st.set_page_config(page_title=title, page_icon=icon)  # https://emojipedia.org/

    # hide "made with Streamlit" text in footer
    hide_streamlit_style = """
                <style>
                #MainMenu {visibility: hidden;}
                footer {visibility: hidden;}
                </style>
                """
    st.markdown(hide_streamlit_style, unsafe_allow_html=True)


def get_st_config_from_pydantic_model(params: BaseModel) -> Tuple[str, dict]:
    for field_name, field in params.model_fields.items():

        expected_types = field.annotation
        # if hasattr(expected_type, "__args__"):
        #     expected_type.__args__
        if type(expected_types) in (typing._UnionGenericAlias, typing.Union):
            # strip
            expected_types = expected_types.__args__

        # ensure iterator object, i.e. tuple
        if not isinstance(expected_types, tuple):
            expected_types = (expected_types, )

        # mapping from pydantic fields to streamlit limits for numeric values
        field_map_num = {
            "gt": "min_value",  # gt - greater than
            "lt": "max_value",  # lt - less than
            "ge": "min_value",  # ge - greater than or equal to
            "le": "max_value",   # le - less than or equal to
            "multiple_of": "step",  # multiple_of - a multiple of the given number
            # "allow_inf_nan": None  # allow_inf_nan - allow 'inf', '-inf', 'nan' values
        }

        st_element_config = dict()
        for exp_type in expected_types:
            if isinstance(exp_type, type):
                new_type = exp_type
            elif isinstance(exp_type, typing._LiteralGenericAlias):
                new_type = exp_type
                # exp_type.__args__
            elif hasattr(exp_type, "__origin__"):
                new_type = exp_type.__origin__


            if "type" not in st_element_config:
                st_element_config["type"] = new_type
            elif (new_type is type(float)) and (st_element_config["type"] is int):
                # overwrite int with float
                st_element_config["type"] = float
            elif (new_type is type(str)) and (st_element_config["type"] is not None):
                st_element_config["type"] = str
            elif isinstance(new_type, typing._LiteralGenericAlias):
                st_element_config["type"] = new_type

            if new_type is type(None):
                st_element_config["value"] = None

            if hasattr(exp_type, "__metadata__"):  # isinstance(etp, typing._AnnotatedAlias):
                # annotation
                # __origin__, __args__, __metadata__
                # loop through metadata annotations
                for md in exp_type.__metadata__:
                    metadata = md.metadata
                    for el in metadata:
                        for ky, ky_st in field_map_num.items():
                            if hasattr(el, ky):
                                st_element_config[ky_st] = getattr(el, ky)

        if "type" not in st_element_config:
            st_element_config["type"] = None

        if (st_element_config["type"] is int) and ("step" not in st_element_config):
            st_element_config["step"] = 1

        if hasattr(field, "default"):
            st_element_config["value"] = field.default

        yield field_name, st_element_config


def create_st_elements_from_pydantic_model(model: BaseModel) -> dict:

    st_elements = dict()
    for field_name, config in get_st_config_from_pydantic_model(model):

        # strip underscore from names
        name = field_name.replace("_", " ")

        # get parameters for streamlit elements from config
        params = {ky: vl for ky, vl in config.items() if ky in ["value", "max_value", "min_value", "step"]}

        if config["type"] == bool:
            st_elements[field_name] = st.checkbox(name, **params)
        elif config["type"] == int:
            # force numeric values to be integer
            for ky, vl in params.items():
                if isinstance(vl, float):
                    params[ky] = int(vl)
            st_elements[field_name] = st.number_input(name, **params, format="%d")
        elif config["type"] == float:
            # force numeric values to be floats
            for ky, vl in params.items():
                if isinstance(vl, int):
                    params[ky] = float(vl)
            st_elements[field_name] = st.number_input(name, **params, format="%f")
        elif isinstance(config["type"], typing._LiteralGenericAlias):
            options = config["type"].__args__
            idx_default = options.index(params["value"]) if "value" in params else None
            st_elements[field_name] = st.selectbox(name, options, index=idx_default)
        else:
            st_elements[field_name] = st.text_input(name, **params)

    return st_elements


def main():
    header(title="Camera", icon=":camera:") # must be called as the first Streamlit command in your script.

    # Create a title for the app
    st.title("Camera API Frontend")

    logger = get_logger()

    # Create a form to input camera settings
    with st.form("camera_settings"):
        # Create two columns
        col1, col2 = st.columns(2)

        # Camera settings
        camera_settings_map = {
            "Camera Settings": CameraSettings,
            "Communication Settings": CameraCommunication,
            "Image Acquisition": CameraImageAcquisition,
        }
        with col1:
            for ky, vl in camera_settings_map.items():
                with st.expander(ky):
                    camera_settings_map[ky] = create_st_elements_from_pydantic_model(vl)

        # image settings
        image_settings_map = {
            "Image Format Settings": ImageParamsFormat,
            "Image Processing": ImageParamsProcessing,
        }
        with col2:
            for ky, vl in image_settings_map.items():
                with st.expander(ky):
                    image_settings_map[ky] = create_st_elements_from_pydantic_model(vl)

        # Create a submit button
        submitted = st.form_submit_button("Trigger", type="primary")

    # If the form is submitted, create a URL with the input values
    if submitted:
        # merge dictionaries
        list_of_dict_values = list((camera_settings_map | image_settings_map).values())
        params = {
            **list_of_dict_values[0],
            **list_of_dict_values[1],
            **list_of_dict_values[2],
            **list_of_dict_values[3],
            **list_of_dict_values[4]
        }
        # clean-up: filter by non None values
        params = {ky: vl for ky, vl in params.items() if vl is not None}

        # Encode the parameters into a URL
        address_backend = get_env_variable("ADDRESS_BACKEND", "http://localhost:5051/basler/single-frame-acquisition/take-photo", check_for_prefix=True)
        address_backend.strip("?")
        url = address_backend + "?" + urllib.parse.urlencode(params)
        logger.debug(f"Request camera API: {url}")
        print(url)

        # Display the URL
        if get_env_variable("SHOW_URL", True, check_for_prefix=True):
            st.write("URL to call backend:")
            st.code(url, language="bash")

        # Send a GET request to the URL
        timeout = get_env_variable("TIMEOUT", 2000, check_for_prefix=True)
        with st.spinner("Requesting backend ..."):
            response = requests.get(url, timeout=timeout)

            # Check if the response is successful
            if response.status_code == 200:
                # with st.form("response"):
                # Display the image
                image = Image.open(BytesIO(response.content))
                if "image" not in st.session_state:
                    st.session_state.image = image
                else:
                    st.session_state.image = image
                # show image
                st.image(image)
            else:
                # Display an error message
                st.error("Failed to retrieve image")

    # Create a text input for the filename
    filename = st.text_input("Enter a filename (without extension):")
    # Create a submit button
    save_image = st.button("Save Image", icon=":material/save:", disabled=not submitted)

    # Create a button to save the image
    if save_image:
        # Save the image to the local file system
        image_path = Path(get_env_variable("IMAGE_EXPORT_DIR", "/data", check_for_prefix=True)) / filename
        image_path = image_path.with_suffix(f".{image_settings_map['Image Format Settings']['format']}")
        logger.debug(f"Saving image to {image_path.as_posix()}")
        st.session_state.image.save(image_path)

        # Display a success message
        logger.info(f"Image saved to {filename}")
        st.success(f"Image saved successfully as '{image_path.name}'!")


if __name__ == "__main__":
    main()