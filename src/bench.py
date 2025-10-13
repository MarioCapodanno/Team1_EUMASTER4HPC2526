import sys
from bootstrap import bootstrap
from parser import parse

if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("usage: bench recipe_file")
        sys.exit()

    recipe_file = sys.argv[1]

    print("[INFO] Parsing recipe file")
    recipe_obj = parse(recipe_file)

    bootstrap_obj = {
            "host": recipe_obj["bootstrap"]["host"],
            "working_dir": recipe_obj["bootstrap"]["working_dir"]
            }
    print("[INFO] Starting bootstrapping process")
    bootstrap(bootstrap_obj)
    print("[INFO] Server is ready")
