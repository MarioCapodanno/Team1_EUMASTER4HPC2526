# TODO
from service_runner import service_runner
from client_runner import client_runner
from monitor_runner import monitor_runner

if __name__ == "__main__":
    # REQUIREMENTS:
    #  PRIMARY THING TO DO:
    #  1. Parse recipe.yml
    #  1. Start one or more service instances on compute nodes
    #      (The ones specified in the recipe.yml)
    #    1. Waits for the services to actually start
    #    1. Gather ip addresses of the services
    #    1. Gather jobids of the services
    ip_addresses, job_ids = service_runner()

    #  1. Start one or more client instances on compute nodes
    #    1. Waits for the clients to actually start
    #    1. Send ip addresses to these clients
    client_runner(ip_addresses)

    #  1. Start one or more monitor instances on compute nodes
    #    1. Waits for the monitors to actually start
    #    1. Send ip addresses to these monitors
    monitor_runner(ip_addresses, job_ids)

    #  SECONDARY THINGS:
    #  1. List currently active services
    #  1. Stop running services
