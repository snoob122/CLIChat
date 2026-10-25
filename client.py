import sys
import json
import socket
import threading
import time
import select
import cmdModule
import subprocess
import utility

util = utility.utility()

# Storing all session's variable in an object
appState = cmdModule.applicationState()
appState.broadcastSignature = 'PRESENCE'
appState.broadcastIP = '<broadcast>'
appState.broadcastPort = 50000
appState.broadcastInterval = 3

appState.threadLock = threading.Lock()
appState.backgroundUpdateInterval = 1

appState.clientIP = util.getIPv4Addr()
appState.clientPORT = int(input("Enter Port: ")) # Local testing only

appState.username = ''
appState.userActivity = True

appState.selectedUser = ()

# Register all required commands
cmdHandler = cmdModule.commandHandler()
cmdHandler.register('/list', 'Show online users with number, name, IP and status', '/list', cmdModule.listCmd(appState))
cmdHandler.register('/chat', 'Open a chat with the selected user (TCP connection)', '/chat <name|number>', cmdModule.chatCmd(appState))
cmdHandler.register('/send', 'Send a message to the current chat partner', '<any text>', cmdModule.sendMsgCmd(appState))
cmdHandler.register('/leave', 'Close the current chat', '/leave', cmdModule.leaveChatCmd(appState))
cmdHandler.register('/status', 'Change your status (sent via UDP)', '/status <online|away>', cmdModule.setActivityCmd(appState))
cmdHandler.register('/help', 'Show all commands', '/help', cmdModule.dummyCmd(appState))
cmdHandler.register('/quit', 'Exit the program', '/quit', cmdModule.quitCmd(appState))

def clearTerminal():
    subprocess.run('clear', shell=True)

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
                    senderName = msgJSON['name']

                    with appState.threadLock:
                        if senderName in appState.discoveredPeer:
                            peer = appState.discoveredPeer[senderName]
                            senderAddr = (peer['ip'], peer['port'])
                        else:
                            continue

                        msgHistory = {'sender': msgJSON['name'], 'message': msgJSON['message']}

                        if appState.chatHistory.get(senderAddr):
                            appState.chatHistory[senderAddr].append(msgHistory)
                        else:
                            appState.chatHistory[senderAddr] = [msgHistory]
        except OSError:
            continue

def loadMsg() -> str:
    conversation = ''

    if appState.selectedUser:
        hasConv = appState.chatHistory.get(appState.selectedUser)

        if not hasConv:
            return "Start a new conversation!"
        
        chatCollection = appState.chatHistory[appState.selectedUser]

        for chat in chatCollection:
            conversation += f'[{chat['sender']}]: {chat['message']}\n'
        
    return conversation

def mainInput():
    lastMsgCount = -2

    while True:
        hasSelectedUser = appState.selectedUser

        if hasSelectedUser:
            curMsgCount = len(appState.chatHistory.get(appState.selectedUser, []))
        else:
            curMsgCount = 0

        if hasSelectedUser and curMsgCount != lastMsgCount: # Forces an update since the current loaded chat history is outdated
            clearTerminal()
            print(loadMsg())
            print("> ", end="", flush=True) # Render the '> '
            lastMsgCount = curMsgCount
        elif not hasSelectedUser and lastMsgCount != -1: # Prevent continuous '> ' when the user is not chatting
            print("> ", end="", flush=True)
            lastMsgCount = -1

        # Different from input(), this doesn't block the flow of the code so it will allow elements to render regardless of input
        readable, _, _ = select.select([sys.stdin], [], [], 0.5) # Read from stdin

        if readable:
            cmd = sys.stdin.readline().strip()
            cmdHandler.process(cmd)
            lastMsgCount = -2

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
