from django.utils.http import url_has_allowed_host_and_scheme


def safe_return_url(request, target, fallback):
    """Accept concrete same-site URLs, never untrusted route names or controls."""
    target = target or ''
    if any(ord(char) < 32 or ord(char) == 127 for char in target):
        return fallback
    target = target.strip()
    if '\\' in target or not target.startswith(('/', 'http://', 'https://')):
        return fallback
    if not url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return fallback
    return target
