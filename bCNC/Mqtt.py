# -*- coding: ascii -*-
# $Id$
#
# Author: gustavo@gustavo.eng.br
# Date: 17-Oct-2021

from __future__ import absolute_import
from __future__ import print_function
__author__ = "Gustavo Ambrozio"
__email__  = "gustavo@gustavo.eng.br"

import json
import sys
import threading
import time

from CNC import CNC
from Utils import config

try:
	import paho.mqtt.client as mqtt
except ImportError:
	mqtt = None


prefix = "bCNC/"


#==============================================================================
# Simple MQTT client
#==============================================================================
class Mqtt():

	def __init__(self):
		self.client = None
		if mqtt is None:
			sys.stdout.write("Can't find paho, please run pip install paho-mqtt. Bailing\n")
			return

		section = "bCNC"
		try: self.broker_address = config.get(section, "mqtt_broker")
		except:
			sys.stdout.write("No broker specified, bailing\n")
			return

		self.setLimits()
		self.gcodeS = 0
		self.connected = False
		self.client = mqtt.Client("bCNC")
		self.client.on_connect = self.on_connect
		self.client.on_message = self.on_message
		self.client.on_disconnect = self.on_disconnect
		self.lastSentState = {}
		sys.stdout.write("MQTT client created\n")

	def start(self):
		if self.client is None: return
		sys.stdout.write("MQTT start called\n")
		try:
			self.client.connect(self.broker_address)
			self.client.loop_start()
		except:
			sys.stdout.write("Error connecting to broker\n")
			return
		sys.stdout.write("MQTT started loop\n")

	def stop(self):
		if self.client is None: return
		self.client.loop_stop()

	def setLimits(self, low=0.0, high=100.0, step=1.0):
		self.low    = float(low)
		self.high   = float(high)
		self.length = float(high-low)
		self.step   = float(step)
		self.done   = float(low)
		self.now    = float(low)
		self.t0     = time.time()

	def updateGCode(self, gcode):
		t = 0
		for block in gcode.blocks:
			if block.enable:
				t += block.time
		self.gcodeS = t

	def setProgress(self, now, done=None):
		self.now = now
		if self.now < self.low:
			self.now = self.low
		elif self.now > self.high:
			self.now = self.high

		if done is None:
			self.done = now - self.step
		else:
			self.done = done

		if self.done < self.low:
			self.done = self.low
		elif self.done > self.high:
			self.done = self.high

	def clear(self):
		self.setProgress(0, 0);

	def sendStatus(self):
		if self.client is None or not self.connected:
			return
		to_send = ["controller", "state", "pins", "color", "msg", "wx", "wy", "wz", "wa", "wb", "wc", "mx", "my", "mz", "ma", "mb", "mc", "G", "running"]
		jsonToSend = {name: CNC.vars[name] for name in to_send}

		completed = 100.0 * (self.done - self.low) / self.length
		jsonToSend["completed"] = completed

		# calculate remaining time
		dt = time.time() - self.t0
		p  = self.now - self.low
		if p > 0:
			total = dt / p * (self.high - self.low)
		else:
			total = 0.0
		remain = max(0.0, total - dt)
		jsonToSend["remain_s"] = remain
		jsonToSend["total_s"] = total
		jsonToSend[ "gcode_s"] = self.gcodeS

		if self.lastSentState != jsonToSend:
			self.lastSentState = jsonToSend
			contentToSend = json.dumps(jsonToSend)
			self.client.publish(prefix + "state", contentToSend, retain=False)
		threading.Timer(1, self.sendStatus).start()

	def on_message(self, client, userdata, message):
		decoded = str(message.payload.decode("utf-8"))
		print("message received", decoded)
		print("message topic =", message.topic)

	# The callback for when the client receives a CONNACK response from the server.
	def on_connect(self, client, userdata, flags, rc):
		# Subscribing in on_connect() means that if we lose the connection and
		# reconnect then subscriptions will be renewed.
		sys.stdout.write("Connected to Mqtt broker\n")
		self.connected = True
		client.subscribe(prefix + "#")
		self.lastSentState = {}
		self.sendStatus()

	def on_disconnect(self, client, userdata, rc):
		sys.stdout.write("Disconnected from Mqtt broker " +  str(rc) + "\n")
		self.connected = False
