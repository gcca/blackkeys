#[macro_use]
extern crate rocket;

#[get("/healthcheck")]
fn healthcheck() -> &'static str {
    "🍻"
}

#[launch]
fn rocket() -> _ {
    rocket::build().mount("/", routes![healthcheck])
}
