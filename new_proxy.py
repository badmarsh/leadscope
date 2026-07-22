import socket
import threading

def handle_client(client_socket):
    try:
        # Connect to the local Gemini proxy
        remote_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        remote_socket.connect(('127.0.0.1', 8046))

        # Receive the request from the client (container)
        request = client_socket.recv(4096)
        
        # Rewrite the Host header to match what the proxy expects
        # The container sends: Host: host.docker.internal:8045
        import re
        request = re.sub(b"(?i)Host:\s*[^\r\n]+", b"Host: 127.0.0.1:8046", request)
        
        print("--- REQUEST ---", flush=True)
        print(request.decode('utf-8', errors='replace'), flush=True)
        print("---------------", flush=True)

        # Send the modified request to the remote proxy
        remote_socket.sendall(request)

        # Receive the response and send it back to the client
        while True:
            response = remote_socket.recv(4096)
            if len(response) == 0:
                print("Remote closed connection.", flush=True)
                break
            client_socket.sendall(response)
    except Exception as e:
        print(f"Error handling request: {e}", flush=True)
    finally:
        client_socket.close()
        try:
            remote_socket.close()
        except:
            pass

def start_proxy():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('127.0.0.1', 8045))
    server.listen(5)
    print("Listening on 127.0.0.1:8045, forwarding to 127.0.0.1:8046...", flush=True)

    while True:
        client_socket, addr = server.accept()
        proxy_thread = threading.Thread(target=handle_client, args=(client_socket,))
        proxy_thread.start()

if __name__ == "__main__":
    start_proxy()
