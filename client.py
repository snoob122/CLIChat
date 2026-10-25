import json
import socket
import threading
import time
import select
import cmdModule

# Storing all session's variable in an object
appState = cmdModule.applicationState()
appState.broadcastSignature = 'PRESENCE'
appState.broadcastIP = '<broadcast>'
appState.broadcastPort = 50000
appState.broadcastInterval = 3

appState.threadLock = threading.Lock()
appState.backgroundUpdateInterval = 1

appState.clientIP = '192.168.1.12'
appState.clientPORT = int(input("Enter Port: ")) # Local testing only

appState.username = ''
appState.userActivity = True

# Register all required commands
cmdHandler = cmdModule.commandHandler()
cmdHandler.register('/list', 'Show online users with number, name, IP and status', '/list', cmdModule.listCmd(appState))
cmdHandler.register('/chat', 'Open a chat with the selected user (TCP connection)', '/chat <name|number>', cmdModule.chatCmd(appState))
cmdHandler.register('/send', 'Send a message to the current chat partner', '<any text>', cmdModule.sendMsgCmd(appState))
cmdHandler.register('/leave', 'Close the current chat', '/leave', cmdModule.leaveChatCmd(appState))
cmdHandler.register('/status', 'Change your status (sent via UDP)', '/status <online|away>', cmdModule.setActivityCmd(appState))
cmdHandler.register('/help', 'Show all commands', '/help', cmdModule.dummyCmd(appState))
cmdHandler.register('/quit', 'Exit the program', '/quit', cmdModule.quitCmd(appState))

def broadcastPresence():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        while True:
            presencePayload = {
                'type': appState.broadcastSignature,
                'username': appState.username,
                'status': appState.userActivity,
                'tcpPort': appState.clientPORT
            }

            bytesPayload = json.dumps(presencePayload).encode('utf-8')

            sock.sendto(bytesPayload, (appState.broadcastIP, appState.broadcastPort))
            time.sleep(appState.broadcastInterval)

def listenPresence():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

        sock.bind(('', appState.broadcastPort))

        while True:
            dataBytes, peerAddr = sock.recvfrom(1024)

            decodedJSON = json.loads(dataBytes.decode('utf-8'))
            if decodedJSON['type'] != appState.broadcastSignature:
                continue

            with appState.threadLock:
                if decodedJSON['username'] != appState.username:
                    appState.discoveredPeer[decodedJSON['username']] = {'ip': peerAddr[0], 'port': decodedJSON['tcpPort'], 'status': decodedJSON['status'], 'timestamp': time.time()}

def backgroundHandling():
    while True:
        curTime = time.time()

        timedOutPeers = []

        with appState.threadLock:
            for k, v in appState.discoveredPeer.items():
                if curTime - v['timestamp'] > 10:
                    timedOutPeers.append(k)

            if timedOutPeers != []:
                for peer in timedOutPeers:
                    appState.discoveredPeer.pop(peer)

        time.sleep(appState.backgroundUpdateInterval)

def tcpAcceptor():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

        sock.bind((appState.clientIP, appState.clientPORT))
        sock.listen(5)

        while True:
            conn, addr = sock.accept()
            appState.tcpConnections[addr] = conn
            print(f"{addr[0]} {addr[1]}")

def tcpReceiver():
    while True:
        sockList = list(appState.tcpConnections.values())

        if not sockList:
            time.sleep(0.5)
            continue

        try:
            # use select to efficiently monitor all sockets simultaneously
            readable, _, _ = select.select(sockList, [], [], 1.0)

            for sock in readable:
                dataBytes = sock.recv(1024)

                if dataBytes:
                    msgJSON = json.loads(dataBytes.decode('utf-8'))

                    senderAddr = None

                    with appState.threadLock:
                        for addr, conn in list(appState.tcpConnections.items()):
                            if conn == sock:
                                senderAddr = addr
                                break

                        print(f"{msgJSON['name']}: {msgJSON['message']}")

                        #appState.chatHistory.append({'sender': senderAddr, 'message': msg})
                        #print(f"New message from {senderAddr}, msg: {msg}")
        except OSError:
            continue

def mainInput():
    while True:
        cmd = input("> ").strip()
        cmdHandler.process(cmd)

if __name__ == '__main__':
    try:
        appState.username = input("Enter your name: ")

        broadcastThread = threading.Thread(target=broadcastPresence, daemon=True)
        backgroundThread = threading.Thread(target=backgroundHandling, daemon=True)
        listenThread = threading.Thread(target=listenPresence, daemon=True)
        tcpReceiveThread = threading.Thread(target=tcpReceiver, daemon=True)
        tcpAcceptThread = threading.Thread(target=tcpAcceptor, daemon=True)
        
        listenThread.start()
        broadcastThread.start()
        backgroundThread.start()
        tcpAcceptThread.start()
        tcpReceiveThread.start()
        mainInput()
    except KeyboardInterrupt:
        print("\nClient Shutting Down...")
