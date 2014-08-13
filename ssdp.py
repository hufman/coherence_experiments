#!/usr/bin/env python

from twisted.internet import reactor
from coherence.upnp.core.ssdp import SSDPServer
from coherence.upnp.core.msearch import MSearch
from coherence.upnp.core.device import Device, RootDevice
from coherence.extern import louie


class DevicesListener(object):
	def __init__(self):
		self.ssdp = SSDPServer()
		self.msearch = MSearch(self.ssdp, test=False)
		self.devices = []
		louie.connect(self.ssdp_detected, 'Coherence.UPnP.SSDP.new_device', louie.Any)
		louie.connect(self.ssdp_deleted, 'Coherence.UPnP.SSDP.removed_device', louie.Any)
		louie.connect(self.device_found, 'Coherence.UPnP.RootDevice.detection_completed', louie.Any)
		self.msearch.double_discover()

	def _get_device_by_id(self, id):
		found = None
		for device in self.devices:
			this_id = device.get_id()
			if this_id[:5] != 'uid:':
				this_id = this_id[5:]
			if this_id == id:
				found = device
				break
		return found

	def _get_device_by_usn(self, usn):
		found = None
		for device in self.devices:
			if device.get_usn() == usn:
				found = device
				break
		return found

	def ssdp_detected(self, device_type, infos, *args, **kwargs):
		print("Found ssdp %s"%(infos,))
		if infos['ST'] == 'upnp:rootdevice':
			root = RootDevice(infos)
		else:
			root_id = infos['USN'][:-len(infos['ST']) - 2]
			root = self._get_device_by_id(root_id)
			device = Device(infos, root)
	def ssdp_deleted(self, device_type, infos, *args, **kwargs):
		device = self._get_device_with_usn(infos['USN'])
		if device:
			louie.send('Coherence.UPnP.Device.removed', None, usn=infos['USN'])
			self.devices.remove(device)
			device.remove()
			if infos['ST'] == 'upnp:rootdevice':
				louie.send('Coherence.UPnP.RootDevice.removed', None, usn=infos['USN'])

	def device_found(self, device):
		print("Found device %s"%(device,))
		self.devices.append(device)

devices = DevicesListener()

print("Beginning")
reactor.run()
