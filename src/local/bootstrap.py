from fabric import Connection
from parser import parse
import time
from pathlib import Path

def bootstrap(bootstrap_obj):
    """
    Production-ready bootstrap function for HPC cluster deployment.
    Connects to the cluster and orchestrates the complete benchmark workflow.
    """
    debug = bootstrap_obj.get("debug", False)
    
    if debug:
        print("[DEBUG] Bootstrap function started")
    
    host = bootstrap_obj["host"]
    working_dir = bootstrap_obj["working_dir"]
    recipe_path = bootstrap_obj["recipe_path"]
    
    if debug:
        print(f"[DEBUG] Host: {host}, Working dir: {working_dir}, Recipe: {recipe_path}")

    try:
        with Connection(host) as c:
            if debug:
                print("[DEBUG] Connection established")
            
            # Create directory structure
            print(f"[SETUP] Setting up workspace on {host}...")
            c.run(f"mkdir -p {working_dir}", hide=True)
            c.run(f"mkdir -p {working_dir}/server", hide=True)
            c.run(f"mkdir -p {working_dir}/scripts", hide=True)
            c.run(f"mkdir -p {working_dir}/templates", hide=True)
            
            # Copy files to cluster
            print("[DEPLOY] Deploying benchmark components...")
            if debug:
                print("[DEBUG] Copying bootstrap.sh...")
            c.put("../../scripts/bootstrap.sh", remote=f"{working_dir}/")
            
            if debug:
                print("[DEBUG] Copying recipe.yml...")
            c.put(recipe_path, remote=f"{working_dir}/")
            
            # Copy server directory
            if debug:
                print("[DEBUG] Copying server directory...")
            server_dir = Path(__file__).parent.parent / "server"
            for py_file in server_dir.glob("*.py"):
                if debug:
                    print(f"[DEBUG] Copying {py_file.name}...")
                c.put(str(py_file), remote=f"{working_dir}/server/")
            
            # Copy supporting files
            if debug:
                print("[DEBUG] Copying parser.py...")
            c.put(str(Path(__file__).parent / "parser.py"), remote=f"{working_dir}/server/")
            c.put(recipe_path, remote=f"{working_dir}/server/")
            
            # Copy scripts and templates
            if debug:
                print("[DEBUG] Copying scripts and templates...")
            c.put("../../scripts/bootstrap.sh", remote=f"{working_dir}/scripts/")
            
            templates_dir = Path(__file__).parent.parent.parent / "templates"
            for template_file in templates_dir.glob("*.j2"):
                if debug:
                    print(f"[DEBUG] Copying template {template_file.name}...")
                c.put(str(template_file), remote=f"{working_dir}/templates/")
            
            print("[EXECUTE] Launching benchmark orchestrator on cluster...")
            result = c.run(
                f"cd {working_dir}/server && python3 runner.py",
                hide=False,
                warn=True
            )
            
            if result.return_code == 0:
                print("[SUCCESS] Benchmark completed successfully on cluster")
                return True
            else:
                print(f"[ERROR] Benchmark failed with return code {result.return_code}")
                if debug:
                    print(f"[DEBUG] Error output: {result.stderr}")
                return False
                
    except Exception as e:
        print(f"[ERROR] Bootstrap failed: {e}")
        if debug:
            import traceback
            traceback.print_exc()
        return False
