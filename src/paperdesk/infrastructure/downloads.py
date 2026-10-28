from __future__ import annotations

import urllib.error
import urllib.request

from .. import APP_ID, __version__
from ..domain.errors import InvalidInput, ProviderUnavailable
from ..ports.downloads import FileDownloader
from ..i18n import _


class UrllibDownloader(FileDownloader):
    def download(self, url: str, *, max_bytes: int, timeout: float) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": f"{APP_ID}/{__version__} (paper reader)"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read(max_bytes + 1)
        except urllib.error.HTTPError as error:
            raise InvalidInput(_("내려받지 못했어요 (HTTP {code}).", code=error.code)) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise ProviderUnavailable(_("내려받지 못했어요: {reason}", reason=str(getattr(error, 'reason', error)))) from error
        if len(data) > max_bytes:
            raise InvalidInput(_("파일이 너무 커요."))
        return data

