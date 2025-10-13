#!/bin/bash -l

#SBATCH --time=00:20:00
#SBATCH --qos=default
#SBATCH --partition=gpu
#SBATCH --account=p200981
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --ntasks-per-node=1

# Load the env
module add Apptainer

# Run the processing
apptainer pull docker://ollama/ollama
apptainer exec --nv ollama_latest.sif ollama serve
apptainer exec --nv ollama_latest.sif ollama pull mistral
