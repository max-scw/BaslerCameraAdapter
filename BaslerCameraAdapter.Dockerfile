# syntax=docker/dockerfile:1

# Base Image
FROM python:3.11-slim-bullseye

# Metadata
LABEL author=scw-max
LABEL project=https://github.com/max-scw/BaslerCameraAdapter
LABEL version=2024.4.18

# Environment variables (default values)
ENV LOGFILE=BaslerCameraAdapter

ARG DEBIAN_FRONTEND=noninteractived

# add white-listed websites
RUN printf "deb https://deb.debian.org/debian bullseye main \
            deb https://security.debian.org/debian-security bullseye-security main \
            deb https://deb.debian.org/debian bullseye-updates main" > /etc/apt/sources.list

# new default user
RUN useradd -ms /bin/bash app
# Set the working directory
WORKDIR /home/app


# Install requirements
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt --no-cache-dir

# Copy app into the container
COPY main.py DataModels.py BaslerCamera.py utils_env_vars.py README.md LICENSE ./


# set to non-root user
USER root
RUN chown -R app:app /home/app
USER app

EXPOSE 5050

# FOR DEBUGGING
#ENTRYPOINT ["tail", "-f", "/dev/null"]
ENTRYPOINT ["uvicorn", "main:app", "--host=0.0.0.0", "--port=5050"]
