from blackkeys.navigation import NavPrimaryItems, NavSearchItem
from blackkeys.templating import RenderPage
from blackkeys.themes import ThemeChoices


def RenderAppPage(template: str, *, active_tab: str, **context: object) -> str:
    return RenderPage(
        template,
        show_theme_picker=True,
        themes=ThemeChoices(),
        show_nav=True,
        nav_primary_items=NavPrimaryItems(active_tab),
        nav_search_item=NavSearchItem(active_tab),
        **context,
    )
