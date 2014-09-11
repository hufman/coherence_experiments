from twisted.internet import reactor, task
from twisted.web.resource import Resource
from twisted.web.server import Site

from coherence.upnp.core.ssdp import SSDPServer
from webrequests import proxy_to, get

import functools
import json
import logging
logging.basicConfig(level=logging.DEBUG)
import socket
from urllib import quote as urlquote
from urlparse import urljoin

REMOTE_SERVERS = ['http://badasp:8080/devices/']
pollers = {}
ssdp = SSDPServer()


def ensure_utf8_bytes(v):
	""" Glibly stolen from the Klein source code """
	if isinstance(v, unicode):
		v = v.encode("utf-8")
	return v
def ensure_utf8(fun):
	@functools.wraps(fun)
	def decorator(*args, **kwargs):
		return ensure_utf8_bytes(fun(*args, **kwargs))
	return decorator

class UpnpClientResource(Resource):
	isLeaf = True

	def __init__(self, remote_url):
		if len(remote_url) > 0 and remote_url[-1] != '/':
			remote_url = remote_url + '/'
		self.remote_url = remote_url

	@ensure_utf8
	def render(self, request):
		return proxy_to(request, self.get_proxied_url(request.uri))

	def get_proxied_url(self, url):
		# base is devices/
		if len(url)>1 and url[0] == '/':
			url = url[1:]
		return self.remote_url + url

class RemoteDevice(object):
	def __init__(self, remote_url, usn, location, st, server_id, subdevices):
		# remote url is server/devices/{uuid}
		# location is /desc.xml
		#
		self.remote_url = remote_url
		resource = UpnpClientResource(remote_url)
		factory = Site(resource)
		
		self.server = reactor.listenTCP(0, factory)
		host = self.server.getHost()
		proxylocation = 'http://%s:%s/%s'%(self._get_local_ip(), host.port, location)
		logging.info("Creating device proxy at %s to %s"%(proxylocation, remote_url))
		ssdp.register('local', usn, st, proxylocation, server_id, host=host.host)
		for sd in subdevices:
			usn = sd['usn']
			st = sd['st']
			ssdp.register('local', usn, st, proxylocation, server_id, host=host.host)
		# tell ssdp where self.server.getHost().port is
	def _get_local_ip(self):
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		s.connect(('8.8.8.8', 80))
		ip = s.getsockname()[0]
		s.close()
		return ip
	def stop(self):
		self.server.stopListening()


class ServerPoller(object):
	def __init__(self, url):
		self.url = url
		self.devices = {}
		self.poller_thread = task.LoopingCall(self.poll)
		self.poller_thread.start(60.0)

	def poll(self):
		# start the connection
		d = get(url, {'Accept':['application/json']})
		d.addCallback(self.on_response)
		d.addErrback(self.on_error)

	def on_response(self, data):
		try:
			obj = json.loads(data['content'])
		except:
			logging.info('Received invalid json data from %s'%(self.url,))
			logging.debug('Received invalid json data from %s: %s'%(self.url, data))
			return

		for device in obj.get('devices', []):
			uuid = device['uuid']
			device_url = urljoin(self.url, urlquote(uuid)) + '/'
			usn = device['usn']
			st = device['st']
			location = device['location']  # relative to devices, includes uuid
			location = location.split('/', 1)[-1] # relative to device root
			subdevices = device['subdevices']
			if uuid not in self.devices:
				self.devices[uuid] = RemoteDevice(device_url, usn, location, st, uuid, subdevices)

	def on_error(self, err):
		print(err)

for url in REMOTE_SERVERS:
	poller = ServerPoller(url)
	pollers[url] = poller

reactor.run()
