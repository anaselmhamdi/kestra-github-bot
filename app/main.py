import json
import logging
import os
import time
from datetime import datetime

import requests
import sseclient
from fastapi import FastAPI, Request
from github import Auth, Github, GithubIntegration
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

app = FastAPI()
logger = logging.getLogger(__name__)

APP_ID = os.environ["APP_ID"]
KESTRA_SERVICE_URL = os.environ["KESTRA_SERVICE_URL"]
KESTRA_WEBAPP_URL = os.environ["KESTRA_WEBAPP_URL"]
TIMEOUT = int(os.environ.get("CHECK_TIMEOUT", 600))

with open(os.path.normpath(os.path.expanduser("./bot-cert.pem")), "r") as cert_file:
    APP_CERT = cert_file.read()

# Create an GitHub integration instance
auth = Auth.AppAuth(APP_ID, APP_CERT)
git_integration = GithubIntegration(auth=auth)


def retry_session(
    retries=8,
    backoff_factor=2.0,
    status_forcelist=frozenset({413, 429, 500, 502, 503, 504}),
    session=None,
):
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        raise_on_redirect=False,
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter()
    adapter.max_retries = retry
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def follow_execution(execution_id):
    session = retry_session()
    stream_response = session.get(f"{KESTRA_SERVICE_URL}/api/v1/executions/{execution_id}/follow", stream=True)
    logger.info(f"Following execution {execution_id}")
    return stream_response


def build_logs(execution_id):
    session = retry_session()
    response = session.get(
        f"{KESTRA_SERVICE_URL}/api/v1/logs/{execution_id}", params={"minLevel": "INFO"}
    )
    main_log = response.json()[0]["message"]
    subflow_execution_id = main_log.split("with id")[-1].replace("'", "").strip()
    time.sleep(1)
    response = session.get(
        f"{KESTRA_SERVICE_URL}/api/v1/logs/{subflow_execution_id}",
        params={"minLevel": "INFO"},
    )
    logs = [main_log] + [log["message"] for log in response.json()]
    return "\n".join(logs)


@app.get("/health")
def health():
    return "ok"


@app.post("/")
async def bot(request: Request):
    session = retry_session()
    # Get the event payload
    payload = await request.json()

    if not payload.get("pull_request") and not payload.get("ref"):
        return "not a pull request or merge event"

    # Check if the event is pull request related
    if payload.get("pull_request") and payload["action"] in ["opened", "synchronize", "reopened"]:
        EVENT = "pull_request"
        logger.info(f"Received pull request event on branch: {payload['pull_request']['head']['ref']}")
    elif payload.get("ref") and payload.get("pusher") and payload["ref"] in ["refs/heads/main", "refs/heads/master"]:
        EVENT = "merge"
        logger.info(f"Received merge event on repo: {payload['repository']['name']}")
    else:
        return "not a relevant event"

    owner = payload["repository"]["owner"]["login"]
    repo_name = payload["repository"]["name"]

    ci_flow_name = f"ci-{repo_name}" if EVENT == "pull_request" else f"merge-{repo_name}"

    git_connection = Github(
        login_or_token=git_integration.get_access_token(
            git_integration.get_installation(owner, repo_name).id
        ).token
    )
    repo = git_connection.get_repo(f"{owner}/{repo_name}")

    # Call Kestra API to get the repo's CI flow (the name should be exactly ci-{repo_name})
    response = session.get(
        f"{KESTRA_SERVICE_URL}/api/v1/flows/search",
        params={"q": ci_flow_name, "page": 1, "size": 10},
    )
    logger.info(f"Search {ci_flow_name} flow response: {response.status_code}")

    if response.json()["total"] == 0:
        return f"No CI flow found for the {repo_name} repo."

    flow = response.json()["results"][0]
    flow_id = flow["id"]
    namespace = flow["namespace"]
    key = flow["triggers"][0]["key"]

    # Execute the flow
    response = session.post(
        f"{KESTRA_SERVICE_URL}/api/v1/executions/webhook/{namespace}/{flow_id}/{key}",
        json=payload,
    )
    logger.info(f"Execute flow response: {response.status_code}")
    if response.status_code != 200:
        return "Failure to execute Kestra flow"

    execution_id = response.json()["id"]

    # Create check runs for subflows
    subflows = [
        task["id"]
        for task in flow["tasks"]
        if task["type"] == "io.kestra.core.tasks.flows.Flow"
    ]
    subflow_runs = {}
    for subflow in subflows:
        check_run = repo.create_check_run(
            name=f"{subflow}",
            head_sha=payload["pull_request"]["head"]["sha"] if EVENT == "pull_request" else payload["after"],
            status="in_progress",
            started_at=datetime.now(),
            details_url=f"{KESTRA_WEBAPP_URL}/ui/executions/{namespace}/{flow_id}/{execution_id}/logs",
        )
        subflow_runs[subflow] = check_run
    logger.info("Created all subflow checks")

    # Listening to changes in the CI flow execution
    stream_response = follow_execution(execution_id)
    client = sseclient.SSEClient(stream_response)
    start_time = time.time()
    for event in client.events():
        execution_data = json.loads(event.data)
        logger.info(execution_data)
        main_flow_status = execution_data["state"]["current"]
        if main_flow_status == "CREATED":
            continue
        if main_flow_status == "RUNNING":
            for task in execution_data["taskRunList"]:
                if task["taskId"] in subflow_runs:
                    logger.info(task)
                    if task.get("attempts"):
                        subflow_status = task["attempts"][-1]["state"]["current"]
                    else:
                        subflow_status = task["state"]["current"]
                    if subflow_status in ["RUNNING", "CREATED"]:
                        logger.info(f"Subflow {task['taskId']} is still running")
                        continue
                    elif subflow_status == "SUCCESS":
                        logs = build_logs(task["executionId"])
                        subflow_runs[task["taskId"]].edit(
                            status="completed",
                            conclusion="success",
                            completed_at=datetime.now(),
                            output={
                                "title": task["taskId"],
                                "summary": f"```{logs}```"
                                if len(logs) < 65535
                                else f"```{logs[-60000:]}```",

                            },
                        )
                        logger.info(f"Subflow {task['taskId']} is completed")
                    elif subflow_status == "FAILED":
                        logs = build_logs(task["executionId"])
                        subflow_runs[task["taskId"]].edit(
                            status="completed",
                            conclusion="failure",
                            completed_at=datetime.now(),
                            output={
                                "title": task["taskId"],
                                "summary": f"```{logs}```"
                                if len(logs) < 65535
                                else f"```{logs[-60000:]}```",
                            },
                        )
                    else:
                        logger.info(f"Subflow {task['taskId']} is stale with status {subflow_status}")
                        logger.info(task)
                        logs = build_logs(task["executionId"])
                        subflow_runs[task["taskId"]].edit(
                            status="completed",
                            conclusion="failure",
                            completed_at=datetime.now(),
                            output={
                                "title": task["taskId"],
                                "summary": f"```{logs}```"
                                if len(logs) < 65535
                                else f"```{logs[-60000:]}```",
                            },
                        )

        # Check if the timeout is reached
        if time.time() - start_time > TIMEOUT:
            for task in execution_data["taskRunList"]:
                if task["taskId"] in subflow_runs:
                    subflow_runs[task["taskId"]].edit(
                        status="completed",
                        conclusion="timed_out",
                        completed_at=datetime.now(),
                    )
            break
    else:
        # Unknown failure, complete all subflows with failure
        logger.info(f"Main flow status {main_flow_status} is unhandled")
        for task_id in subflow_runs:
            logs = build_logs(execution_id)
            subflow_runs[task_id].edit(
                status="completed",
                conclusion="failure",
                completed_at=datetime.now(),
                output={
                    "title": task_id,
                    "summary": f"{flow_id} failed with unhandled status {main_flow_status}."
                }
            )

    return "success"
