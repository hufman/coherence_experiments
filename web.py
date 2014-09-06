#import treq
from klein import Klein
import urllib
from devices import DeviceManager
device_list = DeviceManager()

app = Klein()

import jinja2
templates = jinja2.Environment(loader=jinja2.FileSystemLoader('templates'), trim_blocks=True, autoescape=True)

@app.route('/devices', branch=True)
def devices(request):
	path = urllib.unquote(request.path)
	if path in ['/devices', '/devices/']:
		return format_device_list(request)

def format_device_list(request):
	template = templates.get_template('devices.djhtml')
	return template.render(devices=device_list.devices)

app.run("0.0.0.0", 8080)
