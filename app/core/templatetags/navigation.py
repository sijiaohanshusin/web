from django import template
from django.urls import reverse
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag(takes_context=True)
def nav_current(context, name):
    request = context.get('request')
    if not request:
        return ''
    url = reverse(name)
    if request.path == url:
        return mark_safe(' aria-current="page"')
    if url != '/' and request.path.startswith(url):
        return mark_safe(' aria-current="location"')
    return ''


@register.simple_tag(takes_context=True)
def nav_group(context, group):
    path = getattr(context.get('request'), 'path', '')
    prefixes = {'about': ('/works/', '/honors/', '/team/', '/news/', '/events/'),
                'learn': ('/resources/', '/learn/')}
    return mark_safe(' data-nav-current="true"') if path.startswith(prefixes.get(group, ())) else ''
