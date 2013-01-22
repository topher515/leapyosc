import csv

class FrameSerializer(object):

	def __init__(self, out_fp):
		self.out_fp = out_fp

	def serialize(self, frame):
		for hand in frame.hands:
			self.serialize_hand(hand)
			for finger in hand.fingers:
				self.serialize_finger(finger)

	def serialize_finger(self, finger):
		pass

	def serialize_hand(self, hand):

		pass