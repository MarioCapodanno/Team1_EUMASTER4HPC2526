import yaml

# TODO: validate file
def parse(path):
    """
    This function parses and validates the provided .yml file
    """
    with open(path, "r") as file:
        return yaml.safe_load(file)
