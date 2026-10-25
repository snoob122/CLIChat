import json
import socket
import threading
import time
import subprocess

BACKGROUND_UPDATE_INTERVAL = 1

CLIENT_IP = '192.168.1.6'
#CLIENT_PORT = 50000
CLIENT_PORT = int(input("Enter Port: ")) # Local testing only

BROADCAST_TYPE = 'PRESENCE'
BROADCAST_IP = '<broadcast>'
BROADCAST_PORT = 50000
BROADCAST_INTERVAL = 3

username = ''
userActive = True

isListening : bool = False

threadLock = threading.Lock()

discoveredPeer = {}

selectedUser = None
tcpConnections = {}
chatHistory = []

def clearConsole():
    subprocess.run('clear', shell=True)

def displayDiscoveredPeer(cmd : str) -> bool:
    clearConsole()
    print("Dicovered Peer(s): ")
    for k, v in discoveredPeer.items():
        strStatus = "Online" if v['status'] else 'Offline'

        print(f'{k} | {strStatus} | {v['ip']} | {v['port']}')

    return True

def setActivity(cmd : str) -> bool:
    global userActive

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

    userActive = isActive
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
            # Payload format {type: PRESENCE, username: name, status: True/False}
            # Don't need to include ip because the socket library automatically return the client's address and port
            presencePayload = {
                'type': BROADCAST_TYPE,
                'username': username,
                'status': userActive,
                'tcpPort': CLIENT_PORT
            }

            bytesPayload = json.dumps(presencePayload).encode('utf-8')

            sock.sendto(bytesPayload, (BROADCAST_IP, BROADCAST_PORT))
            time.sleep(BROADCAST_INTERVAL)

def listenPresence():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:

        # These 2 lines is only for local testing, remove when testing LAN
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

        sock.bind(('', BROADCAST_PORT))

        while True:
            dataBytes, peerAddr = sock.recvfrom(1024)

            decodedJSON = json.loads(dataBytes.decode('utf-8'))
            if decodedJSON['type'] != BROADCAST_TYPE:
                continue

            with threadLock:
                if decodedJSON['username'] != username:
                    discoveredPeer[decodedJSON['username']] = {'ip': peerAddr[0], 'port': decodedJSON['tcpPort'], 'status': decodedJSON['status'], 'timestamp': time.time()}

def exitProgram(cmd : str):
    raise KeyboardInterrupt

def backgroundHandling():
    while True:
        curTime = time.time()

        timedOutPeers = []

        with threadLock:
            for k, v in discoveredPeer.items():
                if curTime - v['timestamp'] > 10:
                    timedOutPeers.append(k)

            if timedOutPeers != []:
                for peer in timedOutPeers:
                    discoveredPeer.pop(peer)

        time.sleep(BACKGROUND_UPDATE_INTERVAL)

def tcpAcceptor():
    global tcpConnections

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

        sock.bind((CLIENT_IP, CLIENT_PORT))
        sock.listen(5)

        while True:
            conn, addr = sock.accept()
            tcpConnections[addr] = conn
            print(f"{addr[0]} {addr[1]}")

def tcpReceiver():
    global tcpConnections, chatHistory

    while True:
        sockList = list(tcpConnections.values())
        try:
            for sock in sockList:
                dataBytes = sock.recv(1024)

                if dataBytes:
                    msg = dataBytes.decode('utf-8')

                    senderAddr = None

                    with threadLock:
                        for addr, conn in tcpConnections.items():
                            if conn == sock:
                                senderAddr = addr
                                break

                        chatHistory.append({'sender': senderAddr, 'message': msg})
                    print(f"New message from {senderAddr}, msg: {msg}")
        except OSError:
            continue

def choosePeer(cmd : str) -> bool:
    global selectedUser, discoveredPeer, tcpConnections

    if cmd.count(' ') == 0:
        print("Invalid argument")
        return False

    cmd, arg = cmd.split(' ')

    with threadLock:
        if arg in discoveredPeer:
            peer = discoveredPeer[arg]

            selectedUser = (peer['ip'], peer['port'])

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            print(selectedUser)
            sock.connect(selectedUser)

            tcpConnections[selectedUser] = sock

            print(f"Selected User {arg} ({peer['ip']}, {peer['port']})")
        else:
            print(f"Can not find user {arg}")
            return False

    return True

def clearSelectedUser(cmd : str) -> bool:
    global selectedUser, tcpConnections
    if selectedUser is None:
        print("You haven't selected any user yet")
        return False

    with threadLock:
        if selectedUser in tcpConnections:
            tcpConnections.pop(selectedUser)

    selectedUser = None
    tcpConnections[selectedUser].close()
    return True

def sendMsg(msg : str, selectedUser : tuple):
    global tcpConnections

    if len(msg) == 0:
        print("Message can't be empty")

    sock = tcpConnections[selectedUser]

    sock.sendall(msg.encode('utf-8'))

def mainInput():
    global selectedUser

    commandRegistry = {'/list': displayDiscoveredPeer,
                        '/status': setActivity,
                        '/quit': exitProgram,
                        '/help': displayHelpMenu,
                        '/chat': choosePeer,
                        '/leave': clearSelectedUser}

    while True:
        cmd = input("> ").strip()

        if cmd[0] != '/':
            if selectedUser is None:
                print("Choose a user before chatting")
            else:
                sendMsg(cmd, selectedUser)
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
        username = input("Enter your name: ")

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