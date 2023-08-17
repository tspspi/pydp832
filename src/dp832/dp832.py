from labdevices.exceptions import CommunicationError_ProtocolViolation
from labdevices.exceptions import CommunicationError_Timeout
from labdevices.exceptions import CommunicationError_NotConnected

import sys
import atexit

import logging
import socket
import stat
import time

import os
from pathlib import Path

from labdevices import powersupply

from time import sleep

class DP832(powersupply.PowerSupply):
	def __init__(
		self,

		debug = False,
		timeoutRetry = 3,
		readbackRetry = 3,
		commandDelay = 0.1,

		logLevel = "ERROR",
		logger = None
	):
		super().__init__(
			nChannels = 3,
			vrange = (0, 30, 1e-3),
			arange = (0, 3, 1e-3),
			prange = (0, 90, 1e-3),
			capableVLimit = True,
			capableALimit = True,
			capableMeasureV = True,
			capableMeasureA = True,
			capableOnOff = True
		)

		self._debug = debug
		self._timeoutRetry = timeoutRetry
		self._readbackRetry = readbackRetry
		self._commandDelay = commandDelay

		if logger is not None:
			self._logger = logger
		else:
			self._logger = logging.getLogger()
			loglvls = {
				"DEBUG" : logging.DEBUG,
				"INFO" : logging.INFO,
				"WARNING" : logging.WARNING,
				"ERROR" : logging.ERROR,
				"CRITICAL" : logging.CRITICAL
			}

		if logLevel is not None:
			if not logLevel in loglvls:
				raise ValueError("Unknown loglevel {logLevel}, must be DEBUG, INFO, WARNING, ERROR or CRITICAL")
			self._logger.setLevel(loglvls[logLevel.upper()])

		if logger is None:
			self._logger.addHandler(logging.StreamHandler(sys.stderr))

	def _idn(self, raw = False):
		if self._isConnected():
			if raw:
				return self._scpi_command("*IDN?")
			else:
				resp = self._scpi_command("*IDN?")
				if resp is None:
					return None

				parts = resp.split(",")
				ver = ( (parts[3].split("."))[0], (parts[3].split("."))[1], (parts[3].split("."))[2] )
				sn = parts[2]
				return {
					'idn' : resp,
					'serial' : sn,
					'version' : ver
				}
		return False

	def _setChannelEnable(self, enable, channel):
		if not isinstance(channel, int):
			raise ValueError("Channel number has to be an integer (1-3)")
		if (channel < 1) or (channel > 3):
			raise ValueError("Channel index out of range")

		while True:
			if enable:
				resp = self._scpi_command_noreply(f":OUTP CH{channel},ON")
			else:
				resp = self._scpi_command_noreply(f":OUTP CH{channel},OFF")

			# Do readback ...
			if self._commandDelay:
				if self._commandDelay > 0:
					sleep(self._commandDelay)

			resp = self._scpi_command(f":OUTP? CH{channel}")
			if enable:
				if resp == "ON":
					return True
			else:
				if resp == "OFF":
					return True

			# Error delay and retry (ToDo)

	def _setVoltage(self, voltage, channel):
		if not isinstance(channel, int):
			raise ValueError("Channel number has to be an integer (1-3)")
		if (channel < 1) or (channel > 3):
			raise ValueError("Channel index out of range")
		if (voltage < 0) or (voltage > 30):
			raise ValueError("Voltage has to be in range from 0 to 30V for first two channels")
		if ((voltage < 0) or (voltage > 5)) and (channel == 3):
			raise ValueError("Voltage has to be in range from 0 to 5V for last channel")

		while True:
			self._scpi_command_noreply(f":SOUR{channel}:VOLT {voltage}")

			resp = self._scpi_command(f":SOUR{channel}:VOLT?")
			d = (float(resp) - float(voltage))
			if d < 0:
				d = d * -1.0
			if d < 1e-3:
				return True

			self._logger.warning(f"Requested set voltage {voltage} but read back {resp}, retrying")

	def _setCurrent(self, current, channel):
		if not isinstance(channel, int):
			raise ValueError("Channel number has to be an integer (1-3)")
		if (channel < 1) or (channel > 3):
			raise ValueError("Channel index out of range")
		if (current < 0) or (current > 3):
			raise ValueError("Current has to be in range from 0 to 3A")

		while True:
			self._scpi_command_noreply(f":SOUR{channel}:CURR {current}")

			resp = self._scpi_command(f":SOUR{channel}:CURR?")
			d = (float(resp) - float(current))
			if d < 0:
				d = d * -1.0
			if d < 1e-3:
				return True

			self._logger.warning(f"Requested set current {voltage} but read back {resp}, retrying")

	def _getVoltage(self, channel):
		if not isinstance(channel, int):
			raise ValueError("Channel number has to be an integer (1-3)")
		if (channel < 1) or (channel > 3):
			raise ValueError("Channel index out of range")

		while True:
			resp = self._scpi_command(f":MEAS:ALL? CH{channel}")
			if resp:
				parts = resp.split(",")
				v = float(parts[0])
				a = float(parts[1])
				p = float(parts[2])
				self._logger.debug(f"Measured CH{channel}: {v}V, {a}A, {p}W")

				return v
			raise CommunicationError_ProtocolViolation(f"Unknown response for voltage measurement {resp}")

	def _getCurrent(self, channel):
		if not isinstance(channel, int):
			raise ValueError("Channel number has to be an integer (1-3)")
		if (channel < 1) or (channel > 3):
			raise ValueError("Channel index out of range")

		while True:
			resp = self._scpi_command(f":MEAS:ALL? CH{channel}")
			if resp:
				parts = resp.split(",")
				v = float(parts[0])
				a = float(parts[1])
				p = float(parts[2])
				self._logger.debug(f"Measured CH{channel}: {v}V, {a}A, {p}W")

				return a
			raise CommunicationError_ProtocolViolation(f"Unknown response for current measurement {resp}")

	def _getLimitMode(self, channel):
		if not isinstance(channel, int):
			raise ValueError("Channel number has to be an integer (1-3)")
		if (channel < 1) or (channel > 3):
			raise ValueError("Channel index out of range")

		while True:
			resp = self._scpi_command(f":OUTP:CVCC? CH{channel}")
			if resp:
				if resp == "CV":
					return powersupply.PowerSupplyLimit.VOLTAGE
				if resp == "CC":
					return powersupply.PowerSupplyLimit.CURRENT
				return powersupply.PowerSupplyLimit.NONE

			raise CommunicationError_ProtocolViolation(f"Unknown response for mode query (CVCC) {resp}")

class DP832LAN(DP832):
	def __init__(
		self,

		address = None,
		port = 5555,

		debug = False,
		timeoutRetry = 3,
		readbackRetry = 3,
		commandDelay = 0.1,

		logLevel = "ERROR"

	):
		if not isinstance(address, str):
			raise ValueError("Address has to be a string")
		if not isinstance(port, int):
			raise ValueError("Port has to be an integer")
		if (int(port) <= 0) or (int(port) > 65535):
			raise ValueError("Port has to be an integer in range from 1 to 65535 (default 5555)")

		self._port = port
		self._host = address

		self._socket = None

		super().__init__(debug, timeoutRetry, readbackRetry, commandDelay, logLevel)

		atexit.register(self.__close)


	def __close(self):
		atexit.unregister(self.__close)
		if self._socket is not None:
			#self._off()
			self._disconnect()
		pass

	def __enter__(self):
		if self._usedConnect:
			raise ValueError("Cannot use context management on a connected port")

		self._connect()
		self._usesContext = True

		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.__close()
		self.__usesContext = False

	def _connect(self):
		if self._socket is None:
			self._logger.debug(f"Connecting to {self._host} : {self._port}")

			self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self._socket.connect((self._host, self._port))

			# ToDo: Verify IDN string
			self._logger.debug(f"Requesting identity")
			idnString = self._idn(raw = True)
			if not idnString:
				raise CommunicationError_ProtocolViolation("Device did not respond to identification command")

			self._logger.debug(f"ID: {idnString}")

			parts = idnString.split(",")
			if parts[0] != "RIGOL TECHNOLOGIES":
				raise CommunicationError_ProtocolViolation(f"Expected manufacturer RIGOL TECHNOLOGIES, got {parts[0]}")
			if parts[1] != "DP832":
				raise CommunicationError_ProtocolViolation(f"Expected device typ DP832, got {parts[1]}")

			self._serialNumber = parts[2]

			versionparts = parts[3].split(".")
			if len(versionparts) != 3:
				raise CommunicationError_ProtocolViolation(f"Version number has to consist of 3 parts, got {parts[3]}")

			self._version = ( versionparts[0], versionparts[1], versionparts[2] )
			self._logger.info(f"Device {self._serialNumber} ready")
		else:
			self._logger.debug("Device already connected")
		return True

	def _disconnect(self):
		if self._socket is not None:
			self._socket.shutdown(socket.SHUT_RDWR)
			self._socket.close()
			self._socket = None

	def _isConnected(self):
		if self._socket is not None:
			return True
		else:
			return False

	def _scpi_command(self, command):
		if not self._isConnected():
			raise CommunicationError_NotConnected("Device is not connected")

		self._logger.debug(f"> {command}")
		self._socket.sendall((command + "\n").encode())
		readData = ""

		# ToDo: Implement timeout handling ...
		while True:
			dataBlock = self._socket.recv(4096*10)
			dataBlockStr = dataBlock.decode("utf-8")
			readData = readData + dataBlockStr
			if dataBlockStr[-1] == '\n':
				break

		self._logger.debug(f"< {readData.strip()}")
		return readData.strip()

	def _scpi_command_noreply(self, command):
		if not self._isConnected():
			raise CommunicationError_NotConnected("Device is not connected")

		self._logger.debug(f"> {command}")
		self._socket.sendall((command+"\n").encode())
		return


if __name__ == "__main__":
	with DP832LAN(address = "10.4.1.12", logLevel = "DEBUG") as dp:
		print(dp._idn())
		sleep(5)
		dp._setChannelEnable(True, 1)
		sleep(5)
		dp._setVoltage(1, 1)
		dp._setCurrent(1, 1)
		print(f"Voltage: {dp._getVoltage(1)}, Current: {dp._getCurrent(1)}; Mode: {dp._getLimitMode(1)}")
		sleep(5)
		dp._setVoltage(10, 1)
		dp._setCurrent(2, 1)
		print(f"Voltage: {dp._getVoltage(1)}, Current: {dp._getCurrent(1)}; Mode: {dp._getLimitMode(1)}")
		sleep(5)
		dp._setVoltage(0, 1)
		dp._setCurrent(0, 1)
		print(f"Voltage: {dp._getVoltage(1)}, Current: {dp._getCurrent(1)}; Mode: {dp._getLimitMode(1)}")
		dp._setChannelEnable(False, 1)
		sleep(1)