import sys
import json
import socket
import threading
import time
import select
import cmdModule
import utility
import argparse
from prompt_toolkit.shortcuts import clear
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

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

appState.username = ''
appState.userActivity = True

appState.selectedUser = ()

# Register all required commands
cmdHandler = cmdModule.commandHandler()
cmdHandler.register('/list', 'Show online users with number, name, IP and status', '/list', cmdModule.listCmd(appState))
cmdHandler.register('/chat', 'Open a chat with the selected user (TCP connection)', '/chat <name|number>', cmdModule.chatCmd(appState))
cmdHandler.register('/sendMSG', 'Send a message to the current chat partner', '<any text>', cmdModule.sendMsgCmd(appState))
cmdHandler.register('/leave', 'Close the current chat', '/leave', cmdModule.leaveChatCmd(appState))
cmdHandler.register('/status', 'Change your status (sent via UDP)', '/status <online|away>', cmdModule.setActivityCmd(appState))
cmdHandler.register('/help', 'Show all commands', '/help', cmdModule.dummyCmd(appState))
cmdHandler.register('/quit', 'Exit the program', '/quit', cmdModule.quitCmd(appState))

def clearTerminal():
    clear()

def broadcastPresence():
    print(f"Broadcasting presence on UDP port {appState.broadcastPort}")

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
                    if appState.discoveredPeer.get(decodedJSON['username']):
                        currentStatus = appState.discoveredPeer[decodedJSON['username']]['status']

                        if currentStatus != decodedJSON['status']:
                            status = "Online" if decodedJSON['status'] else "Offline"

                            print(f"[*]: {decodedJSON['username']} just came {status}")

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

        sock.bind((appState.clientIP, appState.clientPORT))
        sock.listen(5)
        print(f"Listening on TCP port {appState.clientPORT}")

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
                header = util.recvAll(sock, 4)

                dataLen = int.from_bytes(header, 'big')

                dataBytes = util.recvAll(sock, dataLen)

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
                        appState.chatHistory.setdefault(senderAddr, [msgHistory]).append(msgHistory)

                        if senderAddr == appState.selectedUser:
                            print(f"[{msgJSON['name']}]: {msgJSON['message']}")
                        else:
                            appState.unreadCount[senderAddr] = appState.unreadCount.get(senderAddr, 0) + 1
                            print(f"[*] New message from {msgJSON['name']} ({appState.unreadCount[senderAddr]} unread)")
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
            conversation += f"[{chat['sender']}]: {chat['message']}\n"
        
    return conversation

session = PromptSession(erase_when_done=True)

def mainInput():
    currentChatUser = appState.selectedUser

    if appState.selectedUser:
        clearTerminal()
        print(loadMsg())

    with patch_stdout():
        while True:
            try:
                cmd : str = session.prompt("> ")

                appState.unreadCount[appState.selectedUser] = 0
                
                if cmd.strip():
                    cmdHandler.process(cmd.strip())
                    
                    if currentChatUser != appState.selectedUser:
                        currentChatUser = appState.selectedUser
                        clearTerminal()

                        if currentChatUser:
                            print(loadMsg())
                    else:
                        if not cmd.startswith('/'):
                            print(f"[{appState.username}]: {cmd.strip()}")
                        
            except (KeyboardInterrupt, EOFError):
                break
if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument('--n', '--name', action='store', dest='name')
        parser.add_argument('--p', '--port', action='store', dest='port')

        args = parser.parse_args()

        if args.name:
            appState.username = args.name
        else:
            appState.username = input("Enter your name: ")

        if args.port:
            appState.clientPORT = int(args.port)
        else:
            appState.clientPORT = int(input("Enter Port: ")) # Local testing only

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
