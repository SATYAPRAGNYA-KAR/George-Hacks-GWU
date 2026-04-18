"""
Run this to start the Crop Health API server.

    python start_server.py

The server binds on all interfaces (0.0.0.0:8000) so teammates on the same
network can reach it at  http://<your-local-ip>:8000
"""
import socket
import uvicorn

def _local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()

if __name__ == "__main__":
    ip = _local_ip()
    print(f"\n  Crop Health API starting...")
    print(f"  Local:    http://localhost:8000")
    print(f"  Network:  http://{ip}:8000")
    print(f"  Docs:     http://{ip}:8000/docs\n")
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)
