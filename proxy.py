import socket
import threading

def handle_client(client_socket):
    remote_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        remote_socket.connect(('127.0.0.1', 8045))
    except Exception as e:
        print(f"Connection to remote failed: {e}")
        try:
            client_socket.close()
        except Exception:
            pass
        try:
            remote_socket.close()
        except Exception:
            pass
        return

    def forward(src, dst):
        try:
            while True:
                data = src.recv(8192)
                if not data:
                    break
                dst.sendall(data)
        except Exception:
            pass
        finally:
            try:
                src.close()
            except Exception:
                pass
            try:
                dst.close()
            except Exception:
                pass

    threading.Thread(target=forward, args=(client_socket, remote_socket), daemon=True).start()
    threading.Thread(target=forward, args=(remote_socket, client_socket), daemon=True).start()

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(('127.0.0.1', 8046))
server.listen(10)
print("TCP Proxy listening on 127.0.0.1:8046 forwarding to 127.0.0.1:8045")

while True:
    try:
        client_socket, addr = server.accept()
        threading.Thread(target=handle_client, args=(client_socket,), daemon=True).start()
    except KeyboardInterrupt:
        break
