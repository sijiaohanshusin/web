"""Gmail-only IMAPS with scoped encrypted DNS and normal TLS identity checking."""
import imaplib
import ipaddress
import json
import socket
import time
from urllib.request import Request, urlopen

DNS_CACHE = {'until': 0, 'addresses': []}


def addresses():
    if DNS_CACHE['until'] > time.monotonic():
        return DNS_CACHE['addresses']
    try:
        request = Request('https://dns.alidns.com/resolve?name=imap.gmail.com&type=A',
                          headers={'Accept': 'application/dns-json'})
        with urlopen(request, timeout=3) as response:
            data = json.loads(response.read(16384))
        result = [record['data'] for record in data.get('Answer', [])
                  if record.get('type') == 1 and ipaddress.ip_address(record['data']).is_global]
        if data.get('Status') == 0 and result:
            DNS_CACHE.update(until=time.monotonic() + 120, addresses=result[:2])
            return result[:2]
    except Exception:
        pass
    return ['imap.gmail.com']


class GmailIMAP(imaplib.IMAP4_SSL):
    def __init__(self, *args, **kwargs):
        self.deadline = time.monotonic() + 18
        super().__init__(*args, **kwargs)

    def remaining(self):
        left = self.deadline - time.monotonic()
        if left <= 0:
            DNS_CACHE.update(until=0, addresses=[])
            raise TimeoutError('Gmail operation deadline exceeded')
        return min(5, left)

    def send(self, data):
        self.sock.settimeout(self.remaining())
        return super().send(data)

    def readline(self):
        self.sock.settimeout(self.remaining())
        return super().readline()

    def read(self, size):
        self.sock.settimeout(self.remaining())
        return super().read(size)

    def _create_socket(self, timeout):
        if self.host != 'imap.gmail.com' or self.port != 993:
            raise ValueError('Only Gmail IMAPS is allowed')
        last = None
        for address in addresses():
            connection = None
            try:
                connection = socket.create_connection((address, self.port), self.remaining())
                connection.settimeout(self.remaining())
                return self.ssl_context.wrap_socket(connection, server_hostname=self.host)
            except (OSError, ValueError) as exc:
                last = exc
                if connection is not None:
                    connection.close()
        DNS_CACHE.update(until=0, addresses=[])
        raise last or OSError('No Gmail address available')
