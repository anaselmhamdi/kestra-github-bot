FROM --platform=linux/amd64 python:3.10

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True

# Install Python dependencies.
COPY requirements.txt requirements.txt
COPY log-conf.yml log-conf.yml
RUN pip install -r requirements.txt

# Set environment variables
ENV APP_ID 855421
ENV KESTRA_SERVICE_URL http://host.docker.internal:8080
ENV KESTRA_WEBAPP_URL https://prod.kestra.core-ops.net
ENV PORT 5000
ENV CHECK_TIMEOUT 600


ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ${APP_HOME}

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT} --timeout-keep-alive 1000 --timeout-graceful-shutdown ${CHECK_TIMEOUT} --log-level debug --log-config=log-conf.yml
LABEL version=0.3.24
