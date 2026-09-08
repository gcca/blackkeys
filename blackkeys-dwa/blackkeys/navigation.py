NAV_PRIMARY = (
    ("stores", "Stores", "/stores/", "🛍️"),
    ("events", "Events", "/events/", "✨"),
)

NAV_SEARCH = ("search", "Search", "/search/", "🔍")


def NavPrimaryItems(active: str) -> list[dict[str, object]]:
    return [
        {
            "key": key,
            "label": label,
            "href": href,
            "icon": icon,
            "active": key == active,
        }
        for key, label, href, icon in NAV_PRIMARY
    ]


def NavSearchItem(active: str) -> list[dict[str, object]]:
    key, label, href, icon = NAV_SEARCH
    return [
        {
            "key": key,
            "label": label,
            "href": href,
            "icon": icon,
            "active": key == active,
        }
    ]
