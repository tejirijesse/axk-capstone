from axk_capstone.web import page

no_cache = 1


def get_context(context):
    return page(context, "chain", "AXK Chain Explorer")
