import os
from pathlib import Path
import subprocess

def read_env_file(env_path='.env'):
    """Read key-value pairs from .env file."""
    env_vars = {}
    if not Path(env_path).exists():
        raise FileNotFoundError(f"Environment file {env_path} not found")
        
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip()
    return env_vars

def build_docker_command(image_name, env_vars, port_mapping):
    """Build docker run command with environment variables."""
    env_flags = ' '.join(f'-e {key}={value}' for key, value in env_vars.items())
    return f"docker run {env_flags} {port_mapping} {image_name}"

def main():
    # Configuration
    IMAGE_NAME = "ttv-ai-clipper"
    PORT_MAPPING = "-p 80:80"
    ENV_FILE = '.env'
    
    try:
        # Read environment variables
        env_vars = read_env_file(ENV_FILE)
        
        # Build the docker command
        docker_cmd = build_docker_command(IMAGE_NAME, env_vars, PORT_MAPPING)
        
        # Print the command for verification
        print(f"Executing command:\n{docker_cmd}")
        
        # Execute the docker command
        result = subprocess.run(docker_cmd, shell=True, check=True)
        
        if result.returncode == 0:
            print("Docker container started successfully")
        else:
            print(f"Error starting container, return code: {result.returncode}")
            
    except FileNotFoundError as e:
        print(f"Error: {e}")
    except subprocess.CalledProcessError as e:
        print(f"Error executing docker command: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()
