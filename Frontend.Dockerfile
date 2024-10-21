# syntax=docker/dockerfile:1

# Base Image
FROM python:3.11-slim-bullseye as base
ENV PYTHONUNBUFFERED 1

# Metadata
LABEL author=max-scw
LABEL project=https://github.com/max-scw/BaslerCameraAdapter
LABEL version=2024.10.21

# Environment variables (default values)
ARG DEBIAN_FRONTEND=noninteractived

RUN printf "deb https://deb.debian.org/debian bullseye main \
            deb https://security.debian.org/debian-security bullseye-security main \
            deb https://deb.debian.org/debian bullseye-updates main" > /etc/apt/sources.list


# new default user
RUN useradd -ms /bin/bash appuser
# Set the working directory
WORKDIR /home/app

# Install requirements
COPY requirements_frontend.txt ./requirements.txt
RUN pip install -r requirements.txt --no-cache-dir

# Copy app into the container
# 1. copy shated files
COPY utils.py \
     DataModels.py \
     README.md \
     LICENSE \
     ./
# 2. copy individual files
COPY app.py ./

# Expose the ports
EXPOSE 8501

# Define the health check using curl for both HTTP and HTTPS
HEALTHCHECK --interval=30s --timeout=5s \
  CMD (curl -fsk http://localhost:8501/_stcore/health) || (curl -fsk https://localhost:8501/_stcore/health) || exit 1

# set to non-root user
USER root
RUN chown -R appuser:appuser /home/app
USER appuser

# Set the entrypoint script as the entrypoint for the container
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
#CMD ["tail", "-f", "/dev/null"]

