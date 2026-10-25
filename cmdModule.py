import socket
import json
import threading
import subprocess
from abc import ABC, abstractmethod

class applicationState:
    def __init__(self):
        self.discoveredPeer : dict = {}
        self.userActivity = True
        self.tcpConnections : dict = {}
        self.selectedUser : tuple = ()
        self.chatHistory : list = []

        self.backgroundUpdateInterval : int = 0
        self.threadLock : threading.Lock

        self.broadcastIP : str = ''
        self.broadcastPort : int = 0
        self.broadcastInterval : float = 0
        self.broadcastSignature : str = ''

        self.userActivity : bool = True
        self.username : str = ''

        self.clientIP : str = ''
        self.clientPORT : int = 0

class commandStrategy(ABC):
    def __init__(self, state: applicationState):
        self._state = state
    def clearConsole(self) -> None:
        subprocess.run('clear', shell=True)
    @abstractmethod
    def execute(self, arg : str = '') -> bool:
        pass

class listCmd(commandStrategy):
    def execute(self, arg: str = '') -> bool:
        self.clearConsole()
        print("Dicovered Peer(s): ")
        for k, v in self._state.discoveredPeer.items():
            strStatus = "Online" if v['status'] else 'Offline'
    
            print(f'{k} | {strStatus} | {v['ip']} | {v['port']}')
    
        return True

class setActivityCmd(commandStrategy):
    def execute(self, arg: str = '') -> bool:
        if not arg:
            print("Argument missing")
            return False

        if arg == 'away':
            self._state.userActivity = False
        elif arg == 'online':
            self._state.userActivity = True
        else:
            print("Invalid arguments")
    
        return True

class quitCmd(commandStrategy):
    def execute(self, arg: str = '') -> bool:
        raise KeyboardInterrupt

class chatCmd(commandStrategy):
    def execute(self, arg: str = '') -> bool:
        with self._state.threadLock:
            if arg in self._state.discoveredPeer:
                peer = self._state.discoveredPeer[arg]
    
                self._state.selectedUser = (peer['ip'], peer['port'])
    
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
                print(self._state.selectedUser)
                sock.connect(self._state.selectedUser)
    
                self._state.tcpConnections[self._state.selectedUser] = sock
    
                print(f"Selected User {arg} ({peer['ip']}, {peer['port']})")
            else:
                print(f"Can not find user {arg}")
                return False
    
        return True

class sendMsgCmd(commandStrategy):
    def execute(self, arg: str = '') -> bool:
        if len(arg) == 0:
            print("Message can't be empty")
            return False
        
        sock : socket.socket = self._state.tcpConnections[self._state.selectedUser]

        msgPayload = {
            'name': self._state.username,
            'message': arg
        }

        bytesPayload = json.dumps(msgPayload).encode('utf-8')

        sock.sendall(bytesPayload)
    
        return True

class leaveChatCmd(commandStrategy):
    def execute(self, arg: str = '') -> bool:
        if not self._state.selectedUser:
            print("You haven't selected any user yet")
            return False
    
        with self._state.threadLock:
            if self._state.selectedUser in self._state.tcpConnections:
                sock = self._state.tcpConnections.pop(self._state.selectedUser)
                sock.close()
    
        self._state.selectedUser = tuple()
        return True

class dummyCmd(commandStrategy):
    def execute(self, arg: str = '') -> bool:
        return True

class commandHandler:  # Removed improper inheritance
    def __init__(self):
        self.__commandDict: dict[str, commandStrategy] = {}
        self.__commandDetails: list[tuple[str, str]] = []

    def register(self, commandName: str, commandDesc: str, commandSyntax: str, command: commandStrategy) -> None:
        self.__commandDict[commandName] = command
        self.__commandDetails.append((commandSyntax, commandDesc))

    def getCmd(self) -> str:
        resultStr = ''
        for syntax, desc in self.__commandDetails:
            resultStr += f"{syntax}: {desc}\n"
        return resultStr

    def process(self, inputStr: str) -> bool:
        inputStr = inputStr.strip()
        if not inputStr:
            return False

        if not inputStr.startswith('/'):
            inputStr = f"/send {inputStr}" 

        inputParts = inputStr.split(maxsplit=1) 
        command_name = inputParts[0]
        
        arg = inputParts[1] if len(inputParts) > 1 else ""

        if command_name == '/help':
            print(self.getCmd())
            return True

        command = self.__commandDict.get(command_name)
        if command:
            return command.execute(arg)
        else:
            print(f"Unknown command: {command_name}")
            return False
            