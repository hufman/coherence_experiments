#import treq
from twisted.internet import reactor
from twisted.web.resource import Resource
from twisted.web.server import Site

import functools
import jinja2
import json
import urllib
import urlparse

import logging
logging.basicConfig(level=logging.DEBUG)

from devices import DeviceManager
from webrequests import proxy_to

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
		self.templates.filters['get_device_icon'] = self.get_device_icon
		self.device_list = DeviceManager()

	@ensure_utf8
	def render(self, request):
		if request.path.startswith('/devices/'):
			return self.devices(request)

	def devices(self, request):
		if request.uri == '/devices/':
			return self.format_device_list(request)
		rest = request.uri[len('/devices/'):]
		slash_idx = rest.find('/')
		if slash_idx > 0:
			dev_id = urllib.unquote(rest[:slash_idx])
			device = self.device_list._get_device_by_id(dev_id)
			if device:
				url = urlparse.urljoin(device.get_location(), rest[slash_idx:])
				print(url)
				return proxy_to(request, url)
			else:
				print("Could not find device %s"%(dev_id,))

	def format_device_list(self, request):
		if 'json' not in request.requestHeaders.getRawHeaders('Accept', '')[0]:
			template = self.templates.get_template('devices.djhtml')
			return template.render(devices=self.device_list.devices)
		else:
			devices = [{
				"uuid": d.get_id(),
				"usn": d.get_usn(),
				"st": d.get_st(),
				"location": self.get_proxied_url(d, urlparse.urlparse(d.get_location())[2]),
				"subdevices": [{
					"usn": s.get_id()+"::"+s.service_type,
					"st": s.service_type,
					"location": self.get_proxied_url(d, urlparse.urlparse(d.get_location())[2])
					} for s in d.get_services()]
				} for d in self.device_list.devices]
			return json.dumps({"devices":devices})

	def get_proxied_url(self, device, url):
		# base is devices/
		if len(url)>1 and url[0] != '/':
			url = '/' + url
		return device.get_id() + url

	def get_device_icon(self, device):
		if len(device.icons) > 0:
			icon = sorted(device.icons, key=lambda i:abs(120-int(i['width'])))[0]
			icon_url = self.get_proxied_url(device, icon['realurl'])
			return icon_url
		else:
			return ''

resource = UpnpResource()
factory = Site(resource)
reactor.listenTCP(8080, factory)
reactor.run()
