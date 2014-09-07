#import treq
from twisted.internet import reactor
from twisted.internet.protocol import Protocol
from twisted.web.client import Agent
from twisted.web.resource import Resource
from twisted.web.server import Site, NOT_DONE_YET

import functools
import jinja2
import urllib
import urlparse

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
		self.templates.filters['get_device_icon'] = self.get_device_icon
		self.device_list = DeviceManager()

	@ensure_utf8
	def render(self, request):
		if request.path.startswith('/devices/'):
			return self.devices(request)

	def devices(self, request):
		path = urllib.unquote(request.path)
		if path == '/devices/':
			return self.format_device_list(request)
		rest = path[len('/devices/'):]
		slash_idx = rest.find('/')
		if slash_idx > 0:
			dev_id = rest[:slash_idx]
			device = self.device_list._get_device_by_id(dev_id)
			if device:
				url = urlparse.urljoin(device.get_location(), rest[slash_idx:])
				print(url)
				return self.proxied_to(request, url)
			else:
				print("Could not find device %s"%(dev_id,))

	def proxied_to(self, request, url):
		def onResponse(response):
			# proxied response started coming back, headers are loaded
			request.setResponseCode(response.code)
			request.responseHeaders = response.headers
			response.deliverBody(RequestWritingPrinter(request))
		def onFailure(_):
			request.setResponseCode(500)
			request.finish()

		class RequestWritingPrinter(Protocol):
			# used to send from the proxied response to the original request
			def __init__(self, request):
				self.request = request
			def dataReceived(self, bytes):
				self.request.write(bytes)
			def connectionLost(self, reason):
				self.request.finish()

		# start the connection
		agent = Agent(reactor)
		body = FileBodyProducer(request.content)
		d = agent.request(request.method, url, request.requestHeaders, body)
		d.addCallback(onResponse)

		# hold on to the request until later
		return NOT_DONE_YET

	def format_device_list(self, request):
		template = self.templates.get_template('devices.djhtml')
		return template.render(devices=self.device_list.devices)

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
