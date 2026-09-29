import os

no_cache = 1

_PUBLIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "public")


def _stamp(rel):
    try:
        return int(os.path.getmtime(os.path.join(_PUBLIC, rel)))
    except OSError:
        return 0


def get_context(context):
    context.title = "AXK Chain Explorer"
    context.no_breadcrumbs = True
    context.show_sidebar = False
    # Cache-bust the page's own assets by modification time.
    context.css_v = _stamp("css/chain.css")
    context.js_v = _stamp("js/chain.js")
    return context
