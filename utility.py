import socket
from prompt_toolkit.shortcuts import clear

class utility:
    def clearTerminal(self) -> None:
        clear()
    def getIPv4Addr(self) -> str:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(('8.8.8.8', 1))
            ip = sock.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            sock.close()

        return ip
    def recvAll(self, sock : socket.socket, length : int) -> bytes:
        result = bytearray()

        while len(result) < length:
            packet = sock.recv(length - len(result))

            if not packet:
                continue

            result.extend(packet)

        return bytes(result)

