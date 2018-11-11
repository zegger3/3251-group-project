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

If an improper command is sent such as "send Hi, how are you?"" (missing the first quotation mark for the message),
the current node will break and a new one will have to be started. Since we weren't supposed to account for churn
yet for this milestone, the old node is not removed from the connections list. So if one node breaks, all nodes need to be disconnected and restarted.

