# kestra-github-bot

Source code for the Kestra bot Github app.
The app is meant to be deployed on a cluster serving Kestra.
The app listens to pull requests events and runs the `ci-{repo_name}` Kestra flow.
It runs checks for the whole flow and every subflow.

## Installation

- Create a Github App
- The scopes needed are checks (read/write), metadata (read), pull requests (read/write)
- Create a private key - it is used and loaded through the `bot-cert.pem` file
- Define a host to use for your webhook or use smee.io locally for testing
- Save the changes
- Install the app on your repository after deploying the app
