from django import template
from helpcenter import content

register = template.Library()


@register.inclusion_tag('helpcenter/contextual.html', takes_context=True)
def contextual_help(context):
    request = context.get('request')
    if request is None or request.path.startswith(('/help/', '/team/')):
        return {'tasks': []}
    candidates = []
    for item in content.visible(request.user):
        for route in item.routes:
            route = route.split('?')[0]
            if route != '/' and request.path.startswith(route):
                candidates.append((len(route), item))
                break
    candidates.sort(key=lambda pair: (-pair[0], pair[1].order))
    return {'tasks': [item for _, item in candidates[:2]]}
