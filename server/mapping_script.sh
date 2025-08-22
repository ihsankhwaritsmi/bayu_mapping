#!/bin/bash

#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

docker run -ti --rm \
  -v "${SCRIPT_DIR}/datasets":/datasets \
  opendronemap/odm \
  --project-path /datasets project \
  --fast-orthophoto \
  --skip-report

# Windows
# docker run -ti --rm -v C:/Users/Administrator/Documents/bayu_mapping/odm/datasets:/datasets opendronemap/odm --project-path /datasets project3 --fast-orthophoto --orthophoto-resolution 20  --resize-to 0   --min-num-features 6000 --skip-report
