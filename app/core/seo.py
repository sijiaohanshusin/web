from xml.etree import ElementTree as ET
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_GET


@require_GET
def sitemap(request):
    """Only URLs selected by the same public querysets as the actual pages."""
    from news.models import Post
    from events.models import Event
    from projects.models import Project
    from showcase.models import Showcase
    ns = "http://www.sitemaps.org/schemas/sitemap/0.9"
    ET.register_namespace("", ns)
    root = ET.Element(f"{{{ns}}}urlset")
    def add(path):
        node = ET.SubElement(root, f"{{{ns}}}url")
        ET.SubElement(node, f"{{{ns}}}loc").text = settings.PUBLIC_SITE_URL + path
    for name in ("core:home", "core:recruit", "recruitment:index", "works:wall", "honors:wall", "team:wall", "news:list", "events:list", "files:list", "core:privacy"):
        add(reverse(name))
    add("/help/")
    guest = AnonymousUser()
    for pk in Post.objects.published().visible_to(guest).values_list("pk", flat=True).iterator():
        add(reverse("news:detail", args=[pk]))
    for pk in Event.objects.published().visible_to(guest).values_list("pk", flat=True).iterator():
        add(reverse("events:detail", args=[pk]))
    for pk in Project.public().values_list("pk", flat=True).iterator():
        add(reverse("works:detail", args=[pk]))
    for public_id in Showcase.objects.visible().values_list("pk", flat=True).iterator():
        add(reverse("team:detail", args=[public_id]))
    response = HttpResponse(ET.tostring(root, encoding="utf-8", xml_declaration=True), content_type="application/xml")
    response["Cache-Control"] = "no-store"
    return response
