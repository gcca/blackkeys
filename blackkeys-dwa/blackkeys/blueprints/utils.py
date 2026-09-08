import sanic


def IsHtmx(request: sanic.Request) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"
