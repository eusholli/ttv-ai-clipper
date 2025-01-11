import os
from pathlib import Path
import subprocess
import json

def read_env_file(env_path='.env.local'):
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

def build_docker_command(image_name, env_vars, port_mapping, debug_mode=False):
    """Build docker run command with environment variables."""
    env_flags = ' '.join(f'-e {key}={value}' for key, value in env_vars.items())
    
    # Add debugpy environment variable if in debug mode
    if debug_mode:
        env_flags += ' -e DEBUGPY_ENABLE=1'
    
    return f"docker run -d {env_flags} {port_mapping} {image_name}"

def get_container_ip(container_id):
    """Get the IP address of a running container."""
    try:
        # Get container details in JSON format
        cmd = f"docker inspect {container_id}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
        
        # Parse the JSON output
        container_info = json.loads(result.stdout)
        
        # Extract IP address from the first network interface
        if container_info and len(container_info) > 0:
            networks = container_info[0].get('NetworkSettings', {}).get('Networks', {})
            if networks:
                # Get the first network interface
                first_network = next(iter(networks.values()))
                return first_network.get('IPAddress')
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
        print(f"Error getting container IP: {e}")
        return None
    return None

def main():
    # Configuration
    IMAGE_NAME = "ttv-ai-clipper"
    DEBUG_MODE = True  # Set to True to enable debugging
    PORT_MAPPING = "-p 80:80 -p 5678:5678" if DEBUG_MODE else "-p 80:80"  # Add debug port when in debug mode
    ENV_FILE = '.env.local'
    
    try:
        # Read environment variables
        env_vars = read_env_file(ENV_FILE)
        
        # Build the docker command
        docker_cmd = build_docker_command(IMAGE_NAME, env_vars, PORT_MAPPING, DEBUG_MODE)
        
        # Print the command for verification
        print(f"Executing command:\n{docker_cmd}")
        
        # Execute the docker command and capture the container ID
        result = subprocess.run(docker_cmd, shell=True, capture_output=True, text=True, check=True)
        container_id = result.stdout.strip()
        
        if container_id:
            print("Docker container started successfully")
            
            # Get container IP address
            container_ip = get_container_ip(container_id)
            host_value = container_ip if container_ip else "localhost"
            
            if DEBUG_MODE:
                print(f"\nDebugger is waiting for connection on port 5678")
                print(f"Container IP address: {host_value}")
                print("Use the following VSCode launch configuration to connect:")
                print(f"""
{{
    "version": "0.2.0",
    "configurations": [
        {{
            "name": "Python: Remote Attach",
            "type": "python",
            "request": "attach",
            "connect": {{
                "host": "{host_value}",
                "port": 5678
            }},
            "pathMappings": [
                {{
                    "localRoot": "${{workspaceFolder}}",
                    "remoteRoot": "/app"
                }}
            ]
        }}
    ]
}}
                """)
        else:
            print("Error: Could not get container ID")
            
    except FileNotFoundError as e:
        print(f"Error: {e}")
    except subprocess.CalledProcessError as e:
        print(f"Error executing docker command: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()
