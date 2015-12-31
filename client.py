#
#
# Leapyosc 
# Leap to OSC converter and OSC client
#
#
# http://www.github.com/topher515/leapyosc/
# @author ckwilcox@gmail.com
#

import Leap
import sys
import OSC
from OSC import OSCClient, OSCMessage, OSCBundle
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import count
from collections import defaultdict

LeapListener = Leap.Listener

from optparse import OptionParser


DEBUG = True

def log(m, newline=False):
    x = ("%s\n" % m) if newline else str(m)
    sys.stderr.write(x)
    sys.stderr.flush()


def ZERO():
    return Leap.Vector(0.0,0.0,0.0)

###############################
###
### 'Smart' Part Tracking 
###
###############################

class RealPart(object):
    """
    Abstract class which is the base for the RealFinger and RealHand object
    """

    NOT_PROXIED = set(['_raw_part','zeroed','tracker','last_seen_frame',
                    'fingers','finger_tracker','update_raw'])

    def __init__(self, part, tracker):
        self._raw_part = part
        self.zeroed = False
        self.tracker = tracker
        self.tracker.claim_next_real_number(self)
        self.last_seen_frame = None
        self.mark_seen()

    def __str__(self):
        return "%s:0" % self.id if self.zeroed else "%s:X" % self.id

    def update_raw(self, raw_part):
        self._raw_part = raw_part

    @property
    def id(self):
        return self.tracker.get_real_number(self._raw_part)

    @property
    def leap_id(self):
        return self._raw_part.id

    def __getattr__(self, key):
        return getattr(self._raw_part, key)

    def __setattr__(self, key, value):
        if key in self.NOT_PROXIED:
            return object.__setattr__(self,key,value)
        return setattr(self._raw_part, key, value)

    def mark_seen(self):
        self.zeroed = False
        self.last_seen_frame = self.tracker.frame_count


class RealFinger(RealPart):
    """
    Wraps the `Leap.Finger` class and provides a consistent interface
    while creating sane finger IDs.
    """

    @property
    def tip_position(self):
        return ZERO() if self.zeroed else self._raw_part.tip_position

    @property
    def direction(self):
        return ZERO() if self.zeroed else self._raw_part.direction

    @property
    def is_extended(self):
        return false if self.zeroed else self._raw_part.is_extended

    def __str__(self):
        return "<Finger%s>" % self.id



class RealHand(RealPart):
    """
    Wraps the `Leap.Hand` class and provides a consistent interface
    while creating sane finger IDs.
    """

    def __init__(self, part, tracker, *args, **kwargs):
        super(RealHand, self).__init__(part, tracker, *args, **kwargs)
        self.finger_tracker = RealFingerTracker()
        self.fingers = self.FingerContainer(self)

    def __str__(self):
        def apply_(f):
            if f:
                if f.zeroed:
                    return "0"
                else:
                    return "|"
            else:
                return " "
        fings = [apply_(x) for x in self.finger_tracker.get_real_parts_or_none()]
        return """<Hand%s %s>""" % (self.id, "".join(fings))


    class FingerContainer(object):

        def __init__(self, real_hand):
            self.real_hand = real_hand

        @property
        def empty(self):
            return len(self.real_hand.finger_tracker) == 0

        # def __iter__(self):
        #     return self

        # def next(self):
        #     for real_finger in self.real_hand.finger_tracker.get_real_parts():
        #         yield real_finger

        def __iter__(self):
            for real_finger in self.real_hand.finger_tracker.get_real_parts():
                yield real_finger

    @property
    def palm_position(self):
        return ZERO() if self.zeroed else self._raw_part.palm_position

    @property
    def palm_normal(self):
        return ZERO() if self.zeroed else self._raw_part.palm_normal

    @property
    def __fingers(self):
        for finger in self._raw_part.fingers():
            yield RealFinger(finger, self.finger_tracker)



class RealPartTracker(object):
    """
    Ensures a consistent id numbering system for the body part
    """

    RealPart = None # Class

    def __init__(self, part_miss_count=5):
        self._real_parts = {}
        self._by_leap_id = {}
        self.part_miss_count = part_miss_count
        self.frame_count = 0


        self._new_raw_parts = {}

    #def __str__(self):
    #    def _(x):
    #        return self._real_parts.get(x,None)
    #    return "%s_tracker: [%s,%s,%s,%s,%s,%s]\n" % \
    #                        (self.part_name, _(0),_(1),_(2),_(3),_(4),_(5))

    def __len__(self):
        return len([x for x in self.get_real_parts() if not x.zeroed])

    def get_raw_parts(self, raw_parent):
        raise NotImplementedError

    def get_real_number(self, raw_part):
        return self._by_leap_id.get(raw_part.id)
    def get_real_part(self, raw_part):
        return self._real_parts.get(self.get_real_number(raw_part))

    def is_old_part(self, real_part):
        return (self.frame_count - real_part.last_seen_frame) >= self.part_miss_count

    def is_really_old_part(self, real_part):
        return (self.frame_count - real_part.last_seen_frame) >= (self.part_miss_count * 2)

    def handle_old_part(self, real_part):
        # Zero out the old hand
        log("Zeroing lost %s:%s\n" % (self.__class__.__name__, real_part.id) )
        real_part.zeroed = True

    def handle_really_old_part(self, real_part):
        # Completely remove the real hand from our tracking
        log("Drop lost %s:%s\n" % (self.__class__.__name__, real_part.id) )
        del self._real_parts[real_part.id]
        del self._by_leap_id[real_part.leap_id]

    def handle_parent_tick(self, raw_parent):

        #sys.stderr.write('.')
        #sys.stderr.flush()

        self.frame_count += 1

        # Deal with old hands
        for real_part in self._real_parts.values():
            if self.is_old_part(real_part):
                self.handle_old_part(real_part)
            if self.is_really_old_part(real_part):
                # This real hand data is really old! Purge it!
                self.handle_really_old_part(real_part)

        for raw_part in self.get_raw_parts(raw_parent):
            self.handle_raw_part(raw_part)


    def handle_raw_part(self, raw_part):

        # last_seen = self._new_raw_parts.get(raw_part.id)
        # self._new_raw_parts[raw_part.id] = self.frame_count
        # if not last_seen or self.frame_count - last_seen < 3:
        #     return

        real_part = self.get_real_part(raw_part)
        if real_part:
            real_part.mark_seen()
            real_part.update_raw(raw_part)
        else:
            real_part = self.RealPart(raw_part, tracker=self)
            

    def claim_next_real_number(self, real_part):
        real_num = None
        for i in count(1):
            existing_real_part = self._real_parts.get(i)
            if existing_real_part:
                if existing_real_part.zeroed:
                    real_num = i
                    break
            else:
                real_num = i
                break

        if real_num:
            self._real_parts[real_num] = real_part
            self._by_leap_id[real_part.leap_id] = real_num

    def get_real_parts_or_none(self):
        real_part_count = len(self._real_parts)
        r_counter = 0
        for i in count(1):
            if r_counter == real_part_count:
                raise StopIteration
            r = self._real_parts.get(i)
            r_counter += 1
            yield r

    def get_real_parts(self):
        return filter(None, self.get_real_parts_or_none())


class RealHandTracker(RealPartTracker):
    part_name = "hand"
    RealPart = RealHand

    def get_raw_parts(self, raw_parent): # Frame is parent
        return raw_parent.hands

    def frame_tick(self, frame):
        self.handle_parent_tick(frame)
        # All of the real hands should now be updated 
        # from this frame's raw hands

        for raw_hand in self.get_raw_parts(frame):
            # Take each raw hand in this frame and find its corresponding real hadn
            real_hand = self.get_real_part(raw_hand)
            # Then pass the raw hand data to this real_hand's finger tracker
            real_hand.finger_tracker.handle_parent_tick(raw_hand)


    @property
    def hands(self):
        return self.get_real_parts()


class RealFingerTracker(RealPartTracker):
    part_name = "finger"
    RealPart = RealFinger

    def get_real_number(self, raw_part):
        return self._by_leap_id.get(raw_part.id)

    def is_old_part(self, real_part):
        return super(RealFingerTracker, self).is_old_part(real_part)

    def get_raw_parts(self, raw_parent): # Hand is parent
        return raw_parent.fingers

    @property
    def fingers(self):
        return self.get_real_parts()



###############################
###
### OSC Conversion / Communication
###
###############################


class BaseLeapListener(LeapListener):
    def on_init(self, controller):
        log("Initialized OSC-Leap Listener\n")

    def on_connect(self, controller):
        log("Connected to Leap\n")

    def on_disconnect(self, controller):
        log("Disconnected from Leap\n")


class OSCLeapListener(BaseLeapListener):
    """
    Convert Leap hand and finger data into OSC format and 
    send to OSC server.

    """

    def __init__(self, *args, **kwargs):
        self.frame_count = 0
        self.osc_messages_sent = 0
        # Settings
        self.client = kwargs.pop('client', OSCClient())
        self.hostname = kwargs.pop('hostname', 'localhost')
        self.port = kwargs.pop('port', 8000)
        self.verbose = kwargs.pop('verbose', False)

        # OSC Connect
        log("Connecting to OSC server at '%s:%s'\n" % (self.hostname,self.port))
        self.client.connect((self.hostname, self.port))
        super(OSCLeapListener,self).__init__(*args,**kwargs)

        self.count_at_log = 0
        self.time_at_log = datetime.now()
        self.osc_messages_sent_at_log = 0
        self.previous_hands = defaultdict(list)


    def pre_send_x(self, val):
        return val
    def pre_send_y(self, val):
        return val
    def pre_send_z(self, val):
        return val

    def on_init(self, controller):
        self.send("/init")
        super(OSCLeapListener,self).on_init(controller)

    def on_exit(self, controller):
        try:
            self.send("/quit")
        except OSC.OSCClientError:
            log("Disconnected from OSC server (unable to quit gracefully)\n")
        log("Exited from OSC Leap Listener\n")

    def send(self,name,val=None):
        msg = OSCMessage(name)
        if val is not None:
            msg.append(val)
        r = self.client.send(msg)
        self.osc_messages_sent += 1
        return r

    def send_vector(self, base, vector):
        self.send("%sx" % base, self.pre_send_x(vector[0]))
        self.send("%sy" % base, self.pre_send_y(vector[1]))
        self.send("%sz" % base, self.pre_send_z(vector[2]))


    def print_frame(self, frame):
        any_ = False
        for hand in self.get_hands(frame):
            any_ = True
            log("%s" % hand)
        if any_:
            log("\n")
        else:
            log("No hands detected.\n")


    def do_stats(self):
        time_diff = datetime.now() - self.time_at_log
        #log(time_diff)
        if time_diff >= timedelta(seconds=1):
            log("Saw %s frames; Sent %4s messges in %s.\n" % 
                        (self.frame_count - self.count_at_log,
                        self.osc_messages_sent - self.osc_messages_sent_at_log,
                        time_diff))
            self.count_at_log = self.frame_count
            self.time_at_log = datetime.now()
            self.osc_messages_sent_at_log = self.osc_messages_sent


    def on_frame(self, controller):
        self.frame_count += 1 

        self.do_stats()

        frame = controller.frame()
        if DEBUG:
            #self.print_frame(frame)
            pass
        self.send_frame_data(frame)


    def get_hands(self, frame):
        return frame.hands

    def send_frame_data(self, frame):

        current_hands = defaultdict(list)

        for hand in self.get_hands(frame):

            hand_base = "/hand%d" % hand.id

            ## Handle fingers
            for finger in hand.fingers:
                self.send_vector("%s/finger%d/t" % (hand_base,finger.id),
                            finger.tip_position)
                self.send_vector("%s/finger%d/d" % (hand_base,finger.id),
                            finger.direction)
                self.send("%s/finger%d/extended" % (hand_base,finger.id),
                            1 if finger.is_extended else 0)
                current_hands[hand.id].append(finger.id)

            ## Handle palm
            # Relative point position of palm
            self.send_vector("%s/palm/t" % hand_base, hand.palm_position)
            # Normal to the plane of the palm
            self.send_vector("%s/palm/d" % hand_base, hand.palm_normal) 
            # Direction pointing from palm to fingers
            # self.send_vector("%s/palm/d" % hand_base, hand.palm_direction)

        # When we lose a hand we should ZERO out the finger data for
        # the missing hand
        # Note: that in the current implementation we only send 1 ZEROing
        # message. This packet could get lost!
        lost_hands = set(self.previous_hands.keys()) - set(current_hands.keys())
        if len(lost_hands) > 0:
            for lost_hand_key in lost_hands:
                hand_base = '/hand%d' % lost_hand_key
                for finger_key in self.previous_hands[lost_hand_key]:
                    self.send_vector("%s/finger%d/t" % (hand_base,finger_key),
                                ZERO())
                    self.send_vector("%s/finger%d/d" % (hand_base,finger_key),
                                ZERO())
                    self.send("%s/finger%d/extended" % (hand_base,finger_key),
                                0)
                self.send_vector("%s/palm/t" % hand_base, ZERO())
                self.send_vector("%s/palm/d" % hand_base, ZERO())
                log("Clear lost hand %s\n" % lost_hand_key) 

        self.previous_hands = current_hands


class BundledMixin(object):
    """
    Combine invidual OSC messages into bundles.

    One bundle is sent per frame (so it will contain all hand and finger data.)
    """

    def __init__(self, *args, **kwargs):
        self.current_bundle = None
        super(BundledMixin,self).__init__(*args,**kwargs)

    def send(self, name, val=None):
        if self.current_bundle is None:
            super(BundledMixin,self).send(name,val)
        else:
            self.osc_messages_sent += 1
            #log("Bundle: %s\n" % self.current_bundle)
            msg = OSCMessage(name)
            if val is not None:
                msg.append(val)
            self.current_bundle.append(msg)

    def send_frame_data(self, frame):
        self.current_bundle = OSCBundle()
        r = super(BundledMixin,self).send_frame_data(frame)
        if len(self.current_bundle.values()) > 0:
            self.client.send(self.current_bundle)
            #log("%s\n" % self.current_bundle.values())
        self.current_bundle = None
        return r


class VectorAsArgsMixin(object):
    """
    Send Leap vector data values with one OSC address and multiple
    OSC arguments. 
        i.e., `/hand1/palm/dxyz 0.4 0.32 0.12`.
    
    Without this mixin, Leap vector data is sent with multiple OSC addresses.
    and single arguments. 
        i.e., `/hand1/palm/dx 0.4` 
              `/hand1/palm/dy 0.32`
              `/hand1/palm/dz 0.12`
    """
    def send_vector(self, name, vector):
        if hasattr(vector,'to_tuple'):
            vec_tuple = vector.to_tuple()
        else:
            vec_tuple = vector
        self.send("%sxyz" % name, vec_tuple)


class RealPartTrackerMixin(object):
    """
    Perform 'smart' tracking of body parts. 

    - Hand and finger IDs are always lowest possible values (starting at 1)
    - "Zero out" hand and finger data when the part is no longer tracked 
        (send multiple (0.0,0.0,0.0) Vectors.)
    """

    def __init__(self, *args, **kwargs):
        super(RealPartTrackerMixin, self).__init__(*args,**kwargs)
        self.real_hands_tracker = RealHandTracker()

    def on_frame(self, controller):
        self.real_hands_tracker.frame_tick(controller.frame())
        r = super(RealPartTrackerMixin,self).on_frame(controller)
        return r

    def get_hands(self, frame):
        return self.real_hands_tracker.hands



class LinearScalingMixin(object):

    def __init__(self, x_mm_min=None, x_mm_max=None, y_mm_min=None, y_mm_max=None, 
                    z_mm_min=None, z_mm_max=None, *args, **kwargs):
        self.x_mm_min = x_mm_min
        self.x_mm_max = x_mm_max
        self.y_mm_min = y_mm_min
        self.y_mm_max = y_mm_max
        self.z_mm_min = z_mm_min
        self.z_mm_max = z_mm_max
        super(LinearScalingMixin,self).__init__(*args, **kwargs)

    def _calc(self, name, val):
        min_ = getattr(self,'%s_mm_min' % name)
        max_ = getattr(self,'%s_mm_max' % name)
        if min_ is not None and max_ is not None:
            return (float(val - min_) / (max_ - min_)) - 0.5
        else:
            return val

    def pre_send_x(self,val):
        return self._calc('x', val) 

    def pre_send_y(self,val):
        return self._calc('y', val)

    def pre_send_z(self,val):
        return self._calc('z', val)


###############################
###
### Command Line Scripting 
###
###############################


class RuntimeLeapListener(OSCLeapListener):
    """
    This class is the one run by the cli script.
    It has its inheritance chain dynamically altered (by adding mixins)
    depending on the options the user selected
    """
    pass


def main(options, hostname, port):

    # Now we append Mixin classes to our LeapListener's inheritance
    # chain based on the options the user specified
    # 
    def runtime_mixin(class_, mixin):
        class_.__bases__ = (mixin,) + class_.__bases__

    if options.multi_arg:
        runtime_mixin(RuntimeLeapListener, VectorAsArgsMixin)
    if not options.dumb:
        runtime_mixin(RuntimeLeapListener, RealPartTrackerMixin)
    if not options.unbundled:
        runtime_mixin(RuntimeLeapListener, BundledMixin)
    # ok, that was weird. Now instantiate this listener
    listener = RuntimeLeapListener(hostname=hostname, port=int(port),
                        verbose=options.verbose)
    controller = Leap.Controller()
    controller.set_policy(Leap.Controller.POLICY_BACKGROUND_FRAMES)
    controller.add_listener(listener)

    # Keep this process running until Enter is pressed
    log("Press Enter to quit...")
    sys.stdin.readline()
    controller.remove_listener(listener)


if __name__ == "__main__":

    parser = OptionParser(usage="usage: %prog [options] [host] [port]")

    #parser.add_option("-a", "--host", dest="host", type="string", 
    #    action="store", default="localhost", 
    #    help="the IP address or hostname to send packets to (default 'localhost')")
    parser.add_option("-p", "--port", dest="port", type="int",
        action="store", default="8000", 
        help="the port to address packets to (defaults to '8000'). (Note that "
            "you can also specify the port as the last argument after 'host')")

    parser.add_option("-m", "--multi-arg-vector", action="store_true", 
        dest="multi_arg",
        help="Send Leap vector data values with one OSC address and multiple "
            "OSC arguments. i.e., `/hand1/palm/dxyz 0.4 0.32 0.12`. " 
            "By default, Leap vector data is sent with multiple OSC addresses " 
            "with a single argument per i.e.,` /hand1/palm/dx 0.4` " 
            "`/hand1/palm/dy 0.32` `/hand1/palm/dz 0.12`.")

    parser.add_option("-v", "--verbose", dest="verbose", action="store_true", 
        help="Be more talkative")

    parser.add_option("-d", "--dumb", dest="dumb", action="store_true",
        help="Disable smart real hand tracking; This will cause raw hand and " 
        "finger IDs to be sent over OSC. By default, 'realistic' hand and finger "
        "IDs are maintained; this means, for instance, that a hand wont have " 
        "fingers with IDs `3, 8, 17,` instead they are mapped to `1, 2, 3`.")

    parser.add_option("-u", "--unbundled", dest="unbundled", action="store_true",
        help="Turn off bundling of OSC message; each addressable message is sent "
        "individually. By default, each Leap 'frame' is bundled into a single "
        "OSC message.")

    (opts, args_) = parser.parse_args() # Default is sys.argv[1:]

    port = None
    if len(args_) < 1:
        host = 'localhost'
    elif len(args_) < 2:
        host = args_[0]
    elif len(args_) < 3:
        host = args_[0]
        port = args_[1]

    main(opts, host, port or opts.port)
