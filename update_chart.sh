#!/bin/bash

# Check if the correct number of arguments is provided
if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <folder_path> <version>"
  exit 1
fi

# Assign arguments to variables
folder_path="charts/"
version="$1"

# Navigate to the specified folder
cd "$folder_path"
helm dependency build
helm package .
helm repo index . --url https://core-ops-charts.storage.googleapis.com/kestra-github-bot
mkdir packaged_chart
mv "kestra-github-bot"-$version.tgz packaged_chart
mv index.yaml packaged_chart
gsutil rsync -r packaged_chart gs://core-ops-charts/kestra-github-bot
rm -rf packaged_chart
