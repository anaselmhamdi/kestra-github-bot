# kestra-github-bot

Source code for the Kestra bot Github app.
The app is meant to be deployed on a cluster serving Kestra.
The app listens to pull requests events and runs the `ci-{repo_name}` Kestra flow.
**The flow also needs to have a webhook trigger** for it to be run by the bot.
It runs checks for the whole flow and every subflow.

## Installation

- Create a Github App
- The scopes needed are checks (read/write), metadata (read), pull requests (read/write)
- Create a private key - it is used and loaded through the `bot-cert.pem` file
- Define a host to use for your webhook or use smee.io locally for testing
- Save the changes
- Install the app on your repository after deploying the app

## Building features

- Install smee `npm i -g smee-client`
- Go on smee.io and create a new channel
- Run `smee -u https://smee.io/your-channel -p PORT` where port is the port used by the Kestra bot
- Use the smee webhook as the webhook for your Github app installation
- Edit the files in the app/ folder to add your features
- Build your Docker and run it.

## Deployment

- Package the charts in the charts/ folder and deploy them on your cluster with Helm
