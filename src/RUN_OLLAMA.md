# RUN MISTRAL
To run mistral:
1. Run `sbatch ollama_sbatch.sh`
2. Get the name of the node on which the job is running with `squeue`
3. Run `cat request.txt | ssh <node_name> | jq ".response"`response
