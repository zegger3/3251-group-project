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
name = ''
localPort = -1
POC_Addr = ''
POC_Port = 0
startTimes = dict() 
RTTs = dict() 
connectedSums = dict() 
connections = dict() 
Ack = dict()
Heartbeats = dict()
Net_Size = 0

hubNode = None
client_socket = None
logs = list()
my_address = (0,0)


def init():
    global selfData
    if(len(sys.argv) == 6):
        print("Starting Node")
        selfData = sys.argv
        startupCheck()
    else:
        print("\nNode requires an input of exactly 5 arguments.  You gave: " + str(len(sys.argv) - 1) + "\nCorrect input should be of the form: \nstar-node <name> <local-port> <PoC-address> <POC_Port> <N> ")

    global name, localPort, Net_Size, client_socket, my_address, connections, hubNode, RTTs, logs
    name = selfData[1]
    localPort = int(selfData[2])
    poc_address = selfData[3]
    poc_port = int(selfData[4])
    Net_Size = int(selfData[5])

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    my_ip = socket.gethostbyname(socket.getfqdn()) 
    my_address = (my_ip, localPort)
    client_socket.bind(('', localPort))

    #Try to connect to POC, if address is 0, keep running until another node connects to this one. (TODO)
    if (poc_address == '0'):
        print("TODO")
    else:
        connected = connect(poc_address, poc_port)
        if connected == -1:
            print("failed to connect to PoC after 1 minute.")
            print("check that PoC is online.")
            sys.exit()
        #if successful then we should have access to all of the active connections
        #in the network via the poc so connect to all of them
        PeerDiscovery()

        #Peer discovery is completed. We can now start calculating RTT and find the hub node

    receivingThread = ReceivePackets(0, "Receiving Thread")
    receivingThread.setDaemon(True)
    receivingThread.start()

    RTTRequestThread = RTTRequest(2, "RTTRequest")
    RTTRequestThread.setDaemon(True)
    RTTRequestThread.start()


    #TODO:
    #implement Heartbeat 
    #
    heartbeat = RequestHeartbeat(3, "HeartBeat Thread")
    heartbeat.setDaemon(True)
    heartbeat.start()

    command = raw_input("Command: ")

    while not command == 'disconnect':
        if 'send' in command:
            #take slice of input after the command + space
            info = command[5:]
            #determine whether we are sending it to the hub or if we are the hub that must send the messages to everyone
            if hubNode is None or hubNode == my_address:
                addresses = connections.values()
            else:
                addresses = [hubNode]
            #check for a quotation mark to determine if sending a message or a file,
            #message is parsed as everything with the quotation marks 
            #create a SendTextPacket if normal message
            if "\"" in info:
                parsed_message = str(info[1:-1])
                messageThread = SendTextPacket(0, 'Send Message', parsed_message, addresses)
                messageThread.setDaemon(True)
                messageThread.start()
                #create a SendFilePacket if File
            else:
                file = open(info, "rb")
                file_data = file.read()
                file.close()

                fileSendThread = SendFilePacket(0, 'Send File', file_data, addresses)
                fileSendThread.setDaemon(True)
                fileSendThread.start()

        #print all connected nodes and their respective RTTs then print which node
        #is currently the hub
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

        #print the log of all packets that have been sent and/or received
        elif command == 'show-log':
            for log in logs:
                print(log)
        #prepare to take next command
        command = raw_input("Command: ")

    print("disconnecting")
    sys.exit()

def startupCheck():
    name = selfData[1]
    localPort = int( selfData[2] )
    POC_Addr = selfData[3]
    POC_Port = int( selfData[4] )
    Net_Size = int(selfData[5])
    
    checkList = [False, False, False, False]
    
    if(len(name) >= 1 and len(name) <= 16):
        checkList[0] = True
        print("Node name, CHECK")
        
    if(type(localPort) is int):
        checkList[1] = True
        print("Local Port #, CHECK")
    
    if(type(POC_Port) is int):
        checkList[2] = True
        
    if(type(Net_Size) is int):
        checkList[3] = True
        
    for item in checkList:
        if(checkList[item] ==  False):
            print("CheckList incomplete @ :" + str(item))
            return
    
    print("Input is good. Launching Node.")

#creates a packet of a given packet type and sets the message 
#for the packet to given message. json then serializes the data
def create_packet(packet_type, message=None):
    packet = dict()
    packet['packetType'] = packet_type
    if not message is None:
        packet['message'] = message

    packet_data = json.dumps(packet)
    return packet_data.encode('utf-8')


#made a seperate function to create file packets
#because json would not serialize them. Used pickle
#for the serialization
def create_file_packet(file):
    packet = dict()
    packet['packetType'] = "MESSAGE_FILE"
    checksum = 0
    packet['message'] = file
    packet_data = pickle.dumps(packet)
    return packet_data

#This thread handles all incoming packets and spawns the various threads 
#that we use to respond to those packes
class ReceivePackets(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name

    def run(self):
        global connections, RTTs, connectedSums, hubNode, startTimes, logs
        rttReceived = 0

        while 1:
            data, received_addr = client_socket.recvfrom(64000)

            #parse received packets and handle them according to their type
            try:
                packet = json.loads(data.decode('utf-8'))
            except Exception as e:
                packet = pickle.loads(data)

            packet_type = packet['packetType']

            #take in the received rtt sum and determine if a more optimal hub node now exists, 
            #if so set that as the new hub
            if packet_type == "SUM":
                message = packet['message']
                sent_sum = float(message)
                connectedSums[received_addr] = sent_sum
                logs.append(str(datetime.now().time()) + ' SUM: ' + str(sent_sum) + ' ' + str(received_addr))

                if len(connectedSums) == len(connections) + 1 and len(connections) > 1:
                    if hubNode is not None:
                        minAddr = None
                        Min = sys.maxsize
                        #go through array of rtt sums and find smallest sum
                        for connected in connectedSums:
                            if connectedSums[connected] < Min:
                                Min = connectedSums[connected]
                                minAddr = connected

                        if not (minAddr == hubNode):
                            #set hub to address of node with smallest rtt sum 
                            if connectedSums[hubNode] > Min:
                                hubNode = minAddr
                                logs.append(str(datetime.now().time()) + ' New Hub: ' + str(hubNode))

                    else:
                        minAddr = None
                        Min = sys.maxsize
                        #go through array of rtt sums and find smallest sum
                        for connected in connectedSums:
                            if connectedSums[connected] < Min:
                                Min = connectedSums[connected]
                                minAddr = connected

                        #set hub to address of node with smallest rtt sum
                        hubNode = minAddr
                        logs.append(str(datetime.now().time()) + ' New Hub: ' + str(hubNode))

            #respond to rtt request if sent RTT_REQUEST packet, 
            #spawn RespondToRTT
            elif packet_type == "RTT_REQUEST":
                logs.append(str(datetime.now().time()) + ' RTT Request Received: ' + str(received_addr))
                RttResponse = RespondToRTT(0, 'RespondToRTT', received_addr)
                RttResponse.start()

            #calculate RTT and start a thread to send the sum of RTTs if all have been received
            elif packet_type == "RTT_RESPONSE":
                logs.append(str(datetime.now().time()) + ' RTT Response Received: ' + str(received_addr))
                start_time = startTimes[received_addr]
                end_time = datetime.now().time()
                time = (datetime.combine(date.today(), end_time) - datetime.combine(date.today(), start_time)).total_seconds() * 1000
                RTTs[received_addr] = time
                rttReceived += 1

                if (len(connections) == len(RTTs) and rttReceived == len(connections)):
                    sendSumThread = SumThread(1, 'SendSumThread')
                    sendSumThread.setDaemon(True)
                    sendSumThread.start()
                    rttReceived = 0

            #print whom the message was received from and the message itself and if you are the hub node,
            #start a send message thread so you send it to the other nodes.
            elif packet_type == "MESSAGE_TEXT":
                logs.append(str(datetime.now().time()) + ' Received Message: ' + str(received_addr) + ' : ' + str(packet['message']))
                ACKsendThread = ACKsend(0, 'ACK Send Thread', received_addr)
                ACKsendThread.start()
                print("Received new message from " + str(received_addr) + ": "+ str(packet['message']))
                print("Command: ")
                if hubNode == my_address:
                    addresses = []
                    for connection in connections:
                        if not connections[connection] == received_addr:
                            addresses.append(connections[connection])
                    logs.append(str(datetime.now().time()) + ' Forwarded Message: ' + str(addresses))
                    sendMessage = SendTextPacket(0, 'SendTextPacket', packet['message'], addresses)
                    sendMessage.setDaemon(True)
                    sendMessage.start()

            #print whom the file was received from and the name of the file and if you are the hub node,
            #start a send message thread so you send it to the other nodes.
            elif packet_type == "MESSAGE_FILE":
                logs.append(str(datetime.now().time()) + ' Received File: ' + str(received_addr))
                ACKsendThread = ACKsend(0, 'ACK Send Thread', received_addr)
                ACKsendThread.start()
                print("Received new file from " + str(received_addr))
                print("Command: ")
                if hubNode == my_address:
                    addresses = []
                    for connection in connections:
                        if not connections[connection] == received_addr:
                            addresses.append(connections[connection])
                    logs.append(str(datetime.now().time()) + ' Forwarded Message: ' + str(addresses))

                    sendFile = SendFilePacket(0, 'SendFilePacket', packet['message'], addresses)
                    sendFile.setDaemon(True)
                    sendFile.start()

            #start a connection response thread and add the name/address to list of connections
            elif packet_type == "CONNECT_REQUEST":

                name = packet['message']

                sent_connections = copy.deepcopy(connections)
                sent_connections[name] = None

                ConnectionResponseThread = RespondToConnection(0, 'Connection Response', received_addr, sent_connections)
                ConnectionResponseThread.setDaemon(True)
                ConnectionResponseThread.start()
                connections[name] = received_addr
                Heartbeats[received_addr] = datetime.now().time()
                logs.append(str(datetime.now().time()) + 'Connected to New Node: ' + str(name) + ' ' + str(received_addr))


            elif packet_type == "HEARTBEAT_REQUEST":
                logs.append(str(datetime.now().time()) + ' Received Heartbeat Request: ' + str(received_addr))
                heartBeatResponse = SendHeartbeat(0, 'Send Heartbeat', received_addr)
                heartBeatResponse.start()

            elif packet_type == "HEARTBEAT_RESPONSE":
                logs.append(str(datetime.now().time()) + ' Received Heartbeat Response: ' + str(received_addr))
                Heartbeats[received_addr] = datetime.now().time()

            elif packet_type == "ACK":
                logs.append(str(datetime.now().time()) + ' Received ACK: ' + str(received_addr))
                Ack[received_addr] = True


#Create a message packet with the given message text and send the message 
#to the given addresses (addresses should just be the hub node unless this
#is the hub node, in which case it is the addresses of all other nodes)
class SendTextPacket(threading.Thread):
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
            ACKwaitThread = ACKwait(0, 'Wait For Ack', address, packet, (RTTs[address] * 2))
            ACKwaitThread.start()
            logs.append(str(datetime.now().time()) + ' Sent Message: ' + str(address))

#Create a file packet with the given message text and send the file 
#to the given addresses (addresses should just be the hub node unless this
#is the hub node, in which case it is the addresses of all other nodes)
class SendFilePacket(threading.Thread):
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
            ACKwaitThread = ACKwait(0, 'Wait For Ack', address, packet, (RTTs[address] * 2))
            ACKwaitThread.start()
            logs.append(str(datetime.now().time()) + ' Sent File: ' + str(address))

#creates an RTT response packet and sends it to address which requested it
class RespondToRTT(threading.Thread):
    def __init__(self, threadID, name, address):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.address = address

    def run(self):
        global logs
        packet = create_packet("RTT_RESPONSE")
        logs.append(str(datetime.now().time()) + ' Sent RTT Response: ' + str(self.address))
        client_socket.sendto(packet, self.address)

#Request the rtt from every other node, do this every 5 seconds to make 
#sure optimal node is always being used as hub
class RTTRequest(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name

    def run(self):
        global connections, startTimes, logs
        while 1:
            for connection in connections:
                addr = connections[connection]
                startTimes[addr] = datetime.now().time()
                packet = create_packet("RTT_REQUEST")
                client_socket.sendto(packet, addr)
                logs.append(str(datetime.now().time()) + ' Sent RTT Request: ' + str(addr))

            time.sleep(10)

#sums the RTT values for a given node and sends it to all known connections
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

#goes through all the known connections, checking the response time of the heartbeat requests and declaring 
#a node offline if the time is more than 15 seconds. Then requests a new heartbeat from every node.
class RequestHeartbeat(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name

    def run(self):
        global connections, logs
        while 1:
            for connection in connections:
                addr = connections[connection]
                start = Heartbeats[addr]
                end = datetime.now().time()
                elapsed = (datetime.combine(date.today(), end) - datetime.combine(date.today(), start)).total_seconds()

                if (elapsed > 15):
                    logs.append(str(datetime.now().time()) + ' Node offline: ' + str(addr))
                    print("Node is offline")

            packet = create_packet("HEARTBEAT_REQUEST")
            for connection in connections.values():
                logs.append(str(datetime.now().time()) + ' Sent Heartbeat Request: ' + str(connection))
                client_socket.sendto(packet, connection)

            time.sleep(4)

#creates a heartbeat response packet and sends it to the node which requested it.
class SendHeartbeat(threading.Thread):
    def __init__(self, threadID, name, address):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.address = address

    def run(self):
        global logs
        packet = create_packet("HEARTBEAT_RESPONSE")
        logs.append(str(datetime.now().time()) + ' Sent Heartbeat Response: ' + str(self.address))
        client_socket.sendto(packet, self.address)

#send an ACK packet to the node which sent it the message
class ACKsend(threading.Thread):
    def __init__(self, threadID, name, address):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.address = address

    def run(self):
        global logs
        packet = create_packet("ACK")
        logs.append(str(datetime.now().time()) + ' Sent ACK: ' + str(self.address))
        client_socket.sendto(packet, self.address)

class ACKwait(threading.Thread):
    def __init__(self, threadID, name, address, resend, wait):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.address = address
        self.resend = resend
        self.wait = wait

    def run(self):
        time.sleep(self.wait)
        if not self.address in Ack or not Ack[self.address]:
            logs.append(str(datetime.now().time()) + ' Resend Packet: ' + str(self.address))
            client_socket.sendto(self.resend, self.address)
            Ack[self.address] = False
            ACKwaitThread = ACKwait(0, 'Wait For Ack', self.address, self.resend, self.wait)
            ACKwaitThread.start()


#contact poc and receive the information
#about the other active nodes
def connect(PoC_address, PoC_port):
    global connections, logs

    #send a CONNECT_REQUEST packet to PoC
    response = None
    received_addr = None
    client_socket.settimeout(5)
    received = False
    CONNECT_REQUEST_packet = create_packet("CONNECT_REQUEST", message=name)
    connection_attempts = 0
    while not received and connection_attempts <= 10:
        client_socket.sendto(CONNECT_REQUEST_packet, (PoC_address, PoC_port))
        try:
            response, received_addr = client_socket.recvfrom(64000)
            received = True
        except socket.timeout:
            received = False
            connection_attempts += 1
    if connection_attempts > 10:
        return -1
    packet = json.loads(response.decode('utf-8'))
    type = packet["packetType"]
    if type == "CONNECT_RESPONSE":
        new_connections = packet["message"]
        for new_connection in new_connections:
            logs.append(str(datetime.now().time()) + 'Connected to New Node: ' + str(new_connection) + ' ' + str(new_connections[new_connection]))
            if new_connections[new_connection] is None:
                connections[new_connection] = received_addr
            else:
                connections[new_connection] = tuple(new_connections[new_connection])

        for connection in connections.values():
            Heartbeats[connection] = datetime.now().time()
    client_socket.settimeout(None)
    return 1

#goes through the list of  connections and
#exchanges contact info with all of them so that the whole network is aware
#that this node is alive now
def PeerDiscovery():
    for connection in connections:
        CONNECT_REQUEST_packet = create_packet("CONNECT_REQUEST", message=name)
        addr = connections[connection]
        client_socket.sendto(CONNECT_REQUEST_packet, addr)
        #TODO: make sure there was a response and handle accordingly otherwise

#create a connection response packet with the connections as a message to the address
#of the node that sent the request
class RespondToConnection(threading.Thread):
    def __init__(self, threadID, name, address, message):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.address = address
        self.message = message

    def run(self):
        packet = create_packet("CONNECT_RESPONSE", self.message)
        client_socket.sendto(packet, self.address)

init()

