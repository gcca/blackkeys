import sanic
import sanic.response
from blackkeys.blueprints.chrome import RenderAppPage

blueprint = sanic.Blueprint("stores")

STORE_TINTS = {
    "indigo": {"bg": "bg-indigo-500/10", "text": "text-indigo-500"},
    "pink": {"bg": "bg-pink-500/10", "text": "text-pink-500"},
    "green": {"bg": "bg-green-500/10", "text": "text-green-600"},
    "orange": {"bg": "bg-orange-500/10", "text": "text-orange-500"},
    "teal": {"bg": "bg-teal-500/10", "text": "text-teal-600"},
    "yellow": {"bg": "bg-yellow-500/10", "text": "text-yellow-600"},
    "red": {"bg": "bg-red-500/10", "text": "text-red-500"},
    "purple": {"bg": "bg-purple-500/10", "text": "text-purple-500"},
    "blue": {"bg": "bg-blue-500/10", "text": "text-blue-500"},
}

FEATURED_STORES = (
    {
        "name": "Samsung",
        "category": "Electronics",
        "location": "Level 2 · Wing A",
        "logo_url": "https://d2pm4x1rp707yw.cloudfront.net/brands/279",
        "tint": "indigo",
    },
    {
        "name": "Zara",
        "category": "Fashion",
        "location": "Level 1 · Wing B",
        "logo_url": "https://d2pm4x1rp707yw.cloudfront.net/brands/zara_logo.png",
        "tint": "pink",
    },
    {
        "name": "Starbucks Coffee",
        "category": "Coffee",
        "location": "Level 1 · Food Court",
        "logo_url": "https://d2pm4x1rp707yw.cloudfront.net/brands/30",
        "tint": "green",
    },
    {
        "name": "Nike",
        "category": "Sportswear",
        "location": "Level 2 · Wing C",
        "logo_url": "https://d2pm4x1rp707yw.cloudfront.net/brands/71",
        "tint": "orange",
    },
)

FEED_STORES = (
    {
        "name": "Ibero Librerias",
        "category": "Bookstore",
        "location": "Level 1 · Wing A",
        "blurb": "Weekend author signing event this Saturday at 2 PM.",
        "logo_url": "https://d2pm4x1rp707yw.cloudfront.net/brands/59",
        "image_height": 180,
        "tint": "teal",
    },
    {
        "name": "Cool Box",
        "category": "Electronics",
        "location": "Level 2 · Wing A",
        "blurb": None,
        "logo_url": "https://d2pm4x1rp707yw.cloudfront.net/brands/266",
        "image_height": 120,
        "tint": "indigo",
    },
    {
        "name": "Pandora",
        "category": "Jewelry",
        "location": "Level 1 · Wing B",
        "blurb": "New charm collection just arrived.",
        "logo_url": "https://d2pm4x1rp707yw.cloudfront.net/brands/pandora_logo.png",
        "image_height": 170,
        "tint": "pink",
    },
    {
        "name": "Plaza Vea",
        "category": "Supermarket",
        "location": "Level 0 · Anchor",
        "blurb": None,
        "logo_url": "https://d2pm4x1rp707yw.cloudfront.net/brands/plaza_vea_logo.png",
        "image_height": 110,
        "tint": "green",
    },
    {
        "name": "Inkafarma",
        "category": "Pharmacy",
        "location": "Level 0 · Wing C",
        "blurb": None,
        "logo_url": "https://d2pm4x1rp707yw.cloudfront.net/brands/inkafarma_logo.png",
        "image_height": 130,
        "tint": "red",
    },
    {
        "name": "Cinnabon",
        "category": "Bakery",
        "location": "Level 1 · Food Court",
        "blurb": "Try the new seasonal caramel roll.",
        "logo_url": "https://d2pm4x1rp707yw.cloudfront.net/brands/cinnabon_logo.png",
        "image_height": 190,
        "tint": "orange",
    },
    {
        "name": "Renzo Costa",
        "category": "Accessories",
        "location": "Level 2 · Wing B",
        "blurb": None,
        "logo_url": "https://d2pm4x1rp707yw.cloudfront.net/brands/renzo_costa_logo.png",
        "image_height": 150,
        "tint": "purple",
    },
    {
        "name": "Lego",
        "category": "Toys",
        "location": "Level 2 · Wing C",
        "blurb": "Build-and-play table open all weekend.",
        "logo_url": "https://d2pm4x1rp707yw.cloudfront.net/brands/lego_logo.png",
        "image_height": 160,
        "tint": "yellow",
    },
)


def StoreView(item: dict[str, object]) -> dict[str, object]:
    tint = STORE_TINTS[item["tint"]]
    return {
        **item,
        "tint_bg_class": tint["bg"],
        "tint_text_class": tint["text"],
    }


@blueprint.get("/stores/")
async def Stores(_: sanic.Request) -> sanic.HTTPResponse:
    return sanic.response.html(
        RenderAppPage(
            "stores",
            title="Stores",
            active_tab="stores",
            featured_stores=[StoreView(item) for item in FEATURED_STORES],
            feed_stores=[StoreView(item) for item in FEED_STORES],
        )
    )
