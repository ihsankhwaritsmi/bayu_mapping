#!/bin/bash

sudo docker run -ti --rm -v /home/ubuntu/datasets:/datasets opendronemap/odm \
  --project-path /datasets project \
  --fast-orthophoto \
  --orthophoto-resolution 20 \
  --resize-to \
  --min-num-features 6000 \
  --skip-report
