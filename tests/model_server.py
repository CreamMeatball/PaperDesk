"""Loopback-only question-model fixture; never connects to a real AI."""
import json
import sys
from pathlib import Path
from paperdesk.app import Application
from paperdesk.config import AppPaths
from paperdesk.infrastructure.secrets import MemorySecretStore
from paperdesk.infrastructure.settings_store import JsonSettingsStore
from paperdesk.platforms import LinuxPlatform
from paperdesk.ports.settings import Settings
from paperdesk.providers.registry import ProviderRegistry
from paperdesk.web.server import create_server
from .test_question_models import QuestionModelProvider

paths=AppPaths(Path(sys.argv[1]))
app=Application.build(paths=paths,platform=LinuxPlatform(),secrets=MemorySecretStore(),
    registry=ProviderRegistry([QuestionModelProvider]),settings_store=JsonSettingsStore(paths.settings_file,Settings()))
app.settings.update_general(provider=QuestionModelProvider.id,ui_language='en',auto_translate=False)
if not app.library.list():app.library.import_pdf('paper.pdf',Path(sys.argv[2]).read_bytes())
server=create_server(app,'127.0.0.1',0)
print(json.dumps({'url':server.url,'document':app.library.list()[0].id}),flush=True)
try:server.serve_forever()
except KeyboardInterrupt:pass
finally:server.server_close()
