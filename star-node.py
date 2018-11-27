import socket
import argparse
import sys
import time
import json
import copy
from datetime import datetime, date
import threading

selfData = []
name = ''
localPort = -1
POC_Addr = ''
POC_Port = 0
starts = dict() 
RTTs = dict() 
sums = dict() 
connections = dict() 
Ack = dict()
Heartbeats = dict()
sentSequence = dict()
recvSequence = dict()

startsLock = threading.Lock()
RTTsLock = threading.Lock()
sumsLock = threading.Lock()
connectionsLock = threading.Lock()
AckLock = threading.Lock()
HeartbeatsLock = threading.Lock()
sentSequenceLock = threading.Lock()
recvSequenceLock = threading.Lock()

logs = list()
my_address = (0,0)
hub = None
client_socket = None


def init():
    global selfData
    if(len(sys.argv) == 6):
        print("Starting Node")
        selfData = sys.argv
        startupCheck()
    else:
        print("\nNode requires an input of exactly 5 arguments.  You gave: " + str(len(sys.argv) - 1) + "\nCorrect input should be of the form: \nstar-node <name> <local-port> <PoC-address> <POC_Port> <N> ")

    global name, localPort, client_socket, my_address, connections, hub, RTTs, logs
    name = selfData[1]
    localPort = int(selfData[2])
    poc_address = selfData[3]
    poc_port = int(selfData[4])

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    my_ip = socket.gethostbyname(socket.getfqdn()) 
    my_address = (my_ip, localPort)
    client_socket.bind(('', localPort))
    
    if (poc_address == '0'):
        print("\n")
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

    heartbeat = RequestHeartbeat(3, "HeartBeat Thread")
    heartbeat.setDaemon(True)
    heartbeat.start()

    command = raw_input("Command: ")

    while not command == 'disconnect':
        if 'send' in command:
            #take slice of input after the command + space
            info = command[5:]
            #determine whether we are sending it to the hub or if we are the hub that must send the messages to everyone
            if hub is None or hub == my_address:
                addresses = connections.values()
            else:
                addresses = [hub]
            #check for a quotation mark to determine if sending a message or a file,
            #message is parsed as everything with the quotation marks 
            #create a SendTextPacket if normal message
            if "\"" in info:
                parsed_message = str(info[1:-1])
                messageThread = SendTextPacket(0, 'Send Message', parsed_message, addresses)
                messageThread.setDaemon(True)
                messageThread.start()

        #print all connected nodes and their respective RTTs then print which node
        #is currently the hub
        if command == 'show-status':
            print("Status:")
            print(connections)
            for x in connections:
                print(x + " : " + str(connections[x]) + " : " + str(RTTs[connections[x]]))

            print("Hub Node: " + str(hub))
            for x in connections:
                if connections[x] == hub:
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
    
    checkList = [False, False, False, False]
    
    if(len(name) >= 1 and len(name) <= 16):
        checkList[0] = True
        print("Node name, CHECK")
        
    if(type(localPort) is int):
        checkList[1] = True
        print("Local Port #, CHECK")
    
    if(type(POC_Port) is int):
        checkList[2] = True
        
        
    for item in checkList:
        if(checkList[item] ==  False):
            print("CheckList incomplete @ :" + str(item))
            return
    
    print("Input is good. Launching Node.")

#creates a packet of a given packet type and sets the message 
#for the packet to given message. json then serializes the data
def create_packet(packet_type, message = None, sequenceNum = None):
    packet = dict()
    packet['packetType'] = packet_type
    if not sequenceNum is None:
        packet['sequence'] = sequenceNum
    if not message is None:
        packet['message'] = message

    packet_data = json.dumps(packet)
    return packet_data.encode('utf-8')

#This thread handles all incoming packets and spawns the various threads 
#that we use to respond to those packes
class ReceivePackets(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name

    def run(self):
        global connections, RTTs, sums, hub, starts, logs, Ack, Heartbeats, sentSequence, recvSequence
        rttReceived = 0

        while 1:
            data, received_addr = client_socket.recvfrom(64000)

            #parse received packets and handle them according to their type
            packet = json.loads(data.decode('utf-8'))

            packet_type = packet['packetType']

            #take in the received rtt sum and determine if a more optimal hub node now exists, 
            #if so set that as the new hub
            if packet_type == "SUM":
                message = packet['message']
                sent_sum = float(message)
                sumsLock.acquire()
                sums[received_addr] = sent_sum
                sumsLock.release()
                logs.append(str(datetime.now().time()) + ' SUM: ' + str(sent_sum) + ' ' + str(received_addr))

                if len(sums) == len(connections) + 1 and len(connections) > 1:
                    if hub is not None:
                        minAddr = None
                        Min = sys.maxsize

                        sumsLock.acquire()
                        #go through array of rtt sums and find smallest sum
                        for connected in sums:
                            if sums[connected] < Min:
                                Min = sums[connected]
                                minAddr = connected
                        sumsLock.release()

                        if not (minAddr == hub):
                            #set hub to address of node with smallest rtt sum 
                            if sums[hub] > Min:
                                hub = minAddr
                                logs.append(str(datetime.now().time()) + ' New Hub: ' + str(hub))

                    else:
                        minAddr = None
                        Min = sys.maxsize

                        sumsLock.acquire()
                        #go through array of rtt sums and find smallest sum
                        for connected in sums:
                            if sums[connected] < Min:
                                Min = sums[connected]
                                minAddr = connected
                        sumsLock.release()

                        #set hub to address of node with smallest rtt sum
                        hub = minAddr
                        logs.append(str(datetime.now().time()) + ' New Hub: ' + str(hub))

            #respond to rtt request if sent RTT_REQUEST packet, 
            #spawn RespondToRTT
            elif packet_type == "RTT_REQUEST":
                logs.append(str(datetime.now().time()) + ' RTT Request Received: ' + str(received_addr))
                RttResponse = RespondToRTT(0, 'RespondToRTT', received_addr)
                RttResponse.start()

            #calculate RTT and start a thread to send the sum of RTTs if all have been received
            elif packet_type == "RTT_RESPONSE":
                logs.append(str(datetime.now().time()) + ' RTT Response Received: ' + str(received_addr))
                start_time = starts[received_addr]
                end_time = datetime.now().time()
                time = (datetime.combine(date.today(), end_time) - datetime.combine(date.today(), start_time)).total_seconds() * 1000
                RTTsLock.acquire()
                RTTs[received_addr] = time
                RTTsLock.release()
                rttReceived += 1

                if (len(connections) == len(RTTs) and rttReceived == len(connections)):
                    sendSumThread = SumThread(1, 'SendSumThread')
                    sendSumThread.setDaemon(True)
                    sendSumThread.start()
                    rttReceived = 0

            #print whom the message was received from and the message itself and if you are the hub node,
            #start a send message thread so you send it to the other nodes.
            elif packet_type == "MESSAGE":
                logs.append(str(datetime.now().time()) + ' Received Message: ' + str(received_addr) + ' : ' + str(packet['message']))
                ACKsendThread = ACKsend(0, 'ACK Send Thread', received_addr, packet['sequence'])
                ACKsendThread.start()

                if not received_addr in recvSequence or not recvSequence[received_addr] == packet['sequence']:
                    recvSequenceLock.acquire()
                    recvSequence[received_addr] = packet['sequence']
                    recvSequenceLock.release()
                    print("Received new message from " + str(received_addr) + ": "+ str(packet['message']))
                    print("Command: ")
                    if hub == my_address:
                        addresses = []

                        connectionsLock.acquire()
                        for connection in connections:
                            if not connections[connection] == received_addr:
                                addresses.append(connections[connection])
                        connectionsLock.release()

                        logs.append(str(datetime.now().time()) + ' Forwarded Message: ' + str(addresses))
                        sendMessage = SendTextPacket(0, 'SendTextPacket', packet['message'], addresses)
                        sendMessage.setDaemon(True)
                        sendMessage.start()

                else:
                    logs.append(str(datetime.now().time()) + ' Duplicate Received: ' + str(received_addr) + ' : ' + str(packet['message']))

            #start a connection response thread and add the name/address to list of connections
            elif packet_type == "CONNECT_REQUEST":

                name = packet['message']

                sent_connections = copy.deepcopy(connections)
                sent_connections[name] = None

                ConnectionResponseThread = RespondToConnection(0, 'Connection Response', received_addr, sent_connections)
                ConnectionResponseThread.setDaemon(True)
                ConnectionResponseThread.start()

                connectionsLock.acquire()
                connections[name] = received_addr
                connectionsLock.release()

                sentSequenceLock.acquire()
                sentSequence[received_addr] = 0
                sentSequenceLock.release()

                HeartbeatsLock.acquire()
                Heartbeats[received_addr] = datetime.now().time()
                HeartbeatsLock.release()

                logs.append(str(datetime.now().time()) + 'Connected to New Node: ' + str(name) + ' ' + str(received_addr))


            elif packet_type == "HEARTBEAT_REQUEST":
                logs.append(str(datetime.now().time()) + ' Received Heartbeat Request: ' + str(received_addr))
                heartBeatResponse = SendHeartbeat(0, 'Send Heartbeat', received_addr)
                heartBeatResponse.start()

            elif packet_type == "HEARTBEAT_RESPONSE":
                logs.append(str(datetime.now().time()) + ' Received Heartbeat Response: ' + str(received_addr))
                HeartbeatsLock.acquire()
                Heartbeats[received_addr] = datetime.now().time()
                HeartbeatsLock.release()

            elif packet_type == "ACK":
                sequence = packet['sequence']
                if sequence == sentSequence[received_addr]:
                    AckLock.acquire()
                    logs.append(str(datetime.now().time()) + ' Received ACK: ' + str(received_addr))
                    Ack[received_addr] = True
                    AckLock.release()


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
        global logs, Ack, sentSequence
        for address in self.addresses:
            AckLock.acquire()
            Ack[address] = False
            AckLock.release()

            if address in sentSequence:
                sentSequence[address] = (sentSequence[address] + 1) % 2
            else:
                sentSequence[address] = 0

            packet = create_packet("MESSAGE", self.message, sequenceNum = sentSequence[address])
            client_socket.sendto(packet, address)
            ACKwaitThread = ACKwait(0, 'Wait For Ack', address, packet, RTTs[address])
            ACKwaitThread.start()
            logs.append(str(datetime.now().time()) + ' Sent Message: ' + str(address))

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
        global connections, starts, logs
        while 1:
            connectionsLock.acquire()
            for connection in connections:
                address = connections[connection]

                startsLock.acquire()
                starts[address] = datetime.now().time()
                startsLock.release()

                packet = create_packet("RTT_REQUEST")
                client_socket.sendto(packet, address)
                logs.append(str(datetime.now().time()) + ' Sent RTT Request: ' + str(address))
            connectionsLock.release()
            time.sleep(5)

#sums the RTT values for a given node and sends it to all known connections
class SumThread(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name

    def run(self):
        global connections, RTTs, sums, hub, logs

        summed = 0

        RTTsLock.acquire()
        for rtt in RTTs:
            value = RTTs[rtt]
            summed += value
        RTTsLock.release()

        logs.append(str(datetime.now().time()) + ' SUM Calculated: ' + str(summed))


        if not (summed == 0):
            sumsLock.acquire()
            sums[my_address] = summed
            sumsLock.release()

            connectionsLock.acquire()
            for connection in connections:
                addr = connections[connection]
                message = str(summed)
                packet = create_packet("SUM", message)
                client_socket.sendto(packet, addr)
            connectionsLock.release()

#goes through all the known connections, checking the response time of the heartbeat requests and declaring 
#a node offline if the time is more than 15 seconds. Then requests a new heartbeat from every node.
class RequestHeartbeat(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name

    def run(self):
        global connections, logs, Heartbeats
        while 1:
            connectionsLock.acquire()
            for connection in connections:
                addr = connections[connection]
                start = Heartbeats[addr]
                end = datetime.now().time()
                elapsed = (datetime.combine(date.today(), end) - datetime.combine(date.today(), start)).total_seconds()

                if (elapsed > 15):
                    logs.append(str(datetime.now().time()) + ' Node offline: ' + str(addr))

                    print("Node is offline")
                    disconnectNode(connection)

                    print("Node " + str(addr) + " is offline")


            packet = create_packet("HEARTBEAT_REQUEST")
            for connection in connections.values():
                logs.append(str(datetime.now().time()) + ' Sent Heartbeat Request: ' + str(connection))
                client_socket.sendto(packet, connection)

            connectionsLock.release()
            time.sleep(4)

#method to disconnect the desired node, represented as an index.  If no node is specified, it deletes itself            
def disconnectNode(node=None):
    if node != None:
        global connections, startTimes, RTTs, connectedSums, Ack, Heartbeats
        #pop modifies the dictionary IN-PLACE, better for this case than del()
        if node in connections.keys():
            connections.pop(node)
        if node in startTimes.keys():
            startTimes.pop(node)
        if node in RTTs.keys():
            RTTs.pop(node)
        if node in connectedSums.keys():
            connectedSums.pop(node)
        if node in Ack.keys():
            Ack.pop(node)
        if node in Heartbeats.keys():
            Heartbeats.pop(node)
    else:
        print("TODO: delete self")

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
    def __init__(self, threadID, name, address, sequenceNum):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.address = address
        self.sequenceNum = sequenceNum

    def run(self):
        global logs
        packet = create_packet("ACK", sequenceNum = self.sequenceNum)
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

            AckLock.acquire()
            Ack[self.address] = False
            AckLock.release()

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

        connectionsLock.acquire()
        for new_connection in new_connections:
            logs.append(str(datetime.now().time()) + 'Connected to New Node: ' + str(new_connection) + ' ' + str(new_connections[new_connection]))
            if new_connections[new_connection] is None:
                connections[new_connection] = received_addr
            else:
                connections[new_connection] = tuple(new_connections[new_connection])

        HeartbeatsLock.acquire()
        for connection in connections.values():
            Heartbeats[connection] = datetime.now().time()
        HeartbeatsLock.release()

        connectionsLock.release()
    client_socket.settimeout(None)
    return 1

#goes through connections and exchanges contact info
#with them so that the network is aware node is alive
def PeerDiscovery():
    connectionsLock.acquire()
    for connection in connections:
        CONNECT_REQUEST_packet = create_packet("CONNECT_REQUEST", message=name)
        addr = connections[connection]
        client_socket.sendto(CONNECT_REQUEST_packet, addr)
    connectionsLock.release()

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

