from fabric import Connection
from parser import parse

def bootstrap(bootstrap_obj):
    """
    This function connects to the login node at the
    specified hostname via ssh and submits the
    bootstrap job.

    The boostrap job is used to gather access to a computing
    node from which all the other operations will take place.
    """

    host = bootstrap_obj["host"]
    working_dir = bootstrap_obj["working_dir"]

    with Connection(host) as c:
        # Create bootstrap working dir if it doesn't exits yet
        c.run(f"mkdir -p {working_dir}")

        # Copy boostrap.sh file into this directory
        c.put("../scripts/bootstrap.sh", remote=f"{working_dir}/")

        # Execute it and wait for the job to be ready
        # TODO
