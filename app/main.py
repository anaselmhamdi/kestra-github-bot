import logging
import os
import time
from datetime import datetime

import requests
from flask import Flask, request
from github import Github, GithubIntegration

app = Flask(__name__)


APP_ID = os.environ["APP_ID"]
KESTRA_SERVICE_URL = os.environ["KESTRA_SERVICE_URL"]
TIMEOUT = os.environ.get("CHECK_TIMEOUT", 600)

with open(
        os.path.normpath(os.path.expanduser('./bot-cert.pem')),
        'r'
) as cert_file:
    APP_CERT = cert_file.read()

# Create an GitHub integration instance
git_integration = GithubIntegration(
    APP_ID,
    APP_CERT,
)


def get_kestra_flow_execution(execution_id):
    response = requests.get(f"{KESTRA_SERVICE_URL}/api/v1/executions/{execution_id}")
    return response.json()


@app.route("/health", methods=['GET'])
def health():
    return "ok"


@app.route("/", methods=['POST'])
def bot():
    # Get the event payload
    payload = request.json

    # Check if the event is pull request related
    if "pull_request" not in payload:
        return "not a pull request"

    if payload['action'] not in ["opened", "synchronize", "reopened"]:
        return "not a relevant pull request action"

    owner = payload['repository']['owner']['login']
    repo_name = payload['repository']['name']
    app.logger.info(f"owner: {owner}, repo_name: {repo_name}, pull_request: {payload['pull_request']['head']['ref']}")
    git_connection = Github(
        login_or_token=git_integration.get_access_token(
            git_integration.get_installation(owner, repo_name).id
        ).token
    )
    repo = git_connection.get_repo(f"{owner}/{repo_name}")

    # Create check run
    main_check_run = repo.create_check_run(
        name="Kestra CI",
        head_sha=payload['pull_request']['head']['sha'],
        status="queued",
        started_at=datetime.now(),
    )

    # Call Kestra API to get the repo's CI flow (the name should be exactly ci-{repo_name})
    response = requests.get(f"{KESTRA_SERVICE_URL}/api/v1/flows/search", params={"q": f"ci-{repo_name}"})

    flow = response.json()['results'][0]
    flow_id = flow['id']
    namespace = flow['namespace']
    key = flow['triggers'][0]['key']

    # Execute the flow
    response = requests.post(
        f"{KESTRA_SERVICE_URL}/api/v1/executions/webhook/{namespace}/{flow_id}/{key}",
        json=payload
    )
    if response.status_code != 200:
        main_check_run.edit(
            name=f"Kestra flow {flow_id}: {flow['flowId']} ",
            status="error",
            conclusion="failure",
            completed_at=datetime.now(),
        )
        return "Failure to execute Kestra flow"

    execution_id = response.json()['id']
    main_check_run.edit(
        status="in_progress",
        details_url=f"{KESTRA_SERVICE_URL}/ui/executions/{namespace}/{flow_id}/{execution_id}/logs",
    )

    # Create check runs for subflows
    subflows = [task["id"] for task in flow['tasks'] if task["type"] == "io.kestra.core.tasks.flows.Flow"]
    subflow_runs = {}
    for subflow in subflows:
        check_run = repo.create_check_run(
            name=f"Running CI subflow {subflow}",
            head_sha=payload['pull_request']['head']['sha'],
            status="in_progress",
            started_at=datetime.now(),
            details_url=f"{KESTRA_SERVICE_URL}/ui/executions/{namespace}/{flow_id}/{execution_id}/logs"
        )
        subflow_runs[subflow] = check_run

    # Check and update status of CI Flow
    execution_data = get_kestra_flow_execution(execution_id)
    main_flow_status = execution_data['state']['current']
    start_time = time.time()
    while main_flow_status == "RUNNING":
        execution_data = get_kestra_flow_execution(execution_id)
        for task in execution_data["taskRunList"]:
            if task["taskId"] in subflow_runs:
                subflow_status = task["attempts"][-1]["state"]['current']
                if subflow_status == "RUNNING":
                    continue
                elif subflow_status == "SUCCESS":
                    subflow_runs[task['taskId']].edit(
                        status="completed",
                        conclusion="success",
                        completed_at=datetime.now(),
                    )
                else:
                    subflow_runs[task['taskId']].edit(
                        status="completed",
                        conclusion="failure",
                        completed_at=datetime.now(),
                    )
        execution_data = get_kestra_flow_execution(execution_id)
        main_flow_status = execution_data['state']['current']

        # Check if the timeout is reached
        if time.time() - start_time > TIMEOUT:
            main_check_run.edit(
                status="completed",
                conclusion="timed_out",
                completed_at=datetime.now(),
                output={"title": "Timeout reached", "summary": f"Timeout of {TIMEOUT} seconds reached. Exiting."}
            )
            return "failure"

    if main_flow_status == "SUCCESS":
        for task in execution_data["taskRunList"]:
            if task["taskId"] in subflow_runs:
                subflow_runs[task['taskId']].edit(
                    status="completed",
                    conclusion="success",
                    completed_at=datetime.now(),
                )

        main_check_run.edit(
            status="completed",
            conclusion="success",
            completed_at=datetime.now(),
        )
    else:
        main_check_run.edit(
            status="completed",
            conclusion="success",
            completed_at=datetime.now(),
        )
    return "success"


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
