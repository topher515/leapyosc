import Leap, sys
import OSC
from OSC import OSCClient, OSCMessage
from collections import defaultdict
from datetime import datetime
from itertools import count


{
    'last_seen'

}


class RealHandTracker(object):

    def __init__(self, hand_miss_count=5):
        self._real_hands = {}
        self._by_id = {}
        self.hand_miss_count = hand_miss_count
        self.frame_count = 0

    def get_real_number(self, hand):
        return self._by_id.get(hand.id)

    def frame_tick(self, frame):
        self.frame_count += 1

        for real_num, hand_data in self._real_hands.items():
            last_seen_frame, real_hand = hand_data
            if self.frame_count - last_seen_frame >= self.hand_miss_count:
                # This real hand data is old! Purge it!
                del self._real_hands[real_num]
                del self._by_id[real_hand.id]

        for hand in frame.hands:
            self.handle(hand)


    def handle(self, hand):
        real_num = self.get_real_number(hand)
        if real_num:
            # We found the real number for this hand, we're done
            return 

        real_num = self.get_next_real_number()
        self._by_id[hand.id] = real_num
        self._real_hands[real_num] = (self.frame_count, hand)

    def get_next_real_number(self):
        for i in count(1):
            if self._real_hands.get(i):
                return i

    @property
    def hands(self):
        real_hand_count = len(self._real_hands)
        r_counter = 0
        for i in count(1):
            if r_counter == real_hand_count:
                raise StopIteration
            r = self._real_hands.get(i)
            if r:
                r_counter += 1
                yield r



class OSCLeapListener(Leap.Listener):

    DEBUG = True

    def __init__(self, *args, **kwargs):
        self.frame_count = 0
        self.saw_finger = False
        # Settings
        self.client = kwargs.pop('client', OSCClient())
        self.hostname = kwargs.pop('hostname','localhost')
        self.port = kwargs.pop('port',7110)
        self.dumb = kwargs.pop('dumb',False)
        # OSC Connect
        print "Connecting to OSC server at '%s:%s'" % (self.hostname,self.port)
        self.client.connect((self.hostname, self.port))

        self.real_hand_tracker = RealHandTracker()

        super(OSCLeapListener,self).__init__(*args,**kwargs)

    def on_init(self, controller):
        self.send("/init")
        print "Initialized OSC-Leap Listener"

    def on_connect(self, controller):
        print "Connected to Leap"

    def on_disconnect(self, controller):
        print "Disconnected from Leap"

    def on_exit(self, controller):
        try:
            self.send("/quit")
        except OSC.OSCClientError:
            print "Disconnected from OSC server (unable to quit gracefully)"
        print "Exited from OSC Leap Listener"

    def send(self,name,val=None):
        msg = OSCMessage(name)
        if val:
            msg.append(val)
        #print msg
        return self.client.send(msg)

    def send_vector(self, base, vector):
        self.send("%sx" % base, vector[0])
        self.send("%sy" % base, vector[1])
        self.send("%sz" % base, vector[2])

    def _on_frame_smart(self, controller):
        frame = controller.frame()

        self.real_hand_tracker.frame_tick(frame)
        for hand in self.real_hand_tracker.hands:




            hand_dict = hand_db.get(hand.id):
            if hand_dict:

            else:
                hand_db[hand.id] = {
                    ""
                }


            else:
                # New hand!
                ["ts"] = datetime.now()


            hand_base = "/hand%d" % hand.id



    def on_frame(self, controller):
        self.frame_count += 1
        if self.dumb:
            return self._on_frame_dumb(controller)
        else:
            return self._on_frame_smart(controller)

    def _on_frame_dumb(self, controller):
        frame = controller.frame()
        #print "Frame id: %d, timestamp: %d, hands: %d, fingers: %d, tools: %d" % (
        #      frame.id, frame.timestamp, len(frame.hands), len(frame.fingers), len(frame.tools))

        if self.DEBUG and (self.frame_count == 1 or self.frame_count % 100 == 0):
            #print "Received frame #%d" % self.frame_count
            if self.saw_finger:
                sys.stderr.write('f')
            else:
                sys.stderr.write(".")
            sys.stderr.flush()

        for hand in frame.hands:
            hand_base = "/hand%d" % hand.id

            if hand.fingers.empty:
                self.saw_finger = False
            else:
                self.saw_finger = True

            ## Handle fingers
            for finger in hand.fingers:
                self.send_vector("%s/finger%d/t" % (hand_base,finger.id),
                            finger.tip_position)
                self.send_vector("%s/finger%d/d" % (hand_base,finger.id),
                            finger.direction)


            ## Handle palm
            # Relative point position of palm
            self.send_vector("%s/palm/t" % hand_base, hand.palm_position)
            # Normal to the plane of the palm
            self.send_vector("%s/palm/d" % hand_base, hand.palm_normal) 
            # Direction pointing from palm to fingers
            # self.send_vector("%s/palm/d" % hand_base, hand.palm_direction)


def main(hostname="10.0.1.83",port="8000"):
    # Create a sample listener and controller
    listener = OSCLeapListener(hostname=hostname, port=int(port))
    controller = Leap.Controller()
    controller.add_listener(listener)

    # Keep this process running until Enter is pressed
    print "Press Enter to quit..."
    sys.stdin.readline()
    controller.remove_listener(listener)


if __name__ == "__main__":
    main(*sys.argv[1:])
