# 3251-group-project

Kyle Hosford
Zach Egger

Example console commands for testing on network lab machines (done in this order):

python star-node.py Andy 25555 0 0 5 (This done on networklab1.cc.gatech.edu)

python star-node.py Alex 2787 networklab1.cc.gatech.edu 25555 5 (This done on networklab2.cc.gatech.edu)

python star-node.py Tony 2666 networklab2.cc.gatech.edu 2787 5 (This done on networklab3.cc.gatech.edu)

send "this is an example message."

send "you must include quotes for non-files"

show-status

show-log

disconnect



Known bugs/limitations:

All thats left to be implemented is the handling of duplicate packets and handling the removal of a node from the network on a disconnect.

