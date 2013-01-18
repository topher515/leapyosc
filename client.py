import Leap, sys
from OSC import OSCClient, OSCMessage


class OSCLeapListener(Leap.Listener):

    def __init__(self, *args, **kwargs):
        self.client = kwargs.pop('client', OSCClient())
        self.hostname = kwargs.pop('hostname','localhost')
        self.port = kwargs.pop('port',7110)
        self.client.connect( (self.hostname, self.port) )
        super(OSCLeapListener,self).__init__(*args,**kwargs)

    def on_init(self, controller):
        self.send("/init")
        print "Initialized"

    # def on_connect(self, controller):
    #     print "Connected"

    # def on_disconnect(self, controller):
    #     print "Disconnected"

    def on_exit(self, controller):
        self.send("/quit")
        print "Exited"

    def send(self,name,val=None):
        if val:
            return self.client.send(OSCMessage(name, val))
        else:
            return self.client.send(OSCMessage(name))

    def send_vector(self, base, vector):
        self.send("%sx" % base, vector[0])
        self.send("%sy" % base, vector[1])
        self.send("%sz" % base, vector[2])

    def on_frame(self, controller):
        # Get the most recent frame and report some basic information
        frame = controller.frame()
        #print "Frame id: %d, timestamp: %d, hands: %d, fingers: %d, tools: %d" % (
        #      frame.id, frame.timestamp, len(frame.hands), len(frame.fingers), len(frame.tools))

        for hand in frame.hands:
            hand_base = "/hand%d/" % hand.id

            ## Handle fingers
            for finger in hand.finger:
                self.send_vector("%s/finger%d/t" % (hand_base,finger.id),
                            finger.tip_position)
                self.send_vector("%s/finger%d/d" % (hand_base,finger.id),
                            finger.direction)

            ## Handle palm
            # Relative point position of palm
            self.send_vector("%s/palm/t" % hand_base, hand.palm_position)
            # Normal to the plane of the palm
            self.send_vector("%s/palm/n" % hand_base, hand.palm_normal) 
            # Direction pointing from palm to fingers
            self.send_vector("%s/palm/d" % hand_base, hand.palm_direction)


def main(hostname="localhost",port="7110"):
    # Create a sample listener and controller
    listener = OSCLeapListener(hostname=hostname, port=int(port))
    controller = Leap.Controller()
    controller.add_listener(listener)

    # Keep this process running until Enter is pressed
    print "Press Enter to quit..."
    sys.stdin.readline()
    controller.remove_listener(listener)


if __name__ == "__main__":
    main(*sys.argv)
