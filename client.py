import json
import socket
import threading
import time
import subprocess
import cmdModule

# Storing all session's variable in an object
appState = cmdModule.applicationState()
appState.broadcastSignature = 'PRESENCE'
appState.broadcastIP = '<broadcast>'
appState.broadcastPort = 50000
appState.broadcastInterval = 3

appState.threadLock = threading.Lock()
appState.backgroundUpdateInterval = 1

appState.clientIP = '192.168.1.6'
appState.clientPORT = int(input("Enter Port: ")) # Local testing only

appState.username = ''
appState.userActivity = True

def clearConsole():
    subprocess.run('clear', shell=True)

def displayDiscoveredPeer(cmd : str) -> bool:
    clearConsole()
    print("Dicovered Peer(s): ")
    for k, v in appState.discoveredPeer.items():
        strStatus = "Online" if v['status'] else 'Offline'
        print(f"{k} | {strStatus} | {v['ip']} | {v['port']}")

    return True

def setActivity(cmd : str) -> bool:
    if cmd.count(' ') == 0:
        print("Invalid arguments")
        return False

    cmd, arg = cmd.split(' ')
    isActive = None
    if arg == 'away':
        isActive = False
    elif arg == 'online':
        isActive = True

    if isActive is None:
        print("Invalid arguments")
        return False

    appState.userActivity = isActive
    return True

def displayHelpMenu(cmd : str) -> bool:
    commandList = {
        '/list': 'Show online users with number, name, IP and status',
        '/chat <name|number>': 'Open a chat with the selected user (TCP connection)',
        '<any text>': 'Send a message to the current chat partner',
        '/send <file>': 'Send a file to the current chat partner',
        '/leave': 'Close the current chat',
        '/status <online|away>': 'Change your status (sent via UDP)',
        '/help': 'Show all commands',
        '/quit': 'Exit the program'
    }

    print("\n\n  Help Menu  ")
    for k, v in commandList.items():
        print(f"{k}: {v}")

    return True

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

def exitProgram(cmd : str):
    raise KeyboardInterrupt

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
        try:
            for sock in sockList:
                dataBytes = sock.recv(1024)

                if dataBytes:
                    msg = dataBytes.decode('utf-8')

                    senderAddr = None

                    with appState.threadLock:
                        for addr, conn in appState.tcpConnections.items():
                            if conn == sock:
                                senderAddr = addr
                                break

                        appState.chatHistory.append({'sender': senderAddr, 'message': msg})
                    print(f"New message from {senderAddr}, msg: {msg}")
        except OSError:
            continue

def choosePeer(cmd : str) -> bool:
    if cmd.count(' ') == 0:
        print("Invalid argument")
        return False

    cmd, arg = cmd.split(' ')

    with appState.threadLock:
        if arg in appState.discoveredPeer:
            peer = appState.discoveredPeer[arg]

            appState.selectedUser = (peer['ip'], peer['port'])

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            print(appState.selectedUser)
            sock.connect(appState.selectedUser)

            appState.tcpConnections[appState.selectedUser] = sock

            print(f"Selected User {arg} ({peer['ip']}, {peer['port']})")
        else:
            print(f"Can not find user {arg}")
            return False

    return True

def clearSelectedUser(cmd : str) -> bool:
    if not appState.selectedUser:
        print("You haven't selected any user yet")
        return False

    with appState.threadLock:
        if appState.selectedUser in appState.tcpConnections:
            sock = appState.tcpConnections.pop(appState.selectedUser)
            sock.close()

    appState.selectedUser = tuple()
    return True

def sendMsg(msg : str, selectedUser : tuple):
    if len(msg) == 0:
        print("Message can't be empty")
        return

    sock = appState.tcpConnections[selectedUser]
    sock.sendall(msg.encode('utf-8'))

def mainInput():
    commandRegistry = {'/list': displayDiscoveredPeer,
                        '/status': setActivity,
                        '/quit': exitProgram,
                        '/help': displayHelpMenu,
                        '/chat': choosePeer,
                        '/leave': clearSelectedUser}

    while True:
        cmd = input("> ").strip()

        if cmd[0] != '/':
            if not appState.selectedUser:
                print("Choose a user before chatting")
            else:
                sendMsg(cmd, appState.selectedUser)
        else:
            commandFound = False
            for k in commandRegistry.keys():
                if cmd.startswith(k):
                    commandFound = True
                    if(not commandRegistry[k](cmd)):
                        print("Invalid Argument")
                    break

            if not commandFound:
                print("Invalid Command")

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
