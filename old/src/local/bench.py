import sys
from bootstrap import bootstrap
from parser import parse

if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("usage: bench recipe_file")
        sys.exit()
    recipe_path = sys.argv[1]

    print("[INFO] Parsing recipe file")
    recipe_obj = parse(recipe_path)

    print("[INFO] Starting bootstrapping process")
    bootstrap_obj = {
            "host": recipe_obj["bootstrap"]["host"],
            "working_dir": recipe_obj["bootstrap"]["working_dir"],
            "recipe_path": recipe_path
            }
    bootstrap(bootstrap_obj)

    # ...
