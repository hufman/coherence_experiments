from zope.interface import implements
from twisted.internet import reactor
from twisted.internet.defer import succeed, Deferred
from twisted.internet.protocol import Protocol
from twisted.web.client import Agent
from twisted.web.http_headers import Headers
from twisted.web.iweb import IBodyProducer
from twisted.web.server import NOT_DONE_YET
from FileBodyProducer import FileBodyProducer

def proxy_to(request, url):
	""" Send a new request to the given url, based on the given request """
	def onResponse(response):
		# proxied response started coming back, headers are load ed
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
	agent = Agent(reactor)
	body = StringProducer(data)
	fetcher = agent.request(method, url, headers, body)
	fetcher.addCallback(onResponse)
	fetcher.addErrback(d.errback)
	return d
get = lambda *args: fetch('get', *args)
post = lambda *args: fetch('post', *args)