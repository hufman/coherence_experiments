#import treq
from twisted.internet import reactor
from twisted.web.resource import Resource
from twisted.web.server import Site

import functools
import jinja2
import json
import traceback
import urllib
import urlparse
import xml.etree.ElementTree as ElementTree
ElementTree.register_namespace('upnp', 'urn:schemas-upnp-org:metadata-1-0/upnp/')
ElementTree.register_namespace('didl', 'urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/')

import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

try:
	import cStringIO as StringIO
except:
	import StringIO

from devices import DeviceManager
from router import Router, ST, URL
from webrequests import proxy_to

router = Router('/devices/')
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
		self.unlocked_ports = {}
		self.device_list.register('added', router.add_device)

	@ensure_utf8
	def render(self, request):
		try:
			if request.path.startswith('/devices/'):
				return self.devices(request)
		except:
			traceback.print_exc()
			raise

	def _get_device_for_uri(self, uri):
		""" Takes a request uri and returns a device that it corresponds to """
		rest = uri[len('/devices/'):]
		slash_idx = rest.find('/')
		dev_id = urllib.unquote(rest[:slash_idx])
		if dev_id in self.unlocked_ports:
			dev_id = dev_id[:dev_id.rfind(':')]
		device = self.device_list._get_device_by_id(dev_id)
		return device

	def devices(self, request):
		if request.uri == '/devices/':
			return self.format_device_list(request)
		rest = request.uri[len('/devices/'):]
		slash_idx = rest.find('/')
		device = self._get_device_for_uri(request.uri)
		dev_id = urllib.unquote(rest[:slash_idx])
		if device and self.is_device_whitelisted(device):
			dev_url = device.get_location()
			if dev_id in self.unlocked_ports:
				dev_port = dev_id[dev_id.rfind(':')+1:]
				urlparsed = urlparse.urlparse(device.get_location())
				proto, netloc = urlparsed[0:2]
				url_ip = netloc.split(':')[0]
				dev_url = '%s://%s:%s/'%(proto, url_ip, dev_port)
			url = urlparse.urljoin(dev_url, rest[slash_idx:])
			logger.debug(url)
			return router.dispatch_device_request(request, url)
		else:
			logger.info("Could not find device %s"%(dev_id,))
			request.setResponseCode(404)
			return 'Could not find device %s'%(dev_id,)

	def is_device_whitelisted(self, device):
		return any(['X_MS_MediaReceiver' in s.service_type or
		            'ContentDirectory' in s.service_type
		            for s in device.get_services()
		          ])

	def format_device_list(self, request):
		def whitelisted_devices(devices):
			return [
			    d for d in devices if self.is_device_whitelisted(d)
			]
		if 'json' not in request.requestHeaders.getRawHeaders('Accept', '')[0]:
			template = self.templates.get_template('devices.djhtml')
			return template.render(devices=whitelisted_devices(self.device_list.devices))
		else:
			devices = [{
				"uuid": d.get_id(),
				"usn": d.get_usn(),
				"st": d.get_st(),
				"server": d.server,
				"location": self.get_proxied_url(d, urlparse.urlparse(d.get_location())[2]),
				"subdevices": [{
					"usn": s.get_id()+"::"+s.service_type,
					"st": s.service_type,
					"location": self.get_proxied_url(d, urlparse.urlparse(d.get_location())[2])
					} for s in d.get_services()]
				} for d in whitelisted_devices(self.device_list.devices)]
			request.responseHeaders.setRawHeaders('Content-Type', ['application/json'])
			return json.dumps({"devices":devices})

	def get_proxied_url(self, device, url):
		# given a url on the device's upnp service
		# return a url relative to /devices/ to proxy to it
		# base is devices/
		if '://' in url:
			proto, netloc = urlparse.urlparse(device.get_location())[0:2]
			if ':' in netloc:
				dev_ip, dev_port = netloc.split(':', 1)
			else:
				dev_ip, dev_port = netloc, '443' if proto=='https' else '80'
			urlparsed = urlparse.urlparse(url)
			proto, netloc = urlparsed[0:2]
			if ':' in netloc:
				url_ip, url_port = netloc.split(':', 1)
			else:
				url_ip, url_port = netloc, '443' if proto=='https' else '80'
			prefix = '%s://%s' % (urlparsed[0:2])
			rest = url[len(prefix):]
			logger.debug("Comparing %s:%s to %s:%s"%(dev_ip, dev_port, url_ip, url_port))
			if url_ip == dev_ip and url_port == dev_port:
				result = device.get_id() + rest
				logger.debug('Converting same-device %s to %s'%(url, result))
				return result
			elif url_ip == dev_ip:
				unlocked_port = device.get_id() + ':' + url_port
				self.unlocked_ports[unlocked_port] = True
				result = unlocked_port + rest
				logger.debug('Converting same-device alt port %s to %s'%(url, result))
				return result
			else:
				logger.debug('Not converting external %s'%(url,))
				return url
		if len(url)>1 and url[0] != '/':
			url = '/' + url
		result = device.get_id() + url
		logger.debug('Converting upnp relative %s to %s'%(url, result))
		return result

	def rewrite_base(self, device, base):
		if urlparse.urljoin(device.get_location(), 'sub') == urlparse.urljoin(base, 'sub'):
			# unnecessary base
			return None
		return self.get_proxied_url(device, base)

	def get_device_icon(self, device):
		if len(device.icons) > 0:
			icon = sorted(device.icons, key=lambda i:abs(120-int(i['width'])))[0]
			icon_url = self.get_proxied_url(device, icon['realurl'])
			return icon_url
		else:
			return ''

	def hack_description_response(self, request, response_data):
		request.setResponseCode(response_data['code'])
		request.responseHeaders = response_data['headers']
		if 'xml' not in response_data['headers'].getRawHeaders('Content-Type', '')[0]:
			request.responseHeaders.setRawHeaders('Content-Length', [len(response_data['content'])])
			request.write(response_data['content'])
			request.finish()
			return
		request.responseHeaders.removeHeader('Content-Length')
		request.responseHeaders.removeHeader('Content-Encoding')
		# get the device that we're talking to, and its ip
		device = self._get_device_for_uri(request.uri)
		# load up the response
		upnp = 'urn:schemas-upnp-org:device-1-0'
		root = ElementTree.fromstring(response_data['content'])
		for urlbase in root.findall("./{%s}URLBase"%(upnp,)):
			newbase = self.rewrite_base(device, urlbase.text)
			if newbase:
				urlbase.text = newbase
			else:
				root.remove(newbase)
		# write out
		doc = ElementTree.ElementTree(root)
		docout = StringIO.StringIO()
		doc.write(docout, encoding='utf-8', xml_declaration=True)
		docoutstr = docout.getvalue()
		request.responseHeaders.setRawHeaders('Content-Length', [len(docoutstr)])
		request.write(docoutstr)
		request.finish()

	def hack_mediaserver_response(self, request, response_data):
		request.setResponseCode(response_data['code'])
		request.responseHeaders = response_data['headers']
		if 'xml' not in response_data['headers'].getRawHeaders('Content-Type', '')[0]:
			request.responseHeaders.setRawHeaders('Content-Length', [len(response_data['content'])])
			request.write(response_data['content'])
			request.finish()
			return
		request.responseHeaders.removeHeader('Content-Length')
		request.responseHeaders.removeHeader('Content-Encoding')
		# get the device that we're talking to, and its ip
		device = self._get_device_for_uri(request.uri)
		# load up response
		didl = 'urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/'
		upnp = 'urn:schemas-upnp-org:metadata-1-0/upnp/'
		root = ElementTree.fromstring(response_data['content'])
		for result in root.iter('Result'):
			resultdoc = ElementTree.fromstring(result.text.encode('utf-8'))
			for uritag in resultdoc.iter('{%s}albumArtURI'%(upnp,)):
				uritag.text = self.get_proxied_url(device, uritag.text).decode('utf-8')
			for uritag in resultdoc.iter('{%s}res'%(didl,)):
				uritag.text = self.get_proxied_url(device, uritag.text).decode('utf-8')
			result.text = ElementTree.tostring(resultdoc, encoding='utf-8').decode('utf-8')
		# write out
		doc = ElementTree.ElementTree(root)
		docout = StringIO.StringIO()
		doc.write(docout, encoding='utf-8', xml_declaration=True)
		docoutstr = docout.getvalue()
		request.responseHeaders.setRawHeaders('Content-Length', [len(docoutstr)])
		request.write(docoutstr)
		request.finish()

resource = UpnpResource()
router.postprocess(ST.ContentDirectory, URL.controlURL)(resource.hack_mediaserver_response)
router.postprocess(ST.ContentDirectory, URL.descURL)(resource.hack_description_response)

factory = Site(resource)
reactor.listenTCP(8080, factory)
reactor.run()
