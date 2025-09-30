#!/bin/bash -l

## This file is called `hello_sbatch.sh`
#SBATCH --time=00:05:00
#SBATCH --qos=default
#SBATCH --partition=cpu
#SBATCH --account=p200981     # Project code
#SBATCH --nodes=1
#SBATCH --ntasks=32
#SBATCH --ntasks-per-node=32

echo "Date = $(date)"
echo "Hostname = $(hostname -s)"
echo "Working directory = $(pwd)"

# Load the env
# module add
# source <path>/bin/activate

srun echo "hello"
