#import treq
from twisted.internet import reactor
from twisted.web.resource import Resource
from twisted.web.server import Site

import functools
import jinja2
import urllib

from devices import DeviceManager
from FileBodyProducer import FileBodyProducer

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

class UpnpResource(Resource):
	isLeaf = True
	def __init__(self):
		self.templates = jinja2.Environment(loader=jinja2.FileSystemLoader('templates'), trim_blocks=True, autoescape=True)
		self.device_list = DeviceManager()

	@ensure_utf8
	def render(self, request):
		if request.path in ['/devices', '/devices/']:
			return self.devices(request)

	def devices(self, request):
		path = urllib.unquote(request.path)
		if path in ['/devices', '/devices/']:
			return self.format_device_list(request)

	def format_device_list(self, request):
		template = self.templates.get_template('devices.djhtml')
		return template.render(devices=self.device_list.devices)

resource = UpnpResource()
factory = Site(resource)
reactor.listenTCP(8080, factory)
reactor.run()
