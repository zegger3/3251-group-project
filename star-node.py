import socket
import argparse
import sys

selfData = []

def init():
    global selfData
    if(len(sys.argv) == 6):
        print("Starting Star Node")
        selfData = sys.argv
        startupCheck()
    else:
        print("\nStar Node requires an input of exactly 5 arguments.  You gave: " + str(len(sys.argv) - 1) + "\nCorrect input should be of the form: \nstar-node <name> <local-port> <PoC-address> <PoCport> <N> ")
    
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
        
    try:
       POC_Addr = socket.inet_aton(POC_Addr)
       print("legal IP Address, CHECK")
       checkList[2] = True
    except socket.error:
        print("Not a legal IP Address")
    
    if( type(POC_Port) is int):
        checkList[3] = True
        
    if( type(Net_Size) is int):
        checkList[4] = True
        
    for item in checkList:
        if(checkList[item] ==  False):
            print("CheckList incomplete @ :" + str(item))
            return
    
    print("Input is good. Launching Node.")
    
def starNode():
    print("Initializing Threads")
    
    
def udpClient():
    UDP_IP = input("IP address? ")
    UDP_PORT = input("Port #? ")
    udpLoop = 1

    while (udpLoop == 1):
            
        MESSAGE = input("Please input the equation. \nThe only supported operations are +, -, /, and *. \nNegative digits are allowed, as are decimals. \nMaximum of 15 characters per number. ")


        if(MESSAGE.upper() == 'QUIT'):
            udpLoop = 0
            print("Bye")
            break;
        print( "UDP target IP:", UDP_IP)
        print( "UDP target port:", UDP_PORT)
        print( "message:", MESSAGE)

        firstSign = 0
        secondSign = 0
        add = MESSAGE.find('+')
        sub = MESSAGE.find('-')
        mult = MESSAGE.find('*')
        div = MESSAGE.find('/')
        
        if(sub == 0):
            firstSign = -1
            sub = MESSAGE[1:].find('-')
            if(sub > -1):
                sub +=1
        operList = []
        if(add > -1):
            operList.append(add)
        if(sub > -1):
            operList.append(sub)
        if(mult > -1):
            operList.append(mult)
        if(div > -1):
            operList.append(div)
        
        oper= min(operList)
        
        
        firstNum = MESSAGE[0-firstSign : oper]
        
        symbol = MESSAGE[oper:oper+1]
        
        if( symbol == '-' ):
            if(MESSAGE[oper+1:oper+2] != '-'):
                secondNum = MESSAGE[oper+1:]
            else:
                secondNum = MESSAGE[oper+2:]
        else:
            if(MESSAGE[oper+1:oper+2] != '-'):
                secondNum = MESSAGE[oper+1:]
            else:
                secondSign = -1
                secondNum = MESSAGE[oper+2:]
            
        clientMessage = ""
        
        if(firstSign == -1):
            clientMessage += '-'
        else:
            clientMessage += '+'
            
        firstPad = ''
        
        while( len(firstPad) < 15 - len(firstNum) ):
            firstPad += '0'
            
        if(firstNum.find('.') == -1):
            clientMessage = clientMessage + firstPad + firstNum
        else:
            clientMessage = clientMessage + firstNum + firstPad
        
        if(secondSign == -1):
            clientMessage += '-'
        else:
            clientMessage += '+'
            
        secondPad = ''
        while( len(secondPad) < 15 - len(secondNum) ):
            secondPad += '0'
        if(secondNum.find('.') == -1):
            clientMessage = clientMessage + secondPad + secondNum
        else:
            clientMessage = clientMessage + secondNum + secondPad
        
        clientMessage += symbol
        
        
        encMessage = str.encode(clientMessage)
        print( encMessage )

        sock = socket.socket(socket.AF_INET, # Internet
                             socket.SOCK_DGRAM) # UDP
        sock.sendto(encMessage, (UDP_IP, int(UDP_PORT)))

        recvLoop = 1
        while recvLoop:
            data, addr = sock.recvfrom(1024)
            if data:
                print(data.decode())
                recvLoop = 0



def udpServ():
    UDP_IP = input("IP address? ")
    UDP_PORT = input("Port #? ")
    udpLoop = 1
    sock = socket.socket(socket.AF_INET, # Internet
                         socket.SOCK_DGRAM) # UDP
    sock.bind((UDP_IP, int(UDP_PORT)))

    while(udpLoop == 1):
        data, addr = sock.recvfrom(1024) # buffer size is 1024 bytes
        if not data: break

        print( "received data: ", data)
        
        clientMessage = data.decode()
        if(clientMessage.upper() == 'quit'):
            tcpLoop = 0
            break;
        firstNum = clientMessage[:16]
        secondNum = clientMessage[16:32]
        oper = clientMessage[32:]

        if(firstNum[:1] == '-'):
            if(firstNum.find('.') > -1):
                firstNum = float(firstNum[1:]) * -1
            else:
                firstNum = int(firstNum[1:]) * -1
        else:
            if(firstNum.find('.') > -1):
                firstNum = float(firstNum[1:])
            else:
                firstNum = int(firstNum[1:])

        if(secondNum[:1] == '-'):
            if(secondNum.find('.') > -1):
                secondNum = float(secondNum[1:]) * -1
            else:
                secondNum = int(secondNum[1:]) * -1
        else:
            if(secondNum.find('.') > -1):
                secondNum = float(secondNum[1:])
            else:
                secondNum = int(secondNum[1:])

        if(oper == '+'):
            result = firstNum + secondNum
        elif(oper == '-'):
            result = firstNum - secondNum
        elif(oper == '*'):
            result = firstNum * secondNum
        elif(oper == '/'):
            result = firstNum / secondNum
        else:
            result = "ERR"

        result= str(result)
        
        if(result != "ERR"):
            resultSign = '+'                
            resultPad = ""
            if(result[:1] == '-'):
                resultSign = '-'
                result = result[1:]
                
            while( len(resultPad) <= 15 - len(result)):
                resultPad += '0'

            if(result.find('.') > -1):
                resultMessage = resultSign + result + resultPad
            else:
                resultMessage = resultSign + resultPad + result

            resultMessage += "\nMade by: Kyle Hosford \n\n"
                
        else:
            resultMessage = "ERR: unknown operator Only use +, -, *, / please"

        sock.sendto(str.encode(resultMessage), addr)
    



def main():
    usrInput = input("Client? or Server?")

    if(usrInput.upper() == "CLIENT" ):
        usrInput = input("TCP? or UDP?")

        if(usrInput.upper() == "UDP"):
            udpClient()
        else:
            print("it's not hard. Type 'UDP' or 'TCP' next time")
            main()
    elif(usrInput.upper() == "SERVER"):
        usrInput = input("TCP? or UDP?")

        if(usrInput.upper() == "UDP"):
            udpServ()
        else:
            print("it's not hard. Type 'UDP' or 'TCP' next time")
            main()
    else:
        print("Bad input. Please type 'client' or 'server'")
        main()



init()

