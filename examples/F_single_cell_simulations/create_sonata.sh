#!/bin/bash

# This script downloads the cADpyr e-model files from the AWS S3 bucket
# and saves them in a local directory called "components".
# It uses the AWS CLI to sync the files from the S3 bucket to the local directory.

# check if the directory exists
if [ ! -d "components" ]; then mkdir -p components; fi

# create subdirectories for mechanisms, hoc, and morphology files
mkdir -p components/mechanisms
mkdir -p components/hoc
mkdir -p components/morphology

# download cADpyr e-model files
# mechanisms
aws s3 sync --no-sign-request s3://openbluebrain/Model_Data/Electrophysiological_models/SSCx/OBP_SSCx/emodels/detailed/cADpyr/mechanisms components/mechanisms
# hoc and morphology file
aws s3 cp --no-sign-request s3://openbluebrain/Model_Data/Electrophysiological_models/SSCx/OBP_SSCx/emodels/detailed/cADpyr/model.hoc components/hoc/model.hoc
aws s3 cp --no-sign-request s3://openbluebrain/Model_Data/Electrophysiological_models/SSCx/OBP_SSCx/emodels/detailed/cADpyr/C060114A5.asc components/morphology/C060114A5.asc
# EModel json resource
aws s3 cp --no-sign-request s3://openbluebrain/Model_Data/Electrophysiological_models/SSCx/OBP_SSCx/emodels/detailed/cADpyr/EM__emodel=cADpyr__etype=cADpyr__mtype=L5_TPC_A__species=mouse__brain_region=grey__iteration=1372346__13.json components/

nrnivmodl components/mechanisms
python create_nodes_file.py