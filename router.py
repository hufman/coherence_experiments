import logging
import urllib
from twisted.web.server import NOT_DONE_YET
logger = logging.getLogger(__name__)

from webrequests import proxy_to, proxy_response

class ST:
	MediaReceiver = 'urn:microsoft.com:service:X_MS_MediaReceiverRegistrar:1'
	ConnectionManager = 'urn:schemas-upnp-org:service:ConnectionManager:1'
	ContentDirectory = 'urn:schemas-upnp-org:service:ContentDirectory:1'

class URL:
	descURL = '<DESCURL>'
	SCPDURL = '<SCPDURL>'
	controlURL = '<controlURL>'
	eventSubURL = '<eventSubURL>'
	presentationURL = '<presentationURL>'

class Router(object):
	def __init__(self, baseurl):
		self.customizers = {}
		self.customizer_rules = []
		self.postprocessors = {}
		self.postprocessor_rules = []
		self.devices = []
		self.base = baseurl

	def customize(self, st, url):
		""" Registers a function to replace the normal proxy system for a url """
		logger.info('Registering custom hook for <%s>/%s'%(st, url))
		def decorator(fun):
			matcher = self._add_matching_rule(self.customizer_rules, st, url, fun)
			self._add_matcher(self.customizers, matcher)
			return fun
		return decorator

	def postprocess(self, st, url):
		""" Registers a function to modify a proxied response """
		logger.info('Registering postprocess hook for <%s>/%s'%(st, url))
		def decorator(fun):
			matcher = self._add_matching_rule(self.postprocessor_rules, st, url, fun)
			self._add_matcher(self.postprocessors, matcher)
			return fun
		return decorator

	def add_device(self, device):
		""" Add a device to be hooked by any matchers """
		logger.debug('Adding device %s to routing hooks'%(device,))
		self.devices.append(device)
		self._add_device(self.customizer_rules, self.customizers, device)
		self._add_device(self.postprocessor_rules, self.postprocessors, device)

	def dispatch_device_request(self, request, url):
		""" request is the incoming request """
		""" url is the backend url """
		rest = request.uri[len(self.base):]
		front_url = urllib.unquote(rest)
		if front_url in self.customizers:
			logger.debug('Routing customizer %s'%(front_url,))
			return self.customizers[url](request, url)
		if front_url in self.postprocessors:
			logger.debug('Routing postprocessor %s'%(front_url,))
			def errback(*args):
				request.setResponseCode(500)
				request.write('Proxy error: %s'%(args[0].getErrorMessage(),))
				logging.info('Proxy error: %s'%(args[0].getErrorMessage(),))
				logging.debug('Proxy error: %s'%(args[0].getTraceback(),))
				request.finish()

			postprocessor = self.postprocessors[front_url]
			response = proxy_response(request, url)
			response.addCallback(lambda data: postprocessor(request, data))
			response.addErrback(errback)
			return NOT_DONE_YET
		logger.debug('Handling device request %s'%(request.uri,))
		return proxy_to(request, url)

	def _add_matching_rule(self, rules, st, url, fun):
		""" Registers a matcher to hook on to devices """
		def matcher(device):
			""" Given a device, return a (url,fun) to hook on, or None """
			if url == URL.descURL:
				finalurl = device.get_location()
				finalurl = finalurl[finalurl.find('/', 9):]
				finalurl = self._get_device_url(device, finalurl)
				logger.debug("Applied a hook <%s>/%s (%s) to %s"%(st, url, finalurl, device))
				return (finalurl, fun)
			for s in device.get_services():
				if st == s.get_type():
					if url == URL.SCPDURL:
						finalurl = s.scpd_url
					elif url == URL.controlURL:
						finalurl = s.control_url
					elif url == URL.eventSubURL:
						finalurl = s.event_sub_url
					elif url == URL.presentationURL:
						finalurl = s.presentation_url
					else:
						finalurl = url
					finalurl = self._get_device_url(device, finalurl)
					logger.debug("Applied a hook <%s>/%s (%s) to %s"%(st, url, finalurl, device))
					return (finalurl, fun)
			logger.debug("Didn't apply a hook <%s>/%s to %s"%(st, url, device))
			return None
		rules.append(matcher)
		return matcher

	def _get_device_url(self, device, url):
		if len(url)>0 and url[0] != '/':
			url = '/' + url
		url = device.get_id() + url
		return url

	def _add_matcher(self, subscription, matcher):
		""" When a new matcher happens, add it to any matching devices """
		for device in self.devices:
			ret = matcher(device)
			if ret:
				subscription[ret[0]] = ret[1]
	def _add_device(self, matchers, subscription, device):
		""" When a new device appears, subscribe it with any matches """
		for matcher in matchers:
			ret = matcher(device)
			if ret:
				subscription[ret[0]] = ret[1]

class ClientRouter(Router):
	""" A special router that assumes only one device """
	""" Just matches on the ST and URL instead of with uuid """
	def _get_device_url(self, device, url):
		if len(url)>0 and url[0] == '/':
			url = url[1:]
		return url
