"""Temporary loopback app for tests/browser/local_state.cjs; blocks external network access."""
import ipaddress
import json
import os
import socket
import sys
from pathlib import Path
from paperdesk.app import Application
from paperdesk.config import AppPaths
from paperdesk.ports.ai import CommandResult, CommandRunner
from paperdesk.web.server import create_server

# In-process network guard: the app may only connect to loopback, including provider probes.
original_connect = socket.socket.connect

def local_connect(sock, address):
    if isinstance(address, tuple):
        host = address[0]
        if host != 'localhost':
            try:
                local = ipaddress.ip_address(host).is_loopback
            except ValueError:
                local = False
            if not local:
                print('EXTERNAL_ATTEMPT ' + str(address), file=sys.stderr, flush=True)
                raise OSError('External network disabled for this verification')
    return original_connect(sock, address)
socket.socket.connect = local_connect

class NoCli(CommandRunner):
    def run(self, argv, *, input_text, cwd, timeout):
        return CommandResult(1, '', 'CLI disabled for offline verification')

app = Application.build(paths=AppPaths(Path(sys.argv[1])), runner=NoCli())
if not app.library.list():
    from tests.helpers import make_pdf
    fixture = os.environ.get('PAPERDESK_TEST_PDF')
    source = Path(fixture).read_bytes() if fixture else make_pdf([
        'A Local Paper Reader', 'Abstract',
        'We study how a reader can keep papers and annotations on the computer.',
        'The application saves completed translations without an external server.',
        '1. Introduction',
        'A local library lets readers organize papers and inspect their notes.',
        'All resources needed to display this paper are bundled with the app.',
    ])
    app.library.import_pdf('paper.pdf', source)
    app.library.import_pdf('second.pdf', make_pdf(['Second paper for conversation isolation.']))
    app.settings.update_general(provider='demo', ui_language='en', target_language='English')
server = create_server(app, '127.0.0.1', 0)
print(json.dumps({'url':server.url, 'docs':[d.id for d in app.library.list()]}), flush=True)
try:
    server.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    server.server_close()
