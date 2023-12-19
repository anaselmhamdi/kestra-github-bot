FROM --platform=linux/amd64 python:3.10

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True

# Install Python dependencies.
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

# Set environment variables
ENV APP_ID 717113
ENV KESTRA_API_URL http://host.docker.internal:8080
ENV PORT 5000


ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ${APP_HOME}

CMD exec gunicorn --bind :$PORT --timeout 0 main:app

LABEL version=0.1.0
