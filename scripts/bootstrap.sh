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

set -euo pipefail

# Model and image parameters
: "${OLLAMA_MODEL:=mistral}"
: "${OLLAMA_IMAGE:=ollama_latest.sif}"

echo "Ensuring Apptainer image present: ${OLLAMA_IMAGE}"
if [ ! -f "${OLLAMA_IMAGE}" ]; then
	echo "Pulling Ollama Apptainer image..."
	apptainer pull -F "${OLLAMA_IMAGE}" docker://ollama/ollama
fi

# Start ollama serve in background, binding to all interfaces for remote clients
echo "Starting ollama serve (bind 0.0.0.0:11434)..."
export OLLAMA_HOST=0.0.0.0
export OLLAMA_TLS_SKIP_VERIFY=1
apptainer exec --nv --env OLLAMA_HOST=0.0.0.0 --env OLLAMA_TLS_SKIP_VERIFY=1 "${OLLAMA_IMAGE}" ollama serve > ollama_serve.log 2>&1 &
SERVE_PID=$!
echo "ollama serve PID: ${SERVE_PID}"

# Wait until HTTP endpoint is ready
echo "Waiting for Ollama HTTP endpoint to become ready..."
READY=0
for i in $(seq 1 180); do
	if curl -sS -m 2 -o /dev/null http://localhost:11434/api/version; then
		READY=1
		break
	fi
	sleep 2
done

if [ "${READY}" -ne 1 ]; then
	echo "Error: Ollama HTTP endpoint did not become ready in time" >&2
	# Exit to let Slurm mark this job as failed; runner will handle cleanup
	exit 1
fi
echo "Ollama HTTP server is ready."

# Pull the requested model synchronously so clients have it available
echo "Pulling model: ${OLLAMA_MODEL}"
echo "Note: Using OLLAMA_TLS_SKIP_VERIFY=1 to bypass certificate validation"

export OLLAMA_HOST=localhost:11434  # Local binding for pull command
MAX_PULL_ATTEMPTS=3  # Try a few times in case of transient issues
PULL_ATTEMPT=0

# Try to pull the model with TLS verification disabled
if apptainer exec --nv --env OLLAMA_HOST=localhost:11434 --env OLLAMA_TLS_SKIP_VERIFY=1 "${OLLAMA_IMAGE}" ollama pull "${OLLAMA_MODEL}" 2>&1 | tee /tmp/ollama_pull.log; then
	echo "✓ Model '${OLLAMA_MODEL}' is available"
else
	echo "⚠ Model pull failed"
	echo "Checking if model exists from previous runs..."
	
	# Check if model is already present in cache
	if apptainer exec --nv --env OLLAMA_HOST=localhost:11434 --env OLLAMA_TLS_SKIP_VERIFY=1 "${OLLAMA_IMAGE}" ollama list | grep -q "${OLLAMA_MODEL}"; then
		echo "✓ Model '${OLLAMA_MODEL}' found in cache"
	else
		echo "✗ Model '${OLLAMA_MODEL}' not available"
		echo "Service will continue but inference requests will return 404"
	fi
fi

echo "Bootstrap complete. Service ready on 0.0.0.0:11434"

# Keep the job attached to the serve process
wait ${SERVE_PID}
