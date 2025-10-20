#!/bin/bash -l

#SBATCH --time=00:20:00
#SBATCH --qos=default
#SBATCH --partition=gpu
#SBATCH --account=p200981
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --ntasks-per-node=1

echo "Date              = $(date)"
echo "Hostname          = $(hostname -s)"
echo "Working Directory = $(pwd)"

# Load the environment
module add Apptainer

: "${OLLAMA_MODEL:=mistral}"

# Start ollama serve in background
echo "Starting ollama serve..."
apptainer exec --nv ollama_latest.sif ollama serve > ollama_serve.log 2>&1 &
SERVE_PID=$!
echo "ollama serve PID: ${SERVE_PID}"

# Wait until HTTP endpoint is ready
echo "Waiting for Ollama HTTP endpoint to become ready..."
for i in $(seq 1 120); do
	if curl -sS -m 2 -o /dev/null http://localhost:11434/api/version; then
		echo "Ollama is ready."
		break
	fi
	sleep 2
done

# Pull the requested model (best-effort; service will still run if this fails)
echo "Pulling model: ${OLLAMA_MODEL}"
apptainer exec --nv ollama_latest.sif ollama pull "${OLLAMA_MODEL}" || echo "Warning: model pull failed"

# Keep the job attached to the serve process
wait ${SERVE_PID}
