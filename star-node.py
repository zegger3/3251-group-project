import socket
import argparse
import sys
import time
import json
import copy
from datetime import datetime, date
import pickle
import threading

selfData = []
my_name = ''
my_port = -1
pocAddress = ''
pocPort = 0
maxConnections = 0
connections = dict() # Key: Server Name, Value: (IP, Port)
RTTs = dict() # Key: (IP, Port) value: RTT
startTimes = dict() # Key: (IP, Port) value: startTime for RTT
connectedSums = dict() # Key: (IP, Port) Value: Sum

hubNode = None
client_socket = None
logs = list()
my_address = (0,0)


def init():
    global selfData
    if(len(sys.argv) == 6):
        print("Starting Star Node")
        selfData = sys.argv
        startupCheck()
    else:
        print("\nStar Node requires an input of exactly 5 arguments.  You gave: " + str(len(sys.argv) - 1) + "\nCorrect input should be of the form: \nstar-node <name> <local-port> <PoC-address> <PoCport> <N> ")

    global my_name, my_port, maxConnections, client_socket, my_address, connections, hubNode, RTTs, logs
    my_name = selfData[1]
    my_port = int(selfData[2])
    poc_address = selfData[3]
    poc_port = int(selfData[4])
    maxConnections = int(selfData[5])

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    my_ip = socket.gethostbyname(socket.getfqdn()) 
    my_address = (my_ip, my_port)
    client_socket.bind(('', my_port))

    #Try to connect to POC, if address is 0, keep running until another node connects to this one. (TODO)
    if (poc_address == '0'):
        print("TODO")
    else:
        connected = connect_to_poc(poc_address, poc_port)
        if connected == -1:
            print("failed to connect to PoC after 1 minute.")
            print("check that PoC is online.")
            sys.exit()
        #if successful then we should have access to all of the active connections
        #in the network via the poc so connect to all of them
        connect_to_network()

        #Peer discovery is completed. We can now start calculating RTT and find the hub node

    recivingThread = ReceivingThread(0, "Recieving Thread")
    recivingThread.setDaemon(True)
    recivingThread.start()

    rttThread = RTTThread(11, "rttThread")
    rttThread.setDaemon(True)
    rttThread.start()


    #TODO:
    #implement Heartbeat 
    command = raw_input("Star-Node Command: ")

    while not command == 'disconnect':

        if command == 'show-status':
            print("Status:")
            print(connections)
            for x in connections:
                print(x + " : " + str(connections[x]) + " : " + str(RTTs[connections[x]]))

            print("Hub Node: " + str(hubNode))
            for x in connections:
                if connections[x] == hubNode:
                    print(x)
                    break
        elif 'send' in command:

            info = command[5:]
            if hubNode is None or hubNode == my_address:
                addresses = connections.values()
            else:
                addresses = [hubNode]
            #have to put quotes around messages but Can't figure a way around it due to being able to send files as well
            if "\"" in info:
                parsed_message = str(info[1:-1])
                messageThread = SendMessageThread(0, 'Send Message', parsed_message, addresses)
                messageThread.setDaemon(True)
                messageThread.start()
            else:
                file = open(info, "rb")
                file_data = file.read()
                file.close()

                fileSendThread = SendFileThread(0, 'Send File', file_data, addresses)
                fileSendThread.setDaemon(True)
                fileSendThread.start()
        elif command == 'show-log':
            for log in logs:
                print(log)

        command = raw_input("Star-Node Command: ")

    print("disconnecting")
    sys.exit()
    #TODO handle the disconnect command more properly
    
def startupCheck():
    name = selfData[1]
    localPort = int( selfData[2] )
    POC_Addr = selfData[3]
    POC_Port = int( selfData[4] )
    Net_Size = int(selfData[5])
    
    checkList = [False, False, False, False, False]
    
    if(len(name) >= 1 and len(name) <= 16):
        checkList[0] = True
        print("Node name, CHECK")
        
    if(type(localPort) is int):
        checkList[1] = True
        print("Local Port #, CHECK")
    
    if(type(POC_Port) is int):
        checkList[3] = True
        
    if(type(Net_Size) is int):
        checkList[4] = True
        
    for item in checkList:
        if(checkList[item] ==  False):
            print("CheckList incomplete @ :" + str(item))
            return
    
    print("Input is good. Launching Node.")

def create_packet(packet_type, message=None):
    packet = dict()
    packet['packetType'] = packet_type
    if not message is None:
        packet['message'] = message
        packet['messageLength'] = len(message)
    else:
        packet['messageLength'] = 0

    packet_data = json.dumps(packet)
    return packet_data.encode('utf-8')


#made a seperate function to create file packets
#because json would not serialize them
def create_file_packet(file):
    packet = dict()
    packet['packetType'] = "MESSAGE_FILE"
    checksum = 0
    packet['message'] = file
    packet_data = pickle.dumps(packet)
    return packet_data


class ReceivingThread(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name

    def run(self):
        global connections, RTTs, connectedSums, hubNode, startTimes, logs
        rttReceived = 0

        while True:
            data, recieved_address = client_socket.recvfrom(64000)

            #parse recieved messages
            try:
                packet = json.loads(data.decode('utf-8'))
            except Exception as e:
                packet = pickle.loads(data)

            packet_type = packet['packetType']

            if packet_type == "SUM":
                message = packet['message']
                sent_sum = float(message)
                connectedSums[recieved_address] = sent_sum
                logs.append(str(datetime.now().time()) + ' SUM Value Recieved: ' + str(sent_sum) + ' ' + str(recieved_address))

                if len(connectedSums) == len(connections) + 1 and len(connections) > 1:
                    if hubNode is None:
                        minAddress = None
                        minSum = sys.maxsize
                        for connectedSum in connectedSums:
                            if connectedSums[connectedSum] < minSum:
                                minSum = connectedSums[connectedSum]
                                minAddress = connectedSum

                        hubNode = minAddress
                        logs.append(str(datetime.now().time()) + ' Hub Node Updated: ' + str(hubNode))

                    else:
                        minAddress = None
                        minSum = sys.maxsize
                        for connectedSum in connectedSums:
                            if connectedSums[connectedSum] < minSum:
                                minSum = connectedSums[connectedSum]
                                minAddress = connectedSum

                        if not (minAddress == hubNode):

                            if connectedSums[hubNode] * .9 > minSum:

                                hubNode = minAddress
                                logs.append(str(datetime.now().time()) + ' Hub Node Updated: ' + str(hubNode))


            elif packet_type == "RTT_REQ":
                logs.append(str(datetime.now().time()) + ' RTT Request Recieved: ' + str(recieved_address))

                rttResponseThread = RTTResponseThread(0, 'RTTResponseThread', recieved_address)
                rttResponseThread.start()

            elif packet_type == "RTT_RES":
                logs.append(str(datetime.now().time()) + ' RTT Response Recieved: ' + str(recieved_address))

                start_time = startTimes[recieved_address]
                end_time = datetime.now().time()
                rtt = (datetime.combine(date.today(), end_time) - datetime.combine(date.today(), start_time)).total_seconds() * 1000
                RTTs[recieved_address] = rtt
                rttReceived += 1

                if (len(connections) == len(RTTs) and rttReceived == len(connections)):
                    sendSumThread = SumThread(10, 'SendSumThread')
                    sendSumThread.setDaemon(True)
                    sendSumThread.start()
                    rttReceived = 0

            elif packet_type == "MESSAGE_TEXT":
                logs.append(str(datetime.now().time()) + ' Message Recieved: ' + str(recieved_address) + ' : ' + str(packet['message']))
                print("new message received from " + str(recieved_address) + ": "+ str(packet['message']))
                if hubNode == my_address:
                    addresses = []
                    for connection in connections:
                        if not connections[connection] == recieved_address:
                            addresses.append(connections[connection])
                    logs.append(str(datetime.now().time()) + ' Message Forwarded: ' + str(addresses))
                    sendMessage = SendMessageThread(0, 'SendMessageThread', packet['message'], addresses)
                    sendMessage.setDaemon(True)
                    sendMessage.start()

            elif packet_type == "MESSAGE_FILE":
                logs.append(str(datetime.now().time()) + ' File Recieved: ' + str(recieved_address))
                print("new file received from " + str(recieved_address))
                if hubNode == my_address:
                    addresses = []
                    for connection in connections:
                        if not connections[connection] == recieved_address:
                            addresses.append(connections[connection])
                    logs.append(str(datetime.now().time()) + ' Message Forwarded: ' + str(addresses))

                    sendFile = SendFileThread(0, 'SendFileThread', packet['message'], addresses)
                    sendFile.setDaemon(True)
                    sendFile.start()

            elif packet_type == "CONNECT_REQ":

                name = packet['message']

                sent_connections = copy.deepcopy(connections)
                sent_connections[my_name] = None

                connectionResponseThread = ConnectionResponseThread(0, 'Connection Response', recieved_address, sent_connections)
                connectionResponseThread.setDaemon(True)
                connectionResponseThread.start()
                connections[name] = recieved_address
                logs.append(str(datetime.now().time()) + 'Connected to New Star Node: ' + str(name) + ' ' + str(recieved_address))


class ConnectionResponseThread(threading.Thread):
    def __init__(self, threadID, name, address, message):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.address = address
        self.message = message

    def run(self):
        packet = create_packet("CONNECT_RES", self.message)
        client_socket.sendto(packet, self.address)


class SendMessageThread(threading.Thread):
    def __init__(self, threadID, name, message, addresses):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.addresses = addresses
        self.message = message

    def run(self):
        global logs
        packet = create_packet("MESSAGE_TEXT", self.message)
        for address in self.addresses:
            client_socket.sendto(packet, address)
            logs.append(str(datetime.now().time()) + ' Message Sent: ' + str(address))


class SendFileThread(threading.Thread):
    def __init__(self, threadID, name, file, addresses):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.addresses = addresses
        self.file = file

    def run(self):
        global logs
        packet = create_file_packet(self.file)
        for address in self.addresses:
            client_socket.sendto(packet, address)
            logs.append(str(datetime.now().time()) + ' File Sent: ' + str(address))


class RTTResponseThread(threading.Thread):
    def __init__(self, threadID, name, address):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.address = address

    def run(self):
        global logs
        packet = create_packet("RTT_RES")
        logs.append(str(datetime.now().time()) + ' RTT Response Sent: ' + str(self.address))

        client_socket.sendto(packet, self.address)


class SumThread(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name

    def run(self):
        global connections, RTTs, connectedSums, hubNode, logs

        summedValue = 0
        for rtt in RTTs:
            value = RTTs[rtt]
            summedValue += value
        logs.append(str(datetime.now().time()) + ' SUM Calculated: ' + str(summedValue))


        if not (summedValue == 0):
            connectedSums[my_address] = summedValue
            for connection in connections:
                addr = connections[connection]
                message = str(summedValue)
                packet = create_packet("SUM", message)
                client_socket.sendto(packet, addr)


class RTTThread(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name

    def run(self):
        global connections, startTimes, logs
        while True:
            for connection in connections:
                addr = connections[connection]
                startTimes[addr] = datetime.now().time()
                packet = create_packet("RTT_REQ")
                client_socket.sendto(packet, addr)
                logs.append(str(datetime.now().time()) + ' RTT Request Sent: ' + str(addr))

            time.sleep(5)


def connect_to_poc(PoC_address, PoC_port):
    global connections, logs
    #contact poc and receive the information
    #about the other active nodes

    #send a CONNECT_REQ packet to PoC
    response = None
    received_address = None
    client_socket.settimeout(5)
    received = False
    connect_req_packet = create_packet("CONNECT_REQ", message=my_name)
    connection_attempts = 0
    while not received and connection_attempts <= 10:
        client_socket.sendto(connect_req_packet, (PoC_address, PoC_port))
        try:
            response, received_address = client_socket.recvfrom(65507)
            received = True
        except socket.timeout:
            received = False
            connection_attempts += 1
    if connection_attempts > 10:
        return -1
    packet = json.loads(response.decode('utf-8'))
    type = packet["packetType"]
    if type == "CONNECT_RES":
        new_connections = packet["message"]
        for new_connection in new_connections:
            logs.append(str(datetime.now().time()) + 'Connected to New Star Node: ' + str(new_connection) + ' ' + str(new_connections[new_connection]))
            if new_connections[new_connection] is None:
                connections[new_connection] = received_address
            else:
                connections[new_connection] = tuple(new_connections[new_connection])
    client_socket.settimeout(None)
    return 1


def connect_to_network():
    #goes through the list of active connections and
    #exchanges contact info with all of them so that the whole network is aware
    #that this node is alive now
    for connection in connections:
        connect_req_packet = create_packet("CONNECT_REQ", message=my_name)
        addr = connections[connection]
        client_socket.sendto(connect_req_packet, addr)
        #dont really need to do anything with the response just make sure that
        #there actually was one

init()

