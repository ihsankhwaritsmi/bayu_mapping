#!/bin/bash

docker run -ti --rm \
  -v C:\Users\Administrator\Documents\bayu_mapping\odm\datasets/datasets:/datasets \
  opendronemap/odm \
  --project-path /datasets project \
  --fast-orthophoto \
  --orthophoto-resolution 20 \
  --resize-to 0 \
  --min-num-features 6000 \
  --skip-report

# Windows
docker run -ti --rm -v C:/Users/Administrator/Documents/bayu_mapping/odm/datasets:/datasets opendronemap/odm --project-path /datasets project3 --fast-orthophoto --orthophoto-resolution 20  --resize-to 0   --min-num-features 6000 --skip-report