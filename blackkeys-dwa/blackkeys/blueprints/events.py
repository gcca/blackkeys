import sanic
import sanic.response
from blackkeys.blueprints.chrome import RenderAppPage

blueprint = sanic.Blueprint("events")

EVENT_TINTS = {
    "purple": {
        "text": "text-purple-600",
        "from": "from-purple-500",
        "to": "to-purple-500/60",
        "solid": "bg-purple-500",
    },
    "pink": {
        "text": "text-pink-600",
        "from": "from-pink-500",
        "to": "to-pink-500/60",
        "solid": "bg-pink-500",
    },
    "orange": {
        "text": "text-orange-600",
        "from": "from-orange-500",
        "to": "to-orange-500/60",
        "solid": "bg-orange-500",
    },
    "green": {
        "text": "text-green-600",
        "from": "from-green-500",
        "to": "to-green-500/60",
        "solid": "bg-green-500",
    },
    "indigo": {
        "text": "text-indigo-600",
        "from": "from-indigo-500",
        "to": "to-indigo-500/60",
        "solid": "bg-indigo-500",
    },
    "yellow": {
        "text": "text-yellow-600",
        "from": "from-yellow-500",
        "to": "to-yellow-500/60",
        "solid": "bg-yellow-500",
    },
    "teal": {
        "text": "text-teal-600",
        "from": "from-teal-500",
        "to": "to-teal-500/60",
        "solid": "bg-teal-500",
    },
    "brown": {
        "text": "text-amber-800",
        "from": "from-amber-700",
        "to": "to-amber-700/60",
        "solid": "bg-amber-700",
    },
}

FEATURED_EVENTS = (
    {
        "title": "Live Jazz Night",
        "category": "Music",
        "day": "12",
        "month": "OCT",
        "time": "7:00 PM",
        "location": "Central Atrium",
        "icon": "🎵",
        "tint": "purple",
    },
    {
        "title": "Fashion Week Runway",
        "category": "Fashion",
        "day": "18",
        "month": "OCT",
        "time": "6:00 PM",
        "location": "Main Stage",
        "icon": "✨",
        "tint": "pink",
    },
    {
        "title": "Weekend Food Fair",
        "category": "Food",
        "day": "25",
        "month": "OCT",
        "time": "11:00 AM",
        "location": "Food Court",
        "icon": "🍴",
        "tint": "orange",
    },
)

UPCOMING_EVENTS = (
    {
        "title": "Kids Painting Workshop",
        "category": "Family",
        "day": "14",
        "month": "OCT",
        "time": "3:00 PM",
        "location": "Level 3 Activity Hall",
        "tint": "green",
    },
    {
        "title": "Tech Expo",
        "category": "Technology",
        "day": "16",
        "month": "OCT",
        "time": "10:00 AM",
        "location": "Level 2 Exhibition Hall",
        "tint": "indigo",
    },
    {
        "title": "Holiday Light Show",
        "category": "Family",
        "day": "22",
        "month": "OCT",
        "time": "8:00 PM",
        "location": "Central Atrium",
        "tint": "yellow",
    },
    {
        "title": "Yoga at the Plaza",
        "category": "Wellness",
        "day": "29",
        "month": "OCT",
        "time": "8:00 AM",
        "location": "Rooftop Terrace",
        "tint": "teal",
    },
    {
        "title": "Charity Book Drive",
        "category": "Community",
        "day": "31",
        "month": "OCT",
        "time": "12:00 PM",
        "location": "Level 1 · Wing A",
        "tint": "brown",
    },
)


def FeaturedEventView(item: dict[str, object]) -> dict[str, object]:
    tint = EVENT_TINTS[item["tint"]]
    return {
        **item,
        "tint_from_class": tint["from"],
        "tint_to_class": tint["to"],
        "tint_text_class": tint["text"],
    }


def UpcomingEventView(item: dict[str, object]) -> dict[str, object]:
    tint = EVENT_TINTS[item["tint"]]
    return {**item, "tint_solid_class": tint["solid"]}


@blueprint.get("/events/")
async def Events(_: sanic.Request) -> sanic.HTTPResponse:
    return sanic.response.html(
        RenderAppPage(
            "events",
            title="Events",
            active_tab="events",
            featured_events=[
                FeaturedEventView(item) for item in FEATURED_EVENTS
            ],
            upcoming_events=[
                UpcomingEventView(item) for item in UPCOMING_EVENTS
            ],
        )
    )
