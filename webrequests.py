from zope.interface import implements
from twisted.internet import reactor
from twisted.internet.defer import succeed, Deferred
from twisted.internet.protocol import Protocol
from twisted.web.client import Agent, ContentDecoderAgent, GzipDecoder
from twisted.web.http_headers import Headers
from twisted.web.iweb import IBodyProducer
from twisted.web.server import NOT_DONE_YET
from FileBodyProducer import FileBodyProducer

from urlparse import urlparse

def proxy_to(request, url):
	""" Send a new request to the given url, based on the given request """
	def onResponse(response):
		# proxied response started coming back, headers are load ed
		request.setResponseCode(response.code)
		request.responseHeaders = response.headers
		if 'xml' in request.responseHeaders.getRawHeaders('Content-Type', '')[0]:
			response.deliverBody(BufferedRequestWritingPrinter(request))
		else:
			response.deliverBody(RequestWritingPrinter(request))
	def onFailure(_):
		request.setResponseCode(502)
		request.finish()

	class BufferedRequestWritingPrinter(Protocol):
		# used to send from the proxied response to the original request
		def __init__(self, request):
			self.request = request
			self.buffer = ''
		def dataReceived(self, bytes):
			self.buffer = self.buffer + bytes
		def connectionLost(self, reason):
			self.request.responseHeaders.setRawHeaders('Content-Length', [len(self.buffer)])
			self.request.write(self.buffer)
			self.request.finish()

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
	headers = request.requestHeaders
	headers.setRawHeaders('Host', [urlparse(url)[1],])
	headers.removeHeader('Content-Length')
	d = agent.request(request.method, url, headers, body)
	d.addCallback(onResponse)

	# hold on to the request until later
	return NOT_DONE_YET

def proxy_response(request, url):
	""" Send a new request to the given url, return a deferred with content """
	d = Deferred()
	response_data = {'code':0, 'content':None, 'headers':Headers({})}
	class StringPrinter(Protocol):
		# used to record the result from a url fetch
		def __init__(self):
			self.buffer = ''
		def dataReceived(self, bytes):
			self.buffer = self.buffer + bytes
		def connectionLost(self, reason):
			response_data['content'] = self.buffer
			d.callback(response_data)
	def onResponse(response):
		# proxied response started coming back, headers are load ed
		response_data['code'] = response.code
		response_data['headers'] = response.headers
		response.deliverBody(StringPrinter())

	class RequestWritingPrinter(Protocol):
		# used to send from the proxied response to the original request
		def __init__(self, request):
			self.request = request
		def dataReceived(self, bytes):
			self.request.write(bytes)
		def connectionLost(self, reason):
			self.request.finish()

	# start the connection
	agent = ContentDecoderAgent(Agent(reactor), [('gzip', GzipDecoder)])
	body = FileBodyProducer(request.content)
	headers = request.requestHeaders
	headers.setRawHeaders('Host', [urlparse(url)[1]])
	headers.removeHeader('Content-Length')
	fetcher = agent.request(request.method, url, headers, body)
	fetcher.addCallback(onResponse)
	fetcher.addErrback(d.errback)
	return d

def fetch(method, url, headers={}, data=''):
	""" Fetches a page and returns a deferred with the response """
	headers = Headers(headers)
	d = Deferred()
	response_data = {'code':0, 'content':None, 'headers':Headers({})}
	class StringPrinter(Protocol):
		# used to record the result from a url fetch
		def __init__(self):
			self.buffer = ''
		def dataReceived(self, bytes):
			self.buffer = self.buffer + bytes
		def connectionLost(self, reason):
			response_data['content'] = self.buffer
			d.callback(response_data)
	class StringProducer(object):
		implements(IBodyProducer)
		def __init__(self, data):
			self.data = data
			self.length = len(data)
		def startProducing(self, consumer):
			consumer.write(self.data)
			return succeed(None)
		def pauseProducing(self):
			pass
		def stopProducing(self):
			pass

	def onResponse(response):
		# proxied response started coming back, headers are load
		response_data['code'] = response.code
		response_data['headers'] = response.headers
		response.deliverBody(StringPrinter())

	# start the connection
	agent = ContentDecoderAgent(Agent(reactor), [('gzip', GzipDecoder)])
	body = StringProducer(data)
	fetcher = agent.request(method, url, headers, body)
	fetcher.addCallback(onResponse)
	fetcher.addErrback(d.errback)
	return d
get = lambda *args: fetch('get', *args)
post = lambda *args: fetch('post', *args)
