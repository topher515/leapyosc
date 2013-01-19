import Leap, sys
import OSC
from OSC import OSCClient, OSCMessage
from collections import defaultdict
from datetime import datetime
from itertools import count


def log(m):
    sys.stderr.write(m)
    sys.stderr.flush()

class RealHand(object):

    NOT_PROXIED = set(['_raw_hand','zeroed','tracker','last_seen_frame'])

    def __init__(self, hand, tracker, *args, **kwargs):
        self._raw_hand = hand
        self.zeroed = False
        self.tracker = tracker
        self.tracker.claim_next_real_number(self)
        self.last_seen_frame = None
        self.mark_seen()

    def __str__(self):
        return "%s:0" % self.id if self.zeroed else "%s:X" % self.id

    @property
    def id(self):
        return self.tracker.get_real_number(self._raw_hand)

    @property
    def leap_id(self):
        return self._raw_hand.id

    @property
    def palm_position(self):
        return (0,0,0) if self.zeroed else self._raw_hand.palm_position

    @property
    def palm_normal(self):
        return (0,0,0) if self.zeroed else self._raw_hand.palm_normal

    def __getattr__(self, key):
        #log('Get: %s' % key)
        #if key in self.NOT_PROXIED:
        #    return object.__getattr__(self,key)
        return getattr(self._raw_hand, key)

    def __setattr__(self, key, value):
        #log("Set: %s to: %s" % (key, value))
        if key in self.NOT_PROXIED:
            return object.__setattr__(self,key,value)
        return setattr(self._raw_hand, key, value)

    def mark_seen(self):
        self.zeroed = False
        self.last_seen_frame = self.tracker.frame_count


class RealHandTracker(object):
    """
    Ensures a consistent hand tracker and numbering system
    """

    def __init__(self, hand_miss_count=5):
        self._real_hands = {}
        self._by_leap_id = {}
        self.hand_miss_count = hand_miss_count
        self.frame_count = 0
        self.current_frame = None

    def get_real_number(self, hand):
        return self._by_leap_id.get(hand.id)
    def get_real_hand(self, hand):
        return self._real_hands.get(self.get_real_number(hand))

    def is_old_hand(self, real_hand):
        return (self.frame_count - real_hand.last_seen_frame) >= self.hand_miss_count

    def is_really_old_hand(self, real_hand):
        return (self.frame_count - real_hand.last_seen_frame) >= (self.hand_miss_count * 10)

    def handle_old_hand(self, real_hand):
        # Zero out the old hand
        real_hand.zeroed = True

    def handle_really_old_hand(self, real_hand):
        # Completely remove the real hand from our tracking
        del self._real_hands[real_hand.id]
        del self._by_leap_id[real_hand.leap_id]

    def frame_tick(self, frame):

        sys.stderr.write('.')
        sys.stderr.flush()

        self.current_frame = frame
        self.frame_count += 1

        # Deal with old hands
        for real_hand in self._real_hands.values():
            if self.is_old_hand(real_hand):
                self.handle_old_hand(real_hand)
            if self.is_really_old_hand(real_hand):
                # This real hand data is really old! Purge it!
                self.handle_really_old_hand(real_hand)

        # Deal with current hands
        for raw_hand in frame.hands:
            self.handle_raw_hand(raw_hand)

        if DEBUG:
            def _(x):
                return self._real_hands.get(x,None)
            log("[%s,%s,%s,%s,%s]\n" % (_(0),_(1),_(2),_(3),_(4)))


    def handle_raw_hand(self, raw_hand):
        real_hand = self.get_real_hand(raw_hand)
        if real_hand:
            real_hand.mark_seen()
        else:
            #log('N')
            real_hand = RealHand(raw_hand, tracker=self)
        #log(str(real_hand.id))

    def claim_next_real_number(self, real_hand):
        real_num = None
        for i in count(1):
            existing_real_hand = self._real_hands.get(i)
            if existing_real_hand:
                if existing_real_hand.zeroed:
                    real_num = i
                    break
            else:
                real_num = i
                break

        if real_num:
            self._real_hands[real_num] = real_hand
            self._by_leap_id[real_hand.leap_id] = real_num

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
        self.hostname = kwargs.pop('hostname', 'localhost')
        self.port = kwargs.pop('port', 8000)
        self.dumb = kwargs.pop('dumb', False)
        # OSC Connect
        print "Connecting to OSC server at '%s:%s'" % (self.hostname,self.port)
        self.client.connect((self.hostname, self.port))
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


    def on_frame(self, controller):
        self.frame_count += 1 
        frame = controller.frame()
        self.send_frame_data(frame)

    def get_hands(self, frame):
        return frame.hands

    def send_frame_data(self, frame):
        #print "Frame id: %d, timestamp: %d, hands: %d, fingers: %d, tools: %d" % (
        #      frame.id, frame.timestamp, len(frame.hands), len(frame.fingers), len(frame.tools))
        if self.DEBUG and (self.frame_count == 1 or self.frame_count % 100 == 0):
            #print "Received frame #%d" % self.frame_count
            if self.saw_finger:
                sys.stderr.write('f')
            else:
                sys.stderr.write(".")
            sys.stderr.flush()

        for hand in self.get_hands(frame):

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


class TrackingOSCLeapListener(OSCLeapListener):

    def __init__(self, *args, **kwargs):
        super(TrackingOSCLeapListener, self).__init__(*args,**kwargs)
        self.real_hand_tracker = RealHandTracker()

    def on_frame(self, controller):
        self.real_hand_tracker.frame_tick(controller.frame())
        r = super(TrackingOSCLeapListener,self).on_frame(controller)
        return r

    def get_hands(self, frame):
        return self.real_hand_tracker.hands


def main(hostname="localhost",port="8000"):
    # Create a sample listener and controller
    listener = TrackingOSCLeapListener(hostname=hostname, port=int(port))
    controller = Leap.Controller()
    controller.add_listener(listener)

    # Keep this process running until Enter is pressed
    print "Press Enter to quit..."
    sys.stdin.readline()
    controller.remove_listener(listener)


if __name__ == "__main__":
    main(*sys.argv[1:])
