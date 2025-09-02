#!/bin/bash

# The first argument is expected to be the UPLOAD_DIR
UPLOAD_DIR="$1"

if [ -z "$UPLOAD_DIR" ]; then
  echo "Error: UPLOAD_DIR not provided as an argument."
  exit 1
fi

echo "Starting OpenDroneMap processing for images in: $UPLOAD_DIR"

docker run -ti --rm \
  -v "${UPLOAD_DIR}":/data \
  opendronemap/odm \
  --project-path /data/odm_project \
  --images /data \
  --fast-orthophoto \
  --skip-report

# Windows
# docker run -ti --rm -v C:/Users/Administrator/Documents/bayu_mapping/odm/datasets:/datasets opendronemap/odm --project-path /datasets project3 --fast-orthophoto --orthophoto-resolution 20  --resize-to 0   --min-num-features 6000 --skip-report
