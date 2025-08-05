"""
SSL Fix patch for bonk_mcp utils.py
Save this as: src/bonk_mcp/utils_patch.py
"""

import aiohttp
import ssl
import certifi

# Create SSL context with proper certificates
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

# Monkey-patch aiohttp ClientSession
original_client_session = aiohttp.ClientSession

class PatchedClientSession(original_client_session):
    def __init__(self, *args, **kwargs):
        if 'connector' not in kwargs:
            kwargs['connector'] = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
        super().__init__(*args, **kwargs)

# Apply the patch
aiohttp.ClientSession = PatchedClientSession

# Import this at the top of your scripts to apply the SSL fix
print("SSL patch applied successfully")