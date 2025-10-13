import yaml

# TODO: validate file
def parse(path):
    with open(path, "r") as file:
        return yaml.safe_load(file)
