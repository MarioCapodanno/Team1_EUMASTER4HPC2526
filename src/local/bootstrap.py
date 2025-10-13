from fabric import Connection
from parser import parse
import time

def bootstrap(bootstrap_obj):
    """
    This function connects to the login node at the
    specified hostname via ssh and submits the
    bootstrap job.

    The bootstrap job is used to gather access to a computing
    node from which all the other operations will take place.
    """

    host = bootstrap_obj["host"]
    working_dir = bootstrap_obj["working_dir"]
    recipe_path = bootstrap_obj["recipe"]

    with Connection(host) as c:
        # Create bootstrap working dir if it doesn't exits yet
        c.run(f"mkdir -p {working_dir}", hide=True)

        # Copy bootstrap.sh file into this directory
        c.put("../scripts/bootstrap.sh", remote=f"{working_dir}/")
        # Copy the recipe.yml into this directoy
        c.put(recipe_path, remote=f"{working_dir}/")
        # TODO: Copy the server directory into this directoy

        # Execute bootstrap.sh and wait for the job to be ready
        res = c.run(f"sbatch {working_dir}/bootstrap.sh", hide=True).stdout.strip()
        jobid = res.split()[3]

        while True:
            res = c.run(f"squeue --jobs={jobid} | tail -n 1 | awk '{{print $6}}'", hide=True).stdout.strip()
            if res != "RUNNING":
                time.sleep(2)
            else:
                break

        # TODO: Here we should check that all the services are running before returning back to the caller
