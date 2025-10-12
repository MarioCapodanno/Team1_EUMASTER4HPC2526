from fabric import Connection

if __name__ == "__main__":
    # TODO: parse recipe.yml to get connection info
    host = "login.lxp.lu"
    user = "u103299"
    port = "8822"
    key_filename = "/home/giupy/.ssh/id_ed25519_mlux"

    c = Connection(host=host,
                   user=user,
                   port=port,
                   connect_kwargs={
                       "key_filename": key_filename 
                   })

    # create job
    result = c.run("cd ~")
