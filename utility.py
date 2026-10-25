import socket
import subprocess

class utility:
    def clearTerminal(self) -> None:
        subprocess.run('clear', shell=True)
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
