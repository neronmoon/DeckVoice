import os
import sys
import logging

try:
    import decky
except ImportError:
    import decky_plugin as decky

logging.basicConfig(
    filename="/tmp/deckvoice.log",
    format="DeckVoice: %(asctime)s %(levelname)s %(message)s",
    filemode="w+",
    force=True,
)
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

plugin_path = os.environ["DECKY_PLUGIN_DIR"]

for dependency_path in (
    os.path.join(plugin_path, "bin", "python"),
    os.path.join(plugin_path, "lib"),
):
    if os.path.exists(dependency_path):
        sys.path.insert(0, dependency_path)
        logger.info("Added dependency path: %s", dependency_path)

try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except ImportError:
    pass

bundled_portaudio = os.path.join(plugin_path, "bin", "lib", "libportaudio.so.2")
if os.path.isfile(bundled_portaudio):
    import ctypes.util
    system_find_library = ctypes.util.find_library

    def find_bundled_library(name):
        if name == "portaudio":
            return bundled_portaudio
        return system_find_library(name)

    ctypes.util.find_library = find_bundled_library
    logger.info("Using bundled PortAudio: %s", bundled_portaudio)

sys.path.insert(0, plugin_path)

from deckvoice.plugin import Plugin  # noqa: E402
