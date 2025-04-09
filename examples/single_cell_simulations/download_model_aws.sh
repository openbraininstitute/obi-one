#!/bin/bash

# This script downloads the cADpyr e-model files from the AWS S3 bucket
# and saves them in a local directory called "cadpyr_emodel".
# It uses the AWS CLI to sync the files from the S3 bucket to the local directory.

# check if the directory exists
if [ ! -d "cadpyr_emodel" ]; then mkdir cadpyr_emodel; fi 

#download cADpyr e-model files
# mechanisms
aws s3 sync --no-sign-request s3://openbluebrain/Model_Data/Electrophysiological_models/SSCx/OBP_SSCx/emodels/detailed/cADpyr/mechanisms ./cadpyr_emodel/mechanisms 
# hoc and morphology file 
aws s3 cp --no-sign-request s3://openbluebrain/Model_Data/Electrophysiological_models/SSCx/OBP_SSCx/emodels/detailed/cADpyr/model.hoc ./cadpyr_emodel/model.hoc
aws s3 cp --no-sign-request s3://openbluebrain/Model_Data/Electrophysiological_models/SSCx/OBP_SSCx/emodels/detailed/cADpyr/C060114A5.asc ./cadpyr_emodel/C060114A5.asc
# EModel json resource
aws s3 cp --no-sign-request s3://openbluebrain/Model_Data/Electrophysiological_models/SSCx/OBP_SSCx/emodels/detailed/cADpyr/EM__emodel=cADpyr__etype=cADpyr__mtype=L5_TPC_A__species=mouse__brain_region=grey__iteration=1372346__13.json ./cadpyr_emodel/