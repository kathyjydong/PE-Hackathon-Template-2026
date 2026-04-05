import docker
import subprocess
import time

# --- PLATINUM CONFIGURATION (4 vCPU / 8GB RAM) ---
CONTAINER_PREFIX = "pe-hackathon-template-2026-app" 
MIN_INSTANCES = 1
MAX_INSTANCES = 7           # 7 clones * 0.5 CPU = 3.5 CPUs maxed out!
SCALE_UP_THRESHOLD = 70.0   # Scale up if average CPU > 70%
SCALE_DOWN_THRESHOLD = 20.0 # Scale down if average CPU < 20%
COOLDOWN_SECONDS = 30       # Wait 30s after scaling before checking again

client = docker.from_env()

def get_average_cpu():
    """Calculates the average CPU percentage across all running app clones."""
    app_containers = [c for c in client.containers.list() if c.name.startswith(CONTAINER_PREFIX)]
    
    if not app_containers:
        return 0.0, 0

    total_cpu_percent = 0.0
    for container in app_containers:
        stats = container.stats(stream=False)
        
        cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - stats['precpu_stats']['cpu_usage']['total_usage']
        system_delta = stats['cpu_stats']['system_cpu_usage'] - stats['precpu_stats']['system_cpu_usage']
        
        if system_delta > 0.0 and cpu_delta > 0.0:
            cpu_percent = (cpu_delta / system_delta) * stats['cpu_stats']['online_cpus'] * 100.0
            total_cpu_percent += cpu_percent

    return total_cpu_percent / len(app_containers), len(app_containers)

def scale_app(target_instances):
    """Fires the terminal command to change the number of clones."""
    print(f"Scaling to {target_instances} instances...")
    subprocess.run(["docker-compose", "up", "-d", "--scale", f"app={target_instances}"])
    print(f"⏳ Sleeping for {COOLDOWN_SECONDS}s cooldown...")
    time.sleep(COOLDOWN_SECONDS)

print("Auto Scaler started. Monitoring CPU usage")

while True:
    try:
        avg_cpu, current_instances = get_average_cpu()
        print(f"Current Clones: {current_instances} | Average CPU: {avg_cpu:.2f}%")

        if avg_cpu > SCALE_UP_THRESHOLD and current_instances < MAX_INSTANCES:
            print("CPU usage high. Spawning new container clone...")
            scale_app(current_instances + 1)
            
        elif avg_cpu < SCALE_DOWN_THRESHOLD and current_instances > MIN_INSTANCES:
            print("CPU usage low. Despawning a container clone...")
            scale_app(current_instances - 1)
            
        else:
            time.sleep(5)
            
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(5)